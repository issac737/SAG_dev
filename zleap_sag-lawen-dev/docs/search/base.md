# SAG 系统算法实现原理与开发指南

## 概述

SAG (SQL-Augmented Generation) 是下一代 RAG 系统，一个 SQL 驱动的检索增强生成系统。

**官方介绍**: https://a63cf762.302ai.app/

## 一、数据处理流程

### 1.1 整体流程

```
原始文档 → Summary提取 → 文档分块 → Event提取 → Key属性提取 → 存储(SQL+向量)
```

### 1.2 详细步骤

#### 步骤1: 文档摘要生成
- 使用 sumy 提取文档重要句子
- 让 LLM 对重要句子进行总结
- 生成基础的文档 summary

#### 步骤2: 文档分块
- 将文档分块得到多个 `[content]`
- 每个分块包含完整的语义单元

#### 步骤3: Event 事件提取
- 使用 LLM 对 `分块 + summary` 提取事项 event
- 一个分块可能包含多个事件（例如讲了5件事，可以提取出5个event）
- **原则**: 事件原子性

#### 步骤4: Key 属性提取
- 使用 LLM 对 `event + summary` 提取属性 key
- 每个 event 可能包含多个属性 key
- 属性包含 type 和 content

**属性示例**:
```json
{
  "type": "主题",
  "content": "乔布斯"
}
{
  "type": "行为",
  "content": "创建苹果公司"
}
{
  "type": "标签",
  "content": "苹果"
}
{
  "type": "标签",
  "content": "iphone"
}
```

**原则**: 语义原子性

#### 步骤5: 数据存储
- 将 `[content]`、`[event]`、`[key]` 分别存入 SQL 和向量数据库
- SQL 存储它们的多对多关系
- 向量数据库存储语义信息
- 支持混合检索

### 1.3 属性提取预检索机制

**问题**: 不同 event 生成的相同属性的 key 文字需要尽可能一致（例如避免 "302.AI"、"302ai"、"ai302" 等不同表述）

**解决方案**: 在提取 key 时进行预检索

#### 预检索流程

1. **向量化新 Event**: 将新的 event 文本进行向量化

2. **检索相关 Key**: 在 Key 向量库中检索 Top-K 个最相关的 `direct_keys` (例如 K=10)

3. **检索相似 Event**: 在 Event 向量库中进行相似度搜索，找到 Top-N 个最相似的 `similar_events` (例如 N=3)

4. **获取关联 Key**: 通过 SQL 查询，获取这 N 个 `similar_events` 所关联的所有 `keys_from_events`

5. **获取属性类型**: 在 Key 数据库使用 SQL 查询出所有属性的 type（维度），用于约束

6. **LLM 提取**: 将这些 keys 作为参考列表，注入到 LLM 的 Prompt 中，让其为新 event 提取 key

#### 提取 Prompt 模板

```
你是一个信息提取专家。请根据下面的【事件】，提取出核心的属性，属性的type必须在属性类别中选择。

【事件】:
{{event_content}}

【属性type】
{{type}}

---

**【参考属性列表】(请优先使用或对齐到列表中的标准名称):**

**直接相关属性:**
{{direct_keys}}

**相似事件中的Key示例 (用于参考):**
{{keys_from_events}}

---

**提取规则:**
1. 提取的属性key必须是事件中的核心实体、概念或行为。
2. 每个key包含'type'和'content'。
3. 请优先使用或对齐到【直接相关实体】列表中的标准名称。
4. 请参考【相似事件中的Key示例】，来提取当前事件的属性。
5. 如果事件中出现了全新的、参考列表中没有的核心概念，可以直接提取。

**输出格式 (JSON):**
[...]
```

### 1.4 属性字段设计

每个属性包含以下字段：

| 字段 | 说明 | 备注 |
|------|------|------|
| `type` | 属性维度 | 例如：人物、地点、标签 |
| `value_string` | 语义类型的属性值 | 可以入向量库 |
| `value_number` | 数字类型的属性值 | 不可入向量库 |
| `value_bool` | 布尔类型的属性值 | 不可入向量库 |

**规则**:
- 三个 value 类型只能选一个
- 如果选了非 string 类型，不可入向量库
- 方便针对属性做 SQL 筛选

---

## 二、检索过程

### 2.1 检索模式

