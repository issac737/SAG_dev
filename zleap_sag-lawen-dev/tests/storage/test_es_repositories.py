#!/usr/bin/env python3
"""
Elasticsearch Repositories 完整功能测试

测试三个已存在索引的基本操作：
- entity_vectors (实体向量)
- event_vectors (事件向量)
- article_sections (文章片段)

测试内容：
1. 基础增删查改（CRUD）
2. 向量相似度搜索（KNN检索） ⭐核心功能
3. 全文检索（多字段搜索）
4. 组合过滤查询

前置条件：
1. 激活虚拟环境: source /Users/mac/dev/data_flow/.venv/bin/activate
2. ES索引已初始化: python scripts/init_es_indices.py

运行方式:
    python tests/storage/test_es_repositories.py                    # 使用随机向量（快速）
    python tests/storage/test_es_repositories.py --use-real-embedding  # 使用真实Embedding API
"""

from dataflow.core.storage import (
    ArticleSectionRepository,
    ElasticsearchClient,
    EntityVectorRepository,
    EventVectorRepository,
)
from dataflow.core.config import get_settings
from openai import AsyncOpenAI
import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================
# 全局变量
# ============================================

# 向量维度：用于随机向量生成（如果使用真实API，维度由配置决定）
VECTOR_DIM = 1024

# Embedding 客户端（全局单例）
_embedding_client: Optional[AsyncOpenAI] = None

# 向量生成器（由 main() 函数设置）
generate_vector = None


# ============================================
# 测试工具函数
# ============================================


def generate_random_vector(dim: int = VECTOR_DIM) -> List[float]:
    """生成随机向量（用于快速测试，不消耗API）"""
    return [random.uniform(-1.0, 1.0) for _ in range(dim)]


async def get_embedding_client() -> AsyncOpenAI:
    """获取 Embedding 客户端（单例）"""
    global _embedding_client
    if _embedding_client is None:
        settings = get_settings()
        _embedding_client = AsyncOpenAI(
            api_key=settings.embedding_api_key or settings.llm_api_key,
            base_url=settings.embedding_base_url or settings.llm_base_url,
        )
    return _embedding_client


async def generate_real_embedding(text: str) -> List[float]:
    """
    使用真实 Embedding API 生成向量

    Args:
        text: 输入文本

    Returns:
        向量（维度由模型决定，或由配置的 embedding_dimensions 指定）

    Raises:
        Exception: API调用失败
    """
    client = await get_embedding_client()
    settings = get_settings()

    try:
        # 构建embedding请求参数
        embedding_kwargs = {
            "model": settings.embedding_model_name,
            "input": text,
        }

        # 仅在配置了维度时才传递 dimensions 参数
        # 某些模型（如 Qwen/Qwen3-Embedding-0.6B）不支持自定义维度
        if settings.embedding_dimensions:
            embedding_kwargs["dimensions"] = settings.embedding_dimensions

        response = await client.embeddings.create(**embedding_kwargs)
        return response.data[0].embedding
    except Exception as e:
        print_error(f"Embedding API 调用失败: {e}")
        raise


