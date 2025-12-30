"""
LLM 缓存模块

基于 Redis 的 LLM 响应缓存，严格参考 HippoRAG2 实现。

核心功能：
- 使用 Redis 替代 SQLite，支持分布式部署
- 无过期机制，缓存永久保存（与 HippoRAG2 一致）
- 支持异步操作
- 通过装饰器透明集成到 LLM 客户端

缓存键生成（与 HippoRAG2 完全一致）：
- messages: 消息列表
- model: 模型名称
- seed: 随机种子
- temperature: 温度参数

使用方式：
    from dataflow.core.cache import llm_cache

    class MyLLMClient:
        @llm_cache
        async def chat(self, messages, temperature=None, **kwargs) -> LLMResponse:
            # LLM API 调用逻辑
            ...
"""

import functools
import hashlib
import json
from typing import Tuple

from dataflow.core.ai.models import LLMResponse, LLMUsage
from dataflow.core.config import get_settings
from dataflow.core.storage.redis import get_redis_client
from dataflow.utils import get_logger

logger = get_logger("ai.cache")


def llm_cache(func):
    """
    LLM 缓存装饰器（严格按照 HippoRAG2 实现）

    特性：
    - 无过期机制，缓存永久保存
    - 只使用 messages, model, seed, temperature 生成缓存键

    Args:
        func: 被装饰的异步函数，应返回 LLMResponse 对象

    Returns:
        包装后的函数，返回 (LLMResponse, bool) 元组
        - LLMResponse: LLM 响应对象
        - bool: 是否命中缓存（True=命中，False=未命中）
    """

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs) -> Tuple[LLMResponse, bool]:
        settings = get_settings()

        # 如果缓存未启用，直接调用原函数
        if not settings.llm_cache_enabled:
            logger.debug("LLM 缓存未启用，直接调用")
            result = await func(self, *args, **kwargs)
            return result, False

        # 提取缓存键参数（只使用 HippoRAG2 的 4 个参数）
        messages = kwargs.get("messages") or (args[0] if args else None)
        if messages is None:
            raise ValueError("Missing required 'messages' parameter for caching")

        temperature = kwargs.get("temperature")
        seed = kwargs.get("seed")

        # 使用 self.config 中的默认值
        config = self.config
        model = config.model
        final_temperature = temperature if temperature is not None else config.temperature

        # 构建缓存键（与 HippoRAG2 完全一致）
        key_data = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "model": model,
            "seed": seed,
            "temperature": final_temperature,
        }
        key_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        key_hash = hashlib.sha256(key_str.encode("utf-8")).hexdigest()
        cache_key = f"{settings.llm_cache_prefix}{key_hash}"

        # 尝试从缓存读取
        redis_client = get_redis_client()

        try:
            cached_data = await redis_client.get(cache_key)

            if cached_data is not None:
                # 缓存命中，重建 LLMResponse 对象
                logger.info(f"缓存命中 - 模型: {model}")

                response = LLMResponse(
                    content=cached_data["content"],
                    model=cached_data["model"],
                    usage=LLMUsage(**cached_data["usage"]),
                    finish_reason=cached_data["finish_reason"],
                )
                return response, True

        except Exception as e:
            logger.warning(f"读取缓存失败: {e}，将直接调用 LLM")

        # 缓存未命中，调用原函数
        logger.debug(f"缓存未命中 - 模型: {model}")
        result = await func(self, *args, **kwargs)

        # 将结果写入缓存（无过期时间，永久保存）
        try:
            result_dict = {
                "content": result.content,
                "model": result.model,
                "usage": {
                    "prompt_tokens": result.usage.prompt_tokens,
                    "completion_tokens": result.usage.completion_tokens,
                    "total_tokens": result.usage.total_tokens,
                },
                "finish_reason": result.finish_reason,
            }

            # 写入缓存，永久保存
            await redis_client.set(cache_key, result_dict)

            logger.info(f"已缓存 - 模型: {model}（永久保存）")
        except Exception as e:
            logger.warning(f"写入缓存失败: {e}，不影响返回结果")

        return result, False

    return wrapper


async def clear_llm_cache(pattern: str = None) -> int:
    """
    清除 LLM 缓存

    Args:
        pattern: 可选的键模式，默认清除所有 LLM 缓存
                例如: "llm:cache:abc*" 只清除特定前缀的缓存

    Returns:
        删除的键数量
    """
    settings = get_settings()
    redis_client = get_redis_client()
    search_pattern = pattern or f"{settings.llm_cache_prefix}*"

    try:
        from dataflow.core.storage.redis import RedisClient

        if not isinstance(redis_client, RedisClient):
            logger.warning("Redis 客户端类型不匹配")
            return 0

        keys = []
        async for key in redis_client.client.scan_iter(match=search_pattern):
            keys.append(key)

        if not keys:
            logger.info(f"没有找到缓存键: {search_pattern}")
            return 0

        deleted_count = await redis_client.client.delete(*keys)
        logger.info(f"已清理 {deleted_count} 个缓存条目")
        return deleted_count

    except Exception as e:
        logger.error(f"清理缓存失败: {e}", exc_info=True)
        return 0
