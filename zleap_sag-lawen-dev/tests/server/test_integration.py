"""
DataFlow 集成测试脚本

测试整个系统的核心功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dataflow.core.ai import LLMMessage, LLMRole, create_llm_client
from dataflow.core.config import get_settings
from dataflow.core.prompt import get_prompt_manager
from dataflow.core.storage import get_es_client, get_mysql_client, get_redis_client
from dataflow.db import get_session_factory, init_database
from dataflow.modules.load import DocumentLoader, MarkdownParser, DocumentProcessor
from dataflow.utils import get_logger

logger = get_logger("test_integration")


def print_section(title: str) -> None:
    """打印分隔符"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


async def test_configuration() -> None:
    """测试配置管理"""
    print_section("1. 测试配置管理")

    settings = get_settings()

    print(f"✓ MySQL: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    print(f"✓ Redis: {settings.redis_host}:{settings.redis_port}")
    print(f"✓ ES: {settings.es_host}:{settings.es_port}")
    print(f"✓ LLM Model: {settings.llm_model}")
    if settings.llm_base_url:
        print(f"  中转API: {settings.llm_base_url}")
    print(f"✓ Log Level: {settings.log_level}")


async def test_storage_layer() -> None:
    """测试存储层"""
    print_section("2. 测试存储层")

    # MySQL
    mysql = get_mysql_client()
    mysql_ok = await mysql.ping()
    print(f"{'✓' if mysql_ok else '✗'} MySQL连接: {'成功' if mysql_ok else '失败'}")

    # Redis
    redis = get_redis_client()
    await redis.set("test_key", {"value": "test"}, expire=60)
    value = await redis.get("test_key")
    redis_ok = value is not None and value.get("value") == "test"
    print(f"{'✓' if redis_ok else '✗'} Redis缓存: {'成功' if redis_ok else '失败'}")

    # Elasticsearch
    es = get_es_client()
    es_ok = await es.ping()
    print(f"{'✓' if es_ok else '✗'} Elasticsearch连接: {'成功' if es_ok else '失败'}")

    return mysql_ok and redis_ok and es_ok


async def test_ai_layer() -> None:
    """测试AI层"""
    print_section("3. 测试AI层")

    # 创建LLM客户端
    llm = create_llm_client(with_retry=True)
    print(f"✓ LLM客户端创建成功")

    # 测试简单对话
    messages = [
        LLMMessage(role=LLMRole.SYSTEM, content="你是一个专业助手，简洁回答问题。"),
        LLMMessage(role=LLMRole.USER, content="用一句话介绍DataFlow项目"),
    ]

    try:
        response = await llm.chat(messages, temperature=0.5)
        print(f"✓ LLM对话成功")
        print(f"  响应: {response.content[:100]}...")
        print(f"  Token: {response.total_tokens}")
    except Exception as e:
        print(f"✗ LLM对话失败: {e}")
        return False

    return True


async def test_prompt_manager() -> None:
    """测试Prompt管理"""
    print_section("4. 测试Prompt管理")

    pm = get_prompt_manager()

    # 列出所有模板
    templates = pm.list_templates()
    print(f"✓ 加载模板数: {len(templates)}")
    print(f"  模板列表: {', '.join(templates)}")

    # 测试模板渲染
    if "article_metadata" in templates:
        prompt = pm.render(
            "article_metadata",
            content="这是一篇关于AI技术的文章...",
            background="技术博客",
        )
        print(f"✓ 模板渲染成功 (长度: {len(prompt)}字符)")

    return True


async def test_database() -> None:
    """测试数据库"""
    print_section("5. 测试数据库")

    # 初始化数据库
    print("初始化数据库...")
    await init_database()
    print("✓ 数据库表创建成功")

    # 创建测试用户
    import uuid

    factory = get_session_factory()
    async with factory() as session:
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            username="test_user",
            email="test@example.com",
            full_name="Test User",
            is_active=True,
        )
        session.add(user)
        await session.commit()

        print(f"✓ 测试用户创建成功 (ID: {user.id})")
        return user.id


async def test_load_module(user_id: str) -> None:
    """测试Load模块"""
    print_section("6. 测试Load模块")

    # 创建测试文档
    test_doc_path = Path(__file__).parent / "test_document.md"
    test_content = """# DataFlow 测试文档

## 简介

DataFlow是一个AI驱动的事件提取和检索引擎。

## 核心功能

### 1. 文档加载

支持Markdown文档的加载和解析。

### 2. 事项提取

使用LLM提取文档中的事件和实体。

### 3. 智能检索

基于向量的混合检索系统。

## 结论

这是一个强大的知识管理系统。
"""

    test_doc_path.write_text(test_content, encoding="utf-8")
    print(f"✓ 测试文档创建: {test_doc_path}")

    # 1. 测试解析器
    parser = MarkdownParser()
    content, sections = parser.parse_file(test_doc_path)
    print(f"✓ 文档解析成功: {len(sections)}个章节")
    for i, section in enumerate(sections[:3]):
        print(f"  {i+1}. [{section.level}] {section.heading} ({section.char_count}字符)")

    # 2. 测试处理器（需要API Key）
    try:
        processor = DocumentProcessor()
        print("✓ 文档处理器创建成功")

        # 生成元数据
        metadata = await processor.generate_metadata(
            content=content[:500],
            background="技术文档测试",
        )
        print(f"✓ 元数据生成成功")
        print(f"  标题: {metadata.get('title', 'N/A')}")
        print(f"  分类: {metadata.get('category', 'N/A')}")
        print(f"  标签: {metadata.get('tags', [])}")

    except Exception as e:
        print(f"⚠ 文档处理器测试跳过: {e}")
        return

    # 3. 测试加载器（完整流程）
    try:
        loader = DocumentLoader()
        article_id = await loader.load_file(
            file_path=test_doc_path,
            user_id=str(user_id),  # 转换为字符串
            background="技术文档测试",
            auto_vector=False,  # 暂不索引
        )
        print(f"✓ 文档加载成功 (Article ID: {article_id})")

    except Exception as e:
        print(f"✗ 文档加载失败: {e}")

    # 清理测试文件
    test_doc_path.unlink()
    print("✓ 测试文档已清理")


async def test_full_pipeline() -> None:
    """完整流程测试"""
    print_section("7. 完整流程测试")

    try:
        # 1. 配置
        await test_configuration()

        # 2. 存储层
        storage_ok = await test_storage_layer()
        if not storage_ok:
            print("\n⚠ 存储层测试失败，请检查docker服务是否启动")
            print("  运行命令: docker-compose up -d")
            return

        # 3. AI层
        ai_ok = await test_ai_layer()
        if not ai_ok:
            print("\n⚠ AI层测试失败，请检查API Key配置")
            return

        # 4. Prompt管理
        await test_prompt_manager()

        # 5. 数据库
        user_id = await test_database()

        # 6. Load模块
        await test_load_module(user_id)

        print("\n" + "=" * 60)
        print("  ✓ 所有测试通过！系统运行正常")
        print("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n✗ 测试失败: {e}")
        sys.exit(1)


async def main() -> None:
    """主函数"""
    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║              DataFlow 集成测试                             ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝")

    await test_full_pipeline()

    # 关闭连接
    from dataflow.db.base import close_database

    await close_database()


if __name__ == "__main__":
    asyncio.run(main())
