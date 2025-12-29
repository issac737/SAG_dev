"""
LLM 缓存装饰器

基于 Redis 的异步 LLM 响应缓存，参考 Hippo RAG2 的缓存策略：
- 使用影响模型输出的参数生成缓存键
- 支持精确匹配缓存
- 可配置 TTL 和缓存键前缀
"""

import functools
import hashlib
import json
from typing import Any, Optional

from dataflow.core.ai.models import LLMResponse, LLMUsage
from dataflow.core.config import get_settings
from dataflow.core.storage.redis import get_redis_client
from dataflow.utils import get_logger

logger = get_logger("ai.cache")


def llm_cache(func):
    """
    LLM 缓存装饰器

    缓存 LLM 响应以减少重复调用。缓存键基于：
    - messages (消息内容)
    - model (模型名称)
    - temperature (温度参数)
    - max_tokens (最大输出token数)
    - top_p (top_p 采样)
    - seed (随机种子，如果有)

    Args:
        func: 被装饰的异步函数，应该是 LLM 的 chat 或 chat_stream 方法

    Returns:
        装饰后的函数，返回 (response, is_cached) 元组
        - response: LLMResponse 对象
        - is_cached: bool，True 表示来自缓存，False 表示新请求
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

        # 构建缓存键数据
        # 只包含影响模型输出的关键参数
        key_data = {
            "messages": [
                {"role": m.role, "content": m.content} for m in messages
            ],  # 转为可序列化格式
            "model": model,
            "temperature": final_temperature,
            "max_tokens": final_max_tokens,
            "top_p": final_top_p,
        }

        # 添加 seed（如果存在）
        if seed is not None:
            key_data["seed"] = seed

        # 生成哈希键
        key_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        key_hash = hashlib.sha256(key_str.encode("utf-8")).hexdigest()
        cache_key = f"{settings.llm_cache_prefix}{key_hash}"

        # 尝试从 Redis 读取缓存
        redis_client = get_redis_client()
        try:
            cached_data = await redis_client.get(cache_key)
            if cached_data is not None:
                logger.info(
                    f"LLM 缓存命中 - 模型: {model}, "
                    f"键: {cache_key[:16]}..."
                )
                # 将字典转换为 LLMResponse 对象
                response = LLMResponse(
                    content=cached_data["content"],
                    model=cached_data["model"],
                    usage=LLMUsage(**cached_data["usage"]),
                    finish_reason=cached_data["finish_reason"],
                )
                return response, True
        except Exception as e:
            logger.warning(f"读取 LLM 缓存失败: {e}，将直接调用 LLM")

        # 缓存未命中，调用原始函数
        logger.debug(f"LLM 缓存未命中 - 模型: {model}")
        result = await func(self, *args, **kwargs)

        # 将结果写入缓存
        try:
            # 将 LLMResponse 转为可序列化格式
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

            await redis_client.set(
                cache_key, result_dict, expire=settings.cache_llm_ttl
            )
            logger.info(
                f"LLM 响应已缓存 - 模型: {model}, "
                f"TTL: {settings.cache_llm_ttl}s, "
                f"键: {cache_key[:16]}..."
            )
        except Exception as e:
            logger.warning(f"写入 LLM 缓存失败: {e}，但不影响返回结果")

        return result, False

    return wrapper


async def clear_llm_cache(pattern: str = None) -> int:
    """
    清理 LLM 缓存

    Args:
        pattern: 缓存键模式，留空则清理所有 LLM 缓存

    Returns:
        清理的缓存数量

    Example:
        # 清理所有 LLM 缓存
        await clear_llm_cache()

        # 清理特定模型的缓存
        await clear_llm_cache("llm:cache:*")
    """
    from dataflow.core.config import get_settings

    settings = get_settings()
    redis_client = get_redis_client()

    # 使用配置的前缀或自定义模式
    search_pattern = pattern or f"{settings.llm_cache_prefix}*"

    try:
        # 获取所有匹配的键
        from dataflow.core.storage.redis import RedisClient

        if not isinstance(redis_client, RedisClient):
            logger.warning("Redis 客户端类型不匹配，无法清理缓存")
            return 0

        # 使用 scan_iter 获取所有匹配的键
        keys = []
        async for key in redis_client.client.scan_iter(match=search_pattern):
            keys.append(key)

        if not keys:
            logger.info(f"没有找到匹配的缓存键: {search_pattern}")
            return 0

        # 批量删除
        deleted_count = await redis_client.client.delete(*keys)

        logger.info(f"已清理 {deleted_count} 个 LLM 缓存条目 (模式: {search_pattern})")
        return deleted_count

    except Exception as e:
        logger.error(f"清理 LLM 缓存失败: {e}", exc_info=True)
        return 0
