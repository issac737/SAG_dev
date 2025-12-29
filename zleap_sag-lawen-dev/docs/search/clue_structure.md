# 线索数据结构规范

## 概述

本文档定义了搜索系统中线索（Clue）的统一数据结构规范。通过统一端点节点和线索的数据格式，确保系统的一致性、可追踪性和可扩展性。

## 设计目标

### 问题背景

**优化前的问题：**
1. **端点结构不统一**：
   - query端：缺少id字段，name存储查询内容
   - entity端：有id、name、entity_type，但缺少category和content
   - event端：有id、name(title)、description(summary截断)，但缺少category和content

2. **字段映射混乱**：
   - entity端：name是实体名称，没有content字段
   - event端：name是title，description是summary（截断100字符），缺少完整content

3. **缺少线索ID**：当前线索没有唯一ID，无法追踪单条线索

### 优化目标

1. **数据一致性**：所有端点使用完全相同的字段结构
2. **可追踪性**：每条线索有唯一ID，可构建完整追踪链
3. **前端友好**：统一结构便于前端可视化展示
4. **可扩展性**：为section端点预留了结构，方便后续扩展

## 统一端点节点结构

所有端点（query/entity/event/section）使用一致的字段结构：

```python
{
    "id": str,           # 数据库ID或UUID
    "type": str,         # 端点类型：query | entity | event | section
    "category": str,     # 分类标识
    "content": str,      # 核心内容
    "description": str   # 辅助描述
}
```

### 字段说明

- **id**: 唯一标识符，数据库ID或UUID
- **type**: 端点类型，固定值：`query` | `entity` | `event` | `section`
- **category**: 分类标识，根据type不同有不同含义（见下表）
- **content**: 核心内容，主要的数据载体
- **description**: 辅助描述，额外的说明信息

## 端点类型详细规范

| 端点类型 | category | content | description |
|---------|----------|---------|-------------|
| **query** | `origin` 原始请求<br>`rewrite` 重写请求 | 查询正文 | "原始搜索内容" / "重写的请求" |
| **entity** | `entity_type`<br>(person/topic/location/action/tags等) | entity.name | entity.description |
| **event** | `event.category`<br>(暂时为空，后续扩展) | event.content<br>(完整内容) | event.summary<br>(完整摘要，不截断) |
| **section** | `section_type`<br>(保留扩展) | section.content | section.summary |

### Query端点

```python
{
    "id": "uuid-generated-from-query",  # 使用uuid5生成确定性ID
    "type": "query",
    "category": "origin",  # 或 "rewrite"
    "content": "用户的搜索查询内容",
    "description": "原始搜索内容"  # 或 "重写的请求"
}
```

**Category判断逻辑：**
```python
category = "rewrite" if (config.origin_query and config.origin_query != config.query) else "origin"
```

### Entity端点

```python
{
    "id": "entity-key-id-from-db",  # 从数据库获取
    "type": "entity",
    "category": "person",  # person/topic/location/action/tags
    "content": "张三",  # entity.name
    "description": "某公司CEO"  # entity.description
}
```

### Event端点

```python
{
    "id": 12345,  # event.id from database
    "type": "event",
    "category": "",  # 暂时为空，等待数据库字段event.category
    "content": "完整的事件内容...",  # event.content (不截断)
    "description": "完整的事件摘要..."  # event.summary (不截断)
}
```

**注意事项：**
- `content` 使用 `event.content`，保留完整内容（不截断）
- `description` 使用 `event.summary`，保留完整摘要（不截断）
- `category` 暂时为空字符串，等待数据库添加该字段

### Section端点（保留扩展）

```python
{
    "id": "section-uuid",
    "type": "section",
    "category": "paragraph",  # 保留扩展
    "content": "段落内容...",
    "description": "段落摘要..."
}
```

## 统一线索结构

```python
{
    "id": str,              # 线索唯一ID（UUID v4）
    "stage": str,           # recall | expand | rerank
    "from": EndpointNode,   # 起点（统一结构）
    "to": EndpointNode,     # 终点（统一结构）
    "confidence": float,    # 置信度分数 [0.0, 1.0]
    "relation": str,        # 关系类型描述
    "metadata": dict        # 其他元数据
}
```