所有检索均遵循: **query → (event ↔ key) → content**

**核心思想**: 属性驱动，先找属性再找原文

#### 可选方案

1. **属性驱动**: `query → (key ↔ event) → content` (推荐，需要 PageRank)
2. **事件驱动**: `query → (event ↔ key) → content` (简化版，省略 PageRank)
3. **双重检索**: 属性驱动 + 事件驱动结合

---

### 2.2 第一阶段：找到关联的属性 Key

#### 流程图概览

```
Query → Key检索(语义扩展) → Event检索(SQL精准匹配) 
     → Event检索(语义匹配) → 过滤交集(精准筛选)
     → Event-Key权重计算 → Event-Key-Query权重计算
     → 反向激活Key权重 → 动态剪枝
```

#### 详细步骤

**步骤1: Query找Key (语义扩展)**

- 如果请求中传入了 key，通过向量相似度找到关联属性 `[key-query-related]`
- 得到相似度向量 `(k1)`
- 如果没有传入 key，直接使用 query 匹配相似的 key

**目的**: 提取问题的属性，找到数据库中有关联的属性。由于直接 SQL 不一定对得上，所以要用语义匹配。

---

**步骤2: Key找Event (精准匹配)**

- 通过 `[key-query-related]` 用 SQL 找到所有关联事项 `[Event-key-query-related]`

**目的**: 通过问题联想属性，找到语义相似的属性，再找到对应的事项（比较宽泛）

---

**步骤3: Query再找Event (语义匹配)**

- 通过向量相似度找到 query 关联事项 `[Event-query-related]`
- 得到相似性向量 `(e1)`

**目的**: 直接通过问题语义找事项，类似传统 RAG（比较精准）。这里也可以做多次检索，不断合并 event 向量再搜索 event，实现 event 级别的多跳。

---

**步骤4: 过滤Event (精准筛选)**

- `[Event-query-related]` 和 `[Event-key-query-related]` 取交集
- 得到新的 `[Event-related]` 和 `[Key-Related]`

**目的**: 选择既语义相关，又有属性关联的 event（精准筛选）

---

**步骤5: 计算Event-Key权重向量 (相似度关联)**

根据每个 event 包含 key 的情况，将对应 key 的权重 `(k1)` 相加：

$$W_{event-key}(e_j) = \sum_{k_i \in e_j} (k_1)_i$$

**目的**: 包含重要 key 越多的 event，越重要

---

**步骤6: 计算Event-Key-Query权重向量 (相似度关联)**

将 `(event-key)` 与 `(e1)` 相乘，得到新的 `(e2)` 向量：

$$W_{e2}(e_j) = W_{event-key}(e_j) \cdot (e_1)_j$$

**结果**: `(event-key-query)` 同时包含 key 的相似度信息和 query 的相似度信息，是一个复合的 event 相似度向量。

---

**步骤7: 反向计算Key权重向量 (反向激活)**

每个 event 都有权重后，反向得出 event 里所有 key 的重要性：

$$W_{key-event}(k_i) = \sum_{e_j \text{ contains } k_i} W_{e2}(e_j)$$

**目的**: 
- event 越重要，key 就越重要
- key 在 event 里出现越多，就越重要

---

**步骤8: 动态剪枝**

- 设置相似度阈值提取重要的 key
- 或提取 top-n 重要的 key
- 得到数组 `[key-final]` 和对应的权重 `(key-final)`
- 每个 key 记录一个步数向量 `(step)`，第一步时所有值为 1

---

**阶段总结**: 通过 **相似度关联 + 反向扩散**，联想出与 query 最相关的 key。如果不需要多跳，此时可以结束。

---

### 2.3 第二阶段：多跳循环

#### 流程图概览

```
[key-final] → Event检索(精准匹配) → 相似度计算
          → Event-Key权重 → Event-Key-Query权重
          → 反向激活 → 动态剪枝 → 判断是否继续
```

#### 详细步骤

**步骤1: Key找Event (精准匹配)**

- 根据 `[key-final]`，用 SQL 查找所有关联的 event
- 得到新的 `[Event-key-related-2]`

**注意**: 这里没再做语义扩展，避免范围过大。如果未来发现经常匹配不到，可以在这里做一次语义扩展。

---

**步骤2: 相似度关联**

