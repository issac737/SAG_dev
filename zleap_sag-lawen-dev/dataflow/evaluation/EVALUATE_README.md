# Evaluate 类使用文档

## 概述

`Evaluate` 类是一个完整的评估框架，用于评估检索系统和QA系统的性能。支持：

- ✅ **数据集加载** - 使用 `DatasetLoader` 加载标准数据集
- ✅ **检索评估** - Recall@k 指标
- ✅ **QA评估** - Exact Match 和 F1 Score 指标
- ✅ **结果保存** - 自动保存评估结果为JSON格式
- ✅ **灵活配置** - 通过 `EvaluationConfig` 配置评估参数

## 快速开始

### 基本使用

```python
from dataflow.evaluation.benchmark import Evaluate, EvaluationConfig

# 1. 创建配置
config = EvaluationConfig(
    dataset_name='musique',
    max_samples=100,  # 可选：限制样本数量用于快速测试
    evaluate_retrieval=True,
    evaluate_qa=True,
    save_results=True,
    output_dir='outputs/evaluation'
)

# 2. 创建评估器
evaluator = Evaluate(config)

# 3. 加载数据集
evaluator.load_dataset()

# 4. 获取问题列表
questions = evaluator.get_questions()

# 5. 运行你的系统（示例）
# retrieved_docs_list = your_retrieval_system(questions)
# predicted_answers = your_qa_system(questions, retrieved_docs_list)

# 6. 评估结果
results = evaluator.evaluate_all(
    retrieved_docs_list=retrieved_docs_list,
    predicted_answers=predicted_answers
)

# 7. 打印摘要
evaluator.print_summary(results)
```

### 便捷函数

```python
from dataflow.evaluation.benchmark import quick_evaluate

# 一行代码完成评估
results = quick_evaluate(
    dataset_name='musique',
    retrieved_docs_list=my_retrieval_results,
    predicted_answers=my_qa_predictions,
    max_samples=100
)
```

## 核心组件

### 1. EvaluationConfig - 评估配置

```python
@dataclass
class EvaluationConfig:
    # 数据集配置
    dataset_name: str = "musique"              # 数据集名称
    dataset_dir: Optional[str] = None          # 数据集目录

    # 评估类型
    evaluate_retrieval: bool = True            # 是否评估检索
    evaluate_qa: bool = True                   # 是否评估QA

    # 检索评估配置
    retrieval_top_k_list: List[int] = [1, 5, 10, 20]  # Recall@k 的 k 值列表

    # QA评估配置
    qa_aggregation: str = "max"                # 聚合函数: max, mean

    # 输出配置
    save_results: bool = True                  # 是否保存结果
    output_dir: str = "outputs/evaluation"     # 输出目录
    save_predictions: bool = True              # 是否保存预测
    verbose: bool = True                       # 是否详细输出

    # 采样配置
    max_samples: Optional[int] = None          # 最大样本数（None=全部）
```

### 2. Evaluate - 评估类

#### 主要方法

| 方法 | 说明 |
|------|------|
| `load_dataset()` | 加载数据集 |
| `get_questions()` | 获取问题列表 |
| `get_docs()` | 获取文档列表 |
| `get_gold_answers()` | 获取标准答案 |
| `get_gold_docs()` | 获取标准文档 |
| `evaluate_retrieval()` | 评估检索性能 |
| `evaluate_qa()` | 评估QA性能 |
| `evaluate_all()` | 运行完整评估 |
| `save_results()` | 保存结果 |
| `print_summary()` | 打印摘要 |

## 使用示例

### 示例1：只评估检索性能

```python
config = EvaluationConfig(
    dataset_name='musique',
    evaluate_retrieval=True,
    evaluate_qa=False,  # 不评估QA
    retrieval_top_k_list=[1, 5, 10, 20, 50]
)

evaluator = Evaluate(config)
evaluator.load_dataset()

# 运行你的检索系统
questions = evaluator.get_questions()
retrieved_docs_list = my_retrieval_system.search(questions)

# 评估检索结果
retrieval_results = evaluator.evaluate_retrieval(
    retrieved_docs_list=retrieved_docs_list
)

print(retrieval_results['pooled'])
# 输出: {'Recall@1': 0.42, 'Recall@5': 0.78, ...}
```

