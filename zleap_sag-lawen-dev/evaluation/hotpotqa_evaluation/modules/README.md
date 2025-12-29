# Modules 目录说明

本目录包含 HotpotQA 评估框架的核心模块，提供数据加载、转换和工具函数。

## 📦 模块列表

### hotpotqa_loader.py - HotpotQA 数据加载器

**类：** `HotpotQALoader`

**功能：**
- 加载 HotpotQA 数据集（支持 Parquet 格式）
- 提供多种数据集配置（distractor、fullwiki）
- 支持不同的数据分割（train、validation）
- 转换为 Event Flow 兼容格式

**使用示例：**
```python
from hotpotqa_evaluation.modules import HotpotQALoader

# 初始化加载器
loader = HotpotQALoader("path/to/hotpotqa")

# 加载验证集
samples = loader.load_validation(limit=100)

# 加载训练集
samples = loader.load_train(limit=1000)

# 转换为 Event Flow 格式
documents = loader.to_eventflow_documents(samples)
```

**主要方法：**
- `load_validation(limit=None)` - 加载验证集
- `load_train(limit=None)` - 加载训练集
- `to_eventflow_documents(samples)` - 转换为 Event Flow 格式
- `get_supporting_facts(sample)` - 获取支撑事实

---

### event_to_sections.py - Event 转 Section 转换器

**类：** `EventToSectionConverter`

**功能：**
- 将 Event Flow 的 Event 转换为 Section
- 处理时间线和关系信息
- 生成结构化的 Section 数据

**使用示例：**
```python
from hotpotqa_evaluation.modules import EventToSectionConverter

# 初始化转换器
converter = EventToSectionConverter()

# 转换 events
sections = converter.convert_events(events)

# 转换单个 event
section = converter.convert_single_event(event)
```

**主要方法：**
- `convert_events(events)` - 批量转换
- `convert_single_event(event)` - 转换单个 event
- `extract_timeline(event)` - 提取时间线信息
- `extract_relations(event)` - 提取关系信息

---

### utils.py - 工具函数

**提供的工具：**

#### 1. ID 格式化

```python
from hotpotqa_evaluation.modules import format_chunk_id, split_merged_id

# 生成 chunk ID
chunk_id = format_chunk_id("sample_123", 0)
# 输出: "sample_123-00"

# 解析 chunk ID
sample_id, index = split_merged_id("sample_123-00")
# 输出: ("sample_123", 0)
```

#### 2. 去重处理

```python
from hotpotqa_evaluation.modules import ChunkDeduplicator

# 初始化去重器
deduplicator = ChunkDeduplicator()

# 去重
unique_chunks = deduplicator.deduplicate(chunks)

# 获取统计信息
stats = deduplicator.get_stats()
print(f"去重前: {stats['total']}, 去重后: {stats['unique']}")
```

**ChunkDeduplicator 特性：**
- 基于纯净文本内容去重（忽略空格、换行等）
- 保留第一个出现的 chunk
- 提供详细的统计信息
- 记录重复的 chunk ID

#### 3. 统计信息打印

```python
from hotpotqa_evaluation.modules import print_stats

# 打印统计信息
stats = {
    'total_samples': 100,
    'total_chunks': 1000,
    'unique_chunks': 850
}
print_stats(stats, title="处理结果")
```

---

## 🔧 导入方式

### 方式 1：从包导出导入（推荐）

```python
from hotpotqa_evaluation import (
    HotpotQALoader,
    EventToSectionConverter,
    format_chunk_id,
    split_merged_id,
    ChunkDeduplicator,
    print_stats
)
```

### 方式 2：从 modules 导入

```python
from hotpotqa_evaluation.modules import (
    HotpotQALoader,
    EventToSectionConverter,
    format_chunk_id,
    split_merged_id,
    ChunkDeduplicator,
    print_stats
)
```

### 方式 3：导入具体模块

```python
from hotpotqa_evaluation.modules.hotpotqa_loader import HotpotQALoader
from hotpotqa_evaluation.modules.event_to_sections import EventToSectionConverter
from hotpotqa_evaluation.modules.utils import ChunkDeduplicator
```

---

## 📋 模块依赖

### 外部依赖
- `pandas` - 数据处理
- `tqdm` - 进度条显示
- `dataflow` - Event Flow 核心库

### 内部依赖
- `config.py` - 配置文件
- 各模块之间相互独立，无交叉依赖

---

## 🛠️ 开发指南

### 添加新模块

1. 在 `modules/` 目录下创建新文件
2. 定义清晰的类和函数
3. 添加完整的文档字符串
4. 在 `modules/__init__.py` 中导出
5. 在主 `__init__.py` 中添加到 `__all__`
6. 更新本 README

### 代码规范

```python
"""
模块说明

功能描述...

使用方法:
    from hotpotqa_evaluation.modules import YourClass

    obj = YourClass()
    result = obj.method()
"""

class YourClass:
    """类说明"""

    def __init__(self, param: str):
        """
        初始化

        Args:
            param: 参数说明
        """
        self.param = param

    def method(self) -> str:
        """
        方法说明

        Returns:
            返回值说明
        """
        return self.param
```

### 单元测试

建议为每个模块添加单元测试：

```python
# 在 tests/ 目录下创建测试文件
def test_format_chunk_id():
    from hotpotqa_evaluation.modules import format_chunk_id

    result = format_chunk_id("test", 0)
    assert result == "test-00"
```

---

## 📊 性能考虑

- **HotpotQALoader**: 使用 pandas 批量加载，支持 limit 参数控制内存使用
- **ChunkDeduplicator**: 使用哈希表实现 O(n) 时间复杂度的去重
- **EventToSectionConverter**: 流式处理，适合大规模数据

---

## 🔍 故障排查

### 问题：导入模块失败

**解决方案：**
```bash
# 确保在项目根目录
cd /path/to/event_flow

# 检查 Python 路径
python -c "import sys; print(sys.path)"

# 使用正确的导入
from hotpotqa_evaluation.modules import HotpotQALoader
```

### 问题：数据加载失败

**解决方案：**
1. 检查 `config.py` 中的数据集路径
2. 确认数据集格式正确（Parquet）
3. 检查数据集配置名称（distractor/fullwiki）

### 问题：去重效果不理想

**解决方案：**
```python
# 检查去重统计
deduplicator = ChunkDeduplicator()
unique = deduplicator.deduplicate(chunks)
stats = deduplicator.get_stats()
print(f"去重率: {(1 - stats['unique']/stats['total']) * 100:.2f}%")

# 查看重复的内容
for duplicate_ids in deduplicator.duplicate_groups.values():
    print(f"重复的chunks: {duplicate_ids}")
```

---

## 📝 版本信息

- **版本：** 1.0.0
- **最后更新：** 2024-11-03

---

## 🤝 贡献

添加新功能时请确保：
1. 代码遵循现有风格
2. 添加完整的文档字符串
3. 更新 `__init__.py` 导出
4. 更新本 README
5. 添加使用示例
