# DataFlow 引擎使用指南

## 概述

DataFlow 引擎是一个标准化的数据处理任务引擎，支持三个独立的处理阶段：

1. **Load（加载）** - 加载和解析文档
2. **Extract（提取）** - 从文档中提取事项和实体
3. **Search（搜索）** - 支持多种搜索模式：
   - **LLM** - 大模型智能检索（默认）
   - **RAG** - 纯向量检索（开发中）
   - **SAG** - SQL驱动的混合检索（开发中）

## 核心特性

✅ **可分可合** - 三个阶段完全独立，可单独执行或组合  
✅ **灵活输出** - 支持ID或完整内容两种输出模式  
✅ **日志管理** - 日志总是保存，可配置是否打印  
✅ **链式调用** - 支持优雅的链式API  
✅ **统一配置** - 也支持统一的TaskConfig配置  
✅ **异步支持** - 支持异步和同步两种执行方式

## 快速开始

### 1. 基础使用（分步调用）

```python
from dataflow import DataFlowEngine, LoadBaseConfig, ExtractBaseConfig

# 初始化引擎
engine = DataFlowEngine(source_config_id="my-source")

# 加载文档
engine.load(LoadBaseConfig(path="docs/document.md"))

# 提取事项
engine.extract(ExtractBaseConfig(parallel=True))

# 获取结果
result = engine.get_result()
print(f"提取了 {len(result.extract_result.data_ids)} 个事项")
```

### 2. 链式调用（推荐）

```python
from dataflow import DataFlowEngine, LoadBaseConfig, ExtractBaseConfig, SearchBaseConfig

result = (
    DataFlowEngine(source_config_id="my-source")
    .load(LoadBaseConfig(path="docs/document.md"))
    .extract(ExtractBaseConfig(parallel=True, max_concurrency=3))
    .search(SearchBaseConfig(query="查找AI相关内容", top_k=5))
    .get_result()
)

print(f"匹配了 {len(result.search_result.data_ids)} 个事项")
```

### 3. 统一配置（配置可分可合）

```python
from dataflow import DataFlowEngine, TaskConfig, LoadBaseConfig, ExtractBaseConfig, OutputConfig, OutputMode

task_config = TaskConfig(
    task_name="完整流程",
    source_config_id="my-source",
    background="这是技术文档集合，重点关注技术实现",  # 全局背景信息
    load=LoadBaseConfig(path="docs/document.md"),
    extract=ExtractBaseConfig(parallel=True),  # 使用全局 background
    output=OutputConfig(mode=OutputMode.ID_ONLY),
)

engine = DataFlowEngine(task_config=task_config)
result = engine.run()

# 输出结果
output = engine.output()
print(output)
```

## 配置说明

### ModelConfig - LLM配置

```python
from dataflow import ModelConfig

model_config = ModelConfig(
    api_key="sk-your-api-key",  # API密钥（留空从环境变量读取）
    model="sophnet/Qwen3-30B-A3B-Thinking-2507",  # 模型名称
    base_url="https://api.openai.com/v1",  # API基础URL（中转API）
    timeout=60,  # 超时时间（秒）
    max_retries=3,  # 最大重试次数
    temperature=0.3,  # 生成温度
    with_retry=True,  # 是否启用重试
)
```

### LoadBaseConfig - 加载阶段配置

```python
from dataflow import LoadBaseConfig

load_config = LoadBaseConfig(
    path="docs/document.md",  # 文件或目录路径（必填）
    auto_vector=True,  # 是否自动索引到ES
    recursive=True,  # 是否递归搜索子目录
    pattern="*.md",  # 文件匹配模式
    max_tokens=8000,  # 最大token数
)
# 注意：background, source_config_id 由引擎自动提供
```

### ExtractBaseConfig - 提取阶段配置

```python
from dataflow import ExtractBaseConfig

extract_config = ExtractBaseConfig(
    parallel=True,  # 是否并行处理
    max_concurrency=3,  # 最大并发数
    max_sections=10,  # 每批最大片段数
    max_tokens=8000,  # 每批最大token数
)
# 注意：background, source_config_id, article_id 由引擎自动提供
```

### SearchBaseConfig - 搜索阶段配置

