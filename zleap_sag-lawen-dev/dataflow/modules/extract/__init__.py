"""
Extract模块 - 事项提取

从文章片段中提取结构化事项和实体
"""

from dataflow.modules.extract.config import ExtractConfig
from dataflow.modules.extract.extractor import EventExtractor
from dataflow.modules.extract.processor import EventProcessor

__all__ = [
    "EventExtractor",
    "EventProcessor",
    "ExtractConfig",
]
