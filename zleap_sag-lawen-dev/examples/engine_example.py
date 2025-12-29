"""
DataFlow 引擎使用示例

展示如何使用 DataFlow 引擎的各种功能
"""

import asyncio
from pathlib import Path

from dataflow import (
    DataFlowEngine,
    ExtractBaseConfig,
    LoadBaseConfig,
    ModelConfig,
    OutputConfig,
    OutputMode,
    SearchBaseConfig,
    TaskConfig,
)


# ============================================================================
# 示例 1: 独立执行Load
# ============================================================================


def example_load_only():
    """只加载文档，不提取"""
    print("\n=== 示例1：只加载文档 ===\n")

    engine = DataFlowEngine(source_config_id="my-source")
    engine.load(LoadBaseConfig(path="docs/article.md"))

    result = engine.get_result()

    # 输出ID列表
    if result.load_result:
        sections_ids = result.load_result.data_ids
        print(f"✓ 加载了 {len(sections_ids)} 个片段")
        print(f"片段ID: {sections_ids}")


# ============================================================================
# 示例 2: 独立执行Extract
# ============================================================================


def example_extract_only():
    """只提取事项（文档已加载）"""
    print("\n=== 示例2：只提取事项 ===\n")

    engine = DataFlowEngine(source_config_id="my-source")

    # 假设 article_id 已存在
    engine._article_id = "677eb2ce-013b-43f3-aa7c-43eddc385a14"
    engine.extract(ExtractBaseConfig(parallel=True))

    result = engine.get_result()

    if result.extract_result:
        events = result.extract_result.data_full
        print(f"✓ 提取了 {len(events)} 个事项")
        for event in events[:3]:  # 只显示前3个
            print(f"  - {event['title']}")


# ============================================================================
# 示例 3: 独立执行Search
# ============================================================================


def example_search_only():
    """只搜索事项"""
    print("\n=== 示例3：只搜索事项 ===\n")

    engine = DataFlowEngine(source_config_id="my-source")
    engine.search(SearchBaseConfig(query="查找AI相关内容", top_k=10))

    result = engine.get_result()

    if result.search_result:
        # 只输出ID
        matched_ids = result.search_result.data_ids
        print(f"✓ 找到 {len(matched_ids)} 个匹配事项")
        print(f"匹配事项ID: {matched_ids}")


# ============================================================================
# 示例 4: 链式调用
# ============================================================================


def example_chaining():
    """链式调用三个阶段"""
    print("\n=== 示例4：链式调用 ===\n")

    result = (
        DataFlowEngine(source_config_id="my-source")
        .load(LoadBaseConfig(path="docs/article.md"))
        .extract(ExtractBaseConfig(parallel=True, max_concurrency=3))
        .search(SearchBaseConfig(query="查找技术相关内容", top_k=5))
        .get_result()
    )

    print(f"✓ 完整流程执行完成")
    if result.load_result:
        print(f"  - Sections: {len(result.load_result.data_ids)}")
    if result.extract_result:
        print(f"  - Events: {len(result.extract_result.data_ids)}")
    if result.search_result:
        print(f"  - Matched: {len(result.search_result.data_ids)}")


# ============================================================================
# 示例 5: 统一配置
# ============================================================================


def example_unified_config():
    """使用统一配置运行"""
    print("\n=== 示例5：统一配置 ===\n")

    task_config = TaskConfig(
        task_name="完整流程",
        # source_config_id="test-search-mode-02",
        load=LoadBaseConfig(path="docs/article.md"),
        extract=ExtractBaseConfig(parallel=True),
        search=SearchBaseConfig(query="查找AI辅助诊断系统的应用跟穿戴设备等"),
        output=OutputConfig(
            mode=OutputMode.ID_ONLY,  # 只输出ID
            # mode=OutputMode.FULL,  # 输出完整内容
            # print_logs=True,  # 打印日志
            # include_logs=True,  # 但保存日志
        ),
    )

    engine = DataFlowEngine(task_config=task_config)
    result = engine.run()

    # 输出只包含ID
    output = engine.output()
    print(f"✓ 任务完成: {result.status.value}")
    if output:
        # print(f"\n输出预览:\n{output[:5000]}...")
        print(f"\n输出预览:\n{output}...")


