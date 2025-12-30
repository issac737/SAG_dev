"""
测试提取提示词 - 对比原版 vs 增强版

用法：
1. 运行：python test_extract.py
2. 查看输出对比结果

配置：自动从 .env 文件读取
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# 测试文件路径
TEST_FILE_PATH = PROJECT_ROOT / "tests" / "extract" / "test_extract_prompt" / "林俊杰女友照片经常被识别为AI林俊杰官宣恋情.md"

# LLM 配置（从环境变量读取）
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")

# 提示词文件路径
PROMPT_V1 = str(PROJECT_ROOT / "prompts" / "extract.yaml")
PROMPT_V2 = str(PROJECT_ROOT / "tests" / "extract" / "test_extract_prompt" / "extract_v2.yaml")


# 添加项目路径到 sys.path
sys.path.insert(0, str(PROJECT_ROOT))


async def test_prompt_extraction(
    test_file: str,
    prompt_file: str,
    version_name: str
) -> Dict[str, Any]:
    """
    测试单个提示词版本的提取效果

    Args:
        test_file: 测试文件路径
        prompt_file: 提示词文件路径
        version_name: 版本名称（用于输出）

    Returns:
        提取结果统计
    """
    print(f"\n{'='*80}")
    print(f"测试版本: {version_name}")
    print(f"{'='*80}")
    print(f"提示词文件: {prompt_file}")
    print(f"测试文件: {test_file}\n")

    # 1. 读取测试文件
    print("读取测试文件...")
    try:
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"文件读取成功 ({len(content)} 字符, {len(content.splitlines())} 行)")
    except Exception as e:
        print(f"❌ 文件读取失败: {e}")
        return {"error": str(e)}

    # 2. 加载提示词
    print(f"\n加载提示词...")
    try:
        from dataflow.core.prompt.manager import PromptManager

        # 获取提示词所在目录
        prompt_dir = Path(prompt_file).parent
        prompt_manager = PromptManager(prompts_dir=prompt_dir)

        # 读取提示词内容用于显示
        with open(prompt_file, 'r', encoding='utf-8') as f:
            prompt_content = f.read()

        print(f"提示词加载成功")
        print(f"   提示词长度: {len(prompt_content)} 字符")

    except Exception as e:
        print(f"提示词加载失败: {e}")
        return {"error": str(e)}

    # 3. 初始化 LLM 客户端
    print(f"\n初始化 LLM 客户端...")
    try:
        from dataflow.core.ai.factory import create_llm_client
        from dataflow.core.ai.models import LLMMessage, LLMRole

        # 创建临时配置
        model_config = {
            "model": LLM_MODEL,
            "api_key": LLM_API_KEY,
            "base_url": LLM_BASE_URL,
            "temperature": 0.3
        }

        llm_client = await create_llm_client(
            scenario='extract',
            model_config=model_config
        )

        print(f"LLM 客户端初始化成功")
        print(f"   模型: {LLM_MODEL}")

    except Exception as e:
        print(f"LLM 客户端初始化失败: {e}")
        return {"error": str(e)}

    # 4. 构建提示词
    print(f"\n构建提示词...")

    # 提取原文内容（模拟分块）
    sections = [
        {
            "id": "section_1",
            "content": content
        }
    ]

    # 构建提示词参数
    background = """ """

    # 构建实体类型描述
    entity_types = """
