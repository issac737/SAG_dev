#!/usr/bin/env python3
"""
多源搜索脚本

支持输入多个 source_config_id 进行搜索，展示完整的搜索流程结果。
"""

import asyncio
import sys
from typing import List, Optional

from dataflow import DataFlowEngine
from dataflow.modules.search.config import (
    SearchConfig,
    RecallConfig,
    ExpandConfig,
    RerankConfig,
    RerankStrategy,
)


async def search_with_multiple_sources(
    query: str,
    source_config_ids: List[str],
    top_k: int = 10,
    show_details: bool = True,
):
    """
    使用多个源进行搜索

    Args:
        query: 查询关键词
        source_config_ids: 源ID列表
        top_k: 返回结果数量
        show_details: 是否显示详细信息
    """
    print(f"\n{'='*60}")
    print(f"🔍 多源搜索")
    print(f"{'='*60}")
    print(f"查询: {query}")
    print(f"源ID: {', '.join(source_config_ids)}")
    print(f"期望结果数: {top_k}")
    print(f"{'='*60}\n")

    try:
        # 使用第一个 source_config_id 创建引擎
        primary_source_config_id = source_config_ids[0]
        engine = DataFlowEngine(source_config_id=primary_source_config_id)

        # 构建搜索配置（使用完整的 SearchConfig，支持 source_config_ids）
        search_config = SearchConfig(
            query=query,
            source_config_ids=source_config_ids,  # 传递多源列表
            # Recall 配置
            recall=RecallConfig(
                use_fast_mode=False,  # 使用完整模式
                vector_top_k=top_k,
                max_entities=20,
                max_events=50,
                final_entity_count=10,
            ),
            # Expand 配置
            expand=ExpandConfig(
                enabled=True,
                max_hops=2,
                entities_per_hop=5,
            ),
            # Rerank 配置
            rerank=RerankConfig(
                strategy=RerankStrategy.PAGERANK,
                score_threshold=0.5,
                max_results=top_k,
            ),
        )

        print("⏳ 正在执行搜索...")
        print("   阶段1: Recall (实体召回)")
        print("   阶段2: Expand (图扩展)")
        print("   阶段3: Rerank (重排序)")
        print()

        # 执行搜索
        await engine.search_async(search_config)

        # 获取结果
        result = engine.get_result()

        if not result.search_result:
            print("❌ 搜索失败：未获取到结果")
            return

        if result.search_result.status != "success":
            print(f"❌ 搜索失败：{result.search_result.error}")
            return

        # 显示搜索统计
        search_stats = result.search_result.stats or {}
        matched_count = search_stats.get("matched_count", 0)
        print(f"\n✅ 搜索完成！")
        print(f"   匹配事项数量: {matched_count}")
        print(f"   执行时间: {result.search_result.duration:.2f}秒")

        # 显示线索信息
        if show_details:
            clues = search_stats.get("clues", [])
            if clues:
                print(f"\n📋 搜索线索: {len(clues)} 条")
                # 统计各阶段线索
                stage_counts = {}
                for clue in clues:
                    stage = clue.get("stage", "unknown")
                    stage_counts[stage] = stage_counts.get(stage, 0) + 1

                for stage, count in sorted(stage_counts.items()):
                    print(f"   - {stage}: {count} 条")

        # 显示事项列表
        if result.search_result.data_full:
            print(f"\n📄 搜索结果:")
            print(f"{'-'*60}")

            for i, event in enumerate(result.search_result.data_full, 1):
                print(f"\n[{i}] {event.get('title', 'N/A')}")
                print(f"    ID: {event.get('id', 'N/A')}")
                print(f"    摘要: {event.get('summary', 'N/A')[:100]}...")

                if show_details:
                    content = event.get('content', '')
                    if content:
                        print(f"    内容: {content[:150]}...")

            print(f"\n{'-'*60}")
        else:
            print("\n⚠️ 未找到匹配的事项")

        # 显示所有日志
        if show_details and result.logs:
            print(f"\n📝 执行日志:")
            print(f"{'-'*60}")
            for log in result.logs[-10:]:  # 只显示最后10条
                print(f"[{log.stage}] {log.level}: {log.message}")
            print(f"{'-'*60}")

    except Exception as e:
        print(f"\n❌ 搜索过程中发生错误:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


def get_user_input() -> tuple[str, List[str], int]:
    """
    获取用户输入

    Returns:
        (query, source_config_ids, top_k)
    """
    print("\n" + "="*60)
    print("多源搜索配置")
    print("="*60)

    # 获取查询
    query = input("\n请输入查询关键词: ").strip()
    if not query:
        query = "AI技术"
        print(f"   使用默认查询: {query}")

    # 获取源ID
    print("\n请输入源ID（支持多个，用逗号分隔）:")
    source_input = input("   源ID: ").strip()

    if not source_input:
        # 尝试从环境或其他地方获取示例源ID
        print("   ⚠️  未提供源ID，尝试使用默认值...")
        # 这里可以硬编码一些示例，或从数据库查询
        # 为了演示，我们使用一个示例
        print("   请手动输入至少一个有效的 source_config_id")
        return get_user_input()

    # 解析多个源ID
    source_config_ids = [sid.strip() for sid in source_input.split(",") if sid.strip()]

    if not source_config_ids:
        print("   ❌ 未提供有效的源ID")
        return get_user_input()

    # 获取期望结果数
    try:
        top_k_input = input(f"\n期望返回结果数 (默认10): ").strip()
        top_k = int(top_k_input) if top_k_input else 10
    except ValueError:
        top_k = 10
        print(f"   使用默认结果数: {top_k}")

    return query, source_config_ids, top_k


async def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 DataFlow 多源搜索工具")
    print("="*60)
    print("本工具支持在多个数据源中进行智能搜索")
    print("功能: Recall → Expand → Rerank")
    print()

    try:
        # 获取用户输入
        query, source_config_ids, top_k = get_user_input()

        # 执行搜索
        await search_with_multiple_sources(
            query=query,
            source_config_ids=source_config_ids,
            top_k=top_k,
            show_details=True,
        )

    except KeyboardInterrupt:
        print("\n\n⏹️  搜索已取消")
    except Exception as e:
        print(f"\n❌ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n👋 感谢使用 DataFlow 多源搜索工具！\n")


if __name__ == "__main__":
    # 检查是否提供了命令行参数
    if len(sys.argv) > 1:
        # 命令行模式
        query = sys.argv[1]
        source_config_ids = sys.argv[2:] if len(sys.argv) > 2 else []

        if not source_config_ids:
            print("❌ 错误：需要提供至少一个 source_config_id")
            print(f"   用法: {sys.argv[0]} <查询> <source_config_id1> <source_config_id2> ...")
            sys.exit(1)

        top_k = 10
        asyncio.run(
            search_with_multiple_sources(
                query=query,
                source_config_ids=source_config_ids,
                top_k=top_k,
                show_details=True,
            )
        )
    else:
        # 交互式模式
        asyncio.run(main())