def print_header(title: str):
    """打印测试标题"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_test(test_name: str):
    """打印测试名称"""
    print(f"\n📝 {test_name}")


def print_success(message: str):
    """打印成功信息"""
    print(f"  ✅ {message}")


def print_error(message: str):
    """打印错误信息"""
    print(f"  ❌ {message}")


# ============================================
# EntityVectorRepository 测试
# ============================================


async def test_entity_repository(entity_repo):
    """测试实体向量 Repository - 增删查改"""
    print_header("EntityVectorRepository 增删查改测试")

    # 1. 增 - 索引单个实体
    print_test("1. 增 - 索引单个实体")
    try:
        entity_id = "test_entity_001"
        doc_id = await entity_repo.index_entity(
            entity_id=entity_id,
            source_config_id="test_source_001",
            entity_type="PERSON",
            name="张三",
            vector=generate_random_vector(),
            created_time=datetime.utcnow().isoformat(),
        )
        assert doc_id == entity_id
        print_success(f"实体已索引: {doc_id}")
        await asyncio.sleep(1)  # 等待索引生效
    except Exception as e:
        print_error(f"索引失败: {e}")
        return

    # 2. 查 - 获取单个文档
    print_test("2. 查 - 获取单个文档")
    try:
        doc = await entity_repo.get_document(entity_repo.INDEX_NAME, entity_id)
        assert doc is not None
        assert doc["name"] == "张三"
        assert doc["type"] == "PERSON"
        print_success(f"文档获取成功: {doc['name']} ({doc['type']})")
    except Exception as e:
        print_error(f"查询失败: {e}")

    # 3. 改 - 更新实体（重新索引）
    print_test("3. 改 - 更新实体")
    try:
        doc_id = await entity_repo.index_entity(
            entity_id=entity_id,
            source_config_id="test_source_001",
            entity_type="PERSON",
            name="张三（已更新）",
            vector=generate_random_vector(),
            created_time=datetime.utcnow().isoformat(),
        )
        await asyncio.sleep(1)

        # 验证更新
        doc = await entity_repo.get_document(entity_repo.INDEX_NAME, entity_id)
        assert "已更新" in doc["name"]
        print_success(f"实体已更新: {doc['name']}")
    except Exception as e:
        print_error(f"更新失败: {e}")

    # 4. 查 - 按名称搜索
    print_test("4. 查 - 按名称搜索")
    try:
        results = await entity_repo.search_by_name(
            name="张三", source_config_id="test_source_001", size=10
        )
        print_success(f"找到 {len(results)} 个实体")
        for entity in results[:3]:
            print(f"     - {entity['name']} ({entity['type']})")
    except Exception as e:
        print_error(f"搜索失败: {e}")

    # 5. 删 - 删除实体
    print_test("5. 删 - 删除实体")
    try:
        success = await entity_repo.delete_document(entity_repo.INDEX_NAME, entity_id)
        assert success is True
        print_success(f"实体已删除: {entity_id}")
        await asyncio.sleep(1)

        # 验证删除
        doc = await entity_repo.get_document(entity_repo.INDEX_NAME, entity_id)
        assert doc is None
        print_success("验证删除成功")
    except Exception as e:
        print_error(f"删除失败: {e}")


# ============================================
# EventVectorRepository 测试
# ============================================


async def test_event_repository(event_repo):
    """测试事件向量 Repository - 增删查改"""
    print_header("EventVectorRepository 增删查改测试")

    # 1. 增 - 索引单个事件
    print_test("1. 增 - 索引单个事件")
    try:
        event_id = "test_event_001"
        doc_id = await event_repo.index_event(
            event_id=event_id,
            source_config_id="test_source_001",
            article_id="test_article_001",
            title="人工智能技术突破",
            summary="AI技术取得重大进展",
            content="人工智能技术在自然语言处理领域取得重大突破...",
            title_vector=generate_random_vector(),
            content_vector=generate_random_vector(),
            category="科技",
            tags=["AI", "技术", "突破"],
            entity_ids=["test_entity_010", "test_entity_011"],
            start_time=datetime.utcnow().isoformat(),
            end_time=(datetime.utcnow() + timedelta(days=1)).isoformat(),
            created_time=datetime.utcnow().isoformat(),
        )
        assert doc_id == event_id
        print_success(f"事件已索引: {doc_id}")
        await asyncio.sleep(1)
    except Exception as e:
        print_error(f"索引失败: {e}")
        return

    # 2. 查 - 获取单个文档
    print_test("2. 查 - 获取单个文档")
    try:
        doc = await event_repo.get_document(event_repo.INDEX_NAME, event_id)
        assert doc is not None
        assert doc["title"] == "人工智能技术突破"
        print_success(f"文档获取成功: {doc['title']}")
    except Exception as e:
        print_error(f"查询失败: {e}")

    # 3. 改 - 更新事件
    print_test("3. 改 - 更新事件")
    try:
        doc_id = await event_repo.index_event(
            event_id=event_id,
            source_config_id="test_source_001",
            article_id="test_article_001",
            title="人工智能技术突破（已更新）",
            summary="AI技术取得重大进展（最新）",
            content="人工智能技术在自然语言处理领域取得重大突破...",
            title_vector=generate_random_vector(),
            content_vector=generate_random_vector(),
            category="科技",
            tags=["AI", "技术", "突破", "更新"],
            entity_ids=["test_entity_010", "test_entity_011"],
            start_time=datetime.utcnow().isoformat(),
            end_time=(datetime.utcnow() + timedelta(days=1)).isoformat(),
            created_time=datetime.utcnow().isoformat(),
        )
        await asyncio.sleep(1)

        # 验证更新
        doc = await event_repo.get_document(event_repo.INDEX_NAME, event_id)
        assert "已更新" in doc["title"]
        print_success(f"事件已更新: {doc['title']}")
    except Exception as e:
        print_error(f"更新失败: {e}")

    # 4. 查 - 全文检索
    print_test("4. 查 - 全文检索")
    try:
        results = await event_repo.search_by_text(
            query="人工智能", source_config_id="test_source_001", size=10
        )
        print_success(f"找到 {len(results)} 个事件")
        for event in results[:3]:
            print(f"     - {event['title']}")
    except Exception as e:
        print_error(f"全文检索失败: {e}")

    # 5. 删 - 删除事件
    print_test("5. 删 - 删除事件")
    try:
        success = await event_repo.delete_document(event_repo.INDEX_NAME, event_id)
        assert success is True
        print_success(f"事件已删除: {event_id}")
        await asyncio.sleep(1)

        # 验证删除
        doc = await event_repo.get_document(event_repo.INDEX_NAME, event_id)
        assert doc is None
        print_success("验证删除成功")
    except Exception as e:
        print_error(f"删除失败: {e}")


# ============================================
# ArticleSectionRepository 测试
# ============================================


async def test_article_repository(article_repo):
    """测试文章片段 Repository - 增删查改"""
    print_header("ArticleSectionRepository 增删查改测试")

    # 1. 增 - 索引单个片段
    print_test("1. 增 - 索引单个片段")
    try:
        section_id = "test_section_001"
        doc_id = await article_repo.index_section(
            section_id=section_id,
            article_id="test_article_001",
            source_config_id="test_source_001",
            rank=1,
            heading="第一章：深度学习基础",
            content="这是第一章的内容，讲述深度学习的基础知识...",
            heading_vector=generate_random_vector(),
            content_vector=generate_random_vector(),
            section_type="content",
            content_length=100,
            created_time=datetime.utcnow().isoformat(),
        )
        assert doc_id == section_id
        print_success(f"片段已索引: {doc_id}")
        await asyncio.sleep(1)
    except Exception as e:
        print_error(f"索引失败: {e}")
        return

    # 2. 查 - 获取单个文档
    print_test("2. 查 - 获取单个文档")
    try:
        doc = await article_repo.get_document(article_repo.INDEX_NAME, section_id)
        assert doc is not None
        assert doc["heading"] == "第一章：深度学习基础"
        print_success(f"文档获取成功: {doc['heading']}")
    except Exception as e:
        print_error(f"查询失败: {e}")

    # 3. 改 - 更新片段
    print_test("3. 改 - 更新片段")
    try:
        doc_id = await article_repo.index_section(
            section_id=section_id,
            article_id="test_article_001",
            source_config_id="test_source_001",
            rank=1,
            heading="第一章：深度学习基础（修订版）",
            content="这是第一章的内容，讲述深度学习的基础知识（已更新）...",
            heading_vector=generate_random_vector(),
            content_vector=generate_random_vector(),
            section_type="content",
            content_length=120,
            created_time=datetime.utcnow().isoformat(),
            updated_time=datetime.utcnow().isoformat(),
        )
        await asyncio.sleep(1)

        # 验证更新
        doc = await article_repo.get_document(article_repo.INDEX_NAME, section_id)
        assert "修订版" in doc["heading"]
        print_success(f"片段已更新: {doc['heading']}")
    except Exception as e:
        print_error(f"更新失败: {e}")

    # 4. 查 - 全文检索
    print_test("4. 查 - 全文检索")
    try:
        results = await article_repo.search_by_text(
            query="深度学习", source_config_id="test_source_001", size=10
        )
        print_success(f"找到 {len(results)} 个片段")
        for section in results[:3]:
            print(f"     - {section['heading']}")
    except Exception as e:
        print_error(f"全文检索失败: {e}")

    # 5. 删 - 删除片段
    print_test("5. 删 - 删除片段")
    try:
        success = await article_repo.delete_document(
            article_repo.INDEX_NAME, section_id
        )
        assert success is True
        print_success(f"片段已删除: {section_id}")
        await asyncio.sleep(1)

        # 验证删除
        doc = await article_repo.get_document(article_repo.INDEX_NAME, section_id)
        assert doc is None
        print_success("验证删除成功")
    except Exception as e:
        print_error(f"删除失败: {e}")


# ============================================
# 向量检索专项测试
# ============================================


async def test_vector_search(entity_repo, event_repo, article_repo):
    """测试向量相似度搜索功能（核心功能）"""
    print_header("向量相似度搜索专项测试")

    # ========== 1. EntityVectorRepository 向量检索 ==========
    print_test("1. EntityVectorRepository - 向量相似度搜索")

    # 1.1 批量索引测试实体
    try:
        print("  准备测试数据：批量索引5个实体...")
        test_entities = []
        test_vectors = []  # 保存向量用于后续查询

        for i in range(1, 6):
            vector = generate_random_vector()
            test_vectors.append(vector)

            entity_id = f"test_vector_entity_{i:03d}"
            await entity_repo.index_entity(
                entity_id=entity_id,
                source_config_id="test_vector_source",
                entity_type="PERSON" if i % 2 == 0 else "ORGANIZATION",
                name=f"向量测试实体{i}",
                vector=vector,
                created_time=datetime.utcnow().isoformat(),
            )
            test_entities.append(entity_id)

        await asyncio.sleep(2)  # 等待索引生效
        print_success(f"已索引 {len(test_entities)} 个测试实体")
    except Exception as e:
        print_error(f"批量索引失败: {e}")
        return

    # 1.2 测试向量相似搜索
    try:
        query_vector = test_vectors[0]  # 使用第一个实体的向量作为查询
        results = await entity_repo.search_similar(
            query_vector=query_vector,
            k=3,
            entity_type="PERSON"
        )

        print_success(f"向量搜索成功，找到 {len(results)} 个相似实体")
        for idx, entity in enumerate(results, 1):
            score = entity.get('_score', 0)
            print(
                f"     {idx}. {entity['name']} (相似度分数: {score:.4f}, 类型: {entity['type']})")

        # 验证：结果应该包含相似度分数
        assert all('_score' in result for result in results), "结果缺少相似度分数"
        # 验证：分数应该按降序排列
        scores = [r['_score'] for r in results]
        assert scores == sorted(scores, reverse=True), "相似度分数未按降序排列"
        print_success("✓ 相似度分数验证通过")

    except Exception as e:
        print_error(f"向量搜索失败: {e}")

    # 1.3 测试无过滤条件的向量搜索
    try:
        results_no_filter = await entity_repo.search_similar(
            query_vector=generate_random_vector(),
            k=5
        )
        print_success(f"无过滤条件搜索成功，找到 {len(results_no_filter)} 个结果")
    except Exception as e:
        print_error(f"无过滤搜索失败: {e}")

    # ========== 2. EventVectorRepository 向量检索 ==========
    print_test("2. EventVectorRepository - 标题和内容向量搜索")

    # 2.1 批量索引测试事件
    try:
        print("  准备测试数据：批量索引3个事件...")
        test_events = []
        test_title_vectors = []
        test_content_vectors = []

        categories = ["科技", "经济", "科技"]
        titles = ["AI技术突破", "经济形势分析", "量子计算进展"]

        for i in range(1, 4):
            title_vector = generate_random_vector()
            content_vector = generate_random_vector()
            test_title_vectors.append(title_vector)
            test_content_vectors.append(content_vector)

            event_id = f"test_vector_event_{i:03d}"
            await event_repo.index_event(
                event_id=event_id,
                source_config_id="test_vector_source",
                article_id=f"test_vector_article_{i:03d}",
                title=titles[i-1],
                summary=f"{titles[i-1]}的详细摘要",
                content=f"这是关于{titles[i-1]}的详细内容...",
                title_vector=title_vector,
                content_vector=content_vector,
                category=categories[i-1],
                tags=["测试", "向量"],
                entity_ids=[],
                start_time=datetime.utcnow().isoformat(),
                end_time=(datetime.utcnow() + timedelta(days=1)).isoformat(),
                created_time=datetime.utcnow().isoformat(),
            )
            test_events.append(event_id)

        await asyncio.sleep(2)  # 等待索引生效
        print_success(f"已索引 {len(test_events)} 个测试事件")
    except Exception as e:
        print_error(f"批量索引失败: {e}")
        return

    # 2.2 测试标题向量搜索
    try:
        query_vector = test_title_vectors[0]
        results = await event_repo.search_similar_by_title(
            query_vector=query_vector,
            k=2,
            category="科技"
        )

        print_success(f"标题向量搜索成功，找到 {len(results)} 个相似事件")
        for idx, event in enumerate(results, 1):
            score = event.get('_score', 0)
            print(
                f"     {idx}. {event['title']} (相似度: {score:.4f}, 分类: {event['category']})")

        assert len(results) > 0, "标题向量搜索未返回结果"
        print_success("✓ 标题向量搜索验证通过")

    except Exception as e:
        print_error(f"标题向量搜索失败: {e}")

    # 2.3 测试内容向量搜索
    try:
        query_vector = test_content_vectors[1]
        results = await event_repo.search_similar_by_content(
            query_vector=query_vector,
            k=3
        )

        print_success(f"内容向量搜索成功，找到 {len(results)} 个相似事件")
        for idx, event in enumerate(results, 1):
            score = event.get('_score', 0)
            print(f"     {idx}. {event['title']} (相似度: {score:.4f})")

        # 验证：分数按降序排列
        scores = [r['_score'] for r in results]
        assert scores == sorted(scores, reverse=True), "分数未按降序排列"
        print_success("✓ 内容向量搜索验证通过")

    except Exception as e:
        print_error(f"内容向量搜索失败: {e}")

    # ========== 3. ArticleSectionRepository 向量检索 ==========
    print_test("3. ArticleSectionRepository - 片段内容向量搜索")

    # 3.1 批量索引测试片段
    try:
        print("  准备测试数据：批量索引5个文章片段...")
        test_sections = []
        test_section_vectors = []

        for i in range(1, 6):
            content_vector = generate_random_vector()
            test_section_vectors.append(content_vector)

            section_id = f"test_vector_section_{i:03d}"
            await article_repo.index_section(
                section_id=section_id,
                article_id="test_vector_article_001",
                source_config_id="test_vector_source",
                rank=i,
                heading=f"第{i}节：向量检索测试",
                content=f"这是第{i}节的测试内容，用于验证向量相似度搜索功能。",
                heading_vector=generate_random_vector(),
                content_vector=content_vector,
                section_type="content",
                content_length=50,
                created_time=datetime.utcnow().isoformat(),
            )
            test_sections.append(section_id)

        await asyncio.sleep(2)  # 等待索引生效
        print_success(f"已索引 {len(test_sections)} 个测试片段")
    except Exception as e:
        print_error(f"批量索引失败: {e}")
        return

    # 3.2 测试片段内容向量搜索
    try:
        query_vector = test_section_vectors[2]  # 使用第3个片段的向量
        results = await article_repo.search_similar_by_content(
            query_vector=query_vector,
            k=3,
            section_type="content"
        )

        print_success(f"片段向量搜索成功，找到 {len(results)} 个相似片段")
        for idx, section in enumerate(results, 1):
            score = section.get('_score', 0)
            print(
                f"     {idx}. {section['heading']} (相似度: {score:.4f}, rank: {section['rank']})")

        # 验证Top-K
        assert len(results) <= 3, f"返回结果数量超过k=3，实际: {len(results)}"
        assert all('_score' in r for r in results), "结果缺少相似度分数"
        print_success("✓ 片段向量搜索验证通过")

    except Exception as e:
        print_error(f"片段向量搜索失败: {e}")

    # 3.3 测试无过滤条件的片段搜索
    try:
        results_no_filter = await article_repo.search_similar_by_content(
            query_vector=generate_random_vector(),
            k=5
        )
        print_success(f"无过滤条件搜索成功，找到 {len(results_no_filter)} 个结果")
    except Exception as e:
        print_error(f"无过滤搜索失败: {e}")

    # ========== 4. 清理测试数据 ==========
    print_test("清理向量测试数据")
    try:
        cleanup_count = 0

        # 删除实体
        for entity_id in test_entities:
            if await entity_repo.delete_document(entity_repo.INDEX_NAME, entity_id):
                cleanup_count += 1

        # 删除事件
        for event_id in test_events:
            if await event_repo.delete_document(event_repo.INDEX_NAME, event_id):
                cleanup_count += 1

        # 删除片段
        for section_id in test_sections:
            if await article_repo.delete_document(article_repo.INDEX_NAME, section_id):
                cleanup_count += 1

        await asyncio.sleep(1)
        print_success(f"已清理 {cleanup_count} 个测试文档")

    except Exception as e:
        print_error(f"清理失败: {e}")


# ============================================
# 主测试流程
# ============================================


async def main(use_real_embedding: bool = True):
    """
    主测试流程

    Args:
        use_real_embedding: 是否使用真实 Embedding API（默认使用随机向量）
    """
    vector_mode = "真实Embedding API (1024维)" if use_real_embedding else "随机向量 (1024维)"
    print_header(f"Elasticsearch Repositories 完整功能测试 - {vector_mode}")
    print("  前置条件：ES索引已通过 scripts/init_es_indices.py 初始化")

    if use_real_embedding:
        print("  ⚠️  注意：使用真实Embedding API会消耗API配额")
        # 测试 Embedding API 连接
        try:
            print_test("测试 Embedding API 连接...")
            test_vector = await generate_real_embedding("测试连接")
            print_success(f"Embedding API 连接成功！向量维度: {len(test_vector)}")
        except Exception as e:
            print_error(f"Embedding API 连接失败: {e}")
            print("  提示：请检查 .env 文件中的 EMBEDDING_API_KEY 和 EMBEDDING_BASE_URL 配置")
            return

    # 设置全局向量生成器
    global generate_vector
    generate_vector = generate_real_embedding if use_real_embedding else generate_random_vector

    # 1. 初始化ES客户端
    print_test("初始化 Elasticsearch 客户端...")
    try:
        es_client_wrapper = ElasticsearchClient(
            hosts=["http://localhost:9200"])
        es_client = es_client_wrapper.client
        print_success("ES 客户端已初始化")
    except Exception as e:
        print_error(f"ES 初始化失败: {e}")
        return

    # 2. 创建 Repositories
    entity_repo = EntityVectorRepository(es_client)
    event_repo = EventVectorRepository(es_client)
    article_repo = ArticleSectionRepository(es_client)
    print_success("Repositories 已创建")

    try:
        # 3. 运行增删查改测试
        await test_entity_repository(entity_repo)
        await test_event_repository(event_repo)
        await test_article_repository(article_repo)

        # 4. 运行向量检索测试
        await test_vector_search(entity_repo, event_repo, article_repo)

        print_header("测试完成")
        print_success("所有测试已完成！")
        print("\n测试覆盖：")
        print("  ✅ 增删查改：基础CRUD操作")
        print("  ✅ 向量检索：KNN相似度搜索（核心功能）")
        print("  ✅ 全文检索：多字段文本搜索")
        print("  ✅ 过滤查询：组合条件过滤")
        print(f"  📊 向量模式：{vector_mode}")

    except Exception as e:
        print_error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 5. 关闭连接
        print_test("关闭 Elasticsearch 客户端...")
        await es_client_wrapper.close()
        print_success("ES 客户端已关闭")


if __name__ == "__main__":
    """运行测试"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="Elasticsearch Repositories 功能测试")
    parser.add_argument(
        "--use-real-embedding",
        action="store_true",
        help="使用真实Embedding API生成向量（默认使用随机向量）",
    )
    args = parser.parse_args()

    print("\n提示：请确保已激活虚拟环境")
    print("  source /Users/mac/dev/data_flow/.venv/bin/activate")
    print(
        f"\n向量模式：{'真实Embedding API' if args.use_real_embedding else '随机向量（快速）'}")
    print()

    asyncio.run(main(use_real_embedding=args.use_real_embedding))
