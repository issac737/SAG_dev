"""
Retrieve and Recall Evaluation Module

集成检索和召回评估功能，支持批量处理和逐步统计
"""

from __future__ import annotations

import json
import logging
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))  # 4 个 .parent

# Load environment variables
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"[INFO] Loaded environment variables: {env_path}")
else:
    print(f"[WARN] .env file not found: {env_path}")

# Import required modules
from dataflow.modules.search import EventSearcher, SearchConfig, SAGSearcher
from dataflow.modules.search.config import (
    ReturnType, RecallConfig, ExpandConfig, RerankConfig, RecallMode
)
from dataflow.core.storage.elasticsearch import close_es_client
from dataflow.core.prompt.manager import PromptManager

# Import recall metrics
from evaluation.hotpotqa_evaluation.scripts.recall_metrics import (
    RecallCalculator, RecallResult, normalize_text, calculate_recall
)
# Import shared models & IO helpers
from evaluation.hotpotqa_evaluation.scripts.shared.data_models import RetrievalResult
from evaluation.hotpotqa_evaluation.scripts.shared.io_utils import write_jsonl
from dataflow.utils.logger import setup_logging

# 初始化日志系统，确保logger.info()能够输出到终端
# 如需查看更详细的调试信息，可以将 level 改为 "DEBUG"
setup_logging(level="INFO")
def calculate_recall(
    oracle_chunks: List[Dict[str, Any]],
    retrieved_sections: List[Dict[str, Any]],
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Calculate Recall metric using hybrid matching (title + text fallback)

    Matching strategy (in order of priority):
    1. Title exact match (normalized)
    2. Text substring match (first 100 chars)
    
    This hybrid approach is more robust than single-method matching.

    Args:
        oracle_chunks: Ground truth chunks with 'title' and 'text_preview' fields
        retrieved_sections: Retrieved sections with 'heading' and 'content_preview' fields
        verbose: Show matching details

    Returns:
        Recall statistics
    """
    if not oracle_chunks:
        return {
            'recall': 0.0,
            'total_oracle': 0,
            'recalled': 0,
            'retrieved': len(retrieved_sections),
            'recalled_details': []
        }

    def normalize_title(title: str) -> str:
        """Normalize title by stripping Markdown header prefix and whitespace"""
        if not title:
            return ""
        title = title.strip()
        if title.startswith("# "):
            title = title[2:]
        return title.lower().strip()

    def normalize_text(text: str, max_len: int = 150) -> str:
        """Normalize text for matching: lowercase, remove extra spaces, truncate"""
        if not text:
            return ""
        # Remove markdown header prefix if present at start
        text = text.strip()
        if text.startswith("# "):
            text = text[2:]
        # Normalize whitespace and lowercase
        text = ' '.join(text.lower().split())
        # Truncate to first N chars for matching (avoid length differences)
        return text[:max_len]

    # Build oracle lookup structures
    oracle_by_title = {}  # normalized_title -> oracle chunk
    oracle_by_text = {}   # normalized_text_prefix -> oracle chunk
    
    for chunk in oracle_chunks:
        title = chunk.get('title', '')
        text = chunk.get('text_preview', '')
        
        normalized_title = normalize_title(title)
        normalized_text = normalize_text(text)
        
        if normalized_title:
            oracle_by_title[normalized_title] = chunk
        if normalized_text:
            oracle_by_text[normalized_text] = chunk

    # Check which oracle chunks were recalled
    recalled_details = []
    recalled_oracle_ids = set()  # Track by chunk_id to avoid duplicates

    for section in retrieved_sections:
        retrieved_title = section.get('heading', '')
        retrieved_text = section.get('content_preview', '')
        
        normalized_title = normalize_title(retrieved_title)
        normalized_text = normalize_text(retrieved_text)
        
        matched_chunk = None
        match_method = None
        
        # Strategy 1: Title exact match
        if normalized_title in oracle_by_title:
            matched_chunk = oracle_by_title[normalized_title]
            match_method = "title"
        # Strategy 2: Title contains match (for compound headings like "# A | # B")
        else:
            for oracle_title, chunk in oracle_by_title.items():
                if oracle_title in normalized_title:
                    matched_chunk = chunk
                    match_method = "title_contains"
                    break
        # Strategy 3: Text prefix match
        if not matched_chunk and normalized_text in oracle_by_text:
            matched_chunk = oracle_by_text[normalized_text]
            match_method = "text"
        
        if matched_chunk:
            chunk_id = matched_chunk.get('chunk_id')
            if chunk_id and chunk_id not in recalled_oracle_ids:
                recalled_oracle_ids.add(chunk_id)
                recalled_details.append({
                    'oracle_chunk_id': chunk_id,
                    'oracle_title': matched_chunk.get('title'),
                    'retrieved_section_id': section.get('section_id'),
                    'retrieved_heading': section.get('heading'),
                    'match_method': match_method
                })

    # Calculate recall
    recall = len(recalled_oracle_ids) / len(oracle_chunks) if oracle_chunks else 0.0

    return {
        'recall': recall,
        'total_oracle': len(oracle_chunks),
        'recalled': len(recalled_oracle_ids),
        'retrieved': len(retrieved_sections),
        'recalled_details': recalled_details
    }



def normalize_text(text: str) -> str:
    """
    Normalize text for exact matching
    Remove extra whitespace and trim

    Args:
        text: Input text

    Returns:
        Normalized text
    """
    return ' '.join(text.strip().split())

# 移除本地的 calculate_recall 和 normalize_text 函数，使用 recall_metrics 中的版本


def load_corpus(corpus_path: Path) -> Dict[str, Dict[str, str]]:
    """
    加载语料库，返回 {chunk_id: {title, text}} 的字典
    """
    corpus_dict = {}
    with open(corpus_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                chunk = json.loads(line)
                chunk_id = chunk['id']

                # 处理合并的 ID（格式：id1//id2//id3）
                if "//" in chunk_id:
                    original_ids = chunk_id.split("//")
                    for original_id in original_ids:
                        corpus_dict[original_id] = {
                            'title': chunk['title'],
                            'text': chunk['text']
                        }
                else:
                    corpus_dict[chunk_id] = {
                        'title': chunk['title'],
                        'text': chunk['text']
                    }
    return corpus_dict


def load_oracle_questions(oracle_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    从 oracle.jsonl 加载测试问题

    Args:
        oracle_path: oracle.jsonl 路径
        limit: 加载问题数量限制（None 表示加载全部）

    Returns:
        问题列表
    """
    questions = []

    if not oracle_path.exists():
        raise FileNotFoundError(f"Oracle 文件不存在: {oracle_path}")

    with open(oracle_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            oracle = json.loads(line)
            questions.append({
                'id': oracle['id'],
                'question': oracle['question'],
                'answer': oracle['answer'],
                'oracle_chunk_ids': oracle['oracle_chunk_ids']
            })

    return questions


def load_zero_recall_questions(json_path: Path) -> List[Dict[str, Any]]:
    """
    从 zero_recall_questions.json 加载召回率为0的问题

    Args:
        json_path: zero_recall_questions.json 路径

    Returns:
        问题列表
    """
    if not json_path.exists():
        raise FileNotFoundError(f"Zero recall 文件不存在: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        questions_data = json.load(f)

    # 转换为统一格式
    questions = []
    for q in questions_data:
        questions.append({
            'id': q['id'],
            'question': q['question'],
            'answer': q['answer'],
            'oracle_chunk_ids': q['oracle_chunk_ids']
        })

    return questions



async def process_single_question(
    q: Dict[str, Any],
    searcher: Any,
    source_config_id: str,
    corpus_dict: Dict[str, Dict[str, str]],
    index: int,
    total: int,
    verbose: bool = False,
    zero_recall_mode: bool = False
) -> Dict[str, Any]:
    """
    处理单个问题的检索

    Args:
        q: 问题数据
        searcher: 搜索器实例
        source_config_id: 数据源ID
        corpus_dict: 语料库字典
        index: 当前索引
        total: 总数
        verbose: 是否显示详细信息
        zero_recall_mode: 是否为零召回调试模式

    Returns:
        检索结果
    """
    import logging
    logger = logging.getLogger(__name__)

    question_id = q['id']
    question = q['question']
    answer = q['answer']
    oracle_chunk_ids = q['oracle_chunk_ids']

    if verbose or zero_recall_mode:
        logger.info(f"\n{'='*80}")
        logger.info(f"[{index}/{total}] 搜索问题")
        logger.info(f"{'='*80}")
        logger.info(f"❓ 问题: {question}")
        logger.info(f"✅ 答案: {answer}")

        # 展示标准答案段落
        if oracle_chunk_ids and corpus_dict:
            logger.info(f"\n📌 标准答案对应的段落 ({len(oracle_chunk_ids)}个):")
            for j, chunk_id in enumerate(oracle_chunk_ids[:3], 1):
                if chunk_id in corpus_dict:
                    chunk = corpus_dict[chunk_id]
                    logger.info(f"   [{j}] 标题: {chunk['title']}")
                    text_preview = chunk['text'].replace('\n', ' ')
                    logger.info(f"       内容: {text_preview}...")
            if len(oracle_chunk_ids) > 3:
                logger.info(f"   ... 还有 {len(oracle_chunk_ids) - 3} 个段落")

    # 执行搜索
    search_config = SearchConfig(
        query=question,
        source_config_id=source_config_id,
        return_type=ReturnType.PARAGRAPH,
        recall=RecallConfig(use_fast_mode=False,vector_top_k=50,max_entities=50,recall_mode=RecallMode.FUZZY,entity_similarity_threshold=0.3,entity_weight_threshold=0.2),
        expand=ExpandConfig(max_hops=3),
        rerank=RerankConfig(max_results=10, score_threshold=0.45, strategy="pagerank")
    )

    sections = []
    try:
        search_result = await searcher.search(search_config)
        sections = search_result.get("sections", [])
        if verbose or zero_recall_mode:
            logger.info(f"✅ 搜索完成，找到 {len(sections)} 个相关段落")
    except Exception as e:
        if verbose or zero_recall_mode:
            logger.error(f"⚠️  搜索失败: {e}")
        sections = []

    # 段落去重
    seen_chunk_ids = set()
    unique_sections = []
    for section in sections:
        chunk_id = section.get('chunk_id')
        if chunk_id and chunk_id not in seen_chunk_ids:
            seen_chunk_ids.add(chunk_id)
            unique_sections.append(section)

    sections = unique_sections

    if (verbose or zero_recall_mode) and len(sections) > 0:
        logger.info(f"\n🔍 检索到的段落 (共 {len(sections)} 个):")
        for j, section in enumerate(sections, 1):
            heading = section.get('heading', 'N/A')
            content = section.get('content', '').replace('\n', ' ')

            # 获取得分信息
            cosine_score = section.get('original_score', 0.0)  # 余弦相似度
            pagerank_score = section.get('weight') or section.get('pagerank', 0.0)  # PageRank得分

            # 同时显示余弦相似度和PageRank得分
            logger.info(f"   [{j}] 标题: {heading}")
            logger.info(f"       余弦相似度: {cosine_score:.4f} | PageRank: {pagerank_score:.4f}")
            logger.info(f"       内容: {content}...")
        if len(sections) > 5:
            logger.info(f"   ... 还有 {len(sections) - 5} 个段落")
    elif (verbose or zero_recall_mode) and len(sections) == 0:
        logger.warning(f"⚠️  未检索到任何段落！")

    # 构建检索结果
    oracle_chunks = []
    for chunk_id in oracle_chunk_ids:
        if chunk_id in corpus_dict:
            chunk = corpus_dict[chunk_id]
            oracle_chunks.append({
                'chunk_id': chunk_id,
                'title': chunk['title'],
                'text_preview': chunk['text']  # 保留完整内容
            })

    retrieved_sections = []
    for section in sections:
        retrieved_sections.append({
            'section_id': section.get('chunk_id', ''),
            'event_id': section.get('event_id', ''),
            'event_title': section.get('event_title', ''),
            'heading': section.get('heading', ''),
            'content_preview': section.get('content', ''),  # 保留完整内容
            'similarity_score': section.get('pagerank') or section.get('weight')  # 使用 pagerank 或 weight 作为分数
        })

    return {
        'question_id': question_id,
        'question': question,
        'answer': answer,
        'oracle_chunk_ids': oracle_chunk_ids,
        'oracle_chunks': oracle_chunks,
        'retrieved_sections': retrieved_sections,
        'retrieval_metadata': {
            'source_config_id': source_config_id,
            'top_k': 10,
            'threshold': 0.45,
            'retrieved_count': len(retrieved_sections),
            'timestamp': datetime.now().isoformat()
        }
    }



@dataclass
class RecallStats:
    """召回统计信息"""
    total_questions: int = 0
    total_oracle: int = 0
    total_recalled: int = 0
    total_retrieved: int = 0
    perfect_recall_count: int = 0
    zero_recall_count: int = 0
    partial_recall_count: int = 0  # 部分召回的问题数
    partial_recall_questions: List[Dict[str, Any]] = field(default_factory=list)  # 部分召回的问题列表
    per_question: List[Dict[str, Any]] = field(default_factory=list)
    cumulative_recall: float = 0.0

    def update(self, recall_info: Dict[str, Any], question_id: str, question: str):
        """更新统计信息"""
        self.total_questions += 1
        self.total_oracle += recall_info['total_oracle']
        self.total_recalled += recall_info['recalled']
        self.total_retrieved += recall_info['retrieved']

        if recall_info['recall'] >= 1.0:
            self.perfect_recall_count += 1
        elif recall_info['recall'] == 0.0:
            self.zero_recall_count += 1
        else:
            # 部分召回 (0 < recall < 1.0)
            self.partial_recall_count += 1
            self.partial_recall_questions.append({
                'question_id': question_id,
                'question': question,
                'recall': recall_info['recall'],
                'recalled': recall_info['recalled'],
                'total_oracle': recall_info['total_oracle'],
                'percentage': f"{recall_info['recalled']}/{recall_info['total_oracle']}"
            })

        # 累积召回率
        if self.total_oracle > 0:
            self.cumulative_recall = self.total_recalled / self.total_oracle

        # 记录每个问题的统计
        self.per_question.append({
            'question_id': question_id,
            'question': question,
            'recall': recall_info['recall'],
            'total_oracle': recall_info['total_oracle'],
            'recalled': recall_info['recalled'],
            'retrieved': recall_info['retrieved'],
            'recalled_details': recall_info['recalled_details']
        })

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total_questions': self.total_questions,
            'total_oracle': self.total_oracle,
            'total_recalled': self.total_recalled,
            'total_retrieved': self.total_retrieved,
            'cumulative_recall': self.cumulative_recall,
            'perfect_recall_count': self.perfect_recall_count,
            'zero_recall_count': self.zero_recall_count,
            'partial_recall_count': self.partial_recall_count,
            'partial_recall_questions': self.partial_recall_questions,
            'per_question': self.per_question
        }


class RetrieveRecallEvaluator:
    """
    检索和召回评估器

    功能：
    1. 从指定文件夹读取参数（source_config_id, oracle.jsonl, corpus.jsonl）
    2. 批量执行检索和召回评估
    3. 支持逐步叠加统计结果
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        初始化评估器

        Args:
            data_dir: 数据文件夹路径（包含 oracle.jsonl, corpus.jsonl, process_result.json）
                     如果为None，则使用默认路径 evaluation/hotpotqa_evaluation/data/source/最新文件夹
        """
        self.data_dir = data_dir
        self.source_config_id: Optional[str] = None
        self.corpus_dict: Dict[str, Dict[str, str]] = {}
        self.questions: List[Dict[str, Any]] = []
        self.searcher: Optional[EventSearcher] = None

        # 统计信息
        self.stats = RecallStats()

        # 结果存储
        self.retrieval_results: List["RetrievalResult"] = []

        # 初始化日志
        self._setup_logging()

    def _setup_logging(self):
        """设置日志"""
        self.logger = logging.getLogger(__name__)

    def load_data_directory(self, data_dir: Optional[Path] = None) -> Path:
        """
        加载数据文件夹

        Args:
            data_dir: 指定的数据文件夹，如果为None则使用默认路径

        Returns:
            实际使用的数据文件夹路径
        """
        if data_dir:
            # 使用指定的文件夹
            target_dir = Path(data_dir)
            if not target_dir.exists():
                raise FileNotFoundError(f"Data directory not found: {target_dir}")
        else:
            # 自动查找最后一个文件夹（相对于脚本位置）
            script_dir = Path(__file__).parent
            base_dir = script_dir.parent / "data" / "source"

            if not base_dir.exists():
                raise FileNotFoundError(f"Base directory not found: {base_dir}\n"
                                       f"  Please run from: zleap_sag directory\n"
                                       f"  Or specify --data-dir path")

            # 获取所有子文件夹（按目录名排序，格式: YYYYMMDD_HHMMSS）
            subdirs = [d for d in base_dir.iterdir() if d.is_dir()]
            if not subdirs:
                raise FileNotFoundError(f"No subdirectories found in {base_dir}\n"
                                       f"  Please ensure data has been processed first")

            # 按目录名排序（目录名格式 YYYYMMDD_HHMMSS 可直接字典序比较）
            # 不使用 mtime，因为 mtime 会被各种文件操作更新，不可靠
            target_dir = max(subdirs, key=lambda d: d.name)
            print(f"[INFO] Auto-selected latest directory (by name): {target_dir}")

        self.data_dir = target_dir
        print(f"[INFO] Using data directory: {self.data_dir}")
        return self.data_dir

    def load_parameters(self) -> Dict[str, Any]:
        """
        从数据文件夹加载参数

        Returns:
            参数字典，包含 source_config_id, oracle_path, corpus_path
        """
        if not self.data_dir:
            raise ValueError("Data directory not loaded. Call load_data_directory() first.")

        # 1. 读取 source_config_id (从 process_result.json)
        process_result_path = self.data_dir / "process_result.json"
        if process_result_path.exists():
            with open(process_result_path, 'r', encoding='utf-8') as f:
                process_result = json.load(f)
            self.source_config_id = process_result.get('source_config_id')
            print(f"[INFO] Loaded source_config_id: {self.source_config_id}")
        else:
            raise FileNotFoundError(f"process_result.json not found: {process_result_path}")

        # 2. 加载 corpus.jsonl
        corpus_path = self.data_dir / "corpus.jsonl"
        if corpus_path.exists():
            self.corpus_dict = load_corpus(corpus_path)
            print(f"[INFO] Loaded corpus: {len(self.corpus_dict)} chunks")
        else:
            print(f"[WARN] corpus.jsonl not found: {corpus_path}")
            self.corpus_dict = {}

        # 3. 加载 oracle.jsonl
        oracle_path = self.data_dir / "oracle.jsonl"
        if oracle_path.exists():
            self.questions = load_oracle_questions(oracle_path)
            print(f"[INFO] Loaded oracle: {len(self.questions)} questions")
        else:
            raise FileNotFoundError(f"oracle.jsonl not found: {oracle_path}")

        return {
            'source_config_id': self.source_config_id,
            'corpus_path': corpus_path,
            'oracle_path': oracle_path,
            'corpus_size': len(self.corpus_dict),
            'question_count': len(self.questions)
        }

    def load_bad_cases(self, bad_cases_path: str) -> List[str]:
        """
        从 bad_cases_zero_recall.json 文件加载问题ID列表

        Args:
            bad_cases_path: bad_cases_zero_recall.json 文件路径

        Returns:
            问题ID列表
        """
        bad_cases_file = Path(bad_cases_path)
        if not bad_cases_file.exists():
            raise FileNotFoundError(f"Bad cases file not found: {bad_cases_file}")

        print(f"[INFO] Loading bad cases from: {bad_cases_file}")

        with open(bad_cases_file, 'r', encoding='utf-8') as f:
            bad_cases = json.load(f)

        # 提取问题ID列表
        question_ids = [case['question_id'] for case in bad_cases]
        print(f"[INFO] Loaded {len(question_ids)} bad case question IDs")

        return question_ids

    def filter_questions_by_ids(self, question_ids: List[str]):
        """
        根据问题ID列表过滤问题

        Args:
            question_ids: 要保留的问题ID列表
        """
        question_id_set = set(question_ids)
        original_count = len(self.questions)

        # 过滤问题列表
        self.questions = [q for q in self.questions if q.get('id') in question_id_set]

        filtered_count = len(self.questions)
        print(f"[INFO] Filtered questions: {filtered_count}/{original_count} (based on bad cases)")

        if filtered_count == 0:
            print("[WARN] No questions matched the bad cases IDs!")
        elif filtered_count < len(question_ids):
            print(f"[WARN] Only {filtered_count}/{len(question_ids)} bad case IDs were found in the oracle data")


    def init_searcher(self):
        """初始化搜索器"""
        if not self.source_config_id:
            raise ValueError("source_config_id not loaded. Call load_parameters() first.")

        print("[INFO] Initializing searcher...")
        prompt_manager = PromptManager()
        self.searcher = SAGSearcher(prompt_manager=prompt_manager)
        print("[INFO] Searcher initialized successfully")

    async def process_batch(
        self,
        start_idx: int = 0,
        end_idx: Optional[int] = None,
        concurrency: int = 5,
        verbose: bool = False,
        log_details: bool = True
    ) -> Tuple[List["RetrievalResult"], "RecallStats"]:
        """
        批量处理一批问题

        Args:
            start_idx: 起始索引（包含）
            end_idx: 结束索引（不包含），如果为None则处理到末尾
            concurrency: 并发数
            verbose: 是否显示详细日志
            log_details: 是否记录每个问题的详细进度到日志文件

        Returns:
            (检索结果列表, 召回统计信息)
        """
        if not self.questions:
            raise ValueError("Questions not loaded. Call load_parameters() first.")

        if not self.searcher:
            raise ValueError("Searcher not initialized. Call init_searcher() first.")

        # 确定批次范围
        if end_idx is None or end_idx > len(self.questions):
            end_idx = len(self.questions)

        batch_questions = self.questions[start_idx:end_idx]
        print(f"\n{'='*60}")
        print(f"Processing batch: [{start_idx}:{end_idx}] ({len(batch_questions)} questions)")
        print(f"{'='*60}")

        # 创建信号量
        semaphore = asyncio.Semaphore(concurrency)

        async def process_with_semaphore(q, index):
            """使用信号量控制并发的包装函数"""
            async with semaphore:
                return await process_single_question(
                    q=q,
                    searcher=self.searcher,
                    source_config_id=self.source_config_id,
                    corpus_dict=self.corpus_dict,
                    index=index,
                    total=len(self.questions),
                    verbose=verbose,
                    zero_recall_mode=False
                )

        # 创建所有任务
        tasks = [
            process_with_semaphore(q, i + start_idx + 1)
            for i, q in enumerate(batch_questions, start_idx)
        ]

        # 并发执行
        print(f"[INFO] Starting concurrent processing with {concurrency} workers...")
        start_time = time.time()
        results_dicts = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time

        # 处理结果
        batch_results = []
        batch_stats = RecallStats()
        failed_count = 0

        for i, result in enumerate(results_dicts, 1):
            if isinstance(result, Exception):
                print(f"⚠️  Question {start_idx + i} failed: {result}")
                failed_count += 1
                continue

            # 转换为 RetrievalResult 对象
            retrieval_result = RetrievalResult(**result)
            batch_results.append(retrieval_result)

            # 计算召回率并更新统计
            oracle_chunks = [chunk.dict() for chunk in retrieval_result.oracle_chunks]
            retrieved_sections = [section.dict() for section in retrieval_result.retrieved_sections]

            recall_info = calculate_recall(oracle_chunks, retrieved_sections, verbose=False)
            batch_stats.update(recall_info, retrieval_result.question_id, retrieval_result.question)

            if verbose:
                progress_msg = (f"  [{len(batch_stats.per_question)}/{len(batch_questions)}] "
                               f"Recall: {recall_info['recall']:.4f} "
                               f"({recall_info['recalled']}/{recall_info['total_oracle']})")
                print(progress_msg)
                # 记录到日志文件（非 bad-cases 模式）
                if log_details:
                    self.logger.info(f"Question {retrieval_result.question_id}: "
                                   f"Recall={recall_info['recall']:.4f} "
                                   f"({recall_info['recalled']}/{recall_info['total_oracle']})")

        print(f"\n{'='*60}")
        print(f"Batch completed:")
        print(f"  Processed: {len(batch_results)} questions")
        print(f"  Failed: {failed_count}")
        print(f"  Time elapsed: {elapsed:.2f}s")
        print(f"  Batch recall: {batch_stats.cumulative_recall:.4f}")
        print(f"{'='*60}")

        return batch_results, batch_stats

    def merge_stats(self, new_stats: RecallStats):
        """
        将新的统计信息合并到全局统计中

        Args:
            new_stats: 新的批次统计信息
        """
        # 更新全局统计
        self.stats.total_questions += new_stats.total_questions
        self.stats.total_oracle += new_stats.total_oracle
        self.stats.total_recalled += new_stats.total_recalled
        self.stats.total_retrieved += new_stats.total_retrieved
        self.stats.perfect_recall_count += new_stats.perfect_recall_count
        self.stats.zero_recall_count += new_stats.zero_recall_count
        self.stats.partial_recall_count += new_stats.partial_recall_count
        self.stats.partial_recall_questions.extend(new_stats.partial_recall_questions)
        self.stats.per_question.extend(new_stats.per_question)

        # 重新计算累积召回率
        if self.stats.total_oracle > 0:
            self.stats.cumulative_recall = self.stats.total_recalled / self.stats.total_oracle

    async def run_incremental(
        self,
        batch_size: int = 20,
        concurrency: int = 5,
        verbose: bool = False,
        save_results: bool = True,
        track_zero_recall: bool = False,
        log_file: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        is_bad_cases_mode: bool = False,
        show_search_logs: bool = False
    ) -> Tuple[Dict[str, Any], Path]:
        """
        增量运行：分批处理，逐步叠加统计

        Args:
            batch_size: 每批处理的问题数量
            concurrency: 每批的并发数
            verbose: 是否显示详细日志
            save_results: 是否保存结果到文件
            track_zero_recall: 是否特别追踪零召回问题（生成Bad Case报告）
            log_file: 日志文件路径（如果为None，则自动创建）
            output_dir: 输出目录路径（如果为None，则创建新的时间戳文件夹）
            is_bad_cases_mode: 是否为 bad-cases 模式
            show_search_logs: 是否输出 dataflow/SAG 的完整搜索日志（INFO级别）

        Returns:
            (最终统计信息字典, 日志文件路径)
        """
        if not self.questions:
            raise ValueError("No questions loaded. Call load_parameters() first.")

        # 如果没有指定输出目录，创建新的时间戳文件夹
        if output_dir is None:
            script_dir = Path(__file__).parent
            retrieval_base_dir = script_dir.parent / "data" / "retrieval"
            retrieval_base_dir.mkdir(parents=True, exist_ok=True)

            # 创建时间戳文件夹
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = retrieval_base_dir / timestamp
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"\n[INFO] Created output directory: {output_dir}")
        else:
            print(f"\n[INFO] Using existing directory: {output_dir}")

        # 设置日志文件路径
        if log_file is None:
            # 在 bad-cases 模式下，使用不同的日志文件名
            if is_bad_cases_mode:
                log_file = output_dir / "retrieve_recall_bad_cases.log"
            else:
                log_file = output_dir / "retrieve_recall.log"

        log_file.parent.mkdir(parents=True, exist_ok=True)

        # 配置日志系统：文件只记录当前模块的INFO，控制台根据verbose参数
        # 创建文件处理器（总是记录 INFO 及以上）
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        ))

        # 创建控制台处理器（根据 verbose 参数设置级别）
        console_handler = logging.StreamHandler()
        if verbose or show_search_logs:
            console_handler.setLevel(logging.INFO)
        else:
            console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        ))

        # 只配置当前模块的logger，不影响其他模块
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []  # 清除已有的处理器
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        self.logger.propagate = False  # 不传播到根logger

        # 日志精细化控制：
        # - 默认屏蔽外部 INFO（WARNING）
        # - 如果 show_search_logs=True，仅开放 pagerank_section 的 INFO，其它搜索模块仍保持 WARNING
        default_external_level = logging.WARNING
        logging.getLogger('dataflow').setLevel(default_external_level)
        logging.getLogger('dataflow.modules.search').setLevel(default_external_level)
        logging.getLogger('dataflow.modules.search.recall').setLevel(default_external_level)
        logging.getLogger('dataflow.modules.search.expand').setLevel(default_external_level)
        logging.getLogger('elasticsearch').setLevel(default_external_level)
        logging.getLogger('urllib3').setLevel(default_external_level)
        logging.getLogger('asyncio').setLevel(default_external_level)

        if show_search_logs:
            # 只放开 pagerank_section 的 INFO
            rerank_logger = logging.getLogger('dataflow.search.rerank.pagerank')
            rerank_logger.setLevel(logging.INFO)
            rerank_logger.propagate = True

            # 把 handler 挂到 root，确保冒泡的 INFO 能写入
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)
            if file_handler not in root_logger.handlers:
                root_logger.addHandler(file_handler)
            if console_handler not in root_logger.handlers:
                root_logger.addHandler(console_handler)

        total_questions = len(self.questions)
        num_batches = (total_questions + batch_size - 1) // batch_size

        print(f"\n{'='*60}")
        print(f"INCREMENTAL PROCESSING")
        print(f"Total questions: {total_questions}")
        print(f"Batch size: {batch_size}")
        print(f"Number of batches: {num_batches}")
        print(f"Log file: {log_file}")
        print(f"{'='*60}\n")

        all_results = []
        global_start_time = time.time()

        # 分批处理
        for batch_idx in range(num_batches):
            start_idx = batch_idx * batch_size
            end_idx = min((batch_idx + 1) * batch_size, total_questions)

            print(f"\n[Batch {batch_idx + 1}/{num_batches}] Processing questions {start_idx}-{end_idx}")
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"Batch {batch_idx + 1}/{num_batches}: questions {start_idx}-{end_idx}")
            self.logger.info(f"{'='*60}")

            # 处理当前批次
            batch_results, batch_stats = await self.process_batch(
                start_idx=start_idx,
                end_idx=end_idx,
                concurrency=concurrency,
                verbose=verbose,
                log_details=not is_bad_cases_mode  # bad-cases 模式下不记录详细日志
            )

            # 合并到全局结果和统计
            all_results.extend(batch_results)
            self.merge_stats(batch_stats)

            # 打印当前累积统计
            print(f"\n[Progress after batch {batch_idx + 1}/{num_batches}]")
            print(f"  Cumulative recall: {self.stats.cumulative_recall:.4f}")
            print(f"  Total questions: {self.stats.total_questions}")
            print(f"  Perfect recall: {self.stats.perfect_recall_count}")
            print(f"  Partial recall: {self.stats.partial_recall_count}")
            print(f"  Zero recall: {self.stats.zero_recall_count}")

            # 记录累积统计到日志
            self.logger.info(f"\n[Progress after batch {batch_idx + 1}/{num_batches}]")
            self.logger.info(f"  Cumulative recall: {self.stats.cumulative_recall:.4f}")
            self.logger.info(f"  Total questions: {self.stats.total_questions}")
            self.logger.info(f"  Perfect recall: {self.stats.perfect_recall_count}")
            self.logger.info(f"  Partial recall: {self.stats.partial_recall_count}")
            self.logger.info(f"  Zero recall: {self.stats.zero_recall_count}")

            # 记录到日志
            self.logger.info(f"Batch {batch_idx + 1}/{num_batches} completed:")
            self.logger.info(f"  Processed: {len(batch_results)} questions")
            self.logger.info(f"  Failed: {batch_stats.total_questions - len(batch_results)}")
            self.logger.info(f"  Batch recall: {batch_stats.cumulative_recall:.4f}")
            self.logger.info(f"  Cumulative recall: {self.stats.cumulative_recall:.4f}")

            # 打印部分召回的问题列表（如果有）
            if self.stats.partial_recall_questions:
                print(f"\n  部分召回的问题：")
                for q in self.stats.partial_recall_questions[-5:]:  # 显示最近5个
                    print(f"    - {q['question_id']}: {q['percentage']} ({q['recall']:.2f})")

        global_elapsed = time.time() - global_start_time

        # 最终结果统计
        final_stats = self.stats.to_dict()
        final_stats['processing_time_seconds'] = global_elapsed
        final_stats['average_time_per_question'] = global_elapsed / total_questions if total_questions > 0 else 0

        print(f"\n{'='*60}")
        print("FINAL RESULTS")
        print(f"{'='*60}")
        print(f"Total questions processed: {final_stats['total_questions']}")
        print(f"Overall recall: {final_stats['cumulative_recall']:.4f}")
        print(f"Perfect recall count: {final_stats['perfect_recall_count']}")
        print(f"Partial recall count: {final_stats['partial_recall_count']}")
        print(f"Zero recall count: {final_stats['zero_recall_count']}")

        # 记录到日志
        self.logger.info(f"\n{'='*60}")
        self.logger.info("FINAL RESULTS")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"Total questions: {final_stats['total_questions']}")
        self.logger.info(f"Overall recall: {final_stats['cumulative_recall']:.4f}")
        self.logger.info(f"Perfect recall: {final_stats['perfect_recall_count']}")
        self.logger.info(f"Partial recall: {final_stats['partial_recall_count']}")
        self.logger.info(f"Zero recall: {final_stats['zero_recall_count']}")

        # 详细列出所有部分召回的问题
        if final_stats['partial_recall_questions']:
            print(f"\n[部分召回问题列表] ({len(final_stats['partial_recall_questions'])} 个)：")
            self.logger.info(f"\n[部分召回问题列表] ({len(final_stats['partial_recall_questions'])} 个)：")
            for q in final_stats['partial_recall_questions']:
                msg = f"  - {q['question_id']}: 找到 {q['recalled']} / {q['total_oracle']} 个答案 " \
                      f"(召回率: {q['recall']:.2%})"
                print(msg)
                self.logger.info(msg)

        # 详细列出所有零召回的问题（生成Bad Case）
        zero_recall_questions = [q for q in final_stats['per_question'] if q['recall'] == 0.0]
        if zero_recall_questions:
            print(f"\n[零召回问题列表（Bad Case）] ({len(zero_recall_questions)} 个)：")
            self.logger.warning(f"\n[零召回问题列表（Bad Case）] ({len(zero_recall_questions)} 个)：")
            for q in zero_recall_questions:
                msg = f"  - {q['question_id']}: {q['question'][:100]}..."
                print(f"  - {q['question_id']}: {q['question'][:100]}...")
                self.logger.warning(msg)

        print(f"\nTotal processing time: {global_elapsed:.2f}s")
        print(f"{'='*60}")

        self.logger.info(f"Total processing time: {global_elapsed:.2f}s")
        self.logger.info(f"{'='*60}")

        # 强制刷新日志到文件
        for handler in self.logger.handlers:
            handler.flush()

        # 保存结果
        if save_results and self.data_dir:
            self.save_results(all_results, final_stats, log_file, output_dir, track_zero_recall=track_zero_recall)
        else:
            print(f"\n💡 检索详细日志已保存到: {log_file}")

        return final_stats, log_file

    def save_results(self, results: List["RetrievalResult"], stats: Dict[str, Any], log_file: Path, output_dir: Path, track_zero_recall: bool = False):
        """
        保存结果到文件

        Args:
            results: 检索结果列表
            stats: 统计信息
            log_file: 日志文件路径
            output_dir: 输出目录路径
            track_zero_recall: 是否追踪零召回问题（生成Bad Case报告）
        """
        if not self.data_dir:
            print("[WARN] Cannot save results: data_dir not set")
            return

        print(f"\n[INFO] Saving results to: {output_dir}")

        # 保存检索结果
        output_path = output_dir / "retrieval_results.jsonl"
        write_jsonl(results, output_path)
        print(f"[INFO] Saved retrieval results: {output_path}")

        # 保存统计信息
        stats_path = output_dir / "recall_evaluation.json"
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Saved evaluation stats: {stats_path}")

        # 保存部分召回问题（需要关注的问题）
        if stats.get('partial_recall_questions'):
            partial_path = output_dir / "partial_recall_cases.json"
            with open(partial_path, 'w', encoding='utf-8') as f:
                json.dump(stats['partial_recall_questions'], f, ensure_ascii=False, indent=2)
            print(f"[INFO] Saved partial recall cases: {partial_path} ({len(stats['partial_recall_questions'])} 个)")

        # 保存零召回问题（Bad Case）- 仅在 track_zero_recall=True 时保存
        if track_zero_recall:
            zero_recall_questions = [q for q in stats['per_question'] if q['recall'] == 0.0]
            if zero_recall_questions:
                zero_path = output_dir / "bad_cases_zero_recall.json"
                with open(zero_path, 'w', encoding='utf-8') as f:
                    json.dump(zero_recall_questions, f, ensure_ascii=False, indent=2)
                print(f"[INFO] Saved bad cases (zero recall): {zero_path} ({len(zero_recall_questions)} 个)")

        print(f"\n💡 检索详细日志已保存到: {log_file}")
        print(f"💡 所有评估结果已保存到: {output_dir}")

    async def cleanup(self):
        """清理资源"""
        if self.searcher:
            await close_es_client()
            print("[INFO] Cleanup completed")


