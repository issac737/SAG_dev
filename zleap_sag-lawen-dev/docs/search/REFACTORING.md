# 搜索模块重构总结

## 🎯 重构目标

将 Stage1/2/2.5/3 的技术命名重构为 Recall/Expand/Rerank 的业务语义命名，提高代码可读性和可维护性。

---

## ✅ 完成的工作

### 1. 目录结构重构

#### 新增目录
```
dataflow/modules/search/
└── rerank/                      # 新建：重排序模块
    ├── __init__.py
    ├── base.py                  # 抽象基类
    ├── rrf.py                   # 原 stage2_5.py
    └── pagerank.py              # 原 stage3.py
```

#### 新增文件
```
dataflow/modules/search/
├── recall.py                    # 原 stage1.py（保留原文件向后兼容）
├── expand.py                    # 原 stage2.py（保留原文件向后兼容）
└── rerank/                      # 新建目录
```

---

### 2. 类名重构

| 原类名 | 新类名 | 文件位置 |
|--------|--------|----------|
| `Stage1Searcher` | `RecallSearcher` | `recall.py` |
| `Stage1Result` | `RecallResult` | `recall.py` |
| `Stage2Searcher` | `ExpandSearcher` | `expand.py` |
| `Stage2Result` | `ExpandResult` | `expand.py` |
| `Stage2_5Searcher` | `RerankRRFSearcher` | `rerank/rrf.py` |
| `Stage3Searcher` | `RerankPageRankSearcher` | `rerank/pagerank.py` |

新增抽象基类：
- `BaseRerankSearcher` - 所有 Rerank 算法的基类

---

### 3. Logger 名称更新

| 原名称 | 新名称 |
|--------|--------|
| `search.stage1` | `search.recall` |
| `search.stage2` | `search.expand` |
| `search.stage2_5` | `search.rerank.rrf` |
| `search.stage3` | `search.rerank.pagerank` |

---

### 4. 导入路径更新

#### 核心文件：`sag.py`

**修改前**：
```python
from dataflow.modules.search.stage1 import Stage1Searcher
from dataflow.modules.search.stage2 import Stage2Searcher
from dataflow.modules.search.stage2_5 import Stage2_5Searcher
from dataflow.modules.search.stage3 import Stage3Searcher
```

**修改后**：
```python
from dataflow.modules.search.recall import RecallSearcher
from dataflow.modules.search.expand import ExpandSearcher
from dataflow.modules.search.rerank import RerankRRFSearcher, RerankPageRankSearcher
```

#### 模块导出：`__init__.py`

**修改后**：
```python
from dataflow.modules.search.recall import RecallResult, RecallSearcher
from dataflow.modules.search.expand import ExpandResult, ExpandSearcher
from dataflow.modules.search.rerank import (
    BaseRerankSearcher,
    RerankRRFSearcher,
    RerankPageRankSearcher,
)

__all__ = [
    "RecallSearcher",
    "RecallResult",
    "ExpandSearcher",
    "ExpandResult",
    "BaseRerankSearcher",
    "RerankRRFSearcher",
    "RerankPageRankSearcher",
    "EventSearcher",
]
```

---

### 5. 文档重构

#### 新增文档
- `docs/search/recall.md` - 实体召回阶段文档（基于 stage1.md）
- `docs/search/expand.md` - 多跳扩展阶段文档（基于 stage2_readme.md）
- `docs/search/rerank.md` - 重排序阶段文档（合并 stage2_5.md + stage3.md）

#### 文档修复
- `docs/search/clue.md` - 修复部分乱码问题

---

## 📁 最终文件结构

```
dataflow/modules/search/
├── __init__.py                  # 更新：新的导出接口
├── config.py
├── searcher.py
├── recall.py                    # 新增：Recall 搜索器
├── expand.py                    # 新增：Expand 搜索器
├── rerank/                      # 新增：Rerank 模块
│   ├── __init__.py
│   ├── base.py                  # 新增：抽象基类
│   ├── rrf.py                   # 新增：RRF 算法
│   └── pagerank.py              # 新增：PageRank 算法
├── processor/
│   ├── __init__.py
│   ├── base.py
│   ├── sag.py                   # 更新：使用新的导入路径
│   ├── llm.py
│   └── rag.py
├── stage1.py                    # 保留：向后兼容
├── stage2.py                    # 保留：向后兼容
├── stage2_5.py                  # 保留：向后兼容
└── stage3.py                    # 保留：向后兼容

docs/search/
├── README.md
├── recall.md                    # 新增：Recall 文档
├── expand.md                    # 新增：Expand 文档
├── rerank.md                    # 新增：Rerank 文档
├── clue.md                      # 更新：修复乱码
├── troubleshooting.md
├── stage1.md                    # 保留：向后兼容
├── stage2_readme.md             # 保留：向后兼容
├── stage2_5.md                  # 保留：向后兼容
└── stage3.md                    # 保留：向后兼容
```

---

## 🔄 向后兼容性

为保持向后兼容，保留了所有原有文件：
- `stage1.py`, `stage2.py`, `stage2_5.py`, `stage3.py` 仍然存在
- 旧的导入路径仍然可用（但不推荐）
- 旧的类名仍然可以使用

**推荐迁移路径**：
```python
# 旧代码（仍然可用）
from dataflow.modules.search.stage1 import Stage1Searcher

# 新代码（推荐）
from dataflow.modules.search.recall import RecallSearcher
```

