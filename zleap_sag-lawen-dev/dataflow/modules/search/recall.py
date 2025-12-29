"""
实体召回模块（Recall）

实现6步骤的复合搜索算法：
1. query找key：LLM抽取query的结构化属性，通过向量相似度找到关联实体
2. key找event：通过[key-query-related]用sql找到所有关联事项
3. 过滤Event（权重排序）：
   - 计算event权重：event_weight = balance * e1_weight + (1-balance) * key_weight_sum
   - 按权重排序筛选events（使用max_events限制）
   - 保留所有key（步骤1已通过max_entities限制数量）
4. 计算event-key权重向量：根据每个event包含key的情况计算权重
5. 反向计算key权重向量：根据event权重反向计算key重要性
6. 提取重要的key：通过阈值或top-n方式提取重要key
"""

from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
import time
import numpy as np

from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from dataflow.core.ai.base import BaseLLMClient
from dataflow.core.ai.models import LLMMessage, LLMRole
from dataflow.core.prompt.manager import PromptManager
from dataflow.core.storage.elasticsearch import get_es_client
from dataflow.core.storage.repositories.entity_repository import EntityVectorRepository
from dataflow.core.storage.repositories.event_repository import EventVectorRepository
from dataflow.db import SourceEvent, Entity, EventEntity, get_session_factory
from dataflow.exceptions import AIError
from dataflow.modules.load.processor import DocumentProcessor
from dataflow.modules.search.config import SearchConfig, RecallMode
from dataflow.modules.search.tracker import Tracker  # 🆕 统一使用Tracker
from dataflow.utils import get_logger

logger = get_logger("search.recall")


@dataclass
class RecallResult:
    """实体召回结果"""
    # 查询追踪信息
    original_query: str  # 原始查询文本（用于调试和追踪）

    # 最终结果
    # [{"key": str, "weight": float, "steps": List[int]}, ...]
    key_final: List[Dict[str, Any]]

    # 中间结果（用于调试）
    key_query_related: List[Dict[str, Any]]  # 步骤1结果
    event_key_query_related: List[str]       # 步骤2结果
    event_related: List[str]                 # 步骤3结果
    event_key_weights: Dict[str, float]      # 步骤4结果
    key_event_weights: Dict[str, float]      # 步骤5结果

    # 性能追踪信息
    step_timings: Dict[str, float]           # 各步骤耗时（单位：秒）
    step1_substep_timings: Optional[Dict[str, float]]  # 步骤1子步骤耗时（可选）


