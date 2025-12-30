# 评估基准测试使用文档

## 快速开始

### 命令行使用（推荐）

使用 `--foundation` 参数来执行不同的评估任务：

#### 1. Upload 模式 - 加载并上传数据集
```bash
# 加载数据集并上传到系统
python dataflow/evaluation/benchmark.py \
  --foundation upload \
  --dataset test_hotpotqa

# 指定每个文件的 chunks 数量（默认500）
python dataflow/evaluation/benchmark.py \
  --foundation upload \
  --dataset test_hotpotqa \
  --chunks-per-file 1000
```

#### 2. Search 模式 - 执行检索并评估召回率
```bash
# 测试前5个问题的检索性能（显示详细日志）
python dataflow/evaluation/benchmark.py \
  --foundation search \
  --dataset test_hotpotqa \
  --info-limit 5 \
  --search-verbose

# 测试全部问题，同时评估 QA
python dataflow/evaluation/benchmark.py \
  --foundation search \
  --dataset test_hotpotqa \
  --enable-qa
```

#### 3. Badcase Zero 模式 - 重测 Zero Recall Badcase
```bash
# 重测完全没有召回的问题
python dataflow/evaluation/benchmark.py \
  --foundation badcase_zero \
  --dataset test_hotpotqa \
  --info-limit 5
```

#### 4. Badcase Partial 模式 - 重测 Partial Recall Badcase
```bash
# 重测部分召回的问题
python dataflow/evaluation/benchmark.py \
  --foundation badcase_partial \
  --dataset test_hotpotqa \
  --info-limit 5
```

#### 5. 旧参数语法（仍然支持）
```bash
# 传统的参数组合仍然可用
python dataflow/evaluation/benchmark.py \
  --load \
  --upload \
  --dataset musique

python dataflow/evaluation/benchmark.py \
  --show-retrieval-info \
  --enable-search \
  --info-limit 10
```

## 参数说明

### 核心参数

#### `--foundation` (必需)
指定功能模式：
- `upload`: 加载数据集并上传到系统
- `search`: 执行检索并评估召回率
- `badcase_zero`: 重测完全没有召回的问题
- `badcase_partial`: 重测部分召回的问题

#### `--dataset` (必需)
数据集名称，支持：
- `musique`: MuSiQue 多跳问答数据集
- `hotpotqa`: HotpotQA 多跳问答数据集
- `2wikimultihopqa`: 2WikiMultiHopQA 数据集
- `test_hotpotqa`: HotpotQA 测试数据集
- `sample`: 示例数据集

### 可选参数

#### `--info-limit` (整数, 可选)
限制显示/测试的问题数量。例如 `--info-limit 5` 只处理前5个问题。

#### `--search-verbose` (布尔, 可选)
显示详细的检索过程日志，帮助调试检索性能。

#### `--enable-qa` (布尔, 可选)
在 search 模式下启用 QA 评估，会使用 LLM 生成答案并计算 EM/F1 分数。

#### `--no-paragraphs` (布尔, 可选)
隐藏段落详细信息，使输出更简洁。

#### `--chunks-per-file` (整数, 可选, 默认: 500)
Upload 模式下，每个 markdown 文件包含的片段数量。

## 输出说明

### 信息源文件
上传的数据集保存在：
```
dataflow/evaluation/source/SAG/{model_name}/{dataset_name}/{timestamp}/
  - source_info.json
```

### Badcase 文件
检索失败的案例保存在：
```
dataflow/evaluation/outputs/SAG/{model_name}/{dataset_name}/{timestamp}/
  - zero_{dataset_name}.json      # 完全没有召回的问题
  - partial_{dataset_name}.json   # 部分召回的问题
```

### 模型名称
系统从 `.env` 文件读取模型配置，自动过滤模型名称：
- `Qwen/qwen3` → `qwen3`
- `gpt-4o-mini` → `gpt-4o-mini`

## 注意事项

1. **Badcase 模式不支持 QA 评估**
   - 使用 `--foundation badcase_*` 时，会自动禁用 QA 评估
   - 即使指定了 `--enable-qa` 也会被忽略

2. **Badcase 文件自动加载**
   - Badcase 模式会自动从最新的时间戳目录加载 badcase 文件
   - 如果没有运行过检索评估，badcase 文件不存在，会报错

3. **向后兼容**
   - 旧的参数语法（如 `--load --upload`）仍然支持
   - 建议优先使用新的 `--foundation` 参数

4. **模型配置**
   - 确保 `.env` 文件中配置了正确的 `LLM_MODEL`
   - 模型配置影响上传和检索的行为
