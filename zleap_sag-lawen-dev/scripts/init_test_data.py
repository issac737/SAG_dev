#!/usr/bin/env python3
"""
Windows下的测试数据初始化脚本
创建测试用的source_config和示例数据
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dataflow.core.storage.mysql import MySQLStorage
from dataflow.db.models import SourceConfig, Article, SourceEvent
from sqlalchemy import select


async def init_test_data():
    """初始化测试数据"""
    print("🚀 开始初始化测试数据...")

    try:
        # 创建存储实例
        storage = MySQLStorage()

        # 创建source_config
        source_config = SourceConfig(
            name="测试数据源",
            description="用于测试召回模块的示例数据",
            type="manual",
            config={"test": True},
            created_by="test_user"
        )

        result = await storage.create_source_config(source_config)
        source_config_id = result.id

        print(f"✅ 创建测试数据源: {source_config_id}")

        # 创建示例文章
        articles = [
            {
                "title": "人工智能在医疗领域的突破",
                "content": """人工智能技术在医疗诊断领域取得了重大突破。通过深度学习算法，
                AI系统能够准确识别医学影像中的病变区域，准确率达到了95%以上。
                这项技术将大大提高医生的诊断效率。""",
                "source_config_id": source_config_id
            },
            {
                "title": "脑机接口技术的最新进展",
                "content": """脑机接口技术正在快速发展，最新的研究成果显示，
                通过植入式电极和机器学习算法，瘫痪患者可以通过思维控制机械臂。
                这项技术为残疾人带来了新的希望。""",
                "source_config_id": source_config_id
            },
            {
                "title": "深度学习在自动驾驶中的应用",
                "content": """深度学习算法在自动驾驶领域发挥着关键作用。
                通过神经网络模型，自动驾驶汽车能够实时识别道路标志、行人和其他车辆，
                大大提高了行车安全性。""",
                "source_config_id": source_config_id
            }
        ]

        for article_data in articles:
            article = Article(**article_data)
            await storage.create_article(article)
            print(f"  📄 创建文章: {article.title}")

        print(f"\n✅ 测试数据初始化完成！")
        print(f"📊 Source Config ID: {source_config_id}")
        print(f"📚 文章数量: {len(articles)}")

        return source_config_id

    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return None


if __name__ == "__main__":
    source_id = asyncio.run(init_test_data())
    if source_id:
        print(f"\n🎯 现在可以使用这个ID测试召回模块:")
        print(f"   python scripts/test_sag_recall.py '人工智能' {source_id}")