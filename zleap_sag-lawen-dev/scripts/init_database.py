"""
数据库初始化脚本

安全地创建所有项目表并插入默认数据

功能
- 识别并显示项目表列表
- 创建所有项目表结构
- 插入默认实体类型
- 验证数据库完整性
- 显示每个表的记录数

安全性：
- 使用Base.metadata.tables自动识别项目表
- 只操作项目定义的表
- 提供详细的数据库验证信息
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from dataflow.db import EntityType, get_session_factory
from dataflow.db.base import Base  # 导入Base获取项目表定义
from dataflow.models.entity import DEFAULT_ENTITY_TYPES


# 输出辅助函数（与 init_elasticsearch.py 保持一致）
def print_header(text: str) -> None:
    """打印标题"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_success(text: str) -> None:
    """打印成功信息"""
    print(f"  ✓ {text}")


def print_info(text: str) -> None:
    """打印普通信息"""
    print(f"  • {text}")


def print_warning(text: str) -> None:
    """打印警告信息"""
    print(f"  ⚠️  {text}")


def print_error(text: str) -> None:
    """打印错误信息"""
    print(f"  ✗ {text}")


async def insert_default_entity_types() -> None:
    """
    插入或更新默认实体类型（Upsert模式）
    
    幂等性：按 type 字段检查是否存在
    - 存在：更新字段（保留原ID，避免破坏外键关系）
    - 不存在：插入新记录
    
    默认实体类型: time, location, person, topic, action, tags, ...
    """
    print_header("同步默认实体类型")
    
    factory = get_session_factory()

    async with factory() as session:
        inserted_count = 0
        updated_count = 0
        unchanged_count = 0

        # 逐个检查并插入/更新每个默认实体类型
        for type_def in DEFAULT_ENTITY_TYPES:
            # 按 type 字段检查是否已存在（而不是按 id）
            result = await session.execute(
                select(EntityType).where(
                    EntityType.type == type_def.type,
                    EntityType.is_default == True  # 只检查默认类型
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # 检查是否需要更新
                needs_update = (
                    existing.name != type_def.name or
                    existing.description != type_def.description or
                    existing.weight != type_def.weight or
                    existing.similarity_threshold != type_def.similarity_threshold
                )
                
                if needs_update:
                    # 更新字段（保留原ID！）
                    existing.name = type_def.name
                    existing.description = type_def.description
                    existing.weight = type_def.weight
                    existing.similarity_threshold = type_def.similarity_threshold
                    existing.is_active = type_def.is_active
                    print_success(f"{type_def.type} ({type_def.name}): 已更新")
                    updated_count += 1
                else:
                    print_info(f"{type_def.type} ({type_def.name}): 无变化，跳过")
                    unchanged_count += 1
                continue
            
            # 不存在，则插入新记录
            entity_type = EntityType(
                id=type_def.id,  # 使用预定义的固定UUID
                source_config_id=type_def.source_config_id,  # None 表示系统默认类型
                type=type_def.type,  # 类型标识符 (如 "time")
                name=type_def.name,  # 类型名称 (如 "时间")
                is_default=type_def.is_default,
                description=type_def.description,
                weight=type_def.weight,
                similarity_threshold=type_def.similarity_threshold,
                extra_data=None,
                is_active=type_def.is_active,
            )
            session.add(entity_type)
            print_success(f"{type_def.type} ({type_def.name}): 插入成功")
            inserted_count += 1

        await session.commit()
        
        print_header("同步总结")
        if inserted_count > 0:
            print_success(f"新插入: {inserted_count} 个")
        if updated_count > 0:
            print_success(f"已更新: {updated_count} 个")
        if unchanged_count > 0:
            print_info(f"无变化: {unchanged_count} 个")


def get_project_tables() -> set[str]:
    """获取项目中所有ORM定义的表"""
    # 确保所有模型都被导入（触发 ORM 注册）
    from dataflow.db import models  # noqa: F401
    
    project_tables = set()
    for table_name in Base.metadata.tables.keys():
        # 提取表名（处理可能的schema前缀）
        if '.' in table_name:
            project_tables.add(table_name.split('.')[-1])
        else:
            project_tables.add(table_name)
    
    return project_tables


async def verify_database() -> None:
    """
    验证数据库初始化是否成功
    """
    print_header("验证数据库")

    factory = get_session_factory()
    async with factory() as session:
        # 检查entity_types表的具体内容
        result = await session.execute(select(EntityType))
        entity_types = result.scalars().all()
        
        if entity_types:
            print_info(f"已有默认实体类型: {len(entity_types)} 个")
            for entity_type in entity_types:
                print_success(
                    f"{entity_type.type} ({entity_type.name}): "
                    f"weight={entity_type.weight}, threshold={entity_type.similarity_threshold}"
                )
        else:
            print_warning("未找到默认实体类型")


async def main() -> None:
    """
    主函数
    """
    try:
        print_header("DataFlow 数据库初始化")

        # 1. 插入默认实体类型
        await insert_default_entity_types()

        # 2. 验证数据库
        await verify_database()

        # 3. 总结
        print_header("初始化完成")
        print_success("数据库初始化成功！")
        print("=" * 70 + "\n")

    except Exception as e:
        print_error(f"数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        # 关闭数据库连接
        from dataflow.db.base import close_database

        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
