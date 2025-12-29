"""
AI模块

提供LLM调用、Embedding生成等AI功能
"""

from dataflow.core.ai.base import BaseLLMClient, LLMRetryClient
from dataflow.core.ai.embedding import (
    EmbeddingClient,
    batch_generate_embedding,
    generate_embedding,
)
from dataflow.core.ai.factory import (
    create_llm_client,
    create_embedding_client,
    get_embedding_client,
    reset_embedding_client,
)
from dataflow.core.ai.models import (
    ModelConfig,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMRole,
    LLMUsage,
)
from dataflow.core.ai.llm import OpenAIClient, create_openai_client
from dataflow.core.ai.sumy import SumySummarizer, get_sumy_summarizer

__all__ = [
    # Base
    "BaseLLMClient",
    "LLMRetryClient",
    # Models
    "ModelConfig",
    "LLMMessage",
    "LLMResponse",
    "LLMUsage",
    "LLMProvider",
    "LLMRole",
    # OpenAI
    "OpenAIClient",
    "create_openai_client",
    # Factory
    "create_llm_client",
    "create_embedding_client",
    "get_embedding_client",
    "reset_embedding_client",
    # Embedding
    "EmbeddingClient",
    "generate_embedding",
    "batch_generate_embedding",
    # Sumy
    "SumySummarizer",
    "get_sumy_summarizer",
]