- 计算原始 query 和新的 `[Event-key-related-2]` 的相似度
- 得到相似性向量 `(e-query-2)`

**目的**: 每一步都使用原始 query 约束多跳，尽快收敛

---

**步骤3: 计算Event-Key-2权重向量 (相似度关联)**

根据每个 event 包含 `key-final` 的情况，将对应 key 的权重 `(key-final)` 相加：

$$W_{event-key-2}(e_j) = \sum_{k_i \in e_j} W_{key-final}(k_i)$$

**目的**: 将新的 event 和新的 key 关联上

---

**步骤4: 计算Event-Key-Query权重向量 (相似度关联)**

将 `(event-key-2)` 与 `(e-query-2)` 相乘：

$$W_{e-jump-2}(e_j) = W_{event-key-2}(e_j) \cdot (e_{query-2})_j$$

**目的**: 用原始 query 约束 event 权重

---

**步骤5: 反向计算Key权重向量 (反向激活)**

查询每个 key 对应 event 的向量值，相加得到新的 `(key-event)` 向量

---

**步骤6: 动态剪枝**

- 设置相似度阈值或 top-n
- 得到新的 `[key-final-2]` 和权重 `(key-final-2)`
- 步数向量 `(step)` 中新增的属性步数为 2

---

**步骤7: 多跳循环**

- 根据步数或收敛情况（key 的增加数量）判断是否继续计算 `[key-final-3]`
- 一般步数 ≤ 4

---

**步骤8: 最终结果**

- 得到 `[key-final]`
- 包含对应的 `(k-final)` 和步数向量 `(step)`

---

**阶段总结**: 整个过程就是 **属性 → 事件 → 更多属性 → 更多事件 → 更多属性**，并且在过程中计算相似度，通过相似度剪枝。

---

### 2.4 第三阶段：找到最重要的段落

#### 流程图概览

```
[key-final] → Content检索(精准匹配) → Content检索(语义匹配)
          → 合并Content → 初始权重计算 → PageRank排序
```

#### 详细步骤

**步骤1: Key找Content (精准匹配)**

- 根据 `[key-final]`，SQL 提取所有对应的原文段落 `[content-key-related]`
- 计算和 query 的相似性 `(s1)`

---

**步骤2: Query找Content (语义匹配)**

- 根据 query 通过向量相似度 + BM25
- 在向量库找到所有符合的原文段落 `[content-query-related]`
- 得到相似性向量 `(s2)`

**目的**: 传统方式，通过 query 找原文块

---

**步骤3: 多路检索**

- 合并 `[content-key-related]` 和 `[content-query-related]`
- 得到 `[content-related]`

---

**步骤4: 相似度关联 - 计算初始权重**

段落的权重向量算法：

$$W_{init}(c_j) = 0.5 \cdot s(c_j, Q) + \ln\left(1 + \sum_{k_i \in c_j \cap K_f} \frac{W_{K,f}(k_i) \cdot \ln(1 + count(k_i, c_j))}{step(k_i)}\right)$$

**公式解释**:
- 每个段落权重 = `0.5 × 段落和query的相似性` + `ln(1 + 段落包含的各key权重之和)`
- key 权重计算考虑：
  - key 的重要性 `W_{K,f}(k_i)`
  - key 在段落中出现的次数 `count(k_i, c_j)`
  - key 的步数 `step(k_i)`（步数越大，权重越小）

**目的**: 考虑段落和 query 原始相似性，以及段落包含多少关键 key

---

**步骤5: 顺序重排 - PageRank**

- 此时每个 key 和每个段落都有自己的初始权重分数
- key 和段落之间存在多对多关系
- 可以进行 PageRank 算法

**本质**: 和 query 越相似、属性越多的原文，分数越高

---

**步骤6: 最终输出**

- 根据 PageRank 得到段落的排序
- 取 top-n 重要的段落
- 找到对应的 event
- 组合在一起，交给 LLM 进行回答

---

## 三、查询过程

### 3.1 搜索函数定义

所有检索过程可以视为一个原子性的搜索函数：

```python
def search(query, keys=None, sql=None):
    """
    query: 用户问题
    keys: LLM提取的关键属性
    sql: LLM在查询时传入的限制SQL语句
    """
    pass
```

---

### 3.2 极速查询

**适用场景**: 对延迟极为敏感的领域

