"""
辅助脚本: 创建测试用的 source_config

使用方法:
    python -m tests.token_stats.setup_source_config
"""

import asyncio
import sys
from dataflow.db import get_session_factory, SourceConfig
from sqlalchemy import select


async def create_test_source_config(source_id: str = "token-test-source"):
    """创建一个测试用的source_config"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        # 检查是否已存在
        result_db = await session.execute(
            select(SourceConfig).where(SourceConfig.id == source_id)
        )
        existing = result_db.scalar_one_or_none()

        if existing:
            print(f"✅ source_config 已存在:")
            print(f"   ID: {existing.id}")
            print(f"   名称: {existing.name}")
            print(f"   描述: {existing.description or 'N/A'}")
            return existing.id

        # 创建新的source_config
        new_config = SourceConfig(
            id=source_id,  # 使用固定ID
            name="Token统计测试源",
            description="用于文档Token统计测试的信息源",
        )

        session.add(new_config)
        await session.commit()
        await session.refresh(new_config)

        print(f"✅ 成功创建 source_config:")
        print(f"   ID: {new_config.id}")
        print(f"   名称: {new_config.name}")
        print(f"   描述: {new_config.description}")

        return new_config.id


async def main():
    print("=" * 70)
    print("创建测试用 Source Config")
    print("=" * 70)
    print()

    try:
        source_id = await create_test_source_config()
        print()
        print(f"现在可以运行测试脚本,使用:")
        print(f'SOURCE_CONFIG_ID = "{source_id}"')
        print()
    except Exception as e:
        print(f"❌ 创建失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

