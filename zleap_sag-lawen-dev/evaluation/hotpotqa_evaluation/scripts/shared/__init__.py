"""
共享模块 - 提供数据模型、I/O 工具、验证功能和 RAGAs 适配器
"""
from .data_models import (
    OracleChunk,
    RetrievedSection,
    RetrievalMetadata,
    RetrievalResult,
    GenerationMetadata,
    GeneratedAnswer,
    QuestionScore,
    EvaluationReport,
)
from .io_utils import (
    write_jsonl,
    read_jsonl,
    write_json,
    read_json,
)
from .validation import (
    validate_retrieval_results,
    validate_generated_answers,
)
from .ragas_adapters import (
    create_ragas_llm,
    create_ragas_embeddings,
    print_model_config,
)

__all__ = [
    # 数据模型
    'OracleChunk',
    'RetrievedSection',
    'RetrievalMetadata',
    'RetrievalResult',
    'GenerationMetadata',
    'GeneratedAnswer',
    'QuestionScore',
    'EvaluationReport',
    # I/O 工具
    'write_jsonl',
    'read_jsonl',
    'write_json',
    'read_json',
    # 验证
    'validate_retrieval_results',
    'validate_generated_answers',
    # RAGAs 适配器
    'create_ragas_llm',
    'create_ragas_embeddings',
    'print_model_config',
]
