"""
搜索 Rerank 模块 - 段落级实现

实现6步骤的查找最重要原文块的方法：
1. key找content：根据[key-final]从sql中提取原文块[content-key-related]，从ES获取预存向量并计算和query的余弦相似度（记录event_id）
2. query找content：通过向量相似度（KNN+余弦相似度）在向量数据库找到原文块[content-query-related]（已删除）
3. content合并+去重：合并[content-key-related]和[content-query-related]（已删除，不再需要）
4. 制作[content-related]权重向量：使用公式 weight = 0.5*相似度 + ln(1 + Σ(key权重 × ln(1+出现次数) / step))
5. PageRank重排序：基于段落间的共同实体构建关系图，使用PageRank算法重新排序
6. 取Top-N并返回：按PageRank得分排序

返回格式：
Dict[str, Any]: 包含以下字段的字典：
    - sections (List[Dict]): 段落对象列表（按PageRank顺序排列）
    - clues (Dict): 召回线索信息
        - origin_query (str): 原始查询（重写前）
        - final_query (str): LLM重写后的查询（重写后）
        - query_entities (List[Dict]): 查询召回的实体列表（key_id改为id）
        - recall_entities (List[Dict]): 召回的实体列表（key_id改为id，过滤掉query_entities中的值）

关键特性：
- 实时权重计算：基于key在段落内容中的实际出现频次计算权重
- 内容感知：权重基于key在段落内容中的实际出现频次
- PageRank重排序：考虑段落间的关联关系，提升整体排序质量

"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import math
import re
import time
import asyncio
import logging
from collections import Counter, defaultdict


from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from dataflow.core.storage.elasticsearch import get_es_client
from dataflow.core.storage.repositories.source_chunk_repository import SourceChunkRepository
from dataflow.core.storage.repositories.event_repository import EventVectorRepository
from dataflow.db import SourceEvent, Entity, EventEntity, ArticleSection, Article, SourceChunk, get_session_factory
from dataflow.exceptions import AIError
from dataflow.modules.load.processor import DocumentProcessor
from dataflow.modules.search.config import SearchConfig, BM25Config
from dataflow.modules.search.tracker import Tracker  # 🆕 添加线索追踪器
from dataflow.utils import get_logger
from .base_pagerank import BasePageRankSearcher, ContentSearchResult

logger = get_logger("search.rerank.pagerank")


class RerankPageRankSearcher(BasePageRankSearcher):
    """Rerank段落搜索器 - 实现6步骤的查找最重要段落的方法"""


    async def search(
        self,
        key_final: List[Dict[str, Any]],
        config: SearchConfig
    ) -> Dict[str, Any]:
        """
        Rerank 搜索主方法（段落级 + PageRank）

        整合步骤1-6，统一进行query向量化，避免重复计算

        步骤流程：
          1. key找content（向量相似度过滤）：基于实体关联找到相关段落
          2. query找content（向量相似度过滤）：基于语义相似度找到相关段落（已删除）
          3. 合并content去重（优先保留step1结果）：实体召回的段落优先级更高（已删除）
          4. 计算段落权重向量：结合相似度和实体权重计算权重并排序
          5. PageRank重排序：基于段落间的共同实体构建关系图，使用PageRank算法重新排序
          6. 选择Top-N段落：按PageRank得分排序并保留线索

        Args:
            key_final: 从Recall返回的关键实体列表
            config: Rerank搜索配置

        Returns:
            Dict[str, Any]: 包含以下字段的字典：
                - sections (List[Dict]): 段落对象列表（按PageRank顺序排列）
                - clues (Dict): 召回线索信息
                    - origin_query (str): 原始查询（重写前）
                    - final_query (str): LLM重写后的查询（重写后）
                    - query_entities (List[Dict]): 查询召回的实体列表（key_id改为id）
                    - recall_entities (List[Dict]): 召回的实体列表（key_id改为id，过滤掉query_entities中的值）
        """
        try:
            # 记录总体开始时间
            overall_start = time.perf_counter()

            self.logger.info("=" * 80)
            self.logger.info(f"【段落级】Rerank搜索开始")
            self.logger.info(f"Query: '{config.query}'")
            self.logger.info(f"Source IDs: {config.get_source_config_ids()}")
            self.logger.info("=" * 80)
            self.logger.info("【段落级】Rerank搜索配置")
            self.logger.info(f"  - skip_pagerank: {config.rerank.skip_pagerank}")
            self.logger.info("=" * 80)
            if config.rerank.skip_pagerank:
                self.logger.warning(
                    "⚠️  警告: skip_pagerank=True，"
                    "已跳过 PageRank 重排序，排序质量可能下降但速度更快"
                )

            # 统一进行query向量化（避免在step1和step2中重复计算）
            vector_start = time.perf_counter()
            query_vector = await self._generate_query_vector(config.query, config)
            vector_time = time.perf_counter() - vector_start
            if config.has_query_embedding:
                self.logger.info(
                    f"✓ 使用缓存的query向量，维度: {len(query_vector)}, 耗时: {vector_time:.3f}秒")
            else:
                self.logger.info(
                    f"✓ 查询向量生成成功，维度: {len(query_vector)}, 耗时: {vector_time:.3f}秒")

            # 用于记录各步骤耗时
            step_times = {}

            # 步骤1: key->content
            self.logger.info("\n" + "=" * 80)
            self.logger.info("【Step1】执行实体召回（已禁用Query召回）...")
            self.logger.info("=" * 80)
            step1_start = time.perf_counter()

            # 执行 step1
            step1_results = await self._step1_keys_to_contents(
                key_final=key_final,
                query=config.query,
                source_config_ids=config.get_source_config_ids(),
                query_vector=query_vector,
                config=config
            )

            # 🆕 BM25 搜索作为独立的召回通道
            bm25_results = []
            if config.bm25_enabled:
                self.logger.info("\n" + "=" * 80)
                self.logger.info("【BM25】执行BM25搜索召回...")
                self.logger.info("=" * 80)

                from dataflow.modules.search.bm25 import BM25Searcher
                bm25_searcher = BM25Searcher()
                bm25_config = BM25Config(
                    top_k=config.bm25_top_k,
                    title_weight=config.bm25_title_weight,
                    content_weight=config.bm25_content_weight
                )

                bm25_chunks = await bm25_searcher.search_chunks(
                    query=config.query,
                    source_config_ids=config.get_source_config_ids(),
                    config=bm25_config
                )

                # 将 BM25 结果转换为统一格式
                for idx, chunk in enumerate(bm25_chunks):
                    bm25_results.append({
                        "chunk_id": chunk["chunk_id"],
                        "chunk": chunk,  # 完整的 chunk 信息
                        "heading": chunk["heading"],
                        "content": chunk["content"],
                        "score": chunk["score"],  # BM25 分数
                        "source": "bm25",  # 标记来源为 bm25
                        "clues": [],  # BM25 召回的段落没有实体线索
                        "bm25_rank": idx + 1,  # 记录 BM25 排名
                    })

                self.logger.info(f"✓ BM25 召回完成: {len(bm25_results)} 个段落")

            step1_time = time.perf_counter() - step1_start
            step_times['Step1执行'] = step1_time

            # 步骤4: 计算权重并排序（使用多跳衰减 + 目标维度加权）- 使用统一方法
            step4_start = time.perf_counter()

            # 合并 Step1 和 BM25 的召回结果（按 chunk_id 去重合并）
            self.logger.info("合并 Step1 和 BM25 召回结果（按 chunk_id 去重）...")
            chunk_dict = {}

            # 处理 step1_results（entity召回）
            for result in step1_results:
                chunk_id = result.get("chunk_id")
                if not chunk_id:
                    continue

                if chunk_id not in chunk_dict:
                    chunk_dict[chunk_id] = {
                        "chunk_id": chunk_id,
                        "chunk": result.get("chunk"),
                        "heading": result.get("heading"),
                        "content": result.get("content"),
                        "score": result.get("score", 0.0),  # 相似度分数
                        "source": "entity",  # 标记为entity召回
                        "clues": result.get("clues", []),
                        "recall_sources": ["entity"],  # 记录所有召回来源
                        "bm25_rank": None,  # 默认没有bm25排名
                        "weight": result.get("weight", 0.0),
                    }

            # 处理 bm25_results，合并或新增
            for result in bm25_results:
                chunk_id = result.get("chunk_id")
                if not chunk_id:
                    continue

                if chunk_id in chunk_dict:
                    # 已存在，合并bm25信息
                    chunk_dict[chunk_id]["recall_sources"].append("bm25")
                    chunk_dict[chunk_id]["bm25_rank"] = result.get("bm25_rank")
                    # 更新source标记为both，表示来自多个源
                    if "entity" in chunk_dict[chunk_id]["recall_sources"]:
                        chunk_dict[chunk_id]["source"] = "both"
                else:
                    # 新增bm25召回的段落
                    chunk_dict[chunk_id] = {
                        "chunk_id": chunk_id,
                        "chunk": result.get("chunk"),
                        "heading": result.get("heading"),
                        "content": result.get("content"),
                        "score": 0.0,  # BM25段落没有相似度分数
                        "source": "bm25",  # 标记为bm25召回
                        "clues": [],  # BM25召回的段落没有实体线索
                        "recall_sources": ["bm25"],
                        "bm25_rank": result.get("bm25_rank"),
                        "weight": 0.0,  # 初始权重为0
                    }

            # 转换为列表
            all_chunks = list(chunk_dict.values())

            merged_count = len(all_chunks)
            entity_only = sum(1 for c in all_chunks if c["source"] == "entity")
            bm25_only = sum(1 for c in all_chunks if c["source"] == "bm25")
            both_sources = sum(1 for c in all_chunks if c["source"] == "both")

            self.logger.info(
                f"✓ 合并完成: 共 {merged_count} 个独特段落 "
                f"(仅entity: {entity_only}, 仅bm25: {bm25_only}, 两者都有: {both_sources})"
            )

            sorted_results = await self._step4_calculate_weights(
                items=all_chunks,
                key_final=key_final,
                config=config,
                item_type="段落",
                store_detailed_scores=False  # 段落级不需要详细分数
            )
            step4_time = time.perf_counter() - step4_start
            step_times['Step4_权重计算'] = step4_time
            self.logger.info(
                f"✓ Step4 完成: 计算并排序 {len(sorted_results)} 个段落, 耗时: {step4_time:.3f}秒")

            # 🆕 步骤5: 根据配置决定是否执行 PageRank
            if config and config.rerank.skip_pagerank:
                # ✨ 跳过 PageRank模式
                self.logger.info("=" * 80)
                self.logger.info("【配置】skip_pagerank=True，跳过PageRank重排序")
                self.logger.info("将直接使用Step4权重排序结果进行Top-N筛选")
                self.logger.info("=" * 80)

                step5_time = 0.0  # PageRank未执行
                content_for_step6 = sorted_results  # 使用Step4结果

                # 记录跳过统计
                self.logger.warning(
                    f"⚠️  已跳过 PageRank（配置 skip_pagerank=True）, "
                    f"排序质量可能下降，但速度更快"
                )
            else:
                # ✨ 使用 PageRank模式
                self.logger.info("=" * 80)
                self.logger.info("【配置】skip_pagerank=False，执行PageRank重排序")
                self.logger.info("=" * 80)

                # 步骤5: PageRank 重排序
                step5_start = time.perf_counter()
                pagerank_results = await self._step5_pagerank_rerank(
                    weighted_contents=sorted_results,
                    config=config
                )
                step5_time = time.perf_counter() - step5_start
                step_times['Step5_PageRank重排序'] = step5_time
                self.logger.info(
                    f"✓ Step5 完成: PageRank 重排序 {len(pagerank_results)} 个段落, 耗时: {step5_time:.3f}秒")

                content_for_step6 = pagerank_results  # 使用PageRank结果

            # 步骤6: 统一进行 Top-N 筛选（两种模式都执行）
            step6_start = time.perf_counter()
            final_sections = await self._step6_get_topn_sections(
                sorted_contents=content_for_step6,  # 根据模式选择的结果
                top_k=config.rerank.max_results,
                config=config
            )
            step6_time = time.perf_counter() - step6_start
            step_times['Step6_Top-N筛选'] = step6_time
            self.logger.info(f"✓ Step6 完成: 最终返回 {len(final_sections)} 个段落, 耗时: {step6_time:.3f}秒")

            # 计算总耗时
            overall_time = time.perf_counter() - overall_start

            # 输出耗时统计汇总
            self.logger.info("\n" + "=" * 80)
            self.logger.info("【段落级】各步骤耗时汇总:")
            self.logger.info("-" * 80)
            self.logger.info(
                f"查询向量生成: {vector_time:.3f}秒 ({vector_time/overall_time*100:.1f}%)")
            for step_name, step_time in step_times.items():
                self.logger.info(
                    f"{step_name}: {step_time:.3f}秒 ({step_time/overall_time*100:.1f}%)")
            self.logger.info("-" * 80)
            self.logger.info(f"✓ 总耗时: {overall_time:.3f}秒")
            self.logger.info("=" * 80)

            # 直接返回段落列表
            return {"sections": final_sections}

        except Exception as e:
            self.logger.error(f"[段落级] 搜索失败: {e}", exc_info=True)
            return {"sections": []}  # 失败时返回空字典

    async def _step1_keys_to_contents(
        self,
        key_final: List[Dict[str, Any]],
        query: str,
        source_config_ids: List[str],
        query_vector: Optional[List[float]] = None,
        config: Optional[SearchConfig] = None
    ) -> List[Dict[str, Any]]:
        """
        步骤1: key找content

        复用父类 _keys_to_events 方法获取事件，然后进一步获取这些事件关联的原文块并计算相似度。
        召回路径：Key → Entity → Event → Chunk

        Args:
            key_final: 从Recall返回的key_final数据
            query: 查询文本
            source_config_ids: 数据源配置ID列表
            query_vector: 可选的查询向量
            config: 搜索配置

        Returns:
            ContentSearchResult对象列表，按余弦相似度降序排序
        """
        try:
            self.logger.info(
                f"[段落级Step1] 开始召回: 处理 {len(key_final)} 个key, query='{query}'")

            if not key_final:
                return []

            # 🆕 调用父类方法获取事件（Key → Entity → Event）
            event_results = await self._keys_to_events(
                key_final=key_final,
                query=query,
                source_config_ids=source_config_ids,
                query_vector=query_vector,
                config=config
            )

            if not event_results:
                self.logger.warning("未找到相关事件")
                return []

            self.logger.info(f"[段落级Step1] 找到 {len(event_results)} 个相关事件")

            # 提取事件ID列表和 event_to_entities 映射
            event_ids = [result["event_id"] for result in event_results]

            # 从事件中提取 event_to_entities 映射
            event_to_entities = {}
            for result in event_results:
                event_id = result["event_id"]
                # 从 clues 中提取实体ID
                entity_ids = [clue["id"] for clue in result.get("clues", [])]
                event_to_entities[event_id] = entity_ids

            async with self.session_factory() as session:
                # 1. 获取事件详情并提取 chunk_ids
                from sqlalchemy import select, and_
                from dataflow.db import SourceEvent

                event_detail_query = (
                    select(SourceEvent)
                    .where(
                        and_(
                            SourceEvent.source_config_id.in_(source_config_ids),
                            SourceEvent.id.in_(event_ids)
                        )
                    )
                )

                event_detail_result = await session.execute(event_detail_query)
                events = event_detail_result.scalars().all()

                # 收集 chunk_ids 和建立映射
                chunk_ids = set()
                event_to_chunk = {}
                event_title_map = {}

                for event in events:
                    if event.chunk_id:
                        event_to_chunk[event.id] = event.chunk_id
                        chunk_ids.add(event.chunk_id)
                        event_title_map[event.id] = event.title

                if not chunk_ids:
                    self.logger.warning("所有事件都没有关联到原文块")
                    return []

                self.logger.info(
                    f"收集到 {len(chunk_ids)} 个原文块ID（来自 {len(events)} 个事件）")

                # 2. 获取原文块数据
                chunk_query = (
                    select(SourceChunk)
                    .where(
                        and_(
                            SourceChunk.source_config_id.in_(source_config_ids),
                            SourceChunk.id.in_(list(chunk_ids))
                        )
                    )
                    .order_by(SourceChunk.rank)
                )

                chunk_result = await session.execute(chunk_query)
                chunks = chunk_result.scalars().all()

                if not chunks:
                    self.logger.warning("未找到相关原文块")
                    return []

                self.logger.info(f"从 MySQL 找到 {len(chunks)} 个原文块")

                # 3. 构建 chunk_to_events 反向映射
                chunk_to_events = {}
                for event_id, chunk_id in event_to_chunk.items():
                    if chunk_id not in chunk_to_events:
                        chunk_to_events[chunk_id] = []
                    chunk_to_events[chunk_id].append(event_id)

                # 4. 为每个 chunk 构建数据
                from dataflow.modules.search.ranking.base_pagerank import ContentSearchResult

                content_results = []

                for chunk in chunks:
                    chunk_id = chunk.id

                    # 获取关联的事件ID列表
                    related_event_ids = chunk_to_events.get(chunk_id, [])
                    if not related_event_ids:
                        self.logger.warning(f"原文块 {chunk_id[:8]}... 没有找到关联的事件")
                        continue

                    # 收集所有召回该 chunk 的实体（clues）
                    chunk_clues = []
                    seen_entity_ids = set()

                    for event_id in related_event_ids:
                        # 获取该事件关联的所有实体
                        entity_ids_in_event = event_to_entities.get(event_id, [])

                        # 从 key_final 中查找这些实体的信息
                        for entity_id in entity_ids_in_event:
                            if entity_id not in seen_entity_ids:
                                # 查找对应的 key
                                key_info = next(
                                    (k for k in key_final
                                     if ((k.get("key_id") or k.get("id")) == entity_id)),
                                    None
                                )
                                if key_info:
                                    chunk_clues.append(key_info)
                                    seen_entity_ids.add(entity_id)

                    # 创建 ContentSearchResult
                    result = ContentSearchResult(
                        search_type=f"SQL-1",
                        source_config_id=source_config_ids[0] if source_config_ids else "",
                        source_id=chunk.source_id,
                        chunk_id=chunk_id,
                        rank=chunk.rank,
                        heading=chunk.heading,
                        content=chunk.content,
                        score=0.0,  # 将在后续计算
                        event_ids=related_event_ids,
                        clues=chunk_clues,
                    )
                    content_results.append(result)

                self.logger.info(f"构建了 {len(content_results)} 个原文块对象")

                # 5. 从 ES 获取预存向量
                chunk_ids_list = [c.chunk_id for c in content_results]
                es_chunks_data = await self.content_repo.get_chunks_by_ids(
                    chunk_ids=chunk_ids_list,
                    include_vectors=True
                )

                chunk_vector_map = {
                    es_chunk.get('chunk_id'): es_chunk.get('content_vector')
                    for es_chunk in es_chunks_data
                    if es_chunk.get('chunk_id') and es_chunk.get('content_vector')
                }

                self.logger.info(
                    f"从 ES 获取到 {len(chunk_vector_map)}/{len(chunk_ids_list)} 个原文块向量"
                )

                # 6. 计算相似度得分
                for result in content_results:
                    chunk_id = result.chunk_id
                    vector = chunk_vector_map.get(chunk_id)

                    if vector:
                        try:
                            query_np = np.array(query_vector, dtype=np.float32)
                            chunk_np = np.array(vector, dtype=np.float32)
                            cosine_score = float(
                                np.dot(query_np, chunk_np) /
                                (np.linalg.norm(query_np) * np.linalg.norm(chunk_np))
                            )
                            result.score = cosine_score
                        except Exception as e:
                            self.logger.warning(f"相似度计算失败: {e}")
                            result.score = 0.0
                    else:
                        result.score = 0.0

                # 7. 按得分排序
                content_results.sort(key=lambda x: x.score, reverse=True)

                # 8. 输出统计信息
                if content_results:
                    self.logger.info(
                        f"📊 段落召回完成: 共 {len(content_results)} 个段落, "
                        f"相似度范围: {min(r.score for r in content_results):.4f} ~ "
                        f"{max(r.score for r in content_results):.4f}"
                    )

                # 🆕 将对象转换为字典返回
                results = []
                for r in content_results:
                    result_dict = {
                        "search_type": r.search_type,
                        "source_config_id": r.source_config_id,
                        "source_id": r.source_id,
                        "chunk_id": r.chunk_id,
                        "rank": r.rank,
                        "heading": r.heading,
                        "content": r.content,
                        "score": r.score,
                        "weight": r.weight,
                        "event_ids": r.event_ids,
                        "event": r.event,
                        "clues": r.clues
                    }
                    # 添加统一字段
                    result_dict["id"] = r.chunk_id  # 统一ID字段
                    result_dict["text"] = f"{r.heading} {r.content}"  # 统一文本字段
                    results.append(result_dict)
                return results

        except Exception as e:
            self.logger.error(f"[段落级Step1] 执行失败: {e}", exc_info=True)
            return []

    async def _step5_pagerank_rerank(
        self,
        weighted_contents: List[Dict[str, Any]],
        config: Optional[SearchConfig] = None
    ) -> List[Dict[str, Any]]:
        """
        步骤5（段落级）: 使用 PageRank 算法重排序

        基于段落间的共同实体构建关系图，使用 PageRank 算法重新排序段落。

        图构建规则：
        - 节点：每个段落
        - 边：如果两个段落有共同的 key（实体），则它们之间有连接
        - 边权重：共同 key 的权重累加
        - 初始 PageRank 值：使用 Step4 计算的权重

        Args:
            weighted_contents: 从 step4 返回的段落列表（已包含 weight 字段）
            config: 搜索配置

        Returns:
            按 PageRank 得分降序排序的段落列表
        """
        try:
            n = len(weighted_contents)

            if n == 0:
                self.logger.warning("[Step5] 输入段落为空")
                return []

            if n == 1:
                self.logger.info("[Step5] 只有1个段落，跳过 PageRank")
                return weighted_contents

            self.logger.info("=" * 80)
            self.logger.info(f"[Step5] PageRank 重排序开始，共 {n} 个段落")
            self.logger.info("-" * 80)

            # 1. 构建段落索引映射
            chunk_id_to_idx = {
                content["chunk_id"]: idx
                for idx, content in enumerate(weighted_contents)
            }

            # 2. 构建段落关系图（基于共同实体）
            self.logger.info("[Step5] 正在构建段落关系图...")
            graph = self._build_section_graph(weighted_contents, chunk_id_to_idx)

            # 统计图信息
            total_edges = sum(len(edges) for edges in graph.values())
            self.logger.info(
                f"✓ 关系图构建完成: {n} 个节点, {total_edges} 条边"
            )

            # 3. 准备初始 PageRank 值（使用 Step4 的权重）
            initial_weights = np.array([
                content.get("weight", 0.0)
                for content in weighted_contents
            ])

            self.logger.info(
                f"初始权重统计: min={initial_weights.min():.4f}, "
                f"max={initial_weights.max():.4f}, "
                f"mean={initial_weights.mean():.4f}"
            )

            # 使用基类方法初始化 PageRank 值
            initial_pagerank = self._initialize_pagerank_values(initial_weights)

            # 4. 执行 PageRank 迭代
            self.logger.info("[Step5] 开始 PageRank 迭代计算...")
            final_pagerank = self._execute_pagerank_iteration(
                graph=graph,
                initial_pagerank=initial_pagerank,
                damping=0.85,
                max_iterations=100,
                tolerance=1e-6
            )

            self.logger.info(
                f"✓ PageRank 计算完成: min={final_pagerank.min():.6f}, "
                f"max={final_pagerank.max():.6f}, "
                f"mean={final_pagerank.mean():.6f}"
            )

            # 5. 将 PageRank 得分赋值给段落
            # 🆕 计算 PageRank 的缩放因子，使其与原始权重处于相同量级
            max_original_weight = max(c.get("weight", 0.0) for c in weighted_contents)
            max_pagerank = float(final_pagerank.max()) if final_pagerank.max() > 0 else 1.0
            pagerank_scale = max_original_weight / max_pagerank if max_pagerank > 0 else 1.0
            
            for idx, content in enumerate(weighted_contents):
                raw_pagerank = float(final_pagerank[idx])
                scaled_pagerank = raw_pagerank * pagerank_scale  # 缩放到与原始权重相同量级
                
                content["pagerank_score"] = raw_pagerank
                content["scaled_pagerank"] = scaled_pagerank
                content.setdefault("original_weight", content.get("weight", 0.0))
                
                # 混合：以 RRF 权重为主，PageRank 作为 20% 微调
                content["weight"] = 0.8 * content["original_weight"] + 0.2 * scaled_pagerank
                content["score"] = content["weight"]  # 同步更新 score 用于返回

            # 6. 🆕 按混合后的 weight 重新排序（而不是 pagerank_score）
            sorted_contents = sorted(
                weighted_contents,
                key=lambda x: x["weight"],
                reverse=True
            )

            # 7. 显示 Top-10 段落的 PageRank 变化
            self.logger.info("=" * 80)
            self.logger.info("[Step5] Top-10 段落 PageRank 得分:")
            self.logger.info("-" * 80)

            for rank, content in enumerate(sorted_contents[:10], 1):
                chunk_id = content.get("chunk_id", "")[:8]
                heading = content.get("heading", "")[:40]
                original_weight = content.get("original_weight", 0.0)
                pagerank_score = content.get("pagerank_score", 0.0)

                self.logger.info(
                    f"Rank {rank}: {chunk_id}... | "
                    f"原始权重={original_weight:.4f} → "
                    f"PageRank={pagerank_score:.6f} | "
                    f"标题: {heading}"
                )

            if len(sorted_contents) > 10:
                self.logger.info(f"... (还有 {len(sorted_contents) - 10} 个段落未显示)")

            self.logger.info("=" * 80)
            self.logger.info(f"✓ [Step5] PageRank 重排序完成，返回 {len(sorted_contents)} 个段落")

            return sorted_contents

        except Exception as e:
            self.logger.error(f"[Step5] PageRank 重排序失败: {e}", exc_info=True)
            # 失败时返回原始排序
            return weighted_contents

    def _build_section_graph(
        self,
        contents: List[Dict[str, Any]],
        chunk_id_to_idx: Dict[str, int]
    ) -> Dict[int, List[Tuple[int, float]]]:
        """
        构建段落关系图（调用基类的统一方法）

        规则：
        - 如果两个段落有共同的实体（key），则它们之间有连接
        - 边权重 = 共同实体的权重累加
        - 无向图（双向边）

        Args:
            contents: 段落列表
            chunk_id_to_idx: chunk_id 到索引的映射（未使用，保留用于兼容性）

        Returns:
            邻接表 {node_idx: [(target_idx, weight), ...]}
        """
        # 直接调用基类的统一无向图构建方法
        return self.build_undirected_graph_from_entities(
            items=contents,
            item_type="段落"
        )

    async def _step6_get_topn_sections(
        self,
        sorted_contents: List[Dict[str, Any]],
        top_k: int,
        config: Optional[SearchConfig] = None
    ) -> List[Dict[str, Any]]:
        """
        步骤6: 取Top-N段落并返回

        处理流程：
        1. 取Top-k：从排序后的结果中取前 k 个段落
        2. 直接返回这些段落

        Args:
            sorted_contents: 从step4排序后的段落列表（已按权重降序排序）
            top_k: 取前k个结果
            config: 搜索配置

        Returns:
            List[Dict[str, Any]]: 段落列表，每个段落包含：
                - chunk_id: 原文块ID
                - heading: 段落标题
                - content: 段落内容
                - weight: 权重得分
                - clues: 线索列表（召回该段落的实体）
        """
        try:
            self.logger.info(
                f"[段落级Step6] 开始: 从 {len(sorted_contents)} 个段落中取Top-{top_k}")

            # 1. 取Top-k段落
            topk_sections = sorted_contents[:top_k]
            self.logger.info(f"✓ [段落级Step6] 提取了Top-{len(topk_sections)}个段落")

            # 2. 显示Top-10段落信息
            self.logger.info("=" * 80)
            self.logger.info(
                f"【段落级Step6】Top-{min(len(topk_sections), 10)}段落详情:")
            self.logger.info("-" * 80)

            for idx, section in enumerate(topk_sections[:10], 1):
                heading = section["heading"][:50] if section["heading"] else ""
                weight = section["weight"]
                chunk_id = section["chunk_id"][:8]

                self.logger.info(
                    f"  段落{idx}: {chunk_id}... | W={weight:.4f} | '{heading}'"
                )

            if len(topk_sections) > 10:
                self.logger.info(
                    f"  ... (还有 {len(topk_sections) - 10} 个段落未显示)")

            self.logger.info("=" * 80)
            self.logger.info(f"✓ [段落级Step6] 完成: 返回 {len(topk_sections)} 个段落")

            return topk_sections

        except Exception as e:
            self.logger.error(f"[段落级Step6] 执行失败: {e}", exc_info=True)
            return []  # 失败时返回空列表
