"""
SAG 搜索模块测试 (Rerank阶段)

测试 SAGSearcher 的 Rerank 阶段功能，支持两种返回格式：
1. EVENT 模式：返回事项列表（使用 pagerank.py）
2. PARAGRAPH 模式：返回段落列表（使用 pagerank_section.py）

完整的 search() 流程：
  Recall → Expand → Rerank

返回结果说明：

EVENT 模式:
{
    "events": List[SourceEvent],  # 事项对象列表
    "clues": List[Dict],           # 线索列表
    "stats": Dict,                 # 统计信息
    "query": Dict                  # 查询信息
}

PARAGRAPH 模式:
{
    "sections": List[Dict],        # 段落字典列表
    "clues": List[Dict],           # 线索列表
    "stats": Dict,                 # 统计信息
    "query": Dict                  # 查询信息
}
"""

import asyncio
from typing import Any, Dict, List

from dataflow.modules.search.searcher import SAGSearcher
from dataflow.modules.search.config import SearchConfig, ReturnType, RerankStrategy
from dataflow.core.prompt.manager import PromptManager
from dataflow.utils.logger import setup_logging

# 初始化日志系统，确保logger.info()能够输出到终端
# 如需查看更详细的调试信息，可以将 level 改为 "DEBUG"
setup_logging(level="INFO")

# 全局变量
searcher = None
prompt_manager = None


async def init_searcher():
    """初始化搜索器"""
    global searcher, prompt_manager

    if searcher is None:
        # 初始化 PromptManager
        prompt_manager = PromptManager()

        # 初始化 SAGSearcher
        searcher = SAGSearcher(
            prompt_manager=prompt_manager,
            model_config=None  # 使用默认配置
        )

        print("✓ SAGSearcher 初始化完成\n")


async def test_search_events():
    """测试 EVENT 模式 - 返回事项列表"""
    try:
        print("\n" + "="*100)
        print("【测试 1】EVENT 模式 - 返回事项列表")
        print("="*100 + "\n")

        await init_searcher()
        from dataflow.modules.search.config import (
            ReturnType, RecallConfig, ExpandConfig, RerankConfig, RecallMode
        )
        # 配置搜索参数 - PARAGRAPH 模式
        config = SearchConfig(
            query="Qwen3部署方式",
            source_config_id="0ad9b1b9-6640-43e3-9f3b-683feab411be",
            return_type=ReturnType.EVENT,  # 🔑 段落模式
            enable_query_rewrite=False,

           recall=RecallConfig(use_fast_mode=False,vector_top_k=50,max_entities=50,recall_mode=RecallMode.FUZZY,entity_similarity_threshold=0.3,entity_weight_threshold=0.2),
        expand=ExpandConfig(max_hops=5),
        rerank=RerankConfig(max_results=10, score_threshold=0.45, strategy="pagerank",skip_pagerank=True)
        )

        print(f"🔍 查询: '{config.query}'")
        print(f"📊 返回类型: {config.return_type}")
        print(f"📈 策略: {config.rerank.strategy}\n")

        # 执行搜索
        result = await searcher.search(config)

        # 验证返回格式
        assert "events" in result, "❌ 缺少 'events' 字段"
        assert "clues" in result, "❌ 缺少 'clues' 字段"
        assert "stats" in result, "❌ 缺少 'stats' 字段"
        assert "query" in result, "❌ 缺少 'query' 字段"

        events = result["events"]
        clues = result["clues"]
        stats = result["stats"]

        print(f"\n{'='*100}")
        print(f"✅ 搜索完成！返回 {len(events)} 个事项，{len(clues)} 条线索")
        print(f"{'='*100}\n")

        # 显示统计信息
        print("📊 统计信息:")
        print(f"  Recall 召回实体: {stats['recall']['entities_count']}")
        print(f"  Expand 扩展实体: {stats['expand']['entities_count']}")
        print(f"  Rerank 返回事项: {stats['rerank']['events_count']}")
        print(f"  策略: {stats['rerank']['strategy']}")
        print(f"  返回类型: {stats['rerank']['return_type']}\n")

        # 显示事项列表（Top 5）
        if events:
            print("📋 事项列表 (Top 5):")
            print("-" * 100)
            for i, event in enumerate(events[:5], 1):
                print(f"\n【事项 {i}】")
                print(f"  ID: {event.id[:8]}...")
                print(f"  标题: {event.title}")

                summary = event.summary if event.summary else 'N/A'
                if len(summary) > 150:
                    print(f"  摘要: {summary[:150]}...")
                else:
                    print(f"  摘要: {summary}")

                # 显示召回线索（如果有）
                if hasattr(event, 'clues') and event.clues:
                    print(f"  📌 召回线索 ({len(event.clues)}个):")
                    for clue in event.clues[:3]:  # 只显示前3个
                        clue_type = clue.get('type', 'unknown')
                        clue_name = clue.get('name', 'N/A')
                        clue_weight = clue.get('weight', 0.0)

                        # 根据类型选择图标
                        icon = {
                            'query': "🔍",
                            'organization': "🏢",
                            'person': "👤",
                            'location': "📍",
                        }.get(clue_type, "🔖")

                        print(f"    {icon} [{clue_type}] {clue_name[:40]} (权重={clue_weight:.2f})")

            if len(events) > 5:
                print(f"\n  ... 还有 {len(events) - 5} 个事项未显示")
        else:
            print("⚠️  未找到任何事项")

        print("\n" + "=" * 100)
        print("✓ EVENT 模式测试完成")
        print("=" * 100 + "\n")

    except Exception as e:
        print(f"\n❌ 测试执行出错: {e}")
        import traceback
        traceback.print_exc()


