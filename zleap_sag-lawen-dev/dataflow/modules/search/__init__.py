"""
搜索模块

提供SAG搜索引擎：recall → expand → rerank

架构：
- SAGSearcher/EventSearcher: 统一搜索入口（推荐使用）
- BM25Searcher: 独立的 BM25 检索器（直接用 Query 检索 Event）
- recall/expand/rerank: 三阶段模块（高级使用）
- ranking: 事项排序策略
"""

from dataflow.modules.search.config import (
    SearchConfig,
    SearchBaseConfig,
    RecallConfig,
    ExpandConfig,
    RerankConfig,
    BM25Config,
    RerankStrategy,
)
from dataflow.modules.search.searcher import (
    SAGSearcher,
    EventSearcher,
)
from dataflow.modules.search.bm25 import BM25Searcher
from dataflow.modules.search.recall import (
    RecallSearcher,
    RecallResult,
)
from dataflow.modules.search.expand import (
    ExpandSearcher,
    ExpandResult,
)
from dataflow.modules.search.tracker import Tracker

__all__ = [
    # 配置
    "SearchConfig",
    "SearchBaseConfig",
    "RecallConfig",
    "ExpandConfig",
    "RerankConfig",
    "BM25Config",
    "RerankStrategy",
    # 搜索器（推荐）
    "SAGSearcher",
    "EventSearcher",
    "BM25Searcher",
    # 三阶段模块（高级）
    "RecallSearcher",
    "RecallResult",
    "ExpandSearcher",
    "ExpandResult",
    # 工具
    "Tracker",
]
