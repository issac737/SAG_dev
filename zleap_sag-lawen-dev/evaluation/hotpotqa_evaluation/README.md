# HotpotQA RAG 评估框架

使用 HotpotQA 数据集评估 RAG 系统的检索和问答能力，支持完整的数据处理、上传和 RAGAs 评估流程。

## 📁 项目结构

```
hotpotqa_evaluation/
├── README.md                 # 项目主文档（本文件）
├── __init__.py              # 包初始化，导出主要类和函数
├── config.py                # 全局配置文件
├── run_test.py              # 快速测试脚本（推荐使用）
│
├── modules/                 # 核心模块
│   ├── __init__.py         # 模块导出
│   ├── hotpotqa_loader.py  # HotpotQA 数据加载器
│   ├── event_to_sections.py # Event转换为Section
│   └── utils.py            # 工具函数（格式化、去重等）
│
├── scripts/                 # 评估流程脚本
│   ├── 1_build_corpus.py   # 步骤1：构建全局语料库
│   ├── 2_extract_oracle.py # 步骤2：提取标准答案
│   ├── 3_upload_corpus.py  # 步骤3：上传语料库到Event Flow
│   └── 4_ragas_evaluation.py # 步骤4：RAGAs评估
│
├── data/                    # 数据输出目录
│   ├── corpus.jsonl         # 语料库
│   ├── corpus_merged.md     # Markdown格式语料库
│   ├── oracle.jsonl         # 标准答案
│   ├── process_result.json  # 处理结果
│   ├── test_search_results.json # 搜索测试结果
│   └── ragas_evaluation_report.json # RAGAs评估报告
│
└── docs/                    # 详细文档
    ├── README.md           # 完整文档（数据格式、API等）
    ├── README_event_to_sections.md # Event转换说明
    ├── README_RAGAS.md     # RAGAs评估说明
    └── SETUP_COMPLETE.md   # 配置指南
```

## 🚀 快速开始

### 前置条件

1. 安装依赖（已在 `pyproject.toml` 中定义）
2. 下载 HotpotQA 数据集
3. 配置数据集路径（通过环境变量）

### 环境变量配置

在项目根目录的 `.env` 文件中添加 HotpotQA 数据集路径：

```bash
# HotpotQA 数据集路径（根据你的本地路径修改）
# Windows 示例: C:\Users\user\Downloads\datasets--hotpotqa--hotpot_qa\snapshots\xxx
# macOS/Linux 示例: /Users/username/data/datasets--hotpotqa--hotpot_qa/snapshots/xxx
HOTPOTQA_DATASET_PATH=/your/path/to/hotpotqa/dataset
```

> **注意**：`.env` 文件已被 `.gitignore` 忽略，每个开发者需要在本地配置自己的路径，不会影响其他人。



### 方式一：使用快速测试脚本（推荐）

```bash
# 测试完整流程（使用3个样本）
python run_test.py

# 自定义样本数量
python run_test.py --limit 5

# 只运行特定步骤
python run_test.py --steps 1,2

# 显示详细日志
python run_test.py --verbose
```

**说明：**
- 默认处理 3 个样本，快速验证流程
- 自动运行步骤 1-4（构建语料库 → 提取Oracle → 上传测试 → RAGAs评估）
- 完成后会验证所有输出文件

### 方式二：分步执行

#### 1. 配置数据集路径

在项目根目录的 `.env` 文件中配置（参见上方"环境变量配置"章节）。

#### 2. 构建语料库

```bash
# 处理所有样本
python scripts/1_build_corpus.py

# 测试模式（10个样本）
python scripts/1_build_corpus.py --limit 10
```

**输出：** `data/corpus.jsonl`, `data/corpus_merged.md`

#### 3. 提取标准答案

```bash
# 提取所有样本的 oracle
python scripts/2_extract_oracle.py

# 测试模式
python scripts/2_extract_oracle.py --limit 10
```

**输出：** `data/oracle.jsonl`

#### 4. 上传语料库并测试

