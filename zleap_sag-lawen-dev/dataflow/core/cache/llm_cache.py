"""
LLM 缓存装饰器 - 基于访问频率的自适应过期策略

策略：
- 15 天内访问次数 < 3 → 自动删除
- 访问次数 >= 3 → 根据频率给不同的 TTL
  - 访问 >= 10 次：90 天
  - 访问 >= 5 次：60 天
  - 访问 >= 3 次：30 天
"""

import functools
import hashlib
import json
import time
from typing import Any, Optional

from dataflow.core.ai.models import LLMResponse, LLMUsage
from dataflow.core.config import get_settings
from dataflow.core.storage.redis import get_redis_client
from dataflow.utils import get_logger

logger = get_logger("ai.cache")


def llm_cache(func):
    """
    LLM 缓存装饰器（自适应频率策略）

    缓存结构：
    {
        "content": "...",
        "model": "...",
        "usage": {...},
        "finish_reason": "...",
        "access_count": 5,              # 访问次数
        "first_access_time": 1234567890, # 首次访问时间戳
        "last_access_time": 1234567890   # 最后访问时间戳
    }
    """

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        settings = get_settings()

        # 检查是否启用缓存
        if not settings.llm_cache_enabled:
            logger.debug("LLM 缓存未启用，直接调用")
            result = await func(self, *args, **kwargs)
            return result, False

        # 提取参数
        messages = kwargs.get("messages") or (args[0] if args else None)
        if messages is None:
            raise ValueError("Missing required 'messages' parameter for caching.")

        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")
        top_p = kwargs.get("top_p")
        seed = kwargs.get("seed")

        # 使用 self.config 中的默认值
        config = self.config
        model = config.model
        final_temperature = temperature if temperature is not None else config.temperature
        final_max_tokens = max_tokens if max_tokens is not None else config.max_tokens
        final_top_p = top_p if top_p is not None else config.top_p

        # 构建缓存键
        key_data = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "model": model,
            "temperature": final_temperature,
            "max_tokens": final_max_tokens,
            "top_p": final_top_p,
        }

        if seed is not None:
            key_data["seed"] = seed

        key_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        key_hash = hashlib.sha256(key_str.encode("utf-8")).hexdigest()
        cache_key = f"{settings.llm_cache_prefix}{key_hash}"

        # 尝试从 Redis 读取缓存
        redis_client = get_redis_client()
        current_time = int(time.time())

        try:
            cached_data = await redis_client.get(cache_key)
            if cached_data is not None:
                # 检查是否需要清理（15 天内访问次数 < 3）
                first_access = cached_data.get("first_access_time", current_time)
                access_count = cached_data.get("access_count", 0)
                days_since_first = (current_time - first_access) / 86400

                if days_since_first >= 15 and access_count < 3:
                    # 低频访问，删除缓存
                    await redis_client.delete(cache_key)
                    logger.info(
                        f"缓存已清理（低频） - 模型: {model}, "
                        f"15天访问次数: {access_count}"
                    )
                    # 继续执行，重新调用 API
                else:
                    # 更新访问统计
                    cached_data["access_count"] = access_count + 1
                    cached_data["last_access_time"] = current_time

                    # 根据访问频率给不同的 TTL
                    if access_count >= 10:
                        ttl = 90 * 86400  # 90 天
                    elif access_count >= 5:
                        ttl = 60 * 86400  # 60 天
                    else:
                        ttl = 30 * 86400  # 30 天

                    await redis_client.set(cache_key, cached_data, expire=ttl)

                    logger.info(
                        f"缓存命中 - 模型: {model}, "
                        f"访问: {cached_data['access_count']}次, "
                        f"TTL: {ttl // 86400}天"
                    )

                    # 重构 LLMResponse
                    response = LLMResponse(
                        content=cached_data["content"],
                        model=cached_data["model"],
                        usage=LLMUsage(**cached_data["usage"]),
                        finish_reason=cached_data["finish_reason"],
                    )
                    return response, True

        except Exception as e:
            logger.warning(f"读取缓存失败: {e}，将直接调用 LLM")

        # 缓存未命中，调用原始函数
        logger.debug(f"缓存未命中 - 模型: {model}")
        result = await func(self, *args, **kwargs)

        # 写入缓存（初始化访问统计）
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
                # 访问统计
                "access_count": 1,
                "first_access_time": current_time,
                "last_access_time": current_time,
            }

            # 初始 TTL 15 天（观察期）
            initial_ttl = 15 * 86400

            await redis_client.set(cache_key, result_dict, expire=initial_ttl)

            logger.info(f"已缓存 - 模型: {model}, 初始TTL: 15天")
        except Exception as e:
            logger.warning(f"写入缓存失败: {e}，不影响返回结果")

        return result, False

    return wrapper


async def clear_llm_cache(pattern: str = None) -> int:
    """清理 LLM 缓存"""
    from dataflow.core.config import get_settings

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