### 字段说明

- **id**: 线索唯一标识符，使用UUID v4随机生成
- **stage**: 所属阶段，固定值：`recall` | `expand` | `rerank`
- **from**: 起点端点节点（统一结构）
- **to**: 终点端点节点（统一结构）
- **confidence**: 置信度分数，取值范围 [0.0, 1.0]
- **relation**: 关系类型，如："语义相似"、"关系扩展"、"内容重排"
- **metadata**: 额外的元数据信息（各阶段不同）

### Recall阶段线索（query → entity）

```python
{
    "id": "clue-uuid-xxxx",
    "stage": "recall",
    "from": {
        "id": "query-uuid-xxxx",
        "type": "query",
        "category": "origin",
        "content": "人工智能的发展趋势",
        "description": "原始搜索内容"
    },
    "to": {
        "id": "entity-123",
        "type": "entity",
        "category": "topic",
        "content": "人工智能",
        "description": "AI技术领域"
    },
    "confidence": 0.92,
    "relation": "语义相似",
    "metadata": {
        "similarity": 0.92,
        "method": "vector_search"
    }
}
```

### Expand阶段线索（entity → entity）

```python
{
    "id": "clue-uuid-yyyy",
    "stage": "expand",
    "from": {
        "id": "entity-123",
        "type": "entity",
        "category": "topic",
        "content": "人工智能",
        "description": "AI技术领域"
    },
    "to": {
        "id": "entity-456",
        "type": "entity",
        "category": "topic",
        "content": "机器学习",
        "description": "AI的子领域"
    },
    "confidence": 0.85,
    "relation": "关系扩展",
    "metadata": {
        "hop_count": 2
    }
}
```

### Rerank阶段线索（entity → event）

```python
{
    "id": "clue-uuid-zzzz",
    "stage": "rerank",
    "from": {
        "id": "entity-456",
        "type": "entity",
        "category": "topic",
        "content": "机器学习",
        "description": "AI的子领域"
    },
    "to": {
        "id": 789,
        "type": "event",
        "category": "",
        "content": "某公司发布新的机器学习框架，支持...",  # 完整内容
        "description": "某公司今日宣布..."  # 完整摘要
    },
    "confidence": 0.78,
    "relation": "内容重排",
    "metadata": {
        "entity_weight": 0.85,
        "similarity": 0.75,
        "bm25_score": 12.5,
        "embedding_rank": 3,
        "bm25_rank": 5
    }
}
```

## UUID生成策略

### Query端点ID：确定性生成（UUID v5）

使用UUID v5基于query内容生成确定性ID，确保相同查询生成相同ID：

```python
import uuid

query_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, config.query))
```

**优点：**
- 相同查询生成相同ID，便于去重
- 可预测，便于调试

### 线索ID：随机生成（UUID v4）

每条线索使用UUID v4随机生成唯一ID：

```python
import uuid

clue_id = str(uuid.uuid4())
```

**优点：**
- 每次运行生成不同ID，便于追踪不同的搜索过程
- 无碰撞风险

## 实现：统一构建器

所有线索构建使用 `dataflow/modules/search/clue_builder.py` 中的 `ClueBuilder` 类。

### 核心方法

#### 1. build_query_endpoint()

构建query端点节点：

```python
@staticmethod
def build_query_endpoint(config: SearchConfig) -> Dict[str, Any]:
    """
    构建query端点节点

    Args:
        config: 搜索配置

    Returns:
        统一格式的query端点节点
    """
    # 使用query内容生成确定性UUID
    query_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, config.query))

    # 判断category
    category = "rewrite" if (config.origin_query and
                             config.origin_query != config.query) else "origin"

    return {
        "id": query_id,
        "type": "query",
        "category": category,
        "content": config.query,
        "description": "原始搜索内容" if category == "origin" else "重写的请求"
    }
```

#### 2. build_entity_endpoint()

构建entity端点节点：