# ============================================================================
# 示例 6: 灵活组合
# ============================================================================


def example_flexible():
    """灵活组合：只执行Load和Extract"""
    print("\n=== 示例6：灵活组合 ===\n")

    task_config = TaskConfig(
        task_name="部分流程",
        source_config_id="my-source",
        load=LoadBaseConfig(path="docs/article.md"),
        extract=ExtractBaseConfig(parallel=True),
        search=None,  # 跳过搜索
        output=OutputConfig(mode=OutputMode.FULL),
    )

    engine = DataFlowEngine(task_config=task_config)
    result = engine.run()

    # 输出完整内容
    if result.extract_result:
        print(f"✓ 提取了 {len(result.extract_result.data_full)} 个事项")
        for event in result.extract_result.data_full[:2]:
            print(f"\n  标题: {event['title']}")
            print(f"  摘要: {event.get('summary', '无')[:100]}")


# ============================================================================
# 示例 7: 异步执行
# ============================================================================


async def example_async():
    """异步执行"""
    print("\n=== 示例7：异步执行 ===\n")

    engine = DataFlowEngine(source_config_id="my-source")

    # 异步加载
    await engine.load_async(LoadBaseConfig(path="docs/article.md"))

    # 异步提取
    await engine.extract_async(ExtractBaseConfig(parallel=True))

    result = engine.get_result()

    print(f"✓ 异步执行完成")
    print(f"  - 耗时: {result.duration:.2f}秒" if result.duration else "  - 耗时: N/A")


# ============================================================================
# 示例 8: 高级配置
# ============================================================================


def example_advanced():
    """高级配置 - 展示配置可分可合"""
    print("\n=== 示例8：高级配置(配置可分可合) ===\n")

    model_config = ModelConfig(
        api_key="sk-your-api-key",
        model="sophnet/Qwen3-30B-A3B-Thinking-2507",
        base_url="https://api.your-proxy.com/v1",  # 中转API
        timeout=120,
        max_retries=3,
        temperature=0.2,
    )

    task_config = TaskConfig(
        task_name="高级任务",
        source_name="我的知识库",
        background="这是技术文档集合，重点关注技术实现和架构设计",  # 全局背景
        load=LoadBaseConfig(
            path="docs/",
            recursive=True,
            pattern="*.md",
        ),
        extract=ExtractBaseConfig(
            parallel=True,
            max_concurrency=5,
            max_sections=20,
        ),
        output=OutputConfig(format="json", export_path=Path("output/result.json"), pretty=True),
    )

    engine = DataFlowEngine(task_config=task_config, model_config=model_config)
    result = engine.run()

    print(f"✓ 任务完成: {result.status.value}")
    print(f"  - 统计: {result.stats}")


# ============================================================================
# 示例 9: 错误处理
# ============================================================================


def example_error_handling():
    """错误处理"""
    print("\n=== 示例9：错误处理 ===\n")

    task_config = TaskConfig(
        task_name="容错任务",
        load=LoadBaseConfig(path="docs/article.md"),
        fail_fast=False,  # 不快速失败
    )

    try:
        engine = DataFlowEngine(task_config=task_config)
        result = engine.run()

        if result.is_success():
            print("✓ 任务成功")
        else:
            print("✗ 任务失败")
            print(f"错误: {result.error}")

            # 查看错误日志
            print("\n错误日志:")
            for log in result.logs:
                if log.level.value == "error":
                    print(f"  {log}")

    except Exception as e:
        print(f"✗ 任务异常: {e}")


# ============================================================================
# 示例 10: 普通模式搜索
# ============================================================================


