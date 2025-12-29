# RAGAs 评估使用指南

## 简介

使用 RAGAs (Retrieval-Augmented Generation Assessment) 框架评估 RAG 系统性能。

## 安装依赖

```bash
pip install ragas datasets
```

## 完整评估流程

### 步骤 1: 构建语料库
```bash
python evaluation/hotpotqa_evaluation/1_build_corpus.py
```

生成文件：
- `data/corpus.jsonl`
- `data/corpus_merged.md`
- `data/oracle.jsonl`

### 步骤 2: 上传语料库并测试搜索
```bash
python evaluation/hotpotqa_evaluation/3_upload_corpus.py --test-queries
```

生成文件：
- `data/process_result.json`
- `data/test_search_results.json`

### 步骤 3: 运行 RAGAs 评估
```bash
# 完整评估（评估所有问题）
python evaluation/hotpotqa_evaluation/4_ragas_evaluation.py

# 测试模式（只评估前5个问题）
python evaluation/hotpotqa_evaluation/4_ragas_evaluation.py --limit 5

# 详细日志模式
python evaluation/hotpotqa_evaluation/4_ragas_evaluation.py --verbose

# 自定义输入输出路径
python evaluation/hotpotqa_evaluation/4_ragas_evaluation.py \
    --search-results data/test_search_results.json \
    --output data/my_evaluation_report.json
```

生成文件：
- `data/ragas_evaluation_report.json`

## RAGAs 评估指标

### 1. Faithfulness (忠实度)
- **含义**: 生成的答案是否忠实于检索到的段落（无幻觉）
- **计算**: 答案中能被上下文支持的语句数 / 总语句数
- **范围**: 0-1（越高越好）
- **示例**:
  ```
  上下文: "Scott Derrickson is an American director"
  答案: "Scott is American" → 高分 ✅
  答案: "Scott is French" → 低分 ❌ (幻觉)
  ```

### 2. Answer Relevancy (答案相关性)
- **含义**: 答案是否直接回答了问题
- **计算**: 通过反向生成问题，比较与原问题的相似度
- **范围**: 0-1（越高越好）
- **示例**:
  ```
  问题: "What is Scott's nationality?"
  答案: "American" → 高分 ✅
  答案: "Scott made many films" → 低分 ❌ (跑题)
  ```

### 3. Context Precision (上下文精度)
- **含义**: 检索到的段落中有多少是真正相关的
- **计算**: 相关段落排名靠前的程度
- **范围**: 0-1（越高越好）
- **说明**: 需要 ground_truth 来判断哪些段落相关

### 4. Context Recall (上下文召回率)
- **含义**: 标准答案所需的信息是否被检索到
- **计算**: ground_truth中能被contexts支持的语句数 / 总语句数
- **范围**: 0-1（越高越好）
- **示例**:
  ```
  标准答案: "Scott is American and Ed is American"
  检索到的段落只包含: "Scott is American"
  → 召回率 50%
  ```

## Oracle Chunks 对比指标

除了 RAGAs 指标，脚本还会对比检索结果与标准答案段落：

### Average Precision (平均精确率)
- **含义**: 检索到的段落中有多少在标准答案段落中
- **公式**: 平均(检索段落 ∩ 标准段落 / 检索段落数)

### Average Recall (平均召回率)
- **含义**: 标准答案段落中有多少被检索到
- **公式**: 平均(检索段落 ∩ 标准段落 / 标准段落数)

### F1 Score
- **含义**: 精确率和召回率的调和平均
- **公式**: 2 × Precision × Recall / (Precision + Recall)

## 评估报告示例

```json
{
  "metadata": {
    "timestamp": "2025-01-03T14:30:00",
    "total_questions": 5,
    "search_results_file": "data/test_search_results.json"
  },
  "ragas_metrics": {
    "faithfulness": 0.8523,
    "answer_relevancy": 0.7891,
    "context_precision": 0.6234,
    "context_recall": 0.7012
  },
  "oracle_comparison": {
    "average_precision": 0.4500,
    "average_recall": 0.6000,
    "f1_score": 0.5143
  },
  "sample_data": {
    "question": "Were Scott Derrickson and Ed Wood of the same nationality?",
    "answer": "Yes, both were American.",
    "contexts_count": 3,
    "ground_truth": "yes"
  }
}
```

## 常见问题

### Q: RAGAs 评估很慢怎么办？
A: 使用 `--limit` 参数限制评估数量进行测试：
```bash
python 4_ragas_evaluation.py --limit 5
```

### Q: 出现 "RAGAs 未安装" 错误
A: 安装 RAGAs：
```bash
pip install ragas datasets
```

### Q: 如何调整 LLM 模型？
A: 修改项目根目录的 `.env` 文件：
```bash
LLM_MODEL=gpt-4
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1
```

### Q: 生成答案出错怎么办？
A: 检查：
1. .env 文件是否正确配置
2. API key 是否有效
3. 网络连接是否正常
4. 使用 `--verbose` 查看详细错误信息

## 结果解读

### 好的结果（参考值）
- Faithfulness: > 0.8
- Answer Relevancy: > 0.7
- Context Precision: > 0.6
- Context Recall: > 0.6
- Oracle F1 Score: > 0.5

### 如何改进

**Faithfulness 低**：
- 问题：模型产生幻觉
- 解决：调整提示词，要求模型严格基于上下文回答

**Answer Relevancy 低**：
- 问题：答案偏离问题
- 解决：优化提示词，强调直接回答问题

**Context Precision 低**：
- 问题：检索到太多无关段落
- 解决：提高 `threshold`，调整搜索策略

**Context Recall 低**：
- 问题：相关段落未被检索到
- 解决：降低 `threshold`，增加 `top_k`，启用 Stage2 多跳搜索

**Oracle F1 低**：
- 问题：检索段落与标准答案段落不匹配
- 解决：调整 Stage1-3 的搜索参数

## 参考资料

- [RAGAs 官方文档](https://docs.ragas.io/)
- [RAGAs GitHub](https://github.com/explodinggradients/ragas)
- [HotpotQA 数据集](https://hotpotqa.github.io/)