### 示例2：只评估QA性能

```python
config = EvaluationConfig(
    dataset_name='musique',
    evaluate_retrieval=False,  # 不评估检索
    evaluate_qa=True
)

evaluator = Evaluate(config)
evaluator.load_dataset()

# 运行你的QA系统
questions = evaluator.get_questions()
predicted_answers = my_qa_system.answer(questions)

# 评估QA结果
qa_results = evaluator.evaluate_qa(predicted_answers=predicted_answers)

print(qa_results['pooled'])
# 输出: {'ExactMatch': 0.65, 'F1': 0.72}
```

### 示例3：完整评估流程

```python
config = EvaluationConfig(
    dataset_name='musique',
    max_samples=None,  # 使用全部数据
    save_results=True
)

evaluator = Evaluate(config)
evaluator.load_dataset()

# 运行你的完整RAG系统
questions = evaluator.get_questions()

# 1. 检索
retrieved_docs_list = my_retrieval_system.search(questions)

# 2. 生成答案
predicted_answers = my_qa_system.answer(questions, retrieved_docs_list)

# 3. 完整评估
results = evaluator.evaluate_all(
    retrieved_docs_list=retrieved_docs_list,
    predicted_answers=predicted_answers
)

# 4. 查看结果
evaluator.print_summary(results)
```

### 示例4：多数据集评估

```python
datasets = ['musique', 'hotpotqa', '2wikimultihopqa']

for dataset_name in datasets:
    print(f"\n=== Evaluating {dataset_name} ===")

    config = EvaluationConfig(
        dataset_name=dataset_name,
        max_samples=100
    )

    evaluator = Evaluate(config)
    evaluator.load_dataset()

    questions = evaluator.get_questions()

    # 运行系统
    retrieved_docs = my_system.retrieve(questions)
    answers = my_system.answer(questions, retrieved_docs)

    # 评估
    results = evaluator.evaluate_all(
        retrieved_docs_list=retrieved_docs,
        predicted_answers=answers
    )

    evaluator.print_summary(results)
```

### 示例5：快速测试（采样）

```python
# 只用10个样本快速测试
config = EvaluationConfig(
    dataset_name='musique',
    max_samples=10,
    save_results=False
)

evaluator = Evaluate(config)
evaluator.load_dataset()

# ... 运行系统 ...

results = evaluator.evaluate_all(
    retrieved_docs_list=retrieved_docs,
    predicted_answers=predicted_answers
)
```

## 评估指标

### 检索评估 (Retrieval Evaluation)

**Recall@k** - 前k个检索结果中包含的相关文档比例

```python
Recall@k = |检索到的相关文档| / |所有相关文档|
```

支持的 k 值可以自定义：
```python
config.retrieval_top_k_list = [1, 5, 10, 20, 50, 100]
```

### QA评估 (Question Answering Evaluation)

**Exact Match (EM)** - 预测答案与标准答案完全匹配

```python
EM = 1 if normalize(predicted) == normalize(gold) else 0
```

**F1 Score** - 基于token级别的F1分数

```python
F1 = 2 * (precision * recall) / (precision + recall)
```

## 评估结果格式

### 返回结果结构

```json
{
  "dataset": "musique",
  "timestamp": "2025-12-19T14:46:47.336332",
  "num_questions": 1000,
  "retrieval": {
    "pooled": {
      "Recall@1": 0.4200,
      "Recall@5": 0.7800,
      "Recall@10": 0.8900
    },
    "examples": [...],
    "elapsed_time": 2.34
  },
  "qa": {
    "pooled": {
      "ExactMatch": 0.6500,
      "F1": 0.7200
    },
    "examples": [...],
    "elapsed_time": 1.23
  }
}
```

### 保存的文件

评估结果会保存为两个文件：

