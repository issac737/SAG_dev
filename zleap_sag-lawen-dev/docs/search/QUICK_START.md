# 搜索模块快速开始

## 🎯 三阶段搜索流程

```
Query → Recall（召回实体） → Expand（扩展实体） → Rerank（重排事项） → Events + Clues
```

## 💻 使用方式

### 1. API调用（推荐）

```bash
POST /api/v1/pipeline/search
{
  "source_config_id": "your_source_config_id",
  "query": "人工智能",
  "use_fast_mode": true,
  "max_entities": 30,
  "max_hops": 3,
  "strategy": "pagerank",
  "max_results": 10
}
```

### 2. Python调用

```python
from dataflow.modules.search import SAGSearcher, SearchConfig

searcher = SAGSearcher(llm_client, prompt_manager)

config = SearchConfig(
    query="人工智能",
    source_config_id="source_123",
)

result = await searcher.search(config)
```

## ⚙️ 配置参数

### 功能开关
- `enable_query_rewrite`: 是否启用query重写（默认True）
- `use_fast_mode`: 快速模式，跳过LLM抽取（默认True）

### Recall（召回）
- `vector_top_k`: 向量检索数量（默认15）
- `max_entities`: 最大实体数（默认25）
- `entity_similarity_threshold`: 实体相似度阈值（默认0.4）

### Expand（扩展）
- `expand_enabled`: 是否启用扩展（默认True）
- `max_hops`: 最大跳数（默认3）
- `entities_per_hop`: 每跳实体数（默认10）

### Rerank（重排）
- `strategy`: 排序策略 "pagerank"或"rrf"（默认pagerank）
- `max_results`: 最大返回数（默认10）
- `score_threshold`: 分数阈值（默认0.5）

## 📊 返回结果

```json
{
  "events": [...],      // 事项列表
  "clues": [...],       // 线索列表（支持图谱展示）
  "stats": {...},       // 统计信息
  "query": {...}        // 查询信息
}
```

## 🎨 前端图谱展示

线索数据可直接用于 [relation-graph](https://www.relation-graph.com) 展示：

```typescript
const { clues } = searchResult;

clues.forEach(clue => {
  // clue.from: 起点节点（query/entity/event）
  // clue.to: 终点节点
  // clue.stage: recall/expand/rerank
  // clue.confidence: 置信度
  // clue.relation: 关系类型
});
```

## ✨ 完整示例

```python
from dataflow.modules.search import SAGSearcher, SearchConfig
from dataflow.modules.search.config import RecallConfig, ExpandConfig, RerankConfig, RerankStrategy

searcher = SAGSearcher(llm_client, prompt_manager)

config = SearchConfig(
    query="人工智能的最新进展",
    source_config_id="source_123",
    enable_query_rewrite=True,
    
    recall=RecallConfig(
        use_fast_mode=True,
        vector_top_k=20,
        max_entities=30,
        entity_similarity_threshold=0.5,
    ),
    
    expand=ExpandConfig(
        enabled=True,
        max_hops=3,
        entities_per_hop=10,
        weight_change_threshold=0.1,
    ),
    
    rerank=RerankConfig(
        strategy=RerankStrategy.PAGERANK,
        max_results=15,
        score_threshold=0.5,
    )
)

result = await searcher.search(config)

# 使用结果
events = result['events']
clues = result['clues']  
stats = result['stats']

print(f"找到 {len(events)} 个事项")
print(f"生成 {len(clues)} 条线索")
print(f"召回 {stats['recall']['entities_count']} 个实体")
print(f"扩展到 {stats['expand']['entities_count']} 个实体")
```

---

**版本**: v2.0  
**更新**: 2025-11-04

