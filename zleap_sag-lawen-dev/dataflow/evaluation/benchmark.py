"""
评估基准测试模块

提供数据集评估、检索评估和QA评估功能

使用方法：

1. 指定功能模式（必需）:
   使用 --foundation 参数指定核心功能模式:

   a) Upload 模式 - 加载数据集并上传到系统:
      python dataflow/evaluation/benchmark.py \
          --foundation upload \
          --dataset test_hotpotqa

      可选参数:
      --chunks-per-file 500  # 每个文件的片段数（默认: 500）

   b) Search 模式 - 执行检索并评估召回率:
      python dataflow/evaluation/benchmark.py \
          --foundation search \
          --dataset test_hotpotqa \
          --info-limit 5 \
          --search-verbose

      可选参数:
      --info-limit N         # 限制问题数量（可选）
      --search-verbose       # 显示详细检索过程
      --enable-qa            # 启用 QA 评估
      --no-paragraphs        # 隐藏段落详细信息

   c) Badcase Zero 模式 - 重测 Zero Recall Badcase:
      python dataflow/evaluation/benchmark.py \
          --foundation badcase_zero \
          --dataset test_hotpotqa \
          --info-limit 5

   d) Badcase Partial 模式 - 重测 Partial Recall Badcase:
      python dataflow/evaluation/benchmark.py \
          --foundation badcase_partial \
          --dataset test_hotpotqa \
          --info-limit 5

2. 数据集选择（必需）:
   --dataset DATASET_NAME   # 数据集名称（支持: musique, hotpotqa, 2wikimultihopqa, test_hotpotqa, sample）

3. 模型配置（通过 .env 文件）:
   系统会自动读取 .env 文件中的 LLM_MODEL 配置:
   - gpt-4o, gpt-4o-mini (OpenAI)
   - Qwen/qwen3, qwen-max (阿里云)
   - claude-3-5-sonnet-20241022 (Anthropic)

   模型名称会自动过滤为简写形式（如 Qwen/qwen3 → qwen3）用于目录命名。

4. 输出结果:
   - 信息源文件: dataflow/evaluation/source/SAG/{model_name}/{dataset_name}/{timestamp}/
   - Badcase 文件: dataflow/evaluation/outputs/SAG/{model_name}/{dataset_name}/{timestamp}/
   - 评估结果: outputs/evaluation/（如果使用 API 方式）

完整示例:

# 步骤1: 上传数据集（首次运行）
python dataflow/evaluation/benchmark.py \
    --foundation upload \
    --dataset test_hotpotqa

# 步骤2: 测试检索性能
python dataflow/evaluation/benchmark.py \
    --foundation search \
    --dataset test_hotpotqa \
    --info-limit 10 \
    --search-verbose \
    --enable-qa

# 步骤3: 分析 badcase（如果有）
python dataflow/evaluation/benchmark.py \
    --foundation badcase_zero \
    --dataset test_hotpotqa \
    --info-limit 5

注意:
- Badcase 文件从 dataflow/evaluation/outputs/SAG/{model_name}/{dataset_name}/{timestamp}/ 自动加载
- Badcase 模式下不支持 QA 评估（会自动禁用）
- 使用最新的时间戳目录
- 向后兼容旧的参数语法
"""

import json
import sys
import time
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Callable
from datetime import datetime
from dataclasses import dataclass, field, asdict

from dataflow.utils import get_logger
from dataflow.evaluation.utils import DatasetLoader
from dataflow.evaluation.metrics import (
    QAExactMatch,
    QAF1Score,
    RetrievalRecall,
)
from dataflow import DataFlowEngine, ExtractBaseConfig
from dataflow.modules.load.config import DocumentLoadConfig
from dataflow.db import close_database
from dataflow.engine.config import TaskConfig

# 搜索相关导入
from dataflow.modules.search import SAGSearcher, SearchConfig
from dataflow.modules.search.config import (
    ReturnType, RecallConfig, ExpandConfig, RerankConfig, RecallMode
)
from dataflow.core.prompt.manager import PromptManager
from dataflow.core.storage.elasticsearch import close_es_client
from dataflow.core.ai.factory import create_llm_client
from dataflow.core.ai.base import BaseLLMClient
from dataflow.core.ai.models import LLMMessage, LLMRole

# Token追踪器（最小化版本）
class LLMTokenTracker:
    """追踪LLM调用的token消耗"""
    def __init__(self):
        self.total = {"prompt": 0, "completion": 0, "total": 0}
        self.stages = {}

    def record(self, stage: str, usage):
        """记录token"""
        if not usage:
            return
        prompt = getattr(usage, 'prompt_tokens', 0)
        completion = getattr(usage, 'completion_tokens', 0)
        total = getattr(usage, 'total_tokens', 0)

        self.total["prompt"] += prompt
        self.total["completion"] += completion
        self.total["total"] += total

        if stage not in self.stages:
            self.stages[stage] = {"calls": 0, "prompt": 0, "completion": 0, "total": 0}

        self.stages[stage]["calls"] += 1
        self.stages[stage]["prompt"] += prompt
        self.stages[stage]["completion"] += completion
        self.stages[stage]["total"] += total

    def get_summary(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "total_prompt": self.total["prompt"],
            "total_completion": self.total["completion"],
            "total_tokens": self.total["total"],
            "total_calls": sum(s["calls"] for s in self.stages.values()),
            "stages": self.stages
        }


def enable_llm_tracking(token_tracker: LLMTokenTracker):
    """启用LLM调用追踪（兼容所有阶段：LOAD, EXTRACT, SEARCH, QA）"""
    from dataflow.core.ai import llm
    original_chat = llm.OpenAIClient.chat

    async def tracked_chat(self, messages, **kwargs):
        result = await original_chat(self, messages, **kwargs)
        import inspect
        frame = inspect.currentframe()
        stage = "UNKNOWN"

        try:
            # 向上查找调用栈，最多查找30层
            for _ in range(30):
                if not frame:
                    break
                frame = frame.f_back
                if not frame:
                    break

                # 检查函数名（用于QA阶段）
                func_name = frame.f_code.co_name if frame.f_code else ""
                if func_name == "show_retrieval_info":
                    stage = "QA"
                    break

                # 检查类名（用于LOAD, EXTRACT, SEARCH阶段）
                if 'self' in frame.f_locals:
                    obj = frame.f_locals['self']
                    class_name = obj.__class__.__name__

                    # 检查所有可能的阶段
                    if 'DocumentLoader' in class_name or 'DocumentProcessor' in class_name:
                        stage = "LOAD"
                        break
                    elif 'EventProcessor' in class_name or 'EventExtractor' in class_name:
                        stage = "EXTRACT"
                        break
                    elif 'RecallSearcher' in class_name:
                        stage = "SEARCH"
                        break
        except:
            pass
        finally:
            del frame

        if hasattr(result, 'usage') and result.usage:
            token_tracker.record(stage, result.usage)

        return result

    llm.OpenAIClient.chat = tracked_chat


logger = get_logger("evaluation.benchmark")


@dataclass
class EvaluationConfig:
    """评估配置"""

    # 数据集配置
    dataset_name: str = "musique"
    dataset_dir: Optional[str] = None

    # 评估类型
    evaluate_retrieval: bool = True
    evaluate_qa: bool = True

    # 检索评估配置
    retrieval_top_k_list: List[int] = field(default_factory=lambda: [1, 5, 10, 20])

    # QA评估配置
    qa_aggregation: str = "max"  # max, mean, etc.

    # 输出配置
    save_results: bool = True
    output_dir: str = "./outputs/SAG"
    save_predictions: bool = True
    verbose: bool = True

    # 采样配置（用于快速测试）
    max_samples: Optional[int] = None  # None表示使用全部样本


