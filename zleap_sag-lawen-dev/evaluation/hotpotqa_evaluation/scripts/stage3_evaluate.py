"""
Stage3: 评估

功能：
1. 从 retrieval_results.jsonl 加载检索结果
2. 从 generated_answers.jsonl 加载生成的答案
3. 使用 RAGAs 计算评估指标
4. 生成评估报告

输入：
- retrieval_results.jsonl（Stage1 输出）
- generated_answers.jsonl（Stage2 输出）

输出：
- evaluation_report.json（评估报告）

使用方法：
    # 基本用法
    python stage3_evaluate.py --max-workers 16  

    # 自定义输入/输出路径
    python stage3_evaluate.py --retrieval data/retrieval_results.jsonl --answers data/generated_answers.jsonl --output data/report.json

    # 显示详细日志
    python stage3_evaluate.py --verbose
"""

import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import pandas as pd

# 添加 evaluation 目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 加载环境变量
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"[OK] 已加载环境变量: {env_path}")
else:
    print(f"[WARN] 未找到 .env 文件: {env_path}")

from hotpotqa_evaluation import config

# 导入 RAGAs
try:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )
    RAGAS_AVAILABLE = True
except ImportError:
    print("[WARN] RAGAs 未安装，请运行: pip install ragas datasets pillow")
    RAGAS_AVAILABLE = False

# 导入共享模块
from shared import (
    RetrievalResult,
    GeneratedAnswer,
    EvaluationReport,
    QuestionScore,
    read_jsonl,
    write_json,
    create_ragas_llm,
    create_ragas_embeddings,
    print_model_config,
)


def convert_to_ragas_format(
    retrieval_results: List[RetrievalResult],
    generated_answers: List[GeneratedAnswer]
) -> Dict[str, List]:
    """
    转换为 RAGAs 需要的格式

    Returns:
        {
            "question": [...],
            "answer": [...],
            "contexts": [...],
            "ground_truth": [...]
        }
    """
    questions = []
    answers = []
    contexts = []
    ground_truths = []

    for retrieval, answer in zip(retrieval_results, generated_answers):
        # question
        questions.append(retrieval.question)

        # answer (LLM生成的)
        answers.append(answer.generated_answer)

        # contexts (检索到的段落内容列表)
        retrieved_contexts = [
            section.content_preview
            for section in retrieval.retrieved_sections
        ]
        contexts.append(retrieved_contexts)

        # ground_truth (标准答案)
        ground_truths.append(retrieval.answer)

    return {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths
    }


