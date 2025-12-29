"""DataFlow - 数据流智能引擎

AI驱动的数据处理与聚合检索引擎
"""

__version__ = "0.1.0"
__author__ = "Zleap Team"
__email__ = "contact@zleap.ai"

from dataflow.engine import (
    DataFlowEngine,
    DocumentLoadConfig,
    ExtractBaseConfig,
    LoadBaseConfig,
    ModelConfig,
    LogLevel,
    OutputConfig,
    OutputMode,
    SearchBaseConfig,
    ConversationLoadConfig,
    StageResult,
    TaskConfig,
    TaskLog,
    TaskResult,
    TaskStage,
    TaskStatus,
)
from dataflow.exceptions import DataFlowError, LLMError, StorageError, ValidationError

__all__ = [
    # Version
    "__version__",
    # Engine
    "DataFlowEngine",
    "TaskConfig",
    "TaskResult",
    "TaskLog",
    "TaskStatus",
    "TaskStage",
    "StageResult",
    # Configs
    "ModelConfig",
    "LoadBaseConfig",
    "DocumentLoadConfig",
    "ConversationLoadConfig",
    "ExtractBaseConfig",
    "SearchBaseConfig",
    "OutputConfig",
    "OutputMode",
    "LogLevel",
    # Exceptions
    "DataFlowError",
    "LLMError",
    "StorageError",
    "ValidationError",
]