def example_normal_search():
    """普通模式搜索 - 使用SearchConfig"""
    print("\n=== 示例10：普通模式搜索 ===\n")

    # 导入搜索需要的配置
    from dataflow.modules.search import SearchConfig, SearchMode

    engine = DataFlowEngine(source_config_id="test-search-mode-02")

    # 使用SearchConfig进行普通模式搜索
    config = SearchConfig(
        query="脑机接口技术",
        source_config_id="test-search-mode-02",
        mode=SearchMode.NORMAL,
        top_k=5,
        # 搜索参数
        key_similarity_threshold=0.7,
        event_similarity_threshold=0.6,
        max_keys=20,
        final_key_threshold=0.5,
        top_n_keys=10,
    )

    engine.search(config)
    result = engine.get_result()

    if result.search_result:
        matched_ids = result.search_result.data_ids
        print(f"✓ 普通模式找到 {len(matched_ids)} 个匹配事项")
        print(f"匹配事项ID: {matched_ids}")

        # 如果有完整结果，显示前几个标题
        if hasattr(result.search_result, "data_full") and result.search_result.data_full:
            print("\n搜索结果预览:")
            for i, event in enumerate(result.search_result.data_full[:3], 1):
                print(f"  {i}. {event.get('title', '无标题')}")
    else:
        print("✗ 普通模式搜索未返回结果")


# ============================================================================
# 示例 11: 完整搜索工作流 (推荐)
# ============================================================================


def example_complete_workflow():
    """完整的搜索工作流：Load → Extract → Search（返回事项）"""
    print("\n=== 示例11：完整搜索工作流 (推荐) ===\n")

    print("🚀 开始完整的搜索工作流程...")
    print("   阶段1-2: 使用DataFlow引擎进行Load和Extract")
    print("   阶段3: 使用搜索器进行精准搜索")
    print("=" * 60)

    return _run_complete_workflow()


