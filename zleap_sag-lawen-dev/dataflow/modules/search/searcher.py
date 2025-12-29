"""
搜索器 - 统一入口

只保留SAG引擎，实现三阶段搜索：recall → expand → rerank
"""

import time
from typing import Dict, List, Any, Optional

from dataflow.core.ai.base import BaseLLMClient
from dataflow.core.prompt.manager import PromptManager
from dataflow.db import SourceEvent
from dataflow.exceptions import SearchError
from dataflow.modules.search.config import SearchConfig, RerankStrategy, ReturnType
from dataflow.modules.search.recall import RecallSearcher, RecallResult
from dataflow.modules.search.expand import ExpandSearcher, ExpandResult
from dataflow.modules.search.ranking.pagerank import RerankPageRankSearcher as EventPageRankSearcher
from dataflow.modules.search.ranking.pagerank_section import RerankPageRankSearcher as SectionPageRankSearcher
from dataflow.modules.search.ranking.rrf import RerankRRFSearcher
from dataflow.utils import get_logger

logger = get_logger("search.searcher")


class SAGSearcher:
    """
    SAG搜索器（Structured + Attributes + Graph）

    三阶段搜索流程：
    1. Recall - 实体召回（从query召回相关实体）
    2. Expand - 实体扩展（通过多跳关系发现更多实体）
    3. Rerank - 重排序（基于实体检索和排序事项或段落）

    返回结果（根据 return_type 配置）：

    EVENT模式（返回事项，默认）:
    {
        "events": List[SourceEvent],  # 事项列表
        "clues": List[Dict],           # 线索列表（支持前端图谱）
        "stats": Dict,                 # 统计信息
        "query": Dict                  # 查询信息
    }

    PARAGRAPH模式（返回段落）:
    {
        "sections": List[Dict],        # 段落列表
        "clues": List[Dict],           # 线索列表（支持前端图谱）
        "stats": Dict,                 # 统计信息
        "query": Dict                  # 查询信息
    }
    """
    
    def __init__(
        self,
        prompt_manager: PromptManager,
        model_config: Optional[Dict] = None,
    ):
        """
        初始化搜索器
        
        Args:
            prompt_manager: 提示词管理器
            model_config: LLM配置字典（可选）
                - 如果传入：使用该配置
                - 如果不传：自动从配置管理器获取 'search' 场景配置
        """
        self.prompt_manager = prompt_manager
        self.model_config = model_config
        self._llm_client = None  # 延迟初始化
        self.logger = get_logger("search.sag")
        
        self.logger.info("SAG搜索器初始化完成")
    
    async def _get_llm_client(self) -> BaseLLMClient:
        """获取LLM客户端（懒加载）"""
        if self._llm_client is None:
            from dataflow.core.ai.factory import create_llm_client
            
            self._llm_client = await create_llm_client(
                scenario='search',
                model_config=self.model_config
            )
        
        # 初始化三阶段搜索器
        self.recall_searcher = RecallSearcher(llm_client=self._llm_client, prompt_manager=self.prompt_manager)
        self.expand_searcher = ExpandSearcher(
                self._llm_client,
                self.prompt_manager,
            self.recall_searcher
        )

        # 初始化重排策略 - 事项级
        self.rerank_event_pagerank = EventPageRankSearcher(self._llm_client)
        self.rerank_rrf = RerankRRFSearcher(llm_client=self._llm_client)

        # 初始化重排策略 - 段落级
        self.rerank_section_pagerank = SectionPageRankSearcher(self._llm_client)
        
        return self._llm_client
    
    async def search(self, config: SearchConfig) -> Dict[str, Any]:
        """
        执行搜索

        Args:
            config: 搜索配置

        Returns:
            根据 config.return_type 返回不同格式：

            EVENT模式（返回事项）:
            {
                "events": List[SourceEvent],  # 事项列表
                "clues": List[Dict],           # 完整线索链
                "stats": Dict,                 # 统计信息
                "query": Dict                  # 查询信息
            }

            PARAGRAPH模式（返回段落）:
            {
                "sections": List[Dict],        # 段落列表
                "clues": List[Dict],           # 完整线索链
                "stats": Dict,                 # 统计信息
                "query": Dict                  # 查询信息
            }
        """
        try:
            # 确保LLM客户端已初始化
            await self._get_llm_client()

            total_start = time.perf_counter()

            # 🆕 打印完整的配置参数，方便验证前端传参
            self.logger.info("=" * 100)
            self.logger.info("📋 SAG搜索配置参数详情:")
            self.logger.info("=" * 100)

            # 基础参数
            self.logger.info("🔹 基础参数:")
            self.logger.info(f"  query: '{config.query}'")
            self.logger.info(f"  original_query: '{config.original_query}'")
            self.logger.info(f"  source_config_id: {config.source_config_id}")
            self.logger.info(f"  source_config_ids: {config.source_config_ids[:5]}")
            self.logger.info(f"  enable_query_rewrite: {config.enable_query_rewrite}")
            self.logger.info(f"  return_type: {config.return_type}")

            # Recall 配置
            self.logger.info("")
            self.logger.info("🔹 Recall (实体召回) 配置:")
            self.logger.info(f"  recall_mode: {config.recall.recall_mode}")
            self.logger.info(f"  use_fast_mode: {config.recall.use_fast_mode}")
            self.logger.info(f"  vector_top_k: {config.recall.vector_top_k}")
            self.logger.info(f"  vector_candidates: {config.recall.vector_candidates}")
            self.logger.info(f"  entity_similarity_threshold: {config.recall.entity_similarity_threshold}")
            self.logger.info(f"  event_similarity_threshold: {config.recall.event_similarity_threshold}")
            self.logger.info(f"  max_entities: {config.recall.max_entities}")
            self.logger.info(f"  max_events: {config.recall.max_events}")
            self.logger.info(f"  entity_weight_threshold: {config.recall.entity_weight_threshold}")
            self.logger.info(f"  final_entity_count: {config.recall.final_entity_count}")
            self.logger.info(
                f"  use_tokenizer: {config.recall.use_tokenizer}")

            # Expand 配置
            self.logger.info("")
            self.logger.info("🔹 Expand (实体扩展) 配置:")
            self.logger.info(f"  enabled: {config.expand.enabled}")
            self.logger.info(f"  max_hops: {config.expand.max_hops}")
            self.logger.info(f"  entities_per_hop: {config.expand.entities_per_hop}")
            self.logger.info(f"  weight_change_threshold: {config.expand.weight_change_threshold}")
            self.logger.info(f"  event_similarity_threshold: {config.expand.event_similarity_threshold}")
            self.logger.info(f"  min_events_per_hop: {config.expand.min_events_per_hop}")
            self.logger.info(f"  max_events_per_hop: {config.expand.max_events_per_hop}")

            # Rerank 配置
            self.logger.info("")
            self.logger.info("🔹 Rerank (事项重排) 配置:")
            self.logger.info(f"  strategy: {config.rerank.strategy}")
            self.logger.info(f"  score_threshold: {config.rerank.score_threshold}")
            self.logger.info(f"  max_results: {config.rerank.max_results}")
            self.logger.info(f"  max_key_recall_results: {config.rerank.max_key_recall_results}")
            self.logger.info(f"  max_query_recall_results: {config.rerank.max_query_recall_results}")
            self.logger.info(f"  pagerank_damping_factor: {config.rerank.pagerank_damping_factor}")
            self.logger.info(f"  pagerank_max_iterations: {config.rerank.pagerank_max_iterations}")
            self.logger.info(f"  rrf_k: {config.rerank.rrf_k}")
            self.logger.info("=" * 100)

            self.logger.info(
                f"🔍 开始搜索：query='{config.query}', source_config_id={config.source_config_id}"
            )

            # Recall: 实体召回
            recall_start = time.perf_counter()
            recall_result = await self._recall(config)
            recall_time = time.perf_counter() - recall_start
            
            # Expand: 实体扩展（可选）
            expand_start = time.perf_counter()
            if config.expand.enabled:
                expand_result = await self._expand(config, recall_result)
            else:
                expand_result = recall_result  # 跳过扩展
            expand_time = time.perf_counter() - expand_start
            
            # Rerank: 事项重排
            rerank_start = time.perf_counter()
            rerank_result = await self._rerank(config, expand_result)
            rerank_time = time.perf_counter() - rerank_start
            
            total_time = time.perf_counter() - total_start

            # 输出耗时统计
            self._log_timing(
                recall_time,
                expand_time,
                rerank_time,
                total_time,
                recall_result,
                expand_result,
            )
            
            # 构建最终响应
            response = self._build_response(
                config=config,
                recall_result=recall_result,
                expand_result=expand_result,
                rerank_result=rerank_result,
            )

            # 根据 return_type 输出不同的日志
            if config.return_type == ReturnType.PARAGRAPH:
                self.logger.info(
                    f"✅ 搜索完成：返回 {len(response.get('sections', []))} 个段落，"
                    f"{len(response['clues'])} 条线索"
                )
            else:
                self.logger.info(
                    f"✅ 搜索完成：返回 {len(response.get('events', []))} 个事项，"
                    f"{len(response['clues'])} 条线索"
                )

            return response

        except Exception as e:
            self.logger.error(f"❌ 搜索失败: {e}", exc_info=True)
            raise SearchError(f"搜索失败: {e}") from e
    
    async def _recall(self, config: SearchConfig) -> RecallResult:
        """
        Recall: 实体召回
        
        从query召回相关实体
        """
        self.logger.info("📍 Recall: 实体召回")
        result = await self.recall_searcher.search(config)
        self.logger.info(f"✓ Recall完成：召回 {len(result.key_final)} 个实体")
        return result
    
    async def _expand(
        self, 
        config: SearchConfig, 
        recall_result: RecallResult
    ) -> ExpandResult:
        """
        Expand: 实体扩展
        
        基于召回的实体，通过多跳关系发现更多相关实体
        """
        self.logger.info("📍 Expand: 实体扩展")
        result = await self.expand_searcher.search(config, recall_result)
        self.logger.info(
            f"✓ Expand完成：扩展到 {len(result.key_final)} 个实体，"
            f"跳跃 {result.total_jumps} 次"
        )
        return result
    
    async def _rerank(
        self,
        config: SearchConfig,
        expand_result: ExpandResult
    ) -> Dict[str, Any]:
        """
        Rerank: 事项/段落重排

        根据 return_type 选择返回事项或段落：
        - EVENT: 返回事项列表（使用 pagerank.py）
        - PARAGRAPH: 返回段落列表（使用 pagerank_section.py）
        """
        strategy = config.rerank.strategy
        return_type = config.return_type

        self.logger.info(
            f"📍 Rerank: {'事项' if return_type == ReturnType.EVENT else '段落'}重排"
            f"（策略={strategy}, 返回类型={return_type}）"
        )

        # 根据 return_type 选择不同的 Rerank 实现
        if return_type == ReturnType.PARAGRAPH:
            # 段落级 PageRank（只支持 PAGERANK 策略）
            if strategy != RerankStrategy.PAGERANK:
                self.logger.warning(
                    f"段落返回模式仅支持 PAGERANK 策略，当前策略 {strategy} 将被忽略"
                )
            reranker = self.rerank_section_pagerank
        else:
            # 事项级重排（支持 PAGERANK 和 RRF）
            if strategy == RerankStrategy.PAGERANK:
                reranker = self.rerank_event_pagerank
            elif strategy == RerankStrategy.RRF:
                reranker = self.rerank_rrf
            else:
                raise SearchError(f"不支持的重排策略: {strategy}")

        # 执行重排
        result = await reranker.search(
            key_final=expand_result.key_final,
            config=config
        )

        # 日志输出
        if return_type == ReturnType.PARAGRAPH:
            self.logger.info(
                f"✓ Rerank完成：返回 {len(result.get('sections', []))} 个段落"
            )
        else:
            self.logger.info(
                f"✓ Rerank完成：返回 {len(result.get('events', []))} 个事项"
            )

        return result
    
    def _log_timing(
        self,
        recall_time: float,
        expand_time: float,
        rerank_time: float,
        total_time: float,
        recall_result: Optional[Any] = None,
        expand_result: Optional[Any] = None
    ):
        """输出耗时统计"""

        def format_recall_steps(timings: Dict[str, float], step1_substep_timings: Optional[Dict[str, float]], recall_time_total: float):
            """格式化 recall 各步骤耗时"""
            if not timings:
                return ""

            lines = []
            # 🔧 修复：使用外层传入的 recall_time_total 作为基数，而不是内层的 timings['total']
            total = recall_time_total

            # 🆕 添加：显示召回策略（包括 Fast/Normal 和 FUZZY/EXACT）
            if step1_substep_timings:
                # 判断快速模式还是普通模式
                if "fast_generate_embedding" in step1_substep_timings:
                    mode_type = "快速模式 Fast"
                elif "normal_vector_search" in step1_substep_timings:
                    mode_type = "普通模式 Normal"
                else:
                    mode_type = "未知"
                
                # 判断精确搜索方式（FUZZY=ES / EXACT=MySQL）
                if "normal_mysql_exact" in step1_substep_timings and step1_substep_timings.get("normal_mysql_exact", 0) > 0:
                    recall_mode_type = "EXACT(MySQL)"
                elif "normal_es_exact" in step1_substep_timings and step1_substep_timings.get("normal_es_exact", 0) > 0:
                    recall_mode_type = "FUZZY(ES)"
                else:
                    recall_mode_type = "N/A"
                
                lines.append(f"  召回策略: 【{mode_type} | {recall_mode_type}】")
                lines.append("")

            step_names = {
                "step1": "步骤1 (query找key)",
                "step2": "步骤2 (key找event)",
                "step3": "步骤3 (query再找event)",
                "step4": "步骤4 (过滤Event)",
                "step5": "步骤5 (计算event-key权重)",
                "step6": "步骤6 (计算event-key-query)",
                "step7": "步骤7 (反向计算key权重)",
                "step8": "步骤8 (提取重要key)"
            }

            for step, name in step_names.items():
                if step in timings:
                    time_val = timings[step]
                    percentage = (time_val / total * 100) if total > 0 else 0
                    lines.append(f"  ├── {name}: {time_val:.3f}s ({percentage:.1f}%)")

                    # 如果是step1，添加子步骤详细信息
                    if step == "step1" and step1_substep_timings:
                        # 快速模式子步骤
                        if "fast_generate_embedding" in step1_substep_timings:
                            # 🔧 修复：添加分词召回
                            fast_tokenizer = step1_substep_timings.get("fast_tokenizer", 0)
                            fast_total = (
                                step1_substep_timings.get("fast_generate_embedding", 0) +
                                step1_substep_timings.get("fast_vector_search", 0) +
                                step1_substep_timings.get("fast_filter_threshold", 0) +
                                step1_substep_timings.get("fast_deduplicate", 0) +
                                fast_tokenizer
                            )
                            if fast_total > 0:
                                gen_embedding = step1_substep_timings.get('fast_generate_embedding', 0)
                                vector_search = step1_substep_timings.get('fast_vector_search', 0)
                                filter_threshold = step1_substep_timings.get('fast_filter_threshold', 0)
                                deduplicate = step1_substep_timings.get('fast_deduplicate', 0)
                                lines.append(f"  │   ├── 生成向量: {gen_embedding:.3f}s ({gen_embedding/fast_total*100:.1f}%)")
                                lines.append(f"  │   ├── 向量搜索: {vector_search:.3f}s ({vector_search/fast_total*100:.1f}%)")
                                lines.append(f"  │   ├── 阈值过滤: {filter_threshold:.3f}s ({filter_threshold/fast_total*100:.1f}%)")
                                lines.append(f"  │   ├── 去重限制: {deduplicate:.3f}s ({deduplicate/fast_total*100:.1f}%)")
                                if fast_tokenizer > 0:
                                    lines.append(f"  │   ├── 分词召回: {fast_tokenizer:.3f}s ({fast_tokenizer/fast_total*100:.1f}%)")
                                lines.append(f"  │       └── 快速模式总计: {fast_total:.3f}s")
                        # 普通模式子步骤
                        elif "normal_vector_search" in step1_substep_timings:
                            # 🔧 修复：使用正确的 key 名称
                            mysql_time = step1_substep_timings.get("normal_mysql_exact", 0)
                            es_time = step1_substep_timings.get("normal_es_exact", 0)
                            exact_search_time = mysql_time if mysql_time > 0 else es_time
                            exact_search_label = "MySQL精确匹配" if mysql_time > 0 else "ES模糊匹配"
                            
                            # 🔧 修复：使用正确的 key
                            vector_search = step1_substep_timings.get('normal_vector_search', 0)
                            get_entity_types = step1_substep_timings.get('normal_get_entity_types', 0)
                            llm_rewrite = step1_substep_timings.get('normal_llm_rewrite_extract', 0)  # 🔧 修复 key
                            tokenizer_time = step1_substep_timings.get('normal_tokenizer', 0)         # 🆕 新增
                            merge_results = step1_substep_timings.get('normal_merge_results', 0)      # 🔧 修复 key
                            
                            normal_total = (
                                vector_search +
                                get_entity_types +
                                llm_rewrite +
                                exact_search_time +
                                tokenizer_time +
                                merge_results
                            )
                            
                            if normal_total > 0:
                                lines.append(f"  │   ├── 向量召回: {vector_search:.3f}s ({vector_search/normal_total*100:.1f}%)")
                                lines.append(f"  │   ├── 获取类型: {get_entity_types:.3f}s ({get_entity_types/normal_total*100:.1f}%)")
                                lines.append(f"  │   ├── LLM重写+识别: {llm_rewrite:.3f}s ({llm_rewrite/normal_total*100:.1f}%)")
                                lines.append(f"  │   ├── {exact_search_label}: {exact_search_time:.3f}s ({exact_search_time/normal_total*100:.1f}%)")
                                if tokenizer_time > 0:
                                    lines.append(f"  │   ├── 分词召回: {tokenizer_time:.3f}s ({tokenizer_time/normal_total*100:.1f}%)")
                                lines.append(f"  │   └── 合并结果: {merge_results:.3f}s ({merge_results/normal_total*100:.1f}%)")
                                lines.append(f"  │       └── 普通模式总计: {normal_total:.3f}s")
                                
                                # 🆕 显示未统计的耗时（如果有）
                                step1_time = timings.get("step1", 0)
                                if step1_time > normal_total + 0.01:
                                    untracked = step1_time - normal_total
                                    lines.append(f"  │       ⚠️  未统计: {untracked:.3f}s ({untracked/step1_time*100:.1f}%)")

            # 🆕 添加：显示步骤总和与总时间的对比
            steps_sum = sum(timings.get(step, 0) for step in step_names.keys())
            overhead = total - steps_sum
            if overhead > 0.001:  # 如果开销大于1ms
                lines.append("")
                lines.append(f"  步骤总计: {steps_sum:.3f}s ({steps_sum/total*100:.1f}%)")
                lines.append(f"  其他开销: {overhead:.3f}s ({overhead/total*100:.1f}%)")

            return "\n".join(lines)

        self.logger.info("=" * 80)
        self.logger.info("⏱️  搜索耗时统计：")
        self.logger.info("-" * 80)

        # Recall 阶段详细信息
        if recall_result and hasattr(recall_result, 'step_timings'):
            step1_substep_timings = getattr(recall_result, 'step1_substep_timings', None)
            # 🔧 修复：传入 recall_time 作为基数
            self.logger.info(
                f"Recall 阶段 (总计: {recall_time:.3f}s ({recall_time/total_time*100:.1f}%)):\n"
                f"{format_recall_steps(recall_result.step_timings, step1_substep_timings, recall_time)}"
            )
        else:
            self.logger.info(
                f"Recall (实体召回): {recall_time:.3f}秒 "
                f"({recall_time/total_time*100:.1f}%)"
            )

        # Expand 阶段详细信息
        self.logger.info("")
        expand_details = []
        if expand_result and hasattr(expand_result, "step_average_timings"):
            step_average_timings = getattr(expand_result, "step_average_timings", {}) or {}
            total_jumps = getattr(expand_result, "total_jumps", 0)
            if step_average_timings:
                step_labels = {
                    "step1": "key找event",
                    "step2": "query匹配",
                    "step3": "event-key权重",
                    "step4": "event-key-query",
                    "step5": "反向算key",
                }
                for step in ["step1", "step2", "step3", "step4", "step5"]:
                    if step in step_average_timings:
                        expand_details.append(f"{step_labels.get(step, step)}: {step_average_timings[step]:.3f}s")
        
        if expand_details:
            self.logger.info(
                f"Expand (实体扩展): {expand_time:.3f}秒 ({expand_time/total_time*100:.1f}%) "
                f"| 跳数: {total_jumps}"
            )
            self.logger.info(f"  └── 每跳平均: {', '.join(expand_details)}")
        else:
            self.logger.info(
                f"Expand (实体扩展): {expand_time:.3f}秒 ({expand_time/total_time*100:.1f}%)"
            )
        
        # Rerank 阶段
        self.logger.info(
            f"Rerank (事项重排): {rerank_time:.3f}秒 ({rerank_time/total_time*100:.1f}%)"
        )
        
        self.logger.info("-" * 80)
        self.logger.info(f"总耗时: {total_time:.3f}秒 (100%)")
        
        # 🆕 性能瓶颈提示
        bottleneck_threshold = 2.0  # 2秒以上为瓶颈
        bottlenecks = []
        if recall_time > bottleneck_threshold:
            bottlenecks.append(f"Recall({recall_time:.1f}s)")
        if expand_time > bottleneck_threshold:
            bottlenecks.append(f"Expand({expand_time:.1f}s)")
        if rerank_time > bottleneck_threshold:
            bottlenecks.append(f"Rerank({rerank_time:.1f}s)")
        
        if bottlenecks:
            self.logger.info(f"⚠️  性能瓶颈: {', '.join(bottlenecks)}")
        
        self.logger.info("=" * 80)
    
    def _build_response(
        self,
        config: SearchConfig,
        recall_result: RecallResult,
        expand_result,  # Union[RecallResult, ExpandResult]
        rerank_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        构建最终响应

        整合三阶段的线索和结果，支持事项和段落两种返回格式
        """
        from collections import Counter
        from dataflow.modules.search.path_analyzer import analyze_paths

        # 🆕 使用统一的all_clues字段（新版追踪器）
        all_clues = getattr(config, 'all_clues', [])

        # Fallback: 兼容旧版（如果all_clues为空，尝试从旧字段收集）
        if not all_clues:
            all_clues.extend(getattr(config, 'recall_clues', []))
            all_clues.extend(getattr(config, 'expansion_clues', []))
            all_clues.extend(getattr(config, 'rerank_clues', []))

        # 构建统计信息
        recall_entities = recall_result.key_final
        expand_entities = [
            k for k in expand_result.key_final
            if k.get("steps", [0])[0] >= 2
        ]

        recall_by_type = Counter(
            e.get("type") for e in recall_entities if e.get("type")
        )

        # 判断 expand 是否被执行
        from .expand import ExpandResult
        expand_was_executed = isinstance(expand_result, ExpandResult)

        # 根据 return_type 提取结果
        return_type = config.return_type

        if return_type == ReturnType.PARAGRAPH:
            # 段落模式
            sections = rerank_result.get("sections", [])
            result_key = "sections"
            result_count = len(sections)
            self.logger.info(
                f"✨ 响应构建完成（段落模式）: "
                f"sections={result_count}, "
                f"clues={len(all_clues)}"
            )
        else:
            # 事项模式（默认）
            events = rerank_result.get("events", [])
            result_key = "events"
            result_count = len(events)
            self.logger.info(
                f"✨ 响应构建完成（事项模式）: "
                f"events={result_count}, "
                f"clues={len(all_clues)}"
            )

        stats = {
            "recall": {
                "entities_count": len(recall_entities),
                "by_type": dict(recall_by_type),
                "step_timings": getattr(recall_result, 'step_timings', {}),
                "step1_substep_timings": getattr(recall_result, 'step1_substep_timings', None),
            },
            "expand": {
                "entities_count": len(expand_entities) if expand_was_executed else 0,
                "total_entities": len(expand_result.key_final),
                "hops": expand_result.total_jumps if expand_was_executed else 0,
                "converged": expand_result.convergence_reached if expand_was_executed else False,
            },
            "rerank": {
                f"{result_key}_count": result_count,  # events_count 或 sections_count
                "strategy": str(config.rerank.strategy),
                "return_type": str(return_type),  # 新增：记录返回类型
            }
        }

        # 构建查询信息
        query_info = {
            "original": config.original_query or config.query,
            "current": config.query,
            "rewritten": (
                config.original_query != config.query
                if config.original_query else False
            )
        }

        # 构建响应（根据 return_type 使用不同的键）
        response = {
            result_key: rerank_result.get(result_key, []),  # "events" 或 "sections"
            "clues": all_clues,
            "stats": stats,
            "query": query_info,
        }

        # 🆕 路径分析（仅事项模式需要，段落模式跳过）
        if return_type == ReturnType.EVENT:
            try:
                # 🔧 只对最终返回的事项进行路径分析
                events = rerank_result.get("events", [])
                target_event_ids = [event.id for event in events]

                self.logger.info(
                    f"🔍 路径分��目标: {len(events)} 个事项, "
                    f"事项ID示例: {target_event_ids[:3] if len(target_event_ids) >= 3 else target_event_ids}"
                )

                path_result = analyze_paths(
                    all_clues,
                    target_event_ids=target_event_ids
                )

                # 获取路径分析结果
                min_lines = path_result.get("min_lines", {})
                max_lines = path_result.get("max_lines", {})
                entitys = path_result.get("entitys", {})
                rerank_lines = path_result.get("rerank_lines", {})

                self.logger.info(
                    f"📊 路径分析完成: 事项数={len(min_lines)}, "
                    f"最短路径={len(min_lines)}, 最长路径={len(max_lines)}"
                )

                # 输出 entitys 完整统计
                if entitys:
                    self.logger.debug("=" * 80)
                    self.logger.debug(f"📊 实体按跳数完整统计:")
                    for hop in sorted(entitys.keys(), key=lambda x: int(x)):
                        entities = entitys[hop]
                        self.logger.debug(f"\n  【Hop {hop}】 {len(entities)} 个实体:")
                        for idx, entity in enumerate(entities, 1):
                            self.logger.debug(
                                f"    {idx}. {entity.get('name', 'N/A')[:30]} "
                                f"| 类型: {entity.get('type', 'N/A')}"
                            )

                # 输出 rerank_lines 完整数据（只显示前3个事项的所有路径）
                if rerank_lines:
                    self.logger.debug("=" * 80)
                    self.logger.debug(f"📋 Top 3 事项的所有路径 (共 {len(rerank_lines)} 个事项):")

                    # 只显示前3个事项
                    for idx, (event_id, all_paths) in enumerate(list(rerank_lines.items())[:3], 1):
                        # 获取事项标题（从第一条路径的最后一个节点）
                        event_title = "未知事项"
                        if all_paths and len(all_paths) > 0:
                            for item in all_paths[0]:  # 第一条路径
                                if "event" in item:
                                    event_title = item["event"].get("title", "未知事项")[:40]
                                    break

                        self.logger.debug(f"\n  【事项 {idx}】 {event_title}")
                        self.logger.debug(f"  事项ID: {event_id[:50]}...")
                        self.logger.debug(f"  路径总数: {len(all_paths)} 条")

                        # 输出每条路径
                        for path_idx, path_items in enumerate(all_paths, 1):
                            self.logger.debug(f"\n    ┌─ 路径 {path_idx} (长度: {len(path_items)} 个节点)")

                            for step_idx, item in enumerate(path_items, 1):
                                if "query" in item:
                                    q = item["query"]
                                    self.logger.debug(
                                        f"    │ 步骤{step_idx} [Query]: {q.get('content', 'N/A')[:40]}"
                                    )
                                elif "entity" in item:
                                    e = item["entity"]
                                    self.logger.debug(
                                        f"    │ 步骤{step_idx} [Entity]: {e.get('name', 'N/A')[:30]} "
                                        f"| Hop={e.get('hop', 0)} "
                                        f"| 类型={e.get('type', 'N/A')}"
                                    )
                                elif "event" in item:
                                    ev = item["event"]
                                    self.logger.debug(
                                        f"    │ 步骤{step_idx} [Event]: {ev.get('title', 'N/A')[:40]}"
                                    )

                            self.logger.debug(f"    └─ 路径 {path_idx} 结束")

                    if len(rerank_lines) > 3:
                        self.logger.debug(f"\n  ... 还有 {len(rerank_lines) - 3} 个事项未显示")

                    self.logger.debug("=" * 80)

                # 返回给前端
                response["min_lines"] = path_result.get("min_lines", {})
                response["max_lines"] = path_result.get("max_lines", {})
                response["entitys"] = path_result.get("entitys", {})
                response["rerank_lines"] = path_result.get("rerank_lines", {})

            except Exception as e:
                self.logger.warning(f"⚠️ 路径分析失败: {e}", exc_info=True)

        return response


# 向后兼容别名
EventSearcher = SAGSearcher

__all__ = [
    "SAGSearcher",
    "EventSearcher",
]
