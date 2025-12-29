"""
Evaluation package

提供完整的评估框架，包括数据集加载、检索评估和QA评估
"""

from .benchmark import Evaluate, EvaluationConfig, quick_evaluate
from .utils import DatasetLoader, load_dataset, get_gold_answers, get_gold_docs
from .metrics import (
    BaseMetric,
    QAExactMatch,
    QAF1Score,
    RetrievalRecall,
)

__all__ = [
    # 评估类
    'Evaluate',
    'EvaluationConfig',
    'quick_evaluate',
    # 数据加载
    'DatasetLoader',
    'load_dataset',
    'get_gold_answers',
    'get_gold_docs',
    # 评估指标
    'BaseMetric',
    'QAExactMatch',
    'QAF1Score',
    'RetrievalRecall',
]