async def _run_complete_workflow():
    """内部异步函数：执行完整的搜索工作流（返回SourceEvent对象列表）"""
    # 创建新的事件循环，避免循环冲突
    import asyncio

    # 阶段1-2: 使用DataFlow引擎进行Load和Extract
    print("\n📚 阶段1-2: Load + Extract (引擎统一调度)")
    print("-" * 40)
    from datetime import datetime

    # 使用时间戳生成唯一ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source_config_id = f"sag-workflow-demo-{timestamp}"
    engine = DataFlowEngine(source_config_id=source_config_id)
    # engine = DataFlowEngine(source_config_id="sag-workflow-demo")
    # engine = DataFlowEngine()
    try:
        # Load阶段 - 异步加载文档
        print("📂 开始加载文档...")
        await engine.load_async(LoadBaseConfig(path="tests/load/fixtures/LLM_Architecture.md"))
        print("✅ 文档加载完成")
    except Exception as e:
        print(f"❌ 文档加载失败: {e}")
        print("💡 提示: 请确保 docs/SaaS虚拟群聊数据.md 文件存在")
        return []

    try:
        # Extract阶段 - 异步提取事项
        print("🔍 开始提取事项...")
        await engine.extract_async(ExtractBaseConfig(parallel=True, max_concurrency=3))
        print("✅ 事项提取完成")
    except Exception as e:
        print(f"❌ 事项提取失败: {e}")
        print(f"   错误详情: {str(e)}")
        return []

    # 获取引擎结果
    engine_result = engine.get_result()
    load_count = len(engine_result.load_result.data_ids) if engine_result.load_result else 0
    extract_count = (
        len(engine_result.extract_result.data_ids) if engine_result.extract_result else 0
    )

    print(f"📊 处理统计:")
    print(f"   - 文档片段: {load_count} 个")
    print(f"   - 提取事项: {extract_count} 个")

    if extract_count == 0:
        print("⚠️  没有提取到事项，跳过搜索阶段")
        return []

    # 阶段3: 搜索
    print(f"\n🔍 阶段3: 搜索 (SearchConfig)")
    print("-" * 40)

    # 导入搜索需要的组件
    from dataflow.core.ai.factory import create_llm_client
    from dataflow.core.prompt.manager import PromptManager
    from dataflow.modules.search import EventSearcher, SearchConfig, SearchMode

    try:
        # 初始化搜索器
        print("🔧 初始化搜索器...")
        llm_client = create_llm_client()
        prompt_manager = PromptManager()
        searcher = EventSearcher(llm_client, prompt_manager)
        print("✅ 搜索器初始化完成")

        # 配置SAG搜索
        print("\n⚙️  SAG搜索配置:")
        sag_config = SearchConfig(
            query="大模型应用",  # 复杂查询，发挥SAG优势
            source_config_id=source_config_id,  # 使用与引擎相同的source_config_id
            mode=SearchMode.NORMAL,
            top_k=8,
            # 搜索参数
            key_similarity_threshold=0.4,  # Key发现阈值
            event_similarity_threshold=0.65,  # Event匹配阈值
            max_keys=25,  # 最大Key数量
            max_events=60,  # 最大Event数量
            final_key_threshold=0.45,  # 最终Key筛选阈值
            top_n_keys=12,  # 返回Top-N Keys
            vector_k=15,  # 向量搜索范围
            stage3_top_n_page=10,
            stage3_vector_k=15,
        )

        # 显示配置参数
        print(f"   📝 查询: {config.query}")
        print(f"   🎯 Key相似度阈值: {config.key_similarity_threshold}")
        print(f"   🎯 Event相似度阈值: {config.event_similarity_threshold}")
        print(f"   🔢 最大Keys: {config.max_keys}")
        print(f"   🔢 最终Keys: {config.top_n_keys}")

        # 执行搜索
        print(f"\n🚀 开始搜索...")

        results = await searcher.search(config)

        # 显示搜索结果
        print(f"✅ 搜索完成，找到 {len(results)} 个事项")

        if results:

            print(f"\n📋 === 事项预览 ===")
            for i, event in enumerate(results, 1):
                print(f"\n【事项 {i}】")
                print(f"  🆔 事项ID: {event.id}")
                print(f"  📌 标题: {event.title}")

                # 显示摘要
                summary = event.summary if event.summary else "N/A"
                if len(summary) > 100:
                    print(f"  📝 摘要: {summary[:100]}...")
                else:
                    print(f"  📝 摘要: {summary}")

                # 显示内容预览
                content = event.content if event.content else "N/A"
                if len(content) > 150:
                    print(f"  📄 内容: {content[:150]}...")
                else:
                    print(f"  📄 内容: {content}")

                # 显示其他信息
                if hasattr(event, "rank"):
                    print(f"  🔢 序号: {event.rank}")
        else:
            print("❌ 搜索未找到匹配结果")
            print("💡 建议: 尝试降低相似度阈值或使用更广泛的查询词")

        # 总结
        print(f"\n" + "=" * 60)
        print(f"🎯 完整工作流总结:")
        print(f"   ✅ Load阶段: {load_count} 个片段")
        print(f"   ✅ Extract阶段: {extract_count} 个事项")
        print(f"   ✅ Search阶段: {len(results)} 个匹配事项")
        print(f"   🏆 总体状态: {'成功' if results else '部分成功'}")

        return results

    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        print("💡 可能原因:")
        print("   - LLM API配置问题 (检查 LLM_API_KEY)")
        print("   - 向量检索服务未启动")
        print("   - 数据库连接问题")
        print("   - 事件循环管理问题")
        import traceback

        print(f"   详细错误: {traceback.format_exc()}")
        return []


# ============================================================================
# 主函数
# ============================================================================


def main():
    """运行示例"""
    print("\n" + "=" * 70)
    print("DataFlow 引擎使用示例")
    print("=" * 70)

    # 注意：实际运行前需要：
    # 1. 配置 LLM API Key
    # 2. 初始化数据库
    # 3. 准备测试文档

    print("\n提示：这些示例展示了 DataFlow 引擎的各种使用方式")
    print("实际运行前请确保：")
    print("  1. 已配置 LLM_API_KEY 环境变量")
    print("  2. 已初始化数据库（运行 scripts/init_database.py）")
    print("  3. 已准备测试文档")

    # 取消注释以运行特定示例
    # example_load_only()
    # example_extract_only()
    # example_search_only()
    # example_chaining()
    # example_unified_config()
    # example_flexible()
    # asyncio.run(example_async())
    # example_advanced()
    # example_error_handling()
    # example_normal_search()  # 普通模式搜索 (示例10)
    asyncio.run(example_complete_workflow())  # 完整工作流
    # 默认运行统一配置示例
    # example_unified_config()


if __name__ == "__main__":
    main()
