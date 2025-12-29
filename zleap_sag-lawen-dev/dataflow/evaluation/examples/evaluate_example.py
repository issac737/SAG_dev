"""
Evaluate 类使用示例

演示如何使用 Evaluate 类进行评估
"""

import sys
from typing import List

# 添加项目路径
sys.path.insert(0, '.')

from dataflow.evaluation.benchmark import Evaluate, EvaluationConfig, quick_evaluate


def example_1_basic_usage():
    """示例1：基本使用 - 加载数据集"""
    print("=" * 60)
    print("示例1：基本使用 - 加载数据集")
    print("=" * 60)

    # 创建评估器
    config = EvaluationConfig(
        dataset_name='musique',
        max_samples=10,  # 只使用10个样本进行快速测试
        save_results=False,
        verbose=True
    )

    evaluator = Evaluate(config)

    # 加载数据集
    dataset_info = evaluator.load_dataset()
    print("\n数据集信息:")
    for key, value in dataset_info.items():
        if key != 'stats':
            print(f"  {key}: {value}")

    # 获取数据
    questions = evaluator.get_questions()
    gold_answers = evaluator.get_gold_answers()

    print(f"\n前3个问题:")
    for i, (q, a) in enumerate(zip(questions[:3], gold_answers[:3])):
        print(f"\n问题 {i+1}: {q}")
        print(f"答案: {a}")


def example_2_qa_evaluation():
    """示例2：QA评估"""
    print("\n" + "=" * 60)
    print("示例2：QA评估")
    print("=" * 60)

    config = EvaluationConfig(
        dataset_name='musique',
        max_samples=10,
        evaluate_retrieval=False,
        evaluate_qa=True,
        save_results=False
    )

    evaluator = Evaluate(config)
    evaluator.load_dataset()

    # 模拟预测答案（这里用gold答案的第一个作为预测，测试评估功能）
    predicted_answers = [list(ans_set)[0] if ans_set else "" for ans_set in evaluator.get_gold_answers()]

    # 运行QA评估
    qa_results = evaluator.evaluate_qa(predicted_answers)

    print("\nQA评估结果:")
    print(f"  指标: {qa_results['metrics']}")
    print(f"  汇总结果:")
    for metric, score in qa_results['pooled'].items():
        print(f"    {metric}: {score:.4f}")


def example_3_retrieval_evaluation():
    """示例3：检索评估"""
    print("\n" + "=" * 60)
    print("示例3：检索评估")
    print("=" * 60)

    config = EvaluationConfig(
        dataset_name='musique',
        max_samples=10,
        evaluate_retrieval=True,
        evaluate_qa=False,
        retrieval_top_k_list=[1, 5, 10],
        save_results=False
    )

    evaluator = Evaluate(config)
    evaluator.load_dataset()

    # 模拟检索结果（这里用gold_docs作为检索结果，测试评估功能）
    # 实际使用时，这应该是你的检索系统的输出
    gold_docs = evaluator.get_gold_docs()

    if gold_docs is None:
        print("该数据集没有gold_docs，跳过检索评估")
        return

    # 模拟检索结果：gold_docs + 一些噪声文档
    all_docs = evaluator.get_docs()
    retrieved_docs_list = []

    for gold_doc_list in gold_docs:
        # 将 gold_docs 放在前面，然后添加一些随机文档
        retrieved = gold_doc_list[:5]  # 取前5个gold docs
        # 添加一些其他文档（从corpus中随机选择）
        import random
        other_docs = random.sample(all_docs, min(5, len(all_docs)))
        retrieved.extend(other_docs)
        retrieved_docs_list.append(retrieved[:10])  # 只保留前10个

    # 运行检索评估
    retrieval_results = evaluator.evaluate_retrieval(retrieved_docs_list)

    print("\n检索评估结果:")
    print(f"  指标: {retrieval_results['metrics']}")
    print(f"  汇总结果:")
    for metric, score in retrieval_results['pooled'].items():
        print(f"    {metric}: {score:.4f}")


def example_4_full_evaluation():
    """示例4：完整评估流程"""
    print("\n" + "=" * 60)
    print("示例4：完整评估流程")
    print("=" * 60)

    config = EvaluationConfig(
        dataset_name='musique',
        max_samples=5,
        evaluate_retrieval=True,
        evaluate_qa=True,
        save_results=True,
        output_dir='outputs/evaluation'
    )

    evaluator = Evaluate(config)
    evaluator.load_dataset()

    # 准备模拟数据
    gold_answers_list = evaluator.get_gold_answers()
    gold_docs = evaluator.get_gold_docs()

    # 模拟预测答案
    predicted_answers = [list(ans_set)[0] if ans_set else "" for ans_set in gold_answers_list]

    # 模拟检索结果
    if gold_docs is not None:
        retrieved_docs_list = [docs[:5] for docs in gold_docs]
    else:
        retrieved_docs_list = None

    # 运行完整评估
    results = evaluator.evaluate_all(
        retrieved_docs_list=retrieved_docs_list,
        predicted_answers=predicted_answers
    )

    # 打印摘要
    evaluator.print_summary(results)


def example_5_quick_evaluate():
    """示例5：使用便捷函数"""
    print("\n" + "=" * 60)
    print("示例5：使用便捷函数 quick_evaluate")
    print("=" * 60)

    # 模拟数据（实际使用时，这些应该是你的系统输出）
    # 这里我们先加载数据集来获取模拟数据
    from dataflow.evaluation.utils import load_dataset

    docs, questions, gold_answers, gold_docs = load_dataset('musique')

    # 只取前5个样本
    questions = questions[:5]
    gold_answers = gold_answers[:5]
    if gold_docs:
        gold_docs = gold_docs[:5]

    # 模拟预测
    predicted_answers = [list(ans_set)[0] if ans_set else "" for ans_set in gold_answers]
    retrieved_docs_list = [docs[:5] for docs in gold_docs] if gold_docs else None

    # 快速评估
    results = quick_evaluate(
        dataset_name='musique',
        retrieved_docs_list=retrieved_docs_list,
        predicted_answers=predicted_answers,
        max_samples=5
    )


def example_6_different_datasets():
    """示例6：评估不同数据集"""
    print("\n" + "=" * 60)
    print("示例6：评估不同数据集")
    print("=" * 60)

    datasets = ['musique', 'hotpotqa', '2wikimultihopqa']

    for dataset_name in datasets:
        print(f"\n--- {dataset_name} ---")

        config = EvaluationConfig(
            dataset_name=dataset_name,
            max_samples=5,
            save_results=False
        )

        evaluator = Evaluate(config)
        info = evaluator.load_dataset()

        print(f"  文档数: {info['num_docs']}")
        print(f"  问题数: {info['num_questions']}")
        print(f"  有gold_docs: {info['has_gold_docs']}")


if __name__ == "__main__":
    # 运行示例
    example_1_basic_usage()
    example_2_qa_evaluation()
    example_3_retrieval_evaluation()
    example_4_full_evaluation()
    # example_5_quick_evaluate()  # 这个会保存文件，可选运行
    example_6_different_datasets()

    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)
