"""
AI 信息提取示例

展示如何使用 AI 从文章片段中提取事项(Events)和实体(Entities)
使用带重试的 JSON 输出模式确保稳定性
"""

import asyncio
import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataflow.core.ai.factory import create_llm_client
from dataflow.core.ai.models import LLMMessage, LLMRole
from dataflow.exceptions import LLMError
from dataflow.utils import setup_logging


# ============================================================================
# 示例文章数据
# ============================================================================

SAMPLE_ARTICLES = [
    """
      2024年3月15日，OpenAI在旧金山举办了sophnet/Qwen3-30B-A3B-Thinking-2507发布会。CEO Sam Altman宣布，
      新版本在多项基准测试中超越了GPT-3.5，特别是在逻辑推理和代码生成方面。
      微软作为主要投资方，将sophnet/Qwen3-30B-A3B-Thinking-2507集成到Azure云服务中。发布会结束后，
      OpenAI团队在Twitter上分享了技术细节，引发了AI社区的广泛讨论。
    """,
    """
      李明是一位资深Python开发者，他在2024年1月加入了字节跳动的AI实验室。
      他的主要工作是优化推荐算法，使用PyTorch框架开发深度学习模型。
      在北京办公室，他与团队成员王芳、张伟合作，共同负责用户画像系统的升级。
      项目预计在今年6月完成，届时将服务超过5000万用户。
    """,
    """
      苹果公司计划在2024年秋季发布iPhone 16系列。据知情人士透露，
      新款手机将搭载A18芯片，支持更强大的AI功能。库克在最近的财报会议上表示，
      苹果正在大力投资生成式AI技术。此外，苹果还与台积电签署了新的供应协议，
      确保芯片的稳定供应。发布会预计在9月的加州总部举行。
    """,
]


# ============================================================================
# JSON Schema 定义
# ============================================================================

# 事项提取的 Schema
EVENT_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "description": "从文本中提取的事项列表",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "事项标题（简短描述）"},
                    "description": {"type": "string", "description": "事项详细描述"},
                    "time": {"type": "string", "description": "事项发生时间（如果有）"},
                    "location": {"type": "string", "description": "事项发生地点（如果有）"},
                    "participants": {
                        "type": "array",
                        "description": "参与的人员或组织",
                        "items": {"type": "string"},
                    },
                    "category": {
                        "type": "string",
                        "description": "事项类别（如：会议、发布、合作等）",
                    },
                },
                "required": ["title", "description"],
            },
        },
        "entities": {
            "type": "array",
            "description": "从文本中提取的实体列表",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "实体名称"},
                    "type": {
                        "type": "string",
                        "description": "实体类型（person/organization/location/product/technology等）",
                    },
                    "description": {"type": "string", "description": "实体描述或上下文"},
                    "metadata": {
                        "type": "object",
                        "description": "实体的额外元数据",
                        "properties": {
                            "role": {"type": "string"},
                            "affiliation": {"type": "string"},
                            "date": {"type": "string"},
                        },
                    },
                },
                "required": ["name", "type"],
            },
        },
    },
    "required": ["events", "entities"],
}


# ============================================================================
# 示例 1: 基础事项和实体提取
# ============================================================================


