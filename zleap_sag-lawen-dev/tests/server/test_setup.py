#!/usr/bin/env python3
"""
DataFlow 快速测试脚本

测试基础设施是否正常工作
"""

import asyncio

from dataflow.core.ai import LLMMessage, LLMRole, create_llm_client
from dataflow.core.config import get_settings
from dataflow.core.storage import get_es_client, get_mysql_client, get_redis_client
from dataflow.models import Article, Entity, User
from dataflow.utils import get_logger, get_utc_now, setup_logging

# 配置日志
setup_logging()
logger = get_logger("test")


async def test_config():
    """测试配置加载"""
    print("\n=== 测试配置加载 ===")
    settings = get_settings()
    print(f"✓ MySQL: {settings.mysql_host}:{settings.mysql_port}")
    print(f"✓ Redis: {settings.redis_host}:{settings.redis_port}")
    print(f"✓ LLM: {settings.llm_model}")
    if settings.llm_base_url:
        print(f"  中转API: {settings.llm_base_url}")
    # print(f"✓ 实体权重: {settings.entity_weights_dict}")


async def test_models():
    """测试数据模型"""
    print("\n=== 测试数据模型 ===")

    # 创建用户
    user = User(
        id="test-user-001",
        username="testuser",
        email="test@example.com",
        preferences={"focus": ["AI", "ML"]},
    )
    print(f"✓ User模型: {user.username} ({user.email})")

    # 创建文章
    article = Article(
        id="test-article-001",
        user_id=user.id,
        title="测试文章",
        content="这是一篇测试文章的内容",
        summary="测试摘要",
    )
    print(f"✓ Article模型: {article.title}")

    # 创建实体
    entity = Entity(
        id="test-entity-001",
        user_id=user.id,
        type="topic",
        name="人工智能",
        normalized_name="人工智能",
        description="AI相关话题",
    )
    print(f"✓ Entity模型: {entity.name} ({entity.type})")


async def test_storage():
    """测试存储客户端"""
    print("\n=== 测试存储客户端 ===")

    # 测试MySQL
    try:
        mysql = get_mysql_client()
        is_connected = await mysql.ping()
        if is_connected:
            print("✓ MySQL连接成功")
        else:
            print("✗ MySQL连接失败")
    except Exception as e:
        print(f"✗ MySQL连接失败: {e}")

    # 测试Redis
    try:
        redis = get_redis_client()
        is_connected = await redis.ping()
        if is_connected:
            print("✓ Redis连接成功")

            # 测试缓存操作
            await redis.set("test_key", "test_value", expire=60)
            value = await redis.get("test_key")
            assert value == "test_value"
            print("✓ Redis读写操作正常")

            await redis.delete("test_key")
        else:
            print("✗ Redis连接失败")
    except Exception as e:
        print(f"✗ Redis连接失败: {e}")

    # 测试Elasticsearch
    try:
        es = get_es_client()
        is_connected = await es.ping()
        if is_connected:
            print("✓ Elasticsearch连接成功")
        else:
            print("✗ Elasticsearch连接失败")
    except Exception as e:
        print(f"✗ Elasticsearch连接失败: {e}")


async def test_llm():
    """测试LLM客户端"""
    print("\n=== 测试LLM客户端 ===")

    settings = get_settings()

    # 检查API Key
    if not settings.llm_api_key or settings.llm_api_key == "sk-xxx":
        print("⚠ LLM API Key未配置，跳过测试")
        print("  请在.env文件中配置 LLM_API_KEY")
        return

    try:
        # 创建客户端
        llm = create_llm_client(with_retry=True)
        print(f"✓ LLM客户端创建成功: {settings.llm_model}")

        # 测试简单调用
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content="你是一个友好的助手"),
            LLMMessage(role=LLMRole.USER, content="用一句话介绍DataFlow项目"),
        ]

        print("  正在调用LLM...")
        response = await llm.chat(messages, max_tokens=100)
        print(f"✓ LLM响应: {response.content[:100]}...")
        print(f"  Token使用: {response.usage.total_tokens}")

        # 测试结构化输出
        print("\n  测试结构化输出...")
        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "keywords"],
        }

        messages[1] = LLMMessage(
            role=LLMRole.USER,
            content="请用一句话总结DataFlow项目，并提取3个关键词",
        )

        result = await llm.chat_with_schema(messages, schema, max_tokens=100)
        print(f"✓ 结构化输出成功:")
        print(f"  摘要: {result.get('summary', '')}")
        print(f"  关键词: {', '.join(result.get('keywords', []))}")

    except Exception as e:
        print(f"✗ LLM测试失败: {e}")


async def test_utils():
    """测试工具函数"""
    print("\n=== 测试工具函数 ===")

    from dataflow.utils import (
        estimate_tokens,
        extract_markdown_headings,
        normalize_entity_name,
        truncate_text,
    )

    # 测试文本处理
    text = "这是一个测试文本，包含中文和English混合内容"
    tokens = estimate_tokens(text)
    print(f"✓ Token估算: {tokens} tokens")

    # 测试实体标准化
    entity = "  人工智能  (AI) ！！"
    normalized = normalize_entity_name(entity)
    print(f"✓ 实体标准化: '{entity}' -> '{normalized}'")

    # 测试文本截断
    long_text = "这是一段很长的文本" * 20
    short_text = truncate_text(long_text, max_length=50)
    print(f"✓ 文本截断: {len(long_text)}字符 -> {len(short_text)}字符")

    # 测试Markdown标题提取
    markdown = """
# 一级标题
## 二级标题
### 三级标题
"""
    headings = extract_markdown_headings(markdown)
    print(f"✓ Markdown标题提取: {len(headings)}个标题")

    # 测试时间工具
    now = get_utc_now()
    print(f"✓ 当前UTC时间: {now.isoformat()}")


async def main():
    """主函数"""
    print("=" * 60)
    print("DataFlow 基础设施测试")
    print("=" * 60)

    try:
        await test_config()
        await test_models()
        await test_utils()
        await test_storage()
        await test_llm()

        print("\n" + "=" * 60)
        print("✓ 测试完成！")
        print("=" * 60)

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n✗ 测试失败: {e}")

    finally:
        # 清理资源
        from dataflow.core.storage import (
            close_es_client,
            close_mysql_client,
            close_redis_client,
        )

        await close_mysql_client()
        await close_redis_client()
        await close_es_client()


if __name__ == "__main__":
    asyncio.run(main())
