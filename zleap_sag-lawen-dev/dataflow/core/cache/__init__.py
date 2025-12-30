"""
LLM 缓存模块

提供基于 Redis 的 LLM 响应缓存功能，减少重复调用，提升性能。

使用自适应频率缓存策略：
- 15 天内访问次数 < 3 → 自动删除
- 访问次数 >= 3 → 根据频率给不同的 TTL
  - 访问 >= 10 次：90 天
  - 访问 >= 5 次：60 天
  - 访问 >= 3 次：30 天
"""

from dataflow.core.cache.llm_cache import clear_llm_cache, llm_cache

__all__ = ["llm_cache", "clear_llm_cache"]
