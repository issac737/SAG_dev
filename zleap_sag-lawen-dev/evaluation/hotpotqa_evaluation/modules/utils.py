"""
HotpotQA 评估工具函数

包含：
- 文本处理
- 去重逻辑
- ID 映射
"""

import re
import string
from typing import List, Dict, Set


def purify_text(text: str) -> str:
    """
    去除标点和空格，生成纯净文本用于去重

    Args:
        text: 原始文本

    Returns:
        纯净文本（小写、无标点、无空格）
    """
    # 转小写
    text = text.lower()

    # 去除标点
    text = text.translate(str.maketrans('', '', string.punctuation))

    # 去除空格
    text = re.sub(r'\s+', '', text)

    return text


def merge_chunk_ids(id_list: List[str]) -> str:
    """
    合并多个 chunk ID

    Args:
        id_list: ID 列表

    Returns:
        合并后的 ID，格式: "id1//id2//id3"
    """
    return "//".join(sorted(set(id_list)))


def split_merged_id(merged_id: str) -> List[str]:
    """
    拆分合并的 ID

    Args:
        merged_id: 合并的 ID

    Returns:
        ID 列表
    """
    return merged_id.split("//")


def is_merged_id(chunk_id: str) -> bool:
    """
    检查是否是合并的 ID

    Args:
        chunk_id: chunk ID

    Returns:
        是否是合并的 ID
    """
    return "//" in chunk_id


def format_chunk_id(sample_id: str, local_index: int) -> str:
    """
    生成标准的 chunk ID

    Args:
        sample_id: 样本 ID
        local_index: 本地索引（从 0 开始）

    Returns:
        格式化的 chunk ID，如 "5a8b57f2-00"
    """
    return f"{sample_id}-{local_index:02d}"


def validate_chunk_id(chunk_id: str) -> bool:
    """
    验证 chunk ID 格式

    Args:
        chunk_id: chunk ID

    Returns:
        是否有效
    """
    # 单个ID格式: "xxx-00"
    # 合并ID格式: "xxx-00//yyy-01//zzz-02"

    if is_merged_id(chunk_id):
        ids = split_merged_id(chunk_id)
        return all(validate_single_chunk_id(id) for id in ids)
    else:
        return validate_single_chunk_id(chunk_id)


def validate_single_chunk_id(chunk_id: str) -> bool:
    """
    验证单个 chunk ID 格式

    Args:
        chunk_id: 单个 chunk ID

    Returns:
        是否有效
    """
    pattern = r'^[a-z0-9]+-\d{2}$'
    return bool(re.match(pattern, chunk_id))


class ChunkDeduplicator:
    """Chunk 去重器"""

    def __init__(self):
        # 纯净文本 -> chunk ID 列表的映射
        self.purity_to_ids: Dict[str, List[str]] = {}

        # chunk ID -> 合并后的 ID 的映射
        self.id_mapping: Dict[str, str] = {}

    def add_chunk(self, chunk_id: str, text: str) -> str:
        """
        添加 chunk 并处理去重

        Args:
            chunk_id: chunk ID
            text: chunk 文本

        Returns:
            最终的 chunk ID（可能是合并后的）
        """
        # 生成纯净文本
        purity = purify_text(text)

        if purity in self.purity_to_ids:
            # 已存在，合并 ID
            existing_ids = self.purity_to_ids[purity]
            existing_ids.append(chunk_id)

            # 生成合并 ID
            merged_id = merge_chunk_ids(existing_ids)

            # 更新所有相关 ID 的映射
            for id in existing_ids:
                self.id_mapping[id] = merged_id

            return merged_id
        else:
            # 新的 chunk
            self.purity_to_ids[purity] = [chunk_id]
            self.id_mapping[chunk_id] = chunk_id
            return chunk_id

    def get_mapped_id(self, chunk_id: str) -> str:
        """
        获取映射后的 ID

        Args:
            chunk_id: 原始 chunk ID

        Returns:
            映射后的 ID（可能是合并后的）
        """
        return self.id_mapping.get(chunk_id, chunk_id)

    def get_stats(self) -> Dict:
        """
        获取去重统计信息

        Returns:
            统计信息
        """
        total_chunks = len(self.id_mapping)
        unique_chunks = len(self.purity_to_ids)
        duplicates = total_chunks - unique_chunks

        return {
            "total_chunks": total_chunks,
            "unique_chunks": unique_chunks,
            "duplicates": duplicates,
            "dedup_rate": f"{duplicates / total_chunks * 100:.2f}%" if total_chunks > 0 else "0%"
        }


def print_stats(title: str, stats: Dict):
    """
    打印统计信息

    Args:
        title: 标题
        stats: 统计数据
    """
    print(f"\n{'=' * 60}")
    print(f"📊 {title}")
    print(f"{'=' * 60}")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print(f"{'=' * 60}\n")
