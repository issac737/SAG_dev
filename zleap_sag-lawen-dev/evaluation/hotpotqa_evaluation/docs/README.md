# HotpotQA RAG 评估框架

使用 HotpotQA 数据集评估 RAG 系统的检索能力。

## 📁 目录结构

```
hotpotqa_evaluation/
├── 1_build_corpus.py       # 步骤1：构建全局语料库
├── 2_extract_oracle.py     # 步骤2：提取标准答案
├── 3_upload_corpus.py      # 步骤3：上传语料库到 Event Flow
├── hotpotqa_pipeline.py    # Pipeline 工具类
├── utils.py                # 工具函数
├── config.py               # 配置文件
├── data/                   # 输出数据目录
│   ├── corpus.jsonl        # 语料库 JSONL（步骤1输出）
│   ├── corpus_merged.md    # 合并的 Markdown 文件（步骤1输出）
│   ├── oracle.jsonl        # 标准答案（步骤2输出）
│   └── upload_result.json  # 上传结果（步骤3输出）
└── README.md               # 本文件
```

## 🚀 快速开始

### 1. 配置数据集路径

编辑 `config.py`，设置 HotpotQA 数据集路径：

```python
HOTPOTQA_DATASET_PATH = r"你的/HotpotQA/数据集/路径"
```

### 2. 构建语料库

```bash
# 处理所有样本
python 1_build_corpus.py

# 或者先用小样本测试
python 1_build_corpus.py --limit 10
```

**输出：**
- `data/corpus.jsonl` - 去重后的全局语料库（JSONL 格式）
- `data/corpus_merged.md` - 所有 chunk 合并的 Markdown 文件

### 3. 提取标准答案

```bash
# 提取所有样本的 oracle
python 2_extract_oracle.py

# 或者处理前10个
python 2_extract_oracle.py --limit 10
```

**输出：** `data/oracle.jsonl`
- 每个问题的标准答案（oracle chunk IDs）
- 包含问题、答案、类型、难度等信息

### 4. 上传语料库到 Event Flow（可选）

```bash
# 仅上传（不测试）
python 3_upload_corpus.py

# 上传 + 测试查询
python 3_upload_corpus.py --test-queries

# 仅测试查询（使用已有的 upload_result.json，不重新上传）
python 3_upload_corpus.py --test-only

# 指定 API URL
python 3_upload_corpus.py --api-url http://your-server:8000/api/v1
```

**输出：** `data/upload_result.json`
- 包含 source_config_id, article_id, events_count 等信息
- 如果启用 `--test-queries` 或 `--test-only`，还会生成 `test_search_results.json`

**说明：**
- `--test-only` 会跳过上传步骤，直接使用已有的 `upload_result.json` 运行测试查询
- 这样可以避免重复创建信息源和上传文件

## 📊 数据格式

### corpus.jsonl 格式

```json
{
  "id": "5a8b57f2-00",
  "title": "Scott Derrickson",
  "text": "#Scott Derrickson\nScott Derrickson is an American director..."
}
```

**字段说明：**
- `id`: chunk 唯一 ID，格式 `{sample_id}-{index:02d}`
- `title`: 文档标题
- `text`: 文档文本（Markdown 格式：`#{title}\n{content}`，可直接保存为 .md 文件）

**去重后的 ID：**
```json
{
  "id": "5a8b57f2-00//5ae1796a-03",
  "title": "Scott Derrickson",
  "text": "..."
}
```
- 多个原始 ID 用 `//` 连接
- 表示这些 chunk 的纯净文本相同（已合并）

### oracle.jsonl 格式

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

**字段说明：**
- `id`: 问题 ID（与 HotpotQA 原始 ID 相同）
- `question`: 问题文本
- `answer`: 标准答案
- `oracle_chunk_ids`: 正确答案所需的 chunk IDs（对应 supporting_facts）
- `oracle_titles`: 正确答案的文档标题
- `type`: 问题类型（comparison/bridge）
- `level`: 难度（easy/medium/hard）

## 🔧 配置选项

### config.py 主要配置

```python
# 数据集配置
DATASET_CONFIG = "distractor"      # 或 "fullwiki"
DATASET_SPLIT = "validation"       # 或 "train"
SAMPLE_LIMIT = None                # None=全部, 或设置数字

# 处理配置
ENABLE_DEDUPLICATION = True        # 是否去重
VERBOSE = True                     # 详细日志
```

### 命令行参数

**1_build_corpus.py:**
```bash
--dataset PATH    # 数据集路径
--output PATH     # 输出文件路径
--limit N         # 样本数量限制
--no-dedup        # 禁用去重
```