```python
from dataflow import SearchBaseConfig, SearchMode

search_config = SearchBaseConfig(
    query="查找AI相关内容",  # 检索目标（必填）
    mode=SearchMode.LLM,  # 搜索模式（默认LLM）
    threshold=0.5,  # 相关度阈值
    top_k=10,  # 返回数量上限
)
# 注意：background, source_config_id, article_id 由引擎自动提供

# 三种搜索模式：
# - SearchMode.LLM: 大模型智能检索（默认）
# - SearchMode.RAG: 纯向量检索（开发中）
# - SearchMode.SAG: SQL驱动的混合检索（开发中）
```

### OutputConfig - 输出配置

```python
from dataflow import OutputConfig, OutputMode

output_config = OutputConfig(
    mode=OutputMode.FULL,  # 输出模式（ID_ONLY 或 FULL）
    format="json",  # 输出格式（json/markdown）
    include_logs=True,  # 是否在输出中包含日志
    print_logs=True,  # 是否打印日志到控制台
    export_path=None,  # 导出文件路径（留空返回字符串）
    pretty=True,  # 是否美化输出
)
```

## 使用场景

### 场景1：只加载文档

```python
engine = DataFlowEngine(source_config_id="my-source")
engine.load(LoadBaseConfig(path="docs/document.md"))

result = engine.get_result()
sections_ids = result.load_result.data_ids  # 获取片段ID列表
```

### 场景2：只提取事项

```python
engine = DataFlowEngine(source_config_id="my-source")
engine._article_id = "existing-article-id"  # 设置已存在的文章ID
engine.extract(ExtractBaseConfig(parallel=True))

result = engine.get_result()
events = result.extract_result.data_full  # 获取完整事项列表
```

### 场景3：只搜索事项

```python
engine = DataFlowEngine(source_config_id="my-source")
engine.search(SearchBaseConfig(query="查找AI相关内容"))

result = engine.get_result()
matched_ids = result.search_result.data_ids  # 获取匹配事项ID
```

### 场景4：完整流程

```python
task_config = TaskConfig(
    task_name="完整流程",
    source_config_id="my-source",
    background="技术文档，关注AI技术实现",  # 全局背景信息
    load=LoadBaseConfig(path="docs/document.md"),
    extract=ExtractBaseConfig(parallel=True),
    search=SearchBaseConfig(query="查找..."),
)

engine = DataFlowEngine(task_config=task_config)
result = engine.run()
```

### 场景5：批量处理

```python
documents = [
    ("docs/doc1.md", "技术文档1"),
    ("docs/doc2.md", "技术文档2"),
    ("docs/doc3.md", "技术文档3"),
]

for path, background in documents:
    result = (
        DataFlowEngine(source_config_id="batch-source")
        .load(LoadBaseConfig(path=path))  # background 通过 TaskConfig 全局配置
        .extract(ExtractBaseConfig(parallel=True))
        .get_result()
    )
    print(f"{path}: {result.stats.get('events', 0)} 个事项")
```

## 输出模式

### ID_ONLY 模式

只输出数据ID，适合：
- 需要进一步处理的场景
- 数据量大的场景
- 只需要标识符的场景

```python
OutputConfig(mode=OutputMode.ID_ONLY)

# 输出示例
{
  "load": {
    "results": ["section-id-1", "section-id-2", ...]
  },
  "extract": {
    "results": ["event-id-1", "event-id-2", ...]
  }
}
```

### FULL 模式

输出完整数据，适合：
- 最终结果展示
- 需要详细信息的场景
- 一次性获取所有数据

```python
OutputConfig(mode=OutputMode.FULL)

# 输出示例
{
  "load": {
    "results": [
      {"id": "...", "heading": "...", "content": "..."},
      ...
    ]
  },
  "extract": {
    "results": [
      {"id": "...", "title": "...", "content": "...", "entities": [...]},
      ...
    ]
  }
}
```

## 日志管理

日志总是会保存在 `TaskResult.logs` 中，但可以通过配置控制是否打印：

```python
# 不打印日志但保存
OutputConfig(print_logs=False, include_logs=True)

# 打印日志且保存
OutputConfig(print_logs=True, include_logs=True)

# 打印日志但不在输出中包含
OutputConfig(print_logs=True, include_logs=False)
```

查看日志：

```python
result = engine.get_result()

# 查看所有日志
for log in result.logs:
    print(log)

# 只查看错误日志
for log in result.logs:
    if log.level.value == "error":
        print(log)
```

## 异步执行