def main():
    parser = argparse.ArgumentParser(description='Stage3: 评估')
    parser.add_argument('--retrieval', type=str,
                       default=str(config.DATA_DIR / "retrieval_results.jsonl"),
                       help='检索结果输入路径（Stage1 输出）')
    parser.add_argument('--answers', type=str,
                       default=str(config.DATA_DIR / "generated_answers.jsonl"),
                       help='生成答案输入路径（Stage2 输出）')
    parser.add_argument('--output', type=str,
                       default=str(config.DATA_DIR / "evaluation_report.json"),
                       help='评估报告输出路径')
    parser.add_argument('--max-workers', type=int, default=16,
                       help='并发数（默认 16，根据 API 限流调整）')
    parser.add_argument('--timeout', type=int, default=180,
                       help='单个评估任务超时时间（秒，默认 180）')
    parser.add_argument('--verbose', action='store_true',
                       help='显示详细日志')

    args = parser.parse_args()

    # 配置日志
    if args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
    else:
        logging.basicConfig(level=logging.WARNING)

    print("=" * 60)
    print("🚀 Stage3: 评估")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 检查 RAGAs 是否可用
    if not RAGAS_AVAILABLE:
        print("[X] RAGAs 未安装，无法继续")
        print("   请运行: pip install ragas datasets")
        return

    # 1. 加载检索结果
    retrieval_path = Path(args.retrieval)
    print(f"📂 加载检索结果: {retrieval_path}")

    try:
        retrieval_results = read_jsonl(retrieval_path, RetrievalResult)
    except FileNotFoundError as e:
        print(f"[X] 错误: {e}")
        print("   请先运行 Stage1 (stage1_retrieve.py)")
        return
    except Exception as e:
        print(f"[X] 加载失败: {e}")
        return

    print(f"[OK] 加载了 {len(retrieval_results)} 个检索结果")

    # 2. 加载生成的答案
    answers_path = Path(args.answers)
    print(f"📂 加载生成的答案: {answers_path}")

    try:
        generated_answers = read_jsonl(answers_path, GeneratedAnswer)
    except FileNotFoundError as e:
        print(f"[X] 错误: {e}")
        print("   请先运行 Stage2 (stage2_generate.py)")
        return
    except Exception as e:
        print(f"[X] 加载失败: {e}")
        return

    print(f"[OK] 加载了 {len(generated_answers)} 个生成的答案")
    print()

    # 验证数据一致性
    if len(retrieval_results) != len(generated_answers):
        print(f"[X] 错误: 检索结果数量 ({len(retrieval_results)}) 与答案数量 ({len(generated_answers)}) 不匹配")
        return

    # 3. 转换为 RAGAs 格式
    print("🔄 转换为 RAGAs 格式...")
    ragas_data = convert_to_ragas_format(retrieval_results, generated_answers)

    # 创建 Dataset
    try:
        dataset = Dataset.from_dict(ragas_data)
        print(f"[OK] 转换完成，数据集大小: {len(dataset)}\n")
    except Exception as e:
        print(f"[X] 创建数据集失败: {e}")
        return

    # 4. 创建 RAGAs 使用的模型实例
    print("🤖 初始化 RAGAs 评估模型...")
    print()

    try:
        # 使用项目配置的模型
        ragas_llm = create_ragas_llm(temperature=0.0, verbose=True)
        ragas_embeddings = create_ragas_embeddings(verbose=True)
    except Exception as e:
        print(f"[X] 模型初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 5. 运行 RAGAs 评估（支持并发配置）
    print("📊 运行 RAGAs 评估...")
    print("   评估指标:")
    print("   1. faithfulness (忠实度) - 答案是否基于检索到的段落")
    print("   2. answer_relevancy (答案相关性) - 答案是否回答了问题")
    print("   3. context_precision (上下文精度) - 检索段落的精准度")
    print("   4. context_recall (上下文召回率) - 标准答案信息的覆盖度")
    print(f"   并发数: {args.max_workers}")
    print()

    try:
        # 🆕 配置并发参数
        from ragas.run_config import RunConfig

        run_config = RunConfig(
            max_workers=args.max_workers,  # 并发数
            timeout=args.timeout,           # 超时时间
            max_retries=3                   # 最大重试次数
        )

        # 传入自定义的 LLM 和 Embeddings
        results = evaluate(
            dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            run_config=run_config  # 🆕 传入并发配置
        )
        print("[OK] RAGAs 评估完成\n")
    except Exception as e:
        print(f"[X] RAGAs 评估失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 6. 展示结果
    print("=" * 60)
    print("📊 RAGAs 评估结果")
    print("=" * 60)

    # 将 EvaluationResult 转换为字典
    if hasattr(results, 'to_pandas'):
        df = results.to_pandas()
        # 只选择数值列计算平均值
        numeric_cols = df.select_dtypes(include=['number']).columns
        results_dict = df[numeric_cols].mean().to_dict()

        # 提取每个问题的详细评分
        per_question_scores = []
        for idx, row in df.iterrows():
            question_score = QuestionScore(
                question_id=retrieval_results[idx].question_id,
                faithfulness=float(row.get('faithfulness', 0)),
                answer_relevancy=float(row.get('answer_relevancy', 0)),
                context_precision=float(row.get('context_precision', 0)),
                context_recall=float(row.get('context_recall', 0))
            )
            per_question_scores.append(question_score)

        # 如果开启 verbose，展示每个问题的详细评分
        if args.verbose and len(df) > 0:
            print("\n[*] 每个问题的详细评分:")
            print("=" * 60)
            for idx, row in df.iterrows():
                print(f"\n问题 {idx + 1}: {ragas_data['question'][idx][:60]}...")
                print(f"  标准答案: {ragas_data['ground_truth'][idx][:50]}...")
                print(f"  生成答案: {ragas_data['answer'][idx][:50]}...")
                print(f"  检索段落数: {len(ragas_data['contexts'][idx])}")
                print(f"  评分:")
                for col in numeric_cols:
                    if col in row and pd.notna(row[col]):
                        print(f"    {col:25s}: {row[col]:.4f}")
            print(f"\n{'='*60}\n")
    else:
        results_dict = dict(results)
        per_question_scores = []

    print("\n[*] 平均评分:")
    for metric_name, score in results_dict.items():
        print(f"  {metric_name:25s}: {score:.4f}")

    print()

    # 7. 保存评估报告
    # 获取 retrieval metadata (从第一个结果中提取)
    first_retrieval = retrieval_results[0]

    report = EvaluationReport(
        metadata={
            "timestamp": datetime.now().isoformat(),
            "total_questions": len(retrieval_results),
            "source_config_id": first_retrieval.retrieval_metadata.source_config_id,
            "top_k": first_retrieval.retrieval_metadata.top_k,
            "threshold": first_retrieval.retrieval_metadata.threshold,
            "retrieval_file": str(args.retrieval),
            "answers_file": str(args.answers),
        },
        ragas_metrics={
            metric_name: float(score)
            for metric_name, score in results_dict.items()
        },
        per_question_scores=per_question_scores
    )

    output_path = Path(args.output)
    write_json(report, output_path)

    print("=" * 60)
    print("✅ Stage3 完成")
    print("=" * 60)
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"输出文件: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
