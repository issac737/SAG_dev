"""
PageRank 搜索器基类

提供事项级和段落级 PageRank 的共同逻辑，包括：
- 向量生成和相似度计算
- ES 搜索接口
- PageRank 迭代计算
- 响应构建

子类可以使用这些通用工具方法，并实现自己的搜索流程。
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import math
import time

from dataflow.core.storage.elasticsearch import get_es_client
from dataflow.core.storage.repositories.source_chunk_repository import SourceChunkRepository
from dataflow.core.storage.repositories.event_repository import EventVectorRepository
from dataflow.db import get_session_factory
from dataflow.exceptions import AIError
from dataflow.modules.load.processor import DocumentProcessor
from dataflow.modules.search.config import SearchConfig
from dataflow.utils import get_logger


@dataclass
class ContentSearchResult:
    """
    搜索结果的统一返回格式（SourceChunk架构）

    用于表示从SQL数据库或Embedding向量数据库搜索到的内容
    """
    # 必需字段
    search_type: str      # "sql", "embedding" 或带编号的格式如 "SQL-1", "embedding-2"
    source_config_id: str # 数据源配置ID (UUID)
    source_id: str        # 文章ID (Article.id 或 SourceChunk.source_id)
    chunk_id: str         # 原文块ID (SourceChunk.id)
    rank: int             # 原文块在文章中的排序
    heading: str          # 原文块标题
    content: str          # 原文块内容
    score: float = 0.0    # 相关性得分
    weight: float = 0.0   # 权重值（step4计算后赋值）
    event_ids: List[str] = None  # 关联的事件ID列表
    event: str = ""  # 聚合后的事项摘要（多个summary合并）
    clues: List[Dict[str, Any]] = None  # 召回该段落的线索列表（来自 key_final 或 query）

    def __post_init__(self):
        """初始化后验证"""
        # 初始化 event_ids 为空列表
        if self.event_ids is None:
            self.event_ids = []

        # 初始化 clues 为空列表
        if self.clues is None:
            self.clues = []

        # 允许 "sql", "embedding" 或带编号的格式如 "SQL-1", "embedding-2"
        valid_types = ["sql", "embedding"]
        is_valid = (
            self.search_type in valid_types or
            self.search_type.startswith("SQL-") or
            self.search_type.startswith("embedding-")
        )

        if not is_valid:
            raise ValueError(
                f"search_type 必须是 'sql', 'embedding' 或带编号格式(如 'SQL-1', 'embedding-1')，"
                f"当前值: {self.search_type}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "search_type": self.search_type,
            "source_config_id": self.source_config_id,
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "rank": self.rank,
            "heading": self.heading,
            "content": self.content,
            "score": self.score,
            "weight": self.weight,
            "event_ids": self.event_ids,
            "event": self.event,
            "clues": self.clues,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentSearchResult":
        """从字典创建实例"""
        return cls(
            search_type=data.get("search_type", "sql"),
            source_config_id=data["source_config_id"],
            source_id=data["source_id"],
            chunk_id=data["chunk_id"],
            rank=data.get("rank", 0),
            heading=data.get("heading", ""),
            content=data.get("content", ""),
            score=data.get("score", 0.0),
            weight=data.get("weight", 0.0),
            event_ids=data.get("event_ids", []),
            event=data.get("event", ""),
            clues=data.get("clues", []),
        )

    def __repr__(self) -> str:
        """字符串表示"""
        return (
            f"ContentSearchResult(type={self.search_type}, "
            f"chunk_id={self.chunk_id}, "
            f"heading='{self.heading[:30]}...', "
            f"score={self.score:.3f})"
        )


class BasePageRankSearcher:
    """PageRank 搜索器基类"""

    def __init__(self, llm_client=None):
        """
        初始化搜索器

        Args:
            llm_client: LLM客户端（可选）
        """
        self.session_factory = get_session_factory()
        self.logger = get_logger("search.rerank.pagerank")

        # 初始化 ES 客户端和仓库
        self.es_client = get_es_client()
        self.content_repo = SourceChunkRepository(self.es_client)
        self.event_repo = EventVectorRepository(self.es_client)

        # 初始化文档处理器
        self.processor = DocumentProcessor(llm_client=llm_client)

        self.logger.info(
            f"{self.__class__.__name__} 初始化完成",
            extra={"embedding_model": self.processor.embedding_model_name}
        )

    # ==================== 具体实现方法（子类可直接使用） ====================

    async def _generate_query_vector(
        self,
        query: str,
        config: Optional[SearchConfig] = None
    ) -> List[float]:
        """
        生成查询向量（支持缓存）

        Args:
            query: 查询文本
            config: 搜索配置（可选，用于缓存）

        Returns:
            查询向量
        """
        try:
            # 检查是否已有缓存的 query_embedding
            if config and config.has_query_embedding and config.query_embedding:
                query_embedding = config.query_embedding
                self.logger.debug(f"📦 使用缓存的query向量，长度: {len(query_embedding)}")
                return query_embedding

            # 生成查询向量
            query_embedding = await self.processor.generate_embedding(query)
            self.logger.debug(f"✨ 生成query向量成功，长度: {len(query_embedding)}")

            # 缓存到 config
            if config:
                config.query_embedding = query_embedding
                config.has_query_embedding = True
                self.logger.debug("📦 Query向量已缓存到config")

            return query_embedding

        except Exception as e:
            raise AIError(f"查询向量生成失败: {e}") from e

    async def _cosine_similarity(
        self,
        vec1: List[float],
        vec2: List[float]
    ) -> float:
        """
        计算两个向量的余弦相似度

        Args:
            vec1: 向量1
            vec2: 向量2

        Returns:
            余弦相似度 [0, 1]
        """
        if not vec1 or not vec2:
            return 0.0

        try:
            v1 = np.array(vec1, dtype=np.float32)
            v2 = np.array(vec2, dtype=np.float32)

            if len(v1) != len(v2):
                self.logger.warning(f"向量长度不一致: {len(v1)} vs {len(v2)}")
                return 0.0

            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)
            return max(0.0, min(1.0, float(similarity)))

        except Exception as e:
            self.logger.warning(f"余弦相似度计算失败: {e}")
            return 0.0

    async def _calculate_cosine_scores(
        self,
        query_vector: List[float],
        items: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        批量计算余弦相似度（numpy 向量化优化）

        Args:
            query_vector: 查询向量
            items: 项目列表（必须包含 'vector' 或 'content_vector' 字段）

        Returns:
            {item_id: similarity_score}
        """
        scores = {}
        
        # 收集有效的 item_id 和向量
        valid_ids = []
        valid_vectors = []
        
        for item in items:
            item_id = item.get("id") or item.get("event_id") or item.get("chunk_id")
            if not item_id:
                continue

            # 获取向量（只使用 content_vector）
            vector = item.get("content_vector")

            if not vector:
                self.logger.debug(f"项目 {item_id[:8]}... 缺少向量")
                continue
            
            valid_ids.append(item_id)
            valid_vectors.append(vector)
        
        if not valid_vectors:
            return scores
        
        try:
            # 批量计算余弦相似度
            query_vec = np.array(query_vector, dtype=np.float32)
            item_matrix = np.array(valid_vectors, dtype=np.float32)  # shape: (n, dim)
            
            # 计算 query 范数
            query_norm = np.linalg.norm(query_vec)
            if query_norm == 0:
                return scores
            
            # 批量计算点积和范数
            dot_products = item_matrix @ query_vec  # shape: (n,)
            item_norms = np.linalg.norm(item_matrix, axis=1)  # shape: (n,)
            
            # 避免除零
            valid_norms = item_norms > 0
            similarities = np.zeros(len(valid_ids), dtype=np.float32)
            similarities[valid_norms] = dot_products[valid_norms] / (item_norms[valid_norms] * query_norm)
            
            # Clip to [0, 1]
            similarities = np.clip(similarities, 0.0, 1.0)
            
            # 构建结果字典
            for i, item_id in enumerate(valid_ids):
                scores[item_id] = float(similarities[i])
                
        except Exception as e:
            self.logger.warning(f"批量余弦相似度计算失败，回退逐个计算: {e}")
            # 回退到逐个计算
            for item_id, vector in zip(valid_ids, valid_vectors):
                similarity = await self._cosine_similarity(query_vector, vector)
                scores[item_id] = similarity

        return scores

    async def _search_similar_items_from_es(
        self,
        query_vector: List[float],
        source_config_ids: List[str],
        k: int,
        index_name: str
    ) -> List[Dict[str, Any]]:
        """
        从 ES 搜索相似项目（KNN）

        Args:
            query_vector: 查询向量
            source_config_ids: 数据源ID列表
            k: 返回数量
            index_name: ES索引名称

        Returns:
            相似项目列表
        """
        all_results = []

        for source_config_id in source_config_ids:
            try:
                # 根据索引类型选择不同的仓库和方法
                if "chunk" in index_name.lower():
                    # 段落搜索：使用 search_similar_by_content
                    results = await self.content_repo.search_similar_by_content(
                        query_vector=query_vector,
                        source_config_id=source_config_id,
                        k=k
                    )
                else:
                    # 事项搜索：使用 search_by_vector
                    results = await self.event_repo.search_by_vector(
                        vector=query_vector,
                        source_config_id=source_config_id,
                        top_k=k
                    )

                all_results.extend(results)

            except Exception as e:
                self.logger.warning(
                    f"ES搜索失败 (source_config_id={source_config_id}): {e}"
                )
                continue

        return all_results

    def _initialize_pagerank_values(
        self,
        weights: np.ndarray
    ) -> np.ndarray:
        """
        初始化 PageRank 值

        将权重数组归一化作为初始 PageRank 值。如果所有权重为0，则使用均匀分布。

        Args:
            weights: 权重数组

        Returns:
            归一化的 PageRank 初始值数组
        """
        n = len(weights)

        if weights.sum() > 0:
            pagerank = weights / weights.sum()  # 归一化
            self.logger.debug(f"使用权重归一化作为初始PageRank值")
        else:
            pagerank = np.ones(n) / n  # 均匀分布
            self.logger.warning(f"所有权重为0，使用均匀分布作为初始PageRank值")

        return pagerank

    def _execute_pagerank_iteration(
        self,
        graph: Dict[int, List[Tuple[int, float]]],
        initial_pagerank: np.ndarray,
        damping: float = 0.85,
        max_iterations: int = 100,
        tolerance: float = 1e-6
    ) -> np.ndarray:
        """
        执行 PageRank 迭代计算

        Args:
            graph: 邻接表 {node_idx: [(target_idx, weight), ...]}
            initial_pagerank: 初始 PageRank 值
            damping: 阻尼系数
            max_iterations: 最大迭代次数
            tolerance: 收敛容差

        Returns:
            PageRank 值数组
        """
        n = len(initial_pagerank)
        pagerank = initial_pagerank.copy()

        # 预计算出边权重和
        out_weights = {}
        for j in range(n):
            edges = graph.get(j, [])
            out_weights[j] = sum(w for _, w in edges) if edges else 0.0

        # 迭代计算
        for iteration in range(max_iterations):
            new_pagerank = np.ones(n) * (1 - damping) / n

            for j in range(n):
                if pagerank[j] == 0 or out_weights[j] == 0:
                    continue

                contribution_per_weight = damping * pagerank[j] / out_weights[j]

                for target_idx, edge_weight in graph.get(j, []):
                    new_pagerank[target_idx] += contribution_per_weight * edge_weight

            # 检查收敛
            diff = np.abs(new_pagerank - pagerank).sum()
            if diff < tolerance:
                self.logger.info(f"✓ PageRank收敛于第{iteration + 1}次迭代 (diff={diff:.6f})")
                return new_pagerank

            pagerank = new_pagerank

        self.logger.warning(f"⚠️ 达到最大迭代次数{max_iterations}，未完全收敛")
        return pagerank

    def build_undirected_graph_from_entities(
        self,
        items: List[Dict[str, Any]],
        item_type: str = "item"
    ) -> Dict[int, List[Tuple[int, float]]]:
        """
        统一的无向图构建方法（段落级和事项级通用）

        基于共同实体构建无向图：
        - 如果两个 item 有共同的实体（从 clues 字段获取），则建立无向边
        - 边权重 = 共同实体的权重累加的平均值
        - 构建双向边（i ↔ j）

        Args:
            items: 项目列表（段落或事项），每个项目包含：
                - chunk_id 或 event_id: 唯一标识
                - clues: 实体列表，每个实体包含：
                    - id 或 key_id: 实体ID
                    - weight: 实体权重
            item_type: 项目类型，用于日志显示（"段落" 或 "事项"）

        Returns:
            邻接表 {node_idx: [(target_idx, weight), ...]}

        示例:
            items = [
                {
                    "chunk_id": "chunk_1",
                    "clues": [
                        {"id": "entity_1", "weight": 0.9},
                        {"id": "entity_2", "weight": 0.7}
                    ]
                },
                {
                    "chunk_id": "chunk_2",
                    "clues": [
                        {"id": "entity_2", "weight": 0.7},
                        {"id": "entity_3", "weight": 0.5}
                    ]
                }
            ]

            # 构建图:
            # chunk_1 和 chunk_2 有共同实体 entity_2
            # 边权重 = (0.7 + 0.7) / 2 = 0.7
            # 结果: {0: [(1, 0.7)], 1: [(0, 0.7)]}
        """
        n = len(items)

        if n == 0:
            self.logger.warning(f"[图构建] 输入{item_type}为空")
            return {}

        if n == 1:
            self.logger.info(f"[图构建] 只有1个{item_type}，返回空图")
            return {0: []}

        self.logger.info(f"[图构建] 开始构建无向图: {n} 个{item_type}")

        # 初始化邻接表
        graph = {i: [] for i in range(n)}

        # 为每个项目提取实体信息
        # 结构: [{entity_id: entity_weight, ...}, ...]
        item_entities = []
        for idx, item in enumerate(items):
            clues = item.get("clues", [])
            entity_dict = {}
            for clue in clues:
                entity_id = clue.get("id") or clue.get("key_id")
                entity_weight = clue.get("weight", 0.0)
                if entity_id:
                    entity_dict[entity_id] = entity_weight

            item_entities.append(entity_dict)

            # 调试日志：显示每个项目的实体数
            if idx < 5:  # 只显示前5个
                item_id = item.get("chunk_id") or item.get("event_id", f"item_{idx}")
                self.logger.debug(
                    f"  [{idx}] {item_id[:8]}... 包含 {len(entity_dict)} 个实体"
                )

        # 统计边数
        edge_count = 0
        edge_details = []  # 存储边的详细信息用于调试

        # 构建无向图（遍历上三角矩阵，避免重复）
        for i in range(n):
            for j in range(i + 1, n):
                # 找共同的实体
                common_entities = set(item_entities[i].keys()) & set(item_entities[j].keys())

                if common_entities:
                    # 计算边权重：共同实体权重的累加平均
                    edge_weight = sum(
                        item_entities[i][entity_id] + item_entities[j][entity_id]
                        for entity_id in common_entities
                    ) / 2.0  # 除以2避免重复计数

                    # 添加双向边（无向图）
                    graph[i].append((j, edge_weight))
                    graph[j].append((i, edge_weight))
                    edge_count += 2

                    # 记录边的详细信息（用于调试）
                    if edge_count <= 20:  # 只记录前10条边（双向=20条）
                        edge_details.append({
                            "from": i,
                            "to": j,
                            "weight": edge_weight,
                            "common_count": len(common_entities)
                        })

        # 显示边的详细信息（前5条）
        if edge_details:
            self.logger.debug(f"  前{min(5, len(edge_details))}条边详情:")
            for edge in edge_details[:5]:
                item_i_id = items[edge["from"]].get("chunk_id") or items[edge["from"]].get("event_id", f"item_{edge['from']}")
                item_j_id = items[edge["to"]].get("chunk_id") or items[edge["to"]].get("event_id", f"item_{edge['to']}")
                item_i_heading = items[edge["from"]].get("heading") or items[edge["from"]].get("title", "")
                item_j_heading = items[edge["to"]].get("heading") or items[edge["to"]].get("title", "")

                self.logger.debug(
                    f"    [{edge['from']}] '{item_i_heading[:20]}' <--> "
                    f"[{edge['to']}] '{item_j_heading[:20]}' | "
                    f"权重={edge['weight']:.3f}, 共同实体={edge['common_count']}"
                )

        # 统计图的特征
        degrees = [len(edges) for edges in graph.values()]
        avg_degree = sum(degrees) / n if n > 0 else 0
        max_degree = max(degrees) if degrees else 0
        isolated_nodes = sum(1 for d in degrees if d == 0)

        self.logger.info(
            f"✓ [图构建] 完成: 节点={n}, 边={edge_count//2} (双向={edge_count})"
        )
        self.logger.info(
            f"  图统计: 平均度={avg_degree:.1f}, 最大度={max_degree}, 孤立节点={isolated_nodes}"
        )

        return graph

    def _extract_entity_ids_and_weights(
        self,
        key_final: List[Dict[str, Any]]
    ) -> Tuple[List[str], Dict[str, float]]:
        """
        从 key_final 中提取实体ID列表和权重映射

        Args:
            key_final: 从Recall返回的key_final数据

        Returns:
            (entity_ids, entity_weight_map)
            - entity_ids: 实体ID列表（已过滤None）
            - entity_weight_map: {entity_id: weight}
        """
        entity_ids = [key.get("key_id") or key.get("id") for key in key_final]
        entity_weight_map = {
            key.get("key_id") or key.get("id"): key["weight"]
            for key in key_final
        }

        # 过滤掉可能为 None 的 ID
        entity_ids = [eid for eid in entity_ids if eid]

        return entity_ids, entity_weight_map

    async def _query_event_entities(
        self,
        session,
        entity_ids: List[str],
        source_config_ids: List[str]
    ) -> List:
        """
        查询 EventEntity 表，获取实体关联的事件

        Args:
            session: 数据库会话
            entity_ids: 实体ID列表
            source_config_ids: 数据源配置ID列表

        Returns:
            [(event_id, entity_id, weight), ...] 查询结果列表
        """
        from sqlalchemy import select, and_
        from dataflow.db import EventEntity, SourceEvent

        query = (
            select(EventEntity.event_id, EventEntity.entity_id, EventEntity.weight)
            .join(SourceEvent, EventEntity.event_id == SourceEvent.id)
            .where(
                and_(
                    SourceEvent.source_config_id.in_(source_config_ids),
                    EventEntity.entity_id.in_(entity_ids)
                )
            )
            .distinct()
        )

        result = await session.execute(query)
        return result.fetchall()

    def _build_event_entity_mappings(
        self,
        event_entities: List,
        entity_weight_map: Dict[str, float]
    ) -> Tuple[Dict[str, List[str]], Dict[Tuple[str, str], float]]:
        """
        构建事件-实体映射关系

        Args:
            event_entities: EventEntity 查询结果列表
            entity_weight_map: 实体权重映射 {entity_id: weight}

        Returns:
            (event_to_entities, event_entity_weights)
            - event_to_entities: {event_id: [entity_ids]}
            - event_entity_weights: {(event_id, entity_id): ee_weight}
        """
        event_to_entities = {}
        event_entity_weights = {}

        for event_entity in event_entities:
            event_id = event_entity.event_id
            entity_id = event_entity.entity_id
            ee_weight = event_entity.weight or 1.0

            # 映射关系
            if event_id not in event_to_entities:
                event_to_entities[event_id] = []
            event_to_entities[event_id].append(entity_id)

            # 权重（只记录EventEntity权重）
            event_entity_weights[(event_id, entity_id)] = ee_weight

        return event_to_entities, event_entity_weights

    def _filter_by_similarity_threshold(
        self,
        results: List[Any],
        config: Optional[SearchConfig],
        score_getter: callable,
        item_type: str = "项",
        display_formatter: Optional[callable] = None,
        show_top_n: int = 3
    ) -> List[Any]:
        """
        根据相似度阈值过滤结果

        Args:
            results: 结果列表
            config: 搜索配置
            score_getter: 从结果项获取分数的函数，如 lambda r: r["score"]
            item_type: 项目类型名称（用于日志），如 "事项"、"段落"
            display_formatter: 可选的格式化函数，用于显示过滤后的结果
                              接收一个结果项，返回 (id_str, score, title_str) 元组
            show_top_n: 显示前 N 个过滤后的结果（默认 3）

        Returns:
            过滤后的结果列表
        """
        original_count = len(results)

        # 如果没有配置或没有阈值，跳过过滤
        if not config or not config.rerank.score_threshold:
            self.logger.warning("未设置阈值或config为空，跳过相似度过滤")
            return results

        # 应用阈值过滤
        filtered_results = [
            r for r in results
            if score_getter(r) >= config.rerank.score_threshold
        ]

        # 如果过滤后数量减少，输出日志
        if len(filtered_results) < original_count:
            self.logger.info(
                f"相似度过滤: {original_count} -> {len(filtered_results)} 个{item_type} "
                f"(阈值={config.rerank.score_threshold:.2f})"
            )

            # 展示过滤后保留的结果
            if filtered_results and display_formatter:
                self.logger.info("=" * 80)
                self.logger.info(
                    f"过滤后保留的 {len(filtered_results)} 个{item_type} (Top {show_top_n}):")
                self.logger.info("-" * 80)

                for idx, result in enumerate(filtered_results[:show_top_n], 1):
                    id_str, score, title_str = display_formatter(result)
                    self.logger.info(
                        f"  {idx}. {item_type} {id_str} | "
                        f"Cosine={score:.4f} | "
                        f"标题: {title_str}"
                    )

                if len(filtered_results) > show_top_n:
                    self.logger.info(f"  ... 还有 {len(filtered_results) - show_top_n} 个{item_type}")

                self.logger.info("=" * 80)

        return filtered_results

    async def _build_response(
        self,
        config: SearchConfig,
        key_final: List[Dict],
        items: List[Any],
        item_to_clues: Dict[str, List[Dict]]
    ) -> Dict[str, Any]:
        """
        构建统一的响应格式

        Args:
            config: 搜索配置
            key_final: 最终实体列表
            items: 项目列表（事项或段落）
            item_to_clues: 项目ID到线索的映射

        Returns:
            响应字典
        """
        # 提取 query 和 recall entities
        query_entity_ids = set()
        recall_entity_ids = set()

        for key in key_final:
            key_id = key.get("key_id")
            steps = key.get("steps", [])

            if not steps:
                continue

            if steps[0] == 0 or "query" in str(steps):
                query_entity_ids.add(key_id)
            else:
                recall_entity_ids.add(key_id)

        # 过滤掉在 query_entities 中的 recall_entities
        recall_entity_ids = recall_entity_ids - query_entity_ids

        # 构建 entities 信息
        query_entities = [
            {
                "id": key["key_id"],
                "name": key.get("name", ""),
                "type": key.get("type", ""),
                "weight": key.get("weight", 0)
            }
            for key in key_final
            if key.get("key_id") in query_entity_ids
        ]

        recall_entities = [
            {
                "id": key["key_id"],
                "name": key.get("name", ""),
                "type": key.get("type", ""),
                "weight": key.get("weight", 0)
            }
            for key in key_final
            if key.get("key_id") in recall_entity_ids
        ]

        return {
            "items": items,  # 子类会重命名为 "events" 或 "sections"
            "clues": {
                "origin_query": config.original_query or config.query,
                "final_query": config.query,
                "query_entities": query_entities,
                "recall_entities": recall_entities,
            }
        }

    # ==================== 线索生成工具方法 ====================

    def _build_entity_node_data(
        self,
        entity_id: str,
        key_info: Dict[str, Any],
        recall_method: str = "entity"
    ) -> Dict[str, Any]:
        """
        构建实体节点数据

        Args:
            entity_id: 实体ID
            key_info: 实体信息字典
            recall_method: 召回方法（"entity" 或 "query"）

        Returns:
            实体节点字典
        """
        return {
            "key_id": entity_id,
            "id": entity_id,
            "name": key_info.get("name", ""),
            "type": key_info.get("type", ""),
            "description": key_info.get("description", ""),
            "hop": key_info.get("hop", 0),
            "recall_method": recall_method
        }

    def _build_event_node_data(
        self,
        event_obj: Any,
        stage: str = "rerank",
        recall_method: str = "entity"
    ) -> Dict[str, Any]:
        """
        构建事项节点数据

        Args:
            event_obj: 事项对象（SourceEvent）
            stage: 阶段（"rerank", "search"等）
            recall_method: 召回方法（"entity" 或 "query"）

        Returns:
            事项节点字典
        """
        from dataflow.modules.search.tracker import Tracker

        return {
            "type": "event",
            "event_id": event_obj.id,
            "stage": stage,
            "recall_method": recall_method,
            "source_config_id": getattr(event_obj, "source_config_id", ""),
            "article_id": getattr(event_obj, "article_id", ""),
            "title": getattr(event_obj, "title", ""),
            "summary": getattr(event_obj, "summary", ""),
            "category": getattr(event_obj, "category", "")
        }

    def _build_clue_metadata(
        self,
        method: str,
        weight_score: float,
        similarity_score: float,
        rank: int,
        step: str = "",
        source: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        构建线索的metadata

        Args:
            method: 方法名（"weight_entity", "weight_query", "final_result"）
            weight_score: 权重分数
            similarity_score: 相似度分数
            rank: 排名
            step: 步骤（用于final线索）
            source: 来源（"entity" 或 "query"）
            **kwargs: 其他元数据字段

        Returns:
            metadata字典
        """
        metadata = {
            "method": method,
            "weight_score": weight_score,
            "similarity_score": similarity_score,
            "rank": rank,
        }

        if step:
            metadata["step"] = step

        if source:
            metadata["source"] = source

        # 添加其他自定义字段
        metadata.update(kwargs)

        return metadata

    async def _keys_to_events(
        self,
        key_final: List[Dict[str, Any]],
        query: str,
        source_config_ids: List[str],
        query_vector: Optional[List[float]] = None,
        config: Optional[SearchConfig] = None
    ) -> List[Dict[str, Any]]:
        """
        通用方法：根据 keys 召回相关事项（Key → Entity → Event）

        这是一个通用的实体召回方法，可以被事项级和段落级搜索器复用。
        工作流程：
        1. 提取实体ID和权重
        2. 通过EventEntity表查找相关事件
        3. 从ES批量获取事项的content_vector
        4. 计算每个事项与query的余弦相似度
        5. 按相似度排序并返回

        Args:
            key_final: 从Recall返回的实体列表
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
                "source": str,  # 来源标记（"entity" 或 "query"）
                "clues": List[Dict]  # 召回该事项的实体列表
            }
        """
        try:
            self.logger.debug(
                f"[_keys_to_events] 开始召回: {len(key_final)} 个keys, query='{query}'")

            if not key_final:
                return []

            # 1. 提取实体ID和权重
            entity_ids, entity_weight_map = self._extract_entity_ids_and_weights(key_final)

            if not entity_ids:
                self.logger.warning("key_final 中没有有效的实体ID")
                return []

            self.logger.debug(f"提取到 {len(entity_ids)} 个实体ID")

            # 2. 构建 entity_to_key 映射
            entity_to_key = {}
            for key in key_final:
                key_id = key.get("key_id") or key.get("id")
                if key_id:
                    entity_to_key[key_id] = key

            async with self.session_factory() as session:
                # 3. 查询相关事件
                event_entities = await self._query_event_entities(
                    session=session,
                    entity_ids=entity_ids,
                    source_config_ids=source_config_ids
                )

                if not event_entities:
                    self.logger.warning("未找到相关事件")
                    return []

                # 4. 构建事件-实体映射
                event_to_entities, _ = self._build_event_entity_mappings(
                    event_entities=event_entities,
                    entity_weight_map=entity_weight_map
                )

                event_ids = list(event_to_entities.keys())
                self.logger.debug(f"找到 {len(event_ids)} 个相关事件")

                # 5. 获取事件详情（预加载关联关系）
                from sqlalchemy import select, and_
                from sqlalchemy.orm import selectinload
                from dataflow.db import SourceEvent

                event_detail_query = (
                    select(SourceEvent)
                    .options(
                        selectinload(SourceEvent.source),
                        selectinload(SourceEvent.article)
                    )
                    .where(
                        and_(
                            SourceEvent.source_config_id.in_(source_config_ids),
                            SourceEvent.id.in_(event_ids)
                        )
                    )
                )

                event_detail_result = await session.execute(event_detail_query)
                events = event_detail_result.scalars().all()

                if not events:
                    self.logger.warning("未找到事件详情")
                    return []

                self.logger.debug(f"获取到 {len(events)} 个事件的详细信息")

                # 6. 从ES批量获取事件向量
                es_events_data = await self.event_repo.get_events_by_ids(event_ids=event_ids)

                # 构建 event_id -> content_vector 映射
                event_vector_map = {}
                for es_event in es_events_data:
                    event_id = es_event.get('event_id')
                    content_vector = es_event.get('content_vector')
                    if event_id and content_vector:
                        event_vector_map[event_id] = content_vector

                self.logger.debug(
                    f"从ES获取到 {len(event_vector_map)}/{len(event_ids)} 个事件向量"
                )

                # 7. 生成查询向量（如果没有传入）
                if query_vector is None:
                    query_vector = await self._generate_query_vector(query, config)

                # 8. 计算余弦相似度
                event_results = []

                for event in events:
                    event_id = event.id
                    event_vector = event_vector_map.get(event_id)

                    if not event_vector:
                        self.logger.debug(f"事件 {event_id[:8]}... 无向量，跳过")
                        continue

                    # 计算余弦相似度
                    try:
                        query_np = np.array(query_vector, dtype=np.float32)
                        event_np = np.array(event_vector, dtype=np.float32)

                        cosine_score = float(
                            np.dot(query_np, event_np) /
                            (np.linalg.norm(query_np) * np.linalg.norm(event_np))
                        )
                    except Exception as e:
                        self.logger.warning(f"相似度计算失败: {e}")
                        cosine_score = 0.0

                    # 构建 clues 列表
                    source_entity_ids = event_to_entities.get(event_id, [])
                    clues = []

                    for entity_id in source_entity_ids:
                        key_info = entity_to_key.get(entity_id)
                        if key_info:
                            clues.append({
                                "id": entity_id,
                                "key_id": entity_id,
                                "name": key_info.get("name", ""),
                                "weight": key_info.get("weight", 0.0),
                                "steps": key_info.get("steps", [1]),
                                "type": key_info.get("type", ""),
                                "hop": key_info.get("hop", 0)
                            })

                    # 构建结果
                    event_result = {
                        "event_id": event_id,
                        "event": event,
                        "similarity_score": cosine_score,
                        "source": "entity",  # 来源标记（entity/query）
                        "clues": clues
                    }
                    event_results.append(event_result)

                # 9. 按相似度排序
                event_results.sort(key=lambda x: x["similarity_score"], reverse=True)

                self.logger.debug(
                    f"[_keys_to_events] 完成: 召回 {len(event_results)} 个事件"
                )

                return event_results

        except Exception as e:
            self.logger.error(f"[_keys_to_events] 执行失败: {e}", exc_info=True)
            return []

    def _extract_item_text(self, item: Dict[str, Any]) -> str:
        """
        提取项目文本内容
        """
        # 优先使用统一text字段
        if "text" in item:
            return item["text"]

        # 提取event对象
        if "event" in item:
            event = item["event"]
            if hasattr(event, 'title') and hasattr(event, 'content'):
                return f"{event.title or ''} {event.content or ''}".strip()

        # 合并heading和content
        heading = item.get("heading", "")
        content = item.get("content", "")
        return f"{heading} {content}".strip()

    async def _step4_calculate_weights(
        self,
        items: List[Dict[str, Any]],
        key_final: List[Dict[str, Any]],
        config: Optional[SearchConfig] = None,
        item_type: str = "项目",
        store_detailed_scores: bool = False,
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Step4: 统一权重计算和RRF排序（支持段落级和事项级）

        核心功能：
        1. 支持4路RRF融合：similarity / relation_chain / density / bm25
        2. 对于BM25召回的事项（source="bm25"），跳过前三项计算，直接使用bm25_rank
        3. RRF参数：w_sim=1.5, w_rel=0.5, w_den=0.2, w_bm25=1.0
        """
        if not items:
            return []

        try:
            # 获取目标维度（用于加权）
            target_types = set(config.target_entity_types) if config and config.target_entity_types else set()
            if target_types:
                self.logger.info(f"🎯 目标维度加权: {list(target_types)}")

            self.logger.info("=" * 80)
            self.logger.info(
                f"【{item_type}级Step4】开始计算{item_type}权重（4路RRF融合：similarity/relation/density/bm25）"
            )
            self.logger.info("-" * 80)

            # 存储各组件的分数
            similarity_scores = {}
            relation_scores = {}
            density_scores = {}
            bm25_scores = {}

            # 为所有事项计算各组件分数
            for item in items:
                # 支持统一字段 'id' 和向后兼容的 'chunk_id' / 'event_id'
                item_id = item.get("id") or item.get("chunk_id") or item.get("event_id")
                if not item_id:
                    self.logger.warning(f"跳过没有ID的项目: {item}")
                    continue

                # ==================== similarity分数（所有事项都有） ====================
                # 从item中获取预计算的similarity_score，如果没有则使用score字段
                similarity_score = item.get("similarity_score") or item.get("score", 0.0)
                similarity_scores[item_id] = similarity_score

                # ==================== relation和density分数（基于实体线索） ====================
                relation_chain_score = 0.0
                density_score = 0.0

                # 获取实体线索（BM25召回的事项可能没有）
                item_clues = item.get("clues", [])

                if item_clues:
                    # 提取文本内容用于统计
                    full_text = self._extract_item_text(item)

                    # 计算每个实体的贡献
                    for clue in item_clues:
                        key_name = clue.get("name", "")
                        key_weight = clue.get("weight", 0.0)
                        key_type = clue.get("type", "")
                        hop = clue.get("hop", 0)
                        key_steps = clue.get("steps", [1])
                        step = key_steps[0] if key_steps else 1

                        # 统计key在文本中出现的次数
                        count = full_text.count(key_name) if key_name else 0

                        # 多跳衰减因子
                        hop_factor = 1.0 / (1.0 + hop)

                        # 目标维度加权
                        target_boost = 1.5 if key_type in target_types else 1.0

                        if count > 0:
                            # 关系链得分
                            relation_contribution = hop_factor * target_boost * key_weight
                            relation_chain_score += relation_contribution

                            # 信息密度得分
                            density_contribution = key_weight * math.log(1 + count) / step
                            density_score += density_contribution

                relation_scores[item_id] = relation_chain_score
                density_scores[item_id] = density_score

                # ==================== BM25分数（只有bm25召回的事项有） ====================
                bm25_rank = item.get("bm25_rank")
                if bm25_rank is not None:
                    # 有bm25排名，计算倒数分数
                    bm25_scores[item_id] = 1.0 / bm25_rank
                # 否则不参与bm25维度计算

            # ==================== 统一RRF融合计算 ====================
            def build_rank_map(score_dict: Dict[str, float], reverse: bool = True) -> Dict[str, int]:
                if not score_dict:
                    return {}
                sorted_items = sorted(score_dict.items(), key=lambda x: x[1], reverse=reverse)
                return {id_val: idx + 1 for idx, (id_val, _) in enumerate(sorted_items)}

            # 为每个组件构建排名
            rank_sim = build_rank_map(similarity_scores)
            rank_rel = build_rank_map(relation_scores)
            rank_den = build_rank_map(density_scores)
            rank_bm25 = build_rank_map(bm25_scores)

            # RRF参数（4路融合） - 从 config.rerank 读取
            k_rrf = config.rerank.rrf_k if config and config.rerank else 100
            w_sim = config.rerank.rrf_weight_similarity if config and config.rerank else 1.5
            w_rel = config.rerank.rrf_weight_relation if config and config.rerank else 0.5
            w_den = config.rerank.rrf_weight_density if config and config.rerank else 0.2
            w_bm25 = config.rerank.rrf_weight_bm25 if config and config.rerank else 2.0

            self.logger.info(f"RRF参数: k={k_rrf}, weights=[w_sim={w_sim}, w_rel={w_rel}, w_den={w_den}, w_bm25={w_bm25}]")

            # 计算RRF并存储到items
            for item in items:
                item_id = item.get("id") or item.get("chunk_id") or item.get("event_id")
                if not item_id:
                    continue

                # # 判断是否为BM25事项
                # is_bm25 = item.get("source") == "bm25"

                # if is_bm25:
                #     # BM25 事项：只使用 BM25 排名计算 RRF
                #     bm25_rank = rank_bm25.get(item_id, len(items))
                #     rrf_score = w_bm25 / (k_rrf + bm25_rank)

                #     # 设置相关字段
                #     item["weight"] = rrf_score
                #     item["score"] = rrf_score
                #     item["original_weight"] = rrf_score

                #     # BM25 事项的特殊标记
                #     item["is_bm25"] = True
                #     item["bm25_rank"] = bm25_rank

                #     # 存储详细分数（可选）
                #     if store_detailed_scores:
                #         item["similarity_score"] = 0.0
                #         item["relation_chain_score"] = 0.0
                #         item["density_score"] = 0.0
                #         item["bm25_contribution"] = rrf_score

                # 4路RRF融合（动态处理缺失维度）
                sim_rank = rank_sim[item_id]
                rel_rank = rank_rel[item_id]
                den_rank = rank_den[item_id]

                # 判断该事项是否有bm25分数
                has_bm25 = item_id in bm25_scores
                bm25_rank = rank_bm25.get(item_id, len(items)) if has_bm25 else None

                # 计算各维度贡献
                contributions = {
                    "similarity": w_sim / (k_rrf + sim_rank),
                    "relation": w_rel / (k_rrf + rel_rank),
                    "density": w_den / (k_rrf + den_rank),
                }

                # 总权重分母（根据实际存在的维度动态调整）
                total_weight = w_sim + w_rel + w_den

                if has_bm25:
                    contributions["bm25"] = w_bm25 / (k_rrf + bm25_rank)
                    total_weight += w_bm25

                # 动态RRF分数（按实际存在的维度加权）
                rrf_score = sum(contributions.values())

                # 设置相关字段
                item["weight"] = rrf_score
                item["score"] = rrf_score
                item["original_weight"] = rrf_score
                item["has_bm25"] = has_bm25
                item["bm25_rank"] = bm25_rank
                item["recall_sources"] = item.get("recall_sources", [])

                # 存储详细分数（可选）
                if store_detailed_scores:
                    item["similarity_score"] = similarity_scores.get(item_id, 0.0)
                    item["relation_chain_score"] = relation_scores.get(item_id, 0.0)
                    item["density_score"] = density_scores.get(item_id, 0.0)
                    item["similarity_contribution"] = contributions.get("similarity", 0.0)
                    item["relation_contribution"] = contributions.get("relation", 0.0)
                    item["density_contribution"] = contributions.get("density", 0.0)
                    item["bm25_contribution"] = contributions.get("bm25", 0.0)

            # ==================== 排序和过滤 ====================
            # 按RRF得分排序
            sorted_items = sorted(
                items,
                key=lambda x: x["weight"],
                reverse=True
            )

            # 显示Top-N
            display_n = min(top_n, len(sorted_items))
            self.logger.info("")
            self.logger.info("=" * 80)
            self.logger.info(
                f"【{item_type}级Step4】4路RRF 排序结果（Top-{display_n}）："
            )
            self.logger.info("-" * 80)

            for rank, item in enumerate(sorted_items[:display_n], 1):
                item_id = item.get("id") or item.get("chunk_id") or item.get("event_id")
                weight = item["weight"]
                recall_sources = item.get("recall_sources", [])

                # 显示召回来源
                source_str = ",".join(recall_sources) if recall_sources else "unknown"

                # 获取各维度贡献值
                title_preview = ""
                if item.get("event"):
                    title_preview = item["event"].title[:40] if item["event"].title else "无标题"
                elif item.get("heading"):
                    title_preview = item["heading"][:40]

                # 显示4路融合的详细信息
                if store_detailed_scores:
                    sim = item.get("similarity_score", 0.0)
                    rel = item.get("relation_chain_score", 0.0)
                    den = item.get("density_score", 0.0)
                    bm25_rank = item.get("bm25_rank", "N/A")

                    sim_contrib = item.get("similarity_contribution", 0.0)
                    rel_contrib = item.get("relation_contribution", 0.0)
                    den_contrib = item.get("density_contribution", 0.0)
                    bm25_contrib = item.get("bm25_contribution", 0.0)

                    self.logger.info(
                        f"Rank {rank}: {item_id[:8]}... | "
                        f"RRF={weight:.4f} | "
                        f"Sim={sim:.4f}({sim_contrib:.3f}) | "
                        f"Rel={rel:.4f}({rel_contrib:.3f}) | "
                        f"Den={den:.4f}({den_contrib:.3f}) | "
                        f"BM25:R={bm25_rank}({bm25_contrib:.3f}) | "
                        f"来源=[{source_str}] | "
                        f"标题: {title_preview}"
                    )
                else:
                    # 简化显示
                    self.logger.info(
                        f"Rank {rank}: {item_id[:8]}... | "
                        f"RRF={weight:.4f} | "
                        f"来源=[{source_str}] | "
                        f"标题: {title_preview}"
                    )

            if len(sorted_items) > display_n:
                # 统计各类召回来源的事项数
                entity_only = sum(1 for item in sorted_items if "entity" in item.get("recall_sources", []) and "bm25" not in item.get("recall_sources", []))
                bm25_only = sum(1 for item in sorted_items if "bm25" in item.get("recall_sources", []) and "entity" not in item.get("recall_sources", []))
                both = sum(1 for item in sorted_items if "entity" in item.get("recall_sources", []) and "bm25" in item.get("recall_sources", []))

                self.logger.info(
                    f"... (还有 {len(sorted_items) - display_n} 个{item_type}未显示，"
                    f"总计: {entity_only}个仅entity + {bm25_only}个仅bm25 + {both}个两者都有)"
                )

            self.logger.info("=" * 80)

            # 统计信息
            total_top_n = len(sorted_items[:config.rerank.max_results if config else 50])
            bm25_in_top_n = sum(1 for item in sorted_items[:config.rerank.max_results if config else 50] if item.get("has_bm25", False))

            self.logger.info(f"BM25相关事项在Top-{total_top_n}中占比: {bm25_in_top_n}/{total_top_n} ({bm25_in_top_n/(total_top_n or 1)*100:.1f}%)")

            # 按来源统计分布
            entity_only_top = sum(1 for item in sorted_items[:total_top_n] if item.get("recall_sources") == ["entity"])
            bm25_only_top = sum(1 for item in sorted_items[:total_top_n] if item.get("recall_sources") == ["bm25"])
            both_sources_top = sum(1 for item in sorted_items[:total_top_n] if set(item.get("recall_sources", [])) == {"entity", "bm25"})

            self.logger.info(f"  - 仅entity召回: {entity_only_top}个")
            self.logger.info(f"  - 仅bm25召回: {bm25_only_top}个")
            self.logger.info(f"  - 两者都召回: {both_sources_top}个")

            # 阈值过滤（可选）
            if (config and config.rerank.score_threshold):
                original_count = len(sorted_items)
                # 这里可以添加基于阈值的过滤逻辑
                if len(sorted_items) < original_count:
                    self.logger.info(
                        f"🎯 权重过滤: {original_count} -> {len(sorted_items)} 个"
                        f"{item_type} (阈值={config.rerank.score_threshold:.2f})"
                    )

            self.logger.info(
                f"✓ 【{item_type}级Step4】完成: "
                f"计算并排序 {len(sorted_items)} 个{item_type}，显示 Top-{display_n}"
            )

            return sorted_items

        except Exception as e:
            self.logger.error(
                f"【{item_type}级Step4】执行失败: {e}",
                exc_info=True
            )
            return []