class RecallSearcher:
    """实体召回搜索器 - 实现6步骤复合搜索算法"""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        prompt_manager: PromptManager,
    ):
        """
        初始化实体召回搜索器

        Args:
            llm_client: LLM客户端
            prompt_manager: 提示词管理器
        """
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager
        self.session_factory = get_session_factory()
        self.logger = get_logger("search.recall")

        # 初始化Elasticsearch仓库
        self.es_client = get_es_client()
        self.entity_repo = EntityVectorRepository(self.es_client)
        self.event_repo = EventVectorRepository(self.es_client)

        # 初始化文档处理器用于生成向量
        self.processor = DocumentProcessor(llm_client=llm_client)

        self.logger.info(
            "实体召回搜索器初始化完成",
            extra={
                "embedding_model_name": self.processor.embedding_model_name,
            },
        )

    def _filter_entities_by_type(
        self,
        entities: List[Dict[str, Any]],
        config: SearchConfig,
        context: str = "",
        include_tags_backup: bool = True
    ) -> List[Dict[str, Any]]:
        """
        统一的实体类型过滤方法
        
        优先使用 focus_entity_types（白名单），否则使用 exclude_entity_types（黑名单）
        
        Args:
            entities: 待过滤的实体列表
            config: 搜索配置（包含 focus_entity_types 和 exclude_entity_types）
            context: 上下文描述（用于日志）
            include_tags_backup: 白名单模式下是否包含 tags 作为候补（应对分类错误）
            
        Returns:
            过滤后的实体列表
        """
        if not entities:
            return entities
            
        original_count = len(entities)
        
        # 优先使用白名单（focus_entity_types）
        if config.focus_entity_types:
            focus_types = set(config.focus_entity_types)
            
            # tags 作为兜底（应对分类偏差）
            if include_tags_backup:
                focus_types.add("tags")
            
            filtered = [e for e in entities if e.get("type") in focus_types]
            filtered_count = original_count - len(filtered)
            if filtered_count > 0:
                self.logger.info(
                    f"🎯 {context}白名单过滤: {original_count} → {len(filtered)} "
                    f"(-{filtered_count}个, 聚焦类型: {list(focus_types)[:8]})"
                )
            return filtered
        
        # 回退到黑名单（exclude_entity_types）
        if config.exclude_entity_types:
            exclude_types = set(config.exclude_entity_types)
            filtered = [e for e in entities if e.get("type") not in exclude_types]
            filtered_count = original_count - len(filtered)
            if filtered_count > 0:
                self.logger.info(
                    f"🚫 {context}黑名单过滤: {original_count} → {len(filtered)} "
                    f"(-{filtered_count}个, 排除类型: {list(exclude_types)})"
                )
            return filtered
        
        return entities

    async def search(self, config: SearchConfig) -> RecallResult:
        """
        执行8步骤搜索算法

        Args:
            config: 搜索配置

        Returns:
            实体召回结果
        """
        try:
            # 保存原始query用于结果追踪（必须在step1之前）
            original_query = config.query

            # 🆕 创建线索构建器
            tracker = Tracker(config)

            # 初始化步骤计时器
            step_timings = {}
            total_start = time.perf_counter()

            source_config_ids = config.get_source_config_ids()
            self.logger.info(
                f"开始实体召回：source_config_ids={source_config_ids[:5]}{'...' if len(source_config_ids) > 5 else ''}, "
                f"source_config_id_count={len(source_config_ids)}, query={config.query}"
            )

            # === 步骤1: query找key（语义扩展） ===
            step1_start = time.perf_counter()
            key_query_related, k1_weights, step1_substep_timings = await self._step1_query_to_keys(config)
            step1_end = time.perf_counter()
            step_timings["step1"] = step1_end - step1_start
            self.logger.info(f"步骤1完成：找到 {len(key_query_related)} 个相关key，耗时: {step_timings['step1']:.3f}s")

            # 🆕 记录线索：query → entity（仅快速模式）
            # 普通模式下，线索已经在 step1 内部通过 extracted_entity → entity 记录了
            # 快速模式下，需要在这里记录 query → entity，因为是直接用 query 召回的
            if config.recall.use_fast_mode:
                for entity in key_query_related:
                    # 获取实体权重信息（如果有）
                    entity_weight = entity.get("weight")
                    metadata = {
                        "method": "vector_search",
                        "step": "step1",
                        # 🆕 添加来源属性
                        "source_attribute": entity.get("source_attribute")
                    }
                    # 只有to节点是实体时才存储weight
                    if entity_weight is not None:
                        metadata["weight"] = entity_weight

                    tracker.add_clue(
                        stage="recall",
                        from_node=Tracker.build_query_node(config),
                        to_node=Tracker.build_entity_node(entity),
                        confidence=entity.get("similarity", 0.0),  # 统一使用similarity
                        metadata=metadata
                    )
                self.logger.debug(f"✅ 快速模式：为 {len(key_query_related)} 个实体创建了 query → entity 线索")

            # 🔍 显示召回实体的详细信息
            if key_query_related:
                self.logger.info(f"📋 步骤1召回实体详情 (共{len(key_query_related)}个):")
                for idx, entity in enumerate(key_query_related, 1):
                    self.logger.info(
                        f"  {idx}. 实体ID: {entity.get('entity_id')}, "
                        f"名称: '{entity.get('name')}', "
                        f"类型: {entity.get('type')}, "
                        f"相似度: {entity.get('similarity', 0.0):.4f}, "
                        f"来源属性: '{entity.get('source_attribute')}'"
                    )


            # 存储query召回的所有key到config中
            config.query_recalled_keys = key_query_related
            self.logger.debug(
                f"已将 {len(key_query_related)} 个query召回的key存储到config.query_recalled_keys")

            # === 步骤2: key找event（精准匹配） ===
            step2_start = time.perf_counter()
            event_key_query_related = await self._step2_keys_to_events(config, key_query_related)
            step2_end = time.perf_counter()
            step_timings["step2"] = step2_end - step2_start
            self.logger.info(
                f"步骤2完成：找到 {len(event_key_query_related)} 个key相关event，耗时: {step_timings['step2']:.3f}s")

            # === 步骤2.5: query直接搜索events（可选）===
            query_events = []
            query_event_similarities = {}  # 🆕 存储query召回events的相似度
            if config.recall.use_query_event_search:
                step2_5_start = time.perf_counter()
                query_events, query_event_similarities = await self._step2_query_to_events(config)
                step2_5_end = time.perf_counter()
                step_timings["step2_5"] = step2_5_end - step2_5_start
                self.logger.info(
                    f"步骤2.5完成：找到 {len(query_events)} 个query相关event，"
                    f"耗时: {step_timings['step2_5']:.3f}s"
                )

            # 合并events（去重）
            all_events = list(set(event_key_query_related + query_events))
            self.logger.info(
                f"📊 Events合并: key相关={len(event_key_query_related)}, "
                f"query相关={len(query_events)}, 总计={len(all_events)}"
            )

            # === 步骤3: 过滤Event（权重排序） ===
            step3_start = time.perf_counter()
            event_related, key_query_related, e1_weights = await self._step3_filter_events(
                all_events,
                key_query_related,
                k1_weights,
                config,
                query_event_similarities,  # 🆕 传递query召回events的相似度
            )
            step3_end = time.perf_counter()
            step_timings["step3"] = step3_end - step3_start
            self.logger.info(
                f"步骤3完成：过滤后 {len(event_related)} 个event, {len(key_query_related)} 个key，耗时: {step_timings['step3']:.3f}s")

            # 🔍 显示key保留情况（步骤3不再过滤key）
            original_key_count = len(key_query_related)
            retained_keys_count = len(key_query_related)

            self.logger.info(
                f"🔍 [Step3] Key保留情况: "
                f"步骤1召回={original_key_count}个 → "
                f"步骤3保留全部={retained_keys_count}个 "
                f"(步骤1已通过max_entities={config.recall.max_entities}限制数量)"
            )

            # 🔍 显示步骤3保留的key详情
            if key_query_related:
                # 步骤3保留了所有key，直接使用key_query_related
                retained_key_infos = key_query_related

                self.logger.info(f"📋 步骤3过滤后保留的key详情 (共{len(retained_key_infos)}个):")
                for idx, key_info in enumerate(retained_key_infos, 1):
                    self.logger.info(
                        f"  {idx}. 实体ID: {key_info['entity_id']}, "
                        f"名称: '{key_info['name']}', "
                        f"类型: {key_info['type']}, "
                        f"原始相似度: {key_info.get('similarity', 0.0):.4f}, "
                        f"来源属性: '{key_info.get('source_attribute', 'N/A')}'"
                    )
            else:
                self.logger.warning("⚠️ 步骤3后没有保留任何key，后续步骤将无结果")


            # === 步骤4: 计算event-key权重向量 ===
            step4_start = time.perf_counter()
            event_key_weights = await self._step4_calculate_event_key_weights(
                event_related, key_query_related, k1_weights, e1_weights, config
            )
            step4_end = time.perf_counter()
            step_timings["step4"] = step4_end - step4_start
            self.logger.info(
                f"步骤4完成：计算了 {len(event_key_weights)} 个event的key权重，耗时: {step_timings['step4']:.3f}s")

            # === 步骤5: 反向计算key权重向量 ===
            step5_start = time.perf_counter()
            key_event_weights = await self._step5_calculate_key_event_weights(
                event_related, key_query_related, event_key_weights, k1_weights, config
            )
            step5_end = time.perf_counter()
            step_timings["step5"] = step5_end - step5_start
            self.logger.info(f"步骤5完成：计算了 {len(key_event_weights)} 个key的反向权重，耗时: {step_timings['step5']:.3f}s")


            # === 步骤6: 提取重要的key ===
            step6_start = time.perf_counter()
            key_final = await self._step6_extract_important_keys(
                key_event_weights, config, key_query_related  # 🆕 传入 key_query_related
            )
            step6_end = time.perf_counter()
            step_timings["step6"] = step6_end - step6_start
            self.logger.info(f"步骤6完成：提取了 {len(key_final)} 个重要key，耗时: {step_timings['step6']:.3f}s")

            # 🔍 分析最终key的过滤情况
            if key_final:
                self.logger.info(
                    f"🔍 [Step6] 最终结果: "
                    f"步骤1召回={len(key_query_related)}个 → "
                    f"步骤3保留={len(key_query_related)}个 → "
                    f"步骤6提取={len(key_final)}个"
                )


            # === 🆕 步骤6完成后：生成最终线索 (display_level="final") ===
            # 为最终保留的entity生成线索，根据 query_source 决定线索来源
            # - origin query 召回的实体：origin_query → entity
            # - rewrite query 召回的实体：rewrite_query → entity
            if key_final:
                self.logger.info(f"🎯 [Step6] 生成 {len(key_final)} 条最终线索 (display_level=final)")

                for key in key_final:
                    # 从 key_query_related 中找到原始entity信息
                    original_entity = next(
                        (e for e in key_query_related if e["entity_id"] == key["key_id"]),
                        None
                    )

                    # 获取实体权重信息
                    entity_weight = key.get("weight")

                    if original_entity:
                        # 🔑 根据 query_source 决定线索的起点
                        query_source = original_entity.get("query_source", "origin")  # 默认 origin
                        use_origin = (query_source == "origin")

                        # query 召回的 key
                        metadata = {
                            "method": "final_result",
                            "step": "step6",
                            "steps": key.get("steps", [1]),
                            "source_attribute": original_entity.get("source_attribute"),
                            "query_source": query_source  # 🆕 记录来源
                        }
                        if entity_weight is not None:
                            metadata["weight"] = entity_weight

                        tracker.add_clue(
                            stage="recall",
                            from_node=Tracker.build_query_node(config, use_origin=use_origin),  # 🔑 根据来源选择 query
                            to_node=Tracker.build_entity_node(original_entity),
                            confidence=original_entity.get("similarity", 0.0),
                            relation="语义相似" if query_source == "origin" else ("LLM实体识别" if query_source == "rewrite" else "分词召回"),  # 🔑 区分关系
                            display_level="final",
                            metadata=metadata
                        )
                        self.logger.debug(
                            f"✅ [Step6] 为 {query_source} query 召回的实体 '{original_entity['name']}' 生成 final 线索"
                        )
                    else:
                        # 🆕 从 event 激活的 key（不在 key_query_related 中）
                        # 使用 key_final 中已有的信息构建 entity 节点
                        event_activated_entity = {
                            "entity_id": key["key_id"],
                            "name": key["name"],
                            "type": key["type"],
                        }
                        metadata = {
                            "method": "event_activated",
                            "step": "step6",
                            "steps": key.get("steps", [1]),
                            "source_attribute": "event_activation"  # 标记来源为事件激活
                        }
                        if entity_weight is not None:
                            metadata["weight"] = entity_weight

                        tracker.add_clue(
                            stage="recall",
                            from_node=Tracker.build_query_node(config),
                            to_node=Tracker.build_entity_node(event_activated_entity),
                            confidence=entity_weight if entity_weight else 0.0,  # 使用权重作为置信度
                            relation="事件关联",  # 🆕 区分于语义相似
                            display_level="final",
                            metadata=metadata
                        )
                        self.logger.debug(
                            f"✅ [Step6] 为事件激活的 key '{key['name']}' 生成线索"
                        )

                self.logger.info(
                    f"✅ [Step6] 最终线索生成完成，前端可根据这些 final 线索反推完整推理路径"
                )
            else:
                self.logger.warning(
                    f"⚠️ [Step6] 没有生成任何最终线索！key_final 为空。"
                    f"这可能导致前端精简模式图谱为空。"
                    f"建议检查配置参数：top_n_keys={config.recall.final_entity_count}, "
                    f"final_key_threshold={config.recall.entity_weight_threshold}"
                )


            # === 构建Recall阶段线索 ===
            # 使用config.query_recalled_keys（已在step6中过滤并更新为key_final格式）
            recall_clues = await self._build_recall_clues(
                config, config.query_recalled_keys)
            config.recall_clues = recall_clues
            self.logger.info(
                f"✨ 构建了 {len(recall_clues)} 条Recall线索 (query → entity), "
                f"这些是步骤1直接召回且在最终结果中的实体"
            )

            # 计算recall总耗时
            total_end = time.perf_counter()
            step_timings["total"] = total_end - total_start
            self.logger.info(
                f"实体召回完成：返回 {len(key_final)} 个重要key，总耗时: {step_timings['total']:.3f}s"
            )

            result = RecallResult(
                original_query=original_query,
                key_final=key_final,
                key_query_related=key_query_related,
                event_key_query_related=event_key_query_related,
                event_related=event_related,
                event_key_weights=event_key_weights,
                key_event_weights=key_event_weights,
                step_timings=step_timings,
                step1_substep_timings=step1_substep_timings,
            )

            return result

        except Exception as e:
            self.logger.error(f"实体召回失败: {e}", exc_info=True)
            raise

    # === 步骤实现方法 ===

    async def _step1_query_to_keys(
        self, config: SearchConfig
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float], Dict[str, float]]:
        """
        步骤1: query找key（语义扩展）
        LLM抽取query的结构化属性，通过向量相似度找到关联实体

        如果启用了query重写，会直接修改config.query为重写后的query，
        这样后续的模块都会自动使用重写后的query

        Returns:
            Tuple[List[Dict[str, Any]], Dict[str, float], Dict[str, float]]:
                (key_query_related, k1_weights, step1_substep_timings)
        """
        # TODO: 完善LLM属性抽取实现
        # 当前实现：
        # 1. 使用简单规则从query中提取属性（占位符）
        # 2. 将属性转换为向量（占位符实现）
        # 3. 使用向量搜索找到相似实体

        self.logger.info(
            f"步骤1开始: query='{config.query}', "
            f"key_similarity_threshold={config.recall.entity_similarity_threshold}, "
            f"max_keys={config.recall.max_entities}, "
            f"source_config_ids={config.get_source_config_ids()[:5]}{'...' if len(config.get_source_config_ids()) > 5 else ''}, "
            f"source_config_id_count={len(config.get_source_config_ids())}, "
            f"use_fast_mode={config.recall.use_fast_mode}"
        )

        step1_substep_timings = {}
        # 重置本次查询的分词实体集合，用于后续动态权重调整
        config.tokenizer_entity_ids = set()

        # 快速模式：直接用query的embedding召回key，跳过LLM属性抽取和query重写
        if config.recall.use_fast_mode:
            self.logger.info("🚀 使用快速模式：跳过LLM属性抽取，直接使用query embedding召回key")

            # 快速模式下也需要设置origin_query（未重写）
            config.original_query = config.query

            try:
                substep_start = time.perf_counter()
                # 生成原始query的embedding
                self.logger.debug(f"开始为query '{config.query}' 生成向量...")
                query_embedding = await self.processor.generate_embedding(config.query)
                self.logger.info(f"✅ Query向量生成成功，维度: {len(query_embedding)}")
                step1_substep_timings["fast_generate_embedding"] = time.perf_counter() - substep_start

                # 缓存query_embedding到config，避免重复生成
                config.query_embedding = query_embedding
                config.has_query_embedding = True
                self.logger.debug("📦 Query向量已缓存到config中")

                substep_start = time.perf_counter()
                # 直接搜索entity（不限制entity_type）
                source_config_ids = config.get_source_config_ids()
                self.logger.debug(
                    f"开始向量搜索: k={config.recall.vector_top_k}, source_config_ids={source_config_ids[:5]}{'...' if len(source_config_ids) > 5 else ''} (总量={len(source_config_ids)})")
                similar_entities = await self.entity_repo.search_similar(
                    query_vector=query_embedding,
                    k=config.recall.vector_top_k,
                    source_config_ids=config.get_source_config_ids(),  # 使用多源支持
                    entity_type=None,  # 不限制类型
                    include_type_threshold=True,
                )
                step1_substep_timings["fast_vector_search"] = time.perf_counter() - substep_start

                self.logger.info(f"📊 快速模式搜索到 {len(similar_entities)} 个候选实体")

                # 🆕 统一类型过滤（优先白名单，回退黑名单）
                similar_entities = self._filter_entities_by_type(
                    similar_entities, config, context="快速模式"
                )

                substep_start = time.perf_counter()
                # 过滤阈值
                key_query_related = []
                k1_weights = {}
                passed_count = 0

                for entity in similar_entities:
                    similarity = float(entity.get("_score", 0.0))

                    if similarity >= config.recall.entity_similarity_threshold:
                        # 获取类型阈值和权重
                        type_threshold = entity.get("type_threshold", 0.800)
                        type_weight = entity.get("type_weight", 1.0)
                        final_threshold = config.recall.entity_similarity_threshold
                        # 计算加权分数：similarity × type_weight
                        effective_score = similarity * type_weight
                        key_query_related.append({
                            "entity_id": entity["entity_id"],
                            "name": entity["name"],
                            "type": entity["type"],
                            "similarity": similarity,
                            "type_weight": type_weight,
                            "effective_score": effective_score,
                            "source_attribute": config.query,
                            "type_threshold": type_threshold,
                            "final_threshold": final_threshold,
                        })
                        k1_weights[entity["entity_id"]] = effective_score
                        passed_count += 1

                step1_substep_timings["fast_filter_threshold"] = time.perf_counter() - substep_start

                self.logger.info(
                    f"📈 快速模式阈值过滤结果: "
                    f"通过 {passed_count}/{len(similar_entities)}"
                )

                substep_start = time.perf_counter()
                # 去重并限制数量
                seen_entities = set()
                unique_keys = []
                for key_info in key_query_related:
                    entity_id = key_info["entity_id"]
                    if entity_id not in seen_entities:
                        seen_entities.add(entity_id)
                        unique_keys.append(key_info)

                key_query_related = unique_keys[:config.recall.max_entities]
                step1_substep_timings["fast_deduplicate"] = time.perf_counter() - substep_start

                # 🆕 分词器补充召回
                if config.recall.use_tokenizer:
                    substep_start = time.perf_counter()
                    existing_ids = {e["entity_id"] for e in key_query_related}

                    tokenizer_entities, new_count = await self._tokenizer_match_entities(
                        query=config.query,
                        source_config_ids=config.get_source_config_ids(),
                        top_k=config.recall.tokenizer_top_k,
                        exclude_types=list(config.exclude_entity_types) if not config.focus_entity_types else None,
                        focus_types=config.focus_entity_types or None,
                        existing_entity_ids=existing_ids
                    )
                    step1_substep_timings["fast_tokenizer"] = time.perf_counter() - substep_start

                    # 合并结果
                    if tokenizer_entities:
                        for entity in tokenizer_entities:
                            # 普通模式：k1_weights 直接使用 type_weight，不计算 similarity
                            type_weight = entity.get("type_weight", 1.0)
                            entity["effective_score"] = type_weight  # 用于排序
                            key_query_related.append(entity)
                            k1_weights[entity["entity_id"]] = type_weight
                            config.tokenizer_entity_ids.add(entity["entity_id"])

                        self.logger.info(f"🔀 快速模式分词合并: +{new_count} 个实体")

                    # 按加权分数排序后限制最终数量
                    key_query_related = sorted(key_query_related, key=lambda x: x.get("effective_score", 0), reverse=True)
                    key_query_related = key_query_related[:config.recall.max_entities]

                self.logger.info(
                    f"📋 快速模式完成: 最终返回 {len(key_query_related)} 个key"
                )

                if len(key_query_related) > 0:
                    top_entities = sorted(
                        key_query_related, key=lambda x: x.get("effective_score", 0), reverse=True)[:3]
                    top_info = [
                        f"'{e['name']}'({e['type']}, {e['similarity']:.3f})"
                        for e in top_entities
                    ]
                    self.logger.info(f"🏆 Top 3 相似实体: {', '.join(top_info)}")

                return key_query_related, k1_weights, step1_substep_timings

            except Exception as e:
                self.logger.error(f"❌ 快速模式失败: {e}")
                import traceback
                self.logger.debug(f"详细错误信息: {traceback.format_exc()}")
                raise

        # === 普通模式（新策略）：Query→Event + Keys交集过滤 ===
        self.logger.info("🔄 使用普通模式（新策略）：Query→Event + Keys交集过滤")

        # 🆕 创建线索构建器（统一方式）
        tracker = Tracker(config)

        # 保存原始query
        original_query = config.query
        config.original_query = original_query

        # =====================================================
        # 步骤0: 生成 Query Embedding（如果还没有）
        # =====================================================
        if not getattr(config, 'has_query_embedding', False) or config.query_embedding is None:
            self.logger.info("📌 新策略步骤0: 生成Query向量")
            substep_start = time.perf_counter()
            query_embedding = await self.processor.generate_embedding(config.query)
            config.query_embedding = query_embedding
            config.has_query_embedding = True
            step1_substep_timings["normal_generate_embedding"] = time.perf_counter() - substep_start
            self.logger.info(f"✅ Query向量生成成功，维度: {len(query_embedding)}")

        # =====================================================
        # 步骤1: Query 直接召回 Event（高阈值，保证质量）
        # =====================================================
        self.logger.info("📌 新策略步骤1: Query→Event（高阈值召回高质量事项）")
        substep_start = time.perf_counter()
        
        high_quality_events = await self.event_repo.search_similar_by_content(
            query_vector=config.query_embedding,
            k=config.recall.query_event_max,
            source_config_ids=config.get_source_config_ids()
        )
        
        # 按阈值过滤
        high_quality_events = [
            e for e in high_quality_events 
            if e.get("_score", 0) >= config.recall.query_event_threshold
        ]
        high_quality_event_ids = {e["event_id"] for e in high_quality_events}
        
        step1_substep_timings["new_step1_query_to_events"] = time.perf_counter() - substep_start
        self.logger.info(
            f"✅ 步骤1完成: 召回 {len(high_quality_events)} 个高质量事项 "
            f"(阈值={config.recall.query_event_threshold})"
        )

        # =====================================================
        # 步骤1.2: 从高质量事项反向召回背景实体（给LLM参考）
        # =====================================================
        background_entities = []
        if config.recall.background_entity_enabled and high_quality_events:
            self.logger.info("📌 新策略步骤1.2: 从高质量事项反向召回背景实体")
            substep_start = time.perf_counter()
            
            # 取 top-N 高质量事项
            top_n = min(config.recall.background_event_top_n, len(high_quality_events))
            top_hq_event_ids = [e["event_id"] for e in high_quality_events[:top_n]]
            
            # 反向查找这些事项关联的实体
            background_entities = await self._reverse_find_entities_by_events(
                event_ids=top_hq_event_ids,
                source_config_ids=config.get_source_config_ids(),
                min_name_length=config.recall.background_entity_min_name_length,
                max_count=config.recall.background_entity_max,
                focus_types=config.focus_entity_types or None
            )
            
            step1_substep_timings["new_step1_2_background_entities"] = time.perf_counter() - substep_start
            
            if background_entities:
                # 显示背景实体（按热度排序的前5个）
                bg_preview = [f"[{e['type']}]{e['name']}(热度={e.get('event_count', 0)})" 
                              for e in background_entities[:5]]
                self.logger.info(
                    f"✅ 步骤1.2完成: 反向召回 {len(background_entities)} 个背景实体 "
                    f"(来自top-{top_n}高质量事项)"
                )
                self.logger.info(f"📋 背景实体示例: {bg_preview}")
            else:
                self.logger.info("⚠️ 步骤1.2: 未找到背景实体")
        
        # 保存背景实体到 config，供后续步骤使用
        config.background_entities = background_entities

        # =====================================================
        # 步骤1.5: 向量召回实体（作为 LLM few-shots，可选）
        # =====================================================
        if config.recall.candidate_entities_enabled:
            self.logger.info("📌 新策略步骤1.5: 向量召回候选实体（作为 few-shots）")
            substep_start = time.perf_counter()
            candidate_entities, k1_weights = await self._vector_search_entities(config)
            step1_substep_timings["normal_vector_search"] = time.perf_counter() - substep_start

            if not candidate_entities:
                self.logger.warning("⚠️ 向量召回未找到任何候选实体")
                candidate_entities = []
        else:
            self.logger.info("⏭️ 步骤1.5: 向量召回候选实体已禁用")
            candidate_entities = []
            k1_weights = {}

        # === 步骤2: 获取实体类型 ===
        self.logger.info("📌 普通模式步骤2: 获取实体类型")
        substep_start = time.perf_counter()
        entity_types = await self._get_entity_types_for_source(
            config.get_source_config_ids()
        )
        step1_substep_timings["normal_get_entity_types"] = time.perf_counter() - substep_start

        if not entity_types:
            self.logger.warning("⚠️ 未找到任何实体类型，跳过LLM扩展")
            # 没有实体类型时，直接返回候选实体
            return candidate_entities, k1_weights, step1_substep_timings

        # === 步骤3: LLM合并调用（查询重写 + 聚焦类型 + 实体识别） ===
        if config.recall.llm_filter_enabled:
            self.logger.info("📌 普通模式步骤3: LLM合并调用（查询重写 + 聚焦类型 + 实体识别）")
            substep_start = time.perf_counter()
            rewritten_query, entity_names, focus_types = await self._llm_rewrite_and_extract_entities(
                query=config.query,
                candidate_entities=candidate_entities,
                entity_types=entity_types,
                config=config,
                background_entities=background_entities  # 🆕 传入背景实体
            )
            step1_substep_timings["normal_llm_rewrite_extract"] = time.perf_counter() - substep_start
            
            # focus_types 已在 _llm_rewrite_and_extract_entities 中保存到 config
            if focus_types:
                self.logger.info(f"🎯 聚焦实体类型: {focus_types} (将用于后续过滤)")

            # 处理查询重写结果（始终执行）
            if rewritten_query and rewritten_query != config.query:
                self.logger.info(f"📝 Query重写: '{config.query}' → '{rewritten_query}'")

                # 记录 origin_query → rewrite_query 线索
                origin_query_node = Tracker.build_query_node(config, use_origin=True)
                config.query = rewritten_query  # 更新 query
                rewrite_query_node = Tracker.build_query_node(config, use_origin=False)

                # 🆕 重新生成 embedding（使用重写后的 query）
                config.query_embedding = await self.processor.generate_embedding(rewritten_query)
                self.logger.info(f"✅ 重写后Query向量重新生成，维度: {len(config.query_embedding)}")

                tracker.add_clue(
                    stage="prepare",  # 🔧 查询重写属于准备阶段
                    from_node=origin_query_node,
                    to_node=rewrite_query_node,
                    confidence=1.0,
                    relation="查询重写",
                    display_level="intermediate",
                    metadata={"method": "query_rewrite", "step": "step3"}
                )
                self.logger.info(f"📝 已记录 origin_query → rewrite_query 线索")
            else:
                self.logger.info(f"📝 Query保持不变: '{config.query}'")

            # === 步骤4: 精确搜索（根据recall_mode选择ES或MySQL） ===
            # 所有LLM识别的实体都经过精确搜索
            if config.recall.recall_mode == RecallMode.EXACT:
                self.logger.info("📌 普通模式步骤4: SQL精确搜索（MySQL）")

                # Add logging for entity count before exact search
                self.logger.info(f"📝 SQL精确搜索实体数量: {len(entity_names)}个实体将参与精确搜索")

                substep_start = time.perf_counter()
                exact_matched_entities = await self._mysql_exact_search_entities(
                    expanded_entities=entity_names,
                    source_config_ids=config.get_source_config_ids(),
                    limit_per_name=config.recall.sql_fuzzy_search_limit,
                    exclude_types=config.exclude_entity_types if not config.focus_entity_types else None,
                    focus_types=config.focus_entity_types or None,
                )
                step1_substep_timings["normal_mysql_exact"] = time.perf_counter() - substep_start
            else:
                self.logger.info("📌 普通模式步骤4: ES精确搜索")

                # Add logging for entity count before exact search
                self.logger.info(f"📝 ES精确搜索实体数量: {len(entity_names)}个实体将参与精确搜索")

                substep_start = time.perf_counter()
                exact_matched_entities = await self._es_exact_search_entities(
                    expanded_entities=entity_names,
                    source_config_ids=config.get_source_config_ids(),
                    limit_per_name=config.recall.sql_fuzzy_search_limit,
                )
                step1_substep_timings["normal_es_exact"] = time.perf_counter() - substep_start

            # 为精确搜索的实体记录线索，并标记来源
            # 🔑 精确搜索是基于 LLM 从重写后的 query 中识别的实体名称
            # 所以线索应该从 rewrite_query 出发，并标记 query_source="rewrite"
            for entity in exact_matched_entities:
                # 🆕 标记实体来源于 rewrite query（LLM识别基于重写后的query）
                entity["query_source"] = "rewrite"

                real_entity_dict = {
                    "entity_id": entity["entity_id"],
                    "name": entity["name"],
                    "type": entity["type"],
                }
                metadata = {
                    "method": entity.get("match_method", "exact_search"),
                    "step": "step1",
                    "source_attribute": entity.get("source_attribute"),
                }
                tracker.add_clue(
                    stage="recall",
                    from_node=Tracker.build_query_node(config, use_origin=False),  # 🔑 使用重写后的 query
                    to_node=Tracker.build_entity_node(real_entity_dict),
                    confidence=entity.get("similarity", 0.0),
                    relation="LLM实体识别" if config.recall.recall_mode == RecallMode.EXACT else "LLM实体识别",
                    display_level="intermediate",
                    metadata=metadata
                )

            # === 步骤5: 合并结果 ===
            # 所有实体都经过了搜索，直接使用搜索结果（不再硬性截断25个）
            self.logger.info("📌 新策略步骤5: 合并搜索结果")
            substep_start = time.perf_counter()
            key_query_related, k1_weights = self._merge_exact_search_results(
                exact_matched_entities=exact_matched_entities,
                max_count=config.recall.key_max_count,  # 使用安全上限，不是硬性25
                entity_types=entity_types  # 传递实体类型以计算 type_weight 和 effective_score
            )
            step1_substep_timings["normal_merge_results"] = time.perf_counter() - substep_start
        else:
            # 未启用LLM过滤，直接使用候选实体
            self.logger.info("⏭️ LLM过滤未启用，直接使用向量召回结果")
            key_query_related = candidate_entities[:config.recall.key_max_count]

        # =====================================================
        # 步骤6: Query召回Event用于交集过滤（低阈值）
        # =====================================================
        self.logger.info("📌 新策略步骤6: Query→Event（低阈值用于交集过滤）")
        substep_start = time.perf_counter()
        
        filter_events = await self.event_repo.search_similar_by_content(
            query_vector=config.query_embedding,
            k=config.recall.filter_event_max,
            source_config_ids=config.get_source_config_ids()
        )
        
        # 按低阈值过滤
        filter_events = [
            e for e in filter_events 
            if e.get("_score", 0) >= config.recall.filter_event_threshold
        ]
        filter_event_ids = {e["event_id"] for e in filter_events}
        
        step1_substep_timings["new_step6_filter_events"] = time.perf_counter() - substep_start
        self.logger.info(
            f"✅ 步骤6完成: 召回 {len(filter_events)} 个过滤事项 "
            f"(阈值={config.recall.filter_event_threshold})"
        )

        # =====================================================
        # 步骤7: Keys→SQL→Events，然后与步骤6取交集过滤
        # =====================================================
        self.logger.info("📌 新策略步骤7: Keys→Events + 交集过滤")
        substep_start = time.perf_counter()
        
        # 获取所有 keys 关联的 events
        all_key_ids = [k["entity_id"] for k in key_query_related]
        
        if all_key_ids:
            # 查询 key-event 关联
            async with self.session_factory() as session:
                from dataflow.db import EventEntity
                query = (
                    select(EventEntity.entity_id, EventEntity.event_id)
                    .where(EventEntity.entity_id.in_(all_key_ids))
                )
                result = await session.execute(query)
                key_event_relations = result.fetchall()
            
            # 构建 key → events 映射
            key_to_events: Dict[str, Set[str]] = {}
            for entity_id, event_id in key_event_relations:
                if entity_id not in key_to_events:
                    key_to_events[entity_id] = set()
                key_to_events[entity_id].add(event_id)
            
            # 交集过滤：只保留关联到 filter_event_ids 的 keys
            valid_keys = []
            filtered_out_count = 0
            
            for key in key_query_related:
                entity_id = key["entity_id"]
                key_events = key_to_events.get(entity_id, set())
                
                # 检查是否有交集
                intersection = key_events & filter_event_ids
                
                if intersection:
                    # 有交集，保留这个 key
                    key["related_event_count"] = len(intersection)
                    valid_keys.append(key)
                else:
                    # 无交集，过滤掉
                    filtered_out_count += 1
                    self.logger.debug(
                        f"⚠️ Key '{key['name']}' 被交集过滤掉 "
                        f"(关联events={len(key_events)}, 与query无交集)"
                    )
            
            key_query_related = valid_keys
            self.logger.info(
                f"✅ 交集过滤: {filtered_out_count} 个key被过滤, "
                f"剩余 {len(key_query_related)} 个有效key"
            )
        
        step1_substep_timings["new_step7_intersection_filter"] = time.perf_counter() - substep_start

        # =====================================================
        # 步骤7.5: 兜底机制 - 如果交集过滤后完全为空，加入 top5 背景实体
        # =====================================================
        if len(key_query_related) == 0 and background_entities:
            self.logger.warning("⚠️ 交集过滤后无有效key，启用背景实体兜底")

            # 取 top5 背景实体作为兜底
            top_n = min(5, len(background_entities))
            for bg_entity in background_entities[:top_n]:
                type_weight = bg_entity.get("type_weight", 1.0)

                # 为背景实体添加必要字段
                bg_entity["similarity"] = 0.7  # 兜底默认相似度（仅用于显示）
                bg_entity["effective_score"] = type_weight  # 用于排序，但 k1_weights 只用 type_weight
                bg_entity["query_source"] = "background_fallback"  # 标记为兜底来源

                key_query_related.append(bg_entity)
                # 普通模式：k1_weights 直接使用 type_weight，不使用 effective_score
                k1_weights[bg_entity["entity_id"]] = type_weight
            
            # 显示兜底的背景实体
            fallback_preview = [
                f"[{e['type']}]{e['name']}(权重={e.get('type_weight', 1):.2f})"
                for e in background_entities[:top_n]
            ]
            self.logger.info(f"📋 兜底加入Top{top_n}背景实体: {fallback_preview}")

        # =====================================================
        # 步骤8: 分词器补充召回（可选）
        # =====================================================
        if config.recall.use_tokenizer and len(key_query_related) < 10:
            # 只有当有效keys太少时才启用分词补充
            self.logger.info("📌 新策略步骤8: 分词器补充召回（keys不足时启用）")
            substep_start = time.perf_counter()
            existing_ids = {e["entity_id"] for e in key_query_related}

            tokenizer_entities, new_count = await self._tokenizer_match_entities(
                query=config.query,
                source_config_ids=config.get_source_config_ids(),
                top_k=config.recall.tokenizer_top_k,
                exclude_types=list(config.exclude_entity_types) if not config.focus_entity_types else None,
                focus_types=config.focus_entity_types or None,
                existing_entity_ids=existing_ids
            )
            step1_substep_timings["normal_tokenizer"] = time.perf_counter() - substep_start

            if tokenizer_entities:
                # 分词实体也需要交集过滤
                for entity in tokenizer_entities:
                    entity_id = entity["entity_id"]

                    # 检查是否已存在
                    if entity_id in existing_ids:
                        continue

                    # 标记来源
                    entity["query_source"] = "tokenizer"

                    # 普通模式：k1_weights 直接使用 type_weight，不计算 similarity
                    type_weight = entity.get("type_weight", 1.0)
                    similarity = entity.get("similarity", config.recall.tokenizer_similarity)  # 仅用于显示
                    entity["effective_score"] = type_weight  # 用于排序

                    key_query_related.append(entity)
                    k1_weights[entity["entity_id"]] = type_weight
                    config.tokenizer_entity_ids.add(entity_id)

                    # 记录线索
                    tracker.add_clue(
                        stage="recall",
                        from_node=Tracker.build_query_node(config),
                        to_node=Tracker.build_entity_node({
                            "entity_id": entity["entity_id"],
                            "name": entity["name"],
                            "type": entity["type"],
                        }),
                        confidence=similarity,
                        relation="分词召回",
                        display_level="intermediate",
                        metadata={"method": "tokenizer", "step": "step_tokenizer"}
                    )

                self.logger.info(f"🔀 分词补充: +{new_count} 个实体")

        # =====================================================
        # 步骤8.5: 背景实体兜底（当keys不足时从背景实体补充）
        # =====================================================
        fallback_threshold = config.recall.background_fallback_threshold
        fallback_max = config.recall.background_fallback_max
        
        if len(key_query_related) < fallback_threshold and background_entities:
            self.logger.info(
                f"📌 新策略步骤8.5: 背景实体兜底 "
                f"(当前keys={len(key_query_related)} < 阈值{fallback_threshold})"
            )
            
            # 获取已存在的实体ID
            existing_ids = {k["entity_id"] for k in key_query_related}
            
            # 从背景实体中补充（已按热度排序）
            added_count = 0
            for entity in background_entities:
                if entity["entity_id"] not in existing_ids:
                    # 普通模式：k1_weights 直接使用 type_weight，不计算 similarity
                    type_weight = entity.get("type_weight", 1.0)

                    # 标记来源并设置权重
                    entity["source"] = "background_fallback"
                    entity["similarity"] = config.recall.background_entity_default_similarity  # 仅用于显示
                    entity["type_weight"] = type_weight
                    entity["effective_score"] = type_weight  # 用于排序，但 k1_weights 只用 type_weight
                    entity["source_attribute"] = f"背景实体(热度={entity.get('event_count', 0)})"

                    key_query_related.append(entity)
                    k1_weights[entity["entity_id"]] = type_weight
                    existing_ids.add(entity["entity_id"])
                    added_count += 1
                    
                    if added_count >= fallback_max:
                        break
            
            if added_count > 0:
                self.logger.info(
                    f"🔒 背景兜底: 补充 {added_count} 个背景实体 "
                    f"(来自高质量事项，按热度排序)"
                )
                # 打印补充的实体
                added_names = [
                    f"[{e['type']}]{e['name']}(热度={e.get('event_count', 0)})" 
                    for e in background_entities[:added_count]
                ][:5]
                self.logger.info(f"📋 兜底实体示例: {added_names}")
        else:
            if len(key_query_related) >= fallback_threshold:
                self.logger.info(
                    f"✅ 步骤8.5: keys充足 ({len(key_query_related)} >= {fallback_threshold})，无需兜底"
                )

        # =====================================================
        # 步骤9: 双策略截断（相似度阈值 + 安全上限）
        # =====================================================
        self.logger.info("📌 新策略步骤9: 双策略截断")
        
        # 先按 effective_score 过滤
        before_count = len(key_query_related)
        key_query_related = [
            k for k in key_query_related 
            if k.get("effective_score", 0) >= config.recall.key_score_threshold
        ]
        score_filtered = before_count - len(key_query_related)
        
        # 再按安全上限截断
        key_query_related = sorted(
            key_query_related, 
            key=lambda x: x.get("effective_score", 0), 
            reverse=True
        )[:config.recall.key_max_count]
        
        self.logger.info(
            f"✅ 双策略截断: 分数过滤掉{score_filtered}个 "
            f"(阈值={config.recall.key_score_threshold}), "
            f"最终保留 {len(key_query_related)} 个key "
            f"(上限={config.recall.key_max_count})"
        )

        # 更新 k1_weights（只保留有效的）
        valid_entity_ids = {k["entity_id"] for k in key_query_related}
        k1_weights = {eid: w for eid, w in k1_weights.items() if eid in valid_entity_ids}

        # 保存高质量事项ID到config，供后续步骤使用
        config.high_quality_event_ids = high_quality_event_ids

        # 汇总日志
        self.logger.info(
            f"📋 新策略召回完成: "
            f"高质量事项={len(high_quality_event_ids)}, "
            f"最终keys={len(key_query_related)}"
        )

        if len(key_query_related) > 0:
            # 显示最高加权分数的几个实体
            top_entities = sorted(
                key_query_related, key=lambda x: x.get("effective_score", 0), reverse=True)[:3]
            top_info = [
                f"'{e['name']}'({e['type']}, sim={e.get('similarity', 0):.3f}, w={e.get('type_weight', 1):.2f})"
                for e in top_entities
            ]
            self.logger.info(f"🏆 Top 3 实体: {', '.join(top_info)}")
        else:
            self.logger.error("❌ 普通模式步骤1最终结果: 未找到任何Keys！")

        return key_query_related, k1_weights, step1_substep_timings

    async def _step2_keys_to_events(
        self, config: SearchConfig, key_query_related: List[Dict[str, Any]]
    ) -> List[str]:
        """
        步骤2: key找event（精准匹配）
        通过[key-query-related]用sql找到所有关联事项

        同时记录线索：entity → event
        """
        if not key_query_related:
            return []

        key_entity_ids = [key["entity_id"] for key in key_query_related]

        # 🆕 构建 entity_id → source_attribute 映射
        entity_source_map = {
            key["entity_id"]: key.get("source_attribute")
            for key in key_query_related
        }

        # 🆕 创建线索构建器记录线索
        tracker = Tracker(config)

        async with self.session_factory() as session:
            # 查询entity-event关系（返回完整映射，用于记录线索）
            query = (
                select(EventEntity.entity_id, EventEntity.event_id)
                .where(EventEntity.entity_id.in_(key_entity_ids))
            )

            result = await session.execute(query)
            entity_event_pairs = result.fetchall()

            # 🆕 记录线索：entity → event（使用标准节点，查询event对象获取完整信息）
            # 先批量查询event对象
            event_ids_for_query = list(
                set(event_id for _, event_id in entity_event_pairs))
            events_query = select(SourceEvent).where(
                SourceEvent.id.in_(event_ids_for_query))
            events_result = await session.execute(events_query)
            events = {event.id: event for event in events_result.scalars().all()}

            # 同时查询entity对象
            entities_query = select(Entity).where(
                Entity.id.in_(key_entity_ids))
            entities_result = await session.execute(entities_query)
            entities = {
                entity.id: entity for entity in entities_result.scalars().all()}

            # 记录每个entity→event的线索
            for entity_id, event_id in entity_event_pairs:
                entity_obj = entities.get(entity_id)
                event_obj = events.get(event_id)

                # 构建entity和event节点
                if entity_obj:
                    entity_dict = {
                        "id": entity_obj.id,
                        "entity_id": entity_obj.id,  # 兼容字段
                        "name": entity_obj.name,
                        "type": entity_obj.type,
                        "description": entity_obj.description or "",
                        # 🆕 添加来源属性
                        "source_attribute": entity_source_map.get(entity_id)
                    }
                else:
                    # Fallback
                    entity_dict = {
                        "id": entity_id,
                        "entity_id": entity_id,
                        # 🆕 添加来源属性
                        "source_attribute": entity_source_map.get(entity_id)
                    }

                if event_obj:
                    # 从实体字典中获取相似度作为confidence（如果可用）
                    entity_similarity = entity_dict.get("similarity", 1.0)
                    metadata = {
                        "method": "database_lookup",
                        "step": "step2",
                        # 🆕 添加到metadata
                        "source_attribute": entity_dict.get("source_attribute")
                    }
                    # to节点是事件，不存储weight

                    # tracker.add_clue(
                    #     stage="recall",
                    #     from_node=Tracker.build_entity_node(entity_dict),
                    #     to_node=tracker.get_or_create_event_node(event_obj, "recall"),
                    #     confidence=entity_similarity,  # 使用实体的相似度
                    #     display_level="intermediate",  # 🆕 中间结果
                    #     metadata=metadata
                    # )

            # 返回去重的event_ids
            event_ids = list(
                set(event_id for _, event_id in entity_event_pairs))

        return event_ids

    async def _step2_query_to_events(
        self, config: SearchConfig
    ) -> Tuple[List[str], Dict[str, float]]:
        """
        Step 2.5: 使用重写后的query直接搜索events

        通过向量相似度（混合content和title）搜索与query相关的events

        Args:
            config: 搜索配置

        Returns:
            Tuple[List[str], Dict[str, float]]: (事件ID列表, {event_id: hybrid_similarity})
        """
        if not config.query:
            self.logger.warning("查询为空，跳过query直接搜索events")
            return [], {}

        self.logger.info(
            f"步骤2.5开始: 使用query搜索events，"
            f"query='{config.query}', "
            f"weight_ratio={config.recall.query_event_weight_ratio}, "
            f"threshold={config.recall.event_similarity_threshold}"
        )

        try:
            # 确保query_embedding已生成
            if not config.has_query_embedding or not config.query_embedding:
                config.query_embedding = await self.processor.generate_embedding(config.query)
                config.has_query_embedding = True
                self.logger.debug(f"📦 为query生成向量，维度: {len(config.query_embedding)}")

            query_vector = config.query_embedding

            # 使用ES向量搜索获取候选events
            # 搜索content_vector，获取事件基本信息
            candidate_events = await self.event_repo.search_similar_by_content(
                query_vector=query_vector,
                k=config.recall.max_events,  # 多取一些，用于后续过滤
                source_config_ids=config.get_source_config_ids(),
            )

            if not candidate_events:
                self.logger.info("步骤2.5: 未找到候选events")
                return [], {}

            self.logger.info(f"📊 步骤2.5: 找到 {len(candidate_events)} 个候选events")

            # 计算混合相似度并过滤
            filtered_event_ids = []
            weight_ratio = config.recall.query_event_weight_ratio

            for event in candidate_events:
                event_id = event.get("event_id")
                if not event_id:
                    continue

                # 获取content相似度
                content_similarity = float(event.get("_score", 0.0))

                # 直接使用 content_similarity，不再计算混合相似度（减少 ES 压力）
                hybrid_similarity = content_similarity

                # 应用阈值过滤
                if hybrid_similarity >= config.recall.event_similarity_threshold:
                    filtered_event_ids.append({
                        "event_id": event_id,
                        "title": event.get("title", ""),
                        "hybrid_similarity": hybrid_similarity,
                        "content_similarity": content_similarity,
                        "title_similarity": content_similarity,  # 不再使用 title，与 content 保持一致
                    })
                    self.logger.debug(
                        f"Event {event_id} 通过过滤: "
                        f"hybrid={hybrid_similarity:.4f}, "
                        f"content={content_similarity:.4f}"
                    )

            # 按混合相似度排序
            filtered_event_ids.sort(key=lambda x: x["hybrid_similarity"], reverse=True)

            # 提取event_ids
            result_event_ids = [e["event_id"] for e in filtered_event_ids]

            self.logger.info(
                f"📈 步骤2.5完成: "
                f"候选{len(candidate_events)}个 → "
                f"过滤后{len(result_event_ids)}个events"
            )

            # 显示top events
            if filtered_event_ids:
                top_events = filtered_event_ids[:3]
                for idx, event in enumerate(top_events, 1):
                    self.logger.info(
                        f"  {idx}. Event {event['event_id']}: "
                        f"标题='{event['title'][:50]}...', "
                        f"混合相似度={event['hybrid_similarity']:.4f}"
                    )

            # 🆕 记录线索：query → event
            tracker = Tracker(config)
            query_node = Tracker.build_query_node(config)

            # 批量获取event对象
            event_ids = [e["event_id"] for e in filtered_event_ids]
            if event_ids:
                async with self.session_factory() as session:
                    from dataflow.db import SourceEvent
                    query = select(SourceEvent).where(SourceEvent.id.in_(event_ids))
                    result = await session.execute(query)
                    event_objs = {event.id: event for event in result.scalars().all()}

                    for event_info in filtered_event_ids:
                        event_id = event_info["event_id"]
                        event_obj = event_objs.get(event_id)

                        if event_obj:
                            metadata = {
                                "method": "hybrid_vector_search",
                                "step": "step2_5",
                                "hybrid_similarity": event_info["hybrid_similarity"],
                                "content_similarity": event_info["content_similarity"],
                                "title_similarity": event_info["title_similarity"],
                                "weight_ratio": config.recall.query_event_weight_ratio
                            }

                            # tracker.add_clue(
                            #     stage="recall",
                            #     from_node=query_node,
                            #     to_node=tracker.get_or_create_event_node(event_obj, "recall"),
                            #     confidence=event_info["hybrid_similarity"],
                            #     relation="语义相似",
                            #     display_level="intermediate",
                            #     metadata=metadata
                            # )

                self.logger.debug(f"✅ 步骤2.5记录 {len(filtered_event_ids)} 条 query → event 线索")

            # 构建相似度映射
            query_event_similarities = {e["event_id"]: e["hybrid_similarity"] for e in filtered_event_ids}
            return result_event_ids, query_event_similarities

        except Exception as e:
            self.logger.error(f"步骤2.5执行失败: {e}", exc_info=True)
            import traceback
            self.logger.debug(f"详细错误信息: {traceback.format_exc()}")
            return [], {}


    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        import numpy as np
        return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))


    async def _step3_filter_events(
        self,
        event_key_query_related: List[str],
        key_query_related: List[Dict[str, Any]],
        k1_weights: Dict[str, float],
        config: SearchConfig,
        query_event_similarities: Optional[Dict[str, float]] = None,
    ) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, float]]:
        """
        步骤3: 过滤Event（权重排序）

        1. 使用 key 召回 + query 召回的 events
        2. 计算每个event的综合权重：
           event_weight = balance * e1_weight + (1-balance) * key_weight_sum
        3. 按权重排序筛选events（使用max_events限制）
        4. 保留所有key（不在步骤3过滤key，因为步骤1已限制数量）
        """
        # 1. 提取event IDs（包含 key 召回 + query 召回）
        all_event_ids_set = set(event_key_query_related)
        all_event_ids = list(all_event_ids_set)

        self.logger.info(
            f"📊 [Step3] Events数量: 总计={len(all_event_ids)}"
        )

        # 从ES批量获取事件信息和向量
        events_from_es = await self.event_repo.get_events_by_ids(all_event_ids)

        # 构建事件ID到向量和entity_ids的映射
        event_vectors = {}
        event_title_vectors = {}  # 🆕 存储title向量
        event_entities = {}  # event_id -> list of entity_ids
        for event in events_from_es:
            event_id = event.get("event_id")
            content_vector = event.get("content_vector")
            title_vector = event.get("title_vector")  # 🆕 获取title向量
            entity_ids = event.get("entity_ids", [])
            if event_id and content_vector:
                event_vectors[event_id] = content_vector
                event_entities[event_id] = entity_ids
            if event_id and title_vector:
                event_title_vectors[event_id] = title_vector

        self.logger.info(
            f"从ES获取 {len(all_event_ids)} 个事件，"
            f"成功获取content向量 {len(event_vectors)} 个，"
            f"成功获取title向量 {len(event_title_vectors)} 个，"
            f"成功获取entity_ids {len(event_entities)} 个"
        )

        # 确保 query_embedding 存在
        if not config.has_query_embedding or not config.query_embedding:
            config.query_embedding = await self.processor.generate_embedding(config.query)
            config.has_query_embedding = True

        # 计算 e1_weights（事件与查询的相似度，统一使用hybrid_similarity）
        e1_weights = {}
        query_event_sims = query_event_similarities or {}
        weight_ratio = config.recall.query_event_weight_ratio  # content权重

        for event_id in all_event_ids:
            # 优先使用步骤2.5传递的相似度（query召回的events）
            if event_id in query_event_sims:
                e1_weights[event_id] = query_event_sims[event_id]
            else:
                # 对于key召回的events，也计算hybrid_similarity
                content_vector = event_vectors.get(event_id)
                title_vector = event_title_vectors.get(event_id)

                if content_vector:
                    content_similarity = self._cosine_similarity(
                        config.query_embedding,
                        content_vector
                    )

                    if title_vector:
                        title_similarity = self._cosine_similarity(
                            config.query_embedding,
                            title_vector
                        )
                    else:
                        # 没有title向量时使用content相似度作为fallback
                        title_similarity = content_similarity

                    # 计算hybrid_similarity: ratio * content + (1 - ratio) * title
                    hybrid_similarity = (
                        weight_ratio * content_similarity +
                        (1 - weight_ratio) * title_similarity
                    )

                    # 应用阈值过滤
                    if hybrid_similarity >= config.recall.event_similarity_threshold:
                        e1_weights[event_id] = hybrid_similarity

        # 3. 计算每个event的综合权重
        event_weights = {}
        balance = config.recall.step4_event_key_balance

        for event_id in all_event_ids:
            # query-event相似度权重
            e1_weight = e1_weights.get(event_id, 0.0)

            # 从ES结果获取该event包含的所有key
            event_keys = event_entities.get(event_id, [])

            # 计算该event包含的所有key的k1_weights之和
            key_weight_sum = sum(
                k1_weights.get(key_id, 0.0) for key_id in event_keys
            )

            # 综合权重 = balance * e1_weight + (1-balance) * key_weight_sum
            combined_weight = balance * e1_weight + (1 - balance) * key_weight_sum
            event_weights[event_id] = combined_weight

        # 4. 按权重排序筛选events（使用max_events限制）
        sorted_events = sorted(
            event_weights.items(), key=lambda x: x[1], reverse=True
        )

        # 复用max_events限制数量
        event_related = [
            eid for eid, _ in sorted_events[: config.recall.max_events]
        ]

        self.logger.info(
            f"📊 [Step3] Events权重筛选: key_events={len(all_event_ids)} → "
            f"top-{config.recall.max_events}={len(event_related)}"
        )

        # 显示Top 5 events的权重
        if len(event_related) > 0:
            top5_events = sorted_events[: min(5, len(sorted_events))]
            self.logger.debug(
                f"🏆 Top {len(top5_events)} Events: {top5_events}"
            )

        # 5. 保留所有key（不在步骤3过滤key）
        # 直接返回完整的key_query_related，避免信息丢失
        self.logger.info(
            f"📊 [Step3] Keys保留: input={len(key_query_related)} → "
            f"保留全部={len(key_query_related)} (步骤1已限制数量)"
        )

        # 缓存event_entities映射，供后续步骤使用
        config.event_entities_cache = event_entities

        return event_related, key_query_related, e1_weights

    async def _step4_calculate_event_key_weights(
        self,
        event_related: List[str],
        key_query_related: List[Dict[str, Any]],
        k1_weights: Dict[str, float],
        e1_weights: Dict[str, float],
        config: SearchConfig,
    ) -> Dict[str, float]:
        """
        步骤4: 计算event-key权重向量
        公式: W = 0.5*s(e,Q) + ln(1 + Σ k1_weight * ln(1+count))
        """
        if not event_related or not key_query_related:
            return {}

        import math

        # 从完整信息中提取entity_id列表
        key_related = [key_info["entity_id"] for key_info in key_query_related]

        # 构建 entity_id → name 映射（用于统计出现次数）
        entity_names = {
            key_info["entity_id"]: key_info["name"]
            for key_info in key_query_related
        }

        event_key_weights = {}

        try:
            # 使用缓存的event_entities映射
            event_entities_cache = getattr(config, 'event_entities_cache', {})

            # 从ES获取event内容（用于统计key出现次数）
            events_data = await self.event_repo.get_events_by_ids(event_related)
            event_contents = {
                e.get("event_id"): f"{e.get('title', '')} {e.get('content', '')}"
                for e in events_data
            }

            for event_id in event_related:
                # 1. 获取 event 与 query 的相似度 s(e_j, Q)
                e1_weight = e1_weights.get(event_id, 0.0)

                # 2. 获取该 event 的内容
                full_text = event_contents.get(event_id, "")

                # 3. 获取该 event 包含的 keys（只保留step1召回的）
                event_keys = event_entities_cache.get(event_id, [])
                event_keys = [k for k in event_keys if k in key_related]

                # 4. 计算 Σ W_{K,f}(k_i) * ln(1 + count(k_i, e_j))
                key_weight_sum = 0.0
                for key_id in event_keys:
                    k1_weight = k1_weights.get(key_id, 0.0)
                    key_name = entity_names.get(key_id, "")

                    # 统计 key 在 event 原文中出现的次数（区分大小写）
                    count = full_text.count(key_name) if key_name else 0

                    # W_{K,f}(k_i) * ln(1 + count)
                    key_weight_sum += k1_weight * math.log(1 + count)

                # 5. 应用完整公式：W = 0.5 * s(e_j, Q) + ln(1 + key_weight_sum)
                total_weight = 0.5 * e1_weight + math.log(1 + key_weight_sum)
                event_key_weights[event_id] = total_weight

        except Exception as e:
            self.logger.error(f"步骤4计算event-key权重失败: {e}", exc_info=True)
            raise

        return event_key_weights

    async def _step5_calculate_key_event_weights(
        self,
        event_related: List[str],
        key_query_related: List[Dict[str, Any]],
        event_key_weights: Dict[str, float],
        k1_weights: Dict[str, float],
        config: SearchConfig,
    ) -> Dict[str, float]:
        """
        步骤5: 反向计算key权重向量
        根据每个event的权重反向计算key的重要性

        公式: W_key-event(k_i) = avg(W_event-key(e_j)) × core_boost
        其中 e_j contains k_i
        """
        if not event_related:
            return {}

        key_event_weights = {}

        try:
            # 使用缓存的event_entities映射
            event_entities_cache = getattr(config, 'event_entities_cache', {})

            # 构建反向索引：key_id → [event_ids]（一次遍历，同时收集所有key）
            all_keys_in_events = set()
            key_to_events: Dict[str, List[str]] = {}
            for event_id in event_related:
                event_keys = event_entities_cache.get(event_id, [])
                all_keys_in_events.update(event_keys)
                for key_id in event_keys:
                    if key_id not in key_to_events:
                        key_to_events[key_id] = []
                    key_to_events[key_id].append(event_id)

            self.logger.info(f"📊 [Step5] 从 {len(event_related)} 个 event 中提取到 {len(all_keys_in_events)} 个 key")

            # 收集所有event激活的新key（不在k1_weights中的）
            new_key_ids = [kid for kid in all_keys_in_events if kid not in k1_weights]
            self.logger.info(f"📊 [Step5] 其中 {len(new_key_ids)} 个是event激活的新key")

            # 🆕 获取原始查询（用于核心实体检测）
            original_query_lower = config.original_query.lower() if config.original_query else ""
            
            # 🆕 预加载实体名称（用于核心实体检测）- 批量查询优化
            entity_names_map = {}
            if all_keys_in_events:
                async with self.session_factory() as session:
                    result = await session.execute(
                        select(Entity.id, Entity.name).where(Entity.id.in_(list(all_keys_in_events)))
                    )
                    for row in result:
                        entity_names_map[row[0]] = row[1]
            
            # 为每个key计算权重（使用反向索引，O(1)查表）
            for key_id in all_keys_in_events:
                # 直接从反向索引获取包含该key的events
                key_events = key_to_events.get(key_id, [])

                # 🆕 1. Event 贡献：使用平均值（归一化），消除 event 数量偏差
                event_weights_list = [event_key_weights.get(eid, 0.0) for eid in key_events]
                if event_weights_list:
                    avg_event_weight = sum(event_weights_list) / len(event_weights_list)
                else:
                    avg_event_weight = 0.0

                # 🆕 2. 核心实体检测：实体名称是否出现在原始问题中
                entity_name = entity_names_map.get(key_id, "")
                is_core_entity = entity_name and entity_name.lower() in original_query_lower
                core_boost = 1.5 if is_core_entity else 1.0

                # 🆕 3. 完整公式：event贡献 + 核心实体加成
                # 设计理念：
                # - event 贡献使用平均值归一化，避免高频实体占优
                # - 核心实体（问题中直接提到的）获得 1.5 倍加成保护
                key_event_weights[key_id] = avg_event_weight * core_boost

        except Exception as e:
            self.logger.error(f"步骤5计算key-event权重失败: {e}", exc_info=True)
            raise

        return key_event_weights

    async def _step6_extract_important_keys(
        self,
        key_event_weights: Dict[str, float],
        config: SearchConfig,
        key_query_related: List[Dict[str, Any]] = None,  # 🆕 新增参数，用于获取 query_source
    ) -> List[Dict[str, Any]]:
        """
        步骤6: 提取重要的key
        设置相似度阈值或提取top-n重要的key

        Args:
            key_event_weights: key权重字典
            config: 搜索配置
            key_query_related: 步骤1召回的key列表（包含 query_source 信息）
        """
        # 获取key的详细信息
        key_final = []

        if not key_event_weights:
            return key_final

        # 🆕 构建 key_id → query_source 的映射
        key_source_map = {}
        if key_query_related:
            for key in key_query_related:
                key_id = key.get("entity_id")
                query_source = key.get("query_source", "origin")  # 默认 origin
                if key_id:
                    key_source_map[key_id] = query_source
        # 针对分词召回的key做动态权重提升，避免其因分数偏低被截断
        tokenizer_ids = getattr(config, "tokenizer_entity_ids", set())
        tokenizer_gap = getattr(config.recall, "tokenizer_priority_gap", 0.0)
        if tokenizer_gap > 0 and tokenizer_ids:
            token_weights = [
                weight for key_id, weight in key_event_weights.items()
                if key_id in tokenizer_ids
            ]
            non_token_weights = [
                weight for key_id, weight in key_event_weights.items()
                if key_id not in tokenizer_ids
            ]
            if token_weights and non_token_weights:
                min_token = min(token_weights)
                max_non_token = max(non_token_weights)
                desired_min = max_non_token + tokenizer_gap
                if min_token < desired_min:
                    bias = desired_min - min_token
                    boosted = 0
                    for key_id in tokenizer_ids:
                        if key_id in key_event_weights:
                            key_event_weights[key_id] += bias
                            boosted += 1
                    if boosted > 0:
                        self.logger.info(
                            f"🆙 分词key动态加权: +{bias:.3f}, 覆盖{boosted}个实体，确保其权重领先普通key {tokenizer_gap:.3f}"
                        )

        # 按权重排序
        sorted_keys = sorted(key_event_weights.items(),
                             key=lambda x: x[1], reverse=True)

        # 应用阈值或top-n筛选
        # Always apply threshold filter first
        filtered_keys = [
            (key_id, weight) for key_id, weight in sorted_keys
            if weight >= config.recall.entity_weight_threshold
        ]

        # Then apply top-N if configured
        if config.recall.final_entity_count:
            selected_keys = filtered_keys[: config.recall.final_entity_count]
        else:
            selected_keys = filtered_keys

        # 获取key的详细信息
        if selected_keys:
            key_ids = [key_id for key_id, _ in selected_keys]

            try:
                async with self.session_factory() as session:
                    query = select(Entity).where(Entity.id.in_(key_ids))
                    result = await session.execute(query)
                    entities = {
                        entity.id: entity for entity in result.scalars().all()}

                for key_id, weight in selected_keys:
                    entity = entities.get(key_id)
                    if entity:
                        # 🆕 从 key_source_map 获取 query_source
                        query_source = key_source_map.get(key_id, "origin")  # 默认 origin

                        key_final.append({
                            "key_id": key_id,
                            "name": entity.name,
                            "type": entity.type,
                            "weight": weight,
                            "steps": [1],  # 第一阶段，所有值都为1
                            "query_source": query_source,  # 🆕 添加 query_source
                        })
            except Exception as e:
                self.logger.error(f"步骤6提取重要keys失败: {e}", exc_info=True)
                raise

        # 筛选出最终被使用的query召回的key
        if key_final and config.query_recalled_keys:
            # 构建key_final的key_id到key对象的映射
            key_final_map = {key["key_id"]: key for key in key_final}

            # 记录原始数量
            original_count = len(config.query_recalled_keys)

            # 筛选出在key_final中的query召回的key，并使用key_final中的key对象
            used_query_keys = []
            for query_key in config.query_recalled_keys:
                entity_id = query_key["entity_id"]
                if entity_id in key_final_map:
                    # 使用key_final中的key对象（包含weight和steps等信息）
                    used_query_keys.append(key_final_map[entity_id])

            # 更新config.query_recalled_keys，只保留最终被使用的key（来自key_final）
            config.query_recalled_keys = used_query_keys

            self.logger.info(
                f"步骤6: query召回的key中总共{original_count}个 "
                f"有{len(used_query_keys)}个被保留在key_final中（使用key_final中的key对象）"
            )

            if used_query_keys:
                # 显示被保留的query召回的key
                used_key_names = [key["name"] for key in used_query_keys[:5]]
                self.logger.debug(
                    f"被保留的query召回key（前5个）: {', '.join(used_key_names)}")

        return key_final



    async def _build_recall_clues(
        self,
        config: SearchConfig,
        key_query_related: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        构建Recall阶段的线索（query → entity）

        使用统一的Tracker构建，确保数据结构一致性

        Args:
            config: 搜索配置
            key_query_related: query召回的实体列表

        Returns:
            Recall阶段的线索列表
        """
        from dataflow.modules.search.tracker import Tracker

        clues = []

        # query → entity线索
        for entity in key_query_related:
            # 统一使用similarity作为confidence
            confidence = entity.get("similarity", 0.0)

            # 获取实体权重信息（如果有）
            entity_weight = entity.get("weight")
            metadata = {
                "similarity": entity.get("similarity", 0.0),
                "method": entity.get("method", "vector_search"),
                "source_attribute": entity.get("source_attribute")  # 🆕 添加来源属性
            }
            # 只有to节点是实体时才存储weight
            if entity_weight is not None:
                metadata["weight"] = entity_weight

            # 使用统一构建器创建线索
            clue = Tracker.build_recall_clue(
                config=config,
                entity=entity,
                confidence=confidence,
                metadata=metadata
            )
            clues.append(clue)

            # 将to节点（entity节点）存入缓存，供expand阶段使用
            to_node = clue.get("to")
            if to_node and to_node.get("id"):
                config.entity_node_cache[to_node["id"]] = to_node

        return clues

    # === 普通模式新增方法 ===

    async def _get_entity_types_for_source(
        self, source_config_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        获取信息源的所有实体类型

        Args:
            source_config_ids: 信息源ID列表

        Returns:
            实体类型列表: [{"type": "person", "name": "人物", "description": "..."}, ...]
        """
        from dataflow.db import EntityType

        entity_types = []

        async with self.session_factory() as session:
            # 查询指定信息源的实体类型 + 全局类型
            query = (
                select(EntityType)
                .where(
                    (EntityType.source_config_id.in_(source_config_ids)) |
                    (EntityType.source_config_id.is_(None))  # 全局类型
                )
                .where(EntityType.is_active == True)
            )

            result = await session.execute(query)
            types = result.scalars().all()

            for entity_type in types:
                entity_types.append({
                    "type": entity_type.type,
                    "name": entity_type.name,
                    "description": entity_type.description or ""
                })

        self.logger.info(f"获取到 {len(entity_types)} 个实体类型")
        return entity_types

    def _build_rewrite_and_extract_schema(self) -> Dict[str, Any]:
        """
        构建查询重写+聚焦类型识别+目标类型识别+实体识别的JSON Schema
        """
        return {
            "type": "object",
            "properties": {
                "rewritten_query": {
                    "type": "string",
                    "description": "Rewritten query text"
                },
                "focus_entity_types": {
                    "type": "array",
                    "description": "2-6 entity types to START the search from (clues leading to answer)",
                    "items": {
                        "type": "string",
                        "description": "Entity type identifier (e.g. person, location, work)"
                    }
                },
                "target_entity_types": {
                    "type": "array",
                    "description": "1-3 entity types where the ANSWER is likely found. For 'Who directed X?' target is 'person'. For 'What city is X in?' target includes 'person' (who knows the city) and 'location'",
                    "items": {
                        "type": "string",
                        "description": "Entity type identifier"
                    }
                },
                "entities": {
                    "type": "array",
                    "description": "Extracted entity names (only of focus types)",
                    "items": {
                        "type": "string",
                        "description": "Entity name"
                    }
                }
            },
            "required": ["rewritten_query", "focus_entity_types", "target_entity_types", "entities"]
        }

    async def _llm_rewrite_and_extract_entities(
        self,
        query: str,
        candidate_entities: List[Dict[str, Any]],
        entity_types: List[Dict[str, Any]],
        config: SearchConfig,
        background_entities: Optional[List[Dict[str, Any]]] = None  # 🆕 背景实体
    ) -> Tuple[str, List[str], List[str]]:
        """
        合并的LLM调用：查询重写 + 聚焦类型识别 + 实体识别

        Args:
            query: 用户查询
            candidate_entities: 向量召回的候选实体列表（作为 few-shots）
            entity_types: 可用的实体类型列表
            config: 搜索配置
            background_entities: 背景实体列表（来自高质量事项，按热度排序）

        Returns:
            Tuple[rewritten_query, entity_names, focus_types]:
                - rewritten_query: 重写后的查询
                - entity_names: 识别出的所有相关实体名称列表
                - focus_types: LLM识别的聚焦实体类型列表
        """
        from datetime import datetime

        # 获取当前时间
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构建候选实体的格式化文本（简化格式）
        if candidate_entities:
            candidates_text = "\n".join([
                f"{i}. [{e['type']}] {e['name']}"
                for i, e in enumerate(candidate_entities)
            ])
        else:
            candidates_text = "(No candidates)"

        # 🆕 构建背景实体的格式化文本（来自高质量事项，按热度排序）
        if background_entities:
            background_text = "\n".join([
                f"{i+1}. [{e['type']}] {e['name']} (热度={e.get('event_count', 0)})"
                for i, e in enumerate(background_entities)
            ])
            self.logger.info(f"📋 传给LLM的背景实体: {len(background_entities)} 个")
        else:
            background_text = "(No background entities)"

        # 构建实体类型的格式化文本
        entity_types_text = "\n".join([
            f"- {t['type']}: {t['name']}" + (f" - {t['description']}" if t.get('description') else "")
            for t in entity_types
        ])

        try:
            # 渲染提示词模板
            prompt = self.prompt_manager.render(
                "rewrite_and_extract_entities",
                query=query,
                current_time=current_time,
                candidates=candidates_text,
                background_entities=background_text,  # 🆕 传入背景实体
                entity_types=entity_types_text,
                max_entities=config.recall.max_entities
            )

            # 调用LLM
            messages = [
                LLMMessage(role=LLMRole.USER, content=prompt)
            ]

            schema = self._build_rewrite_and_extract_schema()

            response = await self.llm_client.chat_with_schema(
                messages,
                response_schema=schema,
                temperature=0.1  # 低 temperature 保持稳定性，允许少量灵活性
            )

            # 解析重写后的查询
            rewritten_query = response.get("rewritten_query", "").strip()
            if not rewritten_query:
                rewritten_query = query  # 如果为空，使用原始查询

            # 🆕 解析聚焦实体类型（线索维度 → 用于Recall/Expand过滤）
            focus_types = response.get("focus_entity_types", [])
            if focus_types:
                # 保存到config供后续阶段使用
                config.focus_entity_types = focus_types
                self.logger.info(f"🎯 LLM识别的线索维度(focus): {focus_types}")

            # 🆕 解析目标实体类型（目标维度 → 用于Rerank加权）
            target_types = response.get("target_entity_types", [])
            if target_types:
                # 保存到config供Rerank阶段使用
                config.target_entity_types = target_types
                self.logger.info(f"🎯 LLM识别的目标维度(target): {target_types}")

            # 获取并去重实体列表
            entity_names = response.get("entities", [])

            # 去重：保持原始顺序，去除重复项
            seen = set()
            unique_entity_names = []
            for entity_name in entity_names:
                if entity_name and entity_name not in seen:
                    seen.add(entity_name)
                    unique_entity_names.append(entity_name)

            # 记录去重效果
            if len(entity_names) != len(unique_entity_names):
                self.logger.info(f"🔄 实体去重: 原始{len(entity_names)}个 → 去重后{len(unique_entity_names)}个")

            # 限制实体数量（使用 max_entities 限制）
            entity_names = unique_entity_names[:config.recall.max_entities]

            self.logger.info(
                f"🔄 LLM合并调用完成: "
                f"重写='{query}' → '{rewritten_query}', "
                f"识别出 {len(entity_names)} 个实体"
            )

            # 打印识别出的实体
            if entity_names:
                self.logger.info(f"📋 LLM识别的实体: {entity_names}")

            return rewritten_query, entity_names, focus_types

        except Exception as e:
            self.logger.error(f"LLM合并调用失败: {e}", exc_info=True)
            # 失败时返回原始查询和空列表
            return query, [], []

    async def _es_exact_search_entities(
        self,
        expanded_entities: List[str],
        source_config_ids: List[str],
        limit_per_name: int,
    ) -> List[Dict[str, Any]]:
        """
        ES精确搜索实体（使用全等匹配）

        Args:
            expanded_entities: LLM扩展生成的实体名称列表（字符串数组）
            source_config_ids: 信息源ID列表
            limit_per_name: 每个实体名的最大搜索结果数

        Returns:
            搜索到的实体列表
        """
        if not expanded_entities:
            return []

        # 过滤空字符串
        names = [name.strip() for name in expanded_entities if name.strip()]

        if not names:
            return []

        # 获取实体类型权重信息
        type_info = await self.entity_repo._get_entity_type_info(source_config_ids)

        # 使用 ES 批量精确搜索
        es_results = await self.entity_repo.search_by_names_exact(
            names=names,
            source_config_ids=source_config_ids,
            entity_types=None,  # 不使用类型过滤
            size_per_name=limit_per_name,
        )

        # 处理结果，去重
        results = []
        seen_ids = set()

        for entity in es_results:
            entity_id = entity.get("entity_id")
            entity_name = entity.get("name", "")
            entity_type = entity.get("type", "")

            if entity_id in seen_ids:
                continue

            seen_ids.add(entity_id)

            # 使用类型权重作为 similarity
            type_weight = type_info.get(entity_type, {}).get("weight", 1.0)

            results.append({
                "entity_id": entity_id,
                "name": entity_name,
                "type": entity_type,
                "similarity": type_weight,
                "type_weight": type_weight,
                "source_attribute": entity_name,  # 来源于哪个LLM生成的名称
                "match_method": "es_exact"
            })

        self.logger.info(
            f"ES精确搜索完成: "
            f"输入={len(names)}个名称, "
            f"找到={len(results)}个实体"
        )

        # 打印ES精确搜索找到的实体
        if results:
            es_names = [f"[{e['type']}]{e['name']}" for e in results]
            self.logger.info(f"📋 ES精确搜索实体: {es_names}")

        return results

    async def _tokenizer_match_entities(
        self,
        query: str,
        source_config_ids: List[str],
        top_k: int = 15,
        exclude_types: Optional[List[str]] = None,
        focus_types: Optional[List[str]] = None,
        existing_entity_ids: Optional[set] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        分词提取关键词 → 数据库前缀匹配实体

        Args:
            query: 查询文本
            source_config_ids: 数据源ID列表
            top_k: 最多提取的关键词数量
            exclude_types: 需要排除的实体类型（黑名单）
            focus_types: 聚焦的实体类型（白名单，优先级高于 exclude_types）
            existing_entity_ids: 已存在的实体ID集合（用于去重）

        Returns:
            (新增的实体列表, 新增数量)
        """
        from dataflow.core.ai.tokensize import extract_keywords

        # 1. 分词提取关键词
        keywords = extract_keywords(query, top_k=top_k, mode="tokenizer")
        if not keywords:
            self.logger.debug("分词器未提取到关键词")
            return [], 0

        self.logger.info(f"🔤 分词提取: {keywords}")

        # 2. 数据库匹配（仅精确匹配，禁用前缀匹配避免噪音）
        # 分词器补充召回使用类型权重作为 similarity
        matched_entities = await self._mysql_exact_search_entities(
            expanded_entities=keywords,
            source_config_ids=source_config_ids,
            limit_per_name=2,  # 每个关键词最多匹配2个实体
            exclude_types=exclude_types,
            focus_types=focus_types,
            use_prefix_match=False  # 🆕 禁用前缀匹配，避免 "New" 匹配到 "New York" 等噪音
        )

        if not matched_entities:
            self.logger.debug("分词关键词未匹配到数据库实体")
            return [], 0

        # 3. 去重（排除已存在的实体）
        existing_ids = existing_entity_ids or set()
        new_entities = []
        for entity in matched_entities:
            if entity["entity_id"] not in existing_ids:
                entity["match_method"] = "tokenizer"  # 标记来源
                new_entities.append(entity)

        # 🔧 限制分词补充的总数量（避免单个泛词如"质量"补充过多实体）
        # 按 type_weight 排序，优先保留高权重类型
        max_tokenizer_entities = 20  # 最多补充 20 个实体
        if len(new_entities) > max_tokenizer_entities:
            new_entities.sort(key=lambda x: x.get("type_weight", 1.0), reverse=True)
            truncated_count = len(new_entities) - max_tokenizer_entities
            new_entities = new_entities[:max_tokenizer_entities]
            self.logger.info(f"⚠️ 分词补充截断: 裁剪 {truncated_count} 个（保留Top {max_tokenizer_entities}）")

        new_count = len(new_entities)
        if new_count > 0:
            self.logger.info(
                f"✅ 分词匹配: 找到 {len(matched_entities)} 个, "
                f"去重后新增 {new_count} 个"
            )

        return new_entities, new_count

    async def _mysql_exact_search_entities(
        self,
        expanded_entities: List[str],
        source_config_ids: List[str],
        limit_per_name: int,
        exclude_types: Optional[List[str]] = None,
        focus_types: Optional[List[str]] = None,
        use_prefix_match: bool = True  # 🆕 控制是否使用前缀匹配
    ) -> List[Dict[str, Any]]:
        """
        SQL模糊搜索实体（优化版：前缀匹配 + 批量查询）

        优化策略：
        1. 使用 normalized_name 字段（已有索引 idx_normalized_name）
        2. 使用前缀匹配 LIKE 'name%'（可以使用索引，性能提升明显）
        3. 批量查询减少数据库往返次数
        4. 先精确匹配，再前缀匹配（fallback）
        5. 支持类型过滤：优先白名单(focus_types)，回退黑名单(exclude_types)
        6. 使用实体类型权重作为 similarity

        Args:
            expanded_entities: LLM扩展生成的实体名称列表（字符串数组）
            source_config_ids: 信息源ID列表
            limit_per_name: 每个实体名的最大搜索结果数
            exclude_types: 需要排除的实体类型列表（黑名单）
            focus_types: 聚焦的实体类型列表（白名单，优先级高于 exclude_types）
            use_prefix_match: 是否启用前缀匹配（默认True，分词器补充时应设为False避免噪音）

        Returns:
            搜索到的实体列表
        """
        if not expanded_entities:
            return []

        # 过滤空字符串
        raw_names = [
            name.strip()
            for name in expanded_entities
            if isinstance(name, str) and name.strip()
        ]
        if not raw_names:
            return []

        import time
        sql_start = time.perf_counter()

        def normalize_name(name: str) -> str:
            """标准化名称：转小写、去空格"""
            return name.lower().strip().replace(" ", "").replace("　", "")

        # normalized_name -> {name, type}
        name_to_entity: Dict[str, Dict[str, Any]] = {}
        normalized_names: List[str] = []
        for raw_name in raw_names:
            normalized = normalize_name(raw_name)
            normalized_names.append(normalized)
            name_to_entity[normalized] = {
                "name": raw_name,
                "type": "",
            }

        if not normalized_names:
            return []

        results: List[Dict[str, Any]] = []
        seen_ids: set = set()
        
        # 获取类型权重信息
        type_info = await self.entity_repo._get_entity_type_info(source_config_ids)

        async with self.session_factory() as session:
            # 策略 1：批量精确匹配 normalized_name
            exact_query = (
                select(Entity)
                .where(Entity.source_config_id.in_(source_config_ids))
                .where(Entity.normalized_name.in_(normalized_names))
            )
            # 🆕 类型过滤：优先白名单，回退黑名单
            if focus_types:
                exact_query = exact_query.where(Entity.type.in_(focus_types))
            elif exclude_types:
                exact_query = exact_query.where(~Entity.type.in_(exclude_types))
            exact_result = await session.execute(exact_query)
            exact_entities = exact_result.scalars().all()

            exact_count = 0
            for entity in exact_entities:
                if entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                exact_count += 1

                mapped = name_to_entity.get(entity.normalized_name, {})
                source_name = mapped.get("name", entity.name)

                # 获取类型权重
                entity_type_weight = type_info.get(entity.type, {}).get("weight", 1.0)
                results.append({
                    "entity_id": entity.id,
                    "name": entity.name,
                    "type": entity.type,
                    "similarity": entity_type_weight,  # 使用类型权重作为 similarity
                    "type_weight": entity_type_weight,
                    "source_attribute": source_name,
                    "match_method": "sql_exact_match",
                })

            if exact_count > 0:
                self.logger.info(f"✅ SQL精确匹配找到 {exact_count} 个实体")

            # 策略 2：前缀匹配（排除已精确匹配的名称）
            # 🆕 仅在 use_prefix_match=True 时执行前缀匹配
            remaining_norms = {
                n for n in normalized_names
                if n not in {e.normalized_name for e in exact_entities}
            }

            prefix_count = 0

            if use_prefix_match and remaining_norms:
                from collections import defaultdict
                # 当前不按类型分组，全部放在一个组中，预留扩展
                entities_by_type: Dict[str, List[str]] = defaultdict(list)
                for norm in remaining_norms:
                    entities_by_type[""].append(norm)

                for entity_type, norms in entities_by_type.items():
                    if not norms:
                        continue

                    batch_size = 20
                    for i in range(0, len(norms), batch_size):
                        batch_norms = norms[i:i + batch_size]

                        # 构建批量前缀匹配查询
                        conditions = [
                            Entity.normalized_name.like(f"{n}%")
                            for n in batch_norms
                        ]

                        query = (
                            select(Entity)
                            .where(Entity.source_config_id.in_(source_config_ids))
                            .where(or_(*conditions))
                        )
                        if entity_type:
                            query = query.where(Entity.type == entity_type)
                        # 类型过滤：优先白名单，回退黑名单
                        if focus_types:
                            query = query.where(Entity.type.in_(focus_types))
                        elif exclude_types:
                            query = query.where(~Entity.type.in_(exclude_types))

                        query = query.limit(limit_per_name * len(batch_norms))

                        result = await session.execute(query)
                        entities = result.scalars().all()

                        for entity in entities:
                            if entity.id in seen_ids:
                                continue
                            seen_ids.add(entity.id)
                            prefix_count += 1

                            matched_name = None
                            for n in batch_norms:
                                if entity.normalized_name.startswith(n):
                                    mapped = name_to_entity.get(n, {})
                                    matched_name = mapped.get("name", entity.name)
                                    break

                            # 获取类型权重
                            entity_type_weight = type_info.get(entity.type, {}).get("weight", 1.0)
                            results.append({
                                "entity_id": entity.id,
                                "name": entity.name,
                                "type": entity.type,
                                "similarity": entity_type_weight,  # 使用类型权重作为 similarity
                                "type_weight": entity_type_weight,
                                "source_attribute": matched_name or entity.name,
                                "match_method": "sql_prefix_match",
                            })

        sql_time = time.perf_counter() - sql_start
        self.logger.info(
            f"✅ SQL搜索完成（优化版）: "
            f"输入={len(raw_names)}个名称, "
            f"找到={len(results)}个实体 "
            f"(精确匹配={exact_count}, 前缀匹配={prefix_count}), "
            f"耗时={sql_time:.3f}秒"
        )

        if results:
            sample = [f"[{e['type']}]{e['name']}" for e in results[:10]]
            self.logger.info(f"📋 SQL搜索实体示例（前10个）: {sample}")

        return results

    async def _reverse_find_entities_by_events(
        self,
        event_ids: List[str],
        source_config_ids: List[str],
        min_name_length: int = 2,
        max_count: int = 20,
        focus_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        从事项反向查找关联的实体（按类型权重排序）
        
        Args:
            event_ids: 事项ID列表
            source_config_ids: 信息源ID列表
            min_name_length: 实体名称最小长度（过滤泛化实体）
            max_count: 最大返回数量
            focus_types: 聚焦的实体类型（可选）
        
        Returns:
            实体列表，按类型权重降序排序
        """
        if not event_ids:
            return []
        
        from collections import Counter
        from dataflow.db import EventEntity, Entity
        
        # 获取实体类型权重信息
        type_info = await self.entity_repo._get_entity_type_info(source_config_ids)
        
        async with self.session_factory() as session:
            # 1. 查找这些事项关联的实体ID
            query = (
                select(EventEntity.entity_id)
                .where(EventEntity.event_id.in_(event_ids))
            )
            result = await session.execute(query)
            entity_ids = [row[0] for row in result.fetchall()]
            
            if not entity_ids:
                return []
            
            # 2. 统计每个实体的热度（出现次数）
            entity_counter = Counter(entity_ids)
            unique_entity_ids = list(entity_counter.keys())
            
            # 3. 查询实体详细信息
            entity_query = (
                select(Entity)
                .where(
                    Entity.id.in_(unique_entity_ids),
                    Entity.source_config_id.in_(source_config_ids)
                )
            )
            entity_result = await session.execute(entity_query)
            entities = entity_result.scalars().all()
            
            # 4. 构建结果列表
            background_entities = []
            for entity in entities:
                # 过滤：名称长度
                if len(entity.name) < min_name_length:
                    continue
                
                # 过滤：实体类型
                if focus_types and entity.type not in focus_types:
                    continue
                
                event_count = entity_counter.get(entity.id, 0)
                
                # 获取类型权重（默认1.0）
                type_weight = type_info.get(entity.type, {}).get("weight", 1.0)
                
                background_entities.append({
                    "entity_id": entity.id,
                    "name": entity.name,
                    "type": entity.type,
                    "event_count": event_count,  # 热度
                    "type_weight": type_weight,  # 类型权重
                    "source": "background"
                })
            
            # 5. 按类型权重降序排序（权重相同则按热度排序）
            background_entities.sort(key=lambda x: (x["type_weight"], x["event_count"]), reverse=True)
            
            # 日志：显示排序结果
            if background_entities:
                top_preview = [
                    f"[{e['type']}]{e['name']}(权重={e['type_weight']:.2f}, 热度={e['event_count']})"
                    for e in background_entities[:5]
                ]
                self.logger.info(f"📊 背景实体(按类型权重排序Top5): {top_preview}")
            
            # 6. 限制数量
            return background_entities[:max_count]

    async def _vector_search_entities(
        self, config: SearchConfig
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """
        使用向量搜索召回实体（复用快速模式逻辑）

        Args:
            config: 搜索配置

        Returns:
            Tuple[candidate_entities, k1_weights]:
                - candidate_entities: 召回的实体列表
                - k1_weights: 实体ID到相似度的映射
        """
        self.logger.info(f"🔍 向量搜索实体: query='{config.query}'")

        try:
            # 检查是否已有缓存的query_embedding
            if config.has_query_embedding and config.query_embedding:
                query_embedding = config.query_embedding
                self.logger.debug(f"📦 使用缓存的query向量，维度: {len(query_embedding)}")
            else:
                # 生成原始query的embedding
                query_embedding = await self.processor.generate_embedding(config.query)
                # 缓存query_embedding到config
                config.query_embedding = query_embedding
                config.has_query_embedding = True
                self.logger.debug(f"✅ Query向量生成成功，维度: {len(query_embedding)}")

            # 向量搜索entity
            similar_entities = await self.entity_repo.search_similar(
                query_vector=query_embedding,
                k=config.recall.vector_top_k,
                source_config_ids=config.get_source_config_ids(),
                entity_type=None,  # 不限制类型
                include_type_threshold=True,
            )

            self.logger.info(f"📊 向量搜索到 {len(similar_entities)} 个候选实体")

            # 🆕 过滤指定类型的实体（start_time, end_time 等）
            exclude_types = set(config.exclude_entity_types)
            filtered_by_type_count = 0
            if exclude_types:
                original_count = len(similar_entities)
                similar_entities = [
                    e for e in similar_entities
                    if e.get("type") not in exclude_types
                ]
                filtered_by_type_count = original_count - len(similar_entities)
                if filtered_by_type_count > 0:
                    self.logger.info(
                        f"🚫 类型过滤: 过滤掉 {filtered_by_type_count} 个实体 (类型: {exclude_types})"
                    )

            # 过滤阈值
            candidate_entities = []
            k1_weights = {}

            for entity in similar_entities:
                similarity = float(entity.get("_score", 0.0))

                if similarity >= config.recall.entity_similarity_threshold:
                    # 获取类型阈值和权重
                    type_threshold = entity.get("type_threshold", 0.800)
                    type_weight = entity.get("type_weight", 1.0)
                    final_threshold = config.recall.entity_similarity_threshold
                    # 计算加权分数
                    effective_score = similarity * type_weight
                    candidate_entities.append({
                        "entity_id": entity["entity_id"],
                        "name": entity["name"],
                        "type": entity["type"],
                        "similarity": similarity,
                        "type_weight": type_weight,
                        "effective_score": effective_score,
                        "source_attribute": config.query,
                        "type_threshold": type_threshold,
                        "final_threshold": final_threshold,
                        "match_method": "vector_search"
                    })
                    # 普通模式：k1_weights 直接使用 type_weight，不计算向量相似度
                    k1_weights[entity["entity_id"]] = type_weight

            self.logger.info(
                f"📈 阈值过滤结果: 通过 {len(candidate_entities)}/{len(similar_entities)}"
                f"{f' (已过滤{filtered_by_type_count}个时间类型)' if filtered_by_type_count > 0 else ''}"
            )

            # 打印向量召回的实体详情
            if candidate_entities:
                entity_names = [f"[{e['type']}]{e['name']}" for e in candidate_entities]
                self.logger.info(f"📋 向量召回实体: {entity_names}")

            return candidate_entities, k1_weights

        except Exception as e:
            self.logger.error(f"❌ 向量搜索失败: {e}", exc_info=True)
            raise

    def _merge_exact_search_results(
        self,
        exact_matched_entities: List[Dict[str, Any]],
        max_count: int,
        entity_types: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """
        合并精确搜索结果

        Args:
            exact_matched_entities: 精确搜索到的实体列表
            max_count: 最大返回数量
            entity_types: 实体类型列表（包含 name 和 weight）

        Returns:
            Tuple[merged_entities, k1_weights]:
                - merged_entities: 合并去重后的实体列表
                - k1_weights: 实体ID到effective_score的映射
        """
        seen_ids = set()
        merged = []
        k1_weights = {}

        # 构建类型权重映射
        type_weight_map: Dict[str, float] = {}
        if entity_types:
            for et in entity_types:
                type_name = et.get("name", "")
                type_weight = et.get("weight", 1.0)
                type_weight_map[type_name] = type_weight

        # 添加精确搜索的实体（都已通过搜索验证）
        for entity in exact_matched_entities:
            entity_id = entity["entity_id"]
            if entity_id not in seen_ids:
                seen_ids.add(entity_id)

                # 获取 similarity 和 type_weight
                similarity = entity.get("similarity", 0.5)
                entity_type = entity.get("type", "")
                type_weight = type_weight_map.get(entity_type, 1.0)

                # 计算 effective_score = similarity × type_weight（用于排序）
                effective_score = similarity * type_weight

                # 设置到实体上
                entity["type_weight"] = type_weight
                entity["effective_score"] = effective_score

                merged.append(entity)
                # 普通模式：k1_weights 直接使用 type_weight，不使用 effective_score
                k1_weights[entity_id] = type_weight

        # 按 effective_score 排序并限制数量
        merged.sort(key=lambda x: x.get("effective_score", 0), reverse=True)
        merged = merged[:max_count]

        self.logger.info(
            f"搜索结果合并完成: "
            f"精确匹配={len(exact_matched_entities)}, "
            f"最终={len(merged)}"
        )

        # 打印合并后的最终实体
        if merged:
            merged_names = [f"[{e['type']}]{e['name']}" for e in merged]
            self.logger.info(f"📋 合并后实体: {merged_names}")

        return merged, k1_weights
