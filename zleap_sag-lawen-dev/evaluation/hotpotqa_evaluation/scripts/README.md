# HotpotQA 评估脚本使用指南

本目录包含两个核心脚本，用于处理 HotpotQA 数据集和评估检索召回性能。

## 目录

- [脚本概述](#脚本概述)
- [配置文件说明 (config.py)](#配置文件说明-configpy)
- [1. upload_information.py - 数据处理与上传](#1-upload_informationpy---数据处理与上传)
- [2. retrieve_recall.py - 检索召回评估](#2-retrieve_recallpy---检索召回评估)
- [文件结构说明](#文件结构说明)
- [完整工作流程](#完整工作流程)

---

## 脚本概述

| 脚本名称 | 功能 | 输入 | 输出 |
|---------|------|------|------|
| `upload_information.py` | 处理 HotpotQA 数据集并上传到系统 | HotpotQA 原始数据集 | 语料库、标准答案、处理结果 |
| `retrieve_recall.py` | 评估检索系统的召回性能 | 语料库、标准答案 | 检索结果、召回评估 |

---

## 配置文件说明 (config.py)

配置文件位于 `evaluation/hotpotqa_evaluation/config.py`，包含所有脚本的全局配置。

### 配置项说明

#### 1. 路径配置

| 配置项 | 类型 | 配置方式 | 说明 |
|--------|------|----------|------|
| `BASE_DIR` | Path | 自动检测 | 评估模块的基础目录 |
| `DATA_DIR` | Path | config.py | 数据存储目录 |
| `HOTPOTQA_DATASET_PATH` | str | **环境变量** | **HotpotQA 数据集路径（必须配置）** |
| `CORPUS_OUTPUT` | Path | config.py | 语料库输出路径（旧版，新版使用时间戳文件夹） |
| `ORACLE_OUTPUT` | Path | config.py | 标准答案输出路径（旧版，新版使用时间戳文件夹） |

**重要提示**：
- `HOTPOTQA_DATASET_PATH` 通过**环境变量**配置，请在项目根目录的 `.env` 文件中设置
- `.env` 文件已被 `.gitignore` 忽略，每个开发者独立配置，不会互相影响

**配置方法**：在项目根目录的 `.env` 文件中添加：

```bash
# HotpotQA 数据集路径（根据你的本地路径修改）
# Windows 示例: C:\Users\user\Downloads\datasets--hotpotqa--hotpot_qa\snapshots\xxx
# macOS/Linux 示例: /Users/username/data/datasets--hotpotqa--hotpot_qa/snapshots/xxx
HOTPOTQA_DATASET_PATH=/your/path/to/hotpotqa/dataset
```

#### 2. 数据集配置

| 配置项 | 类型 | 可选值 | 默认值 | 说明 |
|--------|------|--------|--------|------|
| `DATASET_CONFIG` | str | `"distractor"` / `"fullwiki"` | `"distractor"` | 使用的数据集配置 |
| `DATASET_SPLIT` | str | `"train"` / `"validation"` | `"validation"` | 使用的数据集分割 |
| `SAMPLE_LIMIT` | int / None | 任意整数 或 `None` | `None` | 处理的样本数量限制 |

**配置说明**：

- **DATASET_CONFIG**：
  - `"distractor"`：每个问题包含10个文档（2个gold + 8个distractor）
  - `"fullwiki"`：开放域设置，需要从整个维基百科检索
  - 推荐使用 `"distractor"` 进行快速评估

- **DATASET_SPLIT**：
  - `"train"`：训练集（约90,000个问题）
  - `"validation"`：验证集（约7,405个问题）
  - 推荐先使用 `"validation"` 进行测试

- **SAMPLE_LIMIT**：
  - `None`：使用全部样本
  - 设置数字：只处理前N个样本（用于快速测试）
  - 示例：`SAMPLE_LIMIT = 100` 只处理前100个问题

#### 3. 处理配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `ENABLE_DEDUPLICATION` | bool | `True` | 是否启用语料库去重 |
| `VERBOSE` | bool | `True` | 是否显示详细日志 |

**配置说明**：

- **ENABLE_DEDUPLICATION**：
  - `True`：去除重复的文档（基于文本内容哈希）
  - `False`：保留所有文档（可能包含重复）
  - 推荐保持 `True` 以减少冗余

- **VERBOSE**：
  - `True`：显示详细的处理进度和统计信息
  - `False`：只显示关键信息
  - 开发调试时建议设为 `True`

#### 4. 验证配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `VALIDATE_CHUNK_IDS` | bool | `True` | 是否验证chunk ID的存在性 |
| `PRINT_STATS` | bool | `True` | 是否打印统计信息 |

**配置说明**：

- **VALIDATE_CHUNK_IDS**：
  - `True`：在提取oracle时验证chunk ID是否存在于语料库中
  - `False`：跳过验证（不推荐）

- **PRINT_STATS**：
  - `True`：打印去重、处理等环节的统计信息
  - `False`：不打印统计信息

### 配置示例

#### 示例1：快速测试配置

**步骤1**：在 `.env` 文件中配置数据集路径：
```bash
# .env 文件（项目根目录）
HOTPOTQA_DATASET_PATH=/Users/username/data/hotpot_qa/snapshots/...
```

**步骤2**：在 `config.py` 中调整其他配置：
```python
# config.py

# 使用验证集的前100个样本
DATASET_CONFIG = "distractor"
DATASET_SPLIT = "validation"

# 启用所有功能
ENABLE_DEDUPLICATION = True
VERBOSE = True
VALIDATE_CHUNK_IDS = True
PRINT_STATS = True
```

#### 示例2：完整评估配置

```python
# config.py

# 使用全部验证集
DATASET_CONFIG = "distractor"
DATASET_SPLIT = "validation"
SAMPLE_LIMIT = None  # 使用全部7,405个问题

# 启用所有功能
ENABLE_DEDUPLICATION = True
VERBOSE = True
VALIDATE_CHUNK_IDS = True
PRINT_STATS = True
```

#### 示例3：生产环境配置

```python
# config.py

# 使用训练集
DATASET_CONFIG = "distractor"
DATASET_SPLIT = "train"
SAMPLE_LIMIT = None  # 使用全部训练集

# 关闭详细日志以提高性能
ENABLE_DEDUPLICATION = True
VERBOSE = False  # 关闭详细日志
VALIDATE_CHUNK_IDS = True
PRINT_STATS = False  # 关闭统计信息
```

### 如何修改配置

1. **配置数据集路径**（在 `.env` 文件中）：
   ```bash
   # 打开项目根目录的 .env 文件，添加：
   HOTPOTQA_DATASET_PATH=/your/path/to/hotpotqa/dataset
   ```

2. **修改其他配置项**（在 `config.py` 中，可选）：
   ```bash
   # Linux/Mac
   nano evaluation/hotpotqa_evaluation/config.py

   # Windows
   notepad evaluation/hotpotqa_evaluation/config.py
   ```
   - **建议修改**：`DATASET_CONFIG`, `DATASET_SPLIT`, `SAMPLE_LIMIT`

3. **保存并运行脚本**：
   ```bash
   python upload_information.py
   ```

### 注意事项

1. **数据集路径配置**：
   - 通过环境变量 `HOTPOTQA_DATASET_PATH` 在 `.env` 文件中配置
   - `.env` 文件已被 `.gitignore` 忽略，每个开发者独立配置
   - Windows 示例：`HOTPOTQA_DATASET_PATH=C:\path\to\dataset`
   - Linux/Mac 示例：`HOTPOTQA_DATASET_PATH=/path/to/dataset`

2. **数据集下载**：
   - 从 Hugging Face 下载：`datasets--hotpotqa--hotpot_qa`
   - 确保下载的是完整的 snapshot 文件夹

3. **配置优先级**：
   - 命令行参数 > config.py 配置
   - 例如：`--start 0 --end 100` 会覆盖 `SAMPLE_LIMIT` 配置

4. **兼容性**：
   - 两个脚本都会读取 `config.py` 中的配置
   - 修改 `config.py` 会影响所有脚本的行为

---

## 1. upload_information.py - 数据处理与上传

### 功能说明

这个脚本负责处理 HotpotQA 数据集，分为三个阶段：

1. **阶段1：构建语料库** - 从数据集中提取文档，进行文档级拼接和去重
2. **阶段2：提取标准答案** - 提取每个问题的 ground truth（oracle）
3. **阶段3：上传到系统** - 将语料库加载到检索系统中

### 使用方法

#### 快速测试 (样本)

```bash
# 1. 回到项目根目录
cd [PATH_TO_PROJECT]

# 2. 先运行上传脚本（确保语料库生成成功）
python evaluation/hotpotqa_evaluation/scripts/upload_information.py --start 0 --end 5

# 3. 再运行召回评估脚本
python evaluation/hotpotqa_evaluation/scripts/retrieve_recall.py --verbose --track-zero-recall
```

#### 基本用法

```bash
# 处理前10个样本（默认）
python upload_information.py

# 处理指定范围的样本
python upload_information.py --start 0 --end 100

# 禁用事项提取（只加载文档）
python upload_information.py --start 0 --end 50 --enable-extraction

# 禁用日志输出
python upload_information.py --no-log
```

#### 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--start` | int | 0 | 起始样本索引（包含） |
| `--end` | int | 10 | 结束样本索引（不包含） |
| `--enable-extraction` | flag | 启用 | 添加此参数则禁用事项提取 |
| `--no-log` | flag | 关闭 | 禁用日志输出 |

### 输出结果

脚本会自动创建时间戳文件夹，所有文件保存在：

```
evaluation/hotpotqa_evaluation/data/source/YYYYMMDD_HHMMSS/
```

#### 生成的文件

| 文件名 | 格式 | 说明 |
|--------|------|------|
| `corpus.jsonl` | JSONL | 语料库（JSON Lines格式），每行一个chunk |
| `corpus_merged.md` | Markdown | 合并的语料库文档（用于上传） |
| `oracle.jsonl` | JSONL | 标准答案，每行一个问题的ground truth |
| `process_result.json` | JSON | 处理结果摘要（包含source_config_id、统计信息等） |

#### corpus.jsonl 格式

```json
{
  "id": "5a8b57f25542995d1e6f1371_0",
  "title": "Document Title",
  "text": "# Document Title\nDocument content..."
}
```

#### oracle.jsonl 格式

```json
{
  "id": "5a8b57f25542995d1e6f1371",
  "question": "What is the question?",
  "answer": "The answer",
  "oracle_chunk_ids": ["5a8b57f25542995d1e6f1371_0", "5a8b57f25542995d1e6f1371_1"],
  "oracle_titles": ["Title 1", "Title 2"],
  "type": "bridge",
  "level": "medium"
}
```

#### process_result.json 格式

```json
{
  "source_config_id": "hotpotqa-corpus-20251209_143025",
  "source_name": "HotpotQA Corpus",
  "article_id": "article_123",
  "sections_count": 150,
  "events_count": 300,
  "load_time_seconds": 5.2,
  "extract_time_seconds": 15.8,
  "total_processing_time_seconds": 21.0,
  "corpus_file": "path/to/corpus_merged.md",
  "corpus_size_mb": 2.5,
  "timestamp": "20251209_143025",
  "status": "completed"
}
```

### 使用示例

```bash
# 示例1：处理前100个样本，完整流程
python upload_information.py --start 0 --end 100

# 示例2：处理全部验证集（需修改config）
python upload_information.py --start 0 --end 7405

# 示例3：只加载文档，不提取事项（速度更快）
python upload_information.py --start 0 --end 50 --enable-extraction
```

---

## 2. retrieve_recall.py - 检索召回评估

### 功能说明

这个脚本用于评估检索系统的召回性能，包括：

- 批量检索问题的相关文档
- 计算每个问题的召回率（Recall）
- 统计完美召回、部分召回、零召回的问题
- 生成 Bad Case 报告

### 使用方法

#### 基本用法

```bash
# 自动使用最新的数据文件夹
python retrieve_recall.py

# 指定数据文件夹
python retrieve_recall.py --data-dir evaluation/hotpotqa_evaluation/data/source/20251209_143025

# 自定义批次大小和并发数
python retrieve_recall.py --batch-size 10 --concurrency 5

# 显示详细日志
python retrieve_recall.py --verbose

# 追踪零召回问题（生成Bad Case报告）
python retrieve_recall.py --track-zero-recall

# 只评估 Bad Cases
python retrieve_recall.py --bad-cases evaluation/hotpotqa_evaluation/data/retrieval/20251209_150000/bad_cases_zero_recall.json
```

#### 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--data-dir` | str | None | 数据文件夹路径（包含oracle.jsonl、corpus.jsonl等） |
| `--batch-size` | int | 5 | 每批处理的问题数量 |
| `--concurrency` | int | 5 | 每批的并发数 |
| `--verbose` | flag | 关闭 | 显示详细日志 |
| `--no-save` | flag | 关闭 | 不保存结果文件 |
| `--track-zero-recall` | flag | 关闭 | 追踪并保存零召回问题为Bad Case |
| `--bad-cases` | str | None | Bad Case文件路径（只重新评估这些问题） |

### 输出结果

脚本会自动创建时间戳文件夹，所有文件保存在：

```
evaluation/hotpotqa_evaluation/data/retrieval/YYYYMMDD_HHMMSS/
```

#### 生成的文件

| 文件名 | 格式 | 说明 |
|--------|------|------|
| `retrieve_recall.log` | 日志 | 评估过程的详细日志（**只记录批次结果，不含SAG日志**） |
| `retrieval_results.jsonl` | JSONL | 每个问题的检索结果 |
| `recall_evaluation.json` | JSON | 召回评估统计信息 |
| `partial_recall_cases.json` | JSON | 部分召回的问题列表（0 < recall < 1） |
| `bad_cases_zero_recall.json` | JSON | 零召回问题列表（仅在 `--track-zero-recall` 时生成） |
| `retrieve_recall_bad_cases.log` | 日志 | Bad Cases 模式下的日志 |

#### retrieval_results.jsonl 格式

```json
{
  "question_id": "5a8b57f25542995d1e6f1371",
  "question": "What is the question?",
  "oracle_chunks": [
    {
      "chunk_id": "5a8b57f25542995d1e6f1371_0",
      "title": "Title",
      "text": "Content..."
    }
  ],
  "retrieved_sections": [
    {
      "section_id": "section_123",
      "title": "Retrieved Title",
      "content": "Retrieved content...",
      "score": 0.85
    }
  ],
  "metadata": {
    "source_config_id": "hotpotqa-corpus-20251209_143025",
    "retrieval_time": 0.5
  }
}
```

#### recall_evaluation.json 格式

```json
{
  "total_questions": 100,
  "total_oracle": 200,
  "total_recalled": 180,
  "total_retrieved": 500,
  "cumulative_recall": 0.9,
  "perfect_recall_count": 70,
  "partial_recall_count": 25,
  "zero_recall_count": 5,
  "processing_time_seconds": 120.5,
  "average_time_per_question": 1.2,
  "partial_recall_questions": [...],
  "per_question": [...]
}
```

#### partial_recall_cases.json 格式

```json
[
  {
    "question_id": "5a8b57f25542995d1e6f1371",
    "question": "What is the question?",
    "recall": 0.5,
    "recalled": 1,
    "total_oracle": 2,
    "percentage": "1/2"
  }
]
```

#### bad_cases_zero_recall.json 格式

```json
[
  {
    "question_id": "5a8b57f25542995d1e6f1371",
    "question": "What is the question?",
    "recall": 0.0,
    "total_oracle": 2,
    "recalled": 0,
    "retrieved": 10,
    "recalled_details": []
  }
]
```

### 使用示例

```bash
# 示例1：基础评估（自动使用最新数据）
python retrieve_recall.py --batch-size 10 --concurrency 5

# 示例2：显示详细日志并追踪Bad Cases
python retrieve_recall.py --verbose --track-zero-recall

# 示例3：只重新评估零召回的问题
python retrieve_recall.py --bad-cases evaluation/hotpotqa_evaluation/data/retrieval/20251209_150000/bad_cases_zero_recall.json --verbose

# 示例4：指定数据文件夹进行评估
python retrieve_recall.py --data-dir evaluation/hotpotqa_evaluation/data/source/20251209_143025 --batch-size 20
```

### 日志说明

#### 普通模式日志 (`retrieve_recall.log`)

- **只记录批次检索结果**，不记录 SAG 及其他模块的 info 日志
- 包含的内容：
  - 批次处理信息
  - 每个批次的累积统计
  - 最终评估结果
  - 部分召回和零召回问题列表

#### Bad Cases 模式日志 (`retrieve_recall_bad_cases.log`)

- 只记录重新评估 Bad Cases 时的日志
- 不生成其他结果文件，只保存日志

---

## 文件结构说明

### 完整目录结构

```
evaluation/hotpotqa_evaluation/
├── scripts/
│   ├── upload_information.py          # 数据处理与上传
│   ├── retrieve_recall.py             # 检索召回评估
│   └── README.md                      # 本文档
├── data/
│   ├── source/                        # 数据源文件夹
│   │   ├── 20251209_143025/          # 时间戳文件夹（示例）
│   │   │   ├── corpus.jsonl          # 语料库
│   │   │   ├── corpus_merged.md      # 合并的Markdown文档
│   │   │   ├── oracle.jsonl          # 标准答案
│   │   │   └── process_result.json   # 处理结果
│   │   └── 20251209_150000/          # 另一次运行
│   └── retrieval/                     # 检索结果文件夹
│       ├── 20251209_160000/          # 时间戳文件夹（示例）
│       │   ├── retrieve_recall.log   # 评估日志
│       │   ├── retrieval_results.jsonl  # 检索结果
│       │   ├── recall_evaluation.json   # 召回评估
│       │   ├── partial_recall_cases.json  # 部分召回问题
│       │   └── bad_cases_zero_recall.json # Bad Cases（可选）
│       └── 20251209_170000/          # 另一次评估
```

### 数据流向图

```
HotpotQA 数据集
    ↓
[upload_information.py]
    ↓
data/source/YYYYMMDD_HHMMSS/
├── corpus.jsonl
├── corpus_merged.md
├── oracle.jsonl
└── process_result.json
    ↓
[retrieve_recall.py]
    ↓
data/retrieval/YYYYMMDD_HHMMSS/
├── retrieve_recall.log
├── retrieval_results.jsonl
├── recall_evaluation.json
├── partial_recall_cases.json
└── bad_cases_zero_recall.json
```

---

## 完整工作流程

### 第一步：处理数据集

```bash
# 处理前100个样本
cd evaluation/hotpotqa_evaluation/scripts
python upload_information.py --start 0 --end 100
```

输出示例：
```
============================================================
输出文件位置
============================================================
输出文件夹: evaluation/hotpotqa_evaluation/data/source/20251209_143025
文件列表:
  - 语料库 (JSONL): corpus.jsonl
  - 语料库 (Markdown): corpus_merged.md
  - 标准答案: oracle.jsonl
  - 处理结果: process_result.json
============================================================
```

### 第二步：评估召回性能

```bash
# 使用最新的数据文件夹自动评估
python retrieve_recall.py --batch-size 10 --concurrency 5 --verbose --track-zero-recall
```

输出示例：
```
============================================================
INCREMENTAL PROCESSING
Total questions: 100
Batch size: 10
Number of batches: 10
Log file: evaluation/hotpotqa_evaluation/data/retrieval/20251209_160000/retrieve_recall.log
============================================================

[Batch 1/10] Processing questions 0-10
============================================================
Batch completed:
  Processed: 10 questions
  Failed: 0
  Time elapsed: 12.34s
  Batch recall: 0.8500
============================================================

[Progress after batch 1/10]
  Cumulative recall: 0.8500
  Total questions: 10
  Perfect recall: 7
  Partial recall: 2
  Zero recall: 1

...

============================================================
FINAL RESULTS
============================================================
Total questions processed: 100
Overall recall: 0.8750
Perfect recall count: 75
Partial recall count: 20
Zero recall count: 5

💡 检索详细日志已保存到: evaluation/hotpotqa_evaluation/data/retrieval/20251209_160000/retrieve_recall.log
💡 所有评估结果已保存到: evaluation/hotpotqa_evaluation/data/retrieval/20251209_160000
```

### 第三步：分析 Bad Cases（可选）

```bash
# 重新评估零召回的问题
python retrieve_recall.py --bad-cases evaluation/hotpotqa_evaluation/data/retrieval/20251209_160000/bad_cases_zero_recall.json --verbose
```

---

## 注意事项

### 1. 环境配置

- 确保在项目根目录的 `.env` 文件中配置了 `HOTPOTQA_DATASET_PATH`
- 需要连接到 Elasticsearch 和其他必要服务

### 2. 数据路径

- `upload_information.py` 会自动创建时间戳文件夹
- `retrieve_recall.py` 默认使用最新的数据文件夹，也可以通过 `--data-dir` 指定

### 3. 性能优化

- 增加 `--concurrency` 可以加快检索速度，但注意不要超过系统限制
- 增加 `--batch-size` 可以减少批次数，适合大规模评估

### 4. 日志管理

- 普通模式下的 `retrieve_recall.log` **只记录批次结果**，不包含 SAG 模块的 info 日志
- Bad Cases 模式下使用独立的日志文件 `retrieve_recall_bad_cases.log`

### 5. 磁盘空间

- 处理大规模数据集时注意磁盘空间
- `corpus_merged.md` 文件可能较大

---

## 常见问题

### Q1: 如何只重新评估某些问题？

使用 `--bad-cases` 参数指定包含问题ID的文件：

```bash
python retrieve_recall.py --bad-cases path/to/bad_cases_zero_recall.json
```

### Q2: 如何禁用事项提取以加快速度？

在 `upload_information.py` 中添加 `--enable-extraction` 参数：

```bash
python upload_information.py --enable-extraction
```

### Q3: 日志文件太大怎么办？

普通模式下的日志已经过滤了其他模块的 info 日志，只记录批次结果。如果还是太大，可以考虑：
- 减少 `--batch-size` 来减少输出频率
- 不使用 `--verbose` 参数

### Q4: 如何查看检索到了哪些文档？

查看 `retrieval_results.jsonl` 文件，里面包含每个问题的检索结果详情。

### Q5: Bad Cases 文件格式是什么？

Bad Cases 文件是一个 JSON 数组，每个元素包含问题ID、问题文本、召回率等信息。可以直接用于 `--bad-cases` 参数。

---

## 更新日志

- **2025-12-09**: 初始版本，包含两个核心脚本的使用说明
- **2025-12-09**: 更新日志配置说明，普通模式下只记录批次结果
- **2025-12-09**: 数据集路径改为通过环境变量配置，避免多人协作时的路径冲突

---

## 联系方式

如有问题或建议，请联系开发团队。
