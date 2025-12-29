"""
HotpotQA 评估工具模块

提供数据加载、事项转换、工具函数等功能
"""

from .hotpotqa_loader import HotpotQALoader
from .event_to_sections import EventToSectionConverter
from .utils import (
    format_chunk_id,
    split_merged_id,
    ChunkDeduplicator,
    print_stats,
)

__all__ = [
    'HotpotQALoader',
    'EventToSectionConverter',
    'format_chunk_id',
    'split_merged_id',
    'ChunkDeduplicator',
    'print_stats',
]
