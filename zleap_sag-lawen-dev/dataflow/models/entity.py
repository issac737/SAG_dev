"""
Entity Data Models
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator

from dataflow.models.base import DataFlowBaseModel, MetadataMixin, TimestampMixin


class EntityType(DataFlowBaseModel, MetadataMixin, TimestampMixin):
    """Entity type definition model"""

    id: str = Field(..., description="Entity type ID (UUID)")
    scope: str = Field(
        default="global", description="Scope: global/source/article")
    source_config_id: Optional[str] = Field(
        default=None, description="Source config ID (NULL for system default)")
    article_id: Optional[str] = Field(
        default=None, description="Article ID (only when scope=article)")
    type: str = Field(..., min_length=1, max_length=50, description="Type identifier")
    name: str = Field(..., min_length=1, max_length=100, description="Type name")
    is_default: bool = Field(default=False, description="Is system default type")
    description: Optional[str] = Field(default=None, description="Type description")
    weight: float = Field(default=1.0, ge=0.0, le=9.99, description="Default weight")
    similarity_threshold: float = Field(
        default=0.80, ge=0.0, le=1.0, description="Entity similarity threshold (0.000-1.000)"
    )
    is_active: bool = Field(default=True, description="Is active")
    value_format: Optional[str] = Field(
        default=None, description="Value format template (e.g. {number}{unit})")
    value_constraints: Optional[Dict[str, Any]] = Field(
        default=None, description="Value constraints (e.g. enum list, number range)")

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        """Validate weight range"""
        return round(v, 2)

    @field_validator("similarity_threshold")
    @classmethod
    def validate_similarity_threshold(cls, v: float) -> float:
        """Validate similarity threshold and keep 3 decimal places"""
        return round(v, 3)


class Entity(DataFlowBaseModel, MetadataMixin, TimestampMixin):
    """Entity model (many-to-many: linked to events via event_entity)"""

    id: str = Field(..., description="Entity ID (UUID)")
    source_config_id: str = Field(..., description="Source config ID")
    entity_type_id: str = Field(..., description="Entity type ID (references entity_type.id)")
    type: str = Field(
        ..., min_length=1, max_length=50, description="Entity type identifier (redundant field for query)"
    )
    name: str = Field(..., min_length=1, max_length=500, description="Entity name")
    normalized_name: str = Field(..., min_length=1,
                                 max_length=500, description="Normalized name")
    description: Optional[str] = Field(default=None, description="Entity description")

    # ========== Typed value fields (for statistical analysis) ==========
    value_type: Optional[str] = Field(
        default=None, description="Value type (int/float/datetime/bool/enum/text)")
    value_raw: Optional[str] = Field(
        default=None, description="Raw extracted text (e.g. '$199')")
    int_value: Optional[int] = Field(default=None, description="Integer value")
    float_value: Optional[Decimal] = Field(default=None, description="Float value")
    datetime_value: Optional[datetime] = Field(
        default=None, description="Datetime value")
    bool_value: Optional[bool] = Field(default=None, description="Boolean value")
    enum_value: Optional[str] = Field(default=None, description="Enum value")
    value_unit: Optional[str] = Field(
        default=None, description="Unit (e.g. 'USD', 'kg')")
    value_confidence: Optional[Decimal] = Field(
        default=None, ge=0.0, le=1.0, description="Parsing confidence")

    def get_typed_value(self) -> Any:
        """Get typed value based on value_type"""
        if self.value_type == "int":
            return self.int_value
        elif self.value_type == "float":
            return self.float_value
        elif self.value_type == "datetime":
            return self.datetime_value
        elif self.value_type == "bool":
            return self.bool_value
        elif self.value_type == "enum":
            return self.enum_value
        return None

    def get_synonyms(self) -> List[str]:
        """Get synonyms"""
        if self.extra_data and "synonyms" in self.extra_data:
            return self.extra_data["synonyms"]
        return []

    def get_weight(self) -> float:
        """Get weight"""
        if self.extra_data and "weight" in self.extra_data:
            return self.extra_data["weight"]
        return 1.0

    def get_confidence(self) -> float:
        """Get confidence"""
        if self.extra_data and "confidence" in self.extra_data:
            return self.extra_data["confidence"]
        return 1.0


class EventEntity(DataFlowBaseModel, MetadataMixin, TimestampMixin):
    """Event-Entity association model (many-to-many)"""

    id: str = Field(..., description="Association ID (UUID)")
    event_id: str = Field(..., description="Event ID")
    entity_id: str = Field(..., description="Entity ID")
    weight: float = Field(default=1.0, ge=0.0, le=9.99,
                          description="Entity weight in this event")

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        """Validate weight range"""
        return round(v, 2)

    def get_confidence(self) -> float:
        """Get confidence"""
        if self.extra_data and "confidence" in self.extra_data:
            return self.extra_data["confidence"]
        return 1.0

    def get_context(self) -> Optional[str]:
        """Get context"""
        if self.extra_data and "context" in self.extra_data:
            return self.extra_data["context"]
        return None


class EntityWithWeight(DataFlowBaseModel):
    """Entity with weight (for event query results)"""

    entity: Entity
    weight: float = Field(default=1.0, ge=0.0, le=9.99,
                          description="Entity weight in event")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence")


class CustomEntityType(DataFlowBaseModel):
    """Custom entity type definition"""

    type: str = Field(..., description="Type identifier")
    name: str = Field(..., description="Type name")
    description: str = Field(..., description="Type description for LLM extraction")
    weight: float = Field(default=1.0, ge=0.0, le=9.99, description="Default weight")
    extraction_prompt: Optional[str] = Field(
        default=None, description="Custom extraction prompt template")
    extraction_examples: Optional[List[Dict[str, str]]] = Field(
        default=None, description="Few-shot examples"
    )
    validation_rule: Optional[Dict[str, Any]] = Field(
        default=None, description="Validation rule")
    metadata_schema: Optional[Dict[str, Any]] = Field(
        default=None, description="Metadata schema")


# ==============================================================================
# 默认实体类型定义 (基于5W1H框架)
# ==============================================================================
# 
# 设计原则:
# 1. 本体论类型 - 实体"是什么"，而非"用来做什么"
# 2. 互斥性 - 每个实体只属于一个类型
# 3. 完备性 - 覆盖所有可能的实体类型
# 4. 搜索导向 - 支持LLM识别"线索维度"和"目标维度"
#
# 权重说明 (按搜索重要性分层):
# - 高权重 (1.2~1.5): topic(1.5), action(1.3), metric(1.2), person(1.2)
# - 中权重 (1.0~1.1): organization(1.1), product(1.1), group/work/event/time/location(1.0)
# - 兜底 (0.5): tags - 避免滥用
#
# 总计: 12个类型，覆盖95%+问答场景
# - 主体(WHO): person, organization, group
# - 客体(WHAT): product, work, event
# - 概念(ABOUT): topic, action
# - 度量(HOW MUCH): metric
# - 时空: time, location
# - 兜底: tags
#
# ==============================================================================

DEFAULT_ENTITY_TYPES = [
    # ==========================================================================
    # 【WHEN - 时间维度】
    # ==========================================================================
    EntityType(
        id="20000000-0000-0000-0000-000000000001",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="time",
        name="时间",
        is_default=True,
        description="""【When - 时间】事件发生的时间点、时间范围或时间周期。
        包含: 具体日期(2024年1月1日)、时间范围(上半年)、时间周期(每周一)、节假日(春节/圣诞节)、季节(冬天)、年代(90年代)。
        示例: '2024年Q1', '去年夏天', '国庆节期间', '每月15号', '疫情前'。
        边界: 节日名称(如"春节")归入此类，节日活动(如"春节晚会")归入event。""",
        weight=1.0,
        similarity_threshold=0.900,
    ),
    
    # ==========================================================================
    # 【WHERE - 空间维度】
    # ==========================================================================
    EntityType(
        id="20000000-0000-0000-0000-000000000002",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="location",
        name="地点",
        is_default=True,
        description="""【Where - 地点】地理位置、行政区划、物理空间。
        包含: 国家(中国)、城市(北京)、区域(长三角)、地标建筑(故宫/埃菲尔铁塔)、场馆(鸟巢体育场)、机场(浦东机场)。
        示例: '硅谷', '东南亚市场', '中关村', '大湾区', '三里屯'。
        边界: 强调"是哪里"而非"来自哪里"(后者用origin)。建筑物、地标都归入此类。""",
        weight=1.0,
        similarity_threshold=0.750,
    ),
    
    # ==========================================================================
    # 【WHO - 主体维度】
    # ==========================================================================
    EntityType(
        id="20000000-0000-0000-0000-000000000003",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="person",
        name="人物",
        is_default=True,
        description="""【Who - 人物】具体的自然人，无论真实或虚构。
        包含: 真实姓名(马斯克)、艺名(周杰伦)、笔名(鲁迅)、历史人物(诸葛亮)、虚构角色(哈利波特)。
        示例: 'Tim Cook', '李白', '钢铁侠', '乔峰'。
        边界: 必须是"某个具体的人"，而非职业(用profession)或角色类型(用group)。""",
        weight=1.2,
        similarity_threshold=0.950,
    ),
    EntityType(
        id="20000000-0000-0000-0000-000000000008",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="organization",
        name="组织",
        is_default=True,
        description="""【Who - 组织】有明确名称和边界的正式机构或团体。
        包含: 公司(苹果公司)、政府机构(工信部)、学校(清华大学)、NGO(红十字会)、乐队(五月天)、球队(曼联)。
        示例: 'Google', '世卫组织', '腾讯', '北约', '皇家马德里'。
        边界: 必须是"某个具体组织"，有正式名称。泛指的"企业"、"政府"归入group。""",
        weight=1.1,
        similarity_threshold=0.850,
    ),
    EntityType(
        id="20000000-0000-0000-0000-000000000009",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="group",
        name="群体",
        is_default=True,
        description="""【Who - 群体】具有共同特征的人群类别或抽象集合。
        包含: 年龄群体(Z世代/老年人)、职业群体(程序员/医生群体)、消费群体(中产阶级)、社会身份(留学生)。
        示例: '00后', '高净值人群', '新中产', '数字原住民', '职场新人'。
        边界: 强调"一类人"而非"某个人"(用person)或"某个组织"(用organization)。""",
        weight=1.0,
        similarity_threshold=0.700,
    ),
    
    # ==========================================================================
    # 【WHAT - 内容维度】(核心搜索维度)
    # ==========================================================================
    EntityType(
        id="20000000-0000-0000-0000-000000000005",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="topic",
        name="主题",
        is_default=True,
        description="""【What - 主题】被讨论的核心话题、概念、领域或现象。
        包含: 抽象概念(人工智能)、专业领域(机器学习)、社会现象(内卷)、健康话题(睡眠质量)、商业概念(私域流量)。
        示例: '碳中和', '元宇宙', '新能源', '心理健康', '消费升级', '慢性病预防'。
        边界: 这是最重要的搜索维度，优先归类。不是具体的人/组织/产品/作品，而是"讨论什么"。""",
        weight=1.5,
        similarity_threshold=0.600,
    ),
    EntityType(
        id="20000000-0000-0000-0000-000000000027",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="work",
        name="作品",
        is_default=True,
        description="""【What - 作品】人类创作的智力成果、文化产品。
        包含: 书籍(《三体》)、电影(《阿凡达》)、音乐(《稻香》)、软件(Photoshop)、论文、报告。
        示例: '《红楼梦》', 'ChatGPT', '《财富》杂志', '《经济学人》'。
        边界: 必须有明确的"作品名"。与topic区分：topic是"讨论什么"，work是"哪个作品"。""",
        weight=1.0,
        similarity_threshold=0.850,
    ),
    EntityType(
        id="20000000-0000-0000-0000-000000000028",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="product",
        name="产品",
        is_default=True,
        description="""【What - 产品/服务】可购买、使用的商品或服务。
        包含: 硬件产品(iPhone 15)、软件产品(微信)、服务(京东物流)、品牌(耐克)、金融产品(余额宝)。
        示例: 'Model 3', '支付宝', 'Prime会员', '星巴克拿铁', 'AWS云服务'。
        边界: 强调"可消费/可购买"。与work区分：软件既可以是作品也可以是产品，根据语境判断。""",
        weight=1.1,
        similarity_threshold=0.800,
    ),
    EntityType(
        id="20000000-0000-0000-0000-000000000016",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="event",
        name="事件",
        is_default=True,
        description="""【What - 事件】在特定时空发生的具名活动或事件。
        包含: 会议(G20峰会)、展会(CES展)、比赛(世界杯)、活动(双11)、历史事件(工业革命)、突发事件(新冠疫情)。
        示例: '春节晚会', '奥运会', '618大促', '巴黎气候协定签署', '发布会'。
        边界: 强调"发生了什么事"，有时间性。与topic区分：topic是持续讨论的话题，event是特定时间发生的事件。""",
        weight=1.0,
        similarity_threshold=0.850,
    ),
    
    # ==========================================================================
    # 【HOW - 方式维度】
    # ==========================================================================
    EntityType(
        id="20000000-0000-0000-0000-000000000004",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="action",
        name="行为",
        is_default=True,
        description="""【How - 行为】主体执行的动作、操作或方法。
        包含: 业务动作(签约/发布)、用户行为(点击/购买)、方法策略(A/B测试)、流程步骤(审核/验证)。
        示例: '数字化转型', '品牌升级', '降本增效', '用户增长', '预防措施', '健康管理'。
        边界: 强调"怎么做"、"做了什么动作"。通常带有动词性质。""",
        weight=1.3,
        similarity_threshold=0.800,
    ),
    EntityType(
        id="20000000-0000-0000-0000-000000000022",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="metric",
        name="指标",
        is_default=True,
        description="""【How - 指标】可量化的度量、数值或评价标准。
        包含: 业务指标(GMV/DAU/转化率)、财务数据(营收100亿)、评分(4.8分)、排名(第一名)、成就(诺贝尔奖)。
        示例: 'ROI 200%', 'NPS得分', '月活1亿', '增长率30%', '金牌', '最佳导演奖'。
        边界: 强调"多少"、"什么水平"。必须是可量化或可评级的。""",
        weight=1.2,
        similarity_threshold=0.800,
    ),
    
    # ==========================================================================
    # 【兜底维度】
    # ==========================================================================
    EntityType(
        id="20000000-0000-0000-0000-000000000007",
        scope="global",
        source_config_id=None,
        article_id=None,
        type="tags",
        name="标签",
        is_default=True,
        description="""【Other - 其他】无法归入以上任何类型的实体。
        使用场景: 只有当实体确实不属于上述任何类型时才使用。
        警告: 这是最后的选择！优先考虑其他更具体的类型。
        边界: 
        - 人名 → person
        - 组织名 → organization  
        - 人群 → group
        - 地点/建筑 → location
        - 话题/概念 → topic
        - 作品 → work
        - 产品/服务 → product
        - 事件/活动 → event
        - 动作/方法 → action
        - 数值/指标 → metric""",
        weight=0.5,
        similarity_threshold=0.700,
    ),
]
