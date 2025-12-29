"""
数据模型定义（使用 Pydantic 保证类型安全）
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class OracleChunk(BaseModel):
    """标准答案段落"""
    chunk_id: str
    title: str
    text_preview: str


class RetrievedSection(BaseModel):
    """检索到的段落"""
    section_id: str
    event_id: str
    event_title: str
    heading: str
    content_preview: str
    similarity_score: Optional[float] = None


class RetrievalMetadata(BaseModel):
    """检索元数据"""
    source_config_id: str
    top_k: int
    threshold: float
    retrieved_count: int
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class RetrievalResult(BaseModel):
    """Stage1 输出：单个问题的检索结果"""
    question_id: str
    question: str
    answer: str  # ground truth
    oracle_chunk_ids: List[str]
    oracle_chunks: List[OracleChunk]
    retrieved_sections: List[RetrievedSection]
    retrieval_metadata: RetrievalMetadata


class GenerationMetadata(BaseModel):
    """生成元数据"""
    model: str = "unknown"
    temperature: float = 0.3
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class GeneratedAnswer(BaseModel):
    """Stage2 输出：单个问题的生成答案"""
    question_id: str
    question: str
    generated_answer: str
    contexts_used: List[str]
    generation_metadata: GenerationMetadata


class QuestionScore(BaseModel):
    """单个问题的评分"""
    question_id: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


class EvaluationReport(BaseModel):
    """Stage3 输出：完整评估报告"""
    metadata: Dict[str, Any]
    ragas_metrics: Dict[str, float]
    per_question_scores: List[QuestionScore]