async def test_search_sections():
    """测试 PARAGRAPH 模式 - 返回段落列表"""
    try:
        print("\n" + "="*100)
        print("【测试 2-1】PARAGRAPH 模式 - 返回段落列表")
        print("="*100 + "\n")

        await init_searcher()
        from dataflow.modules.search.config import (
            ReturnType, RecallConfig, ExpandConfig, RerankConfig, RecallMode
        )
        # 配置搜索参数 - PARAGRAPH 模式
        config = SearchConfig(
            query="Qwen3部署方式",
            source_config_id="0ad9b1b9-6640-43e3-9f3b-683feab411be",
            return_type=ReturnType.PARAGRAPH,  # 🔑 段落模式

recall=RecallConfig(use_fast_mode=False,vector_top_k=50,max_entities=50,recall_mode=RecallMode.FUZZY,entity_similarity_threshold=0.3,entity_weight_threshold=0.2),
        expand=ExpandConfig(max_hops=3),
        rerank=RerankConfig(max_results=10, score_threshold=0.45, strategy="pagerank")
        )

        print(f"🔍 查询: '{config.query}'")
        print(f"📊 返回类型: {config.return_type}")
        print(f"📈 策略: {config.rerank.strategy}\n")

        # 执行搜索
        result = await searcher.search(config)

        # 验证返回格式
        assert "sections" in result, "❌ 缺少 'sections' 字段"
        assert "clues" in result, "❌ 缺少 'clues' 字段"
        assert "stats" in result, "❌ 缺少 'stats' 字段"
        assert "query" in result, "❌ 缺少 'query' 字段"

        sections = result["sections"]
        clues = result["clues"]
        stats = result["stats"]

        print(f"\n{'='*100}")
        print(f"✅ 搜索完成！返回 {len(sections)} 个段落，{len(clues)} 条线索")
        print(f"{'='*100}\n")

        # 显示统计信息
        print("📊 统计信息:")
        print(f"  Recall 召回实体: {stats['recall']['entities_count']}")
        print(f"  Expand 扩展实体: {stats['expand']['entities_count']}")
        print(f"  Rerank 返回段落: {stats['rerank']['sections_count']}")
        print(f"  策略: {stats['rerank']['strategy']}")
        print(f"  返回类型: {stats['rerank']['return_type']}\n")

        # 显示段落列表（Top 5）
        if sections:
            print("📋 段落列表 (Top 5):")
            print("-" * 100)
            for i, section in enumerate(sections[:5], 1):
                print(f"\n【段落 {i}】")
                print(f"  Section ID: {section.get('section_id', 'N/A')[:8]}...")
                print(f"  Article ID: {section.get('article_id', 'N/A')[:8]}...")
                print(f"  标题: {section.get('heading', '无标题')}")
                print(f"  PageRank: {section.get('pagerank', 0):.6f}")
                print(f"  Weight: {section.get('weight', 0):.4f}")
                print(f"  Score: {section.get('score', 0):.4f}")
                print(f"  来源: {section.get('search_type', 'N/A')}")

                content = section.get('content', '')
                if len(content) > 200:
                    print(f"  内容预览: {content[:200]}...")
                else:
                    print(f"  内容: {content}")

                # 显示关联的事件ID（如果有）
                event_ids = section.get('event_ids', [])
                if event_ids:
                    print(f"  关联事项: {len(event_ids)} 个")
                    for eid in event_ids[:2]:
                        print(f"    - {eid[:8]}...")

                # 显示召回线索（如果有）
                clues_list = section.get('clues', [])
                if clues_list:
                    print(f"  📌 召回线索 ({len(clues_list)}个):")
                    for clue in clues_list[:2]:  # 只显示前2个
                        clue_type = clue.get('type', 'unknown')
                        clue_name = clue.get('name', 'N/A')
                        clue_weight = clue.get('weight', 0.0)
                        print(f"    🔖 [{clue_type}] {clue_name[:40]} (权重={clue_weight:.2f})")

            if len(sections) > 5:
                print(f"\n  ... 还有 {len(sections) - 5} 个段落未显示")
        else:
            print("⚠️  未找到任何段落")

        print("\n" + "=" * 100)
        print("✓ PARAGRAPH 模式测试完成")
        print("=" * 100 + "\n")

    except Exception as e:
        print(f"\n❌ 测试执行出错: {e}")
        import traceback
        traceback.print_exc()


