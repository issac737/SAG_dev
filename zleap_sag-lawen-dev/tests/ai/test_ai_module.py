"""
AI 模块综合测试脚本

测试内容:
- 流式输出 vs 非流式输出
- 带重试 vs 不带重试
- 温度等配置参数
- 角色定义 (system, user, assistant)
- 任务执行
- JSON 输出验证

配置方式:
    1. 在项目根目录创建 .env 文件:
       LLM_API_KEY=sk-your-api-key
       LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507
       LLM_BASE_URL=https://your-proxy-api.com/v1  # 可选，中转API

    2. 或设置环境变量:
       export LLM_API_KEY='your-api-key'
       export LLM_MODEL='sophnet/Qwen3-30B-A3B-Thinking-2507'
       export LLM_BASE_URL='https://your-proxy-api.com/v1'

运行方式:
    python tests/test_ai_module.py

注意: factory.create_llm_client() 会自动从 settings 读取 .env 配置
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataflow.core.ai.factory import create_llm_client
from dataflow.core.ai.models import LLMMessage, LLMRole
from dataflow.exceptions import LLMError, LLMTimeoutError, LLMRateLimitError


class Colors:
    """终端颜色"""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_section(title: str) -> None:
    """打印测试章节标题"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{title:^70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.ENDC}\n")


def print_success(message: str) -> None:
    """打印成功消息"""
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")


def print_error(message: str) -> None:
    """打印错误消息"""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")


def print_info(message: str) -> None:
    """打印信息消息"""
    print(f"{Colors.OKCYAN}ℹ {message}{Colors.ENDC}")


def print_warning(message: str) -> None:
    """打印警告消息"""
    print(f"{Colors.WARNING}⚠ {message}{Colors.ENDC}")


async def test_basic_chat() -> bool:
    """测试 1: 基础聊天功能"""
    print_section("测试 1: 基础聊天功能")

    try:
        # 创建客户端（不带重试）
        client = create_llm_client(with_retry=False)
        print_info("创建 LLM 客户端（不带重试）")

        # 准备消息
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content="你是一个有帮助的助手。"),
            LLMMessage(role=LLMRole.USER, content="请用一句话介绍 Python。"),
        ]
        print_info(f"发送 {len(messages)} 条消息")

        # 调用 API
        response = await client.chat(messages)

        # 验证响应
        print_success("成功获取响应")
        print(f"  模型: {response.model}")
        print(f"  响应长度: {len(response.content)} 字符")
        print(f"  使用 token: {response.total_tokens}")
        print(f"  结束原因: {response.finish_reason}")
        print(f"\n  响应内容:\n  {response.content[:200]}...")

        return True

    except Exception as e:
        print_error(f"测试失败: {e}")
        return False


async def test_streaming_chat() -> bool:
    """测试 2: 流式输出"""
    print_section("测试 2: 流式输出")

    try:
        # 创建客户端（不带重试）
        client = create_llm_client(with_retry=False)
        print_info("创建 LLM 客户端（流式模式）")

        # 准备消息
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content="你是一个诗人。"),
            LLMMessage(role=LLMRole.USER, content="写一首关于春天的短诗（4行）。"),
        ]
        print_info("发送流式请求")

        # 流式调用
        chunks = []
        print("\n  流式输出: ", end="", flush=True)

        async for chunk in client.chat_stream(messages):
            print(chunk, end="", flush=True)
            chunks.append(chunk)

        print()  # 换行

        full_content = "".join(chunks)
        print_success(f"成功接收 {len(chunks)} 个流式片段")
        print(f"  总长度: {len(full_content)} 字符")

        return True

    except Exception as e:
        print_error(f"测试失败: {e}")
        return False


