# DataFlow 核心算法设计文档

**神经网络式搜索引擎 - 激活传播算法**

*by Zleap Team（智跃团队）*

## 目录

- [1. 概览](#1-概览)
- [2. 数据模型](#2-数据模型)
- [3. 数据处理流程](#3-数据处理流程)
- [4. 神经网络式检索机制](#4-神经网络式检索机制)
- [5. 线索激活与传播](#5-线索激活与传播)
- [6. 缓存区与权重计算](#6-缓存区与权重计算)
- [7. 原文块召回与补全](#7-原文块召回与补全)
- [8. 完整检索流程](#8-完整检索流程)

---

## 1. 概览

### 1.1 核心思想

DataFlow 采用 **神经网络式激活传播** 的检索策略，与传统 GraphRAG 的本质区别：

| 维度 | GraphRAG | DataFlow |
|------|----------|-------------|
| **核心比喻** | 预构建知识图谱 | 神经网络激活传播 |
| **基本单元** | 节点+边 | 神经元(事项)+突触(实体) |
| **关系构建** | 预先构建静态边 | 检索时动态激活连接 |
| **传播机制** | 图遍历 | 多线索并行激活传播 |
| **维护成本** | 高（维护图结构） | 低（无预构建） |
| **扩展性** | 固定图结构 | 动态适配查询 |

### 1.2 神经网络类比

```
传统神经网络              DataFlow搜索引擎
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
神经元 (Neuron)     →    事项 (SourceEvent)
突触 (Synapse)      →    实体 (Entity)
激活 (Activation)   →    召回 (Recall)
权重 (Weight)       →    相关度评分 (Score)
层传播 (Layer)      →    多跳扩展 (Hop)
缓存区 (Cache)      →    激活缓存区 (ActiveCache)
```

### 1.3 算法流程概览

```
用户查询 "三国里刘备跟曹操的几大战役"
    ↓
【1】LLM识别检索意图
    ↓ 激活初始实体
    [PERSON: 刘备, 曹操]
    [TOPIC: 战役, 三国]
    [TAG: 军事对抗]
    ↓
【2】多线索并行激活
    线索1: PERSON=刘备 → 召回事项 → 扩展实体(topic: 蜀汉, location: 益州)
    线索2: PERSON=曹操 → 召回事项 → 扩展实体(topic: 曹魏, location: 许昌)
    线索3: TOPIC=战役 → 召回事项 → 扩展实体(action: 对战, time: 公元200年)
    ↓
【3】激活传播（多跳扩展）
    跳1: 基础事项 → 关联实体
    跳2: 扩展事项 → 交叉实体
    跳3: 深度事项 → 汇聚分析
    ↓
【4】缓存区聚合
    激活的实体: [刘备, 曹操, 官渡, 赤壁, 汉中, ...]
    召回的事项: [官渡之战, 赤壁之战, 汉中之战, ...]
    ↓
【5】权重评分
    实体交叉度 × 事项重叠度 → 最终排序
    ↓
【6】原文块召回
    根据事项溯源原文块
    ↓
【7】原文块补全
    片段1、3存在 → 自动补全片段2
    ↓
【8】LLM生成答案
    基于完整知识版本总结
```

---

## 2. 数据模型

### 2.1 三层数据结构

DataFlow 的数据模型分为三层：**原文块 → 事项 → 实体**

```
原文块 (ArticleChunk)
    ↓ LLM提取
事项 (SourceEvent)
    ↓ LLM提取
实体 (Entity)
```

### 2.2 原文块 (ArticleChunk)

**定义**：文档按分段切割后的最小文本单元

**结构**：

```python
class ArticleChunk:
    """
    原文块 - 文档的最小存储单元
    """
    id: str                    # 唯一ID
    source_config_id: str             # 来源ID（用户/信息源）
    article_id: str            # 所属文章ID
    
    # 内容
    title: str                 # 块标题（如 Markdown 的 ## 标题）
    content: str               # 块正文
    
    # 位置信息
    chunk_index: int           # 在文章中的序号（从0开始）
    start_line: int            # 起始行号
    end_line: int              # 结束行号
    
    # 向量
    content_vector: List[float]  # 内容向量（用于语义检索）
    
    # 元数据
    created_time: datetime
    updated_time: datetime
```

**示例**：

```markdown
## 官渡之战                     ← title = "官渡之战"
                                  chunk_index = 5
公元200年，曹操与袁绍在官渡      ← content = "公元200年，曹操与..."
展开决战，曹操以少胜多...
```

### 2.3 事项 (SourceEvent)

**定义**：从原文块中提取的结构化信息单元，相当于 **神经元**

**结构**：

```python
class SourceEvent:
    """
    事项 - 神经网络的神经元
    
    事项是信息的核心单元，通过实体（突触）与其他事项连接
    """
    id: str                    # 唯一ID
    source_config_id: str             # 来源ID
    chunk_id: str              # 来源原文块ID
    article_id: str            # 来源文章ID
    
    # 内容
    title: str                 # 事项标题
    content: str               # 事项内容
    
    # 向量
    content_vector: List[float]  # 内容向量
    
    # 关联实体（突触）
    entities: List[Entity]     # 关联的实体列表
    
    # 元数据
    created_time: datetime
    updated_time: datetime
```

**示例**：

```python
SourceEvent(
    id="evt_001",
    title="官渡之战",
    content="公元200年，曹操与袁绍在官渡展开决战，曹操以少胜多，奠定了统一北方的基础",
    chunk_id="chunk_005",
    entities=[
        Entity(type="PERSON", name="曹操"),
        Entity(type="PERSON", name="袁绍"),
        Entity(type="LOCATION", name="官渡"),
        Entity(type="TIME", name="公元200年"),
        Entity(type="TOPIC", name="战役"),
        Entity(type="ACTION", name="决战"),
        Entity(type="TAG", name="三国")
    ]
)
```

### 2.4 实体 (Entity)

**定义**：事项的属性维度，相当于 **突触**

**5种实体类型**：

```python
class EntityType(Enum):
    """
    实体类型 - 神经网络的突触类型
    """
    TIME = "time"              # 时间：公元200年、建安五年
    LOCATION = "location"      # 地点：官渡、许昌、益州
    PERSON = "person"          # 人物：曹操、刘备、诸葛亮
    TOPIC = "topic"            # 主题：战役、政治、经济
    ACTION = "action"          # 行为：决战、撤退、结盟
    TAG = "tag"                # 标签：三国、军事、历史
```

**结构**：

```python
class Entity:
    """
    实体 - 神经网络的突触
    
    实体是事项之间的连接通道，同一实体可以激活多个事项
    """
    id: str                    # 唯一ID
    type: EntityType           # 实体类型
    name: str                  # 实体名称（原始）
    normalized_name: str       # 标准化名称
    
    # 向量（用于相似度计算）
    entity_vector: List[float]
    
    # 统计
    event_count: int           # 关联的事项数量
    
    # 元数据
    created_time: datetime
```

### 2.5 存储策略

**MySQL**：关系数据、精确查询

```sql
-- 原文块表
CREATE TABLE article_chunk (
    id VARCHAR(36) PRIMARY KEY,
    source_config_id VARCHAR(36),
    article_id VARCHAR(36),
    title TEXT,
    content TEXT,
    chunk_index INT,
    start_line INT,
    end_line INT,
    created_time DATETIME,
    INDEX idx_source_chunk (source_config_id, chunk_index),
    INDEX idx_article_chunk (article_id, chunk_index)
);

-- 事项表
CREATE TABLE source_event (
    id VARCHAR(36) PRIMARY KEY,
    source_config_id VARCHAR(36),
    chunk_id VARCHAR(36),
    article_id VARCHAR(36),
    title TEXT,
    content TEXT,
    created_time DATETIME,
    INDEX idx_source (source_config_id),
    INDEX idx_chunk (chunk_id)
);

-- 实体表
CREATE TABLE entity (
    id VARCHAR(36) PRIMARY KEY,
    type VARCHAR(20),
    name VARCHAR(255),
    normalized_name VARCHAR(255),
    event_count INT DEFAULT 0,
    created_time DATETIME,
    INDEX idx_type_name (type, normalized_name)
);

-- 事项-实体关联表
CREATE TABLE event_entity (
    event_id VARCHAR(36),
    entity_id VARCHAR(36),
    PRIMARY KEY (event_id, entity_id),
    INDEX idx_entity (entity_id)
);
```

**Elasticsearch**：向量检索、语义搜索

```json
{
  "mappings": {
    "article_chunk": {
      "properties": {
        "id": { "type": "keyword" },
        "source_config_id": { "type": "keyword" },
        "title": { "type": "text" },
        "content": { "type": "text" },
        "content_vector": { "type": "dense_vector", "dims": 1536 }
      }
    },
    "source_event": {
      "properties": {
        "id": { "type": "keyword" },
        "source_config_id": { "type": "keyword" },
        "title": { "type": "text" },
        "content": { "type": "text" },
        "content_vector": { "type": "dense_vector", "dims": 1536 },
        "entities": {
          "type": "nested",
          "properties": {
            "type": { "type": "keyword" },
            "name": { "type": "keyword" }
          }
        }
      }
    }
  }
}
```

---

## 3. 数据处理流程

### 3.1 整体流程

```
Markdown文档
    ↓
【1】文档分块
    ↓
原文块列表 (ArticleChunk)
    ↓
【2】LLM提取事项
    ↓
事项列表 (SourceEvent)
    ↓
【3】LLM提取实体
    ↓
实体列表 (Entity)
    ↓
【4】存储到MySQL + Elasticsearch
```

### 3.2 文档分块算法

**目标**：将 Markdown 文档按语义段落切分

**策略**：基于标题层级切分

```python
def chunk_markdown_document(
    document: str,
    max_chunk_size: int = 1000
) -> List[ArticleChunk]:
    """
    Markdown 文档分块
    
    规则：
    1. 按 Markdown 标题（##）切分
    2. 如果块过大，按段落再切分
    3. 保留标题作为块的 title
    4. 记录块的位置信息（chunk_index, start_line, end_line）
    """
    chunks = []
    lines = document.split('\n')
    current_chunk = []
    current_title = ""
    current_start_line = 0
    chunk_index = 0
    
    for i, line in enumerate(lines):
        # 检测标题
        if line.startswith('##'):
            # 保存前一个块
            if current_chunk:
                chunks.append(ArticleChunk(
                    id=f"chunk_{chunk_index}",
                    title=current_title,
                    content='\n'.join(current_chunk),
                    chunk_index=chunk_index,
                    start_line=current_start_line,
                    end_line=i - 1
                ))
                chunk_index += 1
            
            # 开始新块
            current_title = line.replace('##', '').strip()
            current_chunk = []
            current_start_line = i
        else:
            current_chunk.append(line)
        
        # 如果块过大，强制切分
        if len('\n'.join(current_chunk)) > max_chunk_size:
            chunks.append(ArticleChunk(
                id=f"chunk_{chunk_index}",
                title=current_title,
                content='\n'.join(current_chunk),
                chunk_index=chunk_index,
                start_line=current_start_line,
                end_line=i
            ))
            chunk_index += 1
            current_chunk = []
            current_start_line = i + 1
    
    # 保存最后一个块
    if current_chunk:
        chunks.append(ArticleChunk(
            id=f"chunk_{chunk_index}",
            title=current_title,
            content='\n'.join(current_chunk),
            chunk_index=chunk_index,
            start_line=current_start_line,
            end_line=len(lines) - 1
        ))
    
    return chunks
```

**示例**：

```markdown
输入文档：
## 官渡之战
公元200年，曹操与袁绍在官渡展开决战...

## 赤壁之战
公元208年，曹操率军南下，孙刘联军在赤壁迎战...

输出：
[
    ArticleChunk(
        title="官渡之战",
        content="公元200年，曹操与袁绍在官渡展开决战...",
        chunk_index=0,
        start_line=0,
        end_line=2
    ),
    ArticleChunk(
        title="赤壁之战",
        content="公元208年，曹操率军南下，孙刘联军在赤壁迎战...",
        chunk_index=1,
        start_line=3,
        end_line=5
    )
]
```

### 3.3 事项提取算法

**目标**：从原文块提取结构化的事项

```python
async def extract_events_from_chunk(
    chunk: ArticleChunk
) -> List[SourceEvent]:
    """
    从原文块提取事项
    
    使用 LLM 一次性提取：
    1. 事项标题和内容
    2. 事项关联的所有实体
    """
    
    prompt = f"""
你是一个专业的信息提取助手。

请从以下文本中提取具体的事项和实体：

=== 原文块 ===
标题：{chunk.title}
内容：
{chunk.content}

=== 提取要求 ===
1. **事项（SourceEvent）**：独立的、完整的信息单元
   - 可以是：事件、战役、会议、决策、发现、结论等
   - 一个文本块可能包含多个事项

2. **实体（Entity）**：事项的属性维度（5种类型）
   - TIME: 时间（如：公元200年、建安五年）
   - LOCATION: 地点（如：官渡、许昌、益州）
   - PERSON: 人物（如：曹操、刘备、诸葛亮）
   - TOPIC: 主题（如：战役、政治、经济）
   - ACTION: 行为（如：决战、撤退、结盟）
   - TAG: 标签（如：三国、军事、历史）

=== 输出格式（JSON） ===
{{
  "events": [
    {{
      "title": "事项标题",
      "content": "事项详细内容（保留关键信息）",
      "entities": {{
        "time": ["公元200年"],
        "location": ["官渡"],
        "person": ["曹操", "袁绍"],
        "topic": ["战役"],
        "action": ["决战"],
        "tag": ["三国", "军事"]
      }}
    }}
  ]
}}
"""
    
    # 调用 LLM
    result = await llm.chat_with_schema(prompt, schema=EventExtractionSchema)
    
    # 构建事项对象
    events = []
    for event_data in result["events"]:
        event = SourceEvent(
            id=generate_uuid(),
            source_config_id=chunk.source_config_id,
            chunk_id=chunk.id,
            article_id=chunk.article_id,
            title=event_data["title"],
            content=event_data["content"],
            entities=[]  # 后续填充
        )
        
        # 创建实体对象
        for entity_type, entity_names in event_data["entities"].items():
            for name in entity_names:
                entity = Entity(
                    id=generate_uuid(),
                    type=entity_type,
                    name=name,
                    normalized_name=normalize_entity_name(name)
                )
                event.entities.append(entity)
        
        events.append(event)
    
    return events
```

**示例**：

```python
输入：
ArticleChunk(
    title="官渡之战",
    content="公元200年，曹操与袁绍在官渡展开决战，曹操以少胜多，奠定了统一北方的基础"
)

输出：
[
    SourceEvent(
        title="官渡之战",
        content="公元200年，曹操与袁绍在官渡展开决战，曹操以少胜多，奠定了统一北方的基础",
        entities=[
            Entity(type="time", name="公元200年"),
            Entity(type="location", name="官渡"),
            Entity(type="person", name="曹操"),
            Entity(type="person", name="袁绍"),
            Entity(type="topic", name="战役"),
            Entity(type="action", name="决战"),
            Entity(type="tag", name="三国")
        ]
    )
]
```

### 3.4 实体标准化

**目标**：统一不同表达方式的实体

```python
def normalize_entity_name(name: str) -> str:
    """
    实体标准化
    
    规则：
    1. 去除空格、标点
    2. 统一同义词（如：曹孟德 → 曹操）
    3. 统一时间格式（如：公元200年 → 200年）
    """
    # 1. 基础清洗
    normalized = name.strip()
    
    # 2. 同义词映射（可用词典或向量相似度）
    synonyms_map = {
        "曹孟德": "曹操",
        "刘玄德": "刘备",
        "孔明": "诸葛亮"
    }
    if normalized in synonyms_map:
        normalized = synonyms_map[normalized]
    
    # 3. 时间格式统一
    if "公元" in normalized:
        normalized = normalized.replace("公元", "").strip()
    
    return normalized
```

### 3.5 批量存储

**策略**：批量插入 MySQL + Elasticsearch

```python
async def store_processed_data(
    chunks: List[ArticleChunk],
    events: List[SourceEvent],
    entities: List[Entity]
):
    """
    批量存储数据
    
    步骤：
    1. 生成向量（content_vector）
    2. 插入 MySQL（关系数据）
    3. 插入 Elasticsearch（向量检索）
    """
    
    # 1. 批量生成向量
    chunk_texts = [f"{c.title}\n{c.content}" for c in chunks]
    event_texts = [f"{e.title}\n{e.content}" for e in events]
    
    chunk_vectors = await batch_embed(chunk_texts)
    event_vectors = await batch_embed(event_texts)
    
    for chunk, vector in zip(chunks, chunk_vectors):
        chunk.content_vector = vector
    
    for event, vector in zip(events, event_vectors):
        event.content_vector = vector
    
    # 2. 批量插入 MySQL
    async with mysql_session() as session:
        session.add_all(chunks)
        session.add_all(events)
        session.add_all(entities)
        await session.commit()
    
    # 3. 批量插入 Elasticsearch
    await es_bulk_index("article_chunk", chunks)
    await es_bulk_index("source_event", events)
```

---

## 4. 神经网络式检索机制

### 4.1 核心概念

**神经元（事项）**：存储的信息单元，相当于神经网络中的神经元
**突触（实体）**：连接事项的通道，相当于神经网络中的突触
**激活（召回）**：通过实体激活相关事项，类似神经元的激活传播
**权重（评分）**：实体的重要性和事项的相关度

### 4.2 实体类型权重

**5种实体类型及其权重**（可配置）：

```python
ENTITY_TYPE_WEIGHTS = {
    "time": 0.9,        # 时间：公元200年、建安五年
    "location": 1.0,    # 地点：官渡、许昌、益州
    "person": 1.1,      # 人物：曹操、刘备、诸葛亮（稍重要）
    "topic": 1.5,       # 主题：战役、政治、经济（最重要）
    "action": 1.2,      # 行为：决战、撤退、结盟（重要）
    "tag": 1.0,         # 标签：三国、军事、历史
}
```

**权重说明**：
- **topic（主题）**权重最高（1.5），因为它是核心线索
- **person（人物）**和 **action（行为）**权重较高，是关键维度
- **time（时间）**权重较低，通常作为辅助信息

### 4.2 权重计算公式

**场景**：给定源事项A和候选事项B，计算B与A的相关度

**公式**：

```
相关度(A, B) = Σ (匹配维度权重 × 实体相似度) / Σ (所有维度权重)

其中：
- 匹配维度：A和B都有实体的维度
- 实体相似度：该维度上实体的匹配程度（0-1）
```

**详细算法**：

```python
def calculate_relevance(
    source_event: SourceEvent,
    candidate_event: SourceEvent,
    entity_weights: Dict[str, float]
) -> float:
    """
    计算两个事项之间的相关度

    Args:
        source_event: 源事项
        candidate_event: 候选事项
        entity_weights: 实体类型权重配置

    Returns:
        相关度分数（0-1）
    """

    total_weighted_score = 0.0
    total_weight = 0.0

    # 遍历所有实体维度
    for entity_type in ENTITY_TYPES:
        source_entities = source_event.get_entities_by_type(entity_type)
        candidate_entities = candidate_event.get_entities_by_type(entity_type)

        # 如果某个维度双方都有实体，则计算该维度的相似度
        if source_entities and candidate_entities:
            # 计算该维度的实体相似度
            similarity = calculate_entity_similarity(
                source_entities,
                candidate_entities
            )

            # 加权累加
            weight = entity_weights.get(entity_type, 1.0)
            total_weighted_score += similarity * weight
            total_weight += weight

    # 归一化
    if total_weight == 0:
        return 0.0

    return total_weighted_score / total_weight


def calculate_entity_similarity(
    entities_a: List[Entity],
    entities_b: List[Entity]
) -> float:
    """
    计算两个实体集合的相似度

    方法：Jaccard相似度 + 向量相似度

    Jaccard = |A ∩ B| / |A ∪ B|
    """

    # 方法1: 基于标准化名称的Jaccard相似度
    names_a = set(e.normalized_name for e in entities_a)
    names_b = set(e.normalized_name for e in entities_b)

    intersection = len(names_a & names_b)
    union = len(names_a | names_b)

    jaccard = intersection / union if union > 0 else 0.0

    # 方法2: 基于向量的最大相似度（可选）
    # 对于每个实体A，找到与B中最相似的实体，取平均
    if USE_VECTOR_SIMILARITY:
        max_sims = []
        for entity_a in entities_a:
            max_sim = max(
                cosine_similarity(entity_a.vector, entity_b.vector)
                for entity_b in entities_b
            )
            max_sims.append(max_sim)

        vector_sim = sum(max_sims) / len(max_sims) if max_sims else 0.0

        # 混合：Jaccard 60% + Vector 40%
        return jaccard * 0.6 + vector_sim * 0.4
    else:
        return jaccard
```

### 4.3 示例计算

```python
# 示例事项A
event_a = SourceEvent(
    title="302.ai的大模型微调方案",
    entities={
        "ORGANIZATION": ["302.ai"],
        "TOPIC": ["大模型", "微调"],
        "ACTION": ["部署"]
    }
)

# 候选事项B
event_b = SourceEvent(
    title="LLM微调实践",
    entities={
        "TOPIC": ["LLM", "微调", "训练"],
        "ACTION": ["优化"]
    }
)

# 计算相关度
"""
匹配维度：TOPIC, ACTION

TOPIC维度：
- A: {大模型, 微调}
- B: {LLM, 微调, 训练}
- 扩展后 A: {大模型, LLM, 模型, 微调, fine-tuning}
- 扩展后 B: {LLM, 大模型, 微调, fine-tuning, 训练}
- Jaccard = |{LLM, 大模型, 微调, fine-tuning}| / |{LLM, 大模型, 模型, 微调, fine-tuning, 训练}|
         = 4 / 6 = 0.67
- 权重: 1.5

ACTION维度：
- A: {部署}
- B: {优化}
- Jaccard = 0 / 2 = 0.0
- 权重: 1.2

相关度 = (0.67 * 1.5 + 0.0 * 1.2) / (1.5 + 1.2)
       = 1.005 / 2.7
       = 0.37
"""
```

---

## 5. 多维度匹配算法

### 5.1 算法流程

```
源事项A
    ↓
【1】提取A的所有实体
    ↓
【2】按实体类型分组
    ↓
【3】每个维度独立召回
    ↓
【4】聚合召回结果
    ↓
【5】计算匹配度
    ↓
候选事项列表（带匹配度）
```

### 5.2 实现

```python
async def multi_dimensional_match(
    source_event: SourceEvent,
    source_config_id: str,
    expand_entities: bool = True
) -> List[Tuple[SourceEvent, Dict[str, Any]]]:
    """
    多维度匹配算法

    Args:
        source_event: 源事项
        source_config_id: 信息源ID
        expand_entities: 是否扩展实体（同义词）

    Returns:
        [(候选事项, 匹配元数据)]
        匹配元数据包括：
        - matched_dimensions: 匹配的维度列表
        - match_score: 匹配分数
        - dimension_details: 每个维度的详情
    """

    # 【1】提取源事项的实体
    source_entities_by_type = source_event.get_entities_by_type()

    # 【2】扩展实体（可选）
    if expand_entities:
        expanded_entities = {}
        for entity_type, entities in source_entities_by_type.items():
            expanded = []
            for entity in entities:
                synonyms = await expand_entity(entity.name, entity_type)
                expanded.extend(synonyms)
            expanded_entities[entity_type] = list(set(expanded))
    else:
        expanded_entities = {
            k: [e.normalized_name for e in v]
            for k, v in source_entities_by_type.items()
        }

    # 【3】每个维度独立召回
    dimension_recalls = {}
    for entity_type, entity_names in expanded_entities.items():
        if not entity_names:
            continue

        # SQL查询：查找包含这些实体的事项
        recalled_events = await recall_events_by_entities(
            source_config_id=source_config_id,
            entity_type=entity_type,
            entity_names=entity_names
        )

        dimension_recalls[entity_type] = recalled_events

    # 【4】聚合召回结果（统计频次）
    event_match_counts = defaultdict(lambda: defaultdict(int))

    for entity_type, events in dimension_recalls.items():
        for event in events:
            event_match_counts[event.id]["count"] += 1
            event_match_counts[event.id]["dimensions"].add(entity_type)
            event_match_counts[event.id]["event"] = event

    # 【5】计算匹配度
    results = []
    total_dimensions = len(expanded_entities)

    for event_id, match_data in event_match_counts.items():
        candidate_event = match_data["event"]

        # 匹配度 = 匹配维度数 / 总维度数
        match_ratio = match_data["count"] / total_dimensions

        # 详细计算相关度（使用权重）
        relevance_score = calculate_relevance(
            source_event,
            candidate_event,
            ENTITY_TYPE_WEIGHTS
        )

        metadata = {
            "matched_dimensions": list(match_data["dimensions"]),
            "match_count": match_data["count"],
            "total_dimensions": total_dimensions,
            "match_ratio": match_ratio,
            "relevance_score": relevance_score,
            "final_score": match_ratio * 0.4 + relevance_score * 0.6
        }

        results.append((candidate_event, metadata))

    # 按分数排序
    results.sort(key=lambda x: x[1]["final_score"], reverse=True)

    return results


async def recall_events_by_entities(
    source_config_id: str,
    entity_type: str,
    entity_names: List[str]
) -> List[SourceEvent]:
    """
    通过实体召回事项（SQL查询）

    SQL示例：
    SELECT DISTINCT se.*
    FROM source_event se
    JOIN event_entity ee ON se.id = ee.event_id
    JOIN entity e ON ee.entity_id = e.id
    WHERE se.source_config_id = ?
      AND e.type = ?
      AND e.normalized_name IN (?, ?, ...)
    """
    # 实现SQL查询...
    pass
```

---

## 6. 多跳召回算法

### 6.1 算法思想

从源事项A开始，通过实体关联进行多跳扩展：

```
A（大模型, 微调）
    ↓ 第1跳
B（微调, 训练数据）  C（大模型, 推理）
    ↓ 第2跳
D（训练数据, 标注）  E（推理, 优化）
    ↓ 第3跳
...
```

**深度控制**：最多跳N次
**广度控制**：每次最多扩展K个事项

### 6.2 实现

```python
async def multi_hop_recall(
    source_event: SourceEvent,
    source_config_id: str,
    max_depth: int = 3,
    breadth_per_hop: int = 5,
    threshold: float = 0.5
) -> Dict[int, List[SourceEvent]]:
    """
    多跳召回算法（BFS）

    Args:
        source_event: 源事项
        source_config_id: 信息源ID
        max_depth: 最大跳数
        breadth_per_hop: 每跳最多扩展的事项数
        threshold: 相关度阈值

    Returns:
        {深度: [事项列表]}
    """

    # 初始化
    visited = {source_event.id}  # 已访问事项
    hop_results = {0: [source_event]}  # 每一跳的结果
    current_hop = [source_event]

    # BFS多跳扩展
    for depth in range(1, max_depth + 1):
        next_hop = []

        # 对当前层的每个事项进行扩展
        for event in current_hop:
            # 多维度匹配，找到相关事项
            candidates = await multi_dimensional_match(
                source_event=event,
                source_config_id=source_config_id,
                expand_entities=True
            )

            # 过滤：
            # 1. 未访问过
            # 2. 相关度 > 阈值
            # 3. 取top K
            filtered = [
                (candidate, metadata)
                for candidate, metadata in candidates
                if candidate.id not in visited
                   and metadata["relevance_score"] >= threshold
            ][:breadth_per_hop]

            for candidate, metadata in filtered:
                visited.add(candidate.id)
                next_hop.append(candidate)

        # 如果没有新事项，提前结束
        if not next_hop:
            break

        hop_results[depth] = next_hop
        current_hop = next_hop

    return hop_results


# 示例使用
hop_results = await multi_hop_recall(
    source_event=event_a,
    source_config_id="user-001",
    max_depth=3,
    breadth_per_hop=5,
    threshold=0.5
)

"""
返回：
{
    0: [event_a],  # 源事项
    1: [event_b, event_c, event_d],  # 第1跳
    2: [event_e, event_f],  # 第2跳
    3: [event_g]  # 第3跳
}
"""
```

---

## 7. 相关度评分机制

### 7.1 综合评分公式

**最终评分 = 多维度匹配分 × 0.3 + 向量相似度 × 0.3 + 时间衰减 × 0.2 + 用户偏好 × 0.2**

### 7.2 各项评分

```python
def calculate_final_score(
    source_event: SourceEvent,
    candidate_event: SourceEvent,
    query_vector: List[float],
    user_preferences: Dict[str, Any]
) -> float:
    """
    计算最终评分

    包含4个维度：
    1. 多维度匹配分（0.3）
    2. 向量相似度（0.3）
    3. 时间衰减（0.2）
    4. 用户偏好（0.2）
    """

    # 1. 多维度匹配分
    relevance_score = calculate_relevance(
        source_event,
        candidate_event,
        ENTITY_TYPE_WEIGHTS
    )

    # 2. 向量相似度
    vector_sim = cosine_similarity(
        query_vector,
        candidate_event.content_vector
    )

    # 3. 时间衰减
    time_decay = calculate_time_decay(candidate_event.created_time)

    # 4. 用户偏好
    preference_score = calculate_preference_score(
        candidate_event,
        user_preferences
    )

    # 综合评分
    final_score = (
        relevance_score * 0.3 +
        vector_sim * 0.3 +
        time_decay * 0.2 +
        preference_score * 0.2
    )

    return final_score


def calculate_time_decay(created_time: datetime) -> float:
    """
    时间衰减

    策略：越新的事项分数越高

    公式：e^(-λt)
    其中 t = (now - created_time) / 天数
         λ = 衰减因子（默认0.01）
    """
    import math

    days_ago = (datetime.now() - created_time).days
    decay_factor = 0.01
    return math.exp(-decay_factor * days_ago)


def calculate_preference_score(
    event: SourceEvent,
    user_preferences: Dict[str, Any]
) -> float:
    """
    用户偏好评分

    根据用户的focus、memory等个性化信息调整分数

    策略：
    - 如果事项的category/tags与用户focus匹配 → +分
    - 如果涉及用户关注的实体 → +分
    """
    score = 0.5  # 基础分

    # 检查category是否匹配focus
    user_focus = set(user_preferences.get("focus", []))
    event_topics = set(event.get_entities_by_type("TOPIC"))

    if user_focus & event_topics:
        score += 0.3

    # 检查tags
    event_tags = set(event.tags)
    if user_focus & event_tags:
        score += 0.2

    return min(score, 1.0)
```

---

## 8. 检索策略

### 8.1 混合检索（SQL + Vector）

```python
async def hybrid_search(
    query: str,
    source_config_id: str,
    top_k: int = 10,
    sql_weight: float = 0.5,
    vector_weight: float = 0.5
) -> List[SourceEvent]:
    """
    混合检索：SQL精确查询 + 向量语义检索

    Args:
        query: 查询文本
        source_config_id: 信息源ID
        top_k: 返回数量
        sql_weight: SQL检索权重
        vector_weight: 向量检索权重

    Returns:
        排序后的事项列表
    """

    # 1. 从查询中提取实体
    query_entities = await extract_entities(query)

    # 2. SQL精确查询
    sql_results = await sql_search(
        source_config_id=source_config_id,
        entities=query_entities,
        top_k=top_k * 2  # 多召回一些
    )

    # 3. 向量检索
    query_vector = await embed_text(query)
    vector_results = await vector_search(
        vector=query_vector,
        source_config_id=source_config_id,
        top_k=top_k * 2
    )

    # 4. 合并结果（RRF - Reciprocal Rank Fusion）
    merged = reciprocal_rank_fusion(
        [sql_results, vector_results],
        [sql_weight, vector_weight]
    )

    return merged[:top_k]


def reciprocal_rank_fusion(
    result_lists: List[List[SourceEvent]],
    weights: List[float],
    k: int = 60
) -> List[SourceEvent]:
    """
    倒数排名融合（RRF）

    公式：score(event) = Σ weight_i / (k + rank_i)

    Args:
        result_lists: 多个结果列表
        weights: 每个列表的权重
        k: RRF参数（默认60）

    Returns:
        融合后的结果
    """
    scores = defaultdict(float)

    for result_list, weight in zip(result_lists, weights):
        for rank, event in enumerate(result_list, start=1):
            scores[event.id] += weight / (k + rank)

    # 按分数排序
    sorted_events = sorted(
        set(e for results in result_lists for e in results),
        key=lambda e: scores[e.id],
        reverse=True
    )

    return sorted_events
```

### 8.2 完整检索流程

```python
async def search_events(
    query: str,
    source_config_id: str,
    config: SearchConfig
) -> SearchResult:
    """
    完整的检索流程

    流程：
    1. 混合检索（SQL + Vector）
    2. 多维度匹配扩展
    3. 多跳召回（可选）
    4. 综合评分与排序
    5. 阈值过滤
    """

    # 1. 混合检索（初次召回）
    initial_results = await hybrid_search(
        query=query,
        source_config_id=source_config_id,
        top_k=config.top_k * 2
    )

    # 2. 如果需要深度/广度扩展
    if config.depth > 0 or config.breadth > 0:
        expanded_results = []

        for event in initial_results:
            # 多跳召回
            if config.depth > 0:
                hop_results = await multi_hop_recall(
                    source_event=event,
                    source_config_id=source_config_id,
                    max_depth=config.depth,
                    breadth_per_hop=config.breadth,
                    threshold=config.threshold
                )
                # 展开所有跳的结果
                for hop_events in hop_results.values():
                    expanded_results.extend(hop_events)

        # 合并
        all_results = initial_results + expanded_results
    else:
        all_results = initial_results

    # 3. 综合评分
    query_vector = await embed_text(query)
    user_preferences = await load_user_preferences(source_config_id)

    scored_results = []
    for event in all_results:
        score = calculate_final_score(
            source_event=initial_results[0],  # 使用最相关的事项作为参考
            candidate_event=event,
            query_vector=query_vector,
            user_preferences=user_preferences
        )
        scored_results.append((event, score))

    # 4. 排序
    scored_results.sort(key=lambda x: x[1], reverse=True)

    # 5. 阈值过滤
    filtered_results = [
        (event, score)
        for event, score in scored_results
        if score >= config.threshold
    ][:config.top_k]

    # 6. 构建结果
    return SearchResult(
        events=[event for event, _ in filtered_results],
        scores={event.id: score for event, score in filtered_results},
        metadata={
            "query": query,
            "total_recalled": len(all_results),
            "after_filtering": len(filtered_results)
        }
    )
```

---

## 9. 算法优化

### 9.1 性能优化

| 优化点 | 策略 |
|--------|------|
| **实体扩展缓存** | Redis缓存同义词结果（24小时） |
| **向量检索加速** | Elasticsearch ANN索引 |
| **SQL查询优化** | 联合索引 (type, normalized_name) |
| **批量处理** | 并发提取、批量插入 |
| **连接池** | 数据库连接池复用 |

### 9.2 召回优化

| 问题 | 解决方案 |
|------|---------|
| **召回率低** | 增加实体扩展、降低阈值、增加跳数 |
| **精确率低** | 提高阈值、使用智能过滤、优化权重配置 |
| **结果重复** | 去重、聚类相似事项 |

---

## 10. 下一步

- 阅读 [API接口文档](./document.md)
- 阅读 [开发指南](./development.md)
