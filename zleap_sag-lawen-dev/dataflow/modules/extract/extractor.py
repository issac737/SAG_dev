"""
事项提取器

主控制器 - 协调单篇文档的提取流程
"""

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import selectinload

from dataflow.core.ai.factory import get_embedding_client
from dataflow.core.ai.base import BaseLLMClient
from dataflow.core.prompt.manager import PromptManager
from dataflow.core.storage.elasticsearch import get_es_client
from dataflow.core.storage.repositories.entity_repository import EntityVectorRepository
from dataflow.core.storage.repositories.event_repository import EventVectorRepository
from dataflow.db import (
    SourceChunk,
    Entity,
    EntityType as DBEntityType,
    EventEntity,
    SourceEvent,
    get_session_factory,
)
from dataflow.exceptions import ExtractError
from dataflow.modules.extract.config import ExtractConfig
from dataflow.modules.extract.parser import EntityValueParser
from dataflow.modules.extract.processor import EventProcessor
from dataflow.utils import estimate_tokens, get_logger

logger = get_logger("extract.extractor")


# 不需要索引到 ES 的实体类型列表
# 原因：时间类型的属性通常具有一致性，不需要用于相似度计算和关联检索
# 如 start_time、end_time、created_time 等时间字段会影响相似度匹配，但实际不应该作为关联依据
ENTITY_TYPES_SKIP_ES_INDEX = [
    "time",
    "start_time",
    "end_time",
    "created_time",
    "updated_time",
    "tags",  # 关键词标签不需要向量索引
]


def should_index_entity_to_es(entity_type: str) -> bool:
    """
    判断实体类型是否应该索引到 ES

    Args:
        entity_type: 实体类型标识符

    Returns:
        True 表示应该索引，False 表示跳过
    """
    return entity_type not in ENTITY_TYPES_SKIP_ES_INDEX


