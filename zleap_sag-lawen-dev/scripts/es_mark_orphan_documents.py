"""
ES 孤立文档标记脚本

扫描三个 ES 索引，找出 source_config_id 不存在于 MySQL 中的文档，
输出为 CSV 并标记软删除。

安全措施：
- 打印 ES 和 MySQL 地址供确认
- 输出 CSV 供审计
- 随机抽样验证
- 执行前二次确认
"""

import asyncio
import csv
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Set

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from dataflow.core.config import get_settings
from dataflow.core.storage.elasticsearch import ElasticsearchClient, ESConfig
from dataflow.db import SourceConfig, get_session_factory
from dataflow.db.base import close_database
from dataflow.utils import get_logger

logger = get_logger("scripts.es_mark_orphan_documents")

# 需要扫描的索引列表
TARGET_INDICES = [
    "entity_vectors",
    "event_vectors",
    "source_chunks",
]

# 批量处理大小
BATCH_SIZE = 1000


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


async def get_valid_source_config_ids() -> Set[str]:
    """
    从 MySQL 获取所有有效的 source_config_id

    Returns:
        Set[str]: 有效的 source_config_id 集合
    """
    print_info("正在从 MySQL 获取有效的 source_config_id...")

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(SourceConfig.id))
        ids = {row[0] for row in result.fetchall()}

    print_success(f"获取到 {len(ids)} 个有效的 source_config_id")
    return ids


async def scan_index_for_orphans(
    es_client: ElasticsearchClient,
    index_name: str,
    valid_ids: Set[str]
) -> Dict[str, int]:
    """
    扫描单个索引，找出孤立的 source_config_id

    使用 ES composite aggregation 按 source_config_id 分组统计，
    避免遍历每条文档，大幅提升性能。

    Args:
        es_client: ES 客户端
        index_name: 索引名称
        valid_ids: 有效的 source_config_id 集合

    Returns:
        Dict[str, int]: 孤立的 source_config_id -> 文档数量
    """
    print_info(f"正在扫描索引: {index_name}...")

    orphan_counts: Dict[str, int] = {}
    total_source_configs = 0
    orphan_source_configs = 0
    total_orphan_docs = 0

    try:
        # 使用 composite aggregation 分页获取所有 source_config_id 及其文档数
        # composite aggregation 支持分页，可处理高基数字段
        after_key = None

        while True:
            agg_query = {
                "composite": {
                    "size": BATCH_SIZE,
                    "sources": [
                        {"source_config_id": {"terms": {"field": "source_config_id"}}}
                    ]
                }
            }

            # 添加分页 after_key
            if after_key:
                agg_query["composite"]["after"] = after_key

            response = await es_client.client.search(
                index=index_name,
                size=0,  # 不需要返回文档，只要聚合结果
                aggs={"by_source_config": agg_query}
            )

            buckets = response["aggregations"]["by_source_config"]["buckets"]

            if not buckets:
                break

            for bucket in buckets:
                source_config_id = bucket["key"]["source_config_id"]
                doc_count = bucket["doc_count"]
                total_source_configs += 1

                # 在 Python 端过滤出孤立的 source_config_id
                if source_config_id not in valid_ids:
                    orphan_counts[source_config_id] = doc_count
                    orphan_source_configs += 1
                    total_orphan_docs += doc_count

            # 获取下一页的 after_key
            after_key = response["aggregations"]["by_source_config"].get("after_key")
            if not after_key:
                break

    except Exception as e:
        logger.error(f"扫描索引 {index_name} 失败: {e}", exc_info=True)
        raise

    print_info(f"  {index_name}: 总 source_config_id {total_source_configs}, "
               f"孤立 {orphan_source_configs} 个 (共 {total_orphan_docs} 条文档)")

    return orphan_counts