1. **时间戳文件**: `eval_{dataset}_{timestamp}.json`
2. **最新文件**: `eval_{dataset}_latest.json` (总是指向最新结果)

## 与 DatasetLoader 集成

`Evaluate` 类内部使用 `DatasetLoader` 加载数据：

```python
# Evaluate 内部实现
self.dataset_loader = DatasetLoader(
    dataset_name=self.config.dataset_name,
    dataset_dir=self.config.dataset_dir
)

self.docs = self.dataset_loader.get_docs()
self.questions = self.dataset_loader.get_questions()
self.gold_answers = self.dataset_loader.get_gold_answers()
self.gold_docs = self.dataset_loader.get_gold_docs()
```

你也可以直接访问数据集加载器：

```python
evaluator = Evaluate(config)
evaluator.load_dataset()

# 访问数据集加载器
loader = evaluator.dataset_loader
stats = loader.get_stats()
```

## 日志输出

评估过程会输出详细日志：

```
dataflow.evaluation.benchmark - INFO - Loading dataset: musique
dataflow.evaluation.utils.load_utils - INFO - Loaded 11656 documents from corpus
dataflow.evaluation.benchmark - INFO - Dataset loaded successfully: {...}
dataflow.evaluation.benchmark - INFO - Evaluating retrieval with top_k_list: [1, 5, 10, 20]
dataflow.evaluation.benchmark - INFO - Retrieval evaluation completed in 2.34s
dataflow.evaluation.benchmark - INFO - Pooled results: {'Recall@1': 0.42, ...}
```

设置日志级别：
```python
import logging
logging.basicConfig(level=logging.INFO)
```

## 完整代码示例

参考文件：
- `dataflow/evaluation/examples/evaluate_example.py` - 完整示例
- `dataflow/evaluation/benchmark.py` - 源代码

运行示例：
```bash
python dataflow/evaluation/examples/evaluate_example.py
```

## 注意事项

1. **数据格式匹配**
   - `retrieved_docs_list` 的长度必须等于问题数量
   - `predicted_answers` 的长度必须等于问题数量
   - 每个 `retrieved_docs_list[i]` 是一个文档列表

2. **gold_docs 可用性**
   - 不是所有数据集都有 `gold_docs`
   - 如果 `gold_docs` 为 `None`，检索评估会被跳过

3. **采样模式**
   - 设置 `max_samples` 后只使用前N个样本
   - 适合快速测试和调试

4. **结果保存**
   - 设置 `save_results=True` 自动保存结果
   - 结果保存在 `output_dir` 目录

## 扩展和自定义

### 自定义评估指标

```python
from dataflow.evaluation.metrics import BaseMetric

class MyCustomMetric(BaseMetric):
    metric_name = "my_custom"

    def calculate_metric_scores(self, ...):
        # 实现你的评估逻辑
        pass

# 在 Evaluate 类中使用
evaluator.custom_metric = MyCustomMetric()
```

### 自定义聚合函数

```python
import numpy as np

# 使用平均值而不是最大值
evaluator.evaluate_qa(
    predicted_answers=predictions,
    aggregation_fn=np.mean
)
```

## 常见问题

**Q: 如何评估我自己的RAG系统？**

A:
```python
# 1. 加载评估器
evaluator = Evaluate(EvaluationConfig(dataset_name='musique'))
evaluator.load_dataset()

# 2. 获取问题
questions = evaluator.get_questions()

# 3. 运行你的系统
retrieved = my_rag.retrieve(questions)
answers = my_rag.answer(questions)

# 4. 评估
results = evaluator.evaluate_all(retrieved, answers)
```

**Q: 如何只评估部分数据？**

A: 使用 `max_samples` 参数：
```python
config = EvaluationConfig(max_samples=100)
```

**Q: 评估结果保存在哪里？**

A: 默认保存在 `outputs/evaluation/` 目录，可通过 `output_dir` 配置。

**Q: 如何添加新的评估指标？**

A: 继承 `BaseMetric` 类并实现 `calculate_metric_scores` 方法。
