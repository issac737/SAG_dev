# 搜索问题诊断指南

## 问题：有实体没事项

### 症状
- ✅ `query_entities` 和 `recall_entities` 有数据（实体召回成功）
- ❌ `events` 返回空数组 `[]`（事项查询失败）
- ⚠️ `matched_count: 0`

### 可能原因

根据搜索流程，有以下几个关键检查点会导致返回空事项：

#### 1. 数据库关联问题（最常见）

**检查点**: EventEntity 表

```sql
-- 检查实体是否关联到事项
SELECT ee.entity_id, e.name as entity_name, COUNT(ee.event_id) as event_count
FROM event_entity ee
JOIN entity e ON e.id = ee.entity_id
WHERE ee.entity_id IN ('实体ID1', '实体ID2', ...)
GROUP BY ee.entity_id, e.name;
```

**可能原因**:
- EventEntity 表中没有数据
- 实体与事项未建立关联关系
- 数据导入流程跳过了实体抽取步骤

**解决方案**:
```bash
# 重新处理文档，确保实体抽取和关联
python -m dataflow.modules.load.main --source-id <source_config_id> --reprocess
```

#### 2. 相似度阈值过高（常见）

**检查点**: Stage2.5 步骤5 或 Stage3 步骤6

**日志特征**:
```
⚠️ Stage2.5步骤5失败：所有 X 个事项都被阈值过滤掉了。
  当前阈值: 0.70
  最高相似度: 0.42
  平均相似度: 0.28
  建议：降低 threshold 参数
```

**解决方案**:

方案1: 降低阈值（推荐）
```python
config = SearchConfig(
    query="美团外卖",
    source_config_id="test_source",
    threshold=0.3,  # 从默认的 0.5 降低到 0.3
    ...
)
```

方案2: 使用自适应阈值
```python
config = SearchConfig(
    query="美团外卖",
    source_config_id="test_source",
    threshold=0.0,  # 不过滤，查看所有结果的相似度分布
    top_k=20,  # 增加返回数量
    ...
)
```

#### 3. 向量缺失

**检查点**: Elasticsearch 向量存储

**日志特征**:
```
⚠️ Stage2.5步骤4失败：Embedding相似度计算返回空结果。
```

**解决方案**:
```bash
# 检查 ES 索引
curl -XGET 'localhost:9200/event_vectors/_count'

# 重新生成向量
python -m dataflow.scripts.rebuild_vectors --source-id <source_config_id>
```

#### 4. SourceEvent.references 字段缺失（Stage3 特有）

**检查点**: SourceEvent 表的 references 字段

```sql
-- 检查事项的 references 字段
SELECT id, title,
       CASE
           WHEN references IS NULL THEN 'NULL'
           WHEN references = '[]' THEN 'EMPTY'
           ELSE 'OK'
       END as references_status,
       source_config_id
FROM source_event
WHERE source_config_id = 'test_source'
LIMIT 10;
```

**日志特征**:
```
没有找到与段落关联的事项
```

**解决方案**:
- 确保文档处理时正确生成了段落引用
- 检查段落切分逻辑是否正常工作

### 诊断流程

#### 步骤1: 查看详细日志

```bash
# 设置日志级别为 DEBUG
export LOG_LEVEL=DEBUG

# 重新执行搜索，观察每个阶段的输出
```

关注以下关键日志：

**Stage1 成功标志**:
```
✅ 步骤8完成：提取了 X 个重要key
```

**Stage2 成功标志**:
```
阶段2完成：多跳搜索发现 X 个keys
```

**Stage2.5/Stage3 失败标志**:
```
⚠️ Stage2.5步骤1-3失败：未从 X 个实体找到任何关联事项
⚠️ Stage2.5步骤5失败：所有 X 个事项都被阈值过滤掉了
```

#### 步骤2: 数据库诊断

```sql
-- 1. 检查信息源数据完整性
SELECT
    (SELECT COUNT(*) FROM source_event WHERE source_config_id = 'test_source') as event_count,
    (SELECT COUNT(*) FROM entity WHERE source_config_id = 'test_source') as entity_count,
    (SELECT COUNT(*) FROM event_entity WHERE entity_id IN
        (SELECT id FROM entity WHERE source_config_id = 'test_source')) as relation_count;

-- 2. 检查 query 召回的实体是否有关联事项
SELECT e.id, e.name, e.type, COUNT(ee.event_id) as linked_events
FROM entity e
LEFT JOIN event_entity ee ON ee.entity_id = e.id
WHERE e.name IN ('美团外卖', '叠瑜', '拉斯维加斯', ...)  -- 替换为实际召回的实体名称
GROUP BY e.id, e.name, e.type;

-- 3. 查看事项的向量和摘要完整性
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN summary IS NULL OR summary = '' THEN 1 ELSE 0 END) as no_summary,
    SUM(CASE WHEN references IS NULL OR references = '[]' THEN 1 ELSE 0 END) as no_references
FROM source_event
WHERE source_config_id = 'test_source';
```