async def scan_all_indices(
    es_client: ElasticsearchClient,
    valid_ids: Set[str]
) -> Dict[str, Dict[str, int]]:
    """
    并行扫描所有目标索引

    Returns:
        Dict[str, Dict[str, int]]: 索引名 -> (source_config_id -> 文档数量)
    """
    print_header("扫描 ES 索引")

    # 先检查哪些索引存在
    existing_indices = []
    for index_name in TARGET_INDICES:
        exists = await es_client.index_exists(index_name)
        if not exists:
            print_warning(f"{index_name}: 索引不存在，跳过")
        else:
            existing_indices.append(index_name)

    if not existing_indices:
        return {}

    # 并行扫描所有存在的索引
    tasks = [
        scan_index_for_orphans(es_client, index_name, valid_ids)
        for index_name in existing_indices
    ]
    scan_results = await asyncio.gather(*tasks)

    return dict(zip(existing_indices, scan_results))


def save_to_csv(scan_results: Dict[str, Dict[str, int]], output_dir: Path) -> str:
    """
    将扫描结果保存到 CSV 文件

    Args:
        scan_results: 扫描结果
        output_dir: 输出目录

    Returns:
        str: CSV 文件路径
    """
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"orphan_source_configs_{timestamp}.csv"

    # 写入 CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["index_name", "source_config_id", "document_count"])

        for index_name, orphan_counts in scan_results.items():
            for source_config_id, count in orphan_counts.items():
                writer.writerow([index_name, source_config_id, count])

    return str(csv_path)


def get_random_samples(scan_results: Dict[str, Dict[str, int]], count: int = 5) -> list:
    """
    从扫描结果中随机抽取样本

    Returns:
        list: [(index_name, source_config_id, doc_count), ...]
    """
    all_orphans = []
    for index_name, orphan_counts in scan_results.items():
        for source_config_id, doc_count in orphan_counts.items():
            all_orphans.append((index_name, source_config_id, doc_count))

    if len(all_orphans) <= count:
        return all_orphans

    return random.sample(all_orphans, count)


def calculate_total_stats(scan_results: Dict[str, Dict[str, int]]) -> dict:
    """
    计算总体统计信息

    Returns:
        dict: {total_docs, total_orphan_ids, by_index: {index: {docs, ids}}}
    """
    total_docs = 0
    total_orphan_ids = set()
    by_index = {}

    for index_name, orphan_counts in scan_results.items():
        index_docs = sum(orphan_counts.values())
        index_ids = len(orphan_counts)

        total_docs += index_docs
        total_orphan_ids.update(orphan_counts.keys())

        by_index[index_name] = {
            "docs": index_docs,
            "ids": index_ids
        }

    return {
        "total_docs": total_docs,
        "total_orphan_ids": len(total_orphan_ids),
        "by_index": by_index
    }


