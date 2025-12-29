"""
DataFlow 引擎模块

提供统一的任务引擎接口
"""

from dataflow.engine.config import (
    ModelConfig,
    OutputConfig,
    TaskConfig,
)
from dataflow.engine.core import DataFlowEngine
from dataflow.engine.enums import LogLevel, OutputMode, TaskStage, TaskStatus
from dataflow.engine.models import StageResult, TaskLog, TaskResult
from dataflow.modules.extract.config import ExtractBaseConfig
from dataflow.modules.load.config import (
    DocumentLoadConfig,
    LoadBaseConfig,
    ConversationLoadConfig,
)
from dataflow.modules.search.config import SearchBaseConfig

__all__ = [
    # 核心引擎
    "DataFlowEngine",
    # 配置类
    "ModelConfig",
    "LoadBaseConfig",
    "DocumentLoadConfig",
    "ConversationLoadConfig",
    "ExtractBaseConfig",
    "SearchBaseConfig",
    "OutputConfig",
    "TaskConfig",
    # 枚举
    "TaskStatus",
    "TaskStage",
    "LogLevel",
    "OutputMode",
    # 模型
    "TaskResult",
    "TaskLog",
    "StageResult",
]
