"""
BM25 检索器

独立于三阶段搜索的 BM25 检索器，直接使用 Query 检索 Event，
完全利用 ES 原生 BM25 能力（ES text 字段默认使用 BM25 算法）。

使用示例：
    from dataflow.modules.search import BM25Searcher, BM25Config

    config = BM25Config(
        top_k=20,
        title_weight=3.0,
        content_weight=1.0
    )

    searcher = BM25Searcher()
    events = await searcher.search(
        query="人工智能技术发展",
        source_config_ids=["source_1", "source_2"],
        config=config
    )
"""

import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from dataflow.core.storage.elasticsearch import get_es_client
from dataflow.db import SourceEvent, get_session_factory
from dataflow.modules.search.config import BM25Config
from dataflow.utils import get_logger

logger = get_logger("search.bm25")


class BM25Searcher:
    """
    BM25 检索器

    独立于三阶段搜索，直接使用 Query 检索 Event。
    完全利用 ES 原生 BM25 能力，不在 Python 中计算 BM25 分数。
    """

    INDEX_NAME = "event_vectors"

    def __init__(self):
        """初始化 BM25 检索器"""
        self.es_client = get_es_client()
        self.session_factory = get_session_factory()

    async def search(
        self,
        query: str,
        source_config_ids: List[str],
        config: Optional[BM25Config] = None,
    ) -> List[SourceEvent]:
        """
        使用 ES 原生 BM25 搜索 Event

        Args:
            query: 查询文本
            source_config_ids: 信息源ID列表（支持多源搜索）
            config: BM25 配置（可选，使用默认配置）

        Returns:
            List[SourceEvent]: 按 BM25 分数排序的事项列表
        """
        if config is None:
            config = BM25Config()

        start_time = time.perf_counter()
        logger.info("=" * 60)
        logger.info(f"【BM25 检索】开始搜索")
        logger.info(f"Query: '{query}'")
        logger.info(f"Source IDs: {source_config_ids}")
        logger.info(f"Config: top_k={config.top_k}, title_weight={config.title_weight}, content_weight={config.content_weight}")
        logger.info("=" * 60)

        # Step 1: 使用 ES BM25 搜索获取 event_id 列表
        es_start = time.perf_counter()
        event_ids_with_scores = await self._search_es_bm25(
            query=query,
            source_config_ids=source_config_ids,
            config=config,
        )
        es_time = time.perf_counter() - es_start
        logger.info(f"✓ ES BM25 搜索完成，命中 {len(event_ids_with_scores)} 个事项，耗时: {es_time:.3f}秒")

        if not event_ids_with_scores:
            logger.info("【BM25 检索】未找到匹配的事项")
            return []

        # Step 2: 从 MySQL 获取完整的 SourceEvent 对象
        db_start = time.perf_counter()
        event_ids = [item["event_id"] for item in event_ids_with_scores]
        events = await self._load_events_from_db(
            event_ids=event_ids,
            source_config_ids=source_config_ids,
        )
        db_time = time.perf_counter() - db_start
        logger.info(f"✓ 数据库加载完成，获取 {len(events)} 个事项详情，耗时: {db_time:.3f}秒")

        # 如果数量不一致，记录警告并打印缺失的 event_ids
        if len(events) < len(event_ids):
            found_ids = {event.id for event in events}
            all_ids = set(event_ids)
            missing_ids = all_ids - found_ids

            logger.warning(
                f"⚠️  数据不一致: ES 命中 {len(event_ids)} 个事项，"
                f"但 MySQL 只返回 {len(events)} 个（source_config_ids={source_config_ids}）"
            )
            logger.warning(f"   - 缺失的 event_ids ({len(missing_ids)}个): {list(missing_ids)}")
            logger.warning(f"   - 可能原因：1) ES 和 MySQL 数据未同步 2) source_config_id 不匹配")
            logger.warning(f"   - 调试方法：检查这些 event_ids 在 ES 中的 source_config_id 值")

        # Step 3: 按 BM25 分数排序（保持 ES 返回的顺序）
        event_id_to_score = {item["event_id"]: item["score"] for item in event_ids_with_scores}
        events_sorted = sorted(
            events,
            key=lambda e: event_id_to_score.get(e.id, 0),
            reverse=True,
        )

        total_time = time.perf_counter() - start_time
        logger.info("=" * 60)
        logger.info(f"【BM25 检索】完成，返回 {len(events_sorted)} 个事项，总耗时: {total_time:.3f}秒")
        logger.info("=" * 60)

        # 打印 Top-5 结果
        for i, event in enumerate(events_sorted[:5]):
            score = event_id_to_score.get(event.id, 0)
            logger.info(f"  Top-{i+1}: score={score:.4f} | {event.title[:50]}...")

        return events_sorted

    async def _search_es_bm25(
        self,
        query: str,
        source_config_ids: List[str],
        config: BM25Config,
    ) -> List[Dict[str, Any]]:
        """
        使用 ES multi_match 查询进行 BM25 搜索

        ES 的 text 字段默认使用 BM25 算法，无需额外配置。

        Args:
            query: 查询文本
            source_config_ids: 信息源ID列表
            config: BM25 配置

        Returns:
            List[Dict]: 包含 event_id 和 score 的列表，按分数降序排列
        """
        # 构建 multi_match 查询
        # ES 默认对 text 字段使用 BM25 算法
        query_body = {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                f"title^{config.title_weight}",
                                f"content^{config.content_weight}",
                            ],
                            "type": "best_fields",  # 使用最佳匹配字段的分数
                        }
                    }
                ],
                "filter": [
                    {"terms": {"source_config_id": source_config_ids}},
                    {
                        "bool": {
                            "should": [
                                {"term": {"is_delete": False}},
                                {"bool": {"must_not": {"exists": {"field": "is_delete"}}}}
                            ]
                        }
                    },
                ],
            }
        }

        # 如果设置了最低分数阈值，添加 min_score 参数
        search_kwargs = {}
        if config.min_score is not None:
            search_kwargs["min_score"] = config.min_score

        try:
            response = await self.es_client.search(
                index=self.INDEX_NAME,
                query=query_body,
                size=config.top_k,
                return_full_response=True,
                _source=["event_id"],  # 只需要 event_id
                **search_kwargs,
            )

            hits = response.get("hits", [])
            results = []
            for hit in hits:
                source = hit.get("source", {})
                event_id = source.get("event_id")
                score = hit.get("score", 0)
                if event_id:
                    results.append({
                        "event_id": event_id,
                        "score": score,
                    })

            logger.debug(f"ES BM25 搜索返回 {len(results)} 个结果，max_score={response.get('max_score', 0)}")
            return results

        except Exception as e:
            logger.error(f"ES BM25 搜索失败: {e}", exc_info=True)
            return []

    async def _load_events_from_db(
        self,
        event_ids: List[str],
        source_config_ids: List[str],
    ) -> List[SourceEvent]:
        """
        从数据库加载完整的 SourceEvent 对象

        Args:
            event_ids: 事项ID列表
            source_config_ids: 信息源ID列表

        Returns:
            List[SourceEvent]: 事项对象列表
        """
        if not event_ids:
            return []

        try:
            async with self.session_factory() as session:
                query = (
                    select(SourceEvent)
                    .options(
                        selectinload(SourceEvent.source),  # 预加载 SourceConfig
                        selectinload(SourceEvent.article),  # 预加载 Article
                    )
                    .where(
                        and_(
                            SourceEvent.source_config_id.in_(source_config_ids),
                            SourceEvent.id.in_(event_ids),
                        )
                    )
                )
                result = await session.execute(query)
                events = result.scalars().all()
                return list(events)

        except Exception as e:
            logger.error(f"从数据库加载事项失败: {e}", exc_info=True)
            return []

    async def search_with_scores(
        self,
        query: str,
        source_config_ids: List[str],
        config: Optional[BM25Config] = None,
    ) -> List[Dict[str, Any]]:
        """
        搜索事项并保留 BM25 分数

        实现方式：先 ES 搜索获取 ID 和分数，再 DB 加载完整对象，最后组合

        Args:
            query: 查询文本
            source_config_ids: 信息源ID列表
            config: BM25 配置

        Returns:
            List[Dict]: 包含完整信息和分数的字典列表
                      按 BM25 分数降序排列
        """
        if config is None:
            config = BM25Config()

        start_time = time.perf_counter()
        logger.info("=" * 60)
        logger.info(f"【BM25 检索（含分数）】开始搜索")
        logger.info(f"Query: '{query}'")
        logger.info(f"Source IDs: {source_config_ids}")
        logger.info("=" * 60)

        # Step 1: ES 搜索获取 event_id 和 score
        es_start = time.perf_counter()
        event_ids_with_scores = await self._search_es_bm25(
            query=query,
            source_config_ids=source_config_ids,
            config=config,
        )
        es_time = time.perf_counter() - es_start
        logger.info(f"✓ ES BM25 搜索完成，命中 {len(event_ids_with_scores)} 个事项，耗时: {es_time:.3f}秒")

        if not event_ids_with_scores:
            logger.info("【BM25 检索】未找到匹配的事项")
            return []

        # 创建 ID -> 分数 映射
        id_to_score = {item["event_id"]: item["score"] for item in event_ids_with_scores}

        # Step 2: DB 加载完整对象
        db_start = time.perf_counter()
        event_ids = list(id_to_score.keys())
        events = await self._load_events_from_db(
            event_ids=event_ids,
            source_config_ids=source_config_ids,
        )
        db_time = time.perf_counter() - db_start
        logger.info(f"✓ 数据库加载完成，获取 {len(events)} 个事项详情，耗时: {db_time:.3f}秒")

        # Step 3: 组合结果（保持 ES 的顺序）
        event_dict = {e.id: e for e in events}
        results = []

        for item in event_ids_with_scores:
            event_id = item["event_id"]
            score = item["score"]

            if event_id in event_dict:
                event = event_dict[event_id]
                results.append({
                    "event_id": event_id,
                    "score": score,
                    "event": event,
                    "title": event.title,
                    "content": event.content,
                    "source_config_id": event.source_config_id,
                })

        total_time = time.perf_counter() - start_time
        logger.info("=" * 60)
        logger.info(f"【BM25 检索（含分数）】完成，返回 {len(results)} 个事项，总耗时: {total_time:.3f}秒")
        logger.info("=" * 60)

        # 打印 Top-5
        for i, result in enumerate(results[:5]):
            logger.info(f"  Top-{i+1}: score={result['score']:.4f} | {result['title'][:50] if result['title'] else '无标题'}...")

        return results

    async def search_chunks(
        self,
        query: str,
        source_config_ids: List[str],
        config: Optional[BM25Config] = None,
    ) -> List[Dict[str, Any]]:
        """
        使用 ES 原生 BM25 搜索 SourceChunk

        新增方法：支持在 source_chunks 索引上进行 BM25 搜索，返回段落级别的结果。
        可用于文档检索场景，返回具体的段落/文本块。

        Args:
            query: 查询文本
            source_config_ids: 信息源ID列表
            config: BM25 配置（可选，使用默认配置）

        Returns:
            List[Dict]: 包含 chunk_id, score, heading, content 等字段的段落列表
                      按 BM25 分数降序排列
        """
        if config is None:
            config = BM25Config()

        start_time = time.perf_counter()
        logger.info("=" * 60)
        logger.info(f"【BM25 Chunk 检索】开始搜索")
        logger.info(f"Query: '{query}'")
        logger.info(f"Source IDs: {source_config_ids}")
        logger.info(f"Config: top_k={config.top_k}, title_weight={config.title_weight}, content_weight={config.content_weight}")
        logger.info("=" * 60)

        # Step 1: 使用 ES BM25 搜索获取 chunk_id 列表
        es_start = time.perf_counter()
        chunk_ids_with_scores = await self._search_es_bm25_chunks(
            query=query,
            source_config_ids=source_config_ids,
            config=config,
        )
        es_time = time.perf_counter() - es_start
        logger.info(f"✓ ES BM25 搜索完成，命中 {len(chunk_ids_with_scores)} 个段落，耗时: {es_time:.3f}秒")

        if not chunk_ids_with_scores:
            logger.info("【BM25 Chunk 检索】未找到匹配的段落")
            return []

        # Step 2: 从 MySQL 获取完整的 SourceChunk 对象
        db_start = time.perf_counter()
        chunk_ids = [item["chunk_id"] for item in chunk_ids_with_scores]
        chunks = await self._load_chunks_from_db(
            chunk_ids=chunk_ids,
            source_config_ids=source_config_ids,
        )
        db_time = time.perf_counter() - db_start
        logger.info(f"✓ 数据库加载完成，获取 {len(chunks)} 个段落详情，耗时: {db_time:.3f}秒")

        # 如果数量不一致，记录警告并打印缺失的 chunk_ids
        if len(chunks) < len(chunk_ids):
            found_ids = {chunk.id for chunk in chunks}
            all_ids = set(chunk_ids)
            missing_ids = all_ids - found_ids

            logger.warning(
                f"⚠️  数据不一致: ES 命中 {len(chunk_ids)} 个段落，"
                f"但 MySQL 只返回 {len(chunks)} 个（source_config_ids={source_config_ids}）"
            )
            logger.warning(f"   - 缺失的 chunk_ids ({len(missing_ids)}个): {list(missing_ids)}")
            logger.warning(f"   - 可能原因：1) ES 和 MySQL 数据未同步 2) source_config_id 不匹配")
            logger.warning(f"   - 调试方法：检查这些 chunk_ids 在 ES 中的 source_config_id 值")

        # Step 3: 按 BM25 分数排序（保持 ES 返回的顺序）
        chunk_id_to_score = {item["chunk_id"]: item["score"] for item in chunk_ids_with_scores}
        chunks_with_score = [
            {
                "chunk_id": chunk.id,
                "score": chunk_id_to_score.get(chunk.id, 0),
                "heading": chunk.heading,
                "content": chunk.content,
                "source_id": chunk.source_id,
                "source_config_id": chunk.source_config_id,
                "rank": chunk.rank,
            }
            for chunk in chunks
        ]

        chunks_sorted = sorted(
            chunks_with_score,
            key=lambda c: c["score"],
            reverse=True,
        )

        total_time = time.perf_counter() - start_time
        logger.info("=" * 60)
        logger.info(f"【BM25 Chunk 检索】完成，返回 {len(chunks_sorted)} 个段落，总耗时: {total_time:.3f}秒")
        logger.info("=" * 60)

        # 打印 Top-5 结果
        for i, chunk in enumerate(chunks_sorted[:5]):
            logger.info(f"  Top-{i+1}: score={chunk['score']:.4f} | {chunk['heading'][:50] if chunk['heading'] else '无标题'}...")

        return chunks_sorted

    async def _search_es_bm25_chunks(
        self,
        query: str,
        source_config_ids: List[str],
        config: BM25Config,
    ) -> List[Dict[str, Any]]:
        """
        使用 ES multi_match 查询在 source_chunks 索引上进行 BM25 搜索

        Args:
            query: 查询文本
            source_config_ids: 信息源ID列表
            config: BM25 配置

        Returns:
            List[Dict]: 包含 chunk_id 和 score 的列表，按分数降序排列
        """
        INDEX_NAME = "source_chunks"

        # 构建 multi_match 查询
        query_body = {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                f"heading^{config.title_weight}",
                                f"content^{config.content_weight}",
                            ],
                            "type": "best_fields",
                        }
                    }
                ],
                "filter": [
                    {"terms": {"source_config_id": source_config_ids}},
                    {
                        "bool": {
                            "should": [
                                {"term": {"is_delete": False}},
                                {"bool": {"must_not": {"exists": {"field": "is_delete"}}}}
                            ]
                        }
                    },
                ],
            }
        }

        # 如果设置了最低分数阈值，添加 min_score 参数
        search_kwargs = {}
        if config.min_score is not None:
            search_kwargs["min_score"] = config.min_score

        try:
            response = await self.es_client.search(
                index=INDEX_NAME,
                query=query_body,
                size=config.top_k,
                return_full_response=True,
                _source=["chunk_id"],  # 只需要 chunk_id
                **search_kwargs,
            )

            hits = response.get("hits", [])
            results = []
            for hit in hits:
                source = hit.get("source", {})
                chunk_id = source.get("chunk_id")
                score = hit.get("score", 0)
                if chunk_id:
                    results.append({
                        "chunk_id": chunk_id,
                        "score": score,
                    })

            logger.debug(f"ES BM25 段落搜索返回 {len(results)} 个结果，max_score={response.get('max_score', 0)}")
            return results

        except Exception as e:
            logger.error(f"ES BM25 段落搜索失败: {e}", exc_info=True)
            return []

    async def _load_chunks_from_db(
        self,
        chunk_ids: List[str],
        source_config_ids: List[str],
    ) -> List[Any]:
        """
        从数据库加载 SourceChunk 对象

        Args:
            chunk_ids: 段落ID列表
            source_config_ids: 信息源ID列表

        Returns:
            List[SourceChunk]: 段落对象列表
        """
        if not chunk_ids:
            return []

        try:
            from dataflow.db import SourceChunk
            from sqlalchemy import select, and_

            async with self.session_factory() as session:
                query = (
                    select(SourceChunk)
                    .where(
                        and_(
                            SourceChunk.source_config_id.in_(source_config_ids),
                            SourceChunk.id.in_(chunk_ids),
                        )
                    )
                )
                result = await session.execute(query)
                chunks = result.scalars().all()
                return list(chunks)

        except Exception as e:
            logger.error(f"从数据库加载段落失败: {e}", exc_info=True)
            return []


__all__ = ["BM25Searcher"]
