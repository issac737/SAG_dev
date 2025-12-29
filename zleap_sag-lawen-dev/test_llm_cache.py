"""
LLM 缓存快速测试

在 VSCode 中右键 -> "在终端中运行 Python 文件" 或按 Ctrl+F5
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from dataflow.core.ai.factory import create_llm_client
from dataflow.core.ai.models import LLMMessage, LLMRole
from dataflow.core.cache import clear_llm_cache
from dataflow.core.config import get_settings
from dataflow.utils import get_logger

logger = get_logger(__name__)


async def main():
    """主测试函数"""

    # 显示当前配置
    settings = get_settings()
    print("\n" + "=" * 70)
    print("📋 LLM 缓存配置")
    print("=" * 70)
    print(f"✅ 缓存启用: {settings.llm_cache_enabled}")
    print(f"🔑 键前缀: {settings.llm_cache_prefix}")
    print(f"⏰ TTL: {settings.cache_llm_ttl} 秒 ({settings.cache_llm_ttl // 86400} 天)")
    print(f"🤖 模型: {settings.llm_model}")
    print(f"🌐 API 地址: {settings.llm_base_url or 'OpenAI 官方'}")
    print("=" * 70 + "\n")

    # 创建 LLM 客户��
    print("正在创建 LLM 客户端...")
    try:
        client = await create_llm_client()
        print("✅ LLM 客户端创建成功\n")
    except Exception as e:
        print(f"❌ 创建 LLM 客户端失败: {e}")
        print("\n请检查 .env 文件中的配置:")
        print("  - llm_api_key")
        print("  - llm_model")
        print("  - llm_base_url")
        return

    # 准备测试消息
    messages = [
        LLMMessage(role=LLMRole.USER, content="请用一句话介绍 Python 编程语言")
    ]

    print("=" * 70)
    print("🚀 第一次调用 - 应该调用 LLM API（缓存未命中）")
    print("=" * 70)

    try:
        response1 = await client.chat(messages=messages)
        print(f"✅ 响应成功")
        print(f"📝 内容: {response1.content[:100]}...")
        print(f"📊 Token 使用: 输入={response1.usage.prompt_tokens}, "
              f"输出={response1.usage.completion_tokens}, "
              f"总计={response1.usage.total_tokens}")
        print(f"🏁 完成原因: {response1.finish_reason}\n")
    except Exception as e:
        print(f"❌ 调用失败: {e}\n")
        return

    print("=" * 70)
    print("🎯 第二次调用 - 应该从缓存返回（缓存命中）")
    print("=" * 70)

    try:
        response2 = await client.chat(messages=messages)
        print(f"✅ 响应成功")
        print(f"📝 内容: {response2.content[:100]}...")
        print(f"📊 Token 使用: 输入={response2.usage.prompt_tokens}, "
              f"输出={response2.usage.completion_tokens}, "
              f"总计={response2.usage.total_tokens}")
        print(f"🏁 完成原因: {response2.finish_reason}\n")
    except Exception as e:
        print(f"❌ 调用失败: {e}\n")
        return

    # 验证缓存
    if response1.content == response2.content:
        print("✅ 缓存验证通过 - 两次响应内容完全一致")
    else:
        print("❌ 缓存验证失败 - 两次响应内容不一致")
        print(f"响应1: {response1.content[:50]}...")
        print(f"响应2: {response2.content[:50]}...")

    print("\n" + "=" * 70)
    print("🧹 清理缓存测试")
    print("=" * 70)

    try:
        deleted_count = await clear_llm_cache()
        print(f"✅ 已清理 {deleted_count} 个缓存条目\n")
    except Exception as e:
        print(f"❌ 清理缓存失败: {e}\n")

    print("=" * 70)
    print("✨ 所有测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())