**特点**: 
- LLM 完全不参与
- 直接传入 query
- 完全由向量匹配

**调用方式**:
```python
search(query)
```

---

### 3.3 普通查询

**流程**:

#### 步骤1: 扩充上下文
- 通过原始 Query 进行向量查询
- 查询到关联的 event 和 key
- 作为背景传递给 LLM

#### 步骤2: 问题重写
- 让 LLM 根据背景和提示词指示
- 扩展用户原有问题
- 提取相关属性

#### 步骤3: 执行搜索
```python
search(query_after, key)
```

---

### 3.4 深入查询

**背景**: 对于深入查询，只靠单次 LLM 的泛化能力不够，需要实现 LLM 多次调用

#### 步骤1: 扩充上下文
- 通过原始 Query 进行向量查询
- 查询到关联的 event 和 key
- 作为背景传递给 LLM

---

#### 步骤2: 生成DAG子查询

让 LLM 生成 DAG 子查询，包含并行和链式调用。

**Prompt 模板**:

```
You are a meticulous planning agent. Your goal is to create a detailed, step-by-step reasoning plan in the form of a Directed Acyclic Graph (DAG) to answer a complex user question.

Follow these steps carefully:

Step 1: Deconstruct the Question (Your internal thought process)
First, think about the user's question. Break it down into the smallest logical pieces. Identify the entities, the relationships, and the sequence of information needed. Write down your thoughts in a <thinking> block.

Step 2: Define Sub-questions (Nodes)
Based on your deconstruction, define a set of clear, answerable sub-questions. Assign a unique ID (q1, q2, q3, ...) to each sub-question.

Step 3: Identify Dependencies (Edges)
For each sub-question, determine if it depends on the answer of any other sub-question. Clearly state these dependencies. For example, "q3 depends on the answers from q1 and q2".

Step 4: Generate the Final JSON Output
Finally, compile your plan into a single JSON object. The JSON must contain a nodes list and an edges list, following the structure you defined. Do not include the <thinking> block in the final JSON.

User Question:
{{query}}

Your Response:
{
  "nodes": [
    {
      "id": "q1",
      "question": "Who is the lead actor of the movie 'The Dark Knight'?"
    },
    {
      "id": "q2",
      "question": "What year was the movie 'Inception' released?"
    },
    {
      "id": "q3",
      "question": "What is the filmography (list of movies) of the actor identified in q1?"
    },
    {
      "id": "q4",
      "question": "Filter the list of movies from q3 to include only those released before the year identified in q2."
    }
  ],
  "edges": [
    {
      "source": "q1",
      "target": "q3",
      "description": "The filmography list in q3 depends on the name of the lead actor identified in q1."
    },
    {
      "source": "q2",
      "target": "q4",
      "description": "Filtering the movies in q4 requires the release year of 'Inception' from q2 as the cutoff date."
    },
    {
      "source": "q3",
      "target": "q4",
      "description": "Filtering in q4 is performed on the filmography list obtained in q3."
    }
  ]
}
```

---

#### 步骤3: 执行子查询

根据 DAG 的链路，执行子查询：

```python
search(query_DAG_1, key1)
search(query_DAG_2, key2)
```

---

#### 步骤4: 子查询循环

- 每次执行完都需要使用 LLM 对子查询进行总结
- 根据预设的子 query 生成新的 query 和 key
- 带入下一轮查询

```python
search(query_DAG_1_1, key1_1)
```

---

#### 步骤5: ReAct循环

- 执行完所有子查询后
- 带上每一步的问题 + 答案，再次交给 LLM
- 判断是否可以回答
- 如果不能，根据现有线索，再继续生成新的 DAG 子查询（ReAct）

---

## 四、聚类过程

**应用场景**: 生成报告时，需要将一定范围内的 event 进行分类展示

**方法**: 
1. 根据属性 key 进行简单分类
2. 根据 event 的含义进行分类（本节重点）

---

### 4.1 第一阶段：数据准备

#### 收集数据

筛选出一批 `[event]`，并提取：

1. **Event 数据**: 语义向量
```python
Event = [{'id': e1, 'vector': [...]}, ...]
```

2. **Key 数据**: key 数组
```python
Key = {k1, k2, ...}
```

3. **关系映射**: event 和 key 的多对多关系
```python
Map = {e1: {k1, k3}, e2: {k3, k5}, ...}
```

