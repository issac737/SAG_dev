"""
DatasetLoader 使用示例

演示如何使用 DatasetLoader 加载数据集
"""

from dataflow.evaluation.utils import DatasetLoader, load_dataset


def example_1_basic_usage():
    """示例1：基本使用 - 使用 DatasetLoader 类"""
    print("=" * 60)
    print("示例1：使用 DatasetLoader 类加载数据")
    print("=" * 60)

    # 创建加载器
    loader = DatasetLoader('musique')

    # 获取统计信息
    stats = loader.get_stats()
    print("\n数据集统计信息:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # 加载各类数据
    corpus = loader.load_corpus()
    print(f"\n加载了 {len(corpus)} 个文档")

    samples = loader.load_samples()
    print(f"加载了 {len(samples)} 个样本")

    questions = loader.get_questions()
    print(f"提取了 {len(questions)} 个问题")

    gold_answers = loader.get_gold_answers()
    print(f"提取了 {len(gold_answers)} 个gold answers")

    gold_docs = loader.get_gold_docs()
    if gold_docs:
        print(f"提取了 {len(gold_docs)} 个gold docs")

    # 查看第一个样本
    print("\n第一个样本:")
    print(f"  问题: {questions[0]}")
    print(f"  答案: {gold_answers[0]}")
    if gold_docs:
        print(f"  支持文档数量: {len(gold_docs[0])}")
        print(f"  第一个支持文档: {gold_docs[0][0][:100]}...")


def example_2_convenience_function():
    """示例2：使用便捷函数"""
    print("\n" + "=" * 60)
    print("示例2：使用便捷函数 load_dataset")
    print("=" * 60)

    # 一次性加载所有常用数据
    docs, questions, gold_answers, gold_docs = load_dataset('hotpotqa')

    print(f"\n加载的数据:")
    print(f"  文档数量: {len(docs)}")
    print(f"  问题数量: {len(questions)}")
    print(f"  Gold answers: {len(gold_answers)}")
    print(f"  Gold docs: {len(gold_docs) if gold_docs else 'None'}")

    # 查看示例
    print(f"\n第一个问题: {questions[0]}")
    print(f"第一个答案: {gold_answers[0]}")


def example_3_all_datasets():
    """示例3：加载所有支持的数据集"""
    print("\n" + "=" * 60)
    print("示例3：加载所有支持的数据集")
    print("=" * 60)

    datasets = ['musique', 'hotpotqa', '2wikimultihopqa']

    for dataset_name in datasets:
        print(f"\n{dataset_name}:")
        loader = DatasetLoader(dataset_name)
        stats = loader.get_stats()

        print(f"  Corpus文档: {stats['num_corpus_docs']}")
        print(f"  问题数量: {stats['num_questions']}")
        print(f"  平均每题支持文档: {stats.get('avg_supporting_docs_per_question', 'N/A'):.2f}")


def example_4_iterate_samples():
    """示例4：遍历样本进行处理"""
    print("\n" + "=" * 60)
    print("示例4：遍历样本进行处理")
    print("=" * 60)

    loader = DatasetLoader('musique')

    questions = loader.get_questions()
    gold_answers = loader.get_gold_answers()
    gold_docs = loader.get_gold_docs()

    # 处理前5个样本
    print("\n处理前5个样本:")
    for i in range(min(5, len(questions))):
        print(f"\n样本 {i + 1}:")
        print(f"  问题: {questions[i]}")
        print(f"  答案: {gold_answers[i]}")
        if gold_docs:
            print(f"  支持文档数: {len(gold_docs[i])}")


def example_5_custom_dataset_dir():
    """示例5：使用自定义数据集目录"""
    print("\n" + "=" * 60)
    print("示例5：使用自定义数据集目录")
    print("=" * 60)

    # 默认使用 dataflow/evaluation/dataset
    loader = DatasetLoader('musique')
    print(f"默认数据集目录: {loader.dataset_dir}")

    # 也可以指定自定义目录
    # loader = DatasetLoader('musique', dataset_dir='/path/to/custom/dataset')


def example_6_print_first_10_questions():
    """示例6：打印前10个问题"""
    print("\n" + "=" * 60)
    print("示例6：打印前10个问题（含支持文档）")
    print("=" * 60)

    # 创建加载器
    loader = DatasetLoader('2wikimultihopqa')

    # 获取问题、答案和支持文档
    questions = loader.get_questions()
    gold_answers = loader.get_gold_answers()
    gold_docs = loader.get_gold_docs()

    # 打印前10个问题
    print(f"\n前10个问题及其信息：\n")
    for i in range(min(10, len(questions))):
        print(f"问题 {i+1}: {questions[i]}")
        print(f"  答案: {gold_answers[i]}")
        if gold_docs:
            print(f"  支持文档数: {len(gold_docs[i])}")
            # 打印每个支持文档的预览
            for doc_idx, doc in enumerate(gold_docs[i]):
                print(f"  支持文档 {doc_idx+1}:")
                print(f"    {doc[:150]}...")
        print()


if __name__ == "__main__":
    # 运行所有示例
    # example_1_basic_usage()
    # example_2_convenience_function()
    # example_3_all_datasets()
    # example_4_iterate_samples()
    # example_5_custom_dataset_dir()
    example_6_print_first_10_questions()

    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)
