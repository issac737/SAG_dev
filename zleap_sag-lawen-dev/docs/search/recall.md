# Search Recall 使用指南

## 概述

RecallSearcher 实现了一个8步骤的复合搜索算法，结合了语义扩展、精准匹配和权重计算，用于从查询中提取重要的结构化属性。

## 算法流程

1. **query找key（语义扩展）**: LLM抽取query的结构化属性，通过向量相似度找到关联实体
2. **key找event（精准匹配）**: 通过[key-query-related]用sql找到所有关联事项
3. **query再找event（语义匹配）**: 通过向量相似度在找到query关联事项
4. **过滤Event（精准筛选）**: [Event-query-related]和[Event-key-query-related]取交集
5. **计算event-key权重向量**: 根据每个event包含key的情况计算权重
6. **计算event-key-query权重向量**: 将(event-key)*(e1)得到新的权重向量
7. **反向计算key权重向量**: 根据event权重反向计算key重要性
8. **提取重要的key**: 通过阈值或top-n方式提取重要key

## 使用示例

```python
from dataflow.modules.search import RecallSearcher, SearchConfig
from dataflow.core.ai.base import BaseLLMClient
from dataflow.core.prompt.manager import PromptManager

# 初始化
llm_client = BaseLLMClient()  # 根据具体实现
prompt_manager = PromptManager()  # 根据具体实现
searcher = RecallSearcher(llm_client, prompt_manager)

# 配置搜索参数
config = SearchConfig(
    source_config_id="your_source_config_id",  # 必需：指定要搜索的数据源ID
    query="AI技术在医疗领域的应用",  # 必需：搜索查询内容
    key_similarity_threshold=0.7,
    event_similarity_threshold=0.6,
    max_keys=20,
    max_events=50,
    final_key_threshold=0.5,
    top_n_keys=10,  # 或者使用final_key_threshold
)

# 执行搜索
result = await searcher.search(config)

# 查看结果
print(f"找到 {len(result.key_final)} 个重要key:")
for key_info in result.key_final:
    print(f"- {key_info['name']} ({key_info['type']}): {key_info['weight']:.3f}")

# 查看中间结果（调试用）
print(f"步骤1 - 找到 {len(result.key_query_related)} 个相关key")
print(f"步骤2 - 找到 {len(result.event_key_query_related)} 个key相关event")
print(f"步骤3 - 找到 {len(result.event_query_related)} 个query相关event")
print(f"步骤4 - 过滤后 {len(result.event_related)} 个event")
```

## 配置参数

### SearchConfig 参数

- `source_config_id`: **信息源ID (必需)** - 指定搜索的数据源范围
- `query`: 查询文本 (必需) - 要搜索的目标内容
- `key_similarity_threshold`: Key语义相似度阈值 (默认: 0.7) - **全局最低要求**
- `event_similarity_threshold`: Event语义相似度阈值 (默认: 0.6)
- `max_keys`: 最大Key数量 (默认: 20)
- `max_events`: 最大Event数量 (默认: 50)
- `final_key_threshold`: 最终Key权重阈值 (默认: 0.5)
- `top_n_keys`: 返回Top-N重要Key (可选，默认: 10)
- `vector_k`: 向量搜索返回数量 (默认: 10)
- `vector_num_candidates`: 向量搜索候选数量 (默认: 100)

### 动态相似度阈值机制

**步骤1中的相似度判断使用动态阈值策略**：

1. **配置阈值** (`config.key_similarity_threshold`) - 全局最低要求
2. **实体类型阈值** (`entity_type.similarity_threshold`) - 数据库中每个实体类型的特定阈值
3. **最终阈值** - 使用 `max(配置阈值, 类型阈值)` 作为判断标准

**示例**：
```python
# 配置：key_similarity_threshold = 0.7
# 实体类型：
#   - PERSON: similarity_threshold = 0.85
#   - TOPIC:  similarity_threshold = 0.75
#   - ORG:    similarity_threshold = 0.70

# 最终判断阈值：
#   - PERSON: max(0.7, 0.85) = 0.85  # 人物实体要求更高精度
#   - TOPIC:  max(0.7, 0.75) = 0.75  # 主题实体适中要求
#   - ORG:    max(0.7, 0.70) = 0.70  # 组织实体使用配置值
```

这种机制允许为不同类型的实体设置不同的相似度要求，同时保持全局配置作为安全网。

## 日志记录和调试

RecallSearcher 提供了详细的日志记录功能，便于调试和监控搜索过程：

### 日志级别
- **INFO**: 关键步骤的汇总信息
  - 每个步骤的开始和完成状态
  - 搜索结果的统计信息
  - Top 相似实体展示

- **DEBUG**: 详细的调试信息
  - 每个属性的搜索过程
  - 实体的阈值检查详情
  - 相似度计算过程

### 示例日志输出
```
INFO  - 步骤1开始: query='AI技术在医疗领域的应用', key_similarity_threshold=0.7, max_keys=20
INFO  - 抽取到 3 个属性: ['AI', '科技', '医疗']
DEBUG - 搜索属性: AI (类型: topic)
DEBUG - 属性 'AI' 搜索到 10 个候选实体
DEBUG - 实体 '人工智能技术' 通过阈值检查: similarity=0.892, type_threshold=0.800, config_threshold=0.700, final_threshold=0.800
DEBUG - 属性 'AI' 通过阈值: 7/10
INFO  - 步骤1完成: 总搜索=30, 通过阈值=22, 去重后=18, 限制max_keys=20
INFO  - Top 3 相似实体: '人工智能技术'(topic, 0.892), 'AI医疗应用'(topic, 0.876), '科技创新'(topic, 0.854)
```

## 数据结构

### RecallResult

```python
@dataclass
class RecallResult:
    # 最终结果
    key_final: List[Dict[str, Any]]  # [{"key_id": str, "name": str, "type": str, "weight": float, "steps": List[int]}, ...]

    # 中间结果（用于调试）
    key_query_related: List[Dict[str, Any]]      # 步骤1结果
    event_key_query_related: List[str]           # 步骤2结果
    event_query_related: List[Dict[str, Any]]    # 步骤3结果
    event_related: List[str]                     # 步骤4结果
    key_related: List[str]                       # 步骤4结果
    event_key_weights: Dict[str, float]          # 步骤5结果
    event_key_query_weights: Dict[str, float]    # 步骤6结果
    key_event_weights: Dict[str, float]          # 步骤7结果
```

## 注意事项

1. **向量搜索**: 需要预先为实体和事件建立向量索引
2. **LLM集成**: 步骤1中使用LLM抽取query的结构化属性，需要配置相应的提示词模板
3. **数据库关联**: 需要确保数据库中的event_entity关联关系正确
4. **性能考虑**: 8步骤算法相对复杂，建议对大型数据集进行性能优化
5. **属性抽取**: LLM属性抽取包含回退机制，在LLM调用失败时会使用基于规则的抽取方案

## 权重计算公式

- **步骤5**: `W_event-key(ej) = Σ(k1)i` (k_i ∈ e_j)
- **步骤6**: `W_e2(ej) = W_event-key(ej) × (e1)j`
- **步骤7**: `W_key-event(ki) = Σ W_e2(ej)` (e_j contains k_i)