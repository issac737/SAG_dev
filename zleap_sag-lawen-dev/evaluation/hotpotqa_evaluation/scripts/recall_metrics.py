"""
HotpotQA Recall Metrics 召回指标计算模块

提供召回率计算的公共功能
"""

from typing import List, Dict, Any
from dataclasses import dataclass


def normalize_text(text: str) -> str:
    """
    归一化文本用于精确匹配
    去除多余空格并去除首尾空格

    Args:
        text: 输入文本

    Returns:
        归一化后的文本
    """
    return ' '.join(text.strip().split())


@dataclass
class RecallResult:
    """单个问题的召回结果"""
    question_id: str
    recall: float  # 召回率 (0.0 - 1.0)
    total_oracle: int  # 标准答案总数
    recalled: int  # 召回的数量
    retrieved: int  # 检索到的段落总数
    recalled_details: List[Dict[str, Any]]  # 召回的详细信息

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'question_id': self.question_id,
            'recall': self.recall,
            'total_oracle': self.total_oracle,
            'recalled': self.recalled,
            'retrieved': self.retrieved,
            'recalled_details': self.recalled_details
        }


class RecallCalculator:
    """召回率计算器"""

    @staticmethod
    def calculate(
        question_id: str,
        oracle_chunks: List[Dict[str, Any]],
        retrieved_sections: List[Dict[str, Any]],
        verbose: bool = False
    ) -> RecallResult:
        """
        基于文本内容精确匹配计算召回率

        Args:
            question_id: 问题ID
            oracle_chunks: 标准答案段落列表，每个包含:
                - chunk_id: 段落ID
                - title: 标题
                - text: 文本内容（用于匹配）
            retrieved_sections: 检索到的段落列表，每个包含:
                - chunk_id: 段落ID
                - heading: 标题
                - content: 内容（用于匹配）
            verbose: 是否显示匹配详情

        Returns:
            RecallResult: 召回结果
        """
        if not oracle_chunks:
            return RecallResult(
                question_id=question_id,
                recall=0.0,
                total_oracle=0,
                recalled=0,
                retrieved=len(retrieved_sections),
                recalled_details=[]
            )

        # 构建 oracle 文本映射（归一化文本 -> oracle chunk）
        oracle_text_map = {}
        for chunk in oracle_chunks:
            text = chunk.get('text', '')
            normalized = normalize_text(text)
            if normalized:  # 只添加非空文本
                oracle_text_map[normalized] = chunk

        if not oracle_text_map:
            return RecallResult(
                question_id=question_id,
                recall=0.0,
                total_oracle=0,
                recalled=0,
                retrieved=len(retrieved_sections),
                recalled_details=[]
            )

        # 检查哪些 oracle chunks 被召回
        recalled_details = []
        recalled_texts = set()

        for section in retrieved_sections:
            retrieved_text = section.get('content', '')
            normalized_retrieved = normalize_text(retrieved_text)

            # 与 oracle 文本进行精确匹配
            if normalized_retrieved in oracle_text_map:
                oracle_chunk = oracle_text_map[normalized_retrieved]
                recalled_texts.add(normalized_retrieved)
                recalled_details.append({
                    'oracle_chunk_id': oracle_chunk.get('chunk_id'),
                    'oracle_title': oracle_chunk.get('title'),
                    'retrieved_chunk_id': section.get('chunk_id'),
                    'retrieved_heading': section.get('heading')
                })

                if verbose:
                    print(f"      [匹配] Oracle: {oracle_chunk.get('title')} <-> "
                          f"Retrieved: {section.get('heading')}")

        # 计算召回率
        recall = len(recalled_texts) / len(oracle_text_map) if oracle_text_map else 0.0

        return RecallResult(
            question_id=question_id,
            recall=recall,
            total_oracle=len(oracle_text_map),
            recalled=len(recalled_texts),
            retrieved=len(retrieved_sections),
            recalled_details=recalled_details
        )


# 兼容旧版 API
def calculate_recall(
    oracle_chunks: List[Dict[str, Any]],
    retrieved_sections: List[Dict[str, Any]],
    verbose: bool = False
) -> Dict[str, Any]:
    """
    兼容旧版的召回率计算函数

    Args:
        oracle_chunks: 标准答案段落
        retrieved_sections: 检索到的段落
        verbose: 显示匹配详情

    Returns:
        召回统计字典
    """
    result = RecallCalculator.calculate(
        question_id="unknown",
        oracle_chunks=oracle_chunks,
        retrieved_sections=retrieved_sections,
        verbose=verbose
    )
    return result.to_dict()
