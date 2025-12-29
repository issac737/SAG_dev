# HotpotQA 评估子目录创建完成！

## 📁 创建的文件结构

```
hotpotqa_evaluation/
├── 1_build_corpus.py         # ✅ 步骤1：构建全局语料库
├── 2_extract_oracle.py       # ✅ 步骤2：提取标准答案
├── 3_upload_corpus.py        # ✅ 步骤3：上传语料库到 Event Flow
├── hotpotqa_pipeline.py      # ✅ Pipeline 工具类
├── utils.py                  # ✅ 工具函数（去重、ID处理等）
├── config.py                 # ✅ 配置文件
├── __init__.py               # ✅ Python 包初始化
├── README.md                 # ✅ 详细文档
├── run_test.py               # ✅ 快速测试脚本
└── data/                     # 📂 数据输出目录
    ├── corpus.jsonl          # （运行后生成）
    ├── corpus_merged.md      # （运行后生成）
    ├── oracle.jsonl          # （运行后生成）
    └── upload_result.json    # （运行后生成）
```

## 🚀 快速开始

### 1. 修改配置

编辑 `hotpotqa_evaluation/config.py`，设置你的 HotpotQA 数据集路径：

```python
HOTPOTQA_DATASET_PATH = r"你的/HotpotQA/路径"
```

### 2. 运行测试（推荐先测试）

```bash
cd hotpotqa_evaluation
python run_test.py
```

这会处理 3 个样本，验证流程是否正常。

### 3. 运行完整流程

```bash
# 步骤 1: 构建语料库
python 1_build_corpus.py

# 步骤 2: 提取 Oracle
python 2_extract_oracle.py

# 步骤 3: 上传到 Event Flow（可选）
python 3_upload_corpus.py
```

## 📊 核心功能

### 1_build_corpus.py

**功能：**
- ✅ 从 HotpotQA 提取所有文档
- ✅ 文档级拼接（Markdown 格式：`#{title}\n{content}`）
- ✅ 智能去重（基于纯净文本）
- ✅ 生成全局唯一 ID

**输出示例：**
```json
{"id": "5a8b57f2-00", "title": "Scott Derrickson", "text": "#Scott Derrickson\nScott Derrickson is..."}
{"id": "5a8b57f2-01", "title": "Ed Wood", "text": "#Ed Wood\nEd Wood was..."}
{"id": "5a8c7595-00//5ae1796a-05", "title": "India", "text": "#India\nIndia is..."}
```

### 2_extract_oracle.py

**功能：**
- ✅ 提取 supporting_facts（标准答案）
- ✅ 标题映射到 chunk ID
- ✅ 验证去重映射
- ✅ 生成 oracle.jsonl

**输出示例：**
```json
{
  "id": "5a8b57f2",
  "question": "Were Scott Derrickson and Ed Wood of the same nationality?",
  "answer": "yes",
  "oracle_chunk_ids": ["5a8b57f2-00", "5a8b57f2-01"],
  "oracle_titles": ["Scott Derrickson", "Ed Wood"],
  "type": "comparison",
  "level": "medium"
}
```

### 3_upload_corpus.py

**功能：**
- ✅ 上传 corpus_merged.md 到 Event Flow 系统
- ✅ 创建信息源
- ✅ 等待事项生成完成
- ✅ 可选：使用 oracle 问题测试检索

**输出示例：**
```json
{
  "source_config_id": "src_xxx",
  "article_id": "art_xxx",
  "events_count": 280,
  "processing_time_seconds": 45.2,
  "corpus_size_mb": 1.5
}
```

## 🔧 工具函数（utils.py）

- `purify_text()` - 文本去重
- `format_chunk_id()` - 生成标准 ID
- `ChunkDeduplicator` - 去重器类
- `merge_chunk_ids()` - 合并 ID
- `validate_chunk_id()` - 验证 ID

## ⚙️ 配置选项（config.py）

```python
# 数据集配置
DATASET_CONFIG = "distractor"      # 或 "fullwiki"
DATASET_SPLIT = "validation"       # 或 "train"
SAMPLE_LIMIT = None                # 处理样本数（None=全部）

# 处理配置
ENABLE_DEDUPLICATION = True        # 是否去重
VERBOSE = True                     # 详细日志
TITLE_SEPARATOR = ": "             # 标题分隔符
```

## 📖 使用示例

### 示例 1：快速测试（3个样本）

```bash
python 1_build_corpus.py --limit 3
python 2_extract_oracle.py --limit 3
python 3_upload_corpus.py --test-queries
```

### 示例 2：处理前100个样本

```bash
python 1_build_corpus.py --limit 100
python 2_extract_oracle.py --limit 100
python 3_upload_corpus.py
```

### 示例 3：处理全部样本

```bash
python 1_build_corpus.py
python 2_extract_oracle.py
python 3_upload_corpus.py
```

### 示例 4：禁用去重

```bash
python 1_build_corpus.py --no-dedup
```

### 示例 5：自定义 API URL

```bash
python 3_upload_corpus.py --api-url http://your-server:8000/api/v1
```

### 示例 6：仅运行测试查询（不重新上传）

```bash
# 第一次：上传 + 测试
python 3_upload_corpus.py --test-queries

# 后续：仅测试（使用已有的 upload_result.json）
python 3_upload_corpus.py --test-only
```

## 📊 预期输出

### 步骤 1 统计示例

```
📊 去重统计
============================================================
  total_chunks: 30
  unique_chunks: 28
  duplicates: 2
  dedup_rate: 6.67%
============================================================

📊 最终统计
============================================================
  样本数量: 3
  原始 chunks: 30
  去重后 chunks: 28
  去重率: 6.67%
  输出文件: data/corpus.jsonl
  文件大小: 0.15 MB
============================================================
```

### 步骤 2 统计示例

```
📊 Oracle 统计
============================================================
  问题总数: 3
  Oracle chunks 总数: 6
  平均每问题 oracle 数: 2.00
  缺失 chunks: 0
  问题类型分布: {'comparison': 1, 'bridge': 2}
  难度分布: {'easy': 1, 'medium': 1, 'hard': 1}
  输出文件: data/oracle.jsonl
  文件大小: 1.23 KB
============================================================
```

## 🎯 下一步计划

完成这两个步骤后，你已经有了：
1. ✅ **corpus.jsonl** - 去重的全局语料库
2. ✅ **oracle.jsonl** - 每个问题的标准答案

下一步可以：
- [ ] 实现检索器（BM25/Dense Retriever）
- [ ] 计算召回指标（Recall@K, Precision@K）
- [ ] 集成到你的 RAG 系统
- [ ] 使用 RAGAS 进行评估

## 🐛 故障排查

### 问题：ModuleNotFoundError

```bash
# 确保在正确目录
cd ragas_evaluate

# 运行脚本
python hotpotqa_evaluation/1_build_corpus.py
```

### 问题：数据集路径错误

```bash
# 检查配置
cat hotpotqa_evaluation/config.py | grep HOTPOTQA_DATASET_PATH

# 修改配置
vim hotpotqa_evaluation/config.py
```

### 问题：corpus.jsonl 不存在

```bash
# 先运行步骤 1
python hotpotqa_evaluation/1_build_corpus.py
```

## 📚 更多信息

查看详细文档：
```bash
cat hotpotqa_evaluation/README.md
```

---

**创建时间：** 2025-10-28
**版本：** 1.0.0
**状态：** ✅ 已完成