async def main():
    """主函数示例"""
    import argparse

    parser = argparse.ArgumentParser(description='Retrieve and Recall Evaluation')
    parser.add_argument('--data-dir', type=str, help='Data directory path (optional)')
    parser.add_argument('--batch-size', type=int, default=5, help='Batch size (default: 50)')
    parser.add_argument('--concurrency', type=int, default=5, help='Concurrency (default: 5)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--no-save', action='store_true', help='Do not save results')
    parser.add_argument('--track-zero-recall', action='store_true', help='Track and save zero recall questions as bad cases')
    parser.add_argument('--bad-cases', type=str, help='Path to bad_cases_zero_recall.json file to re-evaluate only those questions')
    parser.add_argument('--limit', type=int, help='Limit the number of questions to process (optional)')
    parser.add_argument('--show-search-logs', action='store_true', help='Show full search logs (dataflow/SAG set to INFO)')

    args = parser.parse_args()

    # 创建评估器
    evaluator = RetrieveRecallEvaluator(data_dir=args.data_dir)

    try:
        # 1. 加载数据文件夹
        evaluator.load_data_directory()

        # 2. 加载参数
        params = evaluator.load_parameters()
        print(f"\n{'='*60}")
        print(f"📋 LOADED PARAMETERS")
        print(f"{'='*60}")
        print(f"  🔑 source_config_id: {params['source_config_id']}")
        print(f"  📚 corpus_size: {params['corpus_size']}")
        print(f"  ❓ question_count: {params['question_count']}")
        print(f"{'='*60}")

        # 2.3. 如果指定了 limit，则只处理前 N 个问题
        if args.limit and args.limit > 0:
            original_count = len(evaluator.questions)
            evaluator.questions = evaluator.questions[:args.limit]
            print(f"[INFO] Limited to first {args.limit} questions (original: {original_count})")

        # 2.5. 如果指定了 bad-cases 文件，则只处理这些问题
        if args.bad_cases:
            print(f"\n{'='*60}")
            print("BAD CASES MODE")
            print(f"{'='*60}")
            bad_case_ids = evaluator.load_bad_cases(args.bad_cases)
            evaluator.filter_questions_by_ids(bad_case_ids)
            print(f"[INFO] Will re-evaluate {len(evaluator.questions)} bad case questions")
            print(f"[INFO] Bad-cases mode: Only log file will be saved (no result files)")
            print(f"{'='*60}\n")

        # 3. 初始化搜索器
        evaluator.init_searcher()

        # 4. 运行增量处理
        # 在 bad-cases 模式下，默认不保存结果文件，只保存日志，并复用 bad_cases 所在的文件夹
        should_save_results = False if args.bad_cases else (not args.no_save)

        # 在 bad-cases 模式下，使用 bad_cases 文件所在的目录
        output_dir_arg = None
        if args.bad_cases:
            output_dir_arg = Path(args.bad_cases).parent

        stats, log_file = await evaluator.run_incremental(
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            verbose=args.verbose,
            save_results=should_save_results,
            track_zero_recall=args.track_zero_recall,
            output_dir=output_dir_arg,
            is_bad_cases_mode=bool(args.bad_cases),
            show_search_logs=args.show_search_logs
        )

        # 5. 显示最终统计
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Total questions: {stats['total_questions']}")
        print(f"Overall recall: {stats['cumulative_recall']:.2%}")
        print(f"Perfect recall: {stats['perfect_recall_count']}")
        print(f"Partial recall: {stats['partial_recall_count']}")
        print(f"Zero recall: {stats['zero_recall_count']}")
        print(f"\nLog file: {log_file}")

        # 记录最终统计到日志
        logger = logging.getLogger(__name__)
        logger.info(f"\n{'='*60}")
        logger.info("SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total questions: {stats['total_questions']}")
        logger.info(f"Overall recall: {stats['cumulative_recall']:.2%}")
        logger.info(f"Perfect recall: {stats['perfect_recall_count']}")
        logger.info(f"Partial recall: {stats['partial_recall_count']}")
        logger.info(f"Zero recall: {stats['zero_recall_count']}")
        logger.info(f"\nLog file: {log_file}")

        # 显示生成的文件（仅在非 bad-cases 模式且保存了结果时显示）
        if should_save_results and evaluator.data_dir:
            print(f"\nGenerated files:")
            logger.info(f"\nGenerated files:")
            print(f"  - retrieval_results.jsonl")
            logger.info(f"  - retrieval_results.jsonl")
            print(f"  - recall_evaluation.json")
            logger.info(f"  - recall_evaluation.json")
            if stats.get('partial_recall_questions'):
                msg = f"  - partial_recall_cases.json ({len(stats['partial_recall_questions'])} cases)"
                print(msg)
                logger.info(msg)
            zero_count = len([q for q in stats['per_question'] if q['recall'] == 0.0])
            if zero_count > 0:
                msg = f"  - bad_cases_zero_recall.json ({zero_count} cases)"
                print(msg)
                logger.info(msg)

        # 刷新日志到文件
        for handler in logger.handlers:
            handler.flush()

    finally:
        # 6. 清理资源
        await evaluator.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