async def example_basic_extraction():
    """示例 1: 从文章中提取事项和实体"""
    print("\n" + "=" * 70)
    print("示例 1: 基础事项和实体提取")
    print("=" * 70)

    # 创建带重试的客户端
    client = create_llm_client(with_retry=True)

    article = SAMPLE_ARTICLES[0]
    print(f"\n文章内容:\n{article.strip()}\n")

    # 构建提示词
    system_prompt = """你是一个专业的信息提取助手。
你的任务是从给定的文本中提取关键事项(Events)和实体(Entities)。

事项提取要求:
- 识别文本中的重要事件、活动、会议、发布等
- 提取时间、地点、参与者等关键信息
- 对事项进行分类

实体提取要求:
- 识别人名、组织名、地点、产品、技术等
- 标注实体类型
- 提取实体的相关描述和元数据

请严格按照JSON Schema格式返回结果。"""

    user_prompt = f"请从以下文章中提取事项和实体:\n\n{article}"

    messages = [
        LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
        LLMMessage(role=LLMRole.USER, content=user_prompt),
    ]

    try:
        # 使用带重试的 JSON 输出模式
        result = await client.chat_with_schema(
            messages,
            response_schema=EVENT_EXTRACTION_SCHEMA,
            temperature=0.3,  # 低温度以获得更稳定的输出
            max_tokens=2000,
        )

        print("提取结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 统计信息
        print(f"\n统计:")
        print(f"  事项数量: {len(result.get('events', []))}")
        print(f"  实体数量: {len(result.get('entities', []))}")

        # 显示提取的事项
        print(f"\n提取的事项:")
        for i, event in enumerate(result.get("events", []), 1):
            print(f"  {i}. {event['title']}")
            print(f"     时间: {event.get('time', '未指定')}")
            print(f"     地点: {event.get('location', '未指定')}")
            print(f"     参与者: {', '.join(event.get('participants', []))}")

        # 显示提取的实体
        print(f"\n提取的实体:")
        for i, entity in enumerate(result.get("entities", []), 1):
            print(f"  {i}. {entity['name']} ({entity['type']})")
            if entity.get("description"):
                print(f"     描述: {entity['description']}")

        return True

    except LLMError as e:
        print(f"❌ 提取失败: {e}")
        return False


# ============================================================================
# 示例 2: 批量提取
# ============================================================================


async def example_batch_extraction():
    """示例 2: 批量处理多篇文章"""
    print("\n" + "=" * 70)
    print("示例 2: 批量提取多篇文章的事项和实体")
    print("=" * 70)

    client = create_llm_client(with_retry=True)

    all_results = []

    for idx, article in enumerate(SAMPLE_ARTICLES, 1):
        print(f"\n处理文章 {idx}/{len(SAMPLE_ARTICLES)}...")
        print(f"文章片段: {article.strip()[:100]}...\n")

        messages = [
            LLMMessage(
                role=LLMRole.SYSTEM,
                content="你是信息提取专家。从文本中提取所有重要的事项和实体，包括人物、组织、地点、产品、时间等。",
            ),
            LLMMessage(role=LLMRole.USER, content=f"提取以下文章中的事项和实体:\n\n{article}"),
        ]

        try:
            result = await client.chat_with_schema(
                messages,
                response_schema=EVENT_EXTRACTION_SCHEMA,
                temperature=0.2,
                max_tokens=2000,
            )

            all_results.append(
                {
                    "article_id": idx,
                    "article_preview": article.strip()[:80] + "...",
                    "extraction": result,
                }
            )

            print(f"✓ 提取成功: {len(result['events'])} 个事项, {len(result['entities'])} 个实体")

        except LLMError as e:
            print(f"❌ 提取失败: {e}")
            all_results.append(
                {
                    "article_id": idx,
                    "article_preview": article.strip()[:80] + "...",
                    "error": str(e),
                }
            )

        # 避免速率限制
        await asyncio.sleep(1)

    # 汇总统计
    print("\n" + "=" * 70)
    print("批量提取汇总:")
    print("=" * 70)

    total_events = 0
    total_entities = 0
    success_count = 0

    for result in all_results:
        if "extraction" in result:
            events = len(result["extraction"]["events"])
            entities = len(result["extraction"]["entities"])
            total_events += events
            total_entities += entities
            success_count += 1
            print(f"\n文章 {result['article_id']}: {events} 事项, {entities} 实体")
        else:
            print(f"\n文章 {result['article_id']}: ❌ 失败")

    print(f"\n总计:")
    print(f"  成功: {success_count}/{len(SAMPLE_ARTICLES)}")
    print(f"  总事项: {total_events}")
    print(f"  总实体: {total_entities}")

    return success_count == len(SAMPLE_ARTICLES)


# ============================================================================
# 示例 3: 实体关系提取
# ============================================================================


async def example_entity_relationship_extraction():
    """示例 3: 提取实体之间的关系"""
    print("\n" + "=" * 70)
    print("示例 3: 提取实体之间的关系")
    print("=" * 70)

    client = create_llm_client(with_retry=True)

    # 定义关系提取的 Schema
    relationship_schema = {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "type": {"type": "string"}},
                    "required": ["name", "type"],
                },
            },
            "relationships": {
                "type": "array",
                "description": "实体之间的关系",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "源实体名称"},
                        "target": {"type": "string", "description": "目标实体名称"},
                        "relation_type": {"type": "string", "description": "关系类型"},
                        "description": {"type": "string", "description": "关系描述"},
                    },
                    "required": ["source", "target", "relation_type"],
                },
            },
        },
        "required": ["entities", "relationships"],
    }

    article = SAMPLE_ARTICLES[1]
    print(f"\n文章内容:\n{article.strip()}\n")

    messages = [
        LLMMessage(
            role=LLMRole.SYSTEM,
            content="""你是实体关系提取专家。
            提取文本中的实体及其关系，包括:
            - 工作关系 (works_for, collaborates_with)
            - 位置关系 (located_in, works_at)
            - 使用关系 (uses, develops)
            - 时间关系 (joined_on, scheduled_for)
          """,
        ),
        LLMMessage(role=LLMRole.USER, content=f"提取以下文本中的实体及其关系:\n\n{article}"),
    ]

    try:
        result = await client.chat_with_schema(
            messages,
            response_schema=relationship_schema,
            temperature=0.2,
            max_tokens=10000,
        )

        print("提取结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        return True

    except LLMError as e:
        print(f"❌ 提取失败: {e}")
        return False


# ============================================================================
# 示例 4: 灵活提取（无 Schema）
# ============================================================================


async def example_flexible_extraction():
    """示例 4: 灵活提取（不使用固定 Schema）"""
    print("\n" + "=" * 70)
    print("示例 4: 灵活提取（不使用固定 Schema）")
    print("=" * 70)

    client = create_llm_client(with_retry=True)

    article = SAMPLE_ARTICLES[2]
    print(f"\n文章内容:\n{article.strip()}\n")

    messages = [
        LLMMessage(
            role=LLMRole.SYSTEM,
            content="""你是信息提取助手。
              从文本中提取所有有价值的信息，以JSON格式返回。
              可以包含任何你认为重要的字段，比如:
              - 主题/话题
              - 关键人物
              - 公司/组织
              - 产品
              - 时间信息
              - 技术
              - 数据/指标
              等等，根据文本内容灵活调整。
            """,
        ),
        LLMMessage(role=LLMRole.USER, content=f"提取文章中的重要信息:\n\n{article}"),
    ]

    try:
        # 不传 response_schema，只验证 JSON 格式
        result = await client.chat_with_schema(
            messages,
            temperature=0.3,
            max_tokens=2000,
        )

        print("提取结果 (灵活格式):")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        return True

    except LLMError as e:
        print(f"❌ 提取失败: {e}")
        return False


# ============================================================================
# 主函数
# ============================================================================


async def main():
    """运行所有示例"""
    # 初始化日志系统
    setup_logging()

    print("\n" + "=" * 70)
    print("AI 信息提取示例 - 事项和实体提取")
    print("=" * 70)

    examples = [
        # ("基础事项和实体提取", example_basic_extraction),
        # ("批量提取", example_batch_extraction),
        # ("实体关系提取", example_entity_relationship_extraction),
        ("灵活提取（无固定Schema）", example_flexible_extraction),
    ]

    results = []

    for name, example_func in examples:
        try:
            result = await example_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ 示例失败: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

        # 示例间隔
        await asyncio.sleep(2)

    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print(f"\n✓ 所有示例运行成功！")
    else:
        print(f"\n⚠ 部分示例失败")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
