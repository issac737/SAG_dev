# test_stage3.py 测试说明

## 概述

`test_stage3.py` 是 SAG 搜索引擎 Rerank 阶段的测试文件，支持**两种返回格式**的测试：
- **EVENT 模式**：返回事项列表（使用 `pagerank.py` 的事项级 PageRank）
- **PARAGRAPH 模式**：返回段落列表（使用 `pagerank_section.py` 的段落级 PageRank）

## 测试架构

### 完整流程
```
Recall (实体召回) → Expand (实体扩展) → Rerank (重排序)
                                             ↓
                                   根据 return_type 选择:
                                   ├─ EVENT: pagerank.py
                                   └─ PARAGRAPH: pagerank_section.py
```

## 测试菜单

运行测试：
```bash
cd tests/search
python test_stage3.py
```

### 可选测试项

1. **测试 EVENT 模式** - 返回事项列表
2. **测试 PARAGRAPH 模式** - 返回段落列表
3. **对比测试两种模式** - 对比两种返回格式（默认）
4. **运行所有测试** - 依次执行所有测试

## 返回格式对比

### EVENT 模式返回

```python
{
    "events": [                    # List[SourceEvent] - ORM对象列表
        SourceEvent(...),
        ...
    ],
    "clues": [                     # 线索列表
        {
            "stage": "recall",
            "from_node": {...},
            "to_node": {...},
            ...
        },
        ...
    ],
    "stats": {                     # 统计信息
        "recall": {
            "entities_count": 5
        },
        "expand": {
            "entities_count": 3,
            "hops": 2
        },
        "rerank": {
            "events_count": 10,    # ← 事项数量
            "strategy": "pagerank",
            "return_type": "event"
        }
    },
    "query": {
        "original": "...",
        "current": "...",
        "rewritten": false
    }
}
```

### PARAGRAPH 模式返回

```python
{
    "sections": [                  # List[Dict] - 段落字典列表
        {
            "section_id": "...",
            "article_id": "...",
            "heading": "...",
            "content": "...",
            "pagerank": 0.123,     # PageRank 值
            "weight": 0.456,       # 权重
            "score": 0.789,        # 相似度得分
            "search_type": "SQL-1",
            "event_ids": [...],    # 关联的事项ID
            "clues": [...]         # 召回线索
        },
        ...
    ],
    "clues": [                     # 线索列表（同EVENT模式）
        ...
    ],
    "stats": {                     # 统计信息
        "recall": {
            "entities_count": 5
        },
        "expand": {
            "entities_count": 3,
            "hops": 2
        },
        "rerank": {
            "sections_count": 10,  # ← 段落数量
            "strategy": "pagerank",
            "return_type": "paragraph"
        }
    },
    "query": {
        "original": "...",
        "current": "...",
        "rewritten": false
    }
}
```

## 配置参数

### 通过 ReturnType 控制返回格式

```python
from dataflow.modules.search.config import SearchConfig, ReturnType

# EVENT 模式
config = SearchConfig(
    query="MoE模型架构",
    source_config_id="...",
    return_type=ReturnType.EVENT,  # 🔑 控制返回事项
    ...
)

# PARAGRAPH 模式
config = SearchConfig(
    query="MoE模型架构",
    source_config_id="...",
    return_type=ReturnType.PARAGRAPH,  # 🔑 控制返回段落
    ...
)
```

### Rerank 配置参数

```python
SearchConfig(
    # Rerank 策略配置
    rerank__strategy=RerankStrategy.PAGERANK,  # 策略（PAGERANK 或 RRF）
    rerank__max_results=10,                    # 最大返回数量
    rerank__score_threshold=0.5,               # 相似度阈值（过滤低质量）
    rerank__max_key_recall_results=30,         # Step1 Key召回的最大数量
    rerank__max_query_recall_results=30,       # Step2 Query召回的最大数量
    rerank__pagerank_damping_factor=0.85,      # PageRank 阻尼系数
    rerank__pagerank_max_iterations=100,       # PageRank 最大迭代次数
)
```

## 测试函数说明

### 1. `test_search_events()`
测试 EVENT 模式，验证：
- 返回格式包含 `events` 字段
- `events` 是 SourceEvent 对象列表
- 包含完整的 clues 和 stats

### 2. `test_search_sections()`
测试 PARAGRAPH 模式，验证：
- 返回格式包含 `sections` 字段
- `sections` 是字典列表
- 每个段落包含 pagerank, weight, score 等字段

### 3. `test_both_modes()`
对比测试两种模式，验证：
- 相同查询条件下两种模式都能正常工作
- 返回格式符合预期
- 统计信息正确

## 关键验证点

### EVENT 模式
- ✅ 返回键是 `"events"`
- ✅ 数据类型是 `List[SourceEvent]`（ORM对象）
- ✅ 统计信息使用 `events_count`
- ✅ 支持 PAGERANK 和 RRF 两种策略

### PARAGRAPH 模式
- ✅ 返回键是 `"sections"`
- ✅ 数据类型是 `List[Dict]`（字典）
- ✅ 统计信息使用 `sections_count`
- ✅ 仅支持 PAGERANK 策略
- ✅ 每个段落包含 pagerank, weight, score 字段

## 输出示例

### EVENT 模式输出
```
✅ 搜索完成！返回 10 个事项，45 条线索

📊 统计信息:
  Recall 召回实体: 5
  Expand 扩展实体: 3
  Rerank 返回事项: 10
  策略: pagerank
  返回类型: event

📋 事项列表 (Top 5):
【事项 1】
  ID: 3d4fda9f...
  标题: MoE模型架构详解
  摘要: ...
  📌 召回线索 (2个):
    🔖 [topic] MoE扩展 (权重=0.90)
    🔍 [query] MoE模型架构 (权重=1.00)
...
```

### PARAGRAPH 模式输出
```
✅ 搜索完成！返回 10 个段落，45 条线索

📊 统计信息:
  Recall 召回实体: 5
  Expand 扩展实体: 3
  Rerank 返回段落: 10
  策略: pagerank
  返回类型: paragraph

📋 段落列表 (Top 5):
【段落 1】
  Section ID: a1b2c3d4...
  Article ID: e5f6g7h8...
  标题: MoE架构的核心原理
  PageRank: 0.123456
  Weight: 2.3456
  Score: 0.7890
  来源: SQL-1
  内容预览: MoE（Mixture of Experts）是一种...
  关联事项: 2 个
    - 3d4fda9f...
    - 8h7g6f5e...
  📌 召回线索 (2个):
    🔖 [topic] MoE扩展 (权重=0.90)
...
```

## 注意事项

1. **数据库要求**：需要有测试数据库和 Elasticsearch 连接
2. **配置要求**：`source_config_id` 需要是有效的数据源ID
3. **性能考虑**：首次运行会初始化 LLM 客户端，可能较慢
4. **策略限制**：PARAGRAPH 模式仅支持 PAGERANK 策略

## 故障排查

### 错误：未找到任何事项/段落
- 检查 `source_config_id` 是否正确
- 检查数据库中是否有相关数据
- 降低 `score_threshold` 阈值

### 错误：缺少 'events' 或 'sections' 字段
- 检查 `return_type` 配置是否正确
- 检查是否使用了正确的测试函数

### 性能问题
- 调整 `max_key_recall_results` 和 `max_query_recall_results` 降低召回数量
- 调整 `max_results` 限制最终返回数量

## 版本历史

- **v2.0** (2025-01-12): 完全重写，支持 EVENT 和 PARAGRAPH 两种模式
- **v1.0**: 原始版本，仅支持 Stage3Searcher（已废弃）
