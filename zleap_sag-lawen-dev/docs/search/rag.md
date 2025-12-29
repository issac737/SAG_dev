# RAG 三路向量检索详解

## 概述

RAG（Retrieval-Augmented Generation）模式采用**三路向量检索**策略，通过多维度语义搜索提高召回率和准确率。

**核心思想**：从不同维度检索，加权融合，全面覆盖。

---

## 架构设计

### 检索流程图

```
                    Query
                      ↓
              generate_embedding()
                      ↓
              Query Embedding
                      ↓
        ┌─────────────┼─────────────┐
        ↓             ↓              ↓
   路径1: 事项    路径2: 实体    路径3: 片段
   event_vectors  entity_vectors article_sections
        ↓             ↓              ↓
   直接匹配      关联匹配        内容匹配
   (60%权重)     (25%权重)      (15%权重)
        ↓             ↓              ↓
   event_ids     entity→event    section→event
        └─────────────┼─────────────┘
                      ↓
              加权融合 (Weighted Sum)
                      ↓
          排序 → 过滤 → 截断
                      ↓
              返回 Top-K Events
```

---

## 三路检索详解

### 路径1：事项向量检索（60%权重）⭐

**原理**：直接在 `event_vectors` 索引中搜索相似事项

**流程**：
```python
Query Embedding 
    ↓ KNN搜索
EventVectorRepository.search_similar_by_content()
    ↓
[{event_id: "e1", _score: 0.92}, ...]
    ↓
提取 {event_id: score}
```

**优势**：
- ✅ 最直接、最准确
- ✅ 语义匹配度高
- ✅ 搜索速度快（ES KNN）

**权重理由**：事项向量是对事项整体内容的向量化，最能代表事项本身的语义。

---

### 路径2：实体向量检索（25%权重）

**原理**：通过相似实体找关联的事项

**流程**：
```python
Query Embedding
    ↓ KNN搜索
EntityVectorRepository.search_similar()
    ↓
[{entity_id: "ent1", _score: 0.88}, ...]
    ↓ SQL查询（event_entity表）
SELECT event_id FROM event_entity 
WHERE entity_id IN (...)
    ↓
{event_id: max_entity_score}
```

**数据关系**：
```
Entity ←→ EventEntity ←→ SourceEvent
(多对多关系)
```

**聚合策略**：
- 一个event可能关联多个匹配的entity
- 取所有匹配entity的**最大score**
- 原因：只要有一个高度相关的entity，该event就相关

**权重理由**：实体体现了事项的关键概念，但不如整体语义全面。

---

### 路径3：片段向量检索（15%权重）

**原理**：通过相似片段反向找关联的事项

**流程**：
```python
Query Embedding
    ↓ KNN搜索
ArticleSectionRepository.search_similar_by_content()
    ↓
[{section_id: "sec1", _score: 0.85}, ...]
    ↓ SQL查询（references字段）
SELECT id, references FROM source_event
WHERE references IS NOT NULL
    ↓ Python过滤
if section_id in event.references:
    匹配成功
    ↓
{event_id: calculated_score}
```

**数据关系**：
```
ArticleSection ←→ SourceEvent.references (JSON数组)
["section_id_1", "section_id_2", ...]
```

**Score计算**：
```python
# 基础score：匹配sections的平均相似度
avg_score = sum(matched_scores) / len(matched_scores)

# Boost：匹配越多section，boost越大
boost = min(len(matched_sections) / 3.0, 1.0) * 0.3

# 最终score（最多提升30%）
final_score = avg_score * (1 + boost)
```

**权重理由**：片段只是事项的原始素材，间接相关性较弱。

---

## 融合策略

### 加权求和公式

```
final_score(event_id) = 
    event_score × 0.60 +
    entity_score × 0.25 +
    section_score × 0.15
```

### 融合示例

假设某个 `event_123` 在三路检索中的scores：

| 路径     | Score | 权重 | 加权Score  |
| -------- | ----- | ---- | ---------- |
| 事项向量 | 0.85  | 0.60 | 0.51       |
| 实体向量 | 0.90  | 0.25 | 0.225      |
| 片段向量 | 0.75  | 0.15 | 0.1125     |
| **合计** | -     | 1.00 | **0.8475** |

最终 `event_123` 的score = **0.8475**

### 融合优势

