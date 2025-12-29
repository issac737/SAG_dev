# PageRank 重构：从段落级到事项级

## 📋 重构概述

将 PageRank 搜索从**段落级别**改为**事项级别**，直接对事项进行排序。

---

## 🔄 核心变化对比

### 原逻辑（段落级）
```
Step1: key → event → section (SQL + ES向量)
Step2: query → section (ES KNN)
Step3: 合并section去重
Step4: 计算section权重
Step5: section关系图 + PageRank
Step6: Top-N section → 提取event
```

### 新逻辑（事项级）
```
Step1: key → event (SQL + ES向量相似度过滤)
Step2: query → event (ES向量相似度过滤)
Step3: 合并event去重（保留step1结果）
Step4: 计算event权重
Step5: event关系图 + PageRank
Step6: Top-N event（直接输出）
```

---

## 📝 详细实现方案

### Step 1: key → event (向量相似度过滤)

**原逻辑**:
1. key → entity (SQL)
2. entity → event (EventEntity)
3. event → section (references字段)
4. 从ES获取section向量
5. 计算section与query的余弦相似度

**新逻辑**:
1. key → entity (SQL) ✅ 保持
2. entity → event (EventEntity) ✅ 保持
3. **从ES获取event向量**
4. **计算event与query的余弦相似度**
5. **相似度过滤**：只保留相似度 > threshold 的event

**关键代码改动**:
```python
async def _step1_keys_to_events(
    self,
    key_final: List[Dict[str, Any]],
    query: str,
    source_config_ids: List[str],
    query_vector: List[float],
    config: SearchConfig
) -> List[Dict[str, Any]]:
    """
    步骤1: key找event (向量相似度过滤)

    Returns:
        事项列表，格式：
        {
            "search_type": "sql",
            "event_id": str,
            "title": str,
            "content": str,
            "category": str,
            "score": float,  # 余弦相似度
            "weight": float,  # 初始权重（从key权重计算）
            "source_entities": [entity_id1, entity_id2],  # 溯源：哪些实体召回了这个event
            "clues": [...]  # 溯源：召回线索
        }
    """
    # 1-2. 查询 entity 和 event (SQL) - 保持不变
    entity_ids = [key.get("key_id") for key in key_final]

    # 通过 EventEntity 查询 events
    async with self.session_factory() as session:
        event_entity_query = (
            select(EventEntity.event_id, EventEntity.entity_id, EventEntity.weight)
            .join(SourceEvent, EventEntity.event_id == SourceEvent.id)
            .where(
                and_(
                    SourceEvent.source_id.in_(source_config_ids),
                    EventEntity.entity_id.in_(entity_ids)
                )
            )
        )
        event_entities = (await session.execute(event_entity_query)).fetchall()

        # 计算每个event的权重
        event_weights = {}
        event_to_entities = {}
        for ee in event_entities:
            event_id = ee.event_id
            entity_id = ee.entity_id
            entity_weight = entity_weight_map.get(entity_id, 1.0)
            combined_weight = entity_weight * (ee.weight or 1.0)

            event_weights[event_id] = event_weights.get(event_id, 0) + combined_weight
            if event_id not in event_to_entities:
                event_to_entities[event_id] = []
            event_to_entities[event_id].append(entity_id)

        # 获取event详情
        event_query = select(SourceEvent).where(SourceEvent.id.in_(list(event_weights.keys())))
        events = (await session.execute(event_query)).scalars().all()

    # 3. 从ES批量获取event向量
    event_ids = [e.id for e in events]
    event_vectors_map = await self.event_repo.batch_get_event_vectors(event_ids)

    # 4. 计算event与query的余弦相似度
    event_results = []
    for event in events:
        event_vector = event_vectors_map.get(event.id)
        if not event_vector:
            self.logger.warning(f"事项 {event.id[:8]}... 没有向量，跳过")
            continue

        # 计算余弦相似度
        score = self._cosine_similarity(query_vector, event_vector)

        # 5. 相似度过滤
        if score < config.rerank.event_similarity_threshold:  # 新增配置项
            self.logger.debug(f"事项 {event.id[:8]}... 相似度 {score:.3f} 低于阈值，过滤")
            continue

        # 构建结果
        event_results.append({
            "search_type": "sql",
            "event_id": event.id,
            "title": event.title,
            "content": event.content,
            "category": event.category,
            "score": score,  # 余弦相似度
            "weight": event_weights[event.id],  # 初始权重
            "source_entities": event_to_entities[event.id],  # 溯源
            "clues": [...],  # 溯源线索
        })

    self.logger.info(f"Step1: {len(event_results)} 个事项通过相似度过滤")
    return sorted(event_results, key=lambda x: x['score'], reverse=True)
```