```bash
# 上传到Event Flow并测试搜索
python scripts/3_upload_corpus.py --test-queries

# 指定API地址
python scripts/3_upload_corpus.py --api-url http://your-server:8000/api/v1 --test-queries

# 仅测试（不重新上传）
python scripts/3_upload_corpus.py --test-only
```

**输出：** `data/process_result.json`, `data/test_search_results.json`

#### 5. RAGAs 评估

```bash
# 运行RAGAs评估
python scripts/4_ragas_evaluation.py

# 测试模式（5个问题）
python scripts/4_ragas_evaluation.py --limit 5

# 显示详细日志
python scripts/4_ragas_evaluation.py --verbose
```

**输出：** `data/ragas_evaluation_report.json`

## 📊 核心功能

### 数据加载与处理

```python
from hotpotqa_evaluation import HotpotQALoader, ChunkDeduplicator

# 加载数据
loader = HotpotQALoader("path/to/dataset")
samples = loader.load_validation(limit=100)

# 去重处理
deduplicator = ChunkDeduplicator()
unique_chunks = deduplicator.deduplicate(chunks)
```

### 格式转换

```python
from hotpotqa_evaluation import format_chunk_id, split_merged_id

# 生成chunk ID
chunk_id = format_chunk_id("sample_123", 0)  # "sample_123-00"

# 解析chunk ID
sample_id, index = split_merged_id("sample_123-00")  # ("sample_123", 0)
```

### Event转换为Section

```python
from hotpotqa_evaluation import EventToSectionConverter

converter = EventToSectionConverter()
sections = converter.convert_events(events)
```

## 📖 详细文档

- **完整使用指南：** [docs/README.md](docs/README.md)
- **Event转换说明：** [docs/README_event_to_sections.md](docs/README_event_to_sections.md)
- **RAGAs评估说明：** [docs/README_RAGAS.md](docs/README_RAGAS.md)
- **环境配置指南：** [docs/SETUP_COMPLETE.md](docs/SETUP_COMPLETE.md)

## 🔧 配置项

### 环境变量配置（`.env` 文件）

- `HOTPOTQA_DATASET_PATH`: 数据集路径 **（必须配置）**

### `config.py` 配置

- `DATASET_CONFIG`: 使用的配置（`distractor` 或 `fullwiki`）
- `DATASET_SPLIT`: 数据集分割（`train` 或 `validation`）
- `SAMPLE_LIMIT`: 样本数量限制
- `ENABLE_DEDUPLICATION`: 是否启用去重
- `VALIDATE_CHUNK_IDS`: 是否验证chunk ID存在性

## 📈 评估指标

RAGAs 评估提供以下指标：

- **Context Precision**: 检索内容的精确度
- **Context Recall**: 检索内容的召回率
- **Faithfulness**: 生成答案的忠实度
- **Answer Relevancy**: 答案的相关性

## 🛠️ 开发说明

### 导入模块

```python
# 方式1：直接从包导入
from hotpotqa_evaluation import HotpotQALoader, format_chunk_id

# 方式2：从子模块导入
from hotpotqa_evaluation.modules import HotpotQALoader
from hotpotqa_evaluation.modules.utils import format_chunk_id

# 导入配置
from hotpotqa_evaluation import config
```

### 添加新脚本

新脚本应放在 `scripts/` 目录下，并遵循以下规范：

1. 使用 `argparse` 提供命令行参数
2. 从 `hotpotqa_evaluation.modules` 导入需要的模块
3. 使用 `config.py` 中的配置
4. 在文件开头添加清晰的文档字符串

## 📝 版本信息

- **版本：** 1.0.0
- **作者：** RAG Evaluation Team

## ⚠️ 注意事项

1. 首次运行前务必在 `.env` 文件中配置 `HOTPOTQA_DATASET_PATH`
2. 建议先用 `run_test.py` 或 `--limit` 参数测试小样本
3. 上传到 Event Flow 前确保服务正常运行
4. RAGAs 评估需要 OpenAI API（确保配置了相关环境变量）

## 🤝 贡献

如需添加新功能或修复问题，请确保：

1. 代码遵循现有的项目结构
2. 添加必要的文档字符串
3. 在 `docs/` 目录下更新相关文档
4. 测试新功能是否正常工作
