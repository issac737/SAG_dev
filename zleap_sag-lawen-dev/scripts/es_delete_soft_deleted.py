"""
ES 软删除文档物理删除脚本

物理删除三个 ES 索引中 is_delete=true 的文档

安全措施：
- 打印 ES 地址供确认
- 统计待删除文档数量
- 执行前确认
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Dict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dataflow.core.config import get_settings
from dataflow.core.storage.elasticsearch import ElasticsearchClient, ESConfig
from dataflow.utils import get_logger

logger = get_logger("scripts.es_delete_soft_deleted")

# 需要处理的索引列表
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


def print_danger(text: str) -> None:
    """打印危险警告"""
    print(f"  🚨 {text}")


async def count_soft_deleted_documents(
    es_client: ElasticsearchClient
) -> Dict[str, int]:
    """
    统计各索引中软删除标记为 true 的文档数量

    Returns:
        Dict[str, int]: 索引名 -> 文档数量
    """
    print_header("统计待删除文档")

    counts = {}

    for index_name in TARGET_INDICES:
        try:
            exists = await es_client.index_exists(index_name)

            if not exists:
                print_warning(f"{index_name}: 索引不存在，跳过")
                counts[index_name] = 0
                continue

            # 查询 is_delete=true 的文档数量
            count = await es_client.count_documents(
                index=index_name,
                query={
                    "term": {
                        "is_delete": True
                    }
                }
            )

            counts[index_name] = count
            print_info(f"{index_name}: {count} 条待删除文档")

        except Exception as e:
            print_error(f"{index_name}: 统计失败 - {e}")
            logger.error(f"统计索引 {index_name} 失败: {e}", exc_info=True)
            counts[index_name] = -1

    return counts


async def delete_soft_deleted_documents(
    es_client: ElasticsearchClient,
    counts: Dict[str, int]
) -> Dict[str, dict]:
    """
    物理删除软删除标记为 true 的文档

    Returns:
        Dict[str, dict]: 索引名 -> 删除结果
    """
    print_header("执行物理删除")

    results = {}

    for index_name in TARGET_INDICES:
        doc_count = counts.get(index_name, 0)

        if doc_count <= 0:
            print_info(f"{index_name}: 无需删除")
            results[index_name] = {"deleted": 0, "failed": 0}
            continue

        print_info(f"{index_name}: 正在删除 {doc_count} 条文档...")

        try:
            # 使用 delete_by_query 批量删除
            response = await es_client.client.delete_by_query(
                index=index_name,
                query={
                    "term": {
                        "is_delete": True
                    }
                },
                conflicts="proceed",
                refresh=True
            )

            deleted = response.get("deleted", 0)
            failures = len(response.get("failures", []))

            results[index_name] = {
                "deleted": deleted,
                "failed": failures
            }

            if failures > 0:
                print_warning(f"{index_name}: 删除 {deleted} 条，失败 {failures} 条")
            else:
                print_success(f"{index_name}: 删除 {deleted} 条")

        except Exception as e:
            print_error(f"{index_name}: 删除失败 - {e}")
            logger.error(f"删除索引 {index_name} 文档失败: {e}", exc_info=True)
            results[index_name] = {"deleted": 0, "failed": -1, "error": str(e)}

    return results


def confirm_action(prompt: str) -> bool:
    """
    请求用户确认

    Returns:
        bool: 用户是否确认
    """
    print()
    user_input = input(f"  {prompt} (输入 'yes' 确认): ").strip().lower()
    return user_input == "yes"


async def main() -> None:
    """主函数"""
    es_client = None

    try:
        print_header("ES 软删除文档物理删除工具")
        logger.info("=" * 60)
        logger.info("ES 软删除文档物理删除工具")
        logger.info("=" * 60)

        # ==================== 阶段 1: 环境确认 ====================
        print_header("环境信息确认")

        settings = get_settings()
        es_host = f"{settings.es_host}:{settings.es_port}"

        print_danger("这是一个不可逆操作，将永久删除 ES 中的文档！")
        print()
        print_info(f"Elasticsearch 地址: {es_host}")
        print()
        print_warning("请仔细确认 ES 地址是否正确！")

        if not confirm_action("确认 ES 地址正确，开始统计"):
            print_info("操作已取消")
            return

        # ==================== 阶段 2: 连接 ES ====================
        print_header("连接 Elasticsearch")

        es_config = ESConfig(
            hosts=f"{settings.es_host}:{settings.es_port}",
            username=settings.es_username,
            password=settings.es_password,
            scheme=settings.es_scheme,
        )
        es_client = ElasticsearchClient(config=es_config)

        if not await es_client.check_connection():
            print_error("Elasticsearch 连接失败")
            raise Exception("ES 连接失败")

        print_success("Elasticsearch 连接成功")

        # ==================== 阶段 3: 统计文档 ====================
        counts = await count_soft_deleted_documents(es_client)

        total_count = sum(c for c in counts.values() if c > 0)

        if total_count == 0:
            print_header("统计结果")
            print_success("没有需要删除的文档（is_delete=true）")
            return

        # ==================== 阶段 4: 确认删除 ====================
        print_header("删除确认")

        print_danger("警告：以下操作不可逆！")
        print()
        print_info(f"Elasticsearch 地址: {es_host}")
        print()
        print_warning(f"即将永久删除 {total_count} 条文档")
        print()

        for index_name, count in counts.items():
            if count > 0:
                print_info(f"  {index_name}: {count} 条")

        if not confirm_action("确认执行永久删除"):
            print_info("操作已取消")
            return

        # ==================== 阶段 5: 执行删除 ====================
        delete_results = await delete_soft_deleted_documents(es_client, counts)

        # ==================== 阶段 6: 总结 ====================
        print_header("操作总结")

        total_deleted = sum(r.get("deleted", 0) for r in delete_results.values())
        total_failed = sum(r.get("failed", 0) for r in delete_results.values() if r.get("failed", 0) > 0)

        print_success(f"成功删除: {total_deleted} 条文档")

        if total_failed > 0:
            print_warning(f"失败: {total_failed} 条")

        print_success("物理删除完成！")

        logger.info("=" * 60)
        logger.info(f"✓ ES 软删除文档物理删除完成！删除 {total_deleted} 条文档")
        logger.info("=" * 60)

        print("=" * 70 + "\n")

    except Exception as e:
        print_error(f"操作失败: {e}")
        logger.error(f"ES 软删除文档物理删除失败: {e}", exc_info=True)
        sys.exit(1)

    finally:
        # 关闭连接
        if es_client:
            await es_client.close()


if __name__ == "__main__":
    asyncio.run(main())
