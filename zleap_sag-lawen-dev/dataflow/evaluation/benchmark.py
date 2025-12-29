"""
评估基准测试模块

提供数据集评估、检索评估和QA评估功能
"""

import json
import sys
import time
import asyncio
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
    def load_latest_source_info(cls) -> Dict[str, Any]:
        """
        从 dataflow/evaluation/source/SAG 路径下加载最新时间戳文件夹的 source_info.json
        
        Returns:
            包含 source_config_id 和 dataset_name 的字典
        """
        import json
        from pathlib import Path
        
        # 获取 SAG 目录路径
        current_file = Path(__file__)
        sag_dir = current_file.parent / "source" / "SAG"
        
        if not sag_dir.exists():
            raise FileNotFoundError(f"SAG directory not found: {sag_dir}")
        
        # 获取所有时间戳文件夹
        timestamp_dirs = [d for d in sag_dir.iterdir() if d.is_dir()]
        
        if not timestamp_dirs:
            raise FileNotFoundError(f"No timestamp directories found in: {sag_dir}")
        
        # 按时间戳排序，获取最新的
        latest_dir = max(timestamp_dirs, key=lambda d: d.name)
        
        # 读取 source_info.json
        source_info_path = latest_dir / "source_info.json"
        if not source_info_path.exists():
            raise FileNotFoundError(f"source_info.json not found in: {latest_dir}")
        
        logger.info(f"Loading source info from: {source_info_path}")
        
        with open(source_info_path, 'r', encoding='utf-8') as f:
            source_info = json.load(f)
        
        return {
            'source_config_id': source_info.get('source_config_id'),
            'dataset_name': source_info.get('dataset_name'),
            'timestamp': source_info.get('timestamp'),
            'source_name': source_info.get('source_name'),
            'file_path': str(source_info_path)
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
    async def search_questions(cls, source_config_id: str, questions: List[str], limit: Optional[int] = None, verbose: bool = False) -> List[Dict[str, Any]]:
        """
        对问题列表进行检索，返回检索结果
        
        Args:
            source_config_id: 数据源ID
            questions: 问题列表
            limit: 限制处理的问题数量
            verbose: 是否显示详细信息
        
        Returns:
            检索结果列表
        """
        import logging
        
        logger.info("Initializing searcher...")
        
        # 配置日志级别
        if verbose:
            logger.info("启用详细日志模式...")
            
            # 创建控制台handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            
            # 设置各个模块的日志级别
            loggers_to_configure = [
                'dataflow',
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
            logger.info("使用默认日志级别(WARNING)...")
            # 只显示WARNING级别的日志
            for logger_name in ['dataflow', 'dataflow.modules.search', 'elasticsearch', 'urllib3']:
                logging.getLogger(logger_name).setLevel(logging.WARNING)
        
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
    async def show_retrieval_info(cls, limit: Optional[int] = None, show_paragraphs: bool = True, enable_search: bool = False, search_verbose: bool = False) -> Dict[str, Any]:
        """
        显示检索相关信息：最新的 source_config_id、dataset_name 和数据集内容，可选进行实际检索
        
        Args:
            limit: 限制显示的问题数量，None表示显示全部
            show_paragraphs: 是否显示 paragraphs 详细信息
            enable_search: 是否启用实际检索功能
            search_verbose: 检索过程是否显示详细信息
        
        Returns:
            完整的检索信息字典
        """
        logger.info("Loading latest source information...")
        
        # 1. 加载最新的 source_info
        try:
            source_info = cls.load_latest_source_info()
            logger.info("Successfully loaded source information")
        except Exception as e:
            logger.error(f"Failed to load source info: {e}")
            raise
        
        # 2. 加载对应的数据集信息
        dataset_name = source_info['dataset_name']
        logger.info(f"Loading dataset: {dataset_name}")
        
        try:
            dataset_info = cls.load_dataset_info(dataset_name)
            logger.info(f"Successfully loaded dataset with {dataset_info['total_questions']} questions")
        except Exception as e:
            logger.error(f"Failed to load dataset {dataset_name}: {e}")
            raise
        
        # 3. 打印信息
        logger.info("\n" + "=" * 80)
        logger.info("🔍 检索信息概览")
        logger.info("=" * 80)
        logger.info(f"📁 信息源文件: {source_info['file_path']}")
        logger.info(f"🆔 信息源ID: {source_info['source_config_id']}")
        logger.info(f"📊 数据集名称: {source_info['dataset_name']}")
        logger.info(f"📅 时间戳: {source_info['timestamp']}")
        logger.info(f"📝 信息源名称: {source_info['source_name']}")
        logger.info(f"❓ 问题总数: {dataset_info['total_questions']}")
        
        # 4. 显示问题和答案信息
        questions = dataset_info['questions']
        answers = dataset_info['answers'] 
        paragraphs = dataset_info['paragraphs']
        
        # 应用限制
        display_limit = min(len(questions), limit) if limit else len(questions)
        
        logger.info(f"\n📋 显示前 {display_limit} 个问题:")
        logger.info("=" * 80)
        
        for i in range(display_limit):
            logger.info(f"\n[问题 {i+1}]")
            logger.info(f"问题: {questions[i]}")
            logger.info(f"答案: {answers[i]}")
            
            if show_paragraphs and i < len(paragraphs):
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
        if enable_search:
            logger.info(f"\n启动实际检索 (数据源: {source_info['source_config_id']})...")
            logger.info("=" * 80)
            
            try:
                # 执行检索
                search_results = await cls.search_questions(
                    source_config_id=source_info['source_config_id'],
                    questions=questions,
                    limit=display_limit,
                    verbose=search_verbose
                )
                
                # 检查是否有paragraphs数据，如果有则进行召回率评估
                has_supporting_paragraphs = any(
                    paragraphs[i] and any(p.get('is_supporting', False) for p in paragraphs[i] if p)
                    for i in range(min(len(paragraphs), display_limit))
                    if i < len(paragraphs) and paragraphs[i]
                )
                
                if has_supporting_paragraphs:
                    logger.info(f"\n正在进行召回率评估...")
                    # 准备评估数据
                    gold_docs_list = []
                    retrieved_docs_list = []
                    
                    for i, result in enumerate(search_results):
                        if i < len(paragraphs) and paragraphs[i]:
                            # 获取标准答案段落(支持性段落的标题+内容)
                            supporting_docs = []
                            for para in paragraphs[i]:
                                if para.get('is_supporting', False):
                                    supporting_docs.append({
                                        'title': para['title'],
                                        'content': para['text'][:500]  # 取前500字符用于匹配
                                    })
                            
                            # 获取检索结果段落(清理markdown标记)
                            retrieved_docs = []
                            for section in result['sections']:
                                heading = section.get('heading', '')
                                content = section.get('content', '')
                                # 清理markdown标记 (# 前缀) 和首尾空格
                                clean_heading = heading.lstrip('#').strip()
                                clean_content = content.strip()[:500]  # 取前500字符用于匹配
                                if clean_heading and clean_content:
                                    retrieved_docs.append({
                                        'title': clean_heading,
                                        'content': clean_content
                                    })
                            
                            # 进行标题+内容的双重匹配
                            matched_docs = []
                            for gold_doc in supporting_docs:
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
                            
                            # 为了兼容RetrievalRecall，仍然传递标题列表
                            supporting_titles = [doc['title'] for doc in supporting_docs]
                            gold_docs_list.append(matched_docs)  # 传递匹配成功的文档
                            retrieved_docs_list.append([doc['title'] for doc in retrieved_docs])
                            
                            # 调试输出
                            logger.info(f"\n[DEBUG] 问题 {i+1}:")
                            logger.info(f"  标准文档: {supporting_titles}")
                            logger.info(f"  检索文档: {[doc['title'] for doc in retrieved_docs[:5]]}...")  # 只显示前5个
                            logger.info(f"  匹配成功: {matched_docs}")
                            logger.info(f"  匹配率: {len(matched_docs)}/{len(supporting_titles)}")
                    
                    # 使用RetrievalRecall进行评估
                    if gold_docs_list and retrieved_docs_list:
                        from dataflow.evaluation.metrics import RetrievalRecall
                        recall_metric = RetrievalRecall()
                        
                        pooled_recall, example_recalls = recall_metric.calculate_metric_scores(
                            gold_docs=gold_docs_list,
                            retrieved_docs=retrieved_docs_list,
                            k_list=[1, 3, 5, 10]
                        )
                        
                        recall_evaluation = {
                            'pooled_results': pooled_recall,
                            'example_results': example_recalls,
                            'num_questions': len(gold_docs_list)
                        }
                        
                        logger.info(f"\n召回率评估结果:")
                        logger.info("=" * 50)
                        for metric, score in pooled_recall.items():
                            logger.info(f"{metric}: {score:.4f} ({score*100:.2f}%)")
                        logger.info("=" * 50)
                
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
                        logger.info(f"检索到 {len(sections)} 个相关段落:")
                        
                        for j, section in enumerate(sections[:5], 1):  # 只显示前5个
                            heading = section.get('heading', 'N/A')
                            content = section.get('content', '').replace('\n', ' ')
                            
                            # 获取得分信息
                            cosine_score = section.get('original_score', 0.0)
                            pagerank_score = section.get('weight') or section.get('pagerank', 0.0)
                            
                            logger.info(f"   [{j}] 标题: {heading}")
                            logger.info(f"       余弦相似度: {cosine_score:.4f} | PageRank: {pagerank_score:.4f}")
                            logger.info(f"       内容: {content[:200]}..." if len(content) > 200 else f"       内容: {content}")
                            
                        if len(sections) > 5:
                            logger.info(f"   ... 还有 {len(sections) - 5} 个段落")
                    else:
                        error_msg = result.get('error', '未知错误')
                        logger.info(f"检索失败: {error_msg}")
                    
                    if result != search_results[-1]:  # 不是最后一个
                        logger.info("-" * 60)
                
                logger.info("\n" + "=" * 80)
                
            except Exception as e:
                logger.error(f"检索过程出现错误: {e}")
                import traceback
                traceback.print_exc()
        
        # 6. 返回完整信息
        return {
            'source_info': source_info,
            'dataset_info': dataset_info,
            'display_limit': display_limit,
            'show_paragraphs': show_paragraphs,
            'enable_search': enable_search,
            'search_results': search_results,
            'recall_evaluation': recall_evaluation
        }

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
            save_result = loader.save_as_markdown(
                chunks_per_file=chunks_per_file,
                force_regenerate=force_regenerate
            )

            results['markdown_generation'] = {
                'output_dir': str(save_result['output_dir']),
                'stats': save_result['stats'],
                'chunks_per_file': chunks_per_file,
                'status': 'completed'
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

        # 4. 循环处理每个 md 文件
        file_results = []
        total_sections = 0
        total_events = 0

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

            logger.info(f"  ✓ 文件处理完成\n")

        # 5. 保存结果到 dataflow/evaluation/source/SAG/{timestamp}/
        source_dir = Path(__file__).parent / "source" / "SAG" / timestamp
        source_dir.mkdir(parents=True, exist_ok=True)

        result = {
            "source_config_id": source_config_id,
            "source_name": source_name,
            "source_description": source_description,
            "dataset_name": self.config.dataset_name,
            "file_count": len(md_files),
            "successful_files": len([r for r in file_results if r['status'] == 'completed']),
            "failed_files": len([r for r in file_results if r['status'] == 'error']),
            "total_sections_count": total_sections,
            "total_events_count": total_events,
            "file_results": file_results,
            "timestamp": timestamp,
            "status": "completed",
            "extraction_enabled": enable_extraction
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
        choices=["musique", "hotpotqa", "2wikimultihopqa", "sample"],
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
        "--info-limit",
        type=int,
        default=None,
        help="Limit number of questions to display in --show-retrieval-info (default: show all)"
    )

    parser.add_argument(
        "--enable-search",
        action="store_true",
        help="Enable actual search functionality in --show-retrieval-info"
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

    args = parser.parse_args()

    # 如果指定了 --show-retrieval-info，显示检索信息并退出
    if args.show_retrieval_info:
        try:
            # 使用 asyncio.run 运行异步函数
            retrieval_info = asyncio.run(Evaluate.show_retrieval_info(
                limit=args.info_limit,
                show_paragraphs=not args.no_paragraphs,
                enable_search=args.enable_search,
                search_verbose=args.search_verbose
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
                logger.info(f"结果保存位置: dataflow/evaluation/source/SAG/{upload_result['timestamp']}/")
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
