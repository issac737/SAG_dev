"""
BM25 搜索示例 - search_with_scores vs search_chunks 对比

本文件提供 BM25Searcher 的两种带分数搜索方法的对比示例：
1. search_with_scores() - 事项级搜索，返回带 BM25 分数的事项列表
2. search_chunks() - 段落级搜索，返回带 BM25 分数的段落列表

两种方法都返回字典列表，结构一致，便于对比和使用。

使用前提：
1. 确保 Elasticsearch 正在运行并已索引数据
2. 确保 MySQL 中包含 SourceEvent 和 SourceChunk 数据
3. 安装必要的依赖：pytest, pytest-asyncio

运行方式：
    pytest test_bm25_examples.py -v
    pytest test_bm25_examples.py::test_search_with_scores -v  # 事项搜索（带分数）
    pytest test_bm25_examples.py::test_search_chunks -v      # 段落搜索（带分数）

方法对比：
    search() - 返回 SourceEvent 对象列表，不包含 BM25 分数（适合简单场景）
    search_with_scores() - 返回字典列表，包含 BM25 分数（推荐用于分析）
    search_chunks() - 返回字典列表，包含 BM25 分数（段落级搜索）
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from dataflow.modules.search.bm25 import BM25Searcher, BM25Config
from dataflow.modules.search.config import BM25Config


@pytest.fixture
async def bm25_searcher():
    """创建 BM25Searcher 实例"""
    return BM25Searcher()


@pytest.fixture
def source_config_ids():
    """测试用的数据源配置 ID

    注意：请根据你的实际数据修改这里的 ID
    """
    # 示例：使用你的实际配置 ID
    return ["config_001"]  # 修改为实际的数据源配置 ID


@pytest.fixture
def query_examples():
    """测试查询示例"""
    return {
        "technical": "人工智能技术发展",  # 技术相关查询
        "specific": "Qwen3 部署方式",      # 具体技术问题
        "general": "最新技术趋势",         # 一般性查询
    }


@pytest.mark.asyncio
async def test_search_with_scores(bm25_searcher, source_config_ids, query_examples):
    """
    测试事项级 BM25 搜索（使用 search_with_scores）

    搜索路径：Query -> ES(event_vectors) -> MySQL(SourceEvent)

    测试内容：
    1. search_with_scores() 返回带分数的字典列表
    2. 验证返回的字段完整性（event_id, score, event, title, content, source_config_id）
    3. 验证按 BM25 分数降序排列
    4. 自定义配置测试（top_k、字段权重）
    5. 空结果处理
    """
    print("\n" + "=" * 80)
    print("测试 search_with_scores() - 事项级搜索（带分数）")
    print("=" * 80)

    # 测试 1：基本搜索功能
    query = query_examples["specific"]
    print(f"\n[测试 1] 查询: '{query}'")
    print(f"数据源: {source_config_ids}")

    events = await bm25_searcher.search_with_scores(
        query=query,
        source_config_ids=source_config_ids
    )

    print(f"\n✓ 返回事项数量: {len(events)}")

    if events:
        print("\nTop-5 结果:")
        for i, event in enumerate(events[:5], 1):
            print(f"\n{i}. 事项 {event['event_id'][:8]}...")
            print(f"   BM25 分数: {event['score']:.4f}")
            print(f"   标题: {event['title'][:100] if event['title'] else '无标题'}")
            print(f"   内容: {event['content'][:200] if event['content'] else '无内容'}...")
            print(f"   数据源: {event['source_config_id']}")

        # 验证字段完整性
        required_fields = ["event_id", "score", "event", "title", "content", "source_config_id"]
        for field in required_fields:
            assert field in events[0], f"结果缺少必要字段: {field}"

        print("\n✓ 所有必要字段都存在")

        # 验证按分数降序排列
        scores = [e["score"] for e in events]
        is_sorted = all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))
        print(f"\n✓ 分数降序排列: {'是' if is_sorted else '否'}")
        print(f"  最高分: {scores[0]:.4f}")
        if len(scores) > 1:
            print(f"  最低分: {scores[-1]:.4f}")
        assert is_sorted, "结果应该按分数降序排列"

    # 测试 2：自定义配置
    print("\n" + "=" * 80)
    print("\n[测试 2] 自定义 BM25 配置")

    # 配置 1：只搜索标题
    config_title_only = BM25Config(
        top_k=10,
        title_weight=1.0,
        content_weight=0.0  # 不搜索内容
    )

    events_title_only = await bm25_searcher.search_with_scores(
        query=query,
        source_config_ids=source_config_ids,
        config=config_title_only
    )

    print(f"\n配置: 仅搜索标题 (title_weight=1.0, content_weight=0.0)")
    print(f"返回数量: {len(events_title_only)}")

    # 配置 2：高权重搜索内容
    config_content_heavy = BM25Config(
        top_k=10,
        title_weight=1.0,
        content_weight=3.0  # 内容权重更高
    )

    events_content_heavy = await bm25_searcher.search_with_scores(
        query=query,
        source_config_ids=source_config_ids,
        config=config_content_heavy
    )

    print(f"\n配置: 内容权重更高 (title_weight=1.0, content_weight=3.0)")
    print(f"返回数量: {len(events_content_heavy)}")

    # 两种配置结果应该不同
    if len(events_title_only) != len(events_content_heavy):
        print("✓ 不同配置返回不同数量的结果")

    # 测试 3：空查询处理
    print("\n" + "=" * 60)
    print("\n[测试 3] 不存在的查询")

    empty_query = "不存在的查询xyz123"
    empty_events = await bm25_searcher.search_with_scores(
        query=empty_query,
        source_config_ids=source_config_ids
    )

    print(f"查询: '{empty_query}'")
    print(f"返回数量: {len(empty_events)} (应该为 0)")
    assert len(empty_events) == 0, "不存在的查询应该返回空列表"

    print("\n✅ search_with_scores() 测试通过!")


@pytest.mark.asyncio
async def test_search_chunks(bm25_searcher, source_config_ids, query_examples):
    """
    测试段落级 BM25 搜索（使用 search_chunks）

    搜索路径：Query -> ES(source_chunks) -> MySQL(SourceChunk)

    测试内容：
    1. search_chunks() 返回带分数的字典列表
    2. 验证返回的字段完整性（chunk_id, score, heading, content, source_id, source_config_id, rank）
    3. 验证按 BM25 分数降序排列
    4. 与 search_with_scores() 的对比
    """
    print("\n" + "=" * 80)
    print("测试 search_chunks() - 段落级搜索（带分数）")
    print("=" * 80)

    query = query_examples["technical"]
    print(f"\n[测试 1] 查询: '{query}'")
    print(f"数据源: {source_config_ids}")

    # 同时调用两个方法进行对比
    events = await bm25_searcher.search_with_scores(
        query=query,
        source_config_ids=source_config_ids
    )
    chunks = await bm25_searcher.search_chunks(
        query=query,
        source_config_ids=source_config_ids
    )

    print(f"\n✓ 返回段落数量: {len(chunks)}")

    if chunks:
        print("\nTop-5 段落结果:")
        for i, chunk in enumerate(chunks[:5], 1):
            print(f"\n{i}. 段落 {chunk['chunk_id'][:8]}...")
            print(f"   BM25 分数: {chunk['score']:.4f}")
            print(f"   标题: {chunk['heading'][:80] if chunk['heading'] else '无标题'}")
            print(f"   内容: {chunk['content'][:200] if chunk['content'] else '无内容'}...")
            print(f"   来源: {chunk['source_id']}")
            print(f"   排序: {chunk['rank']}")

        # 验证字段完整性
        required_fields = ["chunk_id", "score", "heading", "content", "source_id", "source_config_id", "rank"]
        for field in required_fields:
            assert field in chunks[0], f"结果缺少必要字段: {field}"

        print("\n✓ 所有必要字段都存在")

        # 验证按分数降序排列
        scores = [c["score"] for c in chunks]
        is_sorted = all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))
        print(f"\n✓ 分数降序排列: {'是' if is_sorted else '否'}")
        print(f"  最高分: {scores[0]:.4f}")
        if len(scores) > 1:
            print(f"  最低分: {scores[-1]:.4f}")
        assert is_sorted, "结果应该按分数降序排列"

    # 测试 2：与 search_with_scores() 对比
    print("\n" + "=" * 80)
    print("\n[测试 2] search_with_scores() vs search_chunks() 对比")

    print(f"\n查询: '{query}'")
    print(f"search_with_scores() 结果: {len(events)} 个事项")
    print(f"search_chunks() 结果: {len(chunks)} 个段落")

    if events and chunks:
        print(f"\n事项级 Top-1:")
        print(f"  分数: {events[0]['score']:.4f}")
        print(f"  标题: {events[0]['title'][:50] if events[0]['title'] else '无标题'}")

        print(f"\n段落级 Top-1:")
        print(f"  分数: {chunks[0]['score']:.4f}")
        print(f"  标题: {chunks[0]['heading'][:50] if chunks[0]['heading'] else '无标题'}")

    print("\n✓ 两种方法对比完成")
    print("\n✅ search_chunks() 测试通过!")


@pytest.mark.asyncio
async def test_bm25_comparison(bm25_searcher, source_config_ids):
    """
    BM25 与 Embedding 搜索对比示例

    本示例展示如何同时使用 BM25 和 Embedding 搜索，并进行对比
    """
    print("\n" + "=" * 80)
    print("BM25 vs Embedding 对比测试")
    print("=" * 80)

    query = "人工智能技术应用"

    # BM25 搜索（使用 search_chunks）
    print(f"\n[BM25 搜索] 查询: '{query}'")
    chunks_bm25 = await bm25_searcher.search_chunks(
        query=query,
        source_config_ids=source_config_ids
    )
    print(f"返回段落: {len(chunks_bm25)} 个")

    if chunks_bm25:
        print(f"Top-1 分数: {chunks_bm25[0]['score']:.4f}")

    # Embedding 搜索（假设有这样的搜索器）
    # from dataflow.modules.search import EmbeddingSearcher
    # embedding_searcher = EmbeddingSearcher()
    # chunks_emb = await embedding_searcher.search_chunks(query, source_config_ids)

    # 对比分析
    print("\n[对比分析]")
    print("BM25 优势:")
    print("  ✓ 精确匹配关键词")
    print("  ✓ 速度快")
    print("  ✓ 无需向量计算")
    print("\nEmbedding 优势:")
    print("  ✓ 理解语义")
    print("  ✓ 支持相似词匹配")
    print("  ✓ 跨语言搜索")

    # 混合搜索示例（RRF融合）
    print("\n[混合搜索示例]")
    print("from dataflow.modules.search.ranking.rrf import rrf_fusion")
    print("# chunks_fused = rrf_fusion([chunks_bm25, chunks_emb], weights=[0.5, 0.5])")

    print("\n✅ BM25 对比测试完成!")


async def main():
    """主函数 - 可以直接运行查看示例"""
    print("\n" + "=" * 80)
    print("BM25Searcher 使用示例 - search_with_scores vs search_chunks")
    print("=" * 80)

    # 创建搜索器
    searcher = BM25Searcher()

    # 示例数据源（请根据你的环境修改）
    source_config_ids = ["fbdaac38-f0e7-4d46-9300-ecc705fa67ec"]  # 替换为你的数据源配置 ID

    # 示例查询
    queries = [
        "智能体发展现状"
    ]

    config = BM25Config(top_k=5)

    for query in queries:
        print(f"\n\n{'=' * 80}")
        print(f"查询: {query}")
        print(f"数据源: {source_config_ids}")
        print(f"配置: top_k={config.top_k}, title_weight={config.title_weight}, content_weight={config.content_weight}")
        print('=' * 80)

        try:
            # 搜索事项（使用 search_with_scores）
            print("\n[事项级搜索结果 - search_with_scores()]")
            events = await searcher.search_with_scores(
                query=query,
                source_config_ids=source_config_ids,
                config=config
            )

            for i, event in enumerate(events[:3], 1):
                print(f"\n{i}. 事项 {event['event_id'][:8]}...")
                print(f"   分数: {event['score']:.4f}")
                print(f"   标题: {event['title'][:60] if event['title'] else '无标题'}")
                print(f"   内容: {event['content'][:200] if event['content'] else '无内容'}...")
                print(f"   数据源: {event['source_config_id']}")

            # 搜索段落（使用 search_chunks）
            print("\n\n[段落级搜索结果 - search_chunks()]")
            chunks = await searcher.search_chunks(
                query=query,
                source_config_ids=source_config_ids,
                config=config
            )

            for i, chunk in enumerate(chunks[:3], 1):
                print(f"\n{i}. 段落 {chunk['chunk_id'][:8]}...")
                print(f"   分数: {chunk['score']:.4f}")
                print(f"   标题: {chunk['heading'][:60] if chunk['heading'] else '无标题'}")
                print(f"   内容: {chunk['content'][:200] if chunk['content'] else '无内容'}...")
                print(f"   来源: {chunk['source_id']}")

        except Exception as e:
            print(f"搜索失败: {e}")

    print("\n" + "=" * 80)
    print("示例运行完成!")
    print("=" * 80)


if __name__ == "__main__":
    # 直接运行示例
    asyncio.run(main())
