#!/usr/bin/env python3
"""
SAG召回模块测试脚本

演示完整的SQL-RAG召回流程：Recall → Expand → Rerank
"""

import asyncio
import argparse
import sys
from pathlib import Path

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from dataflow import DataFlowEngine
from dataflow.modules.search.config import (
    SearchConfig,
    RecallConfig,
    ExpandConfig,
    RerankConfig,
    RerankStrategy,
)


async def test_sag_recall(
    query: str,
    source_config_ids: list[str],
    top_k: int = 10,
    max_hops: int = 2,
    rerank_strategy: str = "pagerank",
    show_clues: bool = True,
):
    """
    执行SAG召回测试

    Args:
        query: 查询文本
        source_config_ids: 信息源ID列表
        top_k: 返回结果数量
        max_hops: 最大扩展跳数
        rerank_strategy: 重排序策略 (pagerank/rrf)
        show_clues: 是否显示搜索线索
    """
    print(f"\n{'='*80}")
    print(f"🔍 SAG召回测试 - SQL-RAG智能检索")
    print(f"{'='*80}")
    print(f"查询: {query}")
    print(f"信息源: {', '.join(source_config_ids)}")
    print(f"参数: top_k={top_k}, max_hops={max_hops}, rerank={rerank_strategy}")
    print(f"{'='*80}\n")

    try:
        # 创建DataFlow引擎
        engine = DataFlowEngine(source_config_id=source_config_ids[0])

        # 构建搜索配置
        search_config = SearchConfig(
            query=query,
            source_config_ids=source_config_ids,
            # Recall配置 - 实体召回
            recall=RecallConfig(
                use_fast_mode=False,  # 使用完整模式
                vector_top_k=30,  # 向量搜索返回30个
                max_entities=50,  # 最大实体数
                max_events=100,  # 最大事项数
                entity_similarity_threshold=0.4,  # 相似度阈值
                final_entity_count=20,  # 最终实体数
            ),
            # Expand配置 - 图扩展
            expand=ExpandConfig(
                enabled=True,
                max_hops=max_hops,  # 最大跳数
                entities_per_hop=15,  # 每跳实体数
                weight_change_threshold=0.001,  # 收敛阈值
            ),
            # Rerank配置 - 重排序
            rerank=RerankConfig(
                strategy=RerankStrategy.PAGERANK if rerank_strategy == "pagerank" else RerankStrategy.RRF,
                score_threshold=0.3,
                max_results=top_k,
            ),
        )

        print("⏳ 开始执行三阶段召回流程...")
        print("   阶段1: Recall (实体召回) - 使用6步复合搜索算法")
        print("   阶段2: Expand (图扩展) - 多跳深度关联发现")
        print("   阶段3: Rerank (重排序) - 使用PageRank/RRF算法")
        print()

        # 执行搜索
        await engine.search_async(search_config)

        # 获取结果
        result = engine.get_result()

        if not result.search_result or result.search_result.status != "success":
            print(f"❌ 搜索失败: {result.search_result.error if result.search_result else '未知错误'}")
            return

        # 显示统计信息
        stats = result.search_result.stats or {}
        matched_count = stats.get("matched_count", 0)
        duration = result.search_result.duration

        print(f"\n✅ 召回完成！")
        print(f"   匹配事项: {matched_count} 个")
        print(f"   总耗时: {duration:.2f} 秒")

        # 显示线索统计
        if show_clues:
            clues = stats.get("clues", [])
            if clues:
                print(f"\n📋 搜索线索分析:")
                stage_counts = {}
                for clue in clues:
                    stage = clue.get("stage", "unknown")
                    stage_counts[stage] = stage_counts.get(stage, 0) + 1

                for stage, count in sorted(stage_counts.items()):
                    print(f"   - {stage}: {count} 条关联")

        # 显示事项结果
        if result.search_result.data_full:
            print(f"\n📄 召回结果 (Top {top_k}):")
            print(f"{'-'*80}")

            for i, event in enumerate(result.search_result.data_full[:top_k], 1):
                title = event.get('title', 'N/A')
                summary = event.get('summary', '')[:150]
                content = event.get('content', '')[:200]

                print(f"\n【{i}】{title}")
                print(f"    ID: {event.get('id', 'N/A')}")
                print(f"    分类: {event.get('category', '无')}")
                if summary:
                    print(f"    摘要: {summary}{'...' if len(summary) == 150 else ''}")
                if content:
                    print(f"    内容: {content}{'...' if len(content) == 200 else ''}")

            print(f"\n{'-'*80}")

        # 显示执行日志
        if result.logs:
            print(f"\n📝 执行日志 (最近10条):")
            print(f"{'-'*80}")
            for log in result.logs[-10:]:
                print(f"[{log.stage}] {log.level}: {log.message}")
            print(f"{'-'*80}")

        # 返回结果供进一步分析
        return result

    except Exception as e:
        print(f"\n❌ 召回过程出错: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(
        description="SAG召回模块测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 基础用法
    python scripts/test_sag_recall.py "人工智能" source_config_id

    # 指定跳数和排序策略
    python scripts/test_sag_recall.py "脑机接口" source_id --max-hops 3 --rerank pagerank

    # 多源搜索
    python scripts/test_sag_recall.py "技术发展" source_id1 source_id2 --top-k 20
        """,
    )

    parser.add_argument("query", help="查询关键词")
    parser.add_argument("source_config_ids", nargs="+", help="信息源ID列表")
    parser.add_argument("--top-k", type=int, default=10, help="返回结果数量（默认: 10）")
    parser.add_argument("--max-hops", type=int, default=2, help="最大扩展跳数（默认: 2）")
    parser.add_argument("--rerank", choices=["pagerank", "rrf"], default="pagerank",
                       help="重排序策略（默认: pagerank）")
    parser.add_argument("--no-clues", action="store_true", help="不显示搜索线索")

    args = parser.parse_args()

    # 运行异步函数
    result = asyncio.run(
        test_sag_recall(
            query=args.query,
            source_config_ids=args.source_config_ids,
            top_k=args.top_k,
            max_hops=args.max_hops,
            rerank_strategy=args.rerank,
            show_clues=not args.no_clues,
        )
    )

    if result:
        print(f"\n🎯 召回测试完成！可以使用返回的结果对象进行进一步分析。")
    else:
        print(f"\n❌ 召回测试失败。")


if __name__ == "__main__":
    main()