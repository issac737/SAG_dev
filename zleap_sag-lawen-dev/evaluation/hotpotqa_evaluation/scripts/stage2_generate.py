"""
Stage2: 答案生成

功能：
1. 从 retrieval_results.jsonl 加载检索结果
2. 为每个问题基于检索到的段落生成答案（使用 LLM）
3. 保存生成的答案到 generated_answers.jsonl

输入：
- retrieval_results.jsonl（Stage1 输出）

输出：
- generated_answers.jsonl（生成的答案，每行一个问题）

使用方法：
    # 基本用法
    python stage2_generate.py

    # 自定义输入/输出路径
    python stage2_generate.py --input data/retrieval_results.jsonl --output data/generated_answers.jsonl

    # 显示详细日志
    python stage2_generate.py --verbose
"""

import asyncio
import argparse
import logging
from pathlib import Path
from typing import List
from datetime import datetime

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

# 导入系统模块
from dataflow.core.ai.factory import create_llm_client
from dataflow.core.ai.models import LLMMessage, LLMRole

# 导入共享模块
from shared import (
    RetrievalResult,
    GeneratedAnswer,
    GenerationMetadata,
    read_jsonl,
    write_jsonl,
    validate_generated_answers,
)


async def generate_answer_with_metadata(
    result: RetrievalResult,
    llm_client,
    index: int,
    total: int,
    verbose: bool = False
) -> GeneratedAnswer:
    """
    为单个问题生成答案（带元数据）

    Args:
        result: 检索结果
        llm_client: LLM客户端
        index: 当前索引
        total: 总数
        verbose: 是否显示详细日志

    Returns:
        生成的答案对象
    """
    question = result.question
    question_id = result.question_id

    # 获取检索到的段落
    contexts = [
        section.content_preview
        for section in result.retrieved_sections
    ]

    # 获取 oracle 信息
    oracle_answer = result.answer
    oracle_chunk_ids = result.oracle_chunk_ids

    # 打印进度（简化模式）
    print(f"[{index}/{total}] 生成答案: {question[:60]}...")

    # 生成答案
    if not contexts:
        answer = ""
        if verbose:
            print(f"  [!] 警告: 没有检索到段落，使用空答案")
    else:
        try:
            answer = await generate_answer(question, contexts, llm_client)
            if verbose:
                print(f"  [AI] 答案: {answer[:100]}...")
        except Exception as e:
            print(f"  [X] 生成失败: {e}")
            answer = ""

    # 创建 GeneratedAnswer 对象
    generation_metadata = GenerationMetadata(
        model=llm_client.model_name if hasattr(llm_client, 'model_name') else "unknown",
        temperature=0.3
    )

    generated_answer = GeneratedAnswer(
        question_id=question_id,
        question=question,
        generated_answer=answer,
        contexts_used=contexts,
        generation_metadata=generation_metadata
    )

    return generated_answer


async def generate_answer(
    question: str,
    contexts: List[str],
    llm_client
) -> str:
    """
    基于检索到的段落生成答案

    Args:
        question: 用户问题
        contexts: 检索到的段落列表
        llm_client: LLM客户端

    Returns:
        生成的答案
    """
    # 如果没有检索到段落，返回空答案
    if not contexts:
        return ""

    # 构建上下文文本
    context_text = "\n\n".join(contexts)

    # 使用标准的 RAG prompt 模板
    prompt = f"""You are an assistant for question-answering tasks.
Use the following pieces of retrieved context to answer the question.
If you don't know the answer, just say that you don't know.
Use two sentences maximum and keep the answer concise.
Question: {question}
Context: {context_text}
Answer:"""

    # 调用LLM
    messages = [LLMMessage(role=LLMRole.USER, content=prompt)]
    response = await llm_client.chat(messages, temperature=0.3)

    return response.content.strip()


async def main():
    parser = argparse.ArgumentParser(description='Stage2: 答案生成')
    parser.add_argument('--input', type=str,
                       default=str(config.DATA_DIR / "retrieval_results.jsonl"),
                       help='检索结果输入路径（Stage1 输出）')
    parser.add_argument('--output', type=str,
                       default=str(config.DATA_DIR / "generated_answers.jsonl"),
                       help='生成答案输出路径')
    parser.add_argument('--concurrency', type=int, default=5,
                       help='并发数（默认 5，根据 API 限流调整）')
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
    print("🚀 Stage2: 答案生成")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. 加载检索结果
    input_path = Path(args.input)
    print(f"📂 加载检索结果: {input_path}")

    try:
        retrieval_results = read_jsonl(input_path, RetrievalResult)
    except FileNotFoundError as e:
        print(f"[X] 错误: {e}")
        print("   请先运行 Stage1 (stage1_retrieve.py)")
        return
    except Exception as e:
        print(f"[X] 加载失败: {e}")
        return

    print(f"[OK] 加载了 {len(retrieval_results)} 个检索结果")
    print()

    # 2. 初始化 LLM 客户端
    print("🤖 初始化 LLM 客户端...")
    try:
        llm_client = await create_llm_client()
        print("[OK] 初始化完成\n")
    except Exception as e:
        print(f"[X] 初始化失败: {e}")
        return

    # 3. 为每个问题生成答案（并发处理）
    print("📝 开始生成答案...")
    print("=" * 60)
    print(f"并发数: {args.concurrency}")
    print()

    try:
        # 🆕 使用 asyncio.Semaphore 控制并发数
        semaphore = asyncio.Semaphore(args.concurrency)

        async def generate_with_semaphore(result, index):
            async with semaphore:
                return await generate_answer_with_metadata(
                    result=result,
                    llm_client=llm_client,
                    index=index,
                    total=len(retrieval_results),
                    verbose=args.verbose
                )

        # 🆕 创建所有任务
        tasks = [
            generate_with_semaphore(result, i)
            for i, result in enumerate(retrieval_results, 1)
        ]

        # 🆕 并发执行所有任务
        generated_answers = await asyncio.gather(*tasks)

        print(f"\n{'='*60}")
        print(f"[OK] 所有答案生成完成（共 {len(generated_answers)} 个）")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\n[X] 答案生成失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 4. 验证数据
    print("✓ 验证生成的答案...")
    try:
        validate_generated_answers(generated_answers, retrieval_results)
    except ValueError as e:
        print(f"[X] 验证失败: {e}")
        return

    # 5. 保存结果
    output_path = Path(args.output)
    write_jsonl(generated_answers, output_path)

    print()
    print("=" * 60)
    print("✅ Stage2 完成")
    print("=" * 60)
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"输出文件: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
