"""
搜索模块配置

简洁清晰的三阶段配置：
1. RecallConfig - 实体召回
2. ExpandConfig - 实体扩展  
3. RerankConfig - 事项重排
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import Field

from dataflow.models.base import DataFlowBaseModel


class RerankStrategy(str, Enum):
    """
    重排策略

    - PAGERANK: 基于图算法的PageRank排序
    - RRF: 基于倒数排名融合的排序
    """
    PAGERANK = "pagerank"
    RRF = "rrf"

    def __str__(self) -> str:
        return self.value


class ReturnType(str, Enum):
    """
    返回类型

    - EVENT: 事项（默认）
    - PARAGRAPH: 段落
    """
    EVENT = "event"
    PARAGRAPH = "paragraph"

    def __str__(self) -> str:
        return self.value


class RecallMode(str, Enum):
    """
    实体精确检索模式

    - FUZZY: 模糊（默认，使用 ES 名称检索）
    - EXACT: 精确（使用 MySQL normalized_name 精确/前缀检索）
    """
    FUZZY = "fuzzy"
    EXACT = "exact"

    def __str__(self) -> str:
        return self.value


class RecallConfig(DataFlowBaseModel):
    """
    实体召回配置

    从query召回相关实体（entities/keys）
    """

    # 模式开关
    use_fast_mode: bool = Field(
        default=True,
        description="快速模式（跳过LLM属性抽取，直接用query向量召回实体）"
    )

    # 精确检索模式（ES / MySQL）
    recall_mode: RecallMode = Field(
        default=RecallMode.FUZZY,
        description="实体精确检索模式：fuzzy=ES 名称检索，exact=MySQL normalized 精确/前缀检索"
    )

    # 向量检索
    vector_top_k: int = Field(
        default=40,
        ge=1, le=100,
        description="向量检索返回数量"
    )

    vector_candidates: int = Field(
        default=200,
        ge=10, le=500,
        description="向量检索候选池大小"
    )

    llm_few_shots_count: int = Field(
        default=10,
        ge=1, le=50,
        description="LLM合并调用时的few-shots数量（向量召回实体作为示例）"
    )

    # 相似度阈值
    entity_similarity_threshold: float = Field(
        default=0.4,
        ge=0.0, le=1.0,
        description="实体相似度阈值"
    )

    event_similarity_threshold: float = Field(
        default=0.4,
        ge=0.0, le=1.0,
        description="事项相似度阈值"
    )

    # 数量控制
    max_entities: int = Field(
        default=25,
        ge=1, le=200,
        description="最大实体数量"
    )

    max_events: int = Field(
        default=60,
        ge=1, le=500,
        description="最大事项数量"
    )

    # 权重过滤
    entity_weight_threshold: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="实体权重阈值"
    )

    final_entity_count: int = Field(
        default=15,
        ge=1, le=100,
        description="最终返回实体数量"
    )

    # Step4权重平衡参数
    step4_event_key_balance: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Step4中event权重的query-event占比（0-1），0.5表示两者各占50%"
    )

    # === 普通模式 LLM 过滤+扩展配置 ===
    llm_filter_enabled: bool = Field(
        default=True,
        description="是否启用LLM过滤+扩展（普通模式下生效）"
    )

    llm_expand_max_count: int = Field(
        default=20,
        ge=1, le=100,
        description="LLM扩展生成的最大实体数量"
    )

    sql_fuzzy_search_limit: int = Field(
        default=5,
        ge=1, le=50,
        description="每个LLM生成实体的SQL模糊搜索最大结果数"
    )

    sql_fuzzy_default_similarity: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="SQL模糊搜索匹配实体的默认相似度分数"
    )

    # === 分词器配置 ===
    use_tokenizer: bool = Field(
        default=False,  # 🔧 禁用分词器，避免提取单一泛化词（如"质量"）污染召回
        description="启用分词器辅助召回（向量+分词双通道）"
    )

    tokenizer_top_k: int = Field(
        default=15,
        ge=1, le=50,
        description="分词器提取的最大关键词数量"
    )

    tokenizer_similarity: float = Field(
        default=0.50,  # 🔧 降低权重，避免分词结果污染高质量召回
        ge=0.0, le=1.0,
        description="分词匹配实体的默认相似度分数（配合 type_weight 排序）"
    )

    tokenizer_priority_gap: float = Field(
        default=0.05,
        ge=0.0, le=5.0,
        description="分词补充实体的动态权重间隔，>0 时确保其权重至少领先普通实体"
    )

    # === 向量召回保护配置（已废弃，改用背景实体兜底）===
    vector_protect_top_n: int = Field(
        default=0,  # 默认禁用，改用背景实体兜底
        ge=0, le=50,
        description="[已废弃] 受保护的向量召回实体数量（0=禁用，改用background_fallback）"
    )

    # === Query直接搜索Events配置（新召回策略）===
    # 步骤1: Query直接召回Event（高质量）
    query_event_threshold: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="Query直接召回Event的相似度阈值（高阈值保证质量）"
    )
    
    query_event_max: int = Field(
        default=10,
        ge=1, le=100,
        description="Query直接召回Event的最大数量（高质量事项top-N）"
    )
    
    # === 背景实体配置（高质量事项反向召回）===
    background_entity_enabled: bool = Field(
        default=True,
        description="是否启用背景实体（从高质量事项反向召回实体作为LLM参考）"
    )
    
    background_event_top_n: int = Field(
        default=10,
        ge=1, le=30,
        description="取高质量事项的前N个用于反向召回实体"
    )
    
    background_entity_max: int = Field(
        default=20,
        ge=1, le=50,
        description="背景实体的最大数量（按热度排序后取前N个给LLM参考）"
    )
    
    background_entity_min_name_length: int = Field(
        default=2,
        ge=1, le=10,
        description="背景实体名称最小长度（过滤泛化实体如'质量'）"
    )
    
    background_entity_default_similarity: float = Field(
        default=0.70,
        ge=0.0, le=1.0,
        description="背景实体的默认相似度基准值（无法计算向量相似度时使用）"
    )
    
    background_fallback_threshold: int = Field(
        default=5,
        ge=0, le=20,
        description="兜底触发阈值：当有效keys数量 < 此值时，从背景实体补充"
    )
    
    background_fallback_max: int = Field(
        default=10,
        ge=1, le=30,
        description="兜底时从背景实体最多补充的数量"
    )

    # === 向量召回候选实体配置（步骤1.5）===
    candidate_entities_enabled: bool = Field(
        default=False,
        description="是否启用向量召回候选实体（作为LLM参考的few-shots）"
    )

    # 步骤2.1: Query召回Event用于交集过滤（宽松）
    filter_event_threshold: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="用于交集过滤的Event召回阈值（低阈值，宽松过滤）"
    )
    
    filter_event_max: int = Field(
        default=200,
        ge=1, le=500,
        description="用于交集过滤的Event召回最大数量"
    )
    
    # 步骤3: Keys截断（双策略）
    key_score_threshold: float = Field(
        default=0.2,
        ge=0.0, le=2.0,
        description="Keys的effective_score阈值（similarity × type_weight）"
    )
    
    key_max_count: int = Field(
        default=100,
        ge=1, le=500,
        description="Keys的安全上限数量"
    )

    # 旧配置（保留兼容）
    use_query_event_search: bool = Field(
        default=True,
        description="是否启用query直接搜索events（在step2和step3之间）"
    )

    query_event_weight_ratio: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="content_vector在混合相似度中的权重比例（0.7表示70% content + 30% title）"
    )


class ExpandConfig(DataFlowBaseModel):
    """
    实体扩展配置

    通过多跳关系扩展更多相关实体
    """

    # 开关
    enabled: bool = Field(
        default=True,
        description="是否启用扩展"
    )

    # 跳数控制
    max_hops: int = Field(
        default=3,
        ge=1, le=10,
        description="最大跳数"
    )

    entities_per_hop: int = Field(
        default=10,
        ge=1, le=50,
        description="每跳新增实体数"
    )

    # 收敛控制
    weight_change_threshold: float = Field(
        default=0.1,
        ge=0.0, le=1.0,
        description="权重变化阈值（收敛判断）"
    )

    # 事项过滤
    event_similarity_threshold: float = Field(
        default=0.4,
        ge=0.0, le=1.0,
        description="Step2 事项向量检索的相似度阈值"
    )

    min_events_per_hop: int = Field(
        default=5,
        ge=1, le=100,
        description="每跳最少事项数"
    )

    max_events_per_hop: int = Field(
        default=100,
        ge=1, le=1000,
        description="每跳最多事项数"
    )

    # === 事项截断策略配置 ===
    max_events_per_key: int = Field(
        default=100,
        ge=10, le=5000,
        description="每个key最多关联的事项数量"
    )

    max_recent_events: int = Field(
        default=100,
        ge=100, le=5000,
        description="最新事项数量上限（按创建时间倒序）"
    )

    max_random_events: int = Field(
        default=2000,
        ge=100, le=5000,
        description="从更早事项中随机抽取的数量上限"
    )

    step1_events_limit: int = Field(
        default=5000,
        ge=100, le=20000,
        description="Step1 输出事项总数上限"
    )


class RerankConfig(DataFlowBaseModel):
    """
    事项重排配置

    基于实体列表排序最终事项结果
    """

    # 排序策略
    strategy: RerankStrategy = Field(
        default=RerankStrategy.RRF,
        description="排序策略"
    )

    # 结果控制
    score_threshold: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="相似度阈值（低于此值的事项会被过滤）"
    )

    max_results: int = Field(
        default=50,
        ge=1, le=2000,
        description="最大返回数量（阈值过滤后再截断）"
    )

    # 召回数量控制（分阶段）
    max_key_recall_results: int = Field(
        default=30,
        ge=5, le=200,
        description="Step1 Key召回的最大事项/段落数（按相似度排序截断）"
    )

    max_query_recall_results: int = Field(
        default=30,
        ge=5, le=200,
        description="Step2 Query召回的最大事项/段落数（按相似度排序截断）"
    )

    # 🆕 Rerank向量计算前的事项数量限制（优化性能）
    max_events_for_embedding: int = Field(
        default=10000,
        ge=50, le=50000,
        description="Embedding计算前的最大事项数（超过此数量会基于hop衰减权重预排序截断，设置大值可禁用）"
    )

    pagerank_damping_factor: float = Field(
        default=0.85,
        ge=0.0, le=1.0,
        description="阻尼系数"
    )

    pagerank_max_iterations: int = Field(
        default=100,
        ge=1, le=1000,
        description="最大迭代次数"
    )

    # RRF参数
    rrf_k: int = Field(
        default=60,
        ge=1, le=100,
        description="RRF融合参数K"
    )

    # RRF 4路融合权重参数
    rrf_weight_similarity: float = Field(
        default=1.5,
        ge=0.0, le=10.0,
        description="RRF Similarity维度权重 (w_sim)"
    )

    rrf_weight_relation: float = Field(
        default=0.5,
        ge=0.0, le=10.0,
        description="RRF Relation维度权重 (w_rel)"
    )

    rrf_weight_density: float = Field(
        default=0.2,
        ge=0.0, le=10.0,
        description="RRF Density维度权重 (w_den)"
    )

    rrf_weight_bm25: float = Field(
        default=2.0,
        ge=0.0, le=10.0,
        description="RRF BM25维度权重 (w_bm25)"
    )

    # ✨ 新增：跳过 PageRank 选项
    skip_pagerank: bool = Field(
        default=True,
        description="跳过 PageRank 重排序（True=Step4后直接返回，False=使用PageRank）"
    )


class BM25Config(DataFlowBaseModel):
    """
    BM25 检索器配置

    独立于三阶段搜索，直接使用 Query 检索 Event，
    完全利用 ES 原生 BM25 能力（ES text 字段默认使用 BM25 算法）。

    示例：
        config = BM25Config(
            top_k=20,
            title_weight=3.0,
            content_weight=1.0
        )
    """

    # 返回数量
    top_k: int = Field(
        default=20,
        ge=1, le=1000,
        description="返回的最大事项数量"
    )

    # 字段权重
    title_weight: float = Field(
        default=3.0,
        ge=0.0, le=10.0,
        description="title 字段的搜索权重（ES multi_match 的 boost）"
    )

    content_weight: float = Field(
        default=1.0,
        ge=0.0, le=10.0,
        description="content 字段的搜索权重（ES multi_match 的 boost）"
    )

    # 最低分数阈值（可选）
    min_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="最低 BM25 分数阈值，低于此分数的结果会被过滤（None=不过滤）"
    )


class SearchBaseConfig(DataFlowBaseModel):
    """
    搜索基础配置

    用于引擎层统一配置，包含基础参数 + 算法配置
    """

    # 基础参数（引擎需要）
    query: str = Field(..., description="搜索查询")
    original_query: str = Field(default="", description="原始查询")

    # 功能开关
    enable_query_rewrite: bool = Field(
        default=True,
        description="启用query重写（将口语化表述整理为更适合查询的问题）"
    )

    # 实体类型过滤（Recall 和 Expand 阶段都使用）
    # 注意：当 focus_entity_types 非空时，优先使用白名单；否则使用黑名单
    exclude_entity_types: List[str] = Field(
        default=["start_time", "end_time"],
        description="[黑名单] 需要排除的实体类型（当 focus_entity_types 为空时生效）"
    )

    # 返回类型控制
    return_type: ReturnType = Field(
        default=ReturnType.EVENT,
        description="返回类型：事项(event) 或 段落(paragraph)，默认是事项"
    )

    # 三阶段配置
    recall: RecallConfig = Field(
        default_factory=RecallConfig, description="召回配置")
    expand: ExpandConfig = Field(
        default_factory=ExpandConfig, description="扩展配置")
    rerank: RerankConfig = Field(
        default_factory=RerankConfig, description="重排配置")


class SearchConfig(SearchBaseConfig):
    """
    搜索完整配置（基础配置 + 运行时上下文）

    继承SearchBaseConfig，添加运行时必需的上下文信息

    示例：
        # 单源搜索（向后兼容）
        config = SearchConfig(
            query="人工智能",
            source_config_id="source_123",
            recall=RecallConfig(max_entities=30),
            expand=ExpandConfig(max_hops=3),
            rerank=RerankConfig(strategy=RerankStrategy.PAGERANK)
        )

        # 多源搜索（新增功能）
        config = SearchConfig(
            query="人工智能",
            source_config_ids=["source_001", "source_002", "source_003"],
            recall=RecallConfig(max_entities=30),
            expand=ExpandConfig(max_hops=3),
            rerank=RerankConfig(strategy=RerankStrategy.PAGERANK)
        )
    """

    # === 运行时上下文 ===
    source_config_id: Optional[str] = Field(None, description="数据源ID（单个，向后兼容）")
    source_config_ids: Optional[List[str]] = Field(
        None, description="数据源ID列表（支持多源搜索）")
    article_id: Optional[str] = Field(None, description="文章ID")
    background: Optional[str] = Field(None, description="背景信息")

    def model_post_init(self, __context):
        """初始化后验证和处理 source_config_id/source_config_ids"""
        # 验证：至少提供一个
        if not self.source_config_id and not self.source_config_ids:
            raise ValueError("必须提供 source_config_id 或 source_config_ids 参数")

        # 统一处理：如果只提供 source_config_id，转换为 source_config_ids
        if self.source_config_id and not self.source_config_ids:
            self.source_config_ids = [self.source_config_id]
        elif self.source_config_ids and not self.source_config_id:
            # 多源场景，source_config_id 设为第一个（向后兼容）
            self.source_config_id = self.source_config_ids[0]

    def get_source_config_ids(self) -> List[str]:
        """
        获取统一的 source_config_ids 列表

        Returns:
            source_config_ids 列表（至少包含一个元素）
        """
        return self.source_config_ids or []

    def is_multi_source(self) -> bool:
        """
        判断是否为多源搜索

        Returns:
            True 表示多源搜索，False 表示单源搜索
        """
        return len(self.get_source_config_ids()) > 1

    # 运行时缓存
    query_embedding: Optional[List[float]] = Field(None, description="查询向量缓存")
    has_query_embedding: bool = Field(False, description="是否已生成查询向量")

    # Query召回的实体缓存
    query_recalled_keys: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Query召回的所有实体（用于构建线索）"
    )

    # === 线索追踪 (统一管理) ===
    all_clues: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="所有线索（统一追踪，支持知识图谱构建）"
    )

    # 旧版线索字段（兼容性保留，逐步废弃）
    recall_clues: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="召回线索（已废弃，使用all_clues）"
    )

    expansion_clues: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="扩展线索（已废弃，使用all_clues）"
    )

    rerank_clues: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="重排线索（已废弃，使用all_clues）"
    )

    # 节点缓存
    entity_node_cache: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="实体节点缓存"
    )

    # event到entity的映射缓存
    event_entities_cache: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="event到entity的映射缓存（event_id -> list of entity_ids）"
    )

    # 分词召回实体ID集合（用于动态加权）
    tokenizer_entity_ids: Set[str] = Field(
        default_factory=set,
        description="分词召回的实体ID集合，避免重复记分并支持后续加权"
    )

    # 新策略：高质量事项ID集合（步骤1直接召回的高阈值events）
    high_quality_event_ids: Set[str] = Field(
        default_factory=set,
        description="新召回策略步骤1召回的高质量事项ID（高阈值），用于后续并集合并"
    )

    # 新策略：背景实体列表（从高质量事项反向召回，按热度排序）
    background_entities: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="背景实体列表（来自高质量事项，按热度排序，用于LLM参考和兜底）"
    )

    # === 🆕 聚焦实体类型（LLM动态识别的白名单） ===
    focus_entity_types: List[str] = Field(
        default_factory=list,
        description="[白名单] LLM识别的与查询相关的实体类型（非空时优先使用，空=使用exclude黑名单）"
    )

    # === 🆕 目标实体类型（用于Rerank阶段加权） ===
    target_entity_types: List[str] = Field(
        default_factory=list,
        description="[目标维度] LLM识别的答案相关实体类型，多跳扩展时匹配这些类型的实体会获得加权"
    )

    # === BM25搜索配置 ===
    bm25_enabled: bool = Field(
        default=True,
        description="是否启用BM25搜索作为独立的召回通道"
    )

    bm25_top_k: int = Field(
        default=20,
        ge=1, le=100,
        description="BM25搜索返回的最大事项数量"
    )

    bm25_title_weight: float = Field(
        default=3.0,
        ge=0.0, le=10.0,
        description="BM25搜索中title字段的权重"
    )

    bm25_content_weight: float = Field(
        default=1.0,
        ge=0.0, le=10.0,
        description="BM25搜索中content字段的权重"
    )


__all__ = [
    # 配置
    "SearchConfig",
    "SearchBaseConfig",
    "RecallConfig",
    "ExpandConfig",
    "RerankConfig",
    "BM25Config",
    "RerankStrategy",
    "ReturnType",
    "RecallMode",
]
