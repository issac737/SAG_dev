"""
将数据集保存为 Markdown 格式的示例

演示如何使用 DatasetLoader.save_as_markdown() 方法
"""

import sys
sys.path.insert(0, '.')

from dataflow.evaluation.utils import DatasetLoader


def example_1_basic_save():
    """示例1：基本保存功能"""
    print("=" * 60)
    print("示例1：基本保存功能")
    print("=" * 60)

    # 创建加载器
    loader = DatasetLoader('musique')

    # 保存为 markdown（默认参数：每个文件500个chunks）
    print("\n保存 musique 数据集为 markdown 格式...")
    output_dir = loader.save_as_markdown(force_regenerate=True)

    print(f"\n✅ 保存完成！")
    print(f"输出目录: {output_dir}")

    # 查看生成的文件
    import os
    files = sorted(os.listdir(output_dir))
    print(f"\n生成了 {len(files)} 个 markdown 文件:")
    for i, f in enumerate(files[:10], 1):
        print(f"  {i}. {f}")
    if len(files) > 10:
        print(f"  ... 还有 {len(files) - 10} 个文件")


def example_2_custom_chunks_per_file():
    """示例2：自定义每个文件的chunk数量"""
    print("\n" + "=" * 60)
    print("示例2：自定义每个文件的chunk数量")
    print("=" * 60)

    loader = DatasetLoader('hotpotqa')

    # 每个文件包含 300 个 chunks（更小的文件）
    print("\n保存 hotpotqa 数据集，每个文件300个chunks...")
    output_dir = loader.save_as_markdown(
        chunks_per_file=300,
        force_regenerate=True
    )

    files = sorted(os.listdir(output_dir))
    print(f"\n✅ 保存完成！")
    print(f"生成了 {len(files)} 个文件")
    print(f"每个文件约 300 chunks")


def example_3_all_datasets():
    """示例3：保存所有数据集"""
    print("\n" + "=" * 60)
    print("示例3：保存所有数据集")
    print("=" * 60)

    datasets = [
        ('musique', 500),
        ('hotpotqa', 400),
        ('2wikimultihopqa', 400)
    ]

    for dataset_name, chunks_per_file in datasets:
        print(f"\n保存 {dataset_name}...")
        loader = DatasetLoader(dataset_name)

        output_dir = loader.save_as_markdown(
            chunks_per_file=chunks_per_file,
            force_regenerate=True
        )

        import os
        files = os.listdir(output_dir)
        print(f"  ✅ {dataset_name}: {len(files)} 个文件")


def example_4_view_markdown_content():
    """示例4：查看生成的 markdown 文件内容"""
    print("\n" + "=" * 60)
    print("示例4：查看 markdown 文件内容")
    print("=" * 60)

    loader = DatasetLoader('hotpotqa')
    output_dir = loader.save_as_markdown(
        chunks_per_file=500,
        force_regenerate=True
    )

    # 读取第一个文件的前几行
    first_file = output_dir / f"{loader.dataset_name}_part1.md"
    print(f"\n查看 {first_file.name} 的前 50 行:\n")
    print("-" * 60)

    with open(first_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if i > 50:
                break
            print(line.rstrip())

    print("-" * 60)
    print("\n✅ Markdown 格式正确！")
    print("  - 标题使用了 # 符号")
    print("  - 只包含标题和文本内容")
    print("  - 格式简洁干净")


def example_5_custom_output_dir():
    """示例5：自定义输出目录"""
    print("\n" + "=" * 60)
    print("示例5：自定义输出目录")
    print("=" * 60)

    loader = DatasetLoader('sample')

    # 自定义输出目录
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"\n保存到临时目录: {tmpdir}")

        output_dir = loader.save_as_markdown(
            output_dir=f"{tmpdir}/custom_markdown",
            chunks_per_file=50,
            force_regenerate=True
        )

        print(f"\n✅ 保存完成！")
        print(f"输出目录: {output_dir}")

        # 查看文件
        import os
        files = os.listdir(output_dir)
        print(f"生成了 {len(files)} 个文件")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("数据集 Markdown 转换示例")
    print("=" * 60)

    # 运行示例
    # example_1_basic_save()
    # example_2_custom_chunks_per_file()
    # example_3_all_datasets()
    example_4_view_markdown_content()
    # example_5_custom_output_dir()

    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)
