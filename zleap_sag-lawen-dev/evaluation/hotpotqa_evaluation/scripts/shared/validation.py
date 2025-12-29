"""
数据验证工具
"""
from typing import List
from .data_models import RetrievalResult, GeneratedAnswer


def validate_retrieval_results(results: List[RetrievalResult]) -> bool:
    """
    验证检索结果的完整性

    Args:
        results: 检索结果列表

    Returns:
        True 表示验证通过

    Raises:
        ValueError: 数据不完整或格式错误
    """
    if not results:
        raise ValueError("检索结果列表为空")

    for i, result in enumerate(results, 1):
        # 检查必需字段
        if not result.question_id:
            raise ValueError(f"第 {i} 个结果缺少 question_id")
        if not result.question:
            raise ValueError(f"第 {i} 个结果缺少 question")
        if not result.answer:
            raise ValueError(f"第 {i} 个结果缺少 answer (ground truth)")

        # 检查 oracle_chunks
        if not result.oracle_chunks:
            raise ValueError(f"第 {i} 个结果缺少 oracle_chunks")

        # 检查 retrieved_sections（可以为空，但必须存在）
        if result.retrieved_sections is None:
            raise ValueError(f"第 {i} 个结果的 retrieved_sections 字段不存在")

    print(f"[VALIDATION] 检索结果验证通过: {len(results)} 条记录")
    return True


def validate_generated_answers(
    answers: List[GeneratedAnswer],
    retrieval_results: List[RetrievalResult]
) -> bool:
    """
    验证生成的答案与检索结果的一致性

    Args:
        answers: 生成的答案列表
        retrieval_results: 检索结果列表（用于验证 question_id 一致性）

    Returns:
        True 表示验证通过

    Raises:
        ValueError: 数据不一致或格式错误
    """
    if not answers:
        raise ValueError("生成答案列表为空")

    if len(answers) != len(retrieval_results):
        raise ValueError(
            f"答案数量 ({len(answers)}) 与检索结果数量 ({len(retrieval_results)}) 不匹配"
        )

    # 创建检索结果的 question_id 集合
    retrieval_ids = {r.question_id for r in retrieval_results}

    for i, answer in enumerate(answers, 1):
        # 检查必需字段
        if not answer.question_id:
            raise ValueError(f"第 {i} 个答案缺少 question_id")
        if not answer.question:
            raise ValueError(f"第 {i} 个答案缺少 question")
        if answer.generated_answer is None:  # 允许空字符串
            raise ValueError(f"第 {i} 个答案缺少 generated_answer")

        # 验证 question_id 存在于检索结果中
        if answer.question_id not in retrieval_ids:
            raise ValueError(
                f"第 {i} 个答案的 question_id ({answer.question_id}) "
                f"不存在于检索结果中"
            )

        # contexts_used 可以为空（没有检索到段落的情况）
        if answer.contexts_used is None:
            raise ValueError(f"第 {i} 个答案的 contexts_used 字段不存在")

    print(f"[VALIDATION] 生成答案验证通过: {len(answers)} 条记录")
    return True
