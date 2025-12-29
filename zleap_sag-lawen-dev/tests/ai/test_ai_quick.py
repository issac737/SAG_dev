"""
AI 模块快速测试脚本

这是一个简化版本，用于快速验证 AI 模块的基本功能。

配置方式:
    1. 在项目根目录创建 .env 文件:
       echo "LLM_API_KEY=sk-your-api-key" > .env
       echo "LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507" >> .env

    2. 或设置环境变量:
       export LLM_API_KEY='your-api-key'
       export LLM_MODEL='sophnet/Qwen3-30B-A3B-Thinking-2507'

运行方式:
    python tests/test_ai_quick.py

注意: factory.create_llm_client() 会自动从 settings 读取配置
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataflow.core.ai.factory import create_llm_client
from dataflow.core.ai.models import LLMMessage, LLMRole


async def quick_test():
    """快速测试"""
    print("=" * 60)
    print("AI 模块快速测试")
    print("=" * 60)

    # 创建客户端（会自动从 settings 读取配置）
    print("\n[1] 创建 LLM 客户端...")
    print("    (自动从 .env 或环境变量读取配置)")

    try:
        client = create_llm_client(with_retry=True)
        print("✓ 客户端创建成功")
    except Exception as e:
        print(f"❌ 客户端创建失败: {e}")
        print("\n请检查配置:")
        print("  1. 在项目根目录创建 .env 文件，包含:")
        print("     LLM_API_KEY=sk-your-api-key")
        print("     LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507")
        print("  2. 或设置环境变量")
        return

    # 测试基础聊天
    print("\n[2] 测试基础聊天...")
    messages = [
        LLMMessage(role=LLMRole.SYSTEM, content="你是一个有帮助的助手。"),
        LLMMessage(role=LLMRole.USER, content="用一句话介绍 Python。"),
    ]

    response = await client.chat(messages, temperature=0.7, max_tokens=100)
    print(f"✓ 响应: {response.content}")
    print(f"✓ 使用 token: {response.total_tokens}")

    # 测试流式输出
    print("\n[3] 测试流式输出...")
    messages = [
        LLMMessage(role=LLMRole.USER, content="数 1 到 5。"),
    ]

    print("✓ 流式输出: ", end="", flush=True)
    async for chunk in client.chat_stream(messages, max_tokens=50):
        print(chunk, end="", flush=True)
    print()

    # 测试 JSON 输出
    print("\n[4] 测试 JSON 输出...")
    schema = {
        "type": "object",
        "properties": {"language": {"type": "string"}, "year": {"type": "number"}},
        "required": ["language", "year"],
    }

    messages = [
        LLMMessage(role=LLMRole.USER, content="告诉我 Python 语言的名称和创建年份。"),
    ]

    result = await client.chat_with_schema(messages, schema, temperature=0.3)
    print(f"✓ JSON 结果: {result}")

    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(quick_test())
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
