"""
AI 模块使用示例

展示如何在实际代码中使用 DataFlow AI 模块的各种功能。
"""

import asyncio
import json
from typing import List
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataflow.core.ai.factory import create_llm_client
from dataflow.core.ai.models import LLMMessage, LLMRole


# ============================================================================
# 示例 1: 基本对话
# ============================================================================


async def example_basic_chat():
    """示例 1: 基本对话"""
    print("\n" + "=" * 60)
    print("示例 1: 基本对话")
    print("=" * 60)

    # 创建客户端
    client = create_llm_client(with_retry=True)

    # 准备消息
    messages = [
        LLMMessage(role=LLMRole.SYSTEM, content="你是一个有帮助的助手。"),
        LLMMessage(role=LLMRole.USER, content="什么是机器学习？"),
    ]

    # 发送请求
    response = await client.chat(messages, temperature=0.7)

    print(f"回答: {response.content}")
    print(f"使用 token: {response.total_tokens}")


# ============================================================================
# 示例 2: 流式对话（实时输出）
# ============================================================================


async def example_streaming_chat():
    """示例 2: 流式对话"""
    print("\n" + "=" * 60)
    print("示例 2: 流式对话（实时输出）")
    print("=" * 60)

    client = create_llm_client(with_retry=False)

    messages = [
        LLMMessage(role=LLMRole.SYSTEM, content="你是一个故事作家。"),
        LLMMessage(role=LLMRole.USER, content="讲一个关于小猫的短故事。"),
    ]

    print("故事: ", end="", flush=True)

    # 流式接收
    async for chunk in client.chat_stream(messages):
        print(chunk, end="", flush=True)

    print("\n")


# ============================================================================
# 示例 3: 多轮对话
# ============================================================================


async def example_multi_turn_chat():
    """示例 3: 多轮对话"""
    print("\n" + "=" * 60)
    print("示例 3: 多轮对话")
    print("=" * 60)

    client = create_llm_client(with_retry=True)

    # 对话历史
    conversation: List[LLMMessage] = [
        LLMMessage(role=LLMRole.SYSTEM, content="你是一个 Python 编程专家，用简洁的语言回答。"),
    ]

    # 第一轮对话
    print("\n问题 1: 如何创建一个 Python 列表？")
    conversation.append(
        LLMMessage(role=LLMRole.USER, content="如何创建一个 Python 列表？用一句话简单说明。")
    )

    response1 = await client.chat(conversation, max_tokens=150)
    print(f"回答 1: {response1.content}")

    # 将助手的回答添加到对话历史
    conversation.append(LLMMessage(role=LLMRole.ASSISTANT, content=response1.content))

    # 第二轮对话（基于上下文的后续问题）
    print("\n问题 2: 那字典呢？")
    conversation.append(LLMMessage(role=LLMRole.USER, content="那字典呢？"))

    response2 = await client.chat(conversation, max_tokens=150)
    print(f"回答 2: {response2.content}")

    # 显示完整对话历史
    print("\n对话历史:")
    for i, msg in enumerate(conversation, 1):
        role_display = {"system": "系统", "user": "用户", "assistant": "助手"}.get(
            msg.role.value, msg.role.value
        )
        content_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
        print(f"  {i}. [{role_display}] {content_preview}")


# ============================================================================
# 示例 4: 结构化输出（JSON）
# ============================================================================


async def example_structured_output():
    """示例 4: 结构化输出"""
    print("\n" + "=" * 60)
    print("示例 4: 结构化输出（JSON）")
    print("=" * 60)

    client = create_llm_client(with_retry=True)

    # 定义期望的 JSON 结构
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "书籍标题"},
            "author": {"type": "string", "description": "作者姓名"},
            "year": {"type": "number", "description": "出版年份"},
            "genres": {"type": "array", "items": {"type": "string"}, "description": "类型列表"},
            "summary": {"type": "string", "description": "简短摘要"},
        },
        "required": ["title", "author", "year", "genres"],
    }

    messages = [
        LLMMessage(role=LLMRole.USER, content="创建一本虚构的科幻小说的信息。"),
    ]

    # 获取结构化输出
    book_info = await client.chat_with_schema(
        messages,
        response_schema=schema,
        temperature=0.5,
    )

    print("书籍信息:")
    print(json.dumps(book_info, indent=2, ensure_ascii=False))


# ============================================================================
# 示例 5: 温度控制
# ============================================================================


