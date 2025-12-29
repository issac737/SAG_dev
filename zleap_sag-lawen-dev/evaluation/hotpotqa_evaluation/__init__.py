"""
HotpotQA RAG 评估框架

包含：
- 语料库构建
- Oracle 提取
- 工具函数
- 数据加载和处理
"""

__version__ = "1.0.0"
__author__ = "RAG Evaluation Team"

# 导入配置
from . import config

# 导入核心模块类
from .modules import (
    HotpotQALoader,
    EventToSectionConverter,
    format_chunk_id,
    split_merged_id,
    ChunkDeduplicator,
    print_stats,
)

__all__ = [
    'config',
    'HotpotQALoader',
    'EventToSectionConverter',
    'format_chunk_id',
    'split_merged_id',
    'ChunkDeduplicator',
    'print_stats',
]