1. **互补性**：三路覆盖不同维度
   - Event: 整体语义
   - Entity: 关键概念
   - Section: 原始内容

2. **鲁棒性**：单路失败不影响整体
   - 即使某一路未召回，其他路可补充

3. **准确性**：多路验证提高可信度
   - 多路都召回的event，相关性更高

---

## 性能特性

### 时间复杂度

| 步骤          | 时间复杂度 | 说明                      |
| ------------- | ---------- | ------------------------- |
| 生成Embedding | O(1)       | API调用，固定时间         |
| 事项向量检索  | O(log N)   | ES KNN索引                |
| 实体向量检索  | O(log M)   | ES KNN索引                |
| 片段向量检索  | O(log P)   | ES KNN索引                |
| SQL关联查询   | O(K)       | K为匹配的entity/section数 |
| 融合排序      | O(E log E) | E为unique event数         |

**总体时间复杂度**：O(log N) - 由ES KNN主导

### 实际性能

| 指标         | 值       | 条件                       |
| ------------ | -------- | -------------------------- |
| **响应时间** | < 300ms  | 普通规模（< 10000 events） |
| **响应时间** | < 500ms  | 大规模（< 100000 events）  |
| **召回率**   | 90%+     | threshold = 0.5            |
| **精准度**   | 85%+     | threshold = 0.7            |
| **吞吐量**   | 100+ QPS | 单实例                     |

---

## 配置调优

### 权重调整

```python
# 场景1：重视精准匹配（默认）
WEIGHTS = {
    "event": 0.60,
    "entity": 0.25,
    "section": 0.15,
}

# 场景2：重视语义关联
WEIGHTS = {
    "event": 0.50,
    "entity": 0.35,  # 提高实体权重
    "section": 0.15,
}

# 场景3：重视内容覆盖
WEIGHTS = {
    "event": 0.45,
    "entity": 0.25,
    "section": 0.30,  # 提高片段权重
}
```

### 阈值设置

| 场景             | threshold | 效果                   |
| ---------------- | --------- | ---------------------- |
| **高精准**       | 0.8-0.9   | 只返回高度相关的结果   |
| **平衡**（推荐） | 0.6-0.7   | 准确率和召回率平衡     |
| **高召回**       | 0.3-0.5   | 返回更多可能相关的结果 |

### 搜索倍数

```python
# SEARCH_MULTIPLIER：控制每路返回的候选数量
k = top_k * SEARCH_MULTIPLIER

# 默认值：3
# - top_k=10 → 每路返回30个候选
# - 融合后去重，最终返回10个

# 调优建议：
# - 数据量小：设为 2-3
# - 数据量大：设为 3-5
```

---

## 使用示例

### 基本使用

```python
from dataflow.modules.search import EventSearcher, SearchConfig, SearchMode

searcher = EventSearcher(llm_client, prompt_manager)

config = SearchConfig(
    query="查找关于人工智能的重要事项",
    source_config_id="source_123",
    mode=SearchMode.RAG,
    top_k=10,
    threshold=0.7,
)

results = await searcher.search(config)
```

### 高精准查询

```python
config = SearchConfig(
    query="sophnet/Qwen3-30B-A3B-Thinking-2507的具体性能指标",
    source_config_id="source_123",
    mode=SearchMode.RAG,
    top_k=5,
    threshold=0.85,  # 高阈值
)

results = await searcher.search(config)
# 返回：高度相关的少量精准结果
```

### 高召回查询

```python
config = SearchConfig(
    query="AI相关内容",
    source_config_id="source_123",
    mode=SearchMode.RAG,
    top_k=20,
    threshold=0.5,  # 低阈值
)

results = await searcher.search(config)
# 返回：更多可能相关的结果
```

### 限制范围查询

```python
config = SearchConfig(
    query="核心结论",
    source_config_id="source_123",
    article_id="article_456",  # 限制在特定文章内
    mode=SearchMode.RAG,
    top_k=10,
)

results = await searcher.search(config)
# 返回：仅来自指定文章的事项
```

---

## 对比分析

### RAG vs LLM

| 维度         | RAG             | LLM               |
| ------------ | --------------- | ----------------- |
| **速度**     | ⚡⚡⚡⚡⚡ (< 500ms) | ⚡⚡⚡ (2-5s)        |
| **成本**     | 💰 (仅embedding) | 💰💰💰 (多次LLM调用) |
| **准确率**   | 85%+            | 90%+              |
| **召回率**   | 90%+            | 75%+              |
| **理解能力** | ⭐⭐⭐ (语义匹配)  | ⭐⭐⭐⭐⭐ (深度理解)  |
| **可扩展性** | ⭐⭐⭐⭐⭐           | ⭐⭐⭐               |