```python
import asyncio

async def async_task():
    engine = DataFlowEngine(source_config_id="my-source")

    # 异步加载
    await engine.load_async(LoadBaseConfig(path="docs/document.md"))

    # 异步提取
    await engine.extract_async(ExtractBaseConfig(parallel=True))

    return engine.get_result()

result = asyncio.run(async_task())
```

## 错误处理

### 快速失败模式

```python
task_config = TaskConfig(
    fail_fast=True,  # 遇到错误立即停止
    ...
)
```

### 容错模式

```python
task_config = TaskConfig(
    fail_fast=False,  # 即使某个阶段失败也继续执行
    ...
)

result = engine.run()

# 检查每个阶段的状态
if result.load_result and result.load_result.status == "failed":
    print(f"加载失败: {result.load_result.error}")

if result.extract_result and result.extract_result.status == "failed":
    print(f"提取失败: {result.extract_result.error}")
```

## 最佳实践

1. **推荐使用链式调用** - 代码更简洁，逻辑更清晰
2. **大文档启用并行处理** - 提高处理效率
3. **提供背景信息** - 提高AI提取准确性
4. **合理设置批次大小** - 避免超出token限制
5. **使用ID模式处理大数据** - 减少内存占用
6. **保存日志便于调试** - include_logs=True
7. **使用中转API提高稳定性** - 配置 base_url
8. **异步执行批量任务** - 提高并发效率

## 并发安全性 ⚡

DataFlow 引擎**完全支持并发运行**，你可以安全地创建多个引擎实例，每个实例使用独立的配置：

### ✅ 并发场景示例

```python
import asyncio

async def run_multiple_engines():
    # 引擎1：处理技术文档
    engine1 = DataFlowEngine(
        model_config=ModelConfig(api_key="sk-tech", model="sophnet/Qwen3-30B-A3B-Thinking-2507", temperature=0.2),
        source_config_id="tech-docs"
    )

    # 引擎2：处理营销内容
    engine2 = DataFlowEngine(
        model_config=ModelConfig(api_key="sk-marketing", model="gpt-3.5-turbo", temperature=0.7),
        source_config_id="marketing"
    )
    
    # 并发运行 - 配置完全隔离！
    result1, result2 = await asyncio.gather(
        engine1.load_async(LoadStageConfig(path="docs/tech.md")),
        engine2.load_async(LoadStageConfig(path="docs/marketing.md"))
    )
```

### 🔒 线程安全保证

- ✅ **不修改全局状态** - 每个引擎独立配置
- ✅ **线程安全** - 支持多线程并发
- ✅ **进程安全** - 支持多进程部署
- ✅ **无竞态条件** - 配置隔离，互不干扰

### 📊 性能特性

- 支持大规模并发（100+ 引擎实例）
- 每个引擎创建时间 < 10ms
- 内存占用合理
- 无全局锁竞争

### 🎯 典型应用场景

1. **多租户SaaS** - 每个租户独立配置
2. **负载均衡** - 分散到多个API端点
3. **批量处理** - 并行处理多个文档
4. **A/B测试** - 同时测试不同模型配置

查看 `concurrent_engines_demo.py` 获取完整的并发示例。

## 完整示例

- `engine_example.py` - 基础功能示例
- `concurrent_engines_demo.py` - 并发安全演示
- `search_modes_demo.py` - 搜索模式演示（LLM/RAG/SAG）

## 注意事项

1. 运行前请确保已配置 LLM_API_KEY 环境变量
2. 需要先初始化数据库（运行 `scripts/init_database.py`）
3. Load阶段依赖实际的文档文件
4. Extract阶段依赖Load阶段的输出
5. Search阶段依赖数据库中已有的事项数据

## 故障排查

### Linter 错误

`Instance of 'FieldInfo' has no 'append' member` - 这是 Pylance 的误报，不影响实际运行。Pydantic 的 `Field(default_factory=list)` 会在运行时正确创建列表。

### 数据库连接错误

确保 MySQL 已启动并且配置正确：

```bash
# 检查配置
cat .env | grep MYSQL

# 初始化数据库
python scripts/init_database.py
```

### LLM API 错误

检查 API Key 和网络连接：

```bash
# 检查环境变量
echo $LLM_API_KEY

# 使用中转API
export LLM_BASE_URL="https://api.your-proxy.com/v1"
```

