"""
关键词提取测试 - CSV 输出模式

仅使用非 LLM 模式（tokenizer 模式）提取关键词，并将结果保存为 CSV 文件。

运行方式：
    python tests/ai/test_tokenizer_entities_csv.py
"""

import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataflow.core.ai.tokensize import get_keyword_extractor


def read_test_file(file_path):
    """读取测试文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return None


def save_keyword_counts_to_csv(keyword_counts, output_file):
    """将关键词频次保存为 CSV 格式"""
    try:
        with open(output_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            # 写入表头
            writer.writerow(['关键词', '出现频次'])

            # 写入数据（按频次降序排序）
            for keyword, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True):
                writer.writerow([keyword, count])

        print(f"✅ 关键词频次已保存到: {output_file}")
    except Exception as e:
        print(f"❌ 保存 CSV 失败: {e}")


def split_into_paragraphs(text):
    """将文本拆分为段落"""
    # 按空行分割段落
    paragraphs = []
    current_paragraph = []

    for line in text.split('\n'):
        line = line.strip()
        if line:
            current_paragraph.append(line)
        else:
            if current_paragraph:
                paragraphs.append(' '.join(current_paragraph))
                current_paragraph = []

    if current_paragraph:
        paragraphs.append(' '.join(current_paragraph))

    return paragraphs


def main():
    """主测试函数"""
    print("=" * 70)
    print("关键词提取 - CSV 输出测试")
    print("仅使用 tokenizer 模式（非 LLM 模式）")
    print("=" * 70)

    # 开始计时
    start_time = time.time()

    # 获取提取器实例（单例模式）
    extractor = get_keyword_extractor()

    # 测试文件路径
    test_file = "tests/load/fixtures/LLM_Architecture.md"
    output_file = "test_tokenizer_keywords_output.csv"

    # 读取测试文件
    print(f"\n📖 正在读取文件: {test_file}")
    read_start = time.time()
    text = read_test_file(test_file)
    read_time = time.time() - read_start

    if not text:
        print("❌ 无法读取测试文件")
        return

    print(f"✅ 文件读取成功，共 {len(text)} 个字符 (耗时: {read_time:.3f}s)")

    # 将文本拆分为段落
    split_start = time.time()
    paragraphs = split_into_paragraphs(text)
    split_time = time.time() - split_start
    print(f"✅ 共拆分为 {len(paragraphs)} 个段落 (耗时: {split_time:.3f}s)")

    # 提取关键词并统计频次
    print("\n🔍 开始提取关键词...")
    extract_start = time.time()
    keyword_counts = {}
    total_keywords = 0

    for idx, paragraph in enumerate(paragraphs, 1):
        if not paragraph.strip():
            continue

        # 只使用 tokenizer 模式提取关键词
        keywords = extractor.extract(paragraph)

        # 统计关键词频次
        for keyword in keywords:
            keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
            total_keywords += 1

        # 显示进度
        if idx % 10 == 0:
            print(f"  已处理 {idx}/{len(paragraphs)} 个段落...", end="\r")

    extract_time = time.time() - extract_start
    print(f"\n✅ 关键词提取完成")
    print(f"  - 处理段落数: {len(paragraphs)}")
    print(f"  - 提取关键词总数: {total_keywords}")
    print(f"  - 唯一关键词数: {len(keyword_counts)}")
    print(f"  - 提取耗时: {extract_time:.3f}s")

    # 将结果保存为 CSV
    print("\n💾 保存结果到 CSV 文件...")
    save_start = time.time()
    save_keyword_counts_to_csv(keyword_counts, output_file)
    save_time = time.time() - save_start
    print(f"  - 保存耗时: {save_time:.3f}s")

    # 显示统计信息
    print("\n" + "=" * 70)
    print("统计信息:")
    print(f"  - 总段落数: {len(paragraphs)}")
    print(f"  - 总关键词数: {total_keywords}")
    print(f"  - 唯一关键词数: {len(keyword_counts)}")
    print(f"  - 平均每段落关键词数: {total_keywords / len(paragraphs):.2f}")
    print("=" * 70)

    # 显示前20个高频关键词
    sorted_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)

    print("\nTop 20 高频关键词:")
    for i, (keyword, count) in enumerate(sorted_keywords[:20], 1):
        print(f"  {i:2d}. {keyword} ({count} 次)")
    print("=" * 70)

    # 总耗时
    total_time = time.time() - start_time
    print(f"\n⏱️  总耗时: {total_time:.3f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
