# Rerank（重排序）阶段

## 概述

Rerank 阶段是搜索流程的最后一个阶段，负责将 Recall 和 Expand 阶段召回的实体转换为最终的事项结果，并按相关度排序。

**核心功能**：从实体（Entity）到事项（Event）的映射和排序

**阶段位置**：Recall（召回实体）→ Expand（扩展实体）→ **Rerank（重排序事项）**

---

## 两种算法

Rerank 阶段提供两种算法，各有优势：

### 1. RRF 算法（快速）

**类名**：`RerankRRFSearcher`
**文件**：`dataflow/modules/search/rerank/rrf.py`

**特点**：
- ⚡ 速度快：直接从实体查找事项，跳过段落检索
- 🎯 准确度高：融合 Embedding + BM25 两种排序
- 💰 成本低：无需调用 LLM，无需段落级计算

**算法流程**：
```
1. 实体匹配：根据 key_final 查找关联事项（通过 EventEntity 表）
2. 事项去重：基于事项ID去重
3. Embedding 相似度计算（粗排）：计算与 query 的余弦相似度
4. 阈值过滤：过滤低于阈值的事项
5. BM25 计算：使用关键词匹配算法计算分数
6. RRF 融合：融合两种排序结果
7. Top-K 限制：返回前 K 个事项
```

**RRF 公式**：
```
RRF_score(event) = 1/(k + embedding_rank) + 1/(k + bm25_rank)
其中 k = 60（固定常数）
```

**适用场景**：
- 生产环境，需要快速响应
- 大规模数据处理
- 资源受限环境

---

### 2. PageRank 算法（精准）

**类名**：`RerankPageRankSearcher`
**文件**：`dataflow/modules/search/rerank/pagerank.py`

**特点**：
- 🎯 精度高：段落级检索，更细粒度
- 🔍 可解释性强：基于图算法，可追踪
- 📊 排序科学：PageRank 考虑段落之间的关联

**算法流程**：
```
1. Step1: 使用实体名称直接查找相关段落（Embedding 相似度）
2. Step2: 使用 query 查找相关段落（Embedding 相似度）
3. Step3: 去重合并段落
4. Step4: 计算段落权重（考虑匹配的实体数量和权重）
5. Step5: PageRank 排序段落
6. Step6: 从段落召回事项，聚合 PageRank 权重排序
```

**PageRank 算法**：
```python
# 阻尼因子 d = 0.85
# 迭代次数 = 10
PR(p) = (1 - d)/N + d * Σ (PR(q) / L(q))
其中：
- p: 当前段落
- q: 指向 p 的段落
- L(q): q 的出链数量
- N: 总段落数
```

**适用场景**：
- 高质量要求场景
- 需要详细可解释性
- 数据量适中

---

## API 使用

### 基础使用

```python
from dataflow.modules.search.rerank import RerankRRFSearcher, RerankPageRankSearcher

# 方式1：使用 RRF 算法（推荐）
rrf_searcher = RerankRRFSearcher()
result = await rrf_searcher.search(
    key_final=key_final,  # 来自 Expand 阶段
    config=search_config
)

# 方式2：使用 PageRank 算法
pagerank_searcher = RerankPageRankSearcher()
result = await pagerank_searcher.search(
    key_final=key_final,
    config=search_config
)
```

### 配置参数

```python
from dataflow.modules.search.config import SearchConfig

config = SearchConfig(
    source_config_id="my-source",
    query="查询文本",

    # Rerank 通用参数
    threshold=0.5,        # 相似度阈值
    top_k=10,             # 返回数量

    # 算法选择（在 SAG Processor 中使用）
    use_stage3=False,     # False=RRF, True=PageRank
)
```

### 返回格式

两种算法返回相同的数据结构：

```python
{
    "events": [
        # 事项对象列表（SourceEvent），附加属性：
        # - RRF 算法：
        #     - similarity_score: Embedding 相似度
        #     - bm25_score: BM25 分数
        #     - rrf_score: RRF 融合分数
        #     - embedding_rank: Embedding 排名
        #     - bm25_rank: BM25 排名
        # - PageRank 算法：
        #     - pagerank: PageRank 权重
        #     - related_sections_count: 关联段落数
        #     - clues: 关联的实体线索
    ],
    "clues": {
        "origin_query": "原始查询",
        "final_query": "重写后的查询（如有）",
        "query_entities": [...]  # 查询召回的实体
        "recall_entities": [...]  # 召回的实体
        "event_entities": {...}   # 事项-实体映射
    }
}
```

