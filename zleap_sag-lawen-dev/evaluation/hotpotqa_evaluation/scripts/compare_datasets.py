"""
HotpotQA 数据集对比脚本

对比 distractor 和 fullwiki 两个数据集的格式和统计信息

使用方法:
    python compare_datasets.py
    python compare_datasets.py --limit 100  # 限制加载样本数量
    python compare_datasets.py --show-samples  # 显示样本示例
"""

import sys
from pathlib import Path
import argparse

# 添加父目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from modules.hotpotqa_loader import HotpotQALoader
import config as hotpot_config


def compare_datasets(limit: int = None, show_samples: bool = False):
    """对比两个数据集"""

    # 检查数据集路径
    if not hotpot_config.HOTPOTQA_DATASET_PATH:
        print("❌ 错误：未设置 HOTPOTQA_DATASET_PATH 环境变量")
        print("请在 .env 文件中配置: HOTPOTQA_DATASET_PATH=/your/path/to/hotpotqa")
        return

    print(f"📁 数据集路径: {hotpot_config.HOTPOTQA_DATASET_PATH}")
    print(f"📊 加载样本数: {'全部' if limit is None else limit}")
    print("=" * 80)

    # 初始化加载器
    loader = HotpotQALoader(hotpot_config.HOTPOTQA_DATASET_PATH)

    # 加载两个数据集
    print("\n🔄 加载 distractor 数据集...")
    distractor_samples = loader.load_validation(config="distractor", limit=limit)

    print("\n🔄 加载 fullwiki 数据集...")
    fullwiki_samples = loader.load_validation(config="fullwiki", limit=limit)

    # 分析统计信息
    print("\n📈 分析数据集统计信息...")
    distractor_stats = loader.analyze_dataset(distractor_samples)
    fullwiki_stats = loader.analyze_dataset(fullwiki_samples)

    # 打印对比结果
    print("\n" + "=" * 80)
    print("📊 数据集对比结果")
    print("=" * 80)

    # 样本数量
    print(f"\n【样本数量】")
    print(f"  distractor:  {distractor_stats['total_samples']:>6} 个")
    print(f"  fullwiki:    {fullwiki_stats['total_samples']:>6} 个")

    # 平均上下文文档数量（关键差异）
    print(f"\n【平均上下文文档数量】⭐ 主要差异")
    print(f"  distractor:  {distractor_stats['avg_contexts']:>6.2f} 个/问题")
    print(f"  fullwiki:    {fullwiki_stats['avg_contexts']:>6.2f} 个/问题")
    print(f"  📌 说明: distractor 固定为 10 个文档（2个相关+8个干扰）")
    print(f"         fullwiki 从整个 Wikipedia 检索，数量更多")

    # 平均 supporting facts 数量
    print(f"\n【平均 Supporting Facts 数量】")
    print(f"  distractor:  {distractor_stats['avg_supporting_facts']:>6.2f} 个/问题")
    print(f"  fullwiki:    {fullwiki_stats['avg_supporting_facts']:>6.2f} 个/问题")

    # 问题类型分布
    print(f"\n【问题类型分布】")
    all_types = set(distractor_stats['question_types'].keys()) | set(fullwiki_stats['question_types'].keys())
    for q_type in sorted(all_types):
        d_count = distractor_stats['question_types'].get(q_type, 0)
        f_count = fullwiki_stats['question_types'].get(q_type, 0)
        d_pct = d_count / distractor_stats['total_samples'] * 100 if distractor_stats['total_samples'] > 0 else 0
        f_pct = f_count / fullwiki_stats['total_samples'] * 100 if fullwiki_stats['total_samples'] > 0 else 0
        print(f"  {q_type:20s}  distractor: {d_count:>4} ({d_pct:>5.1f}%)  fullwiki: {f_count:>4} ({f_pct:>5.1f}%)")

    # 难度级别分布
    print(f"\n【难度级别分布】")
    all_levels = set(distractor_stats['difficulty_levels'].keys()) | set(fullwiki_stats['difficulty_levels'].keys())
    for level in sorted(all_levels):
        d_count = distractor_stats['difficulty_levels'].get(level, 0)
        f_count = fullwiki_stats['difficulty_levels'].get(level, 0)
        d_pct = d_count / distractor_stats['total_samples'] * 100 if distractor_stats['total_samples'] > 0 else 0
        f_pct = f_count / fullwiki_stats['total_samples'] * 100 if fullwiki_stats['total_samples'] > 0 else 0
        print(f"  {level:20s}  distractor: {d_count:>4} ({d_pct:>5.1f}%)  fullwiki: {f_count:>4} ({f_pct:>5.1f}%)")

    # 数据格式说明
    print(f"\n【数据格式】")
    print(f"  ✅ 两个数据集的字段结构完全相同:")
    print(f"     - id: 样本ID")
    print(f"     - question: 问题")
    print(f"     - answer: 答案")
    print(f"     - type: 问题类型 (comparison/bridge)")
    print(f"     - level: 难度级别 (easy/medium/hard)")
    print(f"     - context: 上下文文档 {{title: [...], sentences: [...]}}")
    print(f"     - supporting_facts: 支持事实 {{title: [...], sent_id: [...]}}")

    # 显示样本示例
    if show_samples:
        print("\n" + "=" * 80)
        print("📝 样本示例对比")
        print("=" * 80)

        if distractor_samples and fullwiki_samples:
            print("\n🔹 DISTRACTOR 样本示例:")
            print_sample_summary(distractor_samples[0])

            print("\n🔹 FULLWIKI 样本示例:")
            print_sample_summary(fullwiki_samples[0])

    print("\n" + "=" * 80)
    print("✅ 对比完成")
    print("=" * 80)


def print_sample_summary(sample: dict):
    """打印样本摘要信息"""
    print(f"  ID: {sample['id']}")
    print(f"  Question: {sample['question']}")
    print(f"  Answer: {sample['answer']}")
    print(f"  Type: {sample['type']} | Level: {sample['level']}")
    print(f"  上下文文档数量: {len(sample['context']['title'])} 个")
    print(f"  Supporting Facts: {len(sample['supporting_facts']['title'])} 个")

    # 列出上下文文档标题
    print(f"  上下文文档标题:")
    for i, title in enumerate(sample['context']['title'], 1):
        sentences_count = len(sample['context']['sentences'][i-1])
        print(f"    {i}. {title} ({sentences_count} 句)")


def main():
    parser = argparse.ArgumentParser(description="对比 HotpotQA distractor 和 fullwiki 数据集")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制加载的样本数量（默认加载全部）"
    )
    parser.add_argument(
        "--show-samples",
        action="store_true",
        help="显示样本示例"
    )

    args = parser.parse_args()

    compare_datasets(limit=args.limit, show_samples=args.show_samples)


if __name__ == "__main__":
    main()
