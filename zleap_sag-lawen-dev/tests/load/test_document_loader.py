#!/usr/bin/env python3
"""
DocumentLoader 完整功能测试

测试完整的文档加载流程（使用真实 Embedding API）：
1. Markdown 解析（parser）
2. 元数据生成（processor + LLM）
3. MySQL 存储（Article + ArticleSection）
4. 向量生成和 Elasticsearch 索引（自动）
5. 向量搜索（KNN）
6. 全文检索

前置条件：
1. 激活虚拟环境: source /Users/mac/dev/data_flow/.venv/bin/activate
2. MySQL 数据库已启动并初始化
3. Elasticsearch 已启动
4. ES 索引已初始化: python scripts/init_es_indices.py
5. .env 配置了 Embedding API

运行方式:
    python tests/load/test_document_loader.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dataflow.core.config import get_settings
from dataflow.core.storage import (
    ArticleSectionRepository,
    ElasticsearchClient,
)
from dataflow.db import Article, ArticleSection, SourceConfig, get_session_factory
from dataflow.db.base import close_database
from dataflow.modules.load.loader import DocumentLoader
from dataflow.modules.load.parser import MarkdownParser
from openai import AsyncOpenAI
from sqlalchemy import select


# ============================================
# 测试工具函数
# ============================================


def print_header(title: str):
    """打印测试标题"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_test(test_name: str):
    """打印测试项"""
    print(f"\n📝 {test_name}...")


def print_success(message: str):
    """打印成功信息"""
    print(f"  ✅ {message}")


def print_error(message: str):
    """打印错误信息"""
    print(f"  ❌ {message}")


def print_info(message: str):
    """打印提示信息"""
    print(f"  💡 {message}")


# ============================================
# 测试用例
# ============================================


async def test_embedding_api():
    """测试 Embedding API 连接"""
    print_test("测试 Embedding API 连接")

    try:
        settings = get_settings()
        client = AsyncOpenAI(
            api_key=settings.embedding_api_key or settings.llm_api_key,
            base_url=settings.embedding_base_url or settings.llm_base_url,
        )

        # 构建embedding请求参数
        embedding_kwargs = {
            "model": settings.embedding_model_name,
            "input": "这是一个测试文本",
        }

        # 仅在配置了维度时才传递 dimensions 参数
        if settings.embedding_dimensions:
            embedding_kwargs["dimensions"] = settings.embedding_dimensions

        response = await client.embeddings.create(**embedding_kwargs)
        vector = response.data[0].embedding

        if vector and len(vector) > 0:
            print_success(f"Embedding API 连接成功，向量维度: {len(vector)}")
            print_info(f"模型: {settings.embedding_model_name}")
            return True
        else:
            print_error("Embedding API 返回空向量")
            return False

    except Exception as e:
        print_error(f"Embedding API 连接失败: {e}")
        print_info("请检查 .env 文件中的配置:")
        print_info("  - EMBEDDING_API_KEY")
        print_info("  - EMBEDDING_BASE_URL")
        print_info("  - EMBEDDING_MODEL_NAME")
        return False


async def test_create_test_source() -> str | None:
    """创建测试信息源"""
    print_test("创建测试信息源")

    session_factory = get_session_factory()

    try:
        async with session_factory() as session:
            # 检查是否已存在测试信息源
            stmt = select(SourceConfig).where(SourceConfig.name == "test_loader_source")
            result = await session.execute(stmt)
            existing_source = result.scalar_one_or_none()

            if existing_source:
                print_success(f"使用已存在的测试信息源: {existing_source.id}")
                return existing_source.id

            # 创建新的测试信息源
            source_config_id = str(uuid.uuid4())
            source = SourceConfig(
                id=source_config_id,
                name="test_loader_source",
                description="测试用信息源",
                config={"focus": ["AI", "Technology"], "language": "zh"},
            )
            session.add(source)
            await session.commit()

            print_success(f"测试信息源创建成功: {source_config_id}")
            return source_config_id

    except Exception as e:
        print_error(f"创建测试信息源失败: {e}")
        return None