---

## 算法对比

| 维度 | RRF 算法 | PageRank 算法 |
|------|---------|---------------|
| **速度** | ⚡⚡⚡ 快 | ⚡⚡ 中等 |
| **精度** | ⭐⭐⭐ 好 | ⭐⭐⭐⭐ 很好 |
| **成本** | 💰 低 | 💰💰 中等 |
| **可解释性** | ⭐⭐ 一般 | ⭐⭐⭐⭐ 强 |
| **数据粒度** | 事项级 | 段落级 |
| **排序方法** | RRF 融合 | PageRank 图算法 |
| **适用场景** | 生产环境 | 高质量场景 |
| **推荐度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

**推荐组合**：
- **快速模式**：`use_fast_mode=True` + RRF（最快）
- **平衡模式**：`use_fast_mode=False` + RRF（推荐）
- **精准模式**：`use_fast_mode=False` + PageRank（最准）

---

## 调试和监控

### RRF 算法日志

```
✅ 步骤1-3: 从实体查找到 50 个关联事项
✅ 步骤4: Embedding计算完成，50 个事项有相似度分数
阈值过滤完成: 阈值=0.50, 过滤前=50个, 过滤后=30个, 过滤掉=20个
RRF 融合排序完成，耗时: 0.2341秒，返回 10 个事项

================================================================================
RRF 融合排序结果（Top 10）：
--------------------------------------------------------------------------------
Rank 1: 美团外卖获得新一轮融资
  Embedding: score=0.8532, rank=1
  BM25: score=15.4234, rank=2
  RRF: score=0.032258
...
```

### PageRank 算法日志

```
Step1完成：实体名称召回 120 个段落
Step2完成：Query召回 85 个段落
Step3: 去重后剩余 150 个段落
Step4: 计算段落权重完成
Step5: PageRank排序完成
Step6: 从段落召回 10 个事项
```

---

## 性能优化

### RRF 优化

1. **向量缓存**：使用 Elasticsearch 预存向量，避免实时计算
2. **批量处理**：分批获取向量（batch_size=100）
3. **快速分词**：使用 `fast_mode=True` 跳过 spaCy

### PageRank 优化

1. **段落过滤**：阈值过滤低相关段落
2. **迭代优化**：限制 PageRank 迭代次数（10次）
3. **Top-N 限制**：每步限制返回数量

---

## 常见问题

### Q: 什么时候用 RRF，什么时候用 PageRank？

A:
- **RRF**：生产环境、需要快速响应、数据量大
- **PageRank**：高质量要求、需要可解释性、数据量适中

### Q: 为什么 RRF 使用 k=60？

A: 这是 RRF 算法的经验值，用于平衡不同排序系统的影响。k 值越大，排名靠后的项目影响越小。

### Q: PageRank 的阻尼因子为什么是 0.85？

A: 0.85 是经典的 PageRank 阻尼因子，模拟用户有 85% 概率继续点击链接，15% 概率随机跳转。

### Q: 如何调整阈值？

A: 参考建议值：
- 高精度场景：0.6-0.8
- 平衡场景：0.4-0.6（默认 0.5）
- 高召回场景：0.2-0.4
- 调试场景：0.0（查看所有结果）

---

## 参考文档

- [Recall 阶段](./recall.md) - 实体召回
- [Expand 阶段](./expand.md) - 多跳扩展
- [Clue 机制](./clue.md) - 线索追踪
- [故障排查](./troubleshooting.md) - 常见问题

---

## 更新日志

**2025-01**：
- ✅ 重命名 Stage2.5 → RerankRRF, Stage3 → RerankPageRank
- ✅ 统一 Rerank 接口，抽象基类 BaseRerankSearcher
- ✅ 优化 RRF 算法性能，批量向量获取
- ✅ 增强日志输出，提供详细的排序过程