async def mark_documents_as_deleted(
    es_client: ElasticsearchClient,
    scan_results: Dict[str, Dict[str, int]]
) -> Dict[str, dict]:
    """
    将孤立文档标记为软删除

    Returns:
        Dict[str, dict]: 索引名 -> 更新结果
    """
    print_header("标记软删除")

    results = {}

    for index_name, orphan_counts in scan_results.items():
        if not orphan_counts:
            print_info(f"{index_name}: 无需更新")
            results[index_name] = {"updated": 0, "failed": 0}
            continue

        orphan_ids = list(orphan_counts.keys())
        print_info(f"{index_name}: 正在更新 {len(orphan_ids)} 个 source_config_id 的文档...")

        try:
            # 使用 update_by_query 批量更新
            response = await es_client.client.update_by_query(
                index=index_name,
                query={
                    "terms": {
                        "source_config_id": orphan_ids
                    }
                },
                script={
                    "source": "ctx._source.is_delete = true",
                    "lang": "painless"
                },
                conflicts="proceed",
                refresh=True
            )

            updated = response.get("updated", 0)
            failures = len(response.get("failures", []))

            results[index_name] = {
                "updated": updated,
                "failed": failures
            }

            if failures > 0:
                print_warning(f"{index_name}: 更新 {updated} 条，失败 {failures} 条")
            else:
                print_success(f"{index_name}: 更新 {updated} 条")

        except Exception as e:
            print_error(f"{index_name}: 更新失败 - {e}")
            logger.error(f"更新索引 {index_name} 失败: {e}", exc_info=True)
            results[index_name] = {"updated": 0, "failed": -1, "error": str(e)}

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
    settings = get_settings()

    try:
        print_header("ES 孤立文档标记工具")
        logger.info("=" * 60)
        logger.info("ES 孤立文档标记工具")
        logger.info("=" * 60)

        # ==================== 阶段 1: 环境确认 ====================
        print_header("环境信息确认")

        es_config = ESConfig(
            hosts=f"{settings.es_host}:{settings.es_port}",
            username=settings.es_username,
            password=settings.es_password,
            scheme=settings.es_scheme,
        )
        es_host = f"{settings.es_host}:{settings.es_port}"
        mysql_host = f"{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"

        print_danger("这是一个危险操作，将修改 ES 文档的软删除标记！")
        print()
        print_info(f"Elasticsearch 地址: {es_host}")
        print_info(f"MySQL 地址: {mysql_host}")
        print()
        print_warning("请仔细确认以上地址是否正确！")

        if not confirm_action("确认以上信息正确，开始扫描"):
            print_info("操作已取消")
            return

        # ==================== 阶段 2: 连接数据库 ====================
        print_header("连接数据库")

        # 连接 ES
        print_info("正在连接 Elasticsearch...")
        es_client = ElasticsearchClient(config=es_config)

        if not await es_client.check_connection():
            print_error("Elasticsearch 连接失败")
            raise Exception("ES 连接失败")

        print_success("Elasticsearch 连接成功")

        # 获取 MySQL 中的有效 ID
        valid_ids = await get_valid_source_config_ids()

        # ==================== 阶段 3: 扫描索引 ====================
        scan_results = await scan_all_indices(es_client, valid_ids)

        # ==================== 阶段 4: 输出 CSV ====================
        print_header("输出 CSV")

        output_dir = Path(__file__).parent / "output"
        csv_path = save_to_csv(scan_results, output_dir)

        print_success(f"CSV 已保存到: {csv_path}")

        # ==================== 阶段 5: 统计和确认 ====================
        stats = calculate_total_stats(scan_results)

        if stats["total_docs"] == 0:
            print_header("扫描结果")
            print_success("未发现孤立文档，无需处理")
            return

        print_header("扫描结果统计")
        print_info(f"总计需要标记的文档: {stats['total_docs']} 条")
        print_info(f"涉及的孤立 source_config_id: {stats['total_orphan_ids']} 个")
        print()

        for index_name, index_stats in stats["by_index"].items():
            print_info(f"  {index_name}: {index_stats['docs']} 条文档, "
                      f"{index_stats['ids']} 个 source_config_id")

        # 随机抽样验证
        print_header("随机抽样验证")
        print_warning("请手动验证以下 source_config_id 是否确实不存在于 MySQL 中：")
        print()

        samples = get_random_samples(scan_results, 5)
        for i, (index_name, source_config_id, doc_count) in enumerate(samples, 1):
            print_info(f"  {i}. [{index_name}] source_config_id: {source_config_id} "
                      f"(文档数: {doc_count})")

        print()
        print_danger("警告：以下操作将修改 ES 文档！")
        print()
        print_info(f"Elasticsearch 地址: {es_host}")
        print_info(f"MySQL 地址: {mysql_host}")
        print()
        print_warning(f"即将标记 {stats['total_docs']} 条文档为软删除状态")

        if not confirm_action("确认执行软删除标记"):
            print_info("操作已取消")
            return

        # ==================== 阶段 6: 执行软删除标记 ====================
        update_results = await mark_documents_as_deleted(es_client, scan_results)

        # ==================== 阶段 7: 总结 ====================
        print_header("操作总结")

        total_updated = sum(r.get("updated", 0) for r in update_results.values())
        total_failed = sum(r.get("failed", 0) for r in update_results.values() if r.get("failed", 0) > 0)

        print_success(f"成功标记: {total_updated} 条文档")

        if total_failed > 0:
            print_warning(f"失败: {total_failed} 条")

        print_info(f"CSV 文件: {csv_path}")
        print_success("软删除标记完成！")

        logger.info("=" * 60)
        logger.info(f"✓ ES 孤立文档标记完成！标记 {total_updated} 条文档")
        logger.info("=" * 60)

        print("=" * 70 + "\n")

    except Exception as e:
        print_error(f"操作失败: {e}")
        logger.error(f"ES 孤立文档标记失败: {e}", exc_info=True)
        sys.exit(1)

    finally:
        # 关闭连接
        if es_client:
            await es_client.close()
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