class EventExtractor:
    """事项提取器（主控制器）"""

    def __init__(
        self,
        prompt_manager: PromptManager,
        model_config: Optional[Dict] = None,
    ):
        """
        初始化事项提取器

        Args:
            prompt_manager: 提示词管理器
            model_config: LLM配置字典（可选）
                - 如果传入：使用该配置
                - 如果不传：自动从配置管理器获取 'extract' 场景配置
        """
        self.prompt_manager = prompt_manager
        self.model_config = model_config
        self._llm_client = None  # 延迟初始化
        self.session_factory = get_session_factory()
        self.logger = get_logger("extract.extractor")
        
        # ES相关（延迟初始化）
        self.es_client = None
        self.event_repo = None
        self.entity_repo = None
    
    async def _get_llm_client(self) -> BaseLLMClient:
        """获取LLM客户端（懒加载）"""
        if self._llm_client is None:
            from dataflow.core.ai.factory import create_llm_client
            
            self._llm_client = await create_llm_client(
                scenario='extract',
                model_config=self.model_config
            )
        
        return self._llm_client
    

    async def extract(self, config: ExtractConfig) -> List[SourceEvent]:
        """
        提取事项（统一入口 - 新架构）
        
        工作流程：
        1. 加载所有chunks
        2. 按max_concurrency并发处理（Semaphore控制）
        3. 每个chunk由一个ExtractorAgent处理
        4. 合并所有结果
        5. 保存到数据库 + Elasticsearch
        6. 更新源状态为已完成

        Args:
            config: 提取配置

        Returns:
            所有chunks提取的事项列表

        Example:
            config = ExtractConfig(
                source_config_id="source-uuid",
                chunk_ids=["chunk-1", "chunk-2", "chunk-3"],
                max_concurrency=3
            )
            events = await extractor.extract(config)
        """
        self.logger.info(
            f"开始批量提取: chunks={len(config.chunk_ids)}, "
            f"并发数={config.max_concurrency}"
        )

        try:
            # 1. 加载所有chunks
            chunks = await self._load_chunks(config.chunk_ids)

            if not chunks:
                self.logger.warning("没有找到可用的chunks")
                return []

            # 2. 并发处理chunks（每个chunk一个Agent）
            all_events = await self._process_chunks_with_agents(chunks, config)
            
            self.logger.info(
                f"批量提取完成: chunks={len(chunks)}, events={len(all_events)}"
            )
            
            # 3. 按原文顺序重新排序并分配全局 rank
            if all_events:
                # 创建 chunk_id -> chunk.rank 的映射
                chunk_rank_map = {chunk.id: chunk.rank for chunk in chunks}
                
                # 排序规则：
                # 1. 先按 chunk.rank（保证 chunk 之间的顺序）
                # 2. 再按事项的时间（会话）或 chunk 内 rank（文档）
                def sort_key(event):
                    chunk_order = chunk_rank_map.get(event.chunk_id, 9999)
                    
                    # 会话类型：按时间排序
                    if event.source_type == "CHAT" and event.start_time:
                        event_order = event.start_time
                    # 文档类型：按 chunk 内 rank 排序
                    else:
                        event_order = event.rank or 0
                    
                    return (chunk_order, event_order)
                
                all_events.sort(key=sort_key)
                
                # 重新分配全局连续 rank
                for i, event in enumerate(all_events):
                    event.rank = i
                
                self.logger.info(
                    f"事项已按原文顺序排序: chunks={len(chunks)}, events={len(all_events)}"
                )
            
            # 4. 保存到数据库（包括ES）
            if all_events:
                await self._save_events(all_events, config)
                
                # 5. 重新从数据库加载事项（带完整关系数据）
                # 解决跨 session 问题：保存后重新查询，确保所有关系正确加载
                event_ids = [e.id for e in all_events]
                all_events = await self._reload_events_with_relations(event_ids)
            else:
                self.logger.warning("没有提取到任何事项，跳过保存")
            
            # 6. 更新源状态为已完成
            if chunks:
                await self._update_source_status(chunks, status="COMPLETED")
            
            return all_events
            
        except Exception as e:
            # 提取失败时，更新状态为失败
            self.logger.error(f"提取失败: {e}", exc_info=True)
            try:
                chunks = await self._load_chunks(config.chunk_ids)
                if chunks:
                    await self._update_source_status(chunks, status="FAILED", error=str(e))
            except Exception as update_error:
                self.logger.error(f"更新失败状态时出错: {update_error}")
            
            raise ExtractError(f"提取失败: {e}") from e
    
    async def _load_chunks(self, chunk_ids: List[str]) -> List[SourceChunk]:
        """批量加载chunks（按rank排序）"""
        async with self.session_factory() as session:
            result = await session.execute(
                select(SourceChunk)
                .where(SourceChunk.id.in_(chunk_ids))
                .order_by(SourceChunk.rank)  # 🆕 按 rank 排序
            )
            chunks = list(result.scalars().all())
            
            if len(chunks) != len(chunk_ids):
                missing = set(chunk_ids) - {c.id for c in chunks}
                self.logger.warning(f"部分chunk不存在: {missing}")
            
            return chunks
    
    async def _process_chunks_with_agents(
        self,
        chunks: List[SourceChunk],
        config: ExtractConfig
    ) -> List[SourceEvent]:
        """
        并发处理chunks（每个chunk一个Agent）
        
        使用asyncio.Semaphore控制并发数量：
        - 同时最多有max_concurrency个Agent在运行
        - 超出的chunk会自动排队等待
        - 一个chunk完成后，立即启动下一个
        
        Args:
            chunks: chunk列表
            config: 提取配置
        
        Returns:
            合并后的所有事项
        """
        semaphore = asyncio.Semaphore(config.max_concurrency)
        
        # 进度跟踪
        completed = 0
        success_count = 0
        failed_count = 0
        total = len(chunks)
        lock = asyncio.Lock()
        
        async def process_single_chunk(
            chunk: SourceChunk,
            index: int
        ) -> List[SourceEvent]:
            """处理单个chunk（带并发控制和进度统计）"""
            nonlocal completed, success_count, failed_count
            
            async with semaphore:  # 🔒 获取并发槽位（没有就等待）
                try:
                    self.logger.info(
                        f"[{index+1}/{total}] 开始处理: chunk_id={chunk.id}, "
                        f"type={chunk.source_type}"
                    )
                    
                    # 调用chunk级提取（使用ExtractorAgent）
                    events = await self.extract_from_chunk(chunk, config)
                    
                    # 更新进度
                    async with lock:
                        completed += 1
                        success_count += 1
                        progress = completed * 100 // total
                        
                    self.logger.info(
                        f"✅ [{index+1}/{total}] 完成 ({progress}%): "
                        f"chunk_id={chunk.id}, events={len(events)}"
                    )
                    
                    return events
                    
                except Exception as e:
                    # 更新失败统计
                    async with lock:
                        completed += 1
                        failed_count += 1
                        progress = completed * 100 // total
                        
                    self.logger.error(
                        f"❌ [{index+1}/{total}] 失败 ({progress}%): "
                        f"chunk_id={chunk.id}, error={e}",
                        exc_info=True
                    )
                    return []  # 失败返回空，不中断其他chunk
                # 🔓 离开时自动释放槽位
        
        # 并发执行所有chunk
        self.logger.info(
            f"🚀 启动并发提取: total={total}, concurrency={config.max_concurrency}"
        )
        
        tasks = [
            process_single_chunk(chunk, i)
            for i, chunk in enumerate(chunks)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        
        # 合并结果
        all_events = []
        for events in results:
            all_events.extend(events)
        
        # 最终统计
        self.logger.info(
            f"📊 批量提取统计: 总数={total}, 成功={success_count}, "
            f"失败={failed_count}, 事项={len(all_events)}"
        )
        
        return all_events

    async def _load_sections(self, config: ExtractConfig) -> List[SourceChunk]:
        """
        加载来源片段

        Args:
            config: 提取配置

        Returns:
            来源片段列表
        """
        self.logger.debug(f"加载文章片段：article_id={config.article_id}")

        async with self.session_factory() as session:
            result = await session.execute(
                select(SourceChunk)
                .where(SourceChunk.source_type == 'article')
                .where(SourceChunk.source_id == config.article_id)
                .order_by(SourceChunk.rank)
            )
            sections = result.scalars().all()

        self.logger.info(f"加载了 {len(sections)} 个来源片段")

        return list(sections)

    async def _ensure_entity_types(self, config: ExtractConfig) -> None:
        """
        确保实体类型已初始化到数据库

        Args:
            config: 提取配置
        """
        if not config.custom_entity_types:
            return

        self.logger.debug(f"初始化自定义实体类型：{len(config.custom_entity_types)} 个")

        async with self.session_factory() as session:
            for custom_type in config.custom_entity_types:
                result = await session.execute(
                    select(DBEntityType)
                    .where(DBEntityType.source_config_id == config.source_config_id)
                    .where(DBEntityType.type == custom_type.type)
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    entity_type = DBEntityType(
                        id=str(uuid.uuid4()),
                        source_config_id=config.source_config_id,
                        type=custom_type.type,
                        name=custom_type.name,
                        description=custom_type.description,
                        weight=custom_type.weight,
                        is_active=True,
                        is_default=False,
                    )
                    session.add(entity_type)
                    self.logger.debug(f"创建自定义实体类型：{custom_type.type}")

            await session.commit()

    def _create_batches(
        self, sections: List[SourceChunk], config: ExtractConfig
    ) -> List[List[SourceChunk]]:
        """
        创建批次（智能分批，基于token限制）

        Args:
            sections: 来源片段列表
            config: 提取配置

        Returns:
            批次列表，每个批次是片段列表
        """
        batches = []
        current_batch = []
        current_tokens = 0

        for section in sections:
            section_text = f"{section.heading}\n{section.content}"
            section_tokens = estimate_tokens(section_text)

            will_exceed_token_limit = (
                current_tokens + section_tokens > config.max_tokens
            )
            will_exceed_section_limit = len(current_batch) >= config.max_sections

            if current_batch and (will_exceed_token_limit or will_exceed_section_limit):
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0

            current_batch.append(section)
            current_tokens += section_tokens

        if current_batch:
            batches.append(current_batch)

        self.logger.info(
            f"创建了 {len(batches)} 个批次，"
            f"平均每批 {len(sections) / len(batches):.1f} 个片段"
        )

        return batches

    async def _process_batches_parallel(
        self,
        sections: List[SourceChunk],
        processor: EventProcessor,
        config: ExtractConfig,
    ) -> List[SourceEvent]:
        """
        并发处理所有批次（两阶段处理）

        Args:
            sections: 来源片段列表
            processor: 事项处理器
            config: 提取配置

        Returns:
            所有批次提取的事项列表（包含实体关联）
        """
        batches = self._create_batches(sections, config)

        if not batches:
            self.logger.warning("没有可处理的批次")
            return []

        semaphore = asyncio.Semaphore(config.max_concurrency)
        
        # 进度统计
        completed_count = 0
        success_count = 0
        failed_count = 0
        progress_lock = asyncio.Lock()

        async def process_single_batch_extraction(
            batch_index: int, batch: List[SourceChunk]
        ) -> List[SourceEvent]:
            nonlocal completed_count, success_count, failed_count
            
            async with semaphore:
                try:
                    self.logger.debug(
                        f"批次 {batch_index + 1}/{len(batches)}: "
                        f"开始处理（阶段1），片段数={len(batch)}"
                    )
                    # 阶段1：提取事项（不含实体关联）
                    events = await processor.extract_events_without_entities(batch, batch_index)
                    
                    # 更新进度统计
                    async with progress_lock:
                        completed_count += 1
                        success_count += 1
                        progress_pct = completed_count * 100 // len(batches)
                        success_rate = success_count * 100 // completed_count
                        
                    self.logger.info(
                            f"📊 进度: {completed_count}/{len(batches)} ({progress_pct}%) | "
                            f"成功率: {success_rate}% ({success_count}✓/{failed_count}✗) | "
                            f"批次 {batch_index + 1}: 提取了 {len(events)} 个事项"
                    )
                    
                    return events
                except Exception as e:
                    # 更新失败统计
                    async with progress_lock:
                        completed_count += 1
                        failed_count += 1
                        progress_pct = completed_count * 100 // len(batches)
                        success_rate = success_count * 100 // completed_count if completed_count > 0 else 0
                        
                        self.logger.error(
                            f"❌ 进度: {completed_count}/{len(batches)} ({progress_pct}%) | "
                            f"成功率: {success_rate}% ({success_count}✓/{failed_count}✗) | "
                            f"批次 {batch_index + 1}: 处理失败: {e}"
                        )
                    
                    self.logger.error(
                        f"批次 {batch_index + 1} 详细错误",
                        exc_info=True,
                        extra={
                            "batch_index": batch_index,
                            "batch_size": len(batch),
                            "error_type": type(e).__name__,
                        },
                    )
                    # 返回空列表，但错误已被记录
                    return []

        # 阶段1：并发提取所有批次的事项（不含实体）
        self.logger.info(
            f"🚀 开始阶段1：并发处理 {len(batches)} 个批次（事项提取） - "
            f"最大并发数={config.max_concurrency}, LLM模型={processor.llm_client.client.config.model}"
        )

        tasks = [process_single_batch_extraction(i, batch) for i, batch in enumerate(batches)]
        batch_results = await asyncio.gather(*tasks, return_exceptions=False)

        all_events = []
        for batch_events in batch_results:
            all_events.extend(batch_events)

        # 计算最终统计
        final_success_rate = success_count * 100 // len(batches) if len(batches) > 0 else 0

        self.logger.info(
            f"✅ 阶段1完成 | "
            f"总批次: {len(batches)} | "
            f"成功: {success_count}✓ | "
            f"失败: {failed_count}✗ | "
            f"成功率: {final_success_rate}% | "
            f"提取事项: {len(all_events)} 个",
            extra={
                "total_batches": len(batches),
                "success_count": success_count,
                "failed_count": failed_count,
                "success_rate": final_success_rate,
                "total_sections": len(sections),
                "total_events": len(all_events),
            },
        )

        # 阶段1.5：实体交叉补充（兜底策略）
        if all_events and len(all_events) > 1:
            self.logger.info("开始阶段1.5：实体交叉补充")
            all_events = processor._cross_fill_entities(all_events)
        
        # 阶段2：统一处理所有事项的实体关联
        if all_events:
            self.logger.info("开始阶段2：统一处理实体关联")
            all_events = await processor.process_entity_associations(all_events)
            self.logger.info(f"阶段2完成，已处理 {len(all_events)} 个事项的实体关联")

        return all_events

    async def _extract_events(
        self, sections: List[SourceChunk], config: ExtractConfig
    ) -> List[SourceEvent]:
        """
        提取事项

        Args:
            sections: 来源片段列表
            config: 提取配置

        Returns:
            提取的事项列表
        """
        # 获取LLM客户端（懒加载）
        llm_client = await self._get_llm_client()
        
        processor = EventProcessor(
            llm_client=llm_client,
            prompt_manager=self.prompt_manager,
            config=config,
        )

        # 初始化处理器（加载实体类型配置）
        await processor.initialize()

        if config.parallel:
            # 并行处理片段（智能分批）- 内部已包含实体关联处理
            events = await self._process_batches_parallel(sections, processor, config)
        else:
            # 顺序处理片段（不含实体）
            events = []
            for i, section in enumerate(sections):
                batch_events = await processor.extract_from_sections([section], i)
                events.extend(batch_events)
            
            # 统一处理实体关联（与并行模式保持一致）
            if events:
                # 实体交叉补充
                if len(events) > 1:
                    events = processor._cross_fill_entities(events)
                # 处理实体关联
                events = await processor.process_entity_associations(events)

        # 统一分配全局 rank（确保同一文章内的事项按顺序排列）
        for i, event in enumerate(events):
            event.rank = i

        self.logger.info(f"提取了 {len(events)} 个事项")

        return events

    async def _save_events(self, events: List[SourceEvent], config: ExtractConfig) -> None:
        """
        保存事项到数据库（包括实体关联）+ Elasticsearch

        Args:
            events: 事项列表
            config: 提取配置
        """
        self.logger.info(f"保存 {len(events)} 个事项到数据库")

        # 1. 保存到 MySQL
        event_ids = []
        async with self.session_factory() as session:
            for event in events:
                event_ids.append(event.id)  # 记录 event ID
                # 添加事项
                session.add(event)
                
                # 添加事项的所有实体关联
                if hasattr(event, 'event_associations') and event.event_associations:
                    for assoc in event.event_associations:
                        session.add(assoc)

            await session.commit()

        self.logger.info("事项保存到MySQL完成")

        # 2. 同步到 Elasticsearch（如果启用）
        if config.auto_vector:
            try:
                # 重新从数据库查询事项（带关系数据），避免 detached instance 问题
                fresh_events = await self._load_events_by_ids(event_ids)
                await self._sync_to_elasticsearch(fresh_events, config)
            except Exception as e:
                self.logger.error(f"同步到ES失败: {e}", exc_info=True)
                # 不中断流程，继续执行

    async def _load_events_by_ids(self, event_ids: List[str]) -> List[SourceEvent]:
        """
        从数据库加载事项列表（预加载关系数据）
        
        Args:
            event_ids: 事项ID列表
            
        Returns:
            事项列表
        """
        if not event_ids:
            return []
        
        async with self.session_factory() as session:
            result = await session.execute(
                select(SourceEvent)
                .where(SourceEvent.id.in_(event_ids))
                .options(selectinload(SourceEvent.event_associations))
            )
            events = result.scalars().all()
            
            # 确保数据在 session 外可访问
            # 设置 expire_on_commit=False 或在这里触发加载
            session.expire_on_commit = False
            
            # 触发加载关系数据和所有字段
            for event in events:
                # 触发所有字段加载，包括 created_time 等
                _ = event.created_time
                _ = event.updated_time
                # 触发关系数据加载
                if hasattr(event, 'event_associations'):
                    _ = len(event.event_associations)
            
            return list(events)

    async def _sync_to_elasticsearch(
        self, events: List[SourceEvent], config: ExtractConfig
    ) -> None:
        """
        将事项和实体同步到Elasticsearch

        Args:
            events: 事项列表
            config: 提取配置
        """
        self.logger.info(f"开始同步 {len(events)} 个事项到Elasticsearch")
        
        # 初始化 ES 客户端（延迟初始化）
        if self.es_client is None:
            self.es_client = get_es_client()
            # Repository 需要 AsyncElasticsearch 对象，而不是 ElasticsearchClient 包装对象
            self.event_repo = EventVectorRepository(self.es_client.client)
            self.entity_repo = EntityVectorRepository(self.es_client.client)
        
        # 检查 ES 连接
        if not await self.es_client.ping():
            raise Exception("Elasticsearch 连接失败")
        
        # 收集所有唯一的实体
        unique_entities = {}  # key: entity_id, value: Entity对象
        for event in events:
            if hasattr(event, 'event_associations') and event.event_associations:
                for assoc in event.event_associations:
                    entity_id = assoc.entity_id
                    if entity_id not in unique_entities:
                        entity = await self._load_entity_by_id(entity_id)
                        if entity:
                            unique_entities[entity_id] = entity
        
        # 1. 先同步实体（可配置）
        if unique_entities and config.enable_entity_vector_sync:
            await self._sync_entities_to_es(list(unique_entities.values()), config)
        elif unique_entities:
            self.logger.info(f"跳过 {len(unique_entities)} 个实体的向量同步 (enable_entity_vector_sync=False)")
        
        # 2. 再同步事项
        await self._sync_events_to_es(events, config)
        
        entity_sync_status = f"{len(unique_entities)} 个实体" if config.enable_entity_vector_sync else "实体同步已禁用"
        self.logger.info(
            f"ES同步完成: {len(events)} 个事项, {entity_sync_status}"
        )


    async def _load_entity_by_id(self, entity_id: str):
        """
        从数据库加载实体

        Args:
            entity_id: 实体ID

        Returns:
            实体对象或None
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(Entity).where(Entity.id == entity_id)
            )
            return result.scalar_one_or_none()

    async def _batch_sync_entities_to_es(
        self,
        entities: List[Entity],
        config: ExtractConfig
    ) -> Dict[str, Any]:
        """
        批量同步实体到ES（两阶段处理）

        Args:
            entities: 实体列表
            config: 提取配置

        Returns:
            统计信息: {
                "total": int,
                "indexed": int,
                "embedding_failed": int,
                "es_failed": int,
                "time": str
            }
        """
        import time
        from dataflow.core.ai.factory import get_embedding_client
        from dataflow.core.storage import get_es_client

        start_time = time.perf_counter()

        if not entities:
            return {"total": 0, "indexed": 0, "embedding_failed": 0, "es_failed": 0, "time": "0.00s"}

        # 获取依赖
        embedding_client = await get_embedding_client(scenario='general')
        es_client = get_es_client()

        documents = []
        embedding_failed = 0

        # === 阶段1: 批量生成向量 ===
        for i in range(0, len(entities), config.embedding_batch_size):
            batch_entities = entities[i:i+config.embedding_batch_size]

            try:
                # 批量生成向量
                texts = [entity.name for entity in batch_entities]
                vectors = await embedding_client.batch_generate(texts)

                # 构建文档
                for entity, vector in zip(batch_entities, vectors):
                    doc = {
                        "id": entity.id,
                        "entity_id": entity.id,
                        "source_config_id": entity.source_config_id,
                        "type": entity.type,
                        "name": entity.name,
                        "vector": vector,
                        "normalized_name": entity.normalized_name or "",
                        "description": entity.description or "",
                        "created_time": entity.created_time.isoformat() if entity.created_time else None,
                    }
                    documents.append(doc)

            except Exception as e:
                self.logger.warning(f"批量生成向量失败，降级重试: {e}")
                # 降级: 逐个重试
                for entity in batch_entities:
                    try:
                        vector = await embedding_client.generate(entity.name)
                        doc = {
                            "id": entity.id,
                            "entity_id": entity.id,
                            "source_config_id": entity.source_config_id,
                            "type": entity.type,
                            "name": entity.name,
                            "vector": vector,
                            "normalized_name": entity.normalized_name or "",
                            "description": entity.description or "",
                            "created_time": entity.created_time.isoformat() if entity.created_time else None,
                        }
                        documents.append(doc)
                    except Exception as retry_e:
                        self.logger.error(f"单条生成向量失败 {entity.id}: {retry_e}")
                        embedding_failed += 1

        # === 阶段2: 批量索引到ES ===
        indexed = 0
        es_failed = 0

        for i in range(0, len(documents), config.es_bulk_index_size):
            batch = documents[i:i+config.es_bulk_index_size]

            try:
                result = await es_client.bulk_index(
                    index=self.entity_repo.INDEX_NAME,
                    documents=batch,
                    return_details=True,
                    routing=config.source_config_id
                )

                indexed += result["success_count"]

                # 处理失败项: 逐个重试
                if result["error_count"] > 0:
                    failed_ids = {err["id"] for err in result["errors"]}
                    for doc in batch:
                        if doc["id"] in failed_ids:
                            try:
                                await es_client.index_document(
                                    index=self.entity_repo.INDEX_NAME,
                                    document=doc,
                                    doc_id=doc["id"],
                                    routing=config.source_config_id
                                )
                                indexed += 1
                            except Exception as retry_e:
                                self.logger.error(f"重试索引失败 {doc['id']}: {retry_e}")
                                es_failed += 1

            except Exception as e:
                self.logger.error(f"批量索引失败，降级重试: {e}")
                # 降级: 整批逐个重试
                for doc in batch:
                    try:
                        await es_client.index_document(
                            index=self.entity_repo.INDEX_NAME,
                            document=doc,
                            doc_id=doc["id"],
                            routing=config.source_config_id
                        )
                        indexed += 1
                    except Exception as retry_e:
                        self.logger.error(f"降级索引失败 {doc['id']}: {retry_e}")
                        es_failed += 1

        total_time = time.perf_counter() - start_time

        stats = {
            "total": len(entities),
            "indexed": indexed,
            "embedding_failed": embedding_failed,
            "es_failed": es_failed,
            "time": f"{total_time:.2f}s"
        }

        if es_failed > 0 or embedding_failed > 0:
            self.logger.warning(f"实体同步部分失败: {stats}")
        else:
            self.logger.debug(f"实体同步成功: {indexed}/{len(entities)} 条, 耗时{total_time:.2f}s")

        return stats

    async def _sync_entities_to_es(
        self, entities: List[Entity], config: ExtractConfig
    ) -> None:
        """
        将实体同步到Elasticsearch（路由方法）

        根据 config.enable_batch_indexing 选择:
        - True: 批量处理 (新实现)
        - False: 串行处理 (保持原有逻辑)

        Args:
            entities: 实体列表
            config: 提取配置
        """
        if not entities:
            return

        # 过滤掉不需要索引到ES的实体类型（如时间类型）
        original_count = len(entities)
        entities = [e for e in entities if should_index_entity_to_es(e.type)]

        if len(entities) < original_count:
            skipped_count = original_count - len(entities)
            self.logger.info(
                f"过滤掉 {skipped_count} 个不需要索引到ES的实体 "
                f"(总数: {original_count}, 索引: {len(entities)})"
            )

        if not entities:
            self.logger.debug("所有实体都被过滤，跳过ES同步")
            return

        # 批量处理路径
        if config.enable_batch_indexing:
            stats = await self._batch_sync_entities_to_es(entities, config)
            # 日志已在 _batch_sync_entities_to_es 中输出
            return

        # 串行处理路径 (保持原有逻辑)
        self.logger.debug(f"同步 {len(entities)} 个实体到ES (串行模式)")

        success_count = 0
        error_count = 0

        embedding_client = await get_embedding_client(scenario='general')

        for entity in entities:
            try:
                # 生成实体名称的向量（使用统一的embedding服务）
                vector = await embedding_client.generate(entity.name)

                # 使用 Repository 的 index_entity 方法索引
                await self.entity_repo.index_entity(
                    entity_id=entity.id,
                    source_config_id=entity.source_config_id,
                    entity_type=entity.type,
                    name=entity.name,
                    vector=vector,
                    normalized_name=entity.normalized_name or "",
                    description=entity.description or "",
                    created_time=entity.created_time.isoformat() if entity.created_time else None,
                )
                success_count += 1

            except Exception as e:
                self.logger.error(f"实体索引失败 {entity.id}: {e}")
                error_count += 1

        if error_count > 0:
            self.logger.warning(
                f"实体同步部分失败: 成功{success_count}, 失败{error_count}"
            )
        else:
            self.logger.debug(f"实体同步成功: {success_count} 个")

    async def _batch_sync_events_to_es(
        self,
        events: List[SourceEvent],
        config: ExtractConfig
    ) -> Dict[str, Any]:
        """
        批量同步事项到ES（两阶段处理）

        Args:
            events: 事项列表
            config: 提取配置

        Returns:
            统计信息: {
                "total": int,
                "indexed": int,
                "embedding_failed": int,
                "es_failed": int,
                "time": str
            }
        """
        import time
        from dataflow.core.ai.factory import get_embedding_client
        from dataflow.core.storage import get_es_client

        start_time = time.perf_counter()

        if not events:
            return {"total": 0, "indexed": 0, "embedding_failed": 0, "es_failed": 0, "time": "0.00s"}

        # 获取依赖
        embedding_client = await get_embedding_client(scenario='general')
        es_client = get_es_client()

        documents = []
        embedding_failed = 0

        # === 阶段1: 批量生成向量 ===
        for i in range(0, len(events), config.embedding_batch_size):
            batch_events = events[i:i+config.embedding_batch_size]

            try:
                # 准备文本 (每个事项需要2个向量)
                title_texts = [event.title for event in batch_events]
                content_texts = [
                    f"{event.title}\n\n{event.content[:500]}"
                    for event in batch_events
                ]

                # 批量生成向量
                title_vectors = await embedding_client.batch_generate(title_texts)
                content_vectors = await embedding_client.batch_generate(content_texts)

                # 构建文档
                for event, title_vec, content_vec in zip(batch_events, title_vectors, content_vectors):
                    # 提取关联实体ID
                    entity_ids = []
                    if hasattr(event, 'event_associations') and event.event_associations:
                        entity_ids = [assoc.entity_id for assoc in event.event_associations]

                    # 准备额外字段
                    extra_fields = {}
                    if event.extra_data and "tags" in event.extra_data:
                        extra_fields["tags"] = event.extra_data["tags"]
                    if event.category:
                        extra_fields["category"] = event.category

                    doc = {
                        "id": event.id,
                        "event_id": event.id,
                        "source_config_id": event.source_config_id,
                        "source_type": event.source_type,
                        "source_id": event.source_id,
                        "title": event.title,
                        "summary": event.summary or "",
                        "content": event.content,
                        "title_vector": title_vec,
                        "content_vector": content_vec,
                        "entity_ids": entity_ids,
                        "start_time": event.start_time.isoformat() if event.start_time else None,
                        "end_time": event.end_time.isoformat() if event.end_time else None,
                        "created_time": event.created_time.isoformat() if event.created_time else None,
                        **extra_fields,
                    }
                    documents.append(doc)

            except Exception as e:
                self.logger.warning(f"批量生成向量失败，降级重试: {e}")
                # 降级: 逐个重试
                for event in batch_events:
                    try:
                        title_vec = await embedding_client.generate(event.title)
                        content_for_vec = f"{event.title}\n\n{event.content[:500]}"
                        content_vec = await embedding_client.generate(content_for_vec)

                        # 提取关联实体ID
                        entity_ids = []
                        if hasattr(event, 'event_associations') and event.event_associations:
                            entity_ids = [assoc.entity_id for assoc in event.event_associations]

                        # 准备额外字段
                        extra_fields = {}
                        if event.extra_data and "tags" in event.extra_data:
                            extra_fields["tags"] = event.extra_data["tags"]
                        if event.category:
                            extra_fields["category"] = event.category

                        doc = {
                            "id": event.id,
                            "event_id": event.id,
                            "source_config_id": event.source_config_id,
                            "source_type": event.source_type,
                            "source_id": event.source_id,
                            "title": event.title,
                            "summary": event.summary or "",
                            "content": event.content,
                            "title_vector": title_vec,
                            "content_vector": content_vec,
                            "entity_ids": entity_ids,
                            "start_time": event.start_time.isoformat() if event.start_time else None,
                            "end_time": event.end_time.isoformat() if event.end_time else None,
                            "created_time": event.created_time.isoformat() if event.created_time else None,
                            **extra_fields,
                        }
                        documents.append(doc)
                    except Exception as retry_e:
                        self.logger.error(f"单条生成向量失败 {event.id}: {retry_e}")
                        embedding_failed += 1

        # === 阶段2: 批量索引到ES ===
        indexed = 0
        es_failed = 0

        for i in range(0, len(documents), config.es_bulk_index_size):
            batch = documents[i:i+config.es_bulk_index_size]

            try:
                result = await es_client.bulk_index(
                    index=self.event_repo.INDEX_NAME,
                    documents=batch,
                    return_details=True,
                    routing=config.source_config_id
                )

                indexed += result["success_count"]

                # 处理失败项: 逐个重试
                if result["error_count"] > 0:
                    failed_ids = {err["id"] for err in result["errors"]}
                    for doc in batch:
                        if doc["id"] in failed_ids:
                            try:
                                await es_client.index_document(
                                    index=self.event_repo.INDEX_NAME,
                                    document=doc,
                                    doc_id=doc["id"],
                                    routing=config.source_config_id
                                )
                                indexed += 1
                            except Exception as retry_e:
                                self.logger.error(f"重试索引失败 {doc['id']}: {retry_e}")
                                es_failed += 1

            except Exception as e:
                self.logger.error(f"批量索引失败，降级重试: {e}")
                # 降级: 整批逐个重试
                for doc in batch:
                    try:
                        await es_client.index_document(
                            index=self.event_repo.INDEX_NAME,
                            document=doc,
                            doc_id=doc["id"],
                            routing=config.source_config_id
                        )
                        indexed += 1
                    except Exception as retry_e:
                        self.logger.error(f"降级索引失败 {doc['id']}: {retry_e}")
                        es_failed += 1

        total_time = time.perf_counter() - start_time

        stats = {
            "total": len(events),
            "indexed": indexed,
            "embedding_failed": embedding_failed,
            "es_failed": es_failed,
            "time": f"{total_time:.2f}s"
        }

        if es_failed > 0 or embedding_failed > 0:
            self.logger.warning(f"事项同步部分失败: {stats}")
        else:
            self.logger.debug(f"事项同步成功: {indexed}/{len(events)} 条, 耗时{total_time:.2f}s")

        return stats

    async def _sync_events_to_es(
        self, events: List[SourceEvent], config: ExtractConfig
    ) -> None:
        """
        将事项同步到Elasticsearch（路由方法）

        根据 config.enable_batch_indexing 选择:
        - True: 批量处理 (新实现)
        - False: 串行处理 (保持原有逻辑)

        Args:
            events: 事项列表
            config: 提取配置
        """
        if not events:
            return

        # 批量处理路径
        if config.enable_batch_indexing:
            stats = await self._batch_sync_events_to_es(events, config)
            # 日志已在 _batch_sync_events_to_es 中输出
            return

        # 串行处理路径 (保持原有逻辑)
        self.logger.debug(f"同步 {len(events)} 个事项到ES (串行模式)")

        success_count = 0
        error_count = 0

        embedding_client = await get_embedding_client(scenario='general')

        for event in events:
            try:
                # 生成标题向量（使用统一的embedding服务）
                title_vector = await embedding_client.generate(event.title)

                # 生成内容向量（使用标题+部分内容）
                content_for_vector = f"{event.title}\n\n{event.content[:500]}"
                content_vector = await embedding_client.generate(content_for_vector)

                # 提取关联的实体ID列表
                entity_ids = []
                if hasattr(event, 'event_associations') and event.event_associations:
                    entity_ids = [assoc.entity_id for assoc in event.event_associations]

                # 准备额外字段
                extra_fields = {}
                if event.extra_data:
                    # category不再从extra_data读取
                    if "tags" in event.extra_data:
                        extra_fields["tags"] = event.extra_data["tags"]

                # category从独立字段读取
                if event.category:
                    extra_fields["category"] = event.category

                # 使用 Repository 的 index_event 方法索引
                await self.event_repo.index_event(
                    event_id=event.id,
                    source_config_id=event.source_config_id,
                    source_type=event.source_type,
                    source_id=event.source_id,
                    title=event.title,
                    summary=event.summary or "",
                    content=event.content,
                    title_vector=title_vector,
                    content_vector=content_vector,
                    entity_ids=entity_ids,
                    start_time=event.start_time.isoformat() if event.start_time else None,
                    end_time=event.end_time.isoformat() if event.end_time else None,
                    created_time=event.created_time.isoformat() if event.created_time else None,
                    **extra_fields,
                )
                success_count += 1

            except Exception as e:
                self.logger.error(f"事项索引失败 {event.id}: {e}")
                error_count += 1

        if error_count > 0:
            self.logger.warning(
                f"事项同步部分失败: 成功{success_count}, 失败{error_count}"
            )
        else:
            self.logger.debug(f"事项同步成功: {success_count} 个")

    async def _reload_events_with_entities(self, article_id: str) -> List[SourceEvent]:
        """
        重新加载事项，预加载实体关系
        
        Args:
            article_id: 文章ID
            
        Returns:
            包含完整实体关系的事项列表
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(SourceEvent)
                .where(SourceEvent.article_id == article_id)
                .order_by(SourceEvent.rank)
                .options(
                    selectinload(SourceEvent.event_associations).selectinload(EventEntity.entity)
                )
            )
            events = list(result.scalars().all())
        
        self.logger.debug(f"重新加载了 {len(events)} 个事项（包含实体关系）")
        return events

    async def extract_from_chunk(
        self,
        chunk: SourceChunk,
        config: ExtractConfig
    ) -> List[SourceEvent]:
        """
        从chunk提取事项
        
        Args:
            chunk: 来源片段对象
            config: 提取配置
        
        Returns:
            提取的事项列表
        """
        try:
            self.logger.info(f"开始从chunk提取: chunk_id={chunk.id}, type={chunk.source_type}")
            
            # 1. 加载内容和元数据
            content_items, raw_metadata = await self._load_chunk_content(chunk)
            if not content_items:
                self.logger.warning(f"Chunk {chunk.id} 无内容")
                return []
            
            # 2. 创建 EventProcessor
            llm_client = await self._get_llm_client()
            processor = EventProcessor(
                llm_client=llm_client,
                prompt_manager=self.prompt_manager,
                config=config,
            )
            await processor.initialize()
            
            # 3. 构建元数据
            metadata = {
                "document_title": raw_metadata.get("title", ""),
                "chunk_title": chunk.heading or f"片段{chunk.rank + 1}",
                "previous_context": self._format_previous_context(raw_metadata.get("previous_chunk")),
            }
            
            # 4. 调用提取
            events = await processor.extract(
                items=content_items,
                metadata=metadata,
                source_type=chunk.source_type
            )
            
            # 5. 关联 chunk_id 并处理实体
            for event in events:
                event.chunk_id = chunk.id
            
            # 5.5. 实体交叉补充
            if len(events) > 1:
                events = processor._cross_fill_entities(events)
            
            # 6. 处理实体关联
            events = await processor.process_entity_associations(events)
            
            self.logger.info(f"Chunk提取完成: chunk_id={chunk.id}, events={len(events)}")
            return events
            
        except Exception as e:
            self.logger.error(f"Chunk提取失败: {e}", exc_info=True)
            raise ExtractError(f"Chunk提取失败: {e}") from e
    
    def _format_previous_context(self, previous_chunk) -> str:
        """格式化前文上下文"""
        if not previous_chunk:
            return ""
        
        title = previous_chunk.get("heading") or previous_chunk.get("title") or "前文"
        content = previous_chunk.get("content", "")
        
        if len(content) > 300:
            content = content[:300] + "..."
        
        return f"**{title}**\n{content}"
    
    async def _load_chunk_content(self, chunk: SourceChunk):
        """加载chunk的内容和元数据"""
        if chunk.source_type == 'ARTICLE':
            return await self._load_article_content(chunk)
        elif chunk.source_type == 'CHAT':
            return await self._load_conversation_content(chunk)
        else:
            raise ExtractError(f"不支持的类型: {chunk.source_type}")
    
    async def _load_article_content(self, chunk: SourceChunk):
        """加载文章片段 + 上文chunk内容作为背景"""
        from dataflow.db import Article, ArticleSection, SourceChunk as SC
        
        async with self.session_factory() as session:
            # 1. 加载文章（源背景）
            article = await session.get(Article, chunk.source_id)
            if not article:
                raise ExtractError(f"文章不存在: {chunk.source_id}")
            
            # 2. 加载当前chunk的sections（待处理内容）
            section_ids = chunk.references if chunk.references else []
            
            if section_ids:
                sections_result = await session.execute(
                    select(ArticleSection)
                    .where(ArticleSection.id.in_(section_ids))
                    .order_by(ArticleSection.rank)
                )
            else:
                sections_result = await session.execute(
                    select(ArticleSection)
                    .where(ArticleSection.article_id == chunk.source_id)
                    .order_by(ArticleSection.rank)
                )
            
            sections = list(sections_result.scalars().all())
            
            # 3. 加载上一个chunk的内容（上文背景）
            previous_chunk = None
            if chunk.rank > 0:
                prev_result = await session.execute(
                    select(SC)
                    .where(SC.source_id == chunk.source_id)
                    .where(SC.source_type == 'ARTICLE')
                    .where(SC.rank == chunk.rank - 1)
                )
                previous_chunk = prev_result.scalar_one_or_none()
            
            return sections, {
                # Article 表字段（源背景）
                "title": article.title,
                "summary": article.summary,
                "category": article.category,
                "tags": article.tags,
                
                # 当前 Chunk 信息
                "chunk_rank": chunk.rank,
                "chunk_heading": chunk.heading,
                
                # 上文 Chunk（提供上下文）
                "previous_chunk": {
                    "heading": previous_chunk.heading,
                    "content": previous_chunk.content[:800] if len(previous_chunk.content or "") > 800 else previous_chunk.content
                } if previous_chunk and previous_chunk.content else None
            }
    
    async def _load_conversation_content(self, chunk: SourceChunk):
        """加载对话消息 + 上文chunk内容作为背景"""
        from dataflow.db import ChatConversation, ChatMessage, SourceChunk as SC
        
        async with self.session_factory() as session:
            # 1. 加载会话（源背景）
            conversation = await session.get(ChatConversation, chunk.source_id)
            if not conversation:
                raise ExtractError(f"会话不存在: {chunk.source_id}")
            
            # 2. 加载当前chunk的messages（待处理内容）
            message_ids = chunk.references if chunk.references else []
            
            if message_ids:
                messages_result = await session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.id.in_(message_ids))
                    .order_by(ChatMessage.timestamp)
                )
            else:
                messages_result = await session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.conversation_id == chunk.source_id)
                    .order_by(ChatMessage.timestamp)
                )
            
            messages = list(messages_result.scalars().all())
            
            # 从当前messages提取参与者和时间（无需额外查询）
            participants = []
            seen_names = set()
            for msg in messages:
                if msg.sender_name and msg.sender_name not in seen_names:
                    participants.append({
                        "name": msg.sender_name,
                        "role": msg.sender_role
                    })
                    seen_names.add(msg.sender_name)
            
            time_range = ""
            if messages:
                start = messages[0].timestamp.strftime('%H:%M')
                end = messages[-1].timestamp.strftime('%H:%M')
                time_range = f"{start} ~ {end}"
            
            # 3. 加载上一个chunk的内容（上文背景）
            previous_chunk = None
            if chunk.rank > 0:
                prev_result = await session.execute(
                    select(SC)
                    .where(SC.source_id == chunk.source_id)
                    .where(SC.source_type == 'CHAT')
                    .where(SC.rank == chunk.rank - 1)
                )
                previous_chunk = prev_result.scalar_one_or_none()
            
            return messages, {
                # ChatConversation 表字段（源背景）
                "title": conversation.title,
                "messages_count": conversation.messages_count,
                
                # extra_data 字段
                "platform": conversation.extra_data.get("platform") if conversation.extra_data else None,
                "scenario": conversation.extra_data.get("scenario") if conversation.extra_data else None,
                
                # 从当前messages提取
                "participants": participants,
                "time_range": time_range,
                
                # 当前 Chunk 信息
                "chunk_rank": chunk.rank,
                "chunk_heading": chunk.heading,
                
                # 上文 Chunk（提供上下文）
                "previous_chunk": {
                    "heading": previous_chunk.heading,
                    "content": previous_chunk.content[:800] if len(previous_chunk.content or "") > 800 else previous_chunk.content
                } if previous_chunk and previous_chunk.content else None
            }
    
    async def _load_entity_types_for_chunk(self, config: ExtractConfig) -> List[Dict]:
        """
        加载实体类型定义（必定返回非空列表）
        
        优先级：
        1. 默认全局类型（is_default=True）
        2. source级别自定义类型
        3. config中的运行时类型
        """
        entity_types = []
        
        async with self.session_factory() as session:
            # 加载默认类型
            default_result = await session.execute(
                select(DBEntityType)
                .where(DBEntityType.is_default == True)
                .where(DBEntityType.is_active == True)
            )
            default_types = default_result.scalars().all()
            
            entity_types.extend([{
                "type": et.type,
                "name": et.name,
                "description": et.description or "",
                "weight": float(et.weight),
                "value_constraints": et.value_constraints,  # 🆕 JSON 配置
            } for et in default_types])
            
            # 加载source级别类型
            if config.source_config_id:
                custom_result = await session.execute(
                    select(DBEntityType)
                    .where(DBEntityType.source_config_id == config.source_config_id)
                    .where(DBEntityType.is_active == True)
                )
                custom_types = custom_result.scalars().all()
                
                entity_types.extend([{
                    "type": et.type,
                    "name": et.name,
                    "description": et.description or "",
                    "weight": float(et.weight),
                    "value_constraints": et.value_constraints,  # 🆕 JSON 配置
                } for et in custom_types])
        
        # 运行时类型（最高优先级）
        if config.custom_entity_types:
            entity_types.extend([{
                "type": et.type,
                "name": et.name,
                "description": et.description,
                "weight": et.weight,
                "value_constraints": getattr(et, 'value_constraints', None),  # 🆕
            } for et in config.custom_entity_types])
        
        return entity_types
    
    async def _build_events_from_result(
        self,
        result: Dict,
        chunk: SourceChunk,
        config: ExtractConfig
    ) -> List[SourceEvent]:
        """转换Agent结果为SourceEvent"""
        events = []

        # 🆕 实体缓存：避免同一批处理中重复创建相同实体
        entity_cache = {}  # {(type, normalized_name): Entity}
        
        # 🆕 过滤统计
        filter_stats = {'total': 0, 'llm_invalid': 0, 'rule_filtered': 0, 'valid': 0}
        filter_details = []

        for idx, evt in enumerate(result.get('events', [])):
            filter_stats['total'] += 1
            title_short = evt.get('title', '')[:20]
            
            # ========== 第1层：LLM 标记过滤 ==========
            if not evt.get('is_valid', True):
                filter_stats['llm_invalid'] += 1
                filter_details.append(f"  ❌ LLM无效: {title_short}")
                continue
            
            # ========== 第2层：代码规则兜底 ==========
            is_low, reason = self._is_low_quality(evt)
            if is_low:
                filter_stats['rule_filtered'] += 1
                filter_details.append(f"  ⚠️ {reason}: {title_short}")
                continue
            
            filter_stats['valid'] += 1
            
            # 处理 references 格式（兼容旧格式和新格式）
            raw_references = evt.get('references', [])
            if raw_references and isinstance(raw_references[0], dict):
                # 旧格式: [{"type": "section", "id": "xxx"}] -> 提取 ID
                references = [ref['id'] for ref in raw_references if isinstance(ref, dict) and 'id' in ref]
            else:
                # 新格式: ["xxx", "yyy"] 或空列表
                references = raw_references
            
            # 🆕 根据来源类型设置时间
            from datetime import datetime
            from dataflow.db import ChatMessage
            from sqlalchemy import select as sql_select
            
            start_time = None
            end_time = None
            
            if chunk.source_type == "ARTICLE":
                # 文档类型：使用当前时间
                current_time = datetime.now()
                start_time = current_time
                end_time = current_time
                
            elif chunk.source_type == "CHAT":
                # 会话类型：从事项引用的消息中获取时间范围
                # ✅ 使用事项自己的 references（从 LLM 提取结果来的）
                if references and isinstance(references, list):
                    async with self.session_factory() as session:
                        result_msgs = await session.execute(
                            sql_select(ChatMessage)
                            .where(ChatMessage.id.in_(references))
                            .order_by(ChatMessage.timestamp)
                        )
                        messages = list(result_msgs.scalars().all())
                        
                        if messages:
                            start_time = messages[0].timestamp
                            end_time = messages[-1].timestamp
            
            # 创建事项
            event = SourceEvent(
                id=str(uuid.uuid4()),
                source_config_id=config.source_config_id,
                source_type=chunk.source_type,
                source_id=chunk.source_id,
                article_id=chunk.source_id if chunk.source_type == 'ARTICLE' else None,
                conversation_id=chunk.source_id if chunk.source_type == 'CHAT' else None,
                chunk_id=chunk.id,
                title=evt['title'],
                summary=evt['summary'],
                content=evt['content'],
                category=evt.get('category', ''),
                # 业务字段（兼容主系统）- type与source_type保持一致
                type=chunk.source_type,
                priority="UNKNOWN",  # 默认值
                status="UNKNOWN",  # 默认值
                rank=idx,
                start_time=start_time,  # 🆕
                end_time=end_time,      # 🆕
                references=references
            )

            # 关联实体（使用去重与描述合并逻辑）
            # 注意：时间类型实体不注入，因为它们不需要用于相似度计算和关联检索
            event.event_associations = []

            # 获取实体列表
            entities_list = list(evt.get('entities', []))  # 拷贝，避免修改原数据
            
            # 🆕 混合模式兜底：LLM + 分词器双通道
            existing_names = {
                e.get('name', '').strip().lower() 
                for e in entities_list 
                if e.get('name')
            }
            
            # 1. LLM兜底：补充实体（带正确分类）
            entity_types = await self._load_entity_types_for_chunk(config)
            fallback_entities = await self._fallback_extract_entities_with_llm(
                references, chunk.source_type, existing_names, entity_types
            )
            entities_list.extend(fallback_entities)
            
            # 2. 分词器补充：专有名词作为 tags（兜底的兜底）
            # 更新 existing_names 包含 LLM 兜底的结果
            for e in fallback_entities:
                existing_names.add(e.get('name', '').strip().lower())
            
            tags_entities = await self._fallback_extract_tags(
                references, chunk.source_type, existing_names
            )
            entities_list.extend(tags_entities)

            # 使用字典跟踪每个实体ID及其描述（防止重复关联）
            entity_map = {}  # {entity_id: {"name": str, "descriptions": [str]}}

            # 第一遍：收集所有实体及其描述
            for entity_data in entities_list:
                # 🆕 先检查缓存，避免重复创建相同实体
                cache_key = (entity_data.get('type', ''), entity_data.get('name', '').strip().lower())

                if cache_key in entity_cache:
                    entity = entity_cache[cache_key]
                else:
                    entity = await self._get_or_create_entity(entity_data, config)
                    if entity:
                        entity_cache[cache_key] = entity

                # 跳过无效实体（type不存在时返回None）
                if entity is None:
                    continue

                # 检查是否已添加过这个实体
                if entity.id not in entity_map:
                    entity_map[entity.id] = {
                        "name": entity.name,
                        "descriptions": []
                    }

                # 收集描述（去重）
                description = entity_data.get('description', '').strip()
                if description and description not in entity_map[entity.id]["descriptions"]:
                    entity_map[entity.id]["descriptions"].append(description)

            # 第二遍：为每个唯一的 entity_id 创建一个关联（合并描述）
            for entity_id, info in entity_map.items():
                # 合并描述
                if info["descriptions"]:
                    final_description = "、".join(info["descriptions"])
                else:
                    final_description = ""

                assoc = EventEntity(
                    id=str(uuid.uuid4()),
                    event_id=event.id,
                    entity_id=entity_id,
                    description=final_description  # 合并后的角色描述
                )
                # ✅ 不设置 entity 关系，避免跨 session 冲突
                # assoc.entity = entity  # 移除，会在保存后重新加载

                event.event_associations.append(assoc)

                # 日志：如果合并了多个描述
                if len(info["descriptions"]) > 1:
                    self.logger.debug(
                        f"✅ 合并实体描述: {info['name']} ({len(info['descriptions'])}个) -> {final_description}"
                    )
            
            events.append(event)
        
        # 🆕 过滤日志（始终输出统计）
        filtered_total = filter_stats['llm_invalid'] + filter_stats['rule_filtered']
        
        msg = (
            f"📊 事项质量: chunk={chunk.id[:8]}..., "
            f"总计{filter_stats['total']}个, 有效{filter_stats['valid']}个"
            + (f", 过滤{filtered_total}个 (LLM{filter_stats['llm_invalid']}+规则{filter_stats['rule_filtered']})"
               if filtered_total > 0 else "")
        )
        self.logger.info(msg)
        
        # 过滤详情（有过滤时输出）
        if filter_details:
            for detail in filter_details:
                self.logger.info(detail)
        
        return events
    
    def _is_low_quality(self, evt: Dict) -> tuple:
        """
        代码层质量兜底（只过滤明显垃圾，宁可放过不可误伤）
        
        Returns:
            (是否低质量, 原因)
        """
        import re
        
        content = evt.get('content', '').strip()
        title = evt.get('title', '').strip()
        entities = evt.get('entities', [])
        
        # 规则1：空内容
        if not content or not title:
            return True, "内容或标题为空"
        
        # 规则2：纯链接（无实质文字）
        text_only = re.sub(r'https?://\S+', '', content).strip()
        if len(text_only) < 5:
            return True, "纯链接"
        
        # 规则3：组合广告特征（需≥2个信号）
        ad_signals = 0
        ad_keywords = ['扫码', '加群', '优惠券', '点击领取', '限时免费']
        if any(kw in content for kw in ad_keywords):
            ad_signals += 1
        if re.search(r'(微信|QQ)[:：]?\s*\w+', content):
            ad_signals += 1
        if not entities and len(content) < 20:
            ad_signals += 1
        if ad_signals >= 2:
            return True, "疑似广告"
        
        # 规则4：乱码（控制字符）
        if re.search(r'[\x00-\x1f\x7f-\x9f]{3,}', content):
            return True, "乱码"
        
        return False, ""
    
    def _build_value_raw(self, name: str, value: str, unit: str, value_type: str) -> str:
        """
        构建完整的 value_raw（人类可读的完整表述）
        
        规则：
        1. text 类型或无 value → 直接返回 name
        2. datetime：检查 name 是否已包含日期格式
        3. 数值类型：检查 name 是否已包含阿拉伯数字
        """
        import re
        
        name = name or ''
        
        # 1. text 类型或无 value → 直接返回 name
        if value_type == 'text' or not value:
            return name
        
        # 2. datetime 类型
        if value_type == 'datetime':
            # 如果 name 已包含日期/时间格式 → 不拼接
            if re.search(r'(\d{4}年|\d{1,2}月|\d{1,2}日|\d{1,2}[:：点]|\d{4}-)', name):
                return name
            # 否则拼接
            return name + value
        
        # 3. 检查 name 是否已包含阿拉伯数字
        if re.search(r'\d', name):
            # name 已有数字 → 只检查是否需要补 unit
            if unit and unit not in name:
                return name + unit
            return name
        
        # 4. name 是纯语义名称 → 拼接 value + unit
        result = name + value
        if unit and unit not in result:
            result += unit
        
        return result
    
    def _parse_entity_value(
        self,
        entity_data: Dict,
        entity_type
    ) -> Dict[str, Any]:
        """
        解析实体值类型（LLM优先 + 代码兜底）
        
        规则：LLM 有效 → 用 LLM，否则 → 代码兜底
        """
        from decimal import Decimal
        from datetime import datetime as dt
        
        name = entity_data['name']
        llm_type = entity_data.get('value_type')
        llm_value = entity_data.get('value')
        llm_unit = entity_data.get('unit')
        
        valid_types = ('text', 'int', 'float', 'datetime', 'bool')
        
        # ========== LLM 有效 → 使用 ==========
        if llm_type and llm_type in valid_types:
            # 构建完整的 value_raw
            value_raw = self._build_value_raw(name, llm_value, llm_unit, llm_type)
            
            fields = {
                "value_type": llm_type,
                "value_raw": value_raw,
                "int_value": None,
                "float_value": None,
                "datetime_value": None,
                "bool_value": None,
                "enum_value": None,
                "value_unit": llm_unit,
                "value_confidence": Decimal("0.90")
            }
            
            try:
                if llm_type == "int" and llm_value:
                    fields["int_value"] = int(float(llm_value.replace(',', '')))
                elif llm_type == "float" and llm_value:
                    fields["float_value"] = Decimal(llm_value.replace(',', ''))
                elif llm_type == "datetime" and llm_value:
                    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%Y年%m月%d日"]:
                        try:
                            fields["datetime_value"] = dt.strptime(llm_value, fmt)
                            break
                        except ValueError:
                            continue
                elif llm_type == "bool" and llm_value:
                    fields["bool_value"] = llm_value.lower() in ("true", "是", "1")
            except Exception:
                pass
            
            fields["_source"] = "llm"
            return fields
        
        # ========== 代码兜底 ==========
        value_constraints = getattr(entity_type, 'value_constraints', None)
        result = EntityValueParser().parse_to_typed_fields(
            name,
            entity_type=entity_data['type'],
            value_constraints=value_constraints
        )
        result["_source"] = "code"
        return result
    
    async def _get_or_create_entity(
        self,
        entity_data: Dict,
        config: ExtractConfig
    ) -> Optional[Entity]:
        """
        查找或创建实体（去重）
        
        支持高并发场景，处理以下异常：
        - IntegrityError: 唯一约束冲突，重新查询已存在的实体
        - OperationalError (1205): 锁等待超时，使用指数退避重试
        
        Returns:
            Entity对象，如果实体类型无效或名称无效则返回None
        """
        # 过滤单字符实体（如标点符号 「」等）
        entity_name = entity_data.get('name', '').strip()
        if len(entity_name) <= 1:
            return None
        
        normalized_name = entity_name.lower()
        
        # 🆕 重试配置：处理锁等待超时 (MySQL error 1205)
        max_retries = 3
        base_delay = 0.1  # 基础延迟 100ms
        
        for attempt in range(max_retries):
            try:
                return await self._get_or_create_entity_inner(
                    entity_data, config, normalized_name
                )
            except OperationalError as e:
                # 检查是否为锁等待超时 (MySQL error 1205) 或死锁 (MySQL error 1213)
                error_str = str(e)
                is_lock_timeout = "1205" in error_str or "Lock wait timeout" in error_str
                is_deadlock = "1213" in error_str or "Deadlock" in error_str
                
                if is_lock_timeout or is_deadlock:
                    error_type = "死锁" if is_deadlock else "锁等待超时"
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # 指数退避: 0.1s, 0.2s, 0.4s
                        self.logger.warning(
                            f"🔄 实体{error_type}，{delay:.1f}s 后重试 ({attempt + 1}/{max_retries}): "
                            f"{entity_data['name']}"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        self.logger.error(
                            f"❌ 实体{error_type}，重试{max_retries}次后仍失败: {entity_data['name']}"
                        )
                # 非锁超时/死锁错误或重试次数用尽，抛出异常
                raise
        
        # 不应该到这里
        return None
    
    async def _get_or_create_entity_inner(
        self,
        entity_data: Dict,
        config: ExtractConfig,
        normalized_name: str
    ) -> Optional[Entity]:
        """
        实际执行实体查找或创建的内部方法
        
        分离出来以支持外层重试逻辑
        """
        async with self.session_factory() as session:
            # 查找已存在
            existing_result = await session.execute(
                select(Entity)
                .where(Entity.source_config_id == config.source_config_id)
                .where(Entity.type == entity_data['type'])
                .where(Entity.normalized_name == normalized_name)
            )
            entity = existing_result.scalar_one_or_none()
            
            if entity:
                return entity
            
            # 创建新实体 - 获取entity_type_id
            entity_type_result = await session.execute(
                select(DBEntityType)
                .where(DBEntityType.type == entity_data['type'])
                .where(
                    (DBEntityType.source_config_id == config.source_config_id) |
                    (DBEntityType.is_default == True)
                )
                .where(DBEntityType.is_active == True)
            )
            entity_type = entity_type_result.scalar_one_or_none()
            
            if not entity_type:
                # ✅ 记录警告但不抛异常，返回 None
                self.logger.warning(
                    f"跳过无效实体类型: type={entity_data['type']}, "
                    f"name={entity_data.get('name', 'N/A')}"
                )
                return None
            
            entity = Entity(
                id=str(uuid.uuid4()),
                source_config_id=config.source_config_id,
                entity_type_id=entity_type.id,
                type=entity_data['type'],
                name=entity_data['name'],
                normalized_name=normalized_name,
                description=None  # 角色描述保存在 EventEntity.description，不保存在 Entity.description
            )

            # 🆕 解析类型化值（LLM优先 + 代码兜底）
            typed_fields = self._parse_entity_value(entity_data, entity_type)
            if typed_fields:
                source = typed_fields.pop("_source", "code")
                entity.value_type = typed_fields.get("value_type")
                entity.value_raw = typed_fields.get("value_raw")
                entity.int_value = typed_fields.get("int_value")
                entity.float_value = typed_fields.get("float_value")
                entity.datetime_value = typed_fields.get("datetime_value")
                entity.bool_value = typed_fields.get("bool_value")
                entity.enum_value = typed_fields.get("enum_value")
                entity.value_unit = typed_fields.get("value_unit")
                entity.value_confidence = typed_fields.get("value_confidence")
                
                # 只记录非text类型（有意义的类型解析）
                if entity.value_type and entity.value_type != "text":
                    unit_str = f", unit={entity.value_unit}" if entity.value_unit else ""
                    self.logger.info(
                        f"📌 实体值: {entity_data['name'][:15]} → {entity.value_type}({source}){unit_str}"
                    )

            try:
                session.add(entity)
                await session.commit()
                await session.refresh(entity)
                return entity

            except IntegrityError as e:
                # 并发冲突：另一个进程/协程已创建相同实体
                await session.rollback()
                self.logger.debug(
                    f"🔄 实体并发冲突，重新查询: {entity_data['name']}, error={e}"
                )

                # 重新查询已存在的实体
                retry_result = await session.execute(
                    select(Entity)
                    .where(Entity.source_config_id == config.source_config_id)
                    .where(Entity.type == entity_data['type'])
                    .where(Entity.normalized_name == normalized_name)
                )
                existing_entity = retry_result.scalar_one_or_none()

                if existing_entity:
                    return existing_entity

                # 理论上不应该到这里
                self.logger.error(f"❌ 实体冲突后重新查询失败: {entity_data['name']}")
                raise
    
    async def _reload_events_with_relations(self, event_ids: List[str]) -> List[SourceEvent]:
        """
        重新从数据库加载事项列表（预加载关系数据）
        
        解决跨 session 问题：保存后重新查询，确保所有关系正确加载
        
        Args:
            event_ids: 事项ID列表
            
        Returns:
            包含完整关系的事项列表
        """
        if not event_ids:
            return []
        
        async with self.session_factory() as session:
            result = await session.execute(
                select(SourceEvent)
                .where(SourceEvent.id.in_(event_ids))
                .options(
                    selectinload(SourceEvent.event_associations).selectinload(EventEntity.entity)
                )
            )
            events = list(result.scalars().all())
            
            # 设置 expire_on_commit=False，确保数据在 session 外可访问
            session.expire_on_commit = False
            
            # 触发关系数据加载（确保所有字段在 session 外可访问）
            for event in events:
                # 触发事项字段加载
                _ = event.title
                _ = event.created_time
                
                # 触发关联和实体加载
                if hasattr(event, 'event_associations'):
                    for assoc in event.event_associations:
                        _ = assoc.id
                        if assoc.entity:
                            _ = assoc.entity.name
                            _ = assoc.entity.type
            
            self.logger.debug(f"重新加载了 {len(events)} 个事项（包含完整关系）")
            return events
    
    async def _fallback_extract_tags(
        self,
        references: List[str],
        source_type: str,
        existing_entity_names: set
    ) -> List[Dict]:
        """
        分词器兜底：从原文提取 tags 实体
        
        Args:
            references: 原文引用ID列表
            source_type: ARTICLE 或 CHAT
            existing_entity_names: 已提取的实体名称集合（小写）
        
        Returns:
            补充的 tags 实体列表
        """
        if not references:
            return []
        
        try:
            from dataflow.db import ArticleSection, ChatMessage
            from dataflow.core.ai.tokensize import get_keyword_extractor, POS
            
            # 1. 加载原文
            async with self.session_factory() as session:
                if source_type == "ARTICLE":
                    result = await session.execute(
                        select(ArticleSection.content).where(ArticleSection.id.in_(references))
                    )
                else:
                    result = await session.execute(
                        select(ChatMessage.content).where(ChatMessage.id.in_(references))
                    )
                contents = [row[0] for row in result.all() if row[0]]
            
            if not contents:
                return []
            
            original_text = " ".join(contents)
            
            # 2. 分词提取 - 限制为专有名词（人名、地名、机构名、产品名）
            proper_noun_pos = {POS.PERSON, POS.PLACE, POS.ORG, POS.PRODUCT}
            keywords = get_keyword_extractor().extract(
                original_text, 
                top_k=20,
                pos=proper_noun_pos
            )
            
            if not keywords:
                return []
            
            # 3. 去重（只检查完全匹配，避免误判）
            tags = []
            skipped = []
            
            for kw in keywords:
                kw_lower = kw.lower()
                is_duplicate = kw_lower in existing_entity_names
                
                if is_duplicate:
                    skipped.append(kw)
                else:
                    tags.append({
                        "type": "tags",
                        "name": kw,
                        "description": "关键词",
                        "value_type": "text"  # 明确指定，避免代码误判
                    })
            
            # 4. 日志
            if tags or skipped:
                self.logger.info(
                    f"📌 Tags兜底: 分词={len(keywords)}, 新增={len(tags)}, 去重={len(skipped)}"
                )
            if tags:
                self.logger.info(f"   ✅ 新增: {[t['name'] for t in tags]}")
            
            return tags
            
        except Exception as e:
            self.logger.warning(f"⚠️ Tags兜底失败: {e}")
            return []

    async def _fallback_extract_entities_with_llm(
        self,
        references: List[str],
        source_type: str,
        existing_entity_names: set,
        entity_types: List[Dict]
    ) -> List[Dict]:
        """
        LLM兜底：从原文提取实体并正确分类（比分词器更精准）
        
        Args:
            references: 原文引用ID列表
            source_type: ARTICLE 或 CHAT
            existing_entity_names: 已提取的实体名称集合（小写）
            entity_types: 实体类型定义列表
        
        Returns:
            补充的实体列表（带正确分类）
        """
        if not references:
            return []
        
        try:
            from dataflow.db import ArticleSection, ChatMessage
            from dataflow.core.ai.factory import create_llm_client
            
            # 1. 加载原文
            async with self.session_factory() as session:
                if source_type == "ARTICLE":
                    result = await session.execute(
                        select(ArticleSection.content).where(ArticleSection.id.in_(references))
                    )
                else:
                    result = await session.execute(
                        select(ChatMessage.content).where(ChatMessage.id.in_(references))
                    )
                contents = [row[0] for row in result.all() if row[0]]
            
            if not contents:
                return []
            
            original_text = " ".join(contents)
            
            # 2. 构建实体类型描述（与首次提取一致）
            type_descriptions = []
            valid_types = []
            for et in entity_types:
                if et.get('type') != 'tags':  # 排除 tags 类型
                    desc = et.get('description', et['name'])
                    type_descriptions.append(f"- **{et['type']}** ({et['name']}): {desc}")
                    valid_types.append(et['type'])
            
            # 日志：显示可用类型
            self.logger.debug(f"🤖 LLM兜底可用类型: {valid_types}")
            
            # 3. 构建 LLM 提示词
            # 将已提取的实体列表全部传给 LLM（最多50个）
            existing_list = sorted(list(existing_entity_names))[:50]
            
            prompt = f"""You are an entity extraction expert. Your goal is to ensure no important clues are missed.

## Purpose
Entities are **answers or clues leading to answers**.
When users ask questions, these entities help find the relevant documents.
The initial extraction may have missed some critical clues. Your job is to fill the gaps.

## Available Entity Types:
{chr(10).join(type_descriptions)}

## Text:
{original_text[:3000]}

## Already Extracted (DO NOT repeat):
{existing_list}

## What to Extract

**Critical clues often missed:**
- ✅ Proper nouns: Names that could be answers (people, places, organizations)
- ✅ Abbreviations & nicknames: Alternative ways users might ask
- ✅ Specific identifiers: Team names, product names, work titles
- ✅ Unique terms: Specialized vocabulary that distinguishes this document

**Skip generic terms (not useful as clues):**
- ❌ Category words: "university", "team", "airport" (without specific name)
- ❌ Common adjectives: "famous", "important", "retired"

**Ask yourself**: 
"If someone asks a question where THIS is the answer, would we find this document?"
- "Who coached VCU in 2011?" → "Shaka Smart" ✅ (must extract)
- "What team?" → "basketball team" ❌ (too generic)

## Output (JSON):
{{"entities": [{{"name": "Entity Name", "type": "type_id"}}]}}
"""
            
            # 4. 调用 LLM
            llm_client = await create_llm_client(scenario='extract')
            from dataflow.core.ai.models import LLMMessage, LLMRole
            
            result = await llm_client.chat_with_schema(
                [LLMMessage(role=LLMRole.USER, content=prompt)],
                response_schema={
                    "type": "object",
                    "properties": {
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string"}
                                },
                                "required": ["name", "type"]
                            }
                        }
                    },
                    "required": ["entities"]
                },
                temperature=0.1
            )
            
            if not result or "entities" not in result:
                return []
            
            # 5. 过滤和去重
            entities = []
            skipped_duplicates = []
            llm_returned = result.get("entities", [])
            
            for e in llm_returned:
                name = e.get("name", "").strip()
                etype = e.get("type", "").strip()
                
                if not name or not etype:
                    continue
                
                # 类型校验
                if etype not in valid_types:
                    etype = "tags"  # 无效类型降级为 tags
                
                # 去重：只检查完全匹配（避免 "VCU Rams" 被 "Rams" 误判为重复）
                name_lower = name.lower()
                is_duplicate = name_lower in existing_entity_names
                
                if is_duplicate:
                    skipped_duplicates.append(name)
                    continue
                
                entities.append({
                    "type": etype,
                    "name": name,
                    "description": "",
                    "value_type": "text"
                })
                existing_entity_names.add(name_lower)
            
            # 详细日志
            self.logger.info(
                f"🤖 LLM兜底: 返回={len(llm_returned)}, 去重={len(skipped_duplicates)}, 新增={len(entities)}"
            )
            if skipped_duplicates:
                self.logger.debug(f"   去重跳过: {skipped_duplicates[:5]}")
            if entities:
                entity_preview = ', '.join(
                    f"{e['type']}:{e['name'][:15]}" for e in entities[:5]
                )
                self.logger.info(f"   ✅ 新增: {entity_preview}{'...' if len(entities) > 5 else ''}")
            
            return entities
            
        except Exception as e:
            self.logger.warning(f"⚠️ LLM兜底失败: {e}")
            # 返回空，由主流程的分词器补充处理
            return []

    async def _update_source_status(
        self,
        chunks: List[SourceChunk],
        status: str,
        error: Optional[str] = None
    ) -> None:
        """
        更新源状态（Article 或 ChatConversation）
        
        Args:
            chunks: chunk列表（用于确定源类型和ID）
            status: 状态值（PENDING/PROCESSING/COMPLETED/FAILED）
            error: 错误信息（可选，失败时提供）
        """
        if not chunks:
            return
        
        from dataflow.db import Article, ChatConversation
        
        # 确定源类型和ID（同一批chunks应该来自同一个源）
        source_type = chunks[0].source_type
        source_id = chunks[0].source_id
        
        # 验证所有chunks来自同一个源
        if not all(c.source_type == source_type and c.source_id == source_id for c in chunks):
            self.logger.warning("Chunks来自不同的源，无法统一更新状态")
            return
        
        async with self.session_factory() as session:
            try:
                if source_type == "ARTICLE":
                    result = await session.execute(
                        select(Article).where(Article.id == source_id)
                    )
                    source = result.scalar_one_or_none()
                    
                    if source:
                        source.status = status
                        if error:
                            source.error = error
                        await session.commit()
                        self.logger.info(f"✅ 已更新文章状态: {source_id} -> {status}")
                    else:
                        self.logger.warning(f"文章不存在: {source_id}")
                
                elif source_type == "CHAT":
                    result = await session.execute(
                        select(ChatConversation).where(ChatConversation.id == source_id)
                    )
                    source = result.scalar_one_or_none()
                    
                    if source:
                        # ChatConversation 没有 status 字段，记录到 extra_data
                        if source.extra_data is None:
                            source.extra_data = {}
                        source.extra_data["extract_status"] = status
                        if error:
                            source.extra_data["extract_error"] = error
                        await session.commit()
                        self.logger.info(f"✅ 已更新会话提取状态: {source_id} -> {status}")
                    else:
                        self.logger.warning(f"会话不存在: {source_id}")
                
                else:
                    self.logger.warning(f"不支持的源类型: {source_type}")
            
            except Exception as e:
                self.logger.error(f"更新源状态失败: {e}", exc_info=True)
                # 不抛出异常，避免影响主流程
    