```python
@staticmethod
def build_entity_endpoint(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    构建entity端点节点

    Args:
        entity: 实体字典，必须包含 id, name, type 字段

    Returns:
        统一格式的entity端点节点
    """
    return {
        "id": entity["id"],
        "type": "entity",
        "category": entity["type"],  # person/topic/location等
        "content": entity["name"],
        "description": entity.get("description", "")
    }
```

#### 3. build_event_endpoint()

构建event端点节点：

```python
@staticmethod
def build_event_endpoint(event: SourceEvent) -> Dict[str, Any]:
    """
    构建event端点节点

    Args:
        event: 事件对象

    Returns:
        统一格式的event端点节点
    """
    return {
        "id": event.id,
        "type": "event",
        "category": getattr(event, "category", ""),  # 暂时为空
        "content": event.content,  # 完整内容
        "description": event.summary or ""  # 完整摘要
    }
```

#### 4. build_recall_clue()

构建Recall阶段线索（query → entity）：

```python
@staticmethod
def build_recall_clue(
    config: SearchConfig,
    entity: Dict[str, Any],
    confidence: float,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    构建Recall阶段线索（query → entity）
    """
    return {
        "id": str(uuid.uuid4()),
        "stage": "recall",
        "from": ClueBuilder.build_query_endpoint(config),
        "to": ClueBuilder.build_entity_endpoint({
            "id": entity.get("key_id") or entity.get("entity_id"),
            "name": entity["name"],
            "type": entity["type"],
            "description": entity.get("description", "")
        }),
        "confidence": confidence,
        "relation": "语义相似",
        "metadata": metadata or {}
    }
```

#### 5. build_expand_clue()

构建Expand阶段线索（entity → entity）：

```python
@staticmethod
def build_expand_clue(
    parent_entity: Dict[str, Any],
    child_entity: Dict[str, Any],
    confidence: float,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    构建Expand阶段线索（entity → entity）
    """
    return {
        "id": str(uuid.uuid4()),
        "stage": "expand",
        "from": ClueBuilder.build_entity_endpoint(parent_entity),
        "to": ClueBuilder.build_entity_endpoint(child_entity),
        "confidence": confidence,
        "relation": "关系扩展",
        "metadata": metadata or {}
    }
```

#### 6. build_rerank_clue()

构建Rerank阶段线索（entity → event）：

```python
@staticmethod
def build_rerank_clue(
    entity: Dict[str, Any],
    event: SourceEvent,
    confidence: float,
    relation: str = "内容重排",
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    构建Rerank阶段线索（entity → event）
    """
    return {
        "id": str(uuid.uuid4()),
        "stage": "rerank",
        "from": ClueBuilder.build_entity_endpoint(entity),
        "to": ClueBuilder.build_event_endpoint(event),
        "confidence": confidence,
        "relation": relation,
        "metadata": metadata or {}
    }
```

## 使用示例

### Recall阶段（recall.py）

```python
from dataflow.modules.search.clue_builder import ClueBuilder

def _build_recall_clues(config, key_query_related):
    clues = []

    for entity in key_query_related:
        # 获取置信度
        confidence = entity.get("weight") or entity.get("similarity", 0.0)

        # 构建元数据
        metadata = {
            "similarity": entity.get("similarity", 0.0),
            "method": entity.get("method", "vector_search")
        }

        # 使用统一构建器创建线索
        clue = ClueBuilder.build_recall_clue(
            config=config,
            entity=entity,
            confidence=confidence,
            metadata=metadata
        )
        clues.append(clue)

    return clues
```

### Expand阶段（expand.py）

```python
from dataflow.modules.search.clue_builder import ClueBuilder

def _build_expand_clues(config, key_final):
    clues = []

    for key in key_final:
        if "parent_entity" in key and key.get("steps", [0])[0] >= 2:
            parent_entity = key["parent_entity"]

            # 准备实体字典
            parent_dict = {
                "id": parent_entity["id"],
                "name": parent_entity["name"],
                "type": parent_entity["type"],
                "description": ""
            }

            child_dict = {
                "id": key["key_id"],
                "name": key["name"],
                "type": key["type"],
                "description": key.get("description", "")
            }

            # 构建元数据
            metadata = {"hop_count": key.get("hop", 1)}

            # 使用统一构建器创建线索
            clue = ClueBuilder.build_expand_clue(
                parent_entity=parent_dict,
                child_entity=child_dict,
                confidence=key["weight"],
                metadata=metadata
            )

            clues.append(clue)

    return clues
```

