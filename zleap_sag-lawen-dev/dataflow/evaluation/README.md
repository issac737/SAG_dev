# DataFlow Evaluation 模块

完整的评估框架，支持检索系统和QA系统的性能评估。

## 📦 模块结构

```
dataflow/evaluation/
├── benchmark.py                # ⭐ Evaluate 类（主评估框架）
├── dataset/                    # 数据集目录
├── metrics/                    # 评估指标
│   ├── base.py                 # BaseMetric（评估指标基类）
│   ├── qa_eval.py              # QA评估指标（EM, F1）
│   └── retrieval_eval.py       # 检索评估指标（Recall@k）
├── utils/                      # 工具函数
│   ├── load_utils.py          # ⭐ DatasetLoader（数据集加载）
│   └── ...
├── examples/                   # 使用示例
│   ├── dataset_loader_example.py
│   └── evaluate_example.py
├── test_evaluate.py            # 集成测试
└── README.md                   # 本文档
```

## 🚀 快速开始

### 1. 数据集加载（调用 load_utils）

```python
from dataflow.evaluation import DatasetLoader

# 创建加载器
loader = DatasetLoader('musique')

# 获取数据
docs = loader.get_docs()              # 11,656 个文档
questions = loader.get_questions()    # 1,000 个问题
gold_answers = loader.get_gold_answers()  # 标准答案
gold_docs = loader.get_gold_docs()    # 支持文档

# 获取统计信息
stats = loader.get_stats()
print(stats)
```

**支持的数据集**：
- ✅ MuSiQue (11,656 docs, 1,000 questions)
- ✅ HotpotQA (9,811 docs, 1,000 questions)
- ✅ 2WikiMultihopQA (6,119 docs, 1,000 questions)

### 2. 完整评估（Evaluate 类）

```python
from dataflow.evaluation import Evaluate, EvaluationConfig

# 配置评估
config = EvaluationConfig(
    dataset_name='musique',
    max_samples=100,
    evaluate_retrieval=True,
    evaluate_qa=True,
    save_results=True
)

# 创建评估器
evaluator = Evaluate(config)

# 加载数据集
evaluator.load_dataset()

# 运行你的系统（示例）
questions = evaluator.get_questions()
retrieved_docs_list = your_retrieval_system(questions)
predicted_answers = your_qa_system(questions, retrieved_docs_list)

# 评估
results = evaluator.evaluate_all(
    retrieved_docs_list=retrieved_docs_list,
    predicted_answers=predicted_answers
)

# 查看结果
evaluator.print_summary(results)
```

### 3. 便捷函数

```python
from dataflow.evaluation import quick_evaluate

# 一行代码完成评估
results = quick_evaluate(
    dataset_name='musique',
    retrieved_docs_list=my_results,
    predicted_answers=my_predictions
)
```

## 📊 评估指标

### 检索评估

- **Recall@k** - 前k个检索结果中包含的相关文档比例

### QA评估

- **Exact Match (EM)** - 精确匹配率
- **F1 Score** - Token级别的F1分数

## 📈 评估结果示例

```json
{
  "dataset": "musique",
  "timestamp": "2025-12-19T14:53:28",
  "num_questions": 20,
  "retrieval": {
    "pooled": {
      "Recall@1": 0.0417,
      "Recall@5": 0.4375,
      "Recall@10": 0.9500,
      "Recall@20": 0.9500
    }
  },
  "qa": {
    "pooled": {
      "ExactMatch": 1.0000,
      "F1": 1.0000
    }
  }
}
```

## 🧪 运行示例

```bash
# 数据集加载示例
python dataflow/evaluation/examples/dataset_loader_example.py

# 评估示例
python dataflow/evaluation/examples/evaluate_example.py

# 集成测试
python dataflow/evaluation/test_evaluate.py
```

## 📚 详细文档

- **EVAL评估框架** - 完整的评估类文档 ([EVALUATE_README.md](./EVALUATE_README.md))
- **数据集加载器** - DatasetLoader 完整文档 ([utils/DATASET_LOADER_README.md](./utils/DATASET_LOADER_README.md))

## 🎓 完整流程示例

```python
from dataflow.evaluation import Evaluate, EvaluationConfig

# 1. 配置
config = EvaluationConfig(
    dataset_name='musique',
    max_samples=100,
    evaluate_retrieval=True,
    evaluate_qa=True,
    retrieval_top_k_list=[1,5,10,20],
    save_results=True
)

# 2. 创建评估器
evaluator = Evaluate(config)

# 3. 加载数据
dataset_info = evaluator.load_dataset()
print(f"Loaded {dataset_info['num_questions']} questions")

# 4. 获取问题
questions = evaluator.get_questions()

# 5. 运行你的系统
retrieved = my_system.retrieve(questions)
answers = my_system.answer(questions, retrieved)

# 6. 评估
results = evaluator.evaluate_all(
    retrieved_docs_list=retrieved,
    predicted_answers=answers
)

# 7. 查看摘要
evaluator.print_summary(results)
```

## 🎯 主要特性

✅ **完整的数据集加载** - 自动加载 corpus、questions、gold_answers、gold_docs
✅ **灵活的评估配置** - 可配置评估类型、top-k 列表、采样等
✅ **标准化指标** - Recall@k, EM, F1
✅ **多数据集支持** - MuSiQue, HotpotQA, 2WikiMultihopQA
✅ **结果自动保存** - JSON格式，带时间戳
✅ **简洁的API** - 易于使用和集成

## 🔗 关键方法说明

### Evaluate 类核心方法

| 方法 | 用途 |
|------|------|
| `load_dataset()` | 加载数据集 |
| `evaluate_retrieval()` | 评估检索性能（Recall@k） |
| `evaluate_qa()` | 评估QA性能（EM, F1） |
| `evaluate_all()` | 运行完整评估流程 |
| `print_summary()` | 打印评估摘要 |

### DatasetLoader 类核心方法

| 方法 | 返回 |
|------|------|
| `get_docs()` | 格式化文档列表 ["title\ntext"] |
| `get_questions()` | 问题列表 |
| `get_gold_answers()` | 标准答案列表（集合） |
| `get_gold_docs()` | 支持文档列表 |
| `get_stats()` | 数据集统计信息 |

## 🎉 开始使用

所有代码已完成并经过测试，可以立即使用！

1. 查看示例：`examples/evaluate_example.py`
2. 查看详细文档：`EVALUATE_README.md`
3. 运行测试：`test_evaluate.py`