**图模型**: 可以把 event 看成图的节点，共同拥有一个 key 就是有一条边

---

#### 计算 IDF 权重

对不同 key 计算 IDF，进行加权：

$$IDF(k) = \log\left(\frac{\text{总事件数}}{\text{拥有key k的事件数}}\right)$$

**原理**: 在 event 里越稀有的 key，越重要

**结果**:
```python
keys_data = [{'id': k1, 'idf': 1.5}, ...]
```

---

### 4.2 第二阶段：计算边权重

#### 计算 Key 边权重

遍历所有 event 对，计算共享 key 的权重：

```python
for i in range(len(events_list)):
    for j in range(i + 1, len(events_list)):
        e_i = events_list[i]
        e_j = events_list[j]
        
        # 找到共享的key
        shared_keys = event_key_map[e_i].intersection(event_key_map[e_j])
        
        # 将共享的key的idf相加
        w_key = sum(keys_data[key_id]['idf'] for key_id in shared_keys)
        
        # 对w_key进行归一化，控制在[0,1]区间
        normalized_W_key = normalize(w_key)
```

---

#### 归一化算法

使用 Z-score 标准化 + Sigmoid 映射：

$$z\_score\_W\_key(i,j) = \frac{W\_key(i,j) - mean(W\_key)}{std\_dev(W\_key)}$$

$$normalized\_W\_key = sigmoid(z\_score\_W\_key) = \frac{1}{1 + e^{-z\_score\_W\_key}}$$

**注意**: 需要把所有 `w_key` 都算出来才能进行归一化

---

#### 计算语义相似度

```python
event_vectors = np.array([event['vector'] for event in events_data])
semantic_sim_matrix = cosine_similarity(event_vectors)
sim_semantic = semantic_sim_matrix[i, j]
```

---

#### 融合边权重

```python
alpha = 0.7  # alpha代表key的关系有多重要
final_weight = alpha * normalized_w_key + (1 - alpha) * sim_semantic
```

---

### 4.3 第三阶段：运行社区发现算法

#### 构建图

```python
import networkx as nx
import community as community_louvain  # python-louvain库
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

G = nx.Graph()
G.add_nodes_from(events_list)

for i in range(len(events_list)):
    for j in range(i + 1, len(events_list)):
        # ... 计算 final_weight (省略)
        
        if final_weight > 0.1:  # 过滤弱连接
            G.add_edge(e_i, e_j, weight=final_weight)
```

**阈值说明**: `W_final(ei, ej)` 大于阈值（例如 0.1）才添加边，过滤掉非常弱的关联

---

#### 运行 Louvain 算法

```python
# 运行louvain算法
partition = community_louvain.best_partition(G, weight='weight')

# 输出结果
# partition是一个字典: {event_id: community_id}
print("事件分类结果:", partition)

# 处理partition来展示每个分类下的事件列表
clusters = {}
for event_id, cluster_id in partition.items():
    if cluster_id not in clusters:
        clusters[cluster_id] = []
    clusters[cluster_id].append(event_id)

print("分成的类别及包含的事件:", clusters)
```

---

#### LLM 生成标题

- 此时已根据语义和 key 的关联，自动创建了不同的 event 类别
- 用 event 的内容和属性让 LLM 做一次总结标题即可

---

### 4.4 可调节参数

| 参数 | 说明 | 影响 |
|------|------|------|
| IDF 计算 | 是否计算 IDF | 不计算时，所有 IDF 都为 1 |
| Key 类型过滤 | 只计算部分类型的 key | 可以剔除比如时间等 |
| Alpha 值 | event 语义和 key 权重融合比例 | alpha 越小，越和 event 自身语义相关 |
| 边权重阈值 | 过滤弱连接的阈值 | 阈值越大，图越稀疏 |

---

## 五、附录

### 5.1 IDF 计算完整代码

