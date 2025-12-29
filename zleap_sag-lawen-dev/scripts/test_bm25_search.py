#!/usr/bin/env python3
"""
BM25 搜索测试脚本

使用 ES 原生 BM25 算法进行快速搜索测试。

使用方法:
    # 基本用法（使用默认配置）
    python scripts/test_bm25_search.py "查询内容" source_config_id1 source_config_id2

    # 指定参数
    python scripts/test_bm25_search.py "人工智能" source_id1 --top-k 20 --title-weight 3.0

环境变量:
    需要在 .env 文件中配置以下变量:
    - ES_HOST, ES_PORT, ELASTIC_PASSWORD 等 ES 连接配置
    - MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE 等数据库配置
"""

import asyncio
import argparse
import sys
from pathlib import Path

# 加载 .env 环境变量
from dotenv import load_dotenv
load_dotenv()

from dataflow.modules.search import BM25Searcher, BM25Config


async def test_bm25_search(
    query: str,
    source_config_ids: list[str],
    top_k: int = 20,
    title_weight: float = 3.0,
    content_weight: float = 1.0,
    min_score: float | None = None,
):
    """
    执行 BM25 搜索测试

    Args:
        query: 查询文本
        source_config_ids: 信息源ID列表
        top_k: 返回数量
        title_weight: title 字段权重
        content_weight: content 字段权重
        min_score: 最低分数阈值
    """
    print(f"\n{'='*70}")
    print(f"🔍 BM25 搜索测试")
    print(f"{'='*70}")
    print(f"查询: {query}")
    print(f"信息源: {', '.join(source_config_ids)}")
    print(f"配置: top_k={top_k}, title_weight={title_weight}, content_weight={content_weight}, min_score={min_score}")
    print(f"{'='*70}\n")

    # 创建配置
    config = BM25Config(
        top_k=top_k,
        title_weight=title_weight,
        content_weight=content_weight,
        min_score=min_score,
    )

    # 创建检索器
    searcher = BM25Searcher()

    # 执行搜索
    print("⏳ 正在执行 BM25 搜索...")
    events = await searcher.search(
        query=query,
        source_config_ids=source_config_ids,
        config=config,
    )

    # 显示结果
    print(f"\n{'='*70}")
    print(f"📋 搜索结果: 共 {len(events)} 个事项")
    print(f"{'='*70}\n")

    if not events:
        print("未找到匹配的事项")
        return

    for i, event in enumerate(events):
        print(f"【{i+1}】{event.title}")
        print(f"    ID: {event.id}")
        print(f"    分类: {event.category or '无'}")
        print(f"    摘要: {event.summary[:100]}..." if len(event.summary) > 100 else f"    摘要: {event.summary}")
        print(f"    内容长度: {len(event.content)} 字符")
        print()

    print(f"{'='*70}")
    print(f"✅ 搜索完成")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(
        description="BM25 搜索测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python scripts/test_bm25_search.py "人工智能" source_id_1
    python scripts/test_bm25_search.py "技术发展" source_id_1 source_id_2 --top-k 10
    python scripts/test_bm25_search.py "产品" source_id_1 --title-weight 5.0 --content-weight 1.0
        """,
    )
    parser.add_argument("query", help="查询文本")
    parser.add_argument("source_config_ids", nargs="+", help="信息源ID列表（支持多个）")
    parser.add_argument("--top-k", type=int, default=20, help="返回数量（默认: 20）")
    parser.add_argument("--title-weight", type=float, default=3.0, help="title 字段权重（默认: 3.0）")
    parser.add_argument("--content-weight", type=float, default=1.0, help="content 字段权重（默认: 1.0）")
    parser.add_argument("--min-score", type=float, default=None, help="最低 BM25 分数阈值（默认: 无）")

    args = parser.parse_args()

    asyncio.run(
        test_bm25_search(
            query=args.query,
            source_config_ids=args.source_config_ids,
            top_k=args.top_k,
            title_weight=args.title_weight,
            content_weight=args.content_weight,
            min_score=args.min_score,
        )
    )


if __name__ == "__main__":
    main()