**2_extract_oracle.py:**
```bash
--dataset PATH    # 数据集路径
--corpus PATH     # corpus.jsonl 路径
--output PATH     # 输出文件路径
--limit N         # 样本数量限制
```

## 📈 统计信息示例

### 步骤1 输出示例

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

### 步骤2 输出示例

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

## 🎯 评估流程

1. **构建语料库** → `corpus.jsonl` + `corpus_merged.md`
2. **提取标准答案** → `oracle.jsonl`
3. **上传到 Event Flow**（可选）→ `upload_result.json`
   - 上传 `corpus_merged.md` 到信息源
   - 等待事项生成完成
   - 可选：运行测试查询
4. **检索评估**（手动或自动）：
   - 用 `question` 从 Event Flow 中检索事项
   - 对比检索结果和 `oracle_chunk_ids`
   - 计算 Recall@K, Precision@K 等指标

## 🔍 核心逻辑

### 文档级拼接

```python
# 原始数据
title = "Scott Derrickson"
sentences = [
    "Scott Derrickson is an American director.",
    "He lives in Los Angeles."
]

# 拼接结果（Markdown 格式）
chunk_text = "#Scott Derrickson\nScott Derrickson is an American director. He lives in Los Angeles."
```

**说明：** 使用 Markdown 一级标题格式，可以直接保存为 `.md` 文件

### 去重逻辑

```python
# 生成纯净文本（去标点、空格、小写）
purity = purify_text(chunk_text)
# → "scottderricksonscottderricksonisamericandirectorheliveslosangeles"

# 如果纯净文本相同，合并 ID
# 原始: "5a8b57f2-00" 和 "5ae1796a-03"
# 合并: "5a8b57f2-00//5ae1796a-03"
```

### Oracle 提取逻辑

```python
# supporting_facts
{
    "title": ["Scott Derrickson", "Ed Wood"],
    "sent_id": [0, 0]  # 我们不使用这个字段
}

# 标题 → context 索引
"Scott Derrickson" → context.title[0] → chunk_id "5a8b57f2-00"
"Ed Wood" → context.title[1] → chunk_id "5a8b57f2-01"

# 结果
oracle_chunk_ids = ["5a8b57f2-00", "5a8b57f2-01"]
```

## 💡 注意事项

1. **为什么不使用 sent_id？**
   - 我们采用**文档级拼接**，而非句子级
   - 只需要知道哪个文档包含答案即可
   - 简化了处理逻辑

2. **为什么要去重？**
   - HotpotQA 中有干扰文档，可能在多个样本中重复
   - 去重可以减少语料库大小
   - 评估时更准确（避免重复计算）

3. **合并 ID 的处理**
   - `corpus.jsonl` 中只保留一个副本（用合并 ID）
   - `oracle.jsonl` 中引用的是原始 ID
   - 评估时需要处理合并 ID 的映射

## 🐛 故障排查

### 问题：找不到模块

```bash
# 确保在正确的目录运行
cd ragas_evaluate

# 或者设置 PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/path/to/ragas_evaluate"
```

### 问题：数据集路径错误

```python
# 修改 config.py 中的路径
HOTPOTQA_DATASET_PATH = r"正确的/路径"
```

### 问题：corpus.jsonl 不存在

```bash
# 先运行步骤1
python hotpotqa_evaluation/1_build_corpus.py
```

### 问题：上传失败或超时

```bash
# 1. 检查 Event Flow 服务是否运行
curl http://localhost:8000/api/v1/health

# 2. 检查 API URL 是否正确
python 3_upload_corpus.py --api-url http://your-server:8000/api/v1

# 3. 增加超时时间（修改 3_upload_corpus.py 中的 max_attempts）
```

### 问题：article_id 为 null

```bash
# 这个问题已在 hotpotqa_pipeline.py 中通过列表查询解决
# 如果仍然出现，检查：
# 1. auto_process 参数是否为 true
# 2. 后端日志是否有错误
# 3. 数据库是否正常写入
```

## 📚 下一步

- [ ] 实现检索器（BM25/Dense）
- [ ] 计算召回指标（Recall@K）
- [ ] 端到端评估流程
- [ ] 与其他系统对比

## 🔗 相关资源

- [HotpotQA 论文](https://arxiv.org/abs/1809.09600)
- [HotpotQA 数据集](https://hotpotqa.github.io/)
- [RAGAS 评估框架](https://github.com/explodinggradients/ragas)
