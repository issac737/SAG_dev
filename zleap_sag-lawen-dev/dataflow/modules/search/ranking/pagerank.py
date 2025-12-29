"""
搜索 Rerank 模块 - 事项级 PageRank 实现

实现6步骤的查找最重要事项的方法：
1. key找event：根据[key-final]从SQL中提取相关事项，计算事项向量与query的余弦相似度作为得分
2. query找event：通过向量相似度（KNN+余弦相似度）在向量数据库找到相似事项（已删除）
3. 合并event去重：优先保留step1结果（实体召回的事项）（已删除）
4. 计算事项权重向量（加权RRF融合）：
   - similarity_score: 事项与query的余弦相似度
   - relation_chain_score: 多跳关系链得分（hop衰减 × 目标维度加权 × 实体权重）
   - density_score: 信息密度得分（实体出现频次 × 权重 / step）
   - 使用RRF融合三个组件：rrf_score = w_sim/(k+sim_rank) + w_rel/(k+rel_rank) + w_den/(k+den_rank)
   - RRF参数：k=60, w_sim=1.5, w_rel=0.5, w_den=0.2
5. PageRank重排序（混合策略）：
   - 基于事项间共同实体构建关系图
   - 执行PageRank算法计算得分
   - 混合权重 = 0.8 × RRF权重 + 0.2 × PageRank得分
6. 选择Top-N事项：保留溯源信息，按混合权重得分排序

返回格式：
Dict[str, Any]: 包含以下字段的字典：
    - events (List[SourceEvent]): 事项对象列表（按混合权重顺序排列）
    - clues (Dict): 召回线索信息
        - origin_query (str): 原始查询（重写前）
        - final_query (str): LLM重写后的查询（重写后）
        - query_entities (List[Dict]): 查询召回的实体列表（key_id改为id）
        - recall_entities (List[Dict]): 召回的实体列表（key_id改为id，过滤掉query_entities中的值）

关键特性：
- 实时权重计算：基于key在事项内容中的实际出现频次计算权重
- 多维度融合：通过加权RRF融合相似度、关系链、密度三个组件
- 多跳衰减：hop越小贡献越大（hop=0→1.0, hop=1→0.5, hop=2→0.33）
- 目标维度加权：匹配target_entity_types的实体获得1.5倍加成
- PageRank混合：80% RRF + 20% PageRank，保持RRF为主导同时考虑事项间关联

"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import math
import time
import asyncio
from collections import defaultdict

from dataflow.core.storage.elasticsearch import get_es_client
from dataflow.core.storage.repositories.source_chunk_repository import SourceChunkRepository
from dataflow.core.storage.repositories.event_repository import EventVectorRepository
from dataflow.db import SourceEvent, Entity, EventEntity, Article, SourceConfig, get_session_factory
from dataflow.exceptions import AIError
from dataflow.modules.load.processor import DocumentProcessor
from dataflow.modules.search.config import SearchConfig, BM25Config
from dataflow.modules.search.ranking.base_pagerank import BasePageRankSearcher
from dataflow.modules.search.bm25 import BM25Searcher
from dataflow.modules.search.tracker import Tracker
from dataflow.utils import get_logger

logger = get_logger("search.rerank.pagerank")


class RerankPageRankSearcher(BasePageRankSearcher):
    """Rerank事项搜索器 - 实现6步骤的查找最重要事项的方法"""


    async def search(
        self,
        key_final: List[Dict[str, Any]],
        config: SearchConfig
    ) -> Dict[str, Any]:
        """
        Rerank 搜索主方法（事项级 + 加权RRF + PageRank混合）

        整合步骤1-6，统一进行query向量化，避免重复计算

        步骤流程：
          1. key找event（向量相似度过滤）：基于实体关联找到相关事项
          2. query找event（向量相似度过滤）：基于语义相似度找到相关事项（已删除）
          3. 合并event去重（优先保留step1结果）：实体召回的事项优先级更高（已删除）
          4. 计算事项权重向量（加权RRF融合）：
             - 计算三个组件：similarity（余弦相似度）、relation（多跳关系链）、density（信息密度）
             - 使用RRF融合：rrf_score = w_sim/(k+sim_rank) + w_rel/(k+rel_rank) + w_den/(k+den_rank)
             - RRF参数：k=60, w_sim=1.5, w_rel=0.5, w_den=0.2
          5. PageRank重排序（混合策略）：
             - 基于事项间共同实体构建关系图
             - 执行PageRank算法（damping=0.85）
             - 混合权重 = 0.8 × RRF权重 + 0.2 × PageRank得分
          6. 选择Top-N事项（保留溯源）：按混合权重排序并保留线索

        Args:
            key_final: 从Recall返回的关键实体列表
            config: Rerank搜索配置

        Returns:
            Dict[str, Any]: 包含以下字段的字典：
                - events (List[SourceEvent]): 事项对象列表（按混合权重顺序排列）
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
            self.logger.info(f"【事项级 PageRank】Rerank搜索开始")
            self.logger.info(f"Query: '{config.query}'")
            self.logger.info(f"Source IDs: {config.get_source_config_ids()}")
            self.logger.info("=" * 80)

            # 初始化 Tracker
            from dataflow.modules.search.tracker import Tracker
            tracker = Tracker(config)

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

            # 步骤1 key->event
            self.logger.info("\n" + "=" * 80)
            self.logger.info("【Step1】执行实体召回（已禁用Query召回）...")
            self.logger.info("=" * 80)
            parallel_start = time.perf_counter()

            # 执行 step1
            step1_events = await self._step1_keys_to_events(
                key_final=key_final,
                query=config.query,
                source_config_ids=config.get_source_config_ids(),
                query_vector=query_vector,
                config=config
            )

            # 🆕 BM25 搜索作为独立的召回通道
            bm25_events = []
            if config.bm25_enabled:
                self.logger.info("\n" + "=" * 80)
                self.logger.info("【BM25】执行BM25搜索召回...")
                self.logger.info("=" * 80)

                bm25_searcher = BM25Searcher()
                bm25_config = BM25Config(
                    top_k=config.bm25_top_k,
                    title_weight=config.bm25_title_weight,
                    content_weight=config.bm25_content_weight
                )

                bm25_results = await bm25_searcher.search(
                    query=config.query,
                    source_config_ids=config.get_source_config_ids(),
                    config=bm25_config
                )

                # 将 BM25 结果转换为统一格式
                for idx, event in enumerate(bm25_results):
                    bm25_events.append({
                        "event_id": event.id,
                        "event": event,
                        "similarity_score": 0.0,  # BM25 事项不需要计算相似度
                        "source": "bm25",  # 标记来源为 bm25
                        "clues": [],  # BM25 召回的事项没有实体线索
                        "bm25_rank": idx + 1,  # 记录 BM25 排名
                        "bm25_score": 0.0  # BM25 分数不作为独立字段存储
                    })

                self.logger.info(f"✓ BM25 召回完成: {len(bm25_events)} 个事项")

            parallel_time = time.perf_counter() - parallel_start
            step_times['Step1执行'] = parallel_time



            # 步骤4: 计算权重并排序（加权RRF）- 使用统一方法
            step4_start = time.perf_counter()

            # 合并 Step1 和 BM25 的召回结果（按 event_id 去重合并）
            self.logger.info("合并 Step1 和 BM25 召回结果（按 event_id 去重）...")
            event_dict = {}

            # 处理 step1_events（entity召回）
            for event in step1_events:
                event_id = event.get("event_id")
                if not event_id:
                    continue

                if event_id not in event_dict:
                    event_dict[event_id] = {
                        "event_id": event_id,
                        "event": event.get("event"),
                        "similarity_score": event.get("similarity_score", 0.0),
                        "source": "entity",  # 标记为entity召回
                        "clues": event.get("clues", []),
                        "recall_sources": ["entity"],  # 记录所有召回来源
                        "bm25_rank": None,  # 默认没有bm25排名
                        "score": event.get("score", 0.0),
                    }

            # 处理 bm25_events，合并或新增
            for event in bm25_events:
                event_id = event.get("event_id")
                if not event_id:
                    continue

                if event_id in event_dict:
                    # 已存在，合并bm25信息
                    event_dict[event_id]["recall_sources"].append("bm25")
                    event_dict[event_id]["bm25_rank"] = event.get("bm25_rank")
                    # 更新source标记为both，表示来自多个源
                    if "entity" in event_dict[event_id]["recall_sources"]:
                        event_dict[event_id]["source"] = "both"
                else:
                    # 新增bm25召回的事项
                    event_dict[event_id] = {
                        "event_id": event_id,
                        "event": event.get("event"),
                        "similarity_score": 0.0,  # BM25事项没有相似度分数
                        "source": "bm25",  # 标记为bm25召回
                        "clues": [],  # BM25召回的事项没有实体线索
                        "recall_sources": ["bm25"],
                        "bm25_rank": event.get("bm25_rank"),
                        "score": 0.0,  # 初始分数为0
                    }

            # 转换为列表
            all_events = list(event_dict.values())

            merged_count = len(all_events)
            entity_only = sum(1 for e in all_events if e["source"] == "entity")
            bm25_only = sum(1 for e in all_events if e["source"] == "bm25")
            both_sources = sum(1 for e in all_events if e["source"] == "both")

            self.logger.info(
                f"✓ 合并完成: 共 {merged_count} 个独特事项 "
                f"(仅entity: {entity_only}, 仅bm25: {bm25_only}, 两者都有: {both_sources})"
            )

            sorted_events = await self._step4_calculate_weights(
                items=all_events,
                key_final=key_final,
                config=config,
                item_type="事项",
                store_detailed_scores=True  # 事项级需要详细分数
            )
            step4_time = time.perf_counter() - step4_start
            step_times['Step4_权重计算'] = step4_time
            self.logger.info(
                f"✓ Step4 完成: 计算并排序 {len(sorted_events)} 个事项, 耗时: {step4_time:.3f}秒")

            # 🆕 步骤5: 根据配置决定是否执行 PageRank
            if config and config.rerank.skip_pagerank:
                # ✨ 跳过 PageRank 模式
                self.logger.info("=" * 80)
                self.logger.info("【配置】skip_pagerank=True，跳过 PageRank 重排序")
                self.logger.info("将直接使用 Step4 权重排序结果进行 Top-N 筛选")
                self.logger.info("=" * 80)

                step5_time = 0.0  # PageRank 未执行
                events_for_step6 = sorted_events  # 使用 Step4 的结果

                # 记录跳过统计
                self.logger.warning(
                    f"⚠️  已跳过 PageRank（配置 skip_pagerank=True）, "
                    f"排序质量可能下降，但速度更快"
                )
            else:
                # ✨ 使用 PageRank 模式
                self.logger.info("=" * 80)
                self.logger.info("【配置】skip_pagerank=False，执行 PageRank 重排序")
                self.logger.info("=" * 80)

                # 步骤5: PageRank 重排序
                step5_start = time.perf_counter()
                pagerank_results = await self._step5_pagerank_rerank_events(
                    weighted_events=sorted_events,
                    config=config
                )
                step5_time = time.perf_counter() - step5_start
                step_times['Step5_PageRank重排序'] = step5_time
                self.logger.info(
                    f"✓ Step5 完成: PageRank 重排序 {len(pagerank_results)} 个事项, 耗时: {step5_time:.3f}秒")

                events_for_step6 = pagerank_results  # 使用 PageRank 的结果

            # 步骤6: 统一进行 Top-N 筛选（两种模式都会执行）
            step6_start = time.perf_counter()
            final_events = await self._step6_get_topn_events(
                sorted_events=events_for_step6,  # 根据模式选择的结果
                key_final=key_final,
                config=config,
                tracker=tracker
            )
            step6_time = time.perf_counter() - step6_start
            step_times['Step6_Top-N筛选'] = step6_time
            self.logger.info(f"✓ Step6 完成: 最终返回 {len(final_events)} 个事项, 耗时: {step6_time:.3f}秒")

            # 计算总耗时
            overall_time = time.perf_counter() - overall_start

            # 输出耗时统计汇总
            self.logger.info("\n" + "=" * 80)
            self.logger.info("【事项级 PageRank】各步骤耗时汇总:")
            self.logger.info("-" * 80)
            self.logger.info(
                f"查询向量生成: {vector_time:.3f}秒 ({vector_time/overall_time*100:.1f}%)")
            for step_name, step_time in step_times.items():
                self.logger.info(
                    f"{step_name}: {step_time:.3f}秒 ({step_time/overall_time*100:.1f}%)")
            self.logger.info("-" * 80)
            self.logger.info(f"✓ 总耗时: {overall_time:.3f}秒")
            self.logger.info("=" * 80)

            # 构建 event_to_clues（从tracker获取）
            # 这里简化处理，直接从 sorted_events 构建
            event_to_clues = {}
            for event_data in sorted_events[:config.rerank.max_results]:
                event_id = event_data["event_id"]
                source_entities = event_data.get("source_entities", [])

                # 将实体ID列表转换为实体对象列表
                entity_objects = []
                for entity_id in source_entities:
                    # 从 key_final 中查找对应的实体信息
                    for key in key_final:
                        if key.get("key_id") == entity_id or key.get("id") == entity_id:
                            entity_objects.append({
                                "id": entity_id,
                                "name": key.get("name", ""),
                                "type": key.get("type", ""),
                                "weight": key.get("weight", 0.0)
                            })
                            break

                event_to_clues[event_id] = entity_objects

            # 构建并返回新的响应格式
            return await self._build_response(config, key_final, final_events, event_to_clues)

        except Exception as e:
            self.logger.error(f"Rerank搜索失败: {e}", exc_info=True)
            # 判断是否应该返回 final_query
            # 如果启用了query重写功能（enable_query_rewrite=True），则返回重写后的query
            # 否则返回 None
            final_query = config.query if config.enable_query_rewrite else None
            return {
                "events": [],
                "clues": {
                    "origin_query": config.original_query,
                    "final_query": final_query,
                    "query_entities": [],
                    "recall_entities": []
                }
            }  # 失败时返回空字典

    async def _step1_keys_to_events(
        self,
        key_final: List[Dict[str, Any]],
        query: str,
        source_config_ids: List[str],
        query_vector: Optional[List[float]] = None,
        config: Optional[SearchConfig] = None
    ) -> List[Dict[str, Any]]:
        """
        步骤1（事项级）: key找event（向量相似度过滤）

        调用父类的通用 _keys_to_events 方法，并添加事项级的额外处理：
        - 相似度阈值过滤
        - max_key_recall_results 截断
        - 日志输出

        Args:
            key_final: 从Recall返回的key_final数据
            query: 查询文本
            source_config_ids: 数据源配置ID列表
            query_vector: 可选的查询向量
            config: 搜索配置

        Returns:
            事项结果列表，每个事项包含：
            {
                "event_id": str,
                "event": SourceEvent对象,
                "similarity_score": float,
                "clues": List[Dict]  # 召回该事项的实体列表
            }
        """
        try:
            self.logger.info(
                f"[事项级Step1] 开始: 处理 {len(key_final)} 个key, query='{query}'")

            if not key_final:
                return []

            # 调用父类的通用方法进行实体召回
            event_results = await self._keys_to_events(
                key_final=key_final,
                query=query,
                source_config_ids=source_config_ids,
                query_vector=query_vector,
                config=config
            )

            if not event_results:
                self.logger.warning("实体召回未找到任何事项")
                return []

            # 输出摘要信息
            self.logger.info(
                f"📊 事项召回完成: 共 {len(event_results)} 个事项, "
                f"相似度范围: {min(r['similarity_score'] for r in event_results):.4f} ~ "
                f"{max(r['similarity_score'] for r in event_results):.4f}"
            )
            self.logger.info("=" * 80)

            # 1. 按相似度排序（父类方法已排序，这里再排一次确保顺序）
            event_results.sort(key=lambda x: x["similarity_score"], reverse=True)

            # 2. 使用 config.rerank.score_threshold 过滤低相似度结果
            original_count = len(event_results)
            if config and config.rerank.score_threshold:
                filtered_results = [
                    r for r in event_results
                    if r["similarity_score"] >= config.rerank.score_threshold
                ]

                if len(filtered_results) < original_count:
                    self.logger.info(
                        f"相似度过滤: {original_count} -> {len(filtered_results)} 个事项 "
                        f"(阈值={config.rerank.score_threshold:.2f})"
                    )

                    # 展示过滤后保留的事项信息
                    if filtered_results:
                        self.logger.info("=" * 80)
                        self.logger.info(
                            f"过滤后保留的 {len(filtered_results)} 个事项 (Top 3):")
                        self.logger.info("-" * 80)
                        for idx, result in enumerate(filtered_results[:3], 1):
                            title_preview = result["event"].title[:40] if result["event"].title else "无标题"
                            self.logger.info(
                                f"  {idx}. 事项 {result['event_id'][:8]}... | "
                                f"Cosine={result['similarity_score']:.4f} | "
                                f"标题: {title_preview}"
                            )
                        if len(filtered_results) > 3:
                            self.logger.info(f"  ... 还有 {len(filtered_results) - 3} 个事项")
                        self.logger.info("=" * 80)

                event_results = filtered_results
            else:
                self.logger.warning("未设置阈值或config为空，跳过相似度过滤")

            self.logger.info(
                f"[事项级Step1] 完成: 处理了 {len(event_results)} 个事项",
                extra={
                    "avg_cosine_score": np.mean([r["similarity_score"] for r in event_results]) if event_results else 0.0
                }
            )

            # 3. 根据 max_key_recall_results 截断（按相似度排序）
            max_key_results = config.rerank.max_key_recall_results if config else 30
            if len(event_results) > max_key_results:
                self.logger.warning(
                    f"⚠️  [事项级Step1] Key召回事项数({len(event_results)})超过max_key_recall_results({max_key_results})，"
                    f"将按相似度排序后截断"
                )

                # 截断
                truncated_results = event_results[:max_key_results]

                self.logger.info(
                    f"📊 [事项级Step1] 截断统计: "
                    f"保留{len(truncated_results)}个, "
                    f"丢弃{len(event_results) - len(truncated_results)}个"
                )

                event_results = truncated_results

            # 4. 显示Top 5结果（调试用）
            top_results = event_results[:5]
            for i, result in enumerate(top_results, 1):
                self.logger.debug(
                    f"Top {i}: {result['event'].title[:50]} - "
                    f"Cosine:{result['similarity_score']:.3f}"
                )

            # 5. 添加统一字段
            for result in event_results:
                event = result["event"]
                # 统一字段
                result["id"] = event.id                      # 统一ID字段
                result["text"] = f"{event.title or ''} {event.content or ''}"  # 统一文本字段
                result["score"] = result["similarity_score"]  # 统一得分字段
                result["heading"] = event.title or ""        # 统一标题字段
                result["content"] = event.content or ""      # 统一内容字段
                # 注意：不再保留 similarity_score 和 event_id 字段

            return event_results

        except Exception as e:
            self.logger.error(f"[事项级Step1] 执行失败: {e}", exc_info=True)
            return []


    async def _step6_get_topn_events(
        self,
        sorted_events: List[Dict[str, Any]],
        key_final: List[Dict[str, Any]],
        config: SearchConfig,
        tracker: Tracker
    ) -> List[SourceEvent]:
        """
        步骤6（事项级）: 选择Top-N事项（保留溯源）

        为排序后的事项生成溯源线索，并返回Top-K事项列表

        流程：
        1. 为所有事项生成 intermediate 线索（普通模式可见）
        2. 为 Top-K 的事项额外生成 final 线索（精简模式高亮显示）
        3. 返回 Top-K 事项列表

        Args:
            sorted_events: 权重排序后的事项列表（已包含weight字段）
            key_final: Recall阶段的key列表（用于构建实体节点）
            config: 搜索配置
            tracker: 线索追踪器

        Returns:
            Top-N事项对象列表（SourceEvent）
        """
        try:
            topn = config.rerank.max_results
            # 所有事项都生成 intermediate 线索
            intermediate_events = sorted_events  # 改为所有事项
            # Top-K 用于生成 final 线索和最终返回
            final_events = sorted_events[:topn]

            self.logger.info(f"[事项级Step6] 开始处理事项")
            self.logger.info(
                f"  所有 {len(intermediate_events)} 个事项生成 intermediate 线索")
            self.logger.info(f"  Top-{topn} 事项生成 final 线索")

            # 1. 构建 entity_id -> key 对象的映射
            entity_to_key = {}
            for key in key_final:
                key_id = key.get("key_id") or key.get("id")
                if key_id:
                    entity_to_key[key_id] = key

            # ========== 第一步：为所有事项生成 intermediate 线索 ==========
            self.logger.info("")
            self.logger.info("=" * 80)
            self.logger.info(
                f"[事项级Step6] 生成 Intermediate 线索 (所有 {len(intermediate_events)} 个事项)")
            self.logger.info("-" * 80)

            intermediate_entity_clue_count = 0
            intermediate_query_clue_count = 0

            for rank, event_data in enumerate(intermediate_events, 1):
                event_obj = event_data["event"]
                event_id = event_data["event_id"]
                source = event_data["source"]
                clues = event_data.get("clues", [])  # 🆕 使用 clues 字段

                if source in ["entity", "both"]:
                    # Step1召回的事项：为每个 clue 生成线索（entity → event）
                    if clues:  # 确保有实体线索
                        for clue in clues:  # 🆕 遍历 clues
                            entity_id = clue.get("id")  # 🆕 从 clue 获取 entity_id
                            if not entity_id:
                                continue

                            # 🆕 直接从 clue 获取实体信息（不再查表）
                            entity_node = Tracker.build_entity_node(clue)

                            event_node = tracker.get_or_create_event_node(
                                event_obj,
                                "rerank",
                                recall_method="entity"
                            )

                            metadata = self._build_clue_metadata(
                                method="weight_entity",
                                weight_score=event_data["weight"],
                                similarity_score=event_data["score"],  # 统一字段
                                rank=rank
                            )

                            tracker.add_clue(
                                stage="rerank",
                                from_node=entity_node,
                                to_node=event_node,
                                confidence=event_data["score"],  # 统一字段
                                relation="实体召回",
                                display_level="intermediate",
                                metadata=metadata
                            )
                            intermediate_entity_clue_count += 1

                if source == "bm25":  # 🆕 BM25 召回的事项：query → event
                    # 🆕 为 BM25 事项生成直接查询匹配线索
                    query_node = Tracker.build_query_node(config)

                    event_node = tracker.get_or_create_event_node(
                        event_obj,
                        "rerank",
                        recall_method="bm25"
                    )

                    metadata = self._build_clue_metadata(
                        method="bm25_direct",
                        weight_score=event_data["weight"],
                        similarity_score=event_data["score"],
                        rank=rank,
                        bm25_rank=event_data.get("bm25_rank", 0)
                    )

                    tracker.add_clue(
                        stage="rerank",
                        from_node=query_node,
                        to_node=event_node,
                        confidence=event_data["score"],
                        relation="BM25匹配",
                        display_level="intermediate",
                        metadata=metadata
                    )
                    intermediate_query_clue_count += 1  # 🆕 使用 query 线索计数器

                # 日志（只显示前10个）
                if rank <= 5:
                    title_preview = event_obj.title[:
                                                    40] if event_obj.title else "无标题"
                    self.logger.info(
                        f"  Rank {rank}: {event_id[:8]}... | "
                        f"来源={source} | "
                        f"实体数={len(clues)} | "
                        f"标题: {title_preview}"
                    )

            if len(intermediate_events) > 5:
                self.logger.info(
                    f"  ... (还有 {len(intermediate_events) - 5} 个事项)")

            self.logger.info("-" * 80)
            self.logger.info(f"Intermediate 线索统计:")
            self.logger.info(f"  实体→事项线索: {intermediate_entity_clue_count} 条")
            self.logger.info(f"  查询→事项线索: {intermediate_query_clue_count} 条")
            self.logger.info(
                f"  总线索数: {intermediate_entity_clue_count + intermediate_query_clue_count} 条")
            self.logger.info("=" * 80)

            # ========== 第二步：为 Top-K 生成 final 线索 ==========
            self.logger.info("")
            self.logger.info(
                "🎯 [事项级 Rerank Final] 生成最终线索 (display_level=final)")
            self.logger.info(f"   为 Top-{topn} 事项生成 final 线索")

            final_clue_count = 0

            for rank, event_data in enumerate(final_events, 1):
                event_obj = event_data["event"]
                event_id = event_data["event_id"]
                source = event_data["source"]
                clues = event_data.get("clues", [])  # 🆕 使用 clues 字段

                if source in ["entity", "both"]:
                    # 为 entity 召回的事项生成 final 线索（entity → event）
                    if clues:  # 确保有实体线索
                        for clue in clues:  # 🆕 遍历 clues
                            entity_id = clue.get("id")  # 🆕 从 clue 获取 entity_id
                            if not entity_id:
                                continue

                            # 🆕 直接从 clue 获取实体信息（不再查表）
                            entity_node = Tracker.build_entity_node(clue)

                            event_node = tracker.get_or_create_event_node(
                                event_obj,
                                "rerank",
                                recall_method="entity"
                            )

                            metadata = self._build_clue_metadata(
                                method="final_result",
                                weight_score=event_data["weight"],  # 直接从事项对象中获取权重
                                similarity_score=event_data["score"],  # 统一字段
                                rank=rank,
                                step="step6",
                                source="entity"
                            )

                            added_clue = tracker.add_clue(
                                stage="rerank",
                                from_node=entity_node,
                                to_node=event_node,
                                confidence=event_data["score"],  # 统一字段
                                relation="最终事项",
                                display_level="final",
                                metadata=metadata
                            )
                            if added_clue:
                                final_clue_count += 1
                            else:
                                self.logger.warning(
                                    f"⚠️ 无法为事项 {event_id[:30]}... 添加 final 线索 (entity → event)"
                                )

                            self.logger.debug(
                                f"  Final: {entity_id[:8]}... ('{clue.get('name', '')[:20]}') "
                                f"→ {event_id[:8]}... ('{event_obj.title[:30]}', weight={event_data['weight']:.4f})"
                            )

                if source == "bm25":
                    # 🆕 为 BM25 事项生成直接查询匹配线索
                    query_node = Tracker.build_query_node(config)

                    event_node = tracker.get_or_create_event_node(
                        event_obj,
                        "rerank",
                        recall_method="bm25"
                    )

                    metadata = self._build_clue_metadata(
                        method="final_result",
                        weight_score=event_data["weight"],
                        similarity_score=event_data["score"],
                        rank=rank,
                        step="step6",
                        source="bm25",
                        bm25_rank=event_data.get("bm25_rank", 0)
                    )

                    added_clue = tracker.add_clue(
                        stage="rerank",
                        from_node=query_node,
                        to_node=event_node,
                        confidence=event_data["score"],
                        relation="最终事项",
                        display_level="final",
                        metadata=metadata
                    )
                    if added_clue:
                        final_clue_count += 1
                    else:
                        self.logger.warning(
                            f"⚠️ 无法为 BM25 事项 {event_id[:30]}... 添加 final 线索"
                        )

                    self.logger.debug(
                        f"  Final (BM25): Query '{config.query[:30]}' "
                        f"→ {event_id[:8]}... ('{event_obj.title[:30]}', BM25排名={event_data.get('bm25_rank', 0)})"
                    )

            self.logger.info(
                f"✅ [事项级 Rerank Final] 生成了 {final_clue_count} 条最终线索"
            )
            self.logger.info(
                f"✅ [事项级 Rerank Final] 前端可根据这些 final 线索反推完整推理路径："
            )
            self.logger.info(f"   - Entity召回: query → entity → event")
            self.logger.info(f"   - BM25召回: query → event")
            self.logger.info("")

            # 🔧 验证：检查每个最终事项是否都有 final 线索
            events_with_final_clues = set()
            for clue in config.all_clues:
                if clue.get("display_level") == "final" and clue.get("stage") == "rerank":
                    to_node = clue.get("to", {})
                    if to_node.get("type") == "event":
                        event_id = to_node.get("event_id") or to_node.get("id")
                        events_with_final_clues.add(event_id)

            final_event_ids = {e["event_id"] for e in final_events}
            missing_final_clues = final_event_ids - events_with_final_clues

            if missing_final_clues:
                self.logger.warning(
                    f"⚠️ ��� {len(missing_final_clues)} 个事项缺少 final 线索: "
                    f"{list(missing_final_clues)[:3]}"
                )
            else:
                self.logger.info(
                    f"✅ 所有 {len(final_events)} 个最终事项都有 final 线索"
                )

            # 3. 提取事项对象列表（保持PageRank顺序，只返回Top-K）
            result_events = [e["event"] for e in final_events]

            self.logger.info(f"[事项级Step6] 完成: 返回 Top-{len(result_events)} 个事项")

            return result_events

        except Exception as e:
            self.logger.error(f"[事项级Step6] 执行失败: {e}", exc_info=True)
            return []

    async def _build_response(
        self,
        config: SearchConfig,
        key_final: List[Dict[str, Any]],
        events: List[SourceEvent],
        event_to_clues: Dict[str, List[Dict]]
    ) -> Dict[str, Any]:
        """
        构建新的响应格式

        Args:
            config: 搜索配置对象
            key_final: 召回的实体列表（key-final）
            events: 事项列表
            event_to_clues: 事项ID到实体列表的映射 {event_id: [entity1, entity2, ...]}

        Returns:
            Dict[str, Any]: 包含以下字段的字典：
                - events: 事项对象列表
                - clues: 召回线索信息
                    - origin_query: 原始查询
                    - final_query: LLM重写后的查询（如果没有重写则为None）
                    - query_entities: 查询召回的实体列表（key_id改为id）
                    - recall_entities: 召回的实体列表（key_id改为id，去除query_entities中的值）
                    - event_entities: 事项与实体的关联映射表 {event_id: [entity1, entity2, ...]}
        """
        # 1. 处理 query_entities：将 config.query_recalled_keys 中的 key_id 改为 id
        query_entities = []
        query_key_ids = set()  # 用于后续过滤

        for key in config.query_recalled_keys:
            key_copy = key.copy()
            if "key_id" in key_copy:
                key_id = key_copy.pop("key_id")
                key_copy["id"] = key_id
                query_key_ids.add(key_id)
            query_entities.append(key_copy)

        # 2. 处理 recall_entities：将 key_final 中的 key_id 改为 id，并过滤掉 query_entities 中的值
        recall_entities = []

        for key in key_final:
            # 获取 key_id 用于过滤判断
            key_id = key.get("key_id")

            # 如果这个 key_id 在 query_recalled_keys 中，则跳过
            if key_id in query_key_ids:
                continue

            # 复制并重命名 key_id 为 id
            key_copy = key.copy()
            if "key_id" in key_copy:
                key_copy["id"] = key_copy.pop("key_id")
            recall_entities.append(key_copy)

        # 3. 判断是否应该返回 final_query
        # 如果启用了query重写功能（enable_query_rewrite=True），则返回重写后的query
        # 否则返回 None
        final_query = config.query if config.enable_query_rewrite and config.recall.use_fast_mode == False else None

        # 4. 过滤 event_to_clues，只保留最终返回的事项
        final_event_ids = {event.id for event in events}
        filtered_event_entities = {
            event_id: clues
            for event_id, clues in event_to_clues.items()
            if event_id in final_event_ids
        }

        # 5. 构建响应
        response = {
            "events": events,  # 事项列表
            "clues": {
                "origin_query": config.original_query,  # 原始query（重写前）
                "final_query": final_query,  # 重写后的query（没有重写则为None）
                "query_entities": query_entities,
                "recall_entities": recall_entities,
                "event_entities": filtered_event_entities  # 只包含最终返回事项的溯源信息
            }
        }

        self.logger.info(
            f"响应构建完成: origin_query='{config.original_query}', "
            f"final_query='{final_query}', "
            f"query_entities={len(query_entities)}个, "
            f"recall_entities={len(recall_entities)}个, "
            f"events={len(events)}个, "
            f"event_entities映射={len(filtered_event_entities)}个 (过滤前={len(event_to_clues)}个)"
        )

        return response

    async def _step5_pagerank_rerank_events(
        self,
        weighted_events: List[Dict[str, Any]],
        config: Optional[SearchConfig] = None
    ) -> List[Dict[str, Any]]:
        """
        步骤5（事项级）: 使用 PageRank 算法重排序事项

        基于事项间的共同实体构建关系图，使用PageRank算法重新排序。
        与段落级PageRank的主要区别：
        - 事项可能包含更多实体（跨段落的聚合）
        - 图的密度可能更高
        - 但核心算法完全相同

        🆕 混合策略（与段落级一致）：
        - PageRank 得分缩放到与 RRF 权重相同量级
        - 最终权重 = 0.8 × RRF权重 + 0.2 × PageRank得分

        Args:
            weighted_events: 从 Step4 返回的事项列表（已包含 weight 字段）
            config: 搜索配置

        Returns:
            按混合权重降序排序的事项列表
        """
        try:
            n = len(weighted_events)

            if n == 0:
                self.logger.warning("[Step5] 输入事项为空，跳过 PageRank")
                return []

            if n == 1:
                self.logger.info("[Step5] 只有1个事项，跳过 PageRank")
                return weighted_events

            self.logger.info("=" * 80)
            self.logger.info(f"[Step5] 事项级 PageRank 重排序开始，共 {n} 个事项")
            self.logger.info("-" * 80)

            # 1. 构建事项索引映射
            event_id_to_idx = {
                event["event_id"]: idx
                for idx, event in enumerate(weighted_events)
            }

            # 2. 构建事项关系图（基于共同实体）
            self.logger.info("[Step5] 正在构建事项关系图（基于共同实体）...")
            graph = self._build_event_graph(weighted_events, event_id_to_idx)

            # 统计图信息
            total_edges = sum(len(edges) for edges in graph.values())
            avg_degree = (total_edges * 2 / n) if n > 0 else 0
            self.logger.info(
                f"✓ 关系图构建完成: {n} 个节点, {total_edges} 条边, "
                f"平均度数: {avg_degree:.2f}"
            )

            # 3. 准备初始 PageRank 值（使用 Step4 的权重）
            import numpy as np
            initial_weights = np.array([
                event.get("weight", 0.0)
                for event in weighted_events
            ])

            if initial_weights.sum() > 0:
                self.logger.info(
                    f"初始权重统计: min={initial_weights.min():.4f}, "
                    f"max={initial_weights.max():.4f}, "
                    f"mean={initial_weights.mean():.4f}, "
                    f"sum={initial_weights.sum():.6f}"
                )
            else:
                self.logger.warning("[Step5] 所有事项的初始权重都为0，使用均匀分布")

            # 使用基类方法初始化 PageRank 值
            initial_pagerank = self._initialize_pagerank_values(initial_weights)

            # 4. 执行 PageRank 迭代
            self.logger.info("[Step5] 开始 PageRank 迭代计算（阻尼系数=0.85）...")
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
                f"mean={final_pagerank.mean():.6f}, "
                f"sum={final_pagerank.sum():.6f}"
            )

            # 5. 🆕 计算 PageRank 的缩放因子，使其与原始权重处于相同量级
            max_original_weight = max(e.get("weight", 0.0) for e in weighted_events)
            max_pagerank = float(final_pagerank.max()) if final_pagerank.max() > 0 else 1.0
            pagerank_scale = max_original_weight / max_pagerank if max_pagerank > 0 else 1.0

            # 6. 将 PageRank 得分赋值给事项，并计算混合权重
            for idx, event in enumerate(weighted_events):
                raw_pagerank = float(final_pagerank[idx])
                scaled_pagerank = raw_pagerank * pagerank_scale  # 缩放到与原始权重相同量级

                event["pagerank_score"] = raw_pagerank
                event["scaled_pagerank"] = scaled_pagerank
                event.setdefault("original_weight", event.get("weight", 0.0))

                # 🆕 混合：以 RRF 权重为主，PageRank 作为 20% 微调
                # 使用硬编码权重 0.8 和 0.2 (与段落版本保持一致)
                event["weight"] = 0.8 * event["original_weight"] + 0.2 * scaled_pagerank
                event["score"] = event["weight"]  # 同步更新 score 用于返回

            # 7. 🆕 按混合后的 weight 重新排序（而不是 pagerank_score）
            sorted_events = sorted(
                weighted_events,
                key=lambda x: x["weight"],
                reverse=True
            )

            # 8. 显示 Top-10 事项的 PageRank 变化
            self.logger.info("=" * 80)
            self.logger.info("[Step5] Top-10 事项混合权重（80% RRF + 20% PageRank）:")
            self.logger.info("-" * 80)

            for rank, event in enumerate(sorted_events[:10], 1):
                event_id = event.get("event_id", "")[:12]
                title = event.get("event").title[:40] if event.get("event") else "无标题"
                original_weight = event.get("original_weight", 0.0)
                pagerank_score = event.get("pagerank_score", 0.0)
                mixed_weight = event.get("weight", 0.0)

                self.logger.info(
                    f"Rank {rank}: {event_id}... | "
                    f"RRF={original_weight:.4f} + PR={pagerank_score:.6f} → "
                    f"混合={mixed_weight:.4f} | "
                    f"标题: {title}"
                )

            if len(sorted_events) > 10:
                self.logger.info(f"... (还有 {len(sorted_events) - 10} 个事项未显示)")

            self.logger.info("=" * 80)
            self.logger.info(f"✓ [Step5] 事项级 PageRank 重排序完成，返回 {len(sorted_events)} 个事项")

            return sorted_events

        except Exception as e:
            self.logger.error(f"[Step5] 事项级 PageRank 重排序失败: {e}", exc_info=True)
            # 失败时返回原始排序（降级处理）
            self.logger.warning("[Step5] 降级处理：返回 Step4 的原始权重排序")
            return weighted_events

    def _build_event_graph(
        self,
        events: List[Dict[str, Any]],
        event_id_to_idx: Dict[str, int]
    ) -> Dict[int, List[Tuple[int, float]]]:
        """
        构建事项关系图（基于共同实体）

        规则：
        - 如果两个事项有共同的实体（从 source_entities 字段获取），则建立连接
        - 边权重 = 共同实体权重累加的平均值（防止重复计算）
        - 无向图（双向边）

        Args:
            events: 事项列表
            event_id_to_idx: event_id 到索引的映射

        Returns:
            邻接表 {node_idx: [(target_idx, weight), ...]}
        """
        # 直接调用基类的统一方法（复用段落级的图构建逻辑）
        # build_undirected_graph_from_entities() 会自动提取 'clues' 字段
        return self.build_undirected_graph_from_entities(
            items=events,
            item_type="事项"
        )