async def test_with_retry() -> bool:
    """测试 3: 带重试机制"""
    print_section("测试 3: 带重试机制")

    try:
        # 创建带重试的客户端
        client = create_llm_client(with_retry=True)
        print_info("创建 LLM 客户端（带智能重试）")

        # 准备消息
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content="你是一个数学老师。"),
            LLMMessage(role=LLMRole.USER, content="什么是斐波那契数列？"),
        ]
        print_info("发送请求（带重试保护）")

        # 调用 API
        response = await client.chat(messages)

        print_success("成功获取响应")
        print(f"  重试配置: 最多 {client.max_retries} 次")
        print(f"  响应长度: {len(response.content)} 字符")

        # 测试重试逻辑
        print_info("\n验证重试逻辑:")
        print(f"  超时错误会重试: {client._should_retry(LLMTimeoutError('test'))}")
        print(f"  速率限制会重试: {client._should_retry(LLMRateLimitError('test'))}")
        print(f"  LLM错误会重试: {client._should_retry(LLMError('test'))}")

        return True

    except Exception as e:
        print_error(f"测试失败: {e}")
        return False


async def test_temperature_configs() -> bool:
    """测试 4: 温度等配置参数"""
    print_section("测试 4: 温度等配置参数")

    try:
        client = create_llm_client(with_retry=False)

        # 测试不同的温度
        temperatures = [0.0, 0.5, 1.0]

        for temp in temperatures:
            print_info(f"\n测试温度: {temp}")

            messages = [
                LLMMessage(role=LLMRole.USER, content="说一个词来形容天空的颜色。"),
            ]

            response = await client.chat(
                messages,
                temperature=temp,
                max_tokens=50,
            )

            print(f"  响应 (temp={temp}): {response.content[:100]}")
            print(f"  使用 token: {response.total_tokens}")

        print_success("\n成功测试不同温度配置")
        return True

    except Exception as e:
        print_error(f"测试失败: {e}")
        return False


async def test_role_definitions() -> bool:
    """测试 5: 角色定义"""
    print_section("测试 5: 角色定义 (System, User, Assistant)")

    try:
        client = create_llm_client(with_retry=False)
        print_info("测试多轮对话与角色定义")

        # 多轮对话
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content="你是一个友好的编程助手，专注于 Python 编程。"),
            LLMMessage(role=LLMRole.USER, content="如何在 Python 中读取文件？"),
            LLMMessage(
                role=LLMRole.ASSISTANT, content="在 Python 中可以使用 open() 函数读取文件。"
            ),
            LLMMessage(role=LLMRole.USER, content="能给个具体例子吗？"),
        ]

        print_info(f"发送 {len(messages)} 条消息（包含历史对话）")
        for i, msg in enumerate(messages, 1):
            print(f"  {i}. [{msg.role.value}] {msg.content[:50]}...")

        response = await client.chat(messages, max_tokens=200)

        print_success("\n成功处理多轮对话")
        print(f"  最终响应:\n  {response.content[:300]}...")

        return True

    except Exception as e:
        print_error(f"测试失败: {e}")
        return False


async def test_json_output() -> bool:
    """测试 6: JSON 输出验证"""
    print_section("测试 6: JSON 输出与 Schema 验证")

    try:
        client = create_llm_client(with_retry=False)
        print_info("测试结构化 JSON 输出")

        # 定义 JSON Schema
        response_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"},
                "skills": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name", "age", "skills"],
        }

        print_info("JSON Schema:")
        print(f"  {json.dumps(response_schema, indent=2, ensure_ascii=False)}")

        # 准备消息
        messages = [
            LLMMessage(
                role=LLMRole.USER, content="创建一个虚构的程序员档案，包含姓名、年龄和技能列表。"
            ),
        ]

        # 调用带 Schema 的接口
        result = await client.chat_with_schema(
            messages,
            response_schema=response_schema,
            temperature=0.3,  # 降低温度以获得更稳定的 JSON
        )

        print_success("\n成功获取结构化 JSON 输出")
        print(f"  JSON 结果:")
        print(f"  {json.dumps(result, indent=2, ensure_ascii=False)}")

        # 验证字段
        assert "name" in result, "缺少 name 字段"
        assert "age" in result, "缺少 age 字段"
        assert "skills" in result, "缺少 skills 字段"
        assert isinstance(result["skills"], list), "skills 不是列表"

        print_success("JSON 字段验证通过")

        return True

    except Exception as e:
        print_error(f"测试失败: {e}")
        return False