- **person** (人物): 人名，如林俊杰
- **organization** (机构): 组织机构名称
- **location** (地点): 地理位置名称
- **tags** (关键词): 其他重要关键词
"""

    # 提取候选关键词（简单取前100个字符作为示例）
    candidate_keywords = content[:100] if content else "无"

    # 构建输出 schema
    output_schema = json.dumps({
        "title": "简洁标题",
        "summary": "一句话摘要",
        "content": "完整事件内容",
        "category": "分类标签",
        "references": ["section.id"],
        "entities": [{"type": "类型", "name": "名称", "description": "描述"}],
        "is_valid": True
    }, ensure_ascii=False, indent=2)

    # 渲染提示词
    try:
        system_prompt = prompt_manager.render(
            "event_extraction" if version_name == "原版(v1)" else "event_extraction",
            background=background,
            entity_types=entity_types,
            candidate_keywords=candidate_keywords,
            output_schema=output_schema
        )

        user_input = {
            "type": "input",
            "name": "测试输入",
            "description": "噪音过滤测试",
            "items": sections
        }

        print(f"✅ 提示词构建成功")
        print(f"   SYSTEM 长度: {len(system_prompt)} 字符")
        print(f"   USER 长度: {len(json.dumps(user_input, ensure_ascii=False))} 字符")

    except Exception as e:
        print(f"❌ 提示词构建失败: {e}")
        return {"error": str(e)}

    # 5. 调用 LLM
    print(f"\n 调用 LLM 进行提取...")
    try:
        from dataflow.core.ai.models import LLMMessage, LLMRole

        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMRole.USER, content=json.dumps(user_input, ensure_ascii=False))
        ]

        # 定义响应 schema
        response_schema = {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "content": {"type": "string"},
                            "category": {"type": "string"},
                            "references": {"type": "array", "items": {"type": "string"}},
                            "entities": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string"},
                                        "name": {"type": "string"},
                                        "description": {"type": "string"}
                                    },
                                    "required": ["type", "name"]
                                }
                            },
                            "is_valid": {"type": "boolean"}
                        },
                        "required": ["title", "content", "is_valid"]
                    }
                }
            },
            "required": ["items"]
        }

        result = await llm_client.chat_with_schema(
            messages=messages,
            response_schema=response_schema,
            temperature=0.3
        )

        items = result.get("items", [])
        print(f"✅ LLM 调用成功")
        print(f"   提取事项数: {len(items)}")

    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

    # 6. 分析结果
    print(f"\n结果分析:")
    print(f"{'-'*80}")

    valid_items = []
    invalid_items = []

    for item in items:
        if item.get("is_valid", True):
            valid_items.append(item)
        else:
            invalid_items.append(item)

    print(f"\n有效事项: {len(valid_items)} 个")
    for i, item in enumerate(valid_items, 1):
        title = item.get("title", "")[:50]
        content_preview = item.get("content", "")[:80]
        print(f"   {i}. {title}")
        print(f"      内容: {content_preview}...")

    print(f"\n❌ 过滤事项: {len(invalid_items)} 个")
    for i, item in enumerate(invalid_items[:10], 1):  # 只显示前10个
        title = item.get("title", "")[:50]
        print(f"   {i}. {title}")

    if len(invalid_items) > 10:
        print(f"   ... 还有 {len(invalid_items) - 10} 个被过滤")

    # 7. 特定噪音检查
    print(f"\n🔍 噪音过滤检查:")
    noise_keywords = [
        "新浪首页", "新浪新闻客户端", "用户操作入口",
        "点击查看", "推荐阅读", "阅读排行榜",
        "投资热点", "加载中", "我的收藏"
    ]

    filtered_noises = []
    for item in invalid_items:
        title = item.get("title", "")
        for keyword in noise_keywords:
            if keyword in title:
                filtered_noises.append(keyword)
                break

    if filtered_noises:
        print(f"成功过滤的噪音: {', '.join(set(filtered_noises))}")
    else:
        print(f"⚠️ 未检测到典型噪音被过滤")

    # 返回统计
    return {
        "version": version_name,
        "total": len(items),
        "valid": len(valid_items),
        "invalid": len(invalid_items),
        "valid_items": valid_items,
        "invalid_items": invalid_items,
        "filtered_noises": filtered_noises
    }


async def main():
    """主测试函数"""
    print("="*80)
    print("提示词对比测试 - 噪音过滤效果")
    print("="*80)
    print(f"\n测试文件: {TEST_FILE_PATH}")
    print(f"LLM 模型: {LLM_MODEL}")
    print(f"LLM 地址: {LLM_BASE_URL}")

    # 检查测试文件是否存在
    if not Path(TEST_FILE_PATH).exists():
        print(f"\n❌ 测试文件不存在: {TEST_FILE_PATH}")
        return

    # 测试原版提示词
    result_v1 = await test_prompt_extraction(
        test_file=TEST_FILE_PATH,
        prompt_file=PROMPT_V1,
        version_name="原版(v1)"
    )

    # 等待一下避免 API 限流
    await asyncio.sleep(2)

    # 测试增强版提示词
    result_v2 = await test_prompt_extraction(
        test_file=TEST_FILE_PATH,
        prompt_file=PROMPT_V2,
        version_name="增强版(v2)"
    )

    # 对比结果
    print(f"\n{'='*80}")
    print(f"对比结果")
    print(f"{'='*80}\n")

    if "error" in result_v1:
        print(f"原版测试失败: {result_v1['error']}")
    elif "error" in result_v2:
        print(f"增强版测试失败: {result_v2['error']}")
    else:
        print(f"{'指标':<20} {'原版(v1)':<15} {'增强版(v2)':<15} {'对比':<15}")
        print(f"{'-'*80}")

        # 总事项数
        total_v1 = result_v1.get("total", 0)
        total_v2 = result_v2.get("total", 0)
        print(f"{'总提取事项':<20} {total_v1:<15} {total_v2:<15} {total_v2 - total_v1:+d}")

        # 有效事项
        valid_v1 = result_v1.get("valid", 0)
        valid_v2 = result_v2.get("valid", 0)
        print(f"{'有效事项':<20} {valid_v1:<15} {valid_v2:<15} {valid_v2 - valid_v1:+d}")

        # 过滤事项
        invalid_v1 = result_v1.get("invalid", 0)
        invalid_v2 = result_v2.get("invalid", 0)
        improvement = invalid_v2 - invalid_v1
        print(f"{'过滤事项':<20} {invalid_v1:<15} {invalid_v2:<15} {improvement:+d}")

        # 过滤率
        rate_v1 = (invalid_v1 / total_v1 * 100) if total_v1 > 0 else 0
        rate_v2 = (invalid_v2 / total_v2 * 100) if total_v2 > 0 else 0
        print(f"{'过滤率':<20} {rate_v1:.1f}%{'':<10} {rate_v2:.1f}%{'':<10} {rate_v2 - rate_v1:+.1f}%")

        # 噪音过滤
        noises_v1 = len(result_v1.get("filtered_noises", []))
        noises_v2 = len(result_v2.get("filtered_noises", []))
        print(f"{'典型噪音过滤':<20} {noises_v1:<15} {noises_v2:<15} {noises_v2 - noises_v1:+d}")

        print(f"\n{'='*80}")
        print(f"💡 结论")
        print(f"{'='*80}\n")

        if improvement > 0:
            print(f"✅ 增强版效果更好！")
            print(f"   - 多过滤了 {improvement} 个噪音事项")
            print(f"   - 过滤率提升 {rate_v2 - rate_v1:.1f}%")
            if noises_v2 > noises_v1:
                print(f"   - 典型噪音识别增加 {noises_v2 - noises_v1} 个")
        elif improvement == 0:
            print(f"⚠️ 两个版本过滤效果相同")
        else:
            print(f"❌ 增强版效果更差，过滤减少了 {-improvement} 个")

        print(f"\n建议:")
        if improvement > 5:
            print(f"  → 建议使用增强版提示词")
        elif improvement > 0:
            print(f"  → 增强版略有提升，可以考虑使用")
        else:
            print(f"  → 建议继续使用原版提示词")

    print(f"\n{'='*80}")
    print(f"测试完成！")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