#### 步骤3: Elasticsearch 诊断

```bash
# 检查事项向量索引
curl -XGET 'localhost:9200/event_vectors/_search' -H 'Content-Type: application/json' -d'
{
  "query": {
    "term": { "source_config_id": "test_source" }
  },
  "size": 1
}'

# 检查实体向量索引
curl -XGET 'localhost:9200/entity_vectors/_search' -H 'Content-Type: application/json' -d'
{
  "query": {
    "term": { "source_config_id": "test_source" }
  },
  "size": 1
}'
```

### 快速修复方案

#### 方案1: 降低阈值（最快）

修改 API 调用参数：
```json
{
  "source_config_id": "test_source",
  "query": "美团外卖",
  "threshold": 0.3,  // 降低阈值
  "top_k": 10
}
```

#### 方案2: 重新处理数据（彻底）

```bash
# 1. 清理旧数据
python -m dataflow.scripts.clean_source --source-id test_source

# 2. 重新导入文档
python -m dataflow.modules.load.main \
    --source-id test_source \
    --documents-path ./data/documents \
    --extract-entities \
    --generate-vectors

# 3. 验证数据
python -m dataflow.scripts.verify_source --source-id test_source
```

#### 方案3: 使用快速模式（绕过问题）

```python
config = SearchConfig(
    query="美团外卖",
    source_config_id="test_source",
    use_fast_mode=True,  # 跳过 LLM 属性抽取，直接用 query embedding
    threshold=0.3,
    ...
)
```

### 监控和预防

#### 添加监控指标

```python
# 在搜索完成后检查关键指标
if result.stats:
    recall_count = result.stats.get("recall", {}).get("entities_count", 0)
    expand_count = result.stats.get("expand", {}).get("entities_count", 0)
    event_count = result.stats.get("rerank", {}).get("final_events", 0)

    if recall_count > 0 and event_count == 0:
        logger.warning(
            f"实体召回成功但事项为空: "
            f"recall={recall_count}, expand={expand_count}, events={event_count}"
        )
```

#### 数据质量检查

定期运行数据质量检查脚本：
```bash
python -m dataflow.scripts.check_data_quality --source-id test_source
```

### 常见问题 FAQ

**Q: 为什么会有实体但没有事项？**

A: 因为搜索是分阶段的：
1. Stage1/Stage2：从 query 召回实体（基于语义相似度）
2. Stage3/Stage2.5：从实体查找事项（需要数据库关联 + 相似度过滤）

如果 EventEntity 表没有关联数据，或者所有事项的相似度都低于阈值，就会出现有实体没事项的情况。

**Q: threshold 应该设置为多少？**

A: 建议值：
- **高精度场景**：0.6-0.8（返回结果少但准确）
- **平衡场景**：0.4-0.6（默认推荐）
- **高召回场景**：0.2-0.4（返回更多结果，可能包含噪音）
- **调试场景**：0.0（查看所有结果的相似度分布）

**Q: 如何判断是阈值问题还是数据问题？**

A: 查看增强日志输出：
- 如果看到 "最高相似度: 0.42" 低于阈值，是阈值问题
- 如果看到 "未从 X 个实体找到任何关联事项"，是数据关联问题
- 如果看到 "Embedding相似度计算返回空结果"，是向量缺失问题

**Q: use_stage3 和 use_fast_mode 的区别？**

A:
- **use_stage3**:
  - True: 使用 Stage3（段落级 PageRank，精度高，速度慢）
  - False: 使用 Stage2.5（事项级 RRF，速度快，精度略低）

- **use_fast_mode**:
  - True: 跳过 LLM 属性抽取，直接用 query embedding 召回实体
  - False: 使用 LLM 抽取属性，语义理解更准确

推荐组合：
- 生产环境：`use_stage3=False, use_fast_mode=True`（最快）
- 高质量场景：`use_stage3=True, use_fast_mode=False`（最准）
