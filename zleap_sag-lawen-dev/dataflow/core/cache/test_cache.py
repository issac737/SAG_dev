"""
LLM 缓存测试示例

演示如何使用 LLM 缓存功能
"""

import asyncio

from dataflow.core.ai.factory import create_llm_client
from dataflow.core.ai.models import LLMMessage, LLMRole
from dataflow.core.cache import clear_llm_cache
from dataflow.core.config import get_settings
from dataflow.utils import get_logger

logger = get_logger(__name__)


async def test_llm_cache():
    """测试 LLM 缓存功能"""

    settings = get_settings()
    logger.info(f"LLM 缓存配置:")
    logger.info(f"  - 启用: {settings.llm_cache_enabled}")
    logger.info(f"  - 前缀: {settings.llm_cache_prefix}")
    logger.info(f"  - TTL: {settings.cache_llm_ttl}s")

    # 创建 LLM 客户端
    client = await create_llm_client()

    # 准备测试消息
    messages = [
        LLMMessage(role=LLMRole.USER, content="你好，请简单介绍一下自己")
    ]

    logger.info("\n" + "=" * 60)
    logger.info("第一次调用 - 应该调用 LLM API（缓存未命中）")
    logger.info("=" * 60)

    response1 = await client.chat(messages=messages)
    logger.info(f"响应内容: {response1.content[:100]}...")
    logger.info(f"Token 使用: {response1.usage.total_tokens}")

    logger.info("\n" + "=" * 60)
    logger.info("第二次调用 - 应该从缓存返回（缓存命中）")
    logger.info("=" * 60)

    response2 = await client.chat(messages=messages)
    logger.info(f"响应内容: {response2.content[:100]}...")
    logger.info(f"Token 使用: {response2.usage.total_tokens}")

    # 验证两次响应是否相同
    assert response1.content == response2.content, "缓存响应应该与原始响应相同"
    logger.info("\n✅ 缓存验证通过 - 两次响应内容一致")

    logger.info("\n" + "=" * 60)
    logger.info("清理缓存")
    logger.info("=" * 60)

    deleted_count = await clear_llm_cache()
    logger.info(f"已清理 {deleted_count} 个缓存条目")

    logger.info("\n" + "=" * 60)
    logger.info("清理后再次调用 - 应该重新调用 LLM API")
    logger.info("=" * 60)

    response3 = await client.chat(messages=messages)
    logger.info(f"响应内容: {response3.content[:100]}...")
    logger.info(f"Token 使用: {response3.usage.total_tokens}")

    logger.info("\n✅ 所有测试通过！")


async def test_cache_with_different_params():
    """测试不同参数的缓存隔离"""

    client = await create_llm_client()
    messages = [LLMMessage(role=LLMRole.USER, content="请用一句话介绍 Python")]

    logger.info("\n" + "=" * 60)
    logger.info("测试参数隔离 - 不同 temperature 应该产生不同缓存")
    logger.info("=" * 60)

    # temperature = 0.0
    logger.info("调用 1: temperature=0.0")
    response1 = await client.chat(messages=messages, temperature=0.0)
    logger.info(f"响应: {response1.content[:100]}...")

    # temperature = 0.7
    logger.info("\n调用 2: temperature=0.7")
    response2 = await client.chat(messages=messages, temperature=0.7)
    logger.info(f"响应: {response2.content[:100]}...")

    # 再次调用 temperature = 0.0，应该命中缓存
    logger.info("\n调用 3: temperature=0.0 (应该命中缓存)")
    response3 = await client.chat(messages=messages, temperature=0.0)
    logger.info(f"响应: {response3.content[:100]}...")

    assert response1.content == response3.content, "相同参数应该返回相同缓存"
    logger.info("\n✅ 参数隔离测试通过！")


if __name__ == "__main__":
    # 运行基础缓存测试
    asyncio.run(test_llm_cache())

    # 运行参数隔离测试
    asyncio.run(test_cache_with_different_params())