async def test_both_modes():
    """对比测试两种模式"""
    try:
        print("\n" + "="*100)
        print("【测试 3】对比两种返回模式")
        print("="*100 + "\n")

        await init_searcher()

        # 相同的查询参数
        query = "Qwen3部署方式"
        source_config_id = "0ad9b1b9-6640-43e3-9f3b-683feab411be"

        # 测试 EVENT 模式
        print("🔹 测试 EVENT 模式...")
        config_event = SearchConfig(
            query=query,
            source_config_id=source_config_id,
            return_type=ReturnType.EVENT,
            enable_query_rewrite=False,
            rerank__max_results=5,
        )
        result_event = await searcher.search(config_event)

        # 测试 PARAGRAPH 模式
        print("\n🔹 测试 PARAGRAPH 模式...")
        config_section = SearchConfig(
            query=query,
            source_config_id=source_config_id,
            return_type=ReturnType.PARAGRAPH,
            enable_query_rewrite=False,
            rerank__max_results=5,
        )
        result_section = await searcher.search(config_section)

        # 对比结果
        print("\n" + "="*100)
        print("📊 对比结果:")
        print("="*100)

        print(f"\n【EVENT 模式】")
        print(f"  返回键: 'events'")
        print(f"  数量: {len(result_event['events'])} 个事项")
        print(f"  线索数: {len(result_event['clues'])} 条")
        print(f"  数据类型: {type(result_event['events'][0]).__name__ if result_event['events'] else 'N/A'}")

        print(f"\n【PARAGRAPH 模式】")
        print(f"  返回键: 'sections'")
        print(f"  数量: {len(result_section['sections'])} 个段落")
        print(f"  线索数: {len(result_section['clues'])} 条")
        print(f"  数据类型: {type(result_section['sections'][0]).__name__ if result_section['sections'] else 'N/A'}")

        print("\n" + "="*100)
        print("✓ 对比测试完成")
        print("="*100 + "\n")

    except Exception as e:
        print(f"\n❌ 测试执行出错: {e}")
        import traceback
        traceback.print_exc()


# 正确的异步测试执行方式
if __name__ == "__main__":
    try:
        print("\n" + "="*100)
        print("SAG 搜索测试菜单 (Rerank 阶段 - 两种返回格式)")
        print("="*100)
        print("1. 测试 EVENT 模式 - 返回事项列表")
        print("2. 测试 PARAGRAPH 模式 - 返回段落列表")
        print("3. 对比测试两种模式")
        print("4. 运行所有测试")
        print("="*100)

        choice = input("\n请选择测试项 (1-4, 默认为3): ").strip()

        if not choice:
            choice = "3"

        if choice == "1":
            print("\n执行 EVENT 模式测试...")
            asyncio.run(test_search_events())
        elif choice == "2":
            print("\n执行 PARAGRAPH 模式测试...")
            asyncio.run(test_search_sections())
        elif choice == "3":
            print("\n执行对比测试...")
            asyncio.run(test_both_modes())
        elif choice == "4":
            print("\n执行所有测试...")
            asyncio.run(test_search_events())
            asyncio.run(test_search_sections())
            asyncio.run(test_both_modes())
        else:
            print(f"⚠️  无效选择: {choice}")

    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"运行测试时出错: {e}")
        import traceback
        traceback.print_exc()