async def test_task_execution() -> bool:
    """测试 7: 复杂任务执行"""
    print_section("测试 7: 复杂任务执行")

    try:
        client = create_llm_client(with_retry=True)
        print_info("测试代码生成任务")

        messages = [
            LLMMessage(
                role=LLMRole.SYSTEM, content="你是一个 Python 专家，擅长编写简洁高效的代码。"
            ),
            LLMMessage(
                role=LLMRole.USER,
                content="""
写一个 Python 函数来判断一个数是否为质数。
要求:
1. 函数名为 is_prime
2. 包含完整的文档字符串
3. 处理边界情况
4. 使用高效的算法
""",
            ),
        ]

        print_info("发送代码生成请求")

        response = await client.chat(
            messages,
            temperature=0.3,  # 低温度以获得更准确的代码
            max_tokens=500,
        )

        print_success("成功生成代码")
        print(f"  响应长度: {len(response.content)} 字符")
        print(f"  使用 token: {response.total_tokens}")
        print(f"\n  生成的代码:\n{response.content}")

        return True

    except Exception as e:
        print_error(f"测试失败: {e}")
        return False


async def test_error_handling() -> bool:
    """测试 8: 错误处理"""
    print_section("测试 8: 错误处理")

    try:
        print_info("测试无效 API 密钥")

        # 使用无效的 API 密钥
        client = create_llm_client(
            api_key="invalid-key-test",
            with_retry=False,
        )

        messages = [
            LLMMessage(role=LLMRole.USER, content="Hello"),
        ]

        try:
            await client.chat(messages)
            print_error("应该抛出异常但没有")
            return False
        except LLMError as e:
            print_success(f"正确捕获 LLMError: {str(e)[:100]}")
            return True

    except Exception as e:
        print_error(f"测试失败: {e}")
        return False


async def run_all_tests() -> None:
    """运行所有测试"""
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("=" * 70)
    print("DataFlow AI 模块综合测试".center(70))
    print("=" * 70)
    print(f"{Colors.ENDC}\n")

    print_info("配置来源: .env 文件或环境变量")
    print_info("factory.create_llm_client() 自动读取 settings 配置")
    print()

    # 尝试创建客户端以验证配置
    try:
        test_client = create_llm_client(with_retry=False)
        print_success("配置检查通过")
    except Exception as e:
        print_error(f"配置错误: {e}")
        print()
        print_info("请检查配置:")
        print("  1. 在项目根目录创建 .env 文件:")
        print("     LLM_API_KEY=sk-your-api-key")
        print("     LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507")
        print("  2. 或设置环境变量:")
        print("     export LLM_API_KEY='your-api-key'")
        return

    # 运行测试
    tests = [
        ("基础聊天功能", test_basic_chat),
        ("流式输出", test_streaming_chat),
        ("带重试机制", test_with_retry),
        ("温度等配置参数", test_temperature_configs),
        ("角色定义", test_role_definitions),
        ("JSON 输出验证", test_json_output),
        ("复杂任务执行", test_task_execution),
        ("错误处理", test_error_handling),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print_error(f"测试 '{name}' 发生异常: {e}")
            results.append((name, False))

        # 测试间隔
        await asyncio.sleep(1)

    # 打印总结
    print_section("测试总结")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        if result:
            print_success(f"{name}")
        else:
            print_error(f"{name}")

    print(f"\n{Colors.BOLD}总计: {passed}/{total} 测试通过{Colors.ENDC}")

    if passed == total:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}🎉 所有测试通过！{Colors.ENDC}")
    else:
        print(f"\n{Colors.WARNING}{Colors.BOLD}⚠ 部分测试失败{Colors.ENDC}")


def main() -> None:
    """主函数"""
    try:
        asyncio.run(run_all_tests())
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}测试被用户中断{Colors.ENDC}")
    except Exception as e:
        print_error(f"测试运行失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