**需要添加的ES方法**:
```python
# 在 EventVectorRepository 中添加
async def batch_get_event_vectors(
    self,
    event_ids: List[str]
) -> Dict[str, List[float]]:
    """批量获取事项向量"""
    # 实现逻辑：从ES批量查询event向量
```

---

### Step 2: query → event (向量相似度过滤)

**原逻辑**:
- ES KNN搜索 section

**新逻辑**:
- ES KNN搜索 event
- 相似度过滤

**关键代码**:
```python
async def _step2_query_to_events(
    self,
    query: str,
    source_config_ids: List[str],
    k: int,
    query_vector: List[float],
    config: SearchConfig
) -> List[Dict[str, Any]]:
    """
    步骤2: query找event (ES向量搜索)

    Returns:
        事项列表（格式同Step1）
    """
    # 1. ES KNN搜索event
    similar_events = []
    for source_id in source_config_ids:
        events = await self.event_repo.search_similar_by_content(
            query_vector=query_vector,
            k=k,
            source_id=source_id
        )
        similar_events.extend(events)

    # 2. 构建结果
    event_results = []
    for event in similar_events:
        # 计算余弦相似度（从ES的_score转换）
        score = event.get('_score', 0.0) / 10.0  # 归一化

        # 相似度过滤
        if score < config.rerank.event_similarity_threshold:
            continue

        event_results.append({
            "search_type": "embedding",
            "event_id": event['id'],
            "title": event.get('title', ''),
            "content": event.get('content', ''),
            "category": event.get('category', ''),
            "score": score,
            "weight": 0.0,  # 初始权重为0
            "source_entities": [],  # 无实体
            "clues": [],
        })

    self.logger.info(f"Step2: {len(event_results)} 个事项通过KNN搜索")
    return event_results
```

---

### Step 3: 合并event去重

**逻辑**:
- 按 `event_id` 去重
- 如果同一个event在step1和step2都出现，**只保留step1的结果**（因为包含实体溯源信息）

**代码**:
```python
async def _step3_merge_events(
    self,
    sql_events: List[Dict[str, Any]],
    embedding_events: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    步骤3: 合并event并去重

    规则：优先保留SQL结果（step1），只添加ES独有的结果
    """
    event_map = {}

    # 先添加SQL结果
    for event in sql_events:
        event_map[event['event_id']] = event

    # 再添加ES独有结果
    for event in embedding_events:
        if event['event_id'] not in event_map:
            event_map[event['event_id']] = event

    merged_events = list(event_map.values())

    self.logger.info(
        f"Step3: 合并 {len(sql_events)} (SQL) + {len(embedding_events)} (ES) "
        f"= {len(merged_events)} 个事项"
    )

    return merged_events
```

---

### Step 4: 计算事项权重

**原逻辑**:
```
section_weight = 0.5 × score + ln(1 + Σ(key_weight × ln(1+count) / step))
```

**新逻辑**:
```
event_weight = 0.5 × score + ln(1 + Σ(entity_weight × entity_event_weight))
```

**参数说明**:
- `score`: event与query的余弦相似度（来自step1/2）
- `entity_weight`: 实体在expand阶段的权重
- `entity_event_weight`: EventEntity表中的weight字段

**代码**:
```python
async def _step4_calculate_weight_of_events(
    self,
    key_final: List[Dict[str, Any]],
    events: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    步骤4: 计算事项的初始权重向量

    公式: weight = 0.5 × score + ln(1 + entity_weight_sum)
    """
    # 构建 entity_id -> entity_weight 映射
    entity_weight_map = {
        (key.get("key_id") or key.get("id")): key["weight"]
        for key in key_final
    }

    for event in events:
        score = event.get("score", 0.0)

        # 计算实体权重和
        entity_weight_sum = 0.0
        for entity_id in event.get("source_entities", []):
            entity_weight = entity_weight_map.get(entity_id, 0.0)
            entity_weight_sum += entity_weight

        # 计算最终权重
        total_weight = 0.5 * score + math.log(1 + entity_weight_sum)
        event["weight"] = total_weight

        self.logger.debug(
            f"事项 {event['event_id'][:8]}... 权重: "
            f"score={score:.3f}, entity_sum={entity_weight_sum:.3f}, "
            f"weight={total_weight:.3f}"
        )

    return events
```