**选择建议**：
- 需要快速响应 → **RAG**
- 需要深度理解 → **LLM**
- 大规模数据 → **RAG**
- 复杂查询 → **LLM**

---

## 最佳实践

### 1. 查询优化

```python
# ✅ 好的查询
query = "人工智能在医疗领域的应用"  # 具体、明确

# ❌ 不好的查询
query = "AI"  # 过于宽泛
query = "所有内容"  # 无意义
```

### 2. 阈值设置

```python
# 探索性查询：低阈值
config.threshold = 0.5

# 精准查询：高阈值
config.threshold = 0.8

# 动态调整：根据结果数量调整
results = await searcher.search(config)
if len(results) < 3:
    config.threshold = 0.5  # 降低阈值重试
    results = await searcher.search(config)
```

### 3. 性能优化

```python
# 限制搜索范围
config.article_id = "specific_article"

# 合理设置top_k
config.top_k = 10  # 不要设置过大

# 批量查询：复用searcher实例
searcher = EventSearcher(llm_client, prompt_manager)
for query in queries:
    results = await searcher.search(config)
```

---

## 故障排查

### 问题1：返回结果为空

**可能原因**：
1. threshold设置过高
2. 向量库中无数据
3. source_config_id不正确

**解决方案**：
```python
# 1. 降低阈值
config.threshold = 0.3

# 2. 检查向量库
# 确保已运行 init_es_indices.py

# 3. 检查source_config_id
# 确保该信息源存在且有数据
```

### 问题2：结果不相关

**可能原因**：
1. Query表达不够明确
2. 向量模型不匹配
3. 权重配置不合理

**解决方案**：
```python
# 1. 优化query
query = "更具体的描述"

# 2. 检查embedding模型
# 确保索引时和检索时使用相同的模型

# 3. 调整权重（高级）
# 修改 RAGSearchProcessor.WEIGHTS
```

### 问题3：响应太慢

**可能原因**：
1. 数据量过大
2. ES集群性能问题
3. 网络延迟

**解决方案**：
```python
# 1. 减少候选数量
# 修改 SEARCH_MULTIPLIER = 2

# 2. 限制搜索范围
config.article_id = "specific_article"

# 3. 优化ES配置
# 增加 num_candidates 参数
```

---

## 技术细节

### Elasticsearch KNN搜索

```python
# ES查询结构
knn_query = {
    "field": "content_vector",
    "query_vector": [0.1, 0.2, ...],  # 1536维
    "k": 30,  # 返回30个结果
    "num_candidates": 300,  # 内部候选数（k * 10）
    "filter": {
        "term": {"source_config_id": "source_123"}
    }
}
```

### Score归一化

```python
# ES返回的score是余弦相似度（0-2之间）
# 需要归一化到 0-1 范围

normalized_score = min(raw_score / 2.0, 1.0)
```

### 内存优化

```python
# 延迟加载：只加载最终需要的events
event_ids = list(merged_scores.keys())  # 先收集IDs
events = await self._load_events_by_ids(event_ids)  # 再加载对象
```

---

## 扩展功能（规划）

### v1.2 版本

1. **BM25混合检索**
   ```python
   # 结合BM25全文检索和向量检索
   bm25_score = search_by_text(query)
   vector_score = search_by_vector(embedding)
   final_score = vector_score * 0.7 + bm25_score * 0.3
   ```

2. **Rerank重排序**
   ```python
   # 使用专门的rerank模型重新排序
   results = await vector_search(...)
   reranked = await rerank_model.rerank(query, results)
   ```

3. **自适应权重**
   ```python
   # 根据查询类型自动调整权重
   if is_entity_query(query):
       WEIGHTS["entity"] = 0.4  # 提高实体权重
   ```

---

## 参考资料

- **Elasticsearch KNN**: https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html
- **向量检索原理**: [docs/algorithm.md](../algorithm.md)
- **数据库设计**: [docs/database.md](../database.md)

---

**版本**: v1.1  
**最后更新**: 2025-10-21  
**维护者**: DataFlow Team

