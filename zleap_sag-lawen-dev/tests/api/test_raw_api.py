"""
直接测试 OpenAI API 响应

检查原始 API 响应结构
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import AsyncOpenAI
from dataflow.core.config.settings import get_settings


async def test_raw_api():
    """测试原始 API 响应"""
    print("=" * 60)
    print("测试原始 OpenAI API 响应")
    print("=" * 60)

    settings = get_settings()

    print(f"\n配置:")
    print(f"  API Key: {settings.llm_api_key[:20]}...")
    print(f"  Model: {settings.llm_model}")
    print(f"  Base URL: {settings.llm_base_url}")

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=30,
    )

    messages = [
        {"role": "user", "content": "说一个词"}
    ]

    print(f"\n发送消息: {messages}")
    print("等待响应...\n")

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            max_tokens=50,
            temperature=0.7,
        )

        print("=" * 60)
        print("完整响应对象:")
        print("=" * 60)
        print(response)
        print()

        print("=" * 60)
        print("响应字段详情:")
        print("=" * 60)
        print(f"response.id: {response.id}")
        print(f"response.model: {response.model}")
        print(f"response.created: {response.created}")
        print(f"response.object: {response.object}")
        print()

        print("=" * 60)
        print("Choices详情:")
        print("=" * 60)
        print(f"choices数量: {len(response.choices)}")

        for i, choice in enumerate(response.choices):
            print(f"\nChoice {i}:")
            print(f"  index: {choice.index}")
            print(f"  finish_reason: {choice.finish_reason}")
            print(f"  message: {choice.message}")
            print(f"  message.role: {choice.message.role}")
            print(f"  message.content: '{choice.message.content}'")
            print(f"  message.content type: {type(choice.message.content)}")
            print(f"  message.content length: {len(choice.message.content or '')}")

            # 检查是否有其他字段
            print(f"\n  message的所有属性:")
            for attr in dir(choice.message):
                if not attr.startswith('_'):
                    value = getattr(choice.message, attr, None)
                    if value is not None and not callable(value):
                        print(f"    {attr}: {value}")

        print("\n" + "=" * 60)
        print("Usage详情:")
        print("=" * 60)
        if response.usage:
            print(f"prompt_tokens: {response.usage.prompt_tokens}")
            print(f"completion_tokens: {response.usage.completion_tokens}")
            print(f"total_tokens: {response.usage.total_tokens}")

            # 检查usage的其他属性
            print(f"\nusage的所有属性:")
            for attr in dir(response.usage):
                if not attr.startswith('_'):
                    value = getattr(response.usage, attr, None)
                    if value is not None and not callable(value):
                        print(f"  {attr}: {value}")

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(test_raw_api())
    except KeyboardInterrupt:
        print("\n测试被中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