---

### Step 5: 构建事项关系图 + PageRank

**原逻辑（段落关系）**:
1. 事件关联（0.6）：共享event_id
2. 段落关联（0.2）：相邻段落
3. 实体关联（0.2）：包含相同key

**新逻辑（事项关系）**:
1. **实体关联（0.7）**：共享相同entity
2. **类别关联（0.3）**：相同category

**代码**:
```python
async def _step5_pagerank_of_events(
    self,
    events: List[Dict[str, Any]],
    key_final: List[Dict[str, Any]],
    damping: float = 0.85,
    iterations: int = 100
) -> List[Dict[str, Any]]:
    """
    步骤5: 事项PageRank排序

    关系图构建:
    - 实体关联（0.7）：共享相同实体的event之间建边
    - 类别关联（0.3）：相同category的event之间建边
    """
    n = len(events)

    # 初始化PageRank
    weights = np.array([e['weight'] for e in events])
    if weights.sum() > 0:
        pagerank = weights / weights.sum()
    else:
        pagerank = np.ones(n) / n

    # 构建关系图
    graph = defaultdict(list)

    # 1. 实体关联（权重0.7）
    entity_to_events = defaultdict(list)
    for i, event in enumerate(events):
        for entity_id in event.get("source_entities", []):
            entity_to_events[entity_id].append(i)

    entity_edges = 0
    for entity_id, event_indices in entity_to_events.items():
        if len(event_indices) > 1:
            for i in event_indices:
                for j in event_indices:
                    if i != j:
                        graph[i].append((j, 0.7))
                        entity_edges += 1

    self.logger.info(f"实体关联: {entity_edges} 条边")

    # 2. 类别关联（权重0.3）
    category_to_events = defaultdict(list)
    for i, event in enumerate(events):
        category = event.get("category", "")
        if category:
            category_to_events[category].append(i)

    category_edges = 0
    for category, event_indices in category_to_events.items():
        if len(event_indices) > 1:
            for i in event_indices:
                for j in event_indices:
                    if i != j:
                        graph[i].append((j, 0.3))
                        category_edges += 1

    self.logger.info(f"类别关联: {category_edges} 条边")

    # PageRank迭代（逻辑同原版）
    for iteration in range(iterations):
        new_pagerank = np.zeros(n)

        for i in range(n):
            incoming_score = 0.0
            for j in range(n):
                edges_from_j = graph.get(j, [])
                if not edges_from_j:
                    continue

                for target, edge_weight in edges_from_j:
                    if target == i:
                        total_out_weight = sum(w for _, w in edges_from_j)
                        if total_out_weight > 0:
                            incoming_score += pagerank[j] * edge_weight / total_out_weight

            new_pagerank[i] = (1 - damping) / n + damping * incoming_score

        # 检查收敛
        diff = np.abs(new_pagerank - pagerank).sum()
        if diff < 1e-6:
            self.logger.info(f"PageRank收敛于第{iteration+1}次迭代")
            pagerank = new_pagerank
            break

        pagerank = new_pagerank

    # 赋值PageRank
    for i, event in enumerate(events):
        event['pagerank'] = float(pagerank[i])

    # 排序
    sorted_events = sorted(events, key=lambda x: x['pagerank'], reverse=True)

    return sorted_events
```

---

### Step 6: 选择Top-N事项（保留溯源）

**原逻辑**:
- Top-N 段落 → 提取event_ids

**新逻辑**:
- 直接返回 Top-N 事项
- 保留溯源信息（source_entities, clues）