---

## 📊 重构影响范围

### 核心修改文件
1. ✅ `dataflow/modules/search/__init__.py` - 导出接口
2. ✅ `dataflow/modules/search/processor/sag.py` - 导入和调用
3. ✅ `dataflow/modules/search/recall.py` - 新建
4. ✅ `dataflow/modules/search/expand.py` - 新建
5. ✅ `dataflow/modules/search/rerank/` - 新建目录及文件

### 文档更新
1. ✅ `docs/search/recall.md` - 新建
2. ✅ `docs/search/expand.md` - 新建
3. ✅ `docs/search/rerank.md` - 新建
4. ✅ `docs/search/clue.md` - 乱码修复

---

## ✅ 验证结果

```python
# 导入验证
from dataflow.modules.search import (
    RecallSearcher,
    ExpandSearcher,
    RerankRRFSearcher,
    RerankPageRankSearcher,
)
# ✅ 所有导入成功

# SAGSearchProcessor 验证
from dataflow.modules.search.processor.sag import SAGSearchProcessor
sag = SAGSearchProcessor(llm, pm)
# ✅ 内部使用新的搜索器：
#   - recall_searcher: RecallSearcher
#   - expand_searcher: ExpandSearcher
#   - rerank_rrf_searcher: RerankRRFSearcher
#   - rerank_pagerank_searcher: RerankPageRankSearcher
```

---

## 🎯 业务语义对照

| 技术术语 | 业务语义 | 说明 |
|---------|---------|------|
| Stage1 | Recall（召回） | 从 query 召回相关实体 |
| Stage2 | Expand（扩展） | 通过多跳扩展发现更多实体 |
| Stage2.5 | Rerank-RRF（快速重排） | 使用 RRF 算法从实体查找事项 |
| Stage3 | Rerank-PageRank（精准重排） | 使用 PageRank 算法从段落聚合事项 |

---

## 📝 待优化项

### 配置参数重命名（可选）

当前配置参数仍使用 `stage` 前缀：
```python
class SearchConfig:
    enable_stage2: bool = True          # 建议改为: expand_enabled
    use_stage3: bool = False            # 建议改为: rerank_algorithm="rrf"|"pagerank"
    stage2_convergence_threshold: float # 建议改为: expand_convergence_threshold
```

**建议的新参数命名**：
```python
class SearchConfig:
    # Recall 参数
    recall_similarity_threshold: float = 0.7
    recall_max_keys: int = 100
    recall_top_n: int = 20

    # Expand 参数
    expand_enabled: bool = True
    expand_max_hops: int = 2
    expand_convergence_threshold: float = 0.01

    # Rerank 参数
    rerank_algorithm: str = "rrf"  # "rrf" | "pagerank"
    rerank_threshold: float = 0.5
    rerank_top_k: int = 10
```

### 文档乱码修复（部分完成）

`clue.md` 文件部分乱码已修复，但仍有少量未处理。可能需要完全重写该文件。

---

## 🚀 使用示例

### 方式1：通过 EventSearcher（推荐）

```python
from dataflow.modules.search import EventSearcher
from dataflow.modules.search.config import SearchConfig

searcher = EventSearcher()
result = await searcher.search(
    SearchConfig(
        source_config_id="my-source",
        query="查询文本",
        mode="sag",
        use_stage3=False,  # False=RRF, True=PageRank
    )
)
```

### 方式2：直接使用搜索器

```python
from dataflow.modules.search import RecallSearcher, ExpandSearcher, RerankRRFSearcher

# 分步执行
recall_searcher = RecallSearcher(llm, pm)
expand_searcher = ExpandSearcher(llm, pm, recall_searcher)
rerank_searcher = RerankRRFSearcher()

# Step1: Recall
recall_result = await recall_searcher.search(config)

# Step2: Expand
expand_result = await expand_searcher.search(config, recall_result)

# Step3: Rerank
final_result = await rerank_searcher.search(expand_result.key_final, config)
```

---

## 📈 重构收益

### 1. 代码可读性提升
- ✅ 业务语义清晰：Recall、Expand、Rerank 一目了然
- ✅ 降低学习成本：新人无需记忆 Stage1/2/3 对应的功能

### 2. 可维护性提升
- ✅ 模块化设计：Rerank 算法独立目录，易于扩展
- ✅ 抽象基类：`BaseRerankSearcher` 统一接口

### 3. 可扩展性提升
- ✅ 新增 Rerank 算法简单：只需继承 `BaseRerankSearcher`
- ✅ 示例：未来可轻松添加 `RerankLambdaMART` 等算法

### 4. 文档友好
- ✅ `rerank.md` 一个文档讲清楚所有重排序算法
- ✅ 算法对比表，方便用户选择

---

## 🎓 最佳实践

### 推荐命名规范
- **模块**：使用业务语义（recall, expand, rerank）
- **算法**：算法名作为后缀（RRF, PageRank）
- **配置**：阶段名_参数名（recall_threshold, expand_max_hops）

### 推荐目录结构
```
模块名/
├── __init__.py
├── 核心功能.py
└── 子模块/
    ├── __init__.py
    ├── base.py
    ├── 算法1.py
    └── 算法2.py
```

---

**重构日期**：2025-01
**重构作者**：Claude Code
**影响范围**：搜索模块核心代码和文档