async def example_temperature_control():
    """示例 5: 温度控制"""
    print("\n" + "=" * 60)
    print("示例 5: 温度控制（创造性 vs 确定性）")
    print("=" * 60)

    client = create_llm_client(with_retry=False)

    prompt = "给我一个形容天空的词。"

    # 低温度 - 更确定、一致
    print("低温度 (0.2) - 确定性输出:")
    messages = [LLMMessage(role=LLMRole.USER, content=prompt)]
    response_low = await client.chat(messages, temperature=0.2, max_tokens=10)
    print(f"  {response_low.content}\n")

    # 中温度 - 平衡
    print("中温度 (0.7) - 平衡:")
    response_mid = await client.chat(messages, temperature=0.7, max_tokens=10)
    print(f"  {response_mid.content}\n")

    # 高温度 - 更有创造性、随机
    print("高温度 (1.2) - 创造性输出:")
    response_high = await client.chat(messages, temperature=1.2, max_tokens=10)
    print(f"  {response_high.content}")


# ============================================================================
# 示例 6: 代码生成任务
# ============================================================================


async def example_code_generation():
    """示例 6: 代码生成"""
    print("\n" + "=" * 60)
    print("示例 6: 代码生成任务")
    print("=" * 60)

    client = create_llm_client(with_retry=True)

    messages = [
        LLMMessage(role=LLMRole.SYSTEM, content="你是一个 Python 专家，编写清晰、高效的代码。"),
        LLMMessage(
            role=LLMRole.USER,
            content="""
写一个 Python 函数来计算斐波那契数列的第 n 项。
要求:
- 函数名为 fibonacci
- 使用迭代法（不是递归）
- 包含文档字符串
- 处理 n=0 和 n=1 的边界情况
""",
        ),
    ]

    response = await client.chat(
        messages,
        temperature=0.3,  # 低温度以获得更准确的代码
        max_tokens=300,
    )

    print("生成的代码:")
    print(response.content)


# ============================================================================
# 示例 7: 错误处理
# ============================================================================


async def example_error_handling():
    """示例 7: 错误处理"""
    print("\n" + "=" * 60)
    print("示例 7: 错误处理")
    print("=" * 60)

    from dataflow.exceptions import (
        LLMError,
        LLMTimeoutError,
        LLMRateLimitError,
    )

    client = create_llm_client(with_retry=True)

    messages = [
        LLMMessage(role=LLMRole.USER, content="你好"),
    ]

    try:
        response = await client.chat(messages)
        print(f"成功: {response.content[:50]}...")

    except LLMTimeoutError as e:
        print(f"超时错误: {e}")
        # 可以选择不重试或使用其他策略

    except LLMRateLimitError as e:
        print(f"速率限制: {e}")
        # 等待一段时间后重试

    except LLMError as e:
        print(f"LLM 错误: {e}")
        # 通用 LLM 错误处理

    except Exception as e:
        print(f"未知错误: {e}")


# ============================================================================
# 示例 8: 使用工厂方法自定义配置
# ============================================================================


async def example_custom_config():
    """示例 8: 自定义配置"""
    print("\n" + "=" * 60)
    print("示例 8: 使用工厂方法自定义配置")
    print("=" * 60)

    # 自定义配置创建客户端
    client = create_llm_client(
        model="gpt-3.5-turbo",  # 使用不同的模型
        temperature=0.5,  # 默认温度
        max_tokens=150,  # 默认最大 token
        with_retry=True,  # 启用重试
    )

    messages = [
        LLMMessage(role=LLMRole.USER, content="测试自定义配置"),
    ]

    response = await client.chat(messages)
    print(f"模型: {response.model}")
    print(f"响应: {response.content[:100]}...")


# ============================================================================
# 主函数
# ============================================================================


async def main():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("DataFlow AI 模块使用示例")
    print("=" * 60)

    examples = [
        ("基本对话", example_basic_chat),
        ("流式对话", example_streaming_chat),
        ("多轮对话", example_multi_turn_chat),
        ("结构化输出", example_structured_output),
        ("温度控制", example_temperature_control),
        ("代码生成", example_code_generation),
        ("错误处理", example_error_handling),
        ("自定义配置", example_custom_config),
    ]

    for i, (name, example_func) in enumerate(examples, 1):  # pylint: disable=unused-variable
        try:
            await example_func()
        except Exception as e:
            print(f"\n❌ 示例 {i} ({name}) 失败: {e}")

        # 示例间隔
        if i < len(examples):
            await asyncio.sleep(1)

    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)


if __name__ == "__main__":
    import os

    # 检查环境变量
    # if not os.getenv("LLM_API_KEY"):
    #     print("❌ 请设置环境变量: export LLM_API_KEY='your-api-key'")
    # else:
    asyncio.run(main())