**代码**:
```python
async def _step6_get_topn_events(
    self,
    sorted_events: List[Dict[str, Any]],
    config: SearchConfig,
    tracker: Tracker
) -> Tuple[List[SourceEvent], Dict]:
    """
    步骤6: 取Top-N事项并生成final线索

    Returns:
        (事项列表, 事项到线索的映射)
    """
    topn = config.rerank.max_results
    final_events = sorted_events[:topn]

    # 查询完整的SourceEvent对象
    event_ids = [e['event_id'] for e in final_events]
    async with self.session_factory() as session:
        event_query = select(SourceEvent).where(SourceEvent.id.in_(event_ids))
        result_events = (await session.execute(event_query)).scalars().all()

    # 保持PageRank顺序
    event_order_map = {e['event_id']: idx for idx, e in enumerate(final_events)}
    result_events = sorted(result_events, key=lambda e: event_order_map[e.id])

    # 生成final线索（entity → event）
    for event_data in final_events:
        event_obj = next((e for e in result_events if e.id == event_data['event_id']), None)
        if not event_obj:
            continue

        # 为每个source_entity生成线索
        for entity_id in event_data.get('source_entities', []):
            entity_node = Tracker.build_entity_node({
                "id": entity_id,
                "key_id": entity_id,
                # ... 其他字段从key_final中获取
            }, tree_level=3)  # expand叶子层

            event_node = tracker.get_or_create_event_node(
                event_obj,
                "rerank",
                recall_method="entity",
                tree_level=4  # rerank层
            )

            tracker.add_clue(
                stage="rerank",
                from_node=entity_node,
                to_node=event_node,
                confidence=event_data['score'],
                relation="实体召回",
                display_level="final",
                metadata={
                    "method": "pagerank_entity_recall",
                    "pagerank": event_data['pagerank'],
                    "weight": event_data['weight']
                }
            )

    self.logger.info(f"Step6: 返回Top-{len(result_events)}事项")

    return result_events, {}
```

---

## 🔧 配置项修改

需要在 `SearchConfig.rerank` 中添加：

```python
class RerankConfig:
    # ... 原有配置

    # 🆕 事项相似度阈值
    event_similarity_threshold: float = 0.3  # 默认0.3

    # 🆕 是否使用事项级PageRank（False=段落级，True=事项级）
    use_event_level_pagerank: bool = False  # 默认False，保持兼容
```

---

## 📊 数据结构变化

### 原结构（段落）
```python
{
    "search_type": "sql",
    "section_id": "xxx",
    "article_id": "yyy",
    "rank": 1,
    "heading": "标题",
    "content": "内容",
    "score": 0.85,
    "weight": 1.2,
    "pagerank": 0.15,
    "event_ids": ["event1", "event2"],  # 段落关联的事项
}
```

### 新结构（事项）
```python
{
    "search_type": "sql",
    "event_id": "xxx",
    "title": "标题",
    "content": "内容",
    "category": "技术",
    "score": 0.85,
    "weight": 1.2,
    "pagerank": 0.15,
    "source_entities": ["entity1", "entity2"],  # 溯源：哪些实体召回
    "clues": [...],  # 溯源线索
}
```

---

## 🧪 测试策略

### 1. 功能开关
通过配置项 `use_event_level_pagerank` 控制使用新逻辑还是旧逻辑

### 2. 对比测试
```python
# 同时运行两种方法，对比结果
old_results = await self._pagerank_section_level(...)
new_results = await self._pagerank_event_level(...)

# 对比Top-10事项是否一致
```

### 3. 性能测试
- 新逻辑应该更快（跳过了段落查询）
- 内存占用应该更少（event数量 << section数量）

---

## 📈 预期收益

1. **性能提升**：
   - 跳过段落查询，减少SQL和ES查询次数
   - 事项数量远少于段落，PageRank迭代更快

2. **准确性提升**：
   - 直接对事项排序，避免段落→事项的损失
   - 向量相似度过滤，提前过滤不相关事项

3. **可解释性提升**：
   - 溯源信息更清晰（source_entities）
   - final线索直接是entity→event

---

## 🚀 实施计划

1. **阶段1**：添加新方法（保留旧方法）
2. **阶段2**：功能开关测试
3. **阶段3**：对比验证
4. **阶段4**：全量切换
5. **阶段5**：删除旧方法

---

**文档版本**: v1.0
**创建时间**: 2025-01-08
**状态**: ✅ 设计完成，待实施