class Evaluate:
    """
    评估类

    提供完整的数据集评估功能，包括检索评估和QA评估
    """

    # 类级别的 LLM 客户端缓存
    _llm_client: Optional[BaseLLMClient] = None
    _prompt_manager: Optional[PromptManager] = None

    def __init__(self, config: Optional[EvaluationConfig] = None):
        """
        初始化评估器

        Args:
            config: 评估配置，如果为None则使用默认配置
        """
        self.config = config or EvaluationConfig()

        # 数据集加载器
        self.dataset_loader: Optional[DatasetLoader] = None

        # 数据缓存
        self.docs: Optional[List[str]] = None
        self.questions: Optional[List[str]] = None
        self.gold_answers: Optional[List[Set[str]]] = None
        self.gold_docs: Optional[List[List[str]]] = None

        # 评估指标
        self.qa_em_metric = QAExactMatch()
        self.qa_f1_metric = QAF1Score()
        self.retrieval_recall_metric = RetrievalRecall()

        # 输出目录
        self.output_dir = Path(self.config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized Evaluate with config: {asdict(self.config)}")

    @classmethod
    def load_badcase_questions(cls, dataset_name: str, badcase_type: str) -> Optional[List[str]]:
        """
        从 badcase 文件中加载问题列表（用于重测 badcase）

        Args:
            dataset_name: 数据集名称
            badcase_type: badcase 类型 ('zero' 或 'partial')

        Returns:
            问题列表，如果加载失败返回 None
        """
        import json
        from pathlib import Path

        try:
            # 获取当前模型名称
            from dataflow.core.config import get_settings
            settings = get_settings()
            model_name = settings.llm_model
            if '/' in model_name:
                filtered_model_name = model_name.split('/')[-1]
            else:
                filtered_model_name = model_name

            # 构建 badcase 文件路径
            # SAG/{model_name}/{dataset_name}/
            badcase_base_dir = Path(__file__).parent / "outputs" / "SAG" / filtered_model_name / dataset_name

            if not badcase_base_dir.exists():
                logger.warning(f"Badcase 目录不存在: {badcase_base_dir}")
                return None

            # 查找最新的时间戳目录
            timestamp_dirs = [d for d in badcase_base_dir.iterdir() if d.is_dir()]
            if not timestamp_dirs:
                logger.warning(f"没有找到时间戳目录: {badcase_base_dir}")
                return None

            # 按时间戳排序，获取最新的
            latest_timestamp_dir = max(timestamp_dirs, key=lambda d: d.name)

            # 构建 badcase 文件名
            badcase_file = latest_timestamp_dir / f"{badcase_type}_{dataset_name}.json"

            if not badcase_file.exists():
                logger.warning(f"Badcase 文件不存在: {badcase_file}")
                return None

            logger.info(f"加载 {badcase_type} badcase 文件: {badcase_file}")

            # 加载 badcase 数据
            with open(badcase_file, 'r', encoding='utf-8') as f:
                badcase_data = json.load(f)

            # 提取问题列表
            questions = [case['question'] for case in badcase_data]

            logger.info(f"成功加载 {len(questions)} 个 {badcase_type} badcase 问题")

            return questions

        except Exception as e:
            logger.warning(f"加载 badcase 文件失败: {e}")
            import traceback
            logger.warning(f"详细错误信息: {traceback.format_exc()}")
            return None

    @classmethod
    def load_latest_source_info(cls, dataset_name: str) -> Dict[str, Any]:
        """
        从 dataflow/evaluation/source/SAG/{model_name}/{dataset_name}/{timestamp}/ 路径下加载最新时间戳文件夹的 source_info.json

        支持新的路径结构：SAG/{model_name}/{dataset_name}/{timestamp}/
        向下兼容旧的路径结构：SAG/{dataset_name}/{timestamp}/

        自动从配置中获取当前模型名称，优先使用该模型的数据集。

        Args:
            dataset_name: 数据集名称

        Returns:
            包含 source_config_id 和 dataset_name 的字典
        """
        import json
        from pathlib import Path

        # 从配置获取当前模型名称（从环境变量或配置文件中）
        try:
            from dataflow.core.config import get_settings
            settings = get_settings()

            # 获取模型名称（从 LLM 配置中）
            model_name = settings.llm_model

            # 过滤模型名称，只保留最后一层（例如：Qwen/qwen3 -> qwen3）
            if '/' in model_name:
                filtered_model_name = model_name.split('/')[-1]
            else:
                filtered_model_name = model_name

            logger.info(f"从配置获取模型名称: {model_name} -> 过滤后: {filtered_model_name}")
        except Exception as e:
            logger.warning(f"获取模型名称失败: {e}，将使用自动检测模式")
            filtered_model_name = None

        # 获取 SAG 目录路径
        current_file = Path(__file__)
        sag_base_dir = current_file.parent / "source" / "SAG"

        if not sag_base_dir.exists():
            raise FileNotFoundError(f"SAG directory not found: {sag_base_dir}")

        # 查找所有可能的 source_info.json 文件
        all_source_info_files = []

        # 如果获取到模型名称，优先使用该模型的数据集
        if filtered_model_name:
            model_dataset_dir = sag_base_dir / filtered_model_name / dataset_name
            if model_dataset_dir.exists():
                timestamp_dirs = [d for d in model_dataset_dir.iterdir() if d.is_dir()]
                for timestamp_dir in timestamp_dirs:
                    source_info_path = timestamp_dir / "source_info.json"
                    if source_info_path.exists():
                        all_source_info_files.append(source_info_path)

        # 如果没有找到（或没有指定模型），则遍历所有 model_name 目录
        if not all_source_info_files:
            for model_dir in sag_base_dir.iterdir():
                if model_dir.is_dir():
                    dataset_dir = model_dir / dataset_name
                    if dataset_dir.exists():
                        # 获取该数据集下的所有时间戳文件夹
                        timestamp_dirs = [d for d in dataset_dir.iterdir() if d.is_dir()]
                        for timestamp_dir in timestamp_dirs:
                            source_info_path = timestamp_dir / "source_info.json"
                            if source_info_path.exists():
                                all_source_info_files.append(source_info_path)

        # 向下兼容旧的路径结构
        old_dataset_dir = sag_base_dir / dataset_name
        if old_dataset_dir.exists():
            timestamp_dirs = [d for d in old_dataset_dir.iterdir() if d.is_dir()]
            for timestamp_dir in timestamp_dirs:
                source_info_path = timestamp_dir / "source_info.json"
                if source_info_path.exists():
                    all_source_info_files.append(source_info_path)

        if not all_source_info_files:
            raise FileNotFoundError(f"No source_info.json found for dataset: {dataset_name}")

        # 按文件修改时间排序，获取最新的
        latest_source_info_path = max(all_source_info_files, key=lambda p: p.stat().st_mtime)

        # 提取模型名称、数据集名称等信息
        path_parts = latest_source_info_path.parts
        model_part = None

        # 检测路径结构：尝试找到 model 位置
        try:
            # 查找路径中的 model_name 部分
            if 'SAG' in path_parts:
                sag_index = path_parts.index('SAG')
                if len(path_parts) > sag_index + 3:
                    model_part = path_parts[sag_index + 1]  # model_name
                    dataset_part = path_parts[sag_index + 2]  # dataset_name
        except:
            pass

        logger.info(f"Loading source info from: {latest_source_info_path}")
        if model_part and model_part != dataset_name:
            logger.info(f"使用模型: {model_part}")

        with open(latest_source_info_path, 'r', encoding='utf-8') as f:
            source_info = json.load(f)

        return {
            'source_config_id': source_info.get('source_config_id'),
            'dataset_name': source_info.get('dataset_name'),
            'timestamp': source_info.get('timestamp'),
            'source_name': source_info.get('source_name'),
            'model_name': model_part if model_part and model_part != dataset_name else None,
            'file_path': str(latest_source_info_path)
        }
    
    @classmethod
    def load_dataset_info(cls, dataset_name: str) -> Dict[str, Any]:
        """
        从 dataflow/evaluation/dataset 目录加载指定数据集的信息
        
        Args:
            dataset_name: 数据集名称
        
        Returns:
            包含 questions, answers, paragraphs 信息的字典
        """
        from dataflow.evaluation.utils import DatasetLoader
        
        # 使用 DatasetLoader 加载数据集
        loader = DatasetLoader(dataset_name)
        
        # 加载原始样本数据
        samples = loader.load_samples()
        
        questions = []
        answers = []
        all_paragraphs = []
        
        for sample in samples:
            questions.append(sample.get('question', ''))
            answers.append(sample.get('answer', []))
            all_paragraphs.append(sample.get('paragraphs', []))
        
        return {
            'dataset_name': dataset_name,
            'total_questions': len(questions),
            'questions': questions,
            'answers': answers,
            'paragraphs': all_paragraphs,
            'samples': samples
        }
    
    @classmethod
    async def search_questions(cls, source_config_id: str, questions: List[str], limit: Optional[int] = None, verbose: bool = False, bench_size: Optional[int] = None, callback: Optional[Callable] = None) -> List[Dict[str, Any]]:
        """
        对问题列表进行检索，返回检索结果

        Args:
            source_config_id: 数据源ID
            questions: 问题列表
            limit: 限制处理的问题数量
            verbose: 是否显示详细信息
            bench_size: 每N个问题执行一次回调
            callback: 回调函数，接收 (current_idx, total, results_so_far)

        Returns:
            检索结果列表
        """
        import logging

        # 获取 logger
        logger = get_logger('dataflow.evaluation.search')

        logger.info("Initializing searcher...")
        
        # 配置日志级别
        if verbose:
            logger.info("启用详细日志模式...")

            # 创建控制台handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)

            # 设置各个模块的日志级别（排除 evaluation，避免影响 benchmark 输出）
            loggers_to_configure = [
                'dataflow.modules.search',
                'dataflow.modules.search.recall',
                'dataflow.modules.search.expand',
                'dataflow.modules.search.rerank',
                'dataflow.search.rerank.pagerank',
                'dataflow.search.pagerank'
            ]

            for logger_name in loggers_to_configure:
                logger_obj = logging.getLogger(logger_name)
                logger_obj.setLevel(logging.INFO)
                # 清除现有handlers避免重复
                logger_obj.handlers = []
                logger_obj.addHandler(console_handler)
                logger_obj.propagate = False
            # 配置根logger以确保所有日志都能输出
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)
            if not root_logger.handlers:
                root_logger.addHandler(console_handler)

        else:
            logger.info("使用默认日志级别(ERROR)...")
            # 只显示WARNING级别的日志（排除 evaluation）
            for logger_name in ['dataflow.modules.search', 'elasticsearch', 'urllib3']:
                logging.getLogger(logger_name).setLevel(logging.ERROR)
        
        # 初始化搜索器
        prompt_manager = PromptManager()
        searcher = SAGSearcher(prompt_manager=prompt_manager)
        
        # 应用限制
        process_questions = questions[:limit] if limit else questions
        logger.info(f"Processing {len(process_questions)} questions for search")
        
        search_results = []

        for i, question in enumerate(process_questions, 1):
            if verbose:
                logger.info(f"\n[{i}/{len(process_questions)}] Searching: {question}")

            # 配置搜索参数
            search_config = SearchConfig(
                query=question,
                source_config_id=source_config_id,
                return_type=ReturnType.PARAGRAPH,
                recall=RecallConfig(
                    use_fast_mode=False,
                    vector_top_k=50,
                    max_entities=50,
                    recall_mode=RecallMode.FUZZY,
                    entity_similarity_threshold=0.3,
                    entity_weight_threshold=0.2
                ),
                expand=ExpandConfig(max_hops=3),
                rerank=RerankConfig(
                    max_results=10,
                    score_threshold=0.45,
                    strategy="pagerank"
                )
            )
            
            try:
                # 执行搜索
                search_result = await searcher.search(search_config)
                sections = search_result.get("sections", [])
                
                # 段落去重
                seen_chunk_ids = set()
                unique_sections = []
                for section in sections:
                    chunk_id = section.get('chunk_id')
                    if chunk_id and chunk_id not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk_id)
                        unique_sections.append(section)
                
                search_results.append({
                    'question_index': i,
                    'question': question,
                    'sections': unique_sections,
                    'total_sections': len(unique_sections),
                    'search_success': True
                })
                
                if verbose:
                    logger.info(f"   Found {len(unique_sections)} unique sections")
                    
            except Exception as e:
                logger.error(f"   Search failed: {e}")
                search_results.append({
                    'question_index': i,
                    'question': question,
                    'sections': [],
                    'total_sections': 0,
                    'search_success': False,
                    'error': str(e)
                })

            # 🆕 每 bench_size 个问题执行回调
            if bench_size and callback and i % bench_size == 0:
                await callback(i, len(process_questions), search_results)

        # 清理资源
        try:
            await close_es_client()
        except Exception as e:
            logger.warning(f"Error closing ES client: {e}")

        logger.info(f"Search completed for {len(search_results)} questions")
        return search_results
    
    @classmethod
    def _check_content_similarity(cls, gold_content: str, retrieved_content: str) -> bool:
        """
        检查内容相似性
        
        Args:
            gold_content: 标准内容
            retrieved_content: 检索到的内容
            
        Returns:
            是否匹配
        """
        # 简单的内容匹配逻辑：检查关键词是否存在
        gold_words = set(gold_content.lower().split())
        retrieved_words = set(retrieved_content.lower().split())
        
        # 计算交集的比例
        if len(gold_words) == 0:
            return False
            
        intersection = gold_words & retrieved_words
        similarity_ratio = len(intersection) / len(gold_words)
        
        # 如果交集超过50%，认为匹配成功
        return similarity_ratio >= 0.5
    
    @classmethod
    async def show_retrieval_info(cls, limit: Optional[int] = None, show_paragraphs: bool = True, enable_search: bool = False, search_verbose: bool = False, enable_qa: bool = False, dataset_name: Optional[str] = None, badcase: Optional[str] = None, bench_size: Optional[int] = None, enable_mlflow: bool = False, mlflow_uri: Optional[str] = None, mlflow_experiment: Optional[str] = None) -> Dict[str, Any]:
        """
        显示检索相关信息：最新的 source_config_id、dataset_name 和数据集内容，可选进行实际检索

        Args:
            limit: 限制显示的问题数量，None表示显示全部
            show_paragraphs: 是否显示 paragraphs 详细信息
            enable_search: 是否启用实际检索功能
            search_verbose: 检索过程是否显示详细信息
            enable_qa: 是否启用 QA 评估功能
            dataset_name: 数据集名称。如果为None，则遍历所有数据集目录找最新的
            badcase: 加载特定的 badcase 进行测试 ('zero' 或 'partial')

        Returns:
            完整的检索信息字典
        """
        logger.info("Loading latest source information...")
        
        # 1. 加载最新的 source_info
        try:
            source_info = cls.load_latest_source_info(dataset_name)
            logger.info("Successfully loaded source information")
        except Exception as e:
            logger.error(f"Failed to load source info: {e}")
            raise

        # 2. 加载对应的数据集信息
        if dataset_name is None:
            dataset_name = source_info['dataset_name']
        logger.info(f"Loading dataset: {dataset_name}")

        # 无论是否加载 badcase，都需要创建 dataset_loader
        try:
            from dataflow.evaluation.utils.load_utils import DatasetLoader
            dataset_loader = DatasetLoader(dataset_name)
        except Exception as e:
            logger.error(f"Failed to create dataset loader for {dataset_name}: {e}")
            raise

        # 🆕 检查是否加载 badcase
        if badcase:
            logger.info(f"\n🎯 Badcase 模式: 加载 {badcase} recall 的问题")
            badcase_questions = cls.load_badcase_questions(dataset_name, badcase)

            if badcase_questions is None or len(badcase_questions) == 0:
                logger.error(f"无法加载 {badcase} badcase，请确保已经运行过检索评估并保存了 badcase")
                sys.exit(1)

            # 从 badcase 加载问题
            if limit:
                questions = badcase_questions[:limit]
            else:
                questions = badcase_questions

            answers = [None] * len(questions)  # Badcase 文件中不包含答案
            paragraphs = [None] * len(questions)

            # 加载数据集信息（用于 gold_docs 和返回 val）
            try:
                dataset_info = dataset_loader.load_all()
            except Exception as e:
                logger.error(f"Failed to load dataset info: {e}")
                raise

            logger.info(f"成功加载 {len(questions)} 个 {badcase} badcase 问题")
        else:
            # 正常加载数据集
            try:
                dataset_info = dataset_loader.load_all()
                logger.info(f"Successfully loaded dataset with {dataset_info['total_questions']} questions")
            except Exception as e:
                logger.error(f"Failed to load dataset {dataset_name}: {e}")
                raise

            # 正常获取数据集信息
            questions = dataset_info['questions']
            answers = dataset_info['answers']
            paragraphs = dataset_info['paragraphs']

        # 3. 打印信息
        logger.info("\n" + "=" * 80)
        logger.info("🔍 检索信息概览")
        logger.info("=" * 80)
        logger.info(f"📁 信息源文件: {source_info['file_path']}")
        logger.info(f"🆔 信息源ID: {source_info['source_config_id']}")
        logger.info(f"📊 数据集名称: {source_info['dataset_name']}")
        logger.info(f"📅 时间戳: {source_info['timestamp']}")
        logger.info(f"📝 信息源名称: {source_info['source_name']}")
        logger.info(f"❓ 问题总数: {len(questions)}")

        if badcase:
            logger.info(f"🎯 测试模式: {badcase} recall badcase")

        # 4. 显示问题和答案信息

        # 应用限制
        display_limit = min(len(questions), limit) if limit else len(questions)

        logger.info(f"\n📋 显示前 {display_limit} 个问题:")
        logger.info("=" * 80)

        # 判断是否在测试模式（不显示详细信息）
        is_testing_mode = enable_search and badcase

        for i in range(display_limit):
            logger.info(f"\n[问题 {i+1}]")
            logger.info(f"问题: {questions[i]}")

            if not is_testing_mode:
                logger.info(f"答案: {answers[i] if i < len(answers) else 'N/A'}")

                if show_paragraphs and i < len(paragraphs) and paragraphs[i] is not None:
                    para_list = paragraphs[i]
                    logger.info(f"段落信息 ({len(para_list)} 个):")

                    for j, para in enumerate(para_list):
                        title = para.get('title', 'N/A')
                        text = para.get('text', 'N/A')
                        is_supporting = para.get('is_supporting', False)

                        logger.info(f"   [{j+1}] 标题: {title}")
                        logger.info(f"       支持性: {'是' if is_supporting else '否'}")
                        logger.info(f"       内容: {text[:200]}..." if len(text) > 200 else f"       内容: {text}")

            if i < display_limit - 1:  # 不是最后一个
                logger.info("-" * 60)
        
        logger.info("\n" + "=" * 80)
        
        # 5. 如果启用了搜索，执行实际检索
        search_results = None
        recall_evaluation = None
        token_tracker = LLMTokenTracker()  # 🆕 在所有路径下都会创建（用于追踪search和QA）
        search_time = 0.0  # 🆕 SEARCH阶段总耗时

        # 🆕 MLflow 初始化
        mlflow_run = None
        if enable_mlflow and enable_search and not badcase:  # 只在search模式且非badcase时启用
            import mlflow
            from datetime import datetime

            # 设置 tracking URI
            if mlflow_uri:
                mlflow.set_tracking_uri(mlflow_uri)

            # 创建或获取实验
            try:
                mlflow.set_experiment(mlflow_experiment)
            except Exception as e:
                if "deleted experiment" in str(e):
                    # 如果实验被删除，创建新实验
                    new_exp_name = f"{mlflow_experiment}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    mlflow.set_experiment(new_exp_name)
                else:
                    raise

            # 创建运行
            run_name = f"retrieval_{dataset_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            mlflow_run = mlflow.start_run(run_name=run_name)

            # 记录参数
            mlflow.log_params({
                "dataset": dataset_name,
                "bench_size": bench_size or 0,
                "total_questions": len(questions),
                "enable_qa": enable_qa,
                "vector_top_k": 50,
                "max_entities": 50,
                "max_hops": 3,
                "max_results": 10
            })

            logger.info(f"✅ MLflow 监控已启用 (实验: {mlflow_experiment}, 运行: {run_name})")

        if enable_search:
            logger.info(f"\n启动实际检索 (数据源: {source_info['source_config_id']})...")
            logger.info("=" * 80)

            # 🆕 启用 LLM token 追踪（在search之前）
            enable_llm_tracking(token_tracker)
            logger.info("✅ 检索阶段的LLM调用追踪已启用")

            try:
                # 🆕 开始计时
                search_start = time.perf_counter()

                # 预获取标准答案文档，用于 bench_size 回调
                gold_docs_for_recall = dataset_loader.get_gold_docs_for_recall(max_length=500, limit=display_limit)

                # 🆕 使用独立的 logger 用于 benchmark 输出（不受 verbose 参数影响）
                bench_logger = logging.getLogger('dataflow.evaluation.benchmark')
                # 显式设置级别为 INFO，确保不受 root logger 级别影响
                bench_logger.setLevel(logging.INFO)
                # 添加 handler，确保日志能够输出
                if not bench_logger.handlers:
                    console_handler = logging.StreamHandler()
                    console_handler.setLevel(logging.INFO)
                    formatter = logging.Formatter('%(message)s')
                    console_handler.setFormatter(formatter)
                    bench_logger.addHandler(console_handler)
                    bench_logger.propagate = False  # 不传播到root logger

                # 定义 bench_size 回调函数
                async def bench_callback(current_idx, total, results_so_far):
                    """每 bench_size 个问题执行的回调"""
                    # 计算批次信息 (批次从1开始编号)
                    batch_index = (current_idx + bench_size - 1) // bench_size  # 向上取整
                    total_batches = (total + bench_size - 1) // bench_size  # 向上取整

                    bench_logger.info(f"\n{'='*80}")
                    bench_logger.info(f"📝 Bench 进度: 批次 {batch_index}/{total_batches} ({current_idx}/{total} 问题)")
                    bench_logger.info(f"{'='*80}")

                    # 获取当前已处理问题的 gold_docs
                    current_gold_docs = gold_docs_for_recall[:current_idx]

                    # 计算累积统计（重新计算 matched_docs，因为此时还没有匹配信息）
                    full_count = 0
                    partial_count = 0
                    zero_count = 0

                    for i, result in enumerate(results_so_far):
                        gold_docs = current_gold_docs[i]
                        retrieved_docs = []

                        # 获取检索结果段落（格式与召回评估一致）
                        for section in result['sections']:
                            heading = section.get('heading', '')
                            content = section.get('content', '')
                            clean_heading = heading.lstrip('#').strip()
                            clean_content = content.strip()
                            if clean_heading and clean_content:
                                retrieved_docs.append({
                                    'title': clean_heading,
                                    'content': clean_content
                                })

                        # 重新计算 matched_docs
                        matched_docs = []
                        for gold_doc in gold_docs:
                            for retrieved_doc in retrieved_docs:
                                title_match = gold_doc['title'].strip().lower() == retrieved_doc['title'].strip().lower()
                                content_match = cls._check_content_similarity(
                                    gold_doc['content'],
                                    retrieved_doc['content']
                                )
                                if title_match and content_match:
                                    matched_docs.append(gold_doc['title'])
                                    break

                        if len(matched_docs) == 0:
                            zero_count += 1
                        elif len(matched_docs) < len(gold_docs):
                            partial_count += 1
                        else:
                            full_count += 1

                    # 打印累积统计
                    bench_logger.info(f"\n📊 累积召回情况统计 ({current_idx} 个问题):")
                    bench_logger.info("=" * 50)
                    bench_logger.info(f"✅ 全部召回: {full_count} 个 ({full_count/current_idx*100:.1f}%)")
                    bench_logger.info(f"⚠️  部分召回: {partial_count} 个 ({partial_count/current_idx*100:.1f}%)")
                    bench_logger.info(f"❌ 零召回: {zero_count} 个 ({zero_count/current_idx*100:.1f}%)")
                    bench_logger.info("=" * 50)

                    # 🆕 准备 recall 评估数据
                    gold_docs_list_for_recall = []
                    retrieved_docs_list_for_recall = []

                    for i, result in enumerate(results_so_far):
                        gold_docs = current_gold_docs[i]
                        retrieved_docs_for_recall = []

                        # 获取检索结果段落（格式与召回评估一致）
                        for section in result['sections']:
                            heading = section.get('heading', '')
                            content = section.get('content', '')
                            clean_heading = heading.lstrip('#').strip()
                            clean_content = content.strip()
                            if clean_heading and clean_content:
                                retrieved_docs_for_recall.append({
                                    'title': clean_heading,
                                    'content': clean_content
                                })

                        # 为 recall 评估准备数据
                        gold_titles = [doc['title'] for doc in gold_docs]
                        gold_docs_list_for_recall.append(gold_titles)
                        retrieved_docs_list_for_recall.append([doc['title'] for doc in retrieved_docs_for_recall])

                    # 计算 recall@k
                    recall_metric = RetrievalRecall()
                    pooled_recall, _ = recall_metric.calculate_metric_scores(
                        gold_docs=gold_docs_list_for_recall,
                        retrieved_docs=retrieved_docs_list_for_recall,
                        k_list=[1, 2, 5, 10]
                    )

                    bench_logger.info(f"\n累积Recall@K:")
                    for metric, score in pooled_recall.items():
                        bench_logger.info(f"  {metric}: {score:.4f} ({score*100:.2f}%)")

                    # 🆕 上传到 MLflow
                    if enable_mlflow and mlflow_run:
                        import mlflow

                        # 记录统计数量
                        mlflow.log_metrics({
                            "full_recall_count": full_count,
                            "partial_recall_count": partial_count,
                            "zero_recall_count": zero_count,
                            "questions_processed": current_idx
                        }, step=batch_index)

                        # 记录 Recall@K
                        for metric_name, score in pooled_recall.items():
                            k = int(metric_name.split('@')[1])
                            mlflow.log_metric(f"recall_at_{k}", score, step=batch_index)

                # 执行检索
                search_results = await cls.search_questions(
                    source_config_id=source_info['source_config_id'],
                    questions=questions,
                    limit=display_limit,
                    verbose=search_verbose,
                    bench_size=bench_size,
                    callback=bench_callback if bench_size else None
                )

                # 🆕 计算SEARCH阶段耗时
                search_time = time.perf_counter() - search_start

                if gold_docs_for_recall and len(gold_docs_for_recall) == len(search_results):
                    bench_logger.info(f"\n正在进行召回率评估（数据集: {dataset_name}）...")
                    # 准备评估数据
                    gold_docs_list = []
                    retrieved_docs_list = []

                    for i, result in enumerate(search_results):
                        if i < len(gold_docs_for_recall):
                            # 获取标准答案文档
                            gold_docs = gold_docs_for_recall[i]

                            # 获取检索结果段落（清理markdown标记）
                            retrieved_docs = []
                            for section in result['sections']:
                                heading = section.get('heading', '')
                                content = section.get('content', '')
                                # 清理markdown标记（# 前缀）和首尾空格
                                clean_heading = heading.lstrip('#').strip()
                                clean_content = content.strip()
                                if clean_heading and clean_content:
                                    retrieved_docs.append({
                                        'title': clean_heading,
                                        'content': clean_content
                                    })

                            # 进行标题+内容的双重匹配
                            matched_docs = []
                            for gold_doc in gold_docs:
                                for retrieved_doc in retrieved_docs:
                                    title_match = gold_doc['title'].strip().lower() == retrieved_doc['title'].strip().lower()
                                    # 内容匹配：检查检索内容是否包含标准内容的关键信息
                                    content_match = cls._check_content_similarity(
                                        gold_doc['content'],
                                        retrieved_doc['content']
                                    )

                                    if title_match and content_match:
                                        matched_docs.append(gold_doc['title'])
                                        break  # 找到匹配后退出内循环

                            # 为了兼容RetrievalRecall，传递标题列表
                            gold_titles = [doc['title'] for doc in gold_docs]
                            gold_docs_list.append(gold_titles)  # 传递所有标准答案文档（修复bug）
                            retrieved_docs_list.append([doc['title'] for doc in retrieved_docs])

                            # 将匹配结果保存到 search_results，用于后续显示
                            result['matched_docs'] = matched_docs
                            result['gold_titles'] = gold_titles

                            # 调试输出
                            logger.debug(f"\n[DEBUG] 问题 {i+1}:")
                            logger.debug(f"  标准文档: {gold_titles}")
                            logger.debug(f"  检索文档: {[doc['title'] for doc in retrieved_docs[:5]]}...")  # 只显示前5个
                            logger.debug(f"  匹配成功: {matched_docs}")
                            logger.debug(f"  匹配率: {len(matched_docs)}/{len(gold_titles)}")
                    # 使用RetrievalRecall进行评估
                    if gold_docs_list and retrieved_docs_list:
                        recall_metric = RetrievalRecall()

                        pooled_recall, example_recalls = recall_metric.calculate_metric_scores(
                            gold_docs=gold_docs_list,
                            retrieved_docs=retrieved_docs_list,
                            k_list=[1, 2, 5, 10]
                        )
                        
                        recall_evaluation = {
                            'pooled_results': pooled_recall,
                            'example_results': example_recalls,
                            'num_questions': len(gold_docs_list)
                        }
                        
                        bench_logger.info(f"\n召回率评估结果:")
                        bench_logger.info("=" * 50)
                        for metric, score in pooled_recall.items():
                            bench_logger.info(f"{metric}: {score:.4f} ({score*100:.2f}%)")
                        bench_logger.info("=" * 50)

                        # Debug info message to verify execution
                        logger.info("DEBUG: Starting statistics calculation...")

                        # Debug print to verify execution
                        logger.debug(f"DEBUG: About to calculate statistics. gold_docs_for_recall length: {len(gold_docs_for_recall)}")

                        # 🆕 统计各个问题的召回情况
                        logger.info("DEBUG: Starting statistics calculation loop...")
                        total_questions = len(gold_docs_for_recall)
                        full_recall_count = 0  # 全部召回
                        partial_recall_count = 0  # 部分召回
                        zero_recall_count = 0  # 零召回

                        logger.info(f"DEBUG: total_questions={total_questions}, search_results length={len(search_results)}")

                        for i, result in enumerate(search_results):
                            if i < len(gold_docs_for_recall):
                                gold_docs = gold_docs_for_recall[i]
                                matched_docs = result.get('matched_docs', [])

                                if len(matched_docs) == 0:
                                    zero_recall_count += 1

                                elif len(matched_docs) < len(gold_docs):
                                    partial_recall_count += 1
   
                                else:
                                    full_recall_count += 1


                        # 🆕 保存统计结果到 recall_evaluation
                        statistics = {
                            'total_questions': total_questions,
                            'full_recall_count': full_recall_count,
                            'partial_recall_count': partial_recall_count,
                            'zero_recall_count': zero_recall_count
                        }

                        # 🆕 显示统计结果（在详细日志中）
                        logger.info(f"\n📊 问题召回情况统计:")
                        logger.info("=" * 50)
                        logger.info(f"总问题数: {total_questions}")
                        logger.info(f"✅ 全部召回: {full_recall_count} 个 ({full_recall_count/total_questions*100:.1f}%)")
                        logger.info(f"⚠️  部分召回: {partial_recall_count} 个 ({partial_recall_count/total_questions*100:.1f}%)")
                        logger.info(f"❌ 零召回: {zero_recall_count} 个 ({zero_recall_count/total_questions*100:.1f}%)")
                        logger.info("=" * 50)

                        # 🆕 保存 badcase 信息
                        try:
                            # 获取当前模型名称
                            from dataflow.core.config import get_settings
                            settings = get_settings()
                            model_name = settings.llm_model
                            if '/' in model_name:
                                filtered_model_name = model_name.split('/')[-1]
                            else:
                                filtered_model_name = model_name

                            # 从 source_info 获取时间戳
                            timestamp = source_info.get('timestamp', datetime.now().strftime("%Y%m%d_%H%M%S"))

                            # 创建输出目录：SAG/{model_name}/{dataset_name}/{timestamp}
                            output_base_dir = Path(__file__).parent / "outputs" / "SAG" / filtered_model_name / dataset_name / timestamp
                            output_base_dir.mkdir(parents=True, exist_ok=True)

                            # 分类 badcase
                            zero_recall_cases = []  # 完全没有召回
                            partial_recall_cases = []  # 部分召回

                            for i, result in enumerate(search_results):
                                if i < len(gold_docs_for_recall):
                                    gold_docs = gold_docs_for_recall[i]
                                    matched_docs = result.get('matched_docs', [])

                                    # 构建与原数据集格式兼容的结构
                                    # 确保所有数据都是可JSON序列化的基本类型
                                    badcase_data = {
                                        'question_index': i + 1,
                                        'question': str(result['question']) if result['question'] else "",
                                        'answer': str(answers[i]) if i < len(answers) and answers[i] else "",
                                        'gold_docs': [
                                            {
                                                'title': str(doc.get('title', '')),
                                                'content': str(doc.get('content', ''))
                                            }
                                            for doc in gold_docs
                                        ],
                                        'retrieved_docs': [  # 检索到的文档（只包含标题和内容）
                                            {
                                                'title': str(section.get('heading', '')).lstrip('#').strip(),
                                                'content': str(section.get('content', '')),
                                                'cosine_score': float(section.get('original_score', 0.0)),
                                                'pagerank_score': float(section.get('weight') or section.get('pagerank', 0.0))
                                            }
                                            for section in result['sections']
                                        ],
                                        'matched_docs': [str(doc) for doc in matched_docs],  # 成功匹配的文档标题
                                        'recall_status': {
                                            'total_gold': int(len(gold_docs)),
                                            'matched': int(len(matched_docs)),
                                            'ratio': float(len(matched_docs) / len(gold_docs) if gold_docs else 0)
                                        }
                                    }

                                    # 检查召回情况
                                    if len(matched_docs) == 0:
                                        # Zero recall - 完全没有召回
                                        zero_recall_cases.append(badcase_data)
                                    elif len(matched_docs) < len(gold_docs):
                                        # Partial recall - 部分召回
                                        partial_recall_cases.append(badcase_data)

                            # 保存 zero recall cases
                            if zero_recall_cases:
                                zero_output_file = output_base_dir / f"zero_{dataset_name}.json"
                                try:
                                    with open(zero_output_file, 'w', encoding='utf-8') as f:
                                        json.dump(zero_recall_cases, f, ensure_ascii=False, indent=2)
                                    logger.info(f"\n💾 保存 Zero Recall Badcase: {zero_output_file}")
                                    logger.info(f"   共 {len(zero_recall_cases)} 个问题完全没有召回")
                                except Exception as e:
                                    logger.error(f"保存 Zero Recall Badcase 失败: {e}")
                                    logger.error(f"数据内容: {zero_recall_cases[:2] if zero_recall_cases else '空'}")  # 打印前两个样本

                            # 保存 partial recall cases
                            if partial_recall_cases:
                                partial_output_file = output_base_dir / f"partial_{dataset_name}.json"
                                try:
                                    with open(partial_output_file, 'w', encoding='utf-8') as f:
                                        json.dump(partial_recall_cases, f, ensure_ascii=False, indent=2)
                                    logger.info(f"\n💾 保存 Partial Recall Badcase: {partial_output_file}")
                                    logger.info(f"   共 {len(partial_recall_cases)} 个问题部分召回")
                                except Exception as e:
                                    logger.error(f"保存 Partial Recall Badcase 失败: {e}")
                                    logger.error(f"数据内容: {partial_recall_cases[:2] if partial_recall_cases else '空'}")  # 打印前两个样本

                        except Exception as e:
                            logger.warning(f"保存 badcase 失败: {e}")
                            import traceback
                            logger.warning(f"详细错误信息: {traceback.format_exc()}")
                
                # 显示检索结果
                logger.info(f"\n检索结果概要:")
                logger.info("=" * 80)
                
                total_successful = sum(1 for r in search_results if r['search_success'])
                total_sections = sum(r['total_sections'] for r in search_results)
                
                logger.info(f"成功检索: {total_successful}/{len(search_results)} 个问题")
                logger.info(f"总检索段落数: {total_sections} 个")
                
                # 显示每个问题的检索结果
                for result in search_results:
                    logger.info(f"\n[问题 {result['question_index']}] {result['question']}")

                    if result['search_success']:
                        sections = result['sections']
                        matched_docs = result.get('matched_docs', [])

                        logger.info(f"检索到 {len(sections)} 个相关段落:")

                        for j, section in enumerate(sections[:5], 1):  # 只显示前5个
                            heading = section.get('heading', 'N/A')
                            content = section.get('content', '').replace('\n', ' ')

                            # 获取得分信息
                            cosine_score = section.get('original_score', 0.0)
                            pagerank_score = section.get('weight') or section.get('pagerank', 0.0)

                            # 检查是否是正确答案
                            is_correct = heading.lstrip('#').strip() in matched_docs

                            logger.info(f"   [{j}] 标题: {heading} {'✅' if is_correct else ''}")
                            logger.info(f"       余弦相似度: {cosine_score:.4f} | PageRank: {pagerank_score:.4f}")
                            logger.info(f"       内容: {content[:200]}..." if len(content) > 200 else f"       内容: {content}")

                        if len(sections) > 5:
                            logger.info(f"   ... 还有 {len(sections) - 5} 个段落")

                        # 显示正确答案统计
                        total_matches = len(matched_docs) if matched_docs else 0
                        logger.info(f"\n   正确答案匹配: {total_matches} 个")
                    else:
                        error_msg = result.get('error', '未知错误')
                        logger.info(f"检索失败: {error_msg}")

                    if result != search_results[-1]:  # 不是最后一个
                        logger.info("-" * 60)
                
                logger.info("\n" + "=" * 80)

                # 🆕 QA 评估（如果启用）
                qa_evaluation = None
                if enable_qa:
                    # 检查是否在 badcase 模式下（badcase 不需要进行 QA 评估）
                    if badcase:
                        logger.warning(f"⚠️  Badcase 模式下不支持 QA 评估，已自动禁用")
                        logger.warning(f"   Badcase 主要用于分析和优化检索性能")
                    else:
                        logger.info(f"\n正在进行 QA 评估...")
                        logger.info("=" * 80)

                        # 准备 QA 评估数据
                        gold_answers_list = []
                        predicted_answers_list = []

                        # 检查数据集对应的提示词文件是否存在
                        qa_prompt_path = f"prompts/benchmark/{dataset_name}.yaml"
                        import os
                        if not os.path.exists(qa_prompt_path):
                            # 如果数据集特定提示词不存在，使用默认的 musique 提示词
                            qa_prompt_path = "prompts/benchmark/musique.yaml"
                            logger.info(f"数据集 {dataset_name} 的提示词不存在，使用默认提示词: {qa_prompt_path}")
                        else:
                            logger.info(f"加载 QA 提示词: {qa_prompt_path}")

                        # 初始化 QA 生成器（使用类级别缓存，避免重复创建）
                        llm_client = cls._llm_client
                        prompt_manager = cls._prompt_manager

                        # 🆕 QA阶段总耗时
                        qa_time = 0.0

                        # 如果缓存为空，则创建 LLM 客户端和 PromptManager
                        if llm_client is None:
                            logger.info("首次使用，创建 LLM 客户端（后续将复用）...")
                            llm_client = await create_llm_client(scenario='search')
                            prompt_manager = PromptManager()

                            # 保存到类级别缓存
                            cls._llm_client = llm_client
                            cls._prompt_manager = prompt_manager
                        else:
                            logger.info("复用已存在的 LLM 客户端（避免重复创建）")

                        # 🆕 开始QA计时
                        qa_start = time.perf_counter()

                        for i, result in enumerate(search_results):
                            if i >= len(answers):
                                break

                            question = result['question']
                            sections = result['sections']

                            # 获取标准答案
                            gold_ans = answers[i]
                            if isinstance(gold_ans, str):
                                gold_ans = [gold_ans]
                            gold_answers_list.append(gold_ans)

                            # 生成预测答案（使用 LLM）
                            if sections:
                                # 格式化文档
                                documents = ""
                                for section in sections[:5]:  # 使用前5个段落
                                    heading = section.get('heading', '').lstrip('#').strip()
                                    content = section.get('content', '').strip()
                                    if heading and content:
                                        documents += f"Wikipedia Title: {heading}\n{content}\n\n"

                                try:
                                    # 使用 prompt_manager.render() 渲染提示词
                                    prompt_text = prompt_manager.render(
                                        "rag_qa_musique",  # 模板名称
                                        document_title="",
                                        document_content=documents,
                                        question=question
                                    )

                                    # 调用 LLM 生成答案
                                    from dataflow.core.ai.models import LLMMessage, LLMRole
                                    response = await llm_client.chat(
                                        messages=[
                                            LLMMessage(role=LLMRole.USER, content=prompt_text)
                                        ],
                                        max_tokens=200,
                                        temperature=0.1
                                    )

                                    # 提取答案
                                    response_text = response.content
                                    predicted_answer = response_text.split("Answer:")[-1].strip() if "Answer:" in response_text else response_text.strip()
                                    logger.debug(f"问题 {i+1} - LLM 生成答案: {predicted_answer[:50]}...")

                                except Exception as e:
                                    logger.warning(f"LLM 生成答案失败 (问题 {i+1}): {e}")
                                    predicted_answer = ""
                            else:
                                predicted_answer = ""

                            predicted_answers_list.append(predicted_answer)

                        # 🆕 计算QA阶段总耗时（在QA循环结束后立即计算）
                        qa_time = time.perf_counter() - qa_start

                        # 使用现有的 QA 评估指标
                        from dataflow.evaluation.metrics import QAExactMatch, QAF1Score

                        qa_em_metric = QAExactMatch()
                        qa_f1_metric = QAF1Score()

                        # 计算 Exact Match
                        em_pooled, em_examples = qa_em_metric.calculate_metric_scores(
                            gold_answers=gold_answers_list,
                            predicted_answers=predicted_answers_list
                        )

                        # 计算 F1 Score
                        f1_pooled, f1_examples = qa_f1_metric.calculate_metric_scores(
                            gold_answers=gold_answers_list,
                            predicted_answers=predicted_answers_list
                        )

                        # 合并结果
                        qa_pooled_results = {**em_pooled, **f1_pooled}
                        qa_example_results = []
                        for em_ex, f1_ex in zip(em_examples, f1_examples):
                            qa_example_results.append({**em_ex, **f1_ex})

                        qa_evaluation = {
                            'pooled_results': qa_pooled_results,
                            'example_results': qa_example_results,
                            'num_questions': len(gold_answers_list)
                        }

                        # 显示 QA 评估结果
                        logger.info(f"\nQA评估结果:")
                        logger.info("=" * 50)
                        for metric, score in qa_pooled_results.items():
                            logger.info(f"{metric}: {score:.4f} ({score*100:.2f}%)")
                        logger.info("=" * 50)

                        # 显示每个问题的 QA 结果
                        logger.info(f"\n每个问题的 QA 评估:")
                        for i, (question, result) in enumerate(zip(questions[:display_limit], search_results)):
                            if i >= len(qa_example_results):
                                break
                            qa_result = qa_example_results[i]
                            logger.info(f"\n[问题 {i+1}] {question}")
                            logger.info(f"  预测答案: {predicted_answers_list[i]}")
                            logger.info(f"  标准答案: {', '.join(gold_answers_list[i])}")
                            logger.info(f"  EM: {qa_result['ExactMatch']:.2f} | F1: {qa_result['F1']:.2f}")


                # 🆕 显示 LLM Token 消耗统计
                if (enable_search or enable_qa) and 'token_tracker' in locals():
                    token_summary = token_tracker.get_summary()
                    if token_summary['total_tokens'] > 0:
                        logger.info("\n" + "=" * 80)
                        logger.info("LLM Token 消耗统计")
                        logger.info("=" * 80)

                        # 按阶段显示（与LOAD/EXTRACT保持一致）
                        if token_summary.get('stages'):
                            for stage, stats in token_summary['stages'].items():
                                logger.info(f"\n{stage}:")
                                logger.info(f"  调用次数: {stats['calls']}")
                                logger.info(f"  输入 Tokens: {stats['prompt']:,}")
                                logger.info(f"  输出 Tokens: {stats['completion']:,}")
                                logger.info(f"  总计 Tokens: {stats['total']:,}")
                        logger.info("\n" + "=" * 80 + "\n")

                # 显示检索评估结果
                if recall_evaluation:
                    logger.info(f"检索统计:")
                    logger.info(f"  问题数: {recall_evaluation['num_questions']}")
                    for metric, score in recall_evaluation['pooled_results'].items():
                        logger.info(f"  {metric}: {score:.4f} ({score*100:.2f}%)")

                # 显示QA评估结果
                if qa_evaluation:
                    logger.info(f"QA统计:")
                    logger.info(f"  问题数: {qa_evaluation['num_questions']}")
                    for metric, score in qa_evaluation['pooled_results'].items():
                        logger.info(f"  {metric}: {score:.4f} ({score*100:.2f}%)")

            except Exception as e:
                logger.error(f"检索过程出现错误: {e}")
                import traceback
                traceback.print_exc()

            # 6. 返回完整信息
            # 准备返回值
            result = {
                'source_info': source_info,
                'dataset_info': dataset_info,
                'display_limit': display_limit,
                'show_paragraphs': show_paragraphs,
                'enable_search': enable_search,
                'search_results': search_results,
                'recall_evaluation': recall_evaluation,
                'qa_evaluation': qa_evaluation if enable_qa else None,
                'llm_token_usage': token_tracker.get_summary() if (enable_search or enable_qa) and 'token_tracker' in locals() else None,
                'stage_times': {  # 🆕 添加各阶段耗时
                    'search': search_time
                }
            }

            # 只有在非 badcase 模式下才添加 qa 时间
            if enable_qa and not badcase:
                result['stage_times']['qa'] = qa_time

            # 添加召回统计信息（如果有）
            if 'statistics' in locals():
                result['recall_statistics'] = statistics

            # 🆕 关闭 MLflow 运行
            if enable_mlflow and mlflow_run:
                import mlflow
                mlflow.end_run()
                logger.info("✅ MLflow 运行已结束")

            return result

    @classmethod
    def evaluate(cls,
                 dataset_name: str,
                 load_and_generate_md: bool = False,
                 chunks_per_file: int = 500,
                 force_regenerate: bool = False) -> Dict[str, Any]:
        """
        类方法：中心评估函数

        Args:
            dataset_name: 数据集名称
            load_and_generate_md: 是否加载数据集并生成 markdown 文件
            chunks_per_file: 每个 markdown 文件包含的 chunk 数量
            force_regenerate: 是否强制重新生成 markdown 文件

        Returns:
            评估结果字典
        """
        logger.info(f"Starting evaluation for dataset: {dataset_name}")

        results = {
            'dataset': dataset_name,
            'timestamp': datetime.now().isoformat(),
        }

        # 加载数据集
        loader = DatasetLoader(dataset_name)

        # 生成 markdown 文件
        if load_and_generate_md:
            logger.info(f"Loading dataset and generating markdown files...")
            load_start = time.perf_counter()  # 🆕 开始LOAD计时
            save_result = loader.save_as_markdown(
                chunks_per_file=chunks_per_file,
                force_regenerate=force_regenerate
            )
            load_time = time.perf_counter() - load_start  # 🆕 计算LOAD耗时

            results['markdown_generation'] = {
                'output_dir': str(save_result['output_dir']),
                'stats': save_result['stats'],
                'chunks_per_file': chunks_per_file,
                'status': 'completed',
                'load_time': load_time  # 🆕 添加LOAD耗时
            }

            logger.info(f"Markdown files generated successfully at: {save_result['output_dir']}")

        # TODO: 后续可以在这里添加更多评估功能
        # - 检索评估
        # - QA 评估
        # - 等等

        return results

    def load_dataset(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        加载数据集

        Args:
            force_reload: 是否强制重新加载

        Returns:
            包含数据集信息的字典
        """
        if self.dataset_loader is None or force_reload:
            logger.info(f"Loading dataset: {self.config.dataset_name}")

            self.dataset_loader = DatasetLoader(
                dataset_name=self.config.dataset_name,
                dataset_dir=self.config.dataset_dir
            )

            # 加载数据
            self.docs = self.dataset_loader.get_docs(force_reload)
            self.questions = self.dataset_loader.get_questions(force_reload)
            self.gold_answers = self.dataset_loader.get_gold_answers(force_reload)
            self.gold_docs = self.dataset_loader.get_gold_docs(force_reload)

            # 采样（如果配置了）
            if self.config.max_samples is not None:
                logger.info(f"Sampling {self.config.max_samples} samples for quick testing")
                self.questions = self.questions[:self.config.max_samples]
                self.gold_answers = self.gold_answers[:self.config.max_samples]
                if self.gold_docs is not None:
                    self.gold_docs = self.gold_docs[:self.config.max_samples]

            # 获取统计信息
            stats = self.dataset_loader.get_stats()

            if self.config.max_samples is not None:
                stats['sampled'] = True
                stats['num_sampled_questions'] = len(self.questions)

            logger.info(f"Dataset loaded successfully: {stats}")

            return {
                'dataset_name': self.config.dataset_name,
                'num_docs': len(self.docs),
                'num_questions': len(self.questions),
                'num_gold_answers': len(self.gold_answers),
                'has_gold_docs': self.gold_docs is not None,
                'stats': stats
            }

        return {
            'dataset_name': self.config.dataset_name,
            'num_docs': len(self.docs) if self.docs else 0,
            'num_questions': len(self.questions) if self.questions else 0,
        }

    def evaluate_retrieval(
        self,
        retrieved_docs_list: List[List[str]],
        top_k_list: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        评估检索性能

        Args:
            retrieved_docs_list: 每个问题的检索结果列表
            top_k_list: 要评估的top-k列表，如果为None则使用配置中的值

        Returns:
            评估结果字典
        """
        if not self.config.evaluate_retrieval:
            logger.warning("Retrieval evaluation is disabled in config")
            return {}

        if self.gold_docs is None:
            logger.warning("Gold docs not available, skipping retrieval evaluation")
            return {}

        if len(retrieved_docs_list) != len(self.gold_docs):
            raise ValueError(
                f"Length mismatch: retrieved_docs_list ({len(retrieved_docs_list)}) "
                f"vs gold_docs ({len(self.gold_docs)})"
            )

        top_k_list = top_k_list or self.config.retrieval_top_k_list

        logger.info(f"Evaluating retrieval with top_k_list: {top_k_list}")

        start_time = time.time()

        # 计算 Recall@k
        pooled_results, example_results = self.retrieval_recall_metric.calculate_metric_scores(
            gold_docs=self.gold_docs,
            retrieved_docs=retrieved_docs_list,
            k_list=top_k_list
        )

        elapsed_time = time.time() - start_time

        logger.info(f"Retrieval evaluation completed in {elapsed_time:.2f}s")
        logger.info(f"Pooled results: {pooled_results}")

        return {
            'pooled': pooled_results,
            'examples': example_results,
            'metrics': ['Recall@k'],
            'top_k_list': top_k_list,
            'num_examples': len(example_results),
            'elapsed_time': elapsed_time
        }

    def evaluate_qa(
        self,
        predicted_answers: List[str],
        aggregation_fn: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        评估QA性能

        Args:
            predicted_answers: 预测的答案列表
            aggregation_fn: 聚合函数（用于多个gold答案的情况），默认使用max

        Returns:
            评估结果字典
        """
        if not self.config.evaluate_qa:
            logger.warning("QA evaluation is disabled in config")
            return {}

        if len(predicted_answers) != len(self.gold_answers):
            raise ValueError(
                f"Length mismatch: predicted_answers ({len(predicted_answers)}) "
                f"vs gold_answers ({len(self.gold_answers)})"
            )

        logger.info(f"Evaluating QA performance on {len(predicted_answers)} examples")

        import numpy as np
        aggregation_fn = aggregation_fn or (
            np.max if self.config.qa_aggregation == "max" else np.mean
        )

        # 将 Set[str] 转换为 List[List[str]]
        gold_answers_list = [list(ans_set) for ans_set in self.gold_answers]

        start_time = time.time()

        # 计算 Exact Match
        em_pooled, em_examples = self.qa_em_metric.calculate_metric_scores(
            gold_answers=gold_answers_list,
            predicted_answers=predicted_answers,
            aggregation_fn=aggregation_fn
        )

        # 计算 F1 Score
        f1_pooled, f1_examples = self.qa_f1_metric.calculate_metric_scores(
            gold_answers=gold_answers_list,
            predicted_answers=predicted_answers,
            aggregation_fn=aggregation_fn
        )

        elapsed_time = time.time() - start_time

        # 合并结果
        pooled_results = {**em_pooled, **f1_pooled}

        # 合并每个样本的结果
        example_results = []
        for em_ex, f1_ex in zip(em_examples, f1_examples):
            example_results.append({**em_ex, **f1_ex})

        logger.info(f"QA evaluation completed in {elapsed_time:.2f}s")
        logger.info(f"Pooled results: {pooled_results}")

        return {
            'pooled': pooled_results,
            'examples': example_results,
            'metrics': ['ExactMatch', 'F1'],
            'aggregation': self.config.qa_aggregation,
            'num_examples': len(example_results),
            'elapsed_time': elapsed_time
        }

    def evaluate_all(
        self,
        retrieved_docs_list: Optional[List[List[str]]] = None,
        predicted_answers: Optional[List[str]] = None,
        top_k_list: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        运行完整的评估流程

        Args:
            retrieved_docs_list: 检索结果列表（用于retrieval评估）
            predicted_answers: 预测答案列表（用于QA评估）
            top_k_list: Recall@k中的k值列表

        Returns:
            完整的评估结果
        """
        logger.info("=" * 60)
        logger.info("Starting comprehensive evaluation")
        logger.info("=" * 60)

        # 确保数据集已加载
        if self.docs is None:
            self.load_dataset()

        results = {
            'dataset': self.config.dataset_name,
            'timestamp': datetime.now().isoformat(),
            'config': asdict(self.config),
            'num_questions': len(self.questions),
        }

        # 检索评估
        if retrieved_docs_list is not None and self.config.evaluate_retrieval:
            logger.info("\n--- Retrieval Evaluation ---")
            retrieval_results = self.evaluate_retrieval(
                retrieved_docs_list=retrieved_docs_list,
                top_k_list=top_k_list
            )
            results['retrieval'] = retrieval_results

        # QA评估
        if predicted_answers is not None and self.config.evaluate_qa:
            logger.info("\n--- QA Evaluation ---")
            qa_results = self.evaluate_qa(predicted_answers=predicted_answers)
            results['qa'] = qa_results

        # 保存结果
        if self.config.save_results:
            self.save_results(results)

        logger.info("=" * 60)
        logger.info("Evaluation completed")
        logger.info("=" * 60)

        return results

    def save_results(self, results: Dict[str, Any], filename: Optional[str] = None):
        """
        保存评估结果

        Args:
            results: 评估结果字典
            filename: 输出文件名，如果为None则自动生成
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"eval_{self.config.dataset_name}_{timestamp}.json"

        output_path = self.output_dir / filename

        logger.info(f"Saving results to {output_path}")

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved successfully")

        # 同时保存一个最新结果的软链接
        latest_path = self.output_dir / f"eval_{self.config.dataset_name}_latest.json"
        with open(latest_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return output_path

    def get_questions(self) -> List[str]:
        """获取问题列表"""
        if self.questions is None:
            self.load_dataset()
        return self.questions

    def get_docs(self) -> List[str]:
        """获取文档列表"""
        if self.docs is None:
            self.load_dataset()
        return self.docs

    def get_gold_answers(self) -> List[Set[str]]:
        """获取标准答案列表"""
        if self.gold_answers is None:
            self.load_dataset()
        return self.gold_answers

    def get_gold_docs(self) -> Optional[List[List[str]]]:
        """获取标准文档列表"""
        if self.gold_docs is None and self.docs is None:
            self.load_dataset()
        return self.gold_docs

    async def upload_corpus(
        self,
        enable_extraction: bool = True,
        source_name: Optional[str] = None,
        source_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        上传数据集的 markdown 文件到系统

        Args:
            enable_extraction: 是否执行提取阶段（False 则只加载文档）
            source_name: 信息源名称，默认为 "{dataset_name} Corpus"
            source_description: 信息源描述

        Returns:
            处理结果字典，包含 source_config_id, article_ids, 统计信息等
        """
        logger.info("=" * 60)
        logger.info("开始上传 corpus 到系统")
        logger.info("=" * 60)

        # 获取当前模型名称
        try:
            # 创建 LLM 客户端来获取模型配置
            llm_client = await create_llm_client(scenario='extract')
            model_name = llm_client.client.config.model if hasattr(llm_client, 'client') else llm_client.config.model

            # 过滤模型名称，只保留最后一层（例如：Qwen/qwen3 -> qwen3）
            if '/' in model_name:
                filtered_model_name = model_name.split('/')[-1]
            else:
                filtered_model_name = model_name

            logger.info(f"当前使用模型: {model_name} -> 过滤后: {filtered_model_name}")
        except Exception as e:
            logger.warning(f"获取模型名称失败: {e}，使用默认模型名称 'default'")
            filtered_model_name = "default"

        # 检查 markdown 文件目录是否存在
        md_dir = Path(__file__).parent / "markdown_datasets" / self.config.dataset_name
        if not md_dir.exists():
            error_msg = f"错误：markdown 目录不存在: {md_dir}"
            logger.error(error_msg)
            return {'status': 'error', 'message': error_msg}

        # 获取所有 md 文件
        md_files = sorted(md_dir.glob("*.md"))
        if not md_files:
            error_msg = f"错误：在 {md_dir} 中未找到 .md 文件"
            logger.error(error_msg)
            return {'status': 'error', 'message': error_msg}

        logger.info(f"找到 {len(md_files)} 个 markdown 文件")

        # 1. 生成信息源 ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        source_config_id = f"{self.config.dataset_name}-{timestamp}"

        # 设置默认名称和描述
        if source_name is None:
            source_name = f"{self.config.dataset_name}-{timestamp}"  # 使用数据集名称+时间戳
        if source_description is None:
            source_description = f"Evaluation corpus for {self.config.dataset_name} dataset"

        logger.info(f"信息源 ID: {source_config_id}")
        logger.info(f"信息源名称: {source_name}")
        logger.info(f"描述: {source_description}\n")

        # 2. 创建 TaskConfig（用于传递 source_name）
        task_config = TaskConfig(
            task_name=f"Upload {self.config.dataset_name} Corpus",
            source_config_id=source_config_id,
            source_name=source_name
        )

        # 3. 创建 DataFlowEngine
        engine = DataFlowEngine(task_config=task_config)

        # 4. 初始化统计
        file_results = []
        total_sections = 0
        total_events = 0
        total_time_load = 0.0
        total_time_extract = 0.0
        total_files_processed = 0

        # Token追踪器（用于记录所有LLM调用的token消耗）
        token_tracker = LLMTokenTracker()

        # 启用LLM调用追踪（使用monkey patch自动拦截所有LLM调用）
        if enable_extraction:
            enable_llm_tracking(token_tracker)
            logger.info("✅ LLM调用追踪已启用，将自动统计token消耗")

        # 用于记录每个文档的LLM Token统计
        file_token_stats = []

        for idx, md_file in enumerate(md_files, 1):
            logger.info(f"[{idx}/{len(md_files)}] 处理文件: {md_file.name}")
            file_size_mb = md_file.stat().st_size / 1024 / 1024
            logger.info(f"  文件大小: {file_size_mb:.2f} MB")

            # Load 阶段 - 加载文档
            load_start = time.perf_counter()
            try:
                await engine.load_async(
                    DocumentLoadConfig(
                        path=str(md_file),
                        recursive=False,
                        source_config_id=source_config_id
                    )
                )
                load_time = time.perf_counter() - load_start
                total_time_load += load_time
                logger.info(f"  ✓ 文档加载完成，耗时: {load_time:.1f} 秒")
            except Exception as e:
                error_msg = f"文档加载失败 ({md_file.name}): {e}"
                logger.error(error_msg, exc_info=True)
                file_results.append({
                    'file': md_file.name,
                    'status': 'error',
                    'message': str(e)
                })
                continue

            # 获取 Load 结果
            engine_result = engine.get_result()
            if not engine_result or not engine_result.load_result:
                error_msg = f"Load 阶段失败：无法获取加载结果 ({md_file.name})"
                logger.error(error_msg)
                file_results.append({
                    'file': md_file.name,
                    'status': 'error',
                    'message': error_msg
                })
                continue

            # 从 engine_result 获取数据
            try:
                article_id = engine_result.article_id
                load_result = engine_result.load_result
                sections_count = load_result.stats.get("chunk_count", 0) if load_result.stats else 0
                total_sections += sections_count

                logger.info(f"  Article ID: {article_id}")
                logger.info(f"  文档片段数: {sections_count}")
            except Exception as e:
                error_msg = f"读取 Load 结果失败 ({md_file.name}): {e}"
                logger.error(error_msg, exc_info=True)
                file_results.append({
                    'file': md_file.name,
                    'status': 'error',
                    'message': str(e)
                })
                continue

            events_count = 0

            # Extract 阶段 - 提取事项（可选）
            if enable_extraction:
                logger.info(f"  开始提取事项...")
                extract_start = time.perf_counter()

                try:
                    await engine.extract_async(
                        ExtractBaseConfig(
                            parallel=True,
                            max_concurrency=50
                        )
                    )
                    extract_time = time.perf_counter() - extract_start
                    total_time_extract += extract_time
                    logger.info(f"  ✓ 事项提取完成，耗时: {extract_time:.1f} 秒")

                    # 获取 Extract 结果
                    engine_result = engine.get_result()
                    if engine_result and engine_result.extract_result:
                        extract_result = engine_result.extract_result
                        events_count = len(extract_result.data_ids) if extract_result.data_ids else 0
                        total_events += events_count
                        logger.info(f"  生成事项数: {events_count}")
                    else:
                        logger.warning(f"  ⚠️  Extract 结果为空")
                except Exception as e:
                    error_msg = f"事项提取失败 ({md_file.name}): {e}"
                    logger.error(error_msg, exc_info=True)
                    # 提取失败不返回错误，因为 Load 已经成功
            else:
                logger.info(f"  跳过提取阶段（enable_extraction=False）")

            # 记录文件处理结果
            file_results.append({
                'file': md_file.name,
                'article_id': article_id,
                'sections_count': sections_count,
                'events_count': events_count,
                'status': 'completed'
            })

            # 如果是提取模式，记录该文件的token统计
            if enable_extraction:
                # 计算本文件处理期间的token增量
                current_stats = token_tracker.get_summary()

                # 获取该文件处理的token（简单的累加方式）
                # 更精确的方式需要按文件隔离统计，这里使用简化的累加方式
                # 因为我们的追踪器是全局的，所以这里只是记录当前总数
                file_tokens = {
                    'file': md_file.name,
                    'prompt_tokens': current_stats['total_prompt'],
                    'completion_tokens': current_stats['total_completion'],
                    'total_tokens': current_stats['total_tokens'],
                    'processing_time': {
                        'load_time': round(load_time, 1),
                        'extract_time': round(extract_time, 1) if 'extract_time' in locals() else 0
                    }
                }
                file_token_stats.append(file_tokens)

                # 显示本文件的token统计（显示增量）
                if len(file_token_stats) > 1:
                    # 计算增量（相对于上一个文件）
                    prev_file = file_token_stats[-2]
                    delta_prompt = file_tokens['prompt_tokens'] - prev_file['prompt_tokens']
                    delta_completion = file_tokens['completion_tokens'] - prev_file['completion_tokens']
                    delta_total = file_tokens['total_tokens'] - prev_file['total_tokens']
                else:
                    # 第一个文件，直接显示总数
                    delta_prompt = file_tokens['prompt_tokens']
                    delta_completion = file_tokens['completion_tokens']
                    delta_total = file_tokens['total_tokens']

                # 仅在有token消耗时显示
                if delta_total > 0:
                    logger.info(f"  📊 LLM Tokens: 输入={delta_prompt:,}, 输出={delta_completion:,}, 总计={delta_total:,}")

            total_files_processed += 1
            logger.info(f"  ✓ 文件处理完成\n")

        # 5. 保存结果到 dataflow/evaluation/source/SAG/{filtered_model_name}/{dataset_name}/{timestamp}/
        source_dir = Path(__file__).parent / "source" / "SAG" / filtered_model_name / self.config.dataset_name / timestamp
        source_dir.mkdir(parents=True, exist_ok=True)

        # 获取token统计
        token_summary = token_tracker.get_summary()

        result = {
            "source_config_id": source_config_id,
            "source_name": source_name,
            "source_description": source_description,
            "dataset_name": self.config.dataset_name,
            "model_name": model_name,  # 添加原始模型名称
            "filtered_model_name": filtered_model_name,  # 添加过滤后的模型名称
            "file_count": len(md_files),
            "successful_files": total_files_processed,
            "failed_files": len([r for r in file_results if r['status'] == 'error']),
            "total_sections_count": total_sections,
            "total_events_count": total_events,
            "processing_time": {
                "total_load_time": round(total_time_load, 1),
                "total_extract_time": round(total_time_extract, 1),
                "total_time": round(total_time_load + total_time_extract, 1)
            },
            "file_results": file_results,
            "timestamp": timestamp,
            "status": "completed",
            "extraction_enabled": enable_extraction,
            "llm_token_usage": token_summary,  # 添加LLM token使用统计
            "file_token_stats": file_token_stats  # 每个文件的token统计
        }

        # 保存到 source_info.json
        source_info_path = source_dir / "source_info.json"
        with open(source_info_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 信息源结果已保存: {source_info_path}")

        # 返回结果
        logger.info("=" * 60)
        logger.info("✅ Corpus 上传完成")
        logger.info(f"  总文件数: {len(md_files)}")
        logger.info(f"  成功: {result['successful_files']}")
        logger.info(f"  失败: {result['failed_files']}")
        logger.info(f"  总片段数: {total_sections}")
        logger.info(f"  总事项数: {total_events}")
        logger.info(f"  结果保存位置: dataflow/evaluation/source/SAG/{filtered_model_name}/{self.config.dataset_name}/{timestamp}/")
        logger.info("=" * 60)

        # 主动关闭数据库连接和AI客户端，避免 "Event loop is closed" 警告
        try:
            logger.info("关闭数据库连接和AI客户端...")
            # 关闭数据库连接
            await close_database()

            logger.info("✓ 所有连接已关闭")
        except Exception as e:
            logger.warning(f"关闭连接时出现警告: {e}")

        return result

    def print_summary(self, results: Dict[str, Any]):
        """
        打印评估结果摘要

        Args:
            results: 评估结果字典
        """
        logger.info("\n" + "=" * 60)
        logger.info(f"Evaluation Summary - {results['dataset']}")
        logger.info("=" * 60)
        logger.info(f"Timestamp: {results['timestamp']}")
        logger.info(f"Num Questions: {results['num_questions']}")

        if 'retrieval' in results:
            logger.info("\n--- Retrieval Results ---")
            pooled = results['retrieval']['pooled']
            for metric, score in pooled.items():
                logger.info(f"{metric}: {score:.4f}")

        if 'qa' in results:
            logger.info("\n--- QA Results ---")
            pooled = results['qa']['pooled']
            for metric, score in pooled.items():
                logger.info(f"{metric}: {score:.4f}")

        logger.info("=" * 60 + "\n")


# 便捷函数
def quick_evaluate(
    dataset_name: str,
    retrieved_docs_list: Optional[List[List[str]]] = None,
    predicted_answers: Optional[List[str]] = None,
    max_samples: Optional[int] = None,
    output_dir: str = "outputs/evaluation"
) -> Dict[str, Any]:
    """
    快速评估函数

    Args:
        dataset_name: 数据集名称
        retrieved_docs_list: 检索结果列表
        predicted_answers: 预测答案列表
        max_samples: 最大样本数（用于快速测试）
        output_dir: 输出目录

    Returns:
        评估结果
    """
    config = EvaluationConfig(
        dataset_name=dataset_name,
        max_samples=max_samples,
        output_dir=output_dir
    )

    evaluator = Evaluate(config)
    results = evaluator.evaluate_all(
        retrieved_docs_list=retrieved_docs_list,
        predicted_answers=predicted_answers
    )

    evaluator.print_summary(results)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluation benchmark for multi-hop QA datasets"
    )

    parser.add_argument(
        "--dataset",
        type=str,
        default="musique",
        choices=["musique", "hotpotqa", "2wikimultihopqa", "sample", "test_hotpotqa"],
        help="Dataset name to evaluate (default: musique)"
    )

    parser.add_argument(
        "--load",
        action="store_true",
        help="Load dataset and generate markdown files"
    )

    parser.add_argument(
        "--chunks-per-file",
        type=int,
        default=500,
        help="Number of chunks per markdown file (default: 500)"
    )


    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload markdown files to system (creates source in dataflow/evaluation/source/SAG/)"
    )

    parser.add_argument(
        "--show-retrieval-info",
        action="store_true",
        help="Show latest source_config_id, dataset info and retrieval information"
    )

    parser.add_argument(
        "--foundation",
        type=str,
        choices=["upload", "search", "badcase_zero", "badcase_partial"],
        help="Foundation mode: 'upload' to load and upload corpus, 'search' to perform retrieval, 'badcase_zero' or 'badcase_partial' to test badcases"
    )

    parser.add_argument(
        "--info-limit",
        type=int,
        default=None,
        help="Limit number of questions to display in --show-retrieval-info (default: show all)"
    )

    parser.add_argument(
        "--badcase",
        type=str,
        choices=["zero", "partial"],
        default=None,
        help="重测特定的 badcase 类型。从已保存的结果中加载 badcase 文件并只测试这些问题。选项：'zero'（零召回），'partial'（部分召回）。使用最新的时间戳。"
    )

    parser.add_argument(
        "--enable-search",
        action="store_true",
        help="Enable actual search functionality in --show-retrieval-info"
    )

    parser.add_argument(
        "--enable-qa",
        action="store_true",
        help="Enable QA evaluation after retrieval (requires --enable-search)"
    )

    parser.add_argument(
        "--search-verbose",
        action="store_true",
        help="Show detailed search process logs"
    )

    parser.add_argument(
        "--no-paragraphs",
        action="store_true",
        help="Hide paragraph details in --show-retrieval-info"
    )

    parser.add_argument(
        "--bench-size",
        type=int,
        default=None,
        help="Print cumulative statistics every N questions during search (default: None, print only at the end)"
    )

    parser.add_argument(
        "--enable-mlflow",
        action="store_true",
        help="Enable MLflow monitoring for recall metrics"
    )

    parser.add_argument(
        "--mlflow-uri",
        type=str,
        default="http://192.168.110.10:5050",
        help="MLflow tracking URI (default: http://192.168.110.10:5050)"
    )

    parser.add_argument(
        "--mlflow-experiment",
        type=str,
        default="benchmark_retrieval",
        help="MLflow experiment name (default: benchmark_retrieval)"
    )

    args = parser.parse_args()

    # 🆕 根据 foundation 模式自动设置参数
    if args.foundation:
        logger.info(f"🎯 Foundation 模式: {args.foundation}")

        if args.foundation == "upload":
            # Upload 模式: 自动设置 load 和 upload
            args.load = True
            args.upload = True
            args.chunks_per_file = 500  # 使用默认值
            logger.info("  自动启用: --load --upload")

        elif args.foundation == "search":
            # Search 模式: 自动设置 --show-retrieval-info 和 --enable-search
            args.show_retrieval_info = True
            args.enable_search = True
            logger.info("  自动启用: --show-retrieval-info --enable-search")

        elif args.foundation == "badcase_zero":
            # Badcase Zero 模式: 自动设置 search + badcase
            args.show_retrieval_info = True
            args.enable_search = True
            args.badcase = "zero"
            logger.info("  自动启用: --show-retrieval-info --enable-search --badcase zero")

        elif args.foundation == "badcase_partial":
            # Badcase Partial 模式: 自动设置 search + badcase
            args.show_retrieval_info = True
            args.enable_search = True
            args.badcase = "partial"
            logger.info("  自动启用: --show-retrieval-info --enable-search --badcase partial")

    # 如果指定了 --show-retrieval-info，显示检索信息并退出
    if args.show_retrieval_info:
        try:
            # 检查参数有效性
            if args.enable_qa and not args.enable_search:
                logger.error("错误: --enable-qa 需要与 --enable-search 一起使用")
                sys.exit(1)

            # 使用 asyncio.run 运行异步函数
            # 添加 badcase 支持
            badcase = getattr(args, 'badcase', None)

            retrieval_info = asyncio.run(Evaluate.show_retrieval_info(
                limit=args.info_limit,
                show_paragraphs=not args.no_paragraphs,
                enable_search=args.enable_search,
                search_verbose=args.search_verbose,
                enable_qa=args.enable_qa,
                dataset_name=args.dataset,
                badcase=badcase,
                bench_size=args.bench_size,
                enable_mlflow=args.enable_mlflow,
                mlflow_uri=args.mlflow_uri,
                mlflow_experiment=args.mlflow_experiment
            ))
            logger.info(f"\n检索信息显示完成")
            logger.info(f"共显示 {retrieval_info['display_limit']} 个问题")
            logger.info(f"信息源ID: {retrieval_info['source_info']['source_config_id']}")
            logger.info(f"数据集: {retrieval_info['source_info']['dataset_name']}")
            if retrieval_info['enable_search'] and retrieval_info['search_results']:
                total_successful = sum(1 for r in retrieval_info['search_results'] if r['search_success'])
                logger.info(f"检索统计: {total_successful}/{len(retrieval_info['search_results'])} 个问题检索成功")

                # 显示召回率评估结果
                if retrieval_info.get('recall_evaluation'):
                    recall_eval = retrieval_info['recall_evaluation']
                    logger.info(f"召回率评估: 基于 {recall_eval['num_questions']} 个问题")
                    for metric, score in recall_eval['pooled_results'].items():
                        logger.info(f"  {metric}: {score:.4f} ({score*100:.2f}%)")

                # 显示统计结果（全部召回、部分召回、零召回）
                if retrieval_info.get('recall_statistics'):
                    stats = retrieval_info['recall_statistics']
                    logger.info(f"\n📊 问题召回情况统计:")
                    logger.info("=" * 50)
                    logger.info(f"总问题数: {stats['total_questions']}")
                    logger.info(f"✅ 全部召回: {stats['full_recall_count']} 个 ({stats['full_recall_count']/stats['total_questions']*100:.1f}%)")
                    logger.info(f"⚠️  部分召回: {stats['partial_recall_count']} 个 ({stats['partial_recall_count']/stats['total_questions']*100:.1f}%)")
                    logger.info(f"❌ 零召回: {stats['zero_recall_count']} 个 ({stats['zero_recall_count']/stats['total_questions']*100:.1f}%)")
                    logger.info("=" * 50)

                # 显示 QA 评估结果（只在非 badcase 模式下）
                if not badcase and retrieval_info.get('qa_evaluation'):
                    qa_eval = retrieval_info['qa_evaluation']
                    logger.info(f"QA评估: 基于 {qa_eval['num_questions']} 个问题")
                    for metric, score in qa_eval['pooled_results'].items():
                        logger.info(f"  {metric}: {score:.4f} ({score*100:.2f}%)")

                # 🆕 显示阶段耗时统计
                if retrieval_info.get('stage_times'):
                    stage_times = retrieval_info['stage_times']
                    # 使用默认值0来避免None比较错误
                    search_time = stage_times.get('search', 0) or 0
                    qa_time = stage_times.get('qa', 0) or 0

                    if search_time > 0 or qa_time > 0:
                        logger.info("\n阶段耗时统计:")
                        logger.info("=" * 50)
                        if search_time > 0:
                            logger.info(f"  SEARCH阶段: {search_time:.1f} 秒")
                        # 只在非 badcase 模式下显示 QA 时间
                        if not badcase and qa_time > 0:
                            logger.info(f"  QA阶段: {qa_time:.1f} 秒")
                        total_time = search_time
                        if not badcase:
                            total_time += qa_time
                        if total_time > 0:
                            logger.info(f"  总计: {total_time:.1f} 秒")
                        logger.info("=" * 50)
        except Exception as e:
            logger.error(f"\n获取检索信息失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        sys.exit(0)  # 显示信息后正常退出

    # 运行评估
    results = Evaluate.evaluate(
        dataset_name=args.dataset,
        load_and_generate_md=args.load,
        chunks_per_file=args.chunks_per_file,
        force_regenerate=True
    )

    # 打印结果摘要
    logger.info("\n" + "=" * 70)
    logger.info("Evaluation Results")
    logger.info("=" * 70)
    logger.info(f"Dataset: {results['dataset']}")
    logger.info(f"Timestamp: {results['timestamp']}")

    if 'markdown_generation' in results:
        logger.info("\n--- Markdown Generation ---")
        stats = results['markdown_generation'].get('stats', {})
        logger.info(f"Output Directory: {results['markdown_generation']['output_dir']}")
        logger.info(f"Total Chunks: {stats.get('total_chunks', 'N/A'):,}")
        logger.info(f"Number of MD Files: {stats.get('num_files', 'N/A')} 个")
        logger.info(f"Chunks Per File: {results['markdown_generation']['chunks_per_file']}")
        if stats.get('last_file_chunks') is not None:
            logger.info(f"Last File Chunks: {stats['last_file_chunks']} 个")
        logger.info(f"Status: {results['markdown_generation']['status']}")

        # 🆕 显示LOAD阶段耗时
        if 'load_time' in results['markdown_generation']:
            logger.info(f"LOAD阶段耗时: {results['markdown_generation']['load_time']:.1f} 秒")

    logger.info("=" * 70 + "\n")

    # 上传到系统（如果指定了 --upload）
    if args.upload:
        logger.info("\n" + "=" * 70)
        logger.info("开始上传 corpus 到系统")
        logger.info("=" * 70)

        config = EvaluationConfig(dataset_name=args.dataset)
        evaluator = Evaluate(config)

        async def upload_task():
            upload_result = await evaluator.upload_corpus(
                enable_extraction=True  # 默认启用提取
            )
            return upload_result

        # 使用更温和的方式管理 event loop
        try:
            upload_result = asyncio.run(upload_task())

            if upload_result['status'] == 'completed':
                logger.info("\n" + "=" * 70)
                logger.info("上传结果")
                logger.info("=" * 70)
                logger.info(f"Source Config ID: {upload_result['source_config_id']}")
                logger.info(f"数据集: {upload_result['dataset_name']}")
                logger.info(f"文件数: {upload_result['file_count']}")
                logger.info(f"成功: {upload_result['successful_files']}")
                logger.info(f"失败: {upload_result['failed_files']}")
                logger.info(f"总片段数: {upload_result['total_sections_count']:,}")
                logger.info(f"总事项数: {upload_result['total_events_count']:,}")
                # 获取模型名称，如果存在则使用完整路径
                filtered_model_name = upload_result.get('filtered_model_name', upload_result.get('model_name', ''))
                if filtered_model_name:
                    logger.info(f"结果保存位置: dataflow/evaluation/source/SAG/{filtered_model_name}/{upload_result['dataset_name']}/{upload_result['timestamp']}/")
                else:
                    logger.info(f"结果保存位置: dataflow/evaluation/source/SAG/{upload_result['dataset_name']}/{upload_result['timestamp']}/")

                # 显示处理时间
                if 'processing_time' in upload_result:
                    time_info = upload_result['processing_time']
                    logger.info(f"\n处理时间:")
                    logger.info(f"  Load 阶段: {time_info['total_load_time']:.1f} 秒")
                    logger.info(f"  Extract 阶段: {time_info['total_extract_time']:.1f} 秒")
                    logger.info(f"  总计: {time_info['total_time']:.1f} 秒")

                logger.info("=" * 70 + "\n")

                # 显示 LLM Token 消耗统计
                if 'llm_token_usage' in upload_result and upload_result['llm_token_usage']['total_tokens'] > 0:
                    token_summary = upload_result['llm_token_usage']
                    logger.info("=" * 70)
                    logger.info("LLM Token 消耗统计")
                    logger.info("=" * 70)
                    logger.info(f"总调用次数: {token_summary['total_calls']:,}")
                    logger.info(f"总输入 Tokens: {token_summary['total_prompt']:,}")
                    logger.info(f"总输出 Tokens: {token_summary['total_completion']:,}")
                    logger.info(f"总 Tokens: {token_summary['total_tokens']:,}")

                    # 按阶段显示
                    if token_summary.get('stages'):
                        logger.info("\n按阶段统计:")
                        for stage, stats in token_summary['stages'].items():
                            logger.info(f"\n  {stage}:")
                            logger.info(f"    调用次数: {stats['calls']:,}")
                            logger.info(f"    输入 Tokens: {stats['prompt']:,}")
                            logger.info(f"    输出 Tokens: {stats['completion']:,}")
                            logger.info(f"    总计 Tokens: {stats['total']:,}")

                    logger.info("=" * 70 + "\n")
            else:
                logger.error(f"\n❌ 上传失败: {upload_result.get('message', 'Unknown error')}\n")
        except KeyboardInterrupt:
            logger.info("\n\n用户中断上传")
            sys.exit(1)
        except Exception as e:
            logger.error(f"\n❌ 上传过程中发生错误: {e}\n")
            import traceback
            traceback.print_exc()
            sys.exit(1)
