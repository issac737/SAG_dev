"""
Elasticsearch 软删除字段映射脚本

为三个 ES 索引添加 is_delete 字段的 mapping
- entity_vectors
- event_vectors
- source_chunks
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dataflow.core.config import get_settings
from dataflow.core.storage.elasticsearch import ElasticsearchClient, ESConfig
from dataflow.utils import get_logger

logger = get_logger("scripts.es_add_soft_delete_mapping")

# 需要添加软删除字段的索引列表
TARGET_INDICES = [
    "entity_vectors",
    "event_vectors",
    "source_chunks",
]


# 输出辅助函数
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


async def add_soft_delete_mapping(es_client: ElasticsearchClient) -> dict[str, str]:
    """
    为所有目标索引添加 is_delete 字段映射

    Returns:
        dict: 索引名 -> 状态 ("updated", "skipped", "failed")
    """
    print_header("添加软删除字段映射")
    logger.info("开始添加软删除字段映射...")

    results = {}

    # 软删除字段映射
    soft_delete_mapping = {
        "properties": {
            "is_delete": {"type": "boolean"}
        }
    }

    for index_name in TARGET_INDICES:
        try:
            # 检查索引是否存在
            exists = await es_client.index_exists(index_name)

            if not exists:
                print_warning(f"{index_name}: 索引不存在，跳过")
                logger.warning(f"索引 {index_name} 不存在，跳过")
                results[index_name] = "skipped"
                continue

            # 检查是否已有 is_delete 字段
            mapping = await es_client.get_mapping(index_name)
            properties = mapping.get("properties", {})

            if "is_delete" in properties:
                print_info(f"{index_name}: is_delete 字段已存在，跳过")
                logger.info(f"索引 {index_name} 已有 is_delete 字段，跳过")
                results[index_name] = "skipped"
                continue

            # 添加映射
            print_info(f"{index_name}: 正在添加 is_delete 字段...")
            await es_client.client.indices.put_mapping(
                index=index_name,
                properties=soft_delete_mapping["properties"]
            )
            print_success(f"{index_name}: is_delete 字段添加成功")
            logger.info(f"索引 {index_name} 添加 is_delete 字段成功")
            results[index_name] = "updated"

        except Exception as e:
            print_error(f"{index_name}: 添加映射失败 - {e}")
            logger.error(f"索引 {index_name} 添加映射失败: {e}", exc_info=True)
            results[index_name] = "failed"

    return results


async def verify_mappings(es_client: ElasticsearchClient) -> bool:
    """
    验证所有索引是否已有 is_delete 字段

    Returns:
        bool: 是否所有索引都验证通过
    """
    print_header("验证映射")
    logger.info("开始验证映射...")

    all_success = True

    for index_name in TARGET_INDICES:
        try:
            exists = await es_client.index_exists(index_name)

            if not exists:
                print_warning(f"{index_name}: 索引不存在")
                continue

            mapping = await es_client.get_mapping(index_name)
            properties = mapping.get("properties", {})

            if "is_delete" in properties:
                field_type = properties["is_delete"].get("type", "unknown")
                print_success(f"{index_name}: is_delete 字段存在 (类型: {field_type})")
                logger.info(f"索引 {index_name} 验证通过，is_delete 类型: {field_type}")
            else:
                print_error(f"{index_name}: is_delete 字段不存在")
                logger.error(f"索引 {index_name} 验证失败，is_delete 字段不存在")
                all_success = False

        except Exception as e:
            print_error(f"{index_name}: 验证失败 - {e}")
            logger.error(f"索引 {index_name} 验证失败: {e}", exc_info=True)
            all_success = False

    return all_success


async def main() -> None:
    """主函数"""
    es_client = None

    try:
        print_header("ES 软删除字段映射添加工具")
        logger.info("=" * 60)
        logger.info("ES 软删除字段映射添加工具")
        logger.info("=" * 60)

        # 1. 创建 ES 客户端
        print_info("正在连接 Elasticsearch...")
        settings = get_settings()
        config = ESConfig(
            hosts=f"{settings.es_host}:{settings.es_port}",
            username=settings.es_username,
            password=settings.es_password,
            scheme=settings.es_scheme,
        )
        es_client = ElasticsearchClient(config=config)

        # 2. 检查连接
        if not await es_client.check_connection():
            print_error("Elasticsearch 连接失败，请检查配置")
            raise Exception("ES 连接失败，请检查配置")

        print_success("Elasticsearch 连接成功")
        print_info(f"ES 地址: {es_client.hosts}")

        # 3. 二次确认
        print_header("操作确认")
        print_warning("此操作将修改 Elasticsearch 索引映射！")
        print_info(f"目标索引: {', '.join(TARGET_INDICES)}")
        print_info(f"ES 地址: {es_client.hosts}")
        print()

        confirm_input = input("  确认执行操作？(输入 'yes' 确认): ").strip().lower()
        if confirm_input != "yes":
            print_info("操作已取消")
            sys.exit(0)

        print_success("确认成功，开始执行操作...")

        # 4. 添加映射
        update_results = await add_soft_delete_mapping(es_client)

        # 5. 验证映射
        verify_success = await verify_mappings(es_client)

        # 6. 总结
        print_header("操作总结")

        updated_count = sum(1 for status in update_results.values() if status == "updated")
        skipped_count = sum(1 for status in update_results.values() if status == "skipped")
        failed_count = sum(1 for status in update_results.values() if status == "failed")

        if updated_count > 0:
            print_success(f"已更新索引: {updated_count} 个")
        if skipped_count > 0:
            print_info(f"跳过索引: {skipped_count} 个（已存在或不存在）")
        if failed_count > 0:
            print_error(f"失败索引: {failed_count} 个")

        if verify_success and failed_count == 0:
            print_success("所有索引映射更新成功！")
            logger.info("=" * 60)
            logger.info("✓ ES 软删除字段映射添加成功！")
            logger.info("=" * 60)
        else:
            print_error("部分索引映射更新失败，请查看详细信息")
            raise Exception("映射更新未完全成功")

        print("=" * 70 + "\n")

    except Exception as e:
        print_error(f"映射更新失败: {e}")
        logger.error(f"ES 软删除字段映射添加失败: {e}", exc_info=True)
        sys.exit(1)

    finally:
        # 关闭连接
        if es_client:
            await es_client.close()


if __name__ == "__main__":
    asyncio.run(main())
