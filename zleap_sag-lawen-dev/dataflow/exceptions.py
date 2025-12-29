"""
DataFlow 异常定义

所有自定义异常都继承自DataFlowError基类
"""


class DataFlowError(Exception):
    """DataFlow基础异常类"""

    def __init__(self, message: str, *args: object) -> None:
        self.message = message
        super().__init__(message, *args)


class ConfigError(DataFlowError):
    """配置错误异常"""

    pass


class StorageError(DataFlowError):
    """存储层异常"""

    pass


class DatabaseError(StorageError):
    """数据库异常"""

    pass


class CacheError(StorageError):
    """缓存异常"""

    pass


class LLMError(DataFlowError):
    """LLM调用异常"""

    pass


class LLMTimeoutError(LLMError):
    """LLM调用超时异常"""

    pass


class LLMRateLimitError(LLMError):
    """LLM速率限制异常"""

    pass


class AIError(DataFlowError):
    """AI相关异常（包括LLM和Embedding）"""

    pass


class ValidationError(DataFlowError):
    """数据验证异常"""

    pass


class LoadError(DataFlowError):
    """文档加载异常"""

    pass


class EntityError(DataFlowError):
    """实体处理异常"""

    pass


class ExtractError(DataFlowError):
    """事项提取异常"""

    pass


class SearchError(DataFlowError):
    """检索异常"""

    pass


class PromptError(DataFlowError):
    """提示词异常"""

    pass