### Rerank阶段（rrf.py / pagerank.py）

```python
from dataflow.modules.search.clue_builder import ClueBuilder

def _build_rerank_clues(config, key_final, final_events, event_to_clues):
    clues = []

    for event in final_events:
        if event.id in event_to_clues:
            for entity in event_to_clues[event.id]:
                # 准备实体字典
                entity_dict = {
                    "id": entity["id"],
                    "name": entity["name"],
                    "type": entity["type"],
                    "description": entity.get("description", "")
                }

                # 获取置信度
                confidence = getattr(event, 'rrf_score', 0.0)

                # 构建元数据
                metadata = {
                    "entity_weight": entity.get("weight", 0.0),
                    "similarity": getattr(event, 'similarity_score', None),
                    "bm25_score": getattr(event, 'bm25_score', None),
                    "embedding_rank": getattr(event, 'embedding_rank', None),
                    "bm25_rank": getattr(event, 'bm25_rank', None)
                }

                # 使用统一构建器创建线索
                clue = ClueBuilder.build_rerank_clue(
                    entity=entity_dict,
                    event=event,
                    confidence=confidence,
                    relation="内容重排",
                    metadata=metadata
                )
                clues.append(clue)

    return clues
```

## 迁移指南

### 从旧结构迁移

如果你的代码中还在使用旧的线索结构，请按照以下步骤迁移：

#### 1. 导入ClueBuilder

```python
from dataflow.modules.search.clue_builder import ClueBuilder
```

#### 2. 替换手动构建的端点节点

**旧代码：**
```python
query_node = {
    "type": "query",
    "name": config.query,
    "description": "用户搜索查询"
}
```

**新代码：**
```python
query_node = ClueBuilder.build_query_endpoint(config)
```

#### 3. 替换手动构建的线索

**旧代码：**
```python
clue = {
    "stage": "recall",
    "from": {"type": "query", "name": config.query},
    "to": {"type": "entity", "id": entity["key_id"], "name": entity["name"]},
    "confidence": entity["weight"],
    "relation": "语义相似"
}
```

**新代码：**
```python
clue = ClueBuilder.build_recall_clue(
    config=config,
    entity=entity,
    confidence=entity["weight"],
    metadata={"similarity": entity.get("similarity", 0.0)}
)
```

## 注意事项

1. **Event.category字段**：目前数据库没有该字段，需要处理为空字符串
2. **Query的UUID**：使用确定性生成（uuid5），同一查询生成相同ID
3. **线索的UUID**：使用随机生成（uuid4），每次运行生成不同ID
4. **Event.content**：保留完整内容，不截断，由前端决定显示长度
5. **向后兼容**：旧代码可以继续使用，但建议尽快迁移到新结构

## 未来扩展

### Section端点支持

当系统支持段落级搜索时，可以添加section端点：

```python
{
    "id": "section-uuid-xxx",
    "type": "section",
    "category": "paragraph",  # paragraph/heading/table等
    "content": "段落完整内容...",
    "description": "段落摘要..."
}
```

### Event.category字段

待数据库添加event.category字段后，可以使用该字段进行事件分类：

```python
{
    "id": 123,
    "type": "event",
    "category": "technology",  # technology/business/politics等
    "content": "...",
    "description": "..."
}
```

## 总结

统一的线索数据结构为系统带来：

1. **一致性**：所有端点和线索使用相同的数据格式
2. **可追踪性**：每条线索都有唯一ID，可构建完整的推理链
3. **可维护性**：集中的构建器便于统一修改和维护
4. **可扩展性**：预留了section等扩展端点的接口
5. **前端友好**：统一结构便于前端可视化展示

通过使用 `ClueBuilder` 类，所有线索构建代码都保持一致，减少了重复代码，提高了代码质量。