```python
import math
import random

# --- 1. 准备数据 ---

# Event数组: 假设我们有200个事件
events = [{'id': f'e{i}'} for i in range(1, 201)]

# Key集合: 所有出现过的key的ID
keys = {f'k{i}' for i in range(1, 11)}  # k1, k2, ..., k10

# Map: 事件与key的关系字典
# 为了演示，我们手动创建一个分布不均的map
# k1, k2, k3 是常见key
# k7, k8, k9, k10 是稀有key
event_key_map = {}

for event in events:
    # 每个事件随机关联3到7个key
    num_keys_for_event = random.randint(3, 7)
    
    # 构造一个偏向常见key的选择池
    # k1, k2, k3的出现概率更高
    key_pool = ['k1', 'k1', 'k1', 'k2', 'k2', 'k3', 'k4', 'k5', 'k6', 'k7', 'k8', 'k9', 'k10']
    
    associated_keys = set(random.sample(key_pool, num_keys_for_event))
    event_key_map[event['id']] = associated_keys

# 打印示例数据
print("--- 模拟数据示例 ---")
print(f"总事件数 (N): {len(events)}")
print(f"总Key数: {len(keys)}")
print(f"event 'e1' 关联的 keys: {event_key_map.get('e1')}")
print(f"event 'e2' 关联的 keys: {event_key_map.get('e2')}\n")


# --- 2. 计算每个Key的文档频率 (Document Frequency, df) ---

# df是一个字典，用来存储每个key在多少个事件中出现过
# key: key_id, value: 出现次数
document_frequency = {key_id: 0 for key_id in keys}

# 遍历event_key_map中的每一个事件
for event_id, associated_keys in event_key_map.items():
    # 对于这个事件所拥有的每一个key
    for key_id in associated_keys:
        # 确保这个key在我们关心的keys集合里
        if key_id in document_frequency:
            # 将这个key的出现次数+1
            document_frequency[key_id] += 1

print("--- 计算文档频率 (df) ---")
print("每个key在多少个事件中出现过:")
# 为了方便查看，按出现次数排序
sorted_df = sorted(document_frequency.items(), key=lambda item: item[1], reverse=True)
for key_id, count in sorted_df:
    print(f"  - Key '{key_id}': {count} 次")
print("\n")


# --- 3. 计算每个Key的逆文档频率 (Inverse Document Frequency, IDF) ---

# N是总事件数
N = len(events)

# idf_scores字典用来存储最终结果
idf_scores = {}

# 遍历刚才计算好的df
for key_id, df_count in document_frequency.items():
    # IDF公式: log( N / (df + 1) )
    # +1 是为了防止df_count为0（虽然在这里不会发生，但这是标准做法），也叫平滑
    idf_value = math.log(N / (df_count + 1))
    
    idf_scores[key_id] = idf_value

print("--- 计算逆文档频率 (IDF) ---")
print("每个key的IDF分数 (分数越高，代表key越稀有，区分度越高):")
# 为了方便查看，按IDF分数排序
sorted_idf = sorted(idf_scores.items(), key=lambda item: item[1], reverse=True)
for key_id, score in sorted_idf:
    # 使用 f-string 格式化输出，保留4位小数
    print(f"  - Key '{key_id}': {score:.4f}")
```

---

## 六、参考资源

- **官方网站**: https://a63cf762.302ai.app/
- **核心算法**: PageRank, Louvain, BM25, Cosine Similarity
- **关键技术**: SQL + Vector Database, Multi-hop Reasoning, DAG Query Planning

---

## 七、开发指南

### 7.1 实现优先级

1. **第一阶段**: 实现基础数据处理流程（Summary → Content → Event → Key）
2. **第二阶段**: 实现单步检索（第一阶段检索）
3. **第三阶段**: 实现 PageRank 排序
4. **第四阶段**: 实现多跳检索
5. **第五阶段**: 实现 DAG 深入查询
6. **第六阶段**: 实现聚类功能

### 7.2 性能优化建议

1. **向量检索**: 使用 HNSW 索引加速
2. **SQL 查询**: 建立合适的索引，优化多对多关系查询
3. **缓存策略**: 缓存常用的 event-key 关系
4. **并行处理**: DAG 子查询可并行执行
5. **剪枝策略**: 合理设置阈值，避免计算爆炸

### 7.3 关键注意事项

1. **属性一致性**: Key 提取时的预检索机制非常重要
2. **步数控制**: 多跳检索步数一般 ≤ 4
3. **权重平衡**: 调整 alpha 参数平衡语义和属性的重要性
4. **收敛判断**: 根据 key 增加数量判断是否继续多跳

---

**文档版本**: v1.0  
**最后更新**: 2025-10-20