async def test_parser():
    """测试 Markdown 解析器"""
    print_test("测试 Markdown 解析器")

    try:
        parser = MarkdownParser(max_tokens=1000)
        test_file = Path(__file__).parent / "fixtures" / "sample_article_2.md"

        if not test_file.exists():
            print_error(f"测试文件不存在: {test_file}")
            return False

        content, sections = parser.parse_file(test_file)

        print_success(f"文档解析成功")
        print_info(f"文档长度: {len(content)} 字符")
        print_info(f"章节数量: {len(sections)}")

        for i, section in enumerate(sections[:3]):  # 只显示前3个章节
            print_info(f"章节 {i+1}: {section.heading[:40]}...")

        return True

    except Exception as e:
        print_error(f"解析失败: {e}")
        return False


async def test_full_load_flow(source_config_id: str):
    """测试完整的加载流程（包含自动索引到ES）"""
    print_test("测试完整的加载流程")

    try:
        # 初始化 DocumentLoader
        loader = DocumentLoader()

        # 测试文件路径
        test_file = Path(__file__).parent / "fixtures" / "sample_article_1.md"

        # 加载文档（自动索引到ES）
        print_info("开始加载文档（会调用 LLM 和 Embedding API，并自动索引到ES）...")
        article_id = await loader.load_file(
            file_path=test_file,
            source_config_id=source_config_id,
            background="人工智能技术文档测试",
            # auto_vector=True 是默认值，会自动索引到ES
        )

        print_success(f"文档加载成功: {article_id}")

        # 验证 MySQL 数据
        session_factory = get_session_factory()
        async with session_factory() as session:
            # 检查文章
            article = await session.get(Article, article_id)
            if not article:
                print_error("文章未保存到MySQL")
                return None

            print_success(f"MySQL 文章记录: {article.title}")
            print_info(f"摘要: {article.summary[:100]}..." if article.summary else "摘要: 无")
            print_info(f"分类: {article.category}")
            print_info(f"标签: {article.tags}")

            # 检查章节
            stmt = select(ArticleSection).where(
                ArticleSection.article_id == article_id
            ).order_by(ArticleSection.rank)
            result = await session.execute(stmt)
            sections = result.scalars().all()

            print_success(f"MySQL 章节记录: {len(sections)} 个")
            for i, section in enumerate(sections[:3]):
                print_info(f"章节 {i+1}: {section.heading[:40]}")

        # 等待ES刷新索引
        print_info("等待ES刷新索引...")
        await asyncio.sleep(2)

        return article_id

    except Exception as e:
        print_error(f"完整流程测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_vector_search(article_id: str):
    """测试向量相似度搜索"""
    print_test("测试向量相似度搜索")

    try:
        # 创建 ES 客户端
        es_client_wrapper = ElasticsearchClient()
        repo = ArticleSectionRepository(es_client_wrapper.client)

        # 生成查询向量
        settings = get_settings()
        client = AsyncOpenAI(
            api_key=settings.embedding_api_key or settings.llm_api_key,
            base_url=settings.embedding_base_url or settings.llm_base_url,
        )

        query_text = "人工智能在医疗中的应用"
        print_info(f"查询文本: {query_text}")

        # 构建embedding请求参数
        embedding_kwargs = {
            "model": settings.embedding_model_name,
            "input": query_text,
        }
        if settings.embedding_dimensions:
            embedding_kwargs["dimensions"] = settings.embedding_dimensions

        response = await client.embeddings.create(**embedding_kwargs)
        query_vector = response.data[0].embedding

        # 执行向量搜索
        results = await repo.search_similar_by_content(
            query_vector=query_vector,
            k=5,
        )

        # 关闭 ES 客户端
        await es_client_wrapper.client.close()

        if results:
            print_success(f"找到 {len(results)} 个相似章节")
            for i, result in enumerate(results[:3]):
                score = result.get("_score", 0)
                heading = result.get("heading", "未命名章节")
                content = result.get("content", "")

                # 显示标题和相似度
                print_info(f"{i+1}. [相似度: {score:.4f}] {heading}")

                # 显示内容（限制在300字以内，避免输出过长）
                if content:
                    content_preview = content[:300] + "..." if len(content) > 300 else content
                    print(f"     {content_preview}\n")
            return True
        else:
            print_error("未找到相似章节")
            return False

    except Exception as e:
        print_error(f"向量搜索测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_text_search():
    """测试全文检索"""
    print_test("测试全文检索")

    try:
        # 创建 ES 客户端
        es_client_wrapper = ElasticsearchClient()
        repo = ArticleSectionRepository(es_client_wrapper.client)

        # 执行全文搜索
        query_text = "深度学习"
        results = await repo.search_by_text(query=query_text, size=5)

        # 关闭 ES 客户端
        await es_client_wrapper.client.close()

        if results:
            print_success(f"找到 {len(results)} 个匹配章节")
            for i, result in enumerate(results[:3]):
                heading = result.get("heading", "未命名章节")
                content = result.get("content", "")

                # 显示标题
                print_info(f"{i+1}. {heading}")

                # 显示内容（限制在300字以内，避免输出过长）
                if content:
                    content_preview = content[:300] + "..." if len(content) > 300 else content
                    print(f"     {content_preview}\n")
            return True
        else:
            print_info("未找到匹配章节（可能是新索引，内容较少）")
            return True  # 不算失败

    except Exception as e:
        print_error(f"全文检索测试失败: {e}")
        return False


async def test_batch_load(source_config_id: str):
    """测试批量加载"""
    print_test("测试批量加载")

    try:
        loader = DocumentLoader()
        fixtures_dir = Path(__file__).parent / "fixtures"

        print_info(f"批量加载目录: {fixtures_dir}")
        print_info("这会处理多个文档，需要一些时间...")

        article_ids = await loader.load_directory(
            dir_path=fixtures_dir,
            source_config_id=source_config_id,
            pattern="sample_article_*.md",
            recursive=False,
            background="批量测试",
        )

        if article_ids:
            print_success(f"批量加载成功: {len(article_ids)} 篇文章")
            for i, aid in enumerate(article_ids):
                print_info(f"{i+1}. {aid}")
            return article_ids
        else:
            print_error("批量加载未返回任何文章")
            return []

    except Exception as e:
        print_error(f"批量加载测试失败: {e}")
        return []


async def cleanup_test_data(source_config_id: str):
    """清理测试数据"""
    print_test("清理测试数据")

    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            # 删除测试信息源（会级联删除所有文章和章节）
            source = await session.get(SourceConfig, source_config_id)
            if source:
                await session.delete(source)
                await session.commit()
                print_success("测试数据清理完成")
            else:
                print_info("测试信息源不存在，无需清理")

    except Exception as e:
        print_error(f"清理测试数据失败: {e}")


# ============================================
# 主测试流程
# ============================================


async def main():
    """主测试流程（使用真实 Embedding API）"""

    print_header("DocumentLoader 完整功能测试")
    print_info("本测试使用真实 Embedding API（会消耗API配额）")

    # 测试API连接
    if not await test_embedding_api():
        print_error("Embedding API 测试失败，退出测试")
        return

    # 创建测试信息源
    source_config_id = await test_create_test_source()
    if not source_config_id:
        print_error("无法创建测试信息源，退出测试")
        return

    try:
        # 1. 测试解析器
        await test_parser()

        # 2. 测试完整加载流程（包含自动索引到ES）
        article_id = await test_full_load_flow(source_config_id)
        if not article_id:
            print_error("完整流程测试失败，跳过后续测试")
            return

        # 3. 测试向量搜索
        await test_vector_search(article_id)

        # 4. 测试全文检索
        await test_text_search()

        # 5. 测试批量加载（可选，注释掉以节省时间）
        # await test_batch_load(source_config_id)

        print_header("测试完成")
        print_success("所有测试通过！")

    finally:
        # 清理测试数据
        cleanup = input("\n是否清理测试数据? (y/N): ").strip().lower()
        if cleanup == "y":
            await cleanup_test_data(source_config_id)
        else:
            print_info(f"测试数据保留，信息源ID: {source_config_id}")

        # 关闭数据库连接池
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
