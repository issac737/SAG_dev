"""
LLM 缓存模块

提供基于 Redis 的 LLM 响应缓存功能，减少重复调用，提升性能。

核心特性（严格参考 HippoRAG2 实现）：
- 使用 Redis 替代 SQLite，支持分布式部署
- 无过期机制，缓存永久保存（与 HippoRAG2 一致）
- 缓存键参数：messages, model, seed, temperature
"""

from dataflow.core.cache.llm_cache import clear_llm_cache, llm_cache

__all__ = ["llm_cache", "clear_llm_cache"]
