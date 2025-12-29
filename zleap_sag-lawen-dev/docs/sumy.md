# DataFlow Sumy 文本摘要模块使用指南

## 概述

DataFlow Sumy 文本摘要模块是一个集成了 Sumy 库和大语言模型的高级文本摘要工具。它采用两阶段摘要策略：

1. **第一阶段**：使用 Sumy 的 TextRank 或 Luhn 算法提取关键句子
2. **第二阶段**：使用大模型基于专业的 sumy 模板对提取的句子进行总结和润色

这种结合方式既能保证摘要的准确性，又能生成信息完整、语言流畅的摘要文本。

## 特性

- 🚀 **智能算法选择**：根据文本句子数量自动选择最优算法（≤1000句用TextRank，>1000句用Luhn）
- 🌐 **多语言支持**：自动检测中文和英文文本
- 📊 **自适应压缩**：根据文本长度智能调整摘要长度和 token 限制
- ⚡ **性能优化**：针对不同规模的文本采用不同处理策略
- 📈 **详细日志**：提供完整的处理过程统计信息和时间消耗
- 🎯 **专业模板**：使用专门的 sumy 提示词模板，确保信息完整性和准确性

## 安装依赖

```bash
pip install sumy nltk
```

首次使用时会自动下载 NLTK 数据包（punkt、punkt_tab）。

## 快速开始

### 基础用法

```python
from dataflow.core.ai.sumy import SumySummarizer

# 创建摘要器实例
summarizer = SumySummarizer()

# 生成摘要（自动检测语言和压缩率）
result = await summarizer.generate_summary(
    text="你的长文本内容...",
    background="文档标题"
)

# result 是字典，直接访问字段
print(f"标题: {result['title']}")
print(f"摘要: {result['summary']}")
print(f"分类: {result['category']}")
print(f"标签: {', '.join(result['tags'])}")
```

### 高级用法

```python
# 指定压缩率（保留20%的句子）
result = await summarizer.generate_summary_with_ratio(
    text="长文本内容...",
    compression_ratio=0.2,
    background="技术文档"
)

print(f"摘要: {result['summary']}")

# 手动指定句子数量
result = await summarizer.generate_summary(
    text="长文本内容...",
    sentence_count=10,
    background="文章标题"
)

print(f"摘要: {result['summary']}")
```

## API 参考

### SumySummarizer 类

#### 构造函数

```python
def __init__(self, llm_client: Optional[BaseLLMClient] = None)
```

**参数：**
- `llm_client`: 可选的 LLM 客户端，默认使用全局客户端

#### 主要方法

##### `generate_summary()`

异步生成文本摘要的核心方法。

```python
async def generate_summary(
    self,
    text: str,
    sentence_count: Optional[int] = None,
    background: str = "文档",
    language: Optional[str] = None,
    compression_ratio: float = 0.3
) -> Dict[str, Any]
```

**参数：**
- `text` (str): 输入文本内容
- `sentence_count` (Optional[int]): 手动指定提取的句子数量，None 表示自动计算
- `background` (str): 文档背景信息，用于提示词上下文
- `language` (Optional[str]): 文本语言（"chinese"/"english"），None 表示自动检测
- `compression_ratio` (float): 压缩率（0-1），默认 0.3 表示保留 30% 的句子

**返回：**
- `Dict[str, Any]`: 包含摘要内容的字典，字段包括：
  - `title` (str): 文档标题
  - `summary` (str): 文档摘要
  - `category` (str): 文档分类
  - `tags` (List[str]): 关键词标签列表

**异常：**
- `AIError`: 摘要生成失败时抛出

**处理策略：**
- ≤10000 tokens：直接使用原文进行摘要，token限制300字
- 10000~50000 tokens：最多提取 150 个句子，token限制350字
- 50000~400000 tokens：最多提取 350 个句子，token限制450字
- >400000 tokens：最多提取 500 个句子，token限制550字

**时间统计输出：**
方法会自动输出详细的时间消耗统计，包括 Sumy 提取时间和 LLM 处理时间。

##### `generate_summary_with_ratio()`

基于压缩率的便捷方法。

```python
async def generate_summary_with_ratio(
    self,
    text: str,
    compression_ratio: float = 0.3,
    background: str = "文档",
    language: Optional[str] = None
) -> Dict[str, Any]
```

**参数：**
- `text` (str): 输入文本内容
- `compression_ratio` (float): 压缩率（0-1）
- `background` (str): 文档背景信息
- `language` (Optional[str]): 文本语言

**返回：**
- `Dict[str, Any]`: 包含摘要内容的字典，字段包括：
  - `title` (str): 文档标题
  - `summary` (str): 文档摘要
  - `category` (str): 文档分类
  - `tags` (List[str]): 关键词标签列表

##### `extract_key_sentences()`

提取关键句子（仅第一阶段）。

```python
def extract_key_sentences(
    self,
    text: str,
    sentence_count: int = 5,
    language: Optional[str] = None
) -> List[str]
```

**算法选择：**
- ≤1000 句子：使用 TextRank 算法（精确度高）
- >1000 句子：使用 Luhn 算法（速度快）

**注意：** 此方法已关闭详细日志输出，只保留基本的提取信息。

##### `detect_language()`

自动检测文本语言。

```python
def detect_language(self, text: str) -> str
```

**返回：**
- `"chinese"` 或 `"english"`

**检测逻辑：**
- 统计中英文字符比例
- 中文字符占比超过 30% 判定为中文

##### `count_sentences()`

统计文本句子数量。

```python
def count_sentences(self, text: str, language: Optional[str] = None) -> int
```

## 使用示例

### 示例 1：基础摘要生成

```python
from dataflow.core.ai.sumy import SumySummarizer

async def basic_example():
    summarizer = SumySummarizer()

    text = """
    人工智能（Artificial Intelligence，AI）是计算机科学的一个分支，致力于创建能够执行通常需要人类智能的任务的系统。
    这些任务包括学习、推理、问题解决、感知和语言理解。AI的发展可以分为多个阶段，从早期的符号主义到现代的深度学习。
    机器学习是AI的一个重要子领域，它使计算机能够从数据中学习而无需明确编程。深度学习是机器学习的一个子集，
    使用神经网络来模拟人脑的工作方式。自然语言处理（NLP）是另一个重要的AI领域，专注于计算机与人类语言之间的交互。
    """

    # 直接获取字典结果
    result = await summarizer.generate_summary(
        text=text,
        background="人工智能概述"
    )

    print("摘要结果：")
    print(f"标题: {result['title']}")
    print(f"摘要: {result['summary']}")
    print(f"分类: {result['category']}")
    print(f"标签: {result['tags']}")
```

### 示例 2：自定义压缩率

```python
async def compression_ratio_example():
    summarizer = SumySummarizer()

    # 长文本示例
    long_text = "..."  # 这里放入长文本

    # 使用不同压缩率生成摘要
    ratios = [0.1, 0.2, 0.3, 0.5]

    for ratio in ratios:
        result = await summarizer.generate_summary_with_ratio(
            text=long_text,
            compression_ratio=ratio,
            background=f"压缩率 {ratio*100:.0f}% 的摘要"
        )

        print(f"\n=== 压缩率 {ratio*100:.0f}% ===")
        print(f"摘要: {result['summary']}")
        print(f"摘要长度: {len(result['summary'])} 字符")
```

### 示例 3：多语言文本处理

```python
async def multilingual_example():
    summarizer = SumySummarizer()

    # 英文文本
    english_text = """
    Artificial Intelligence (AI) is a branch of computer science that aims to create systems capable of performing tasks that typically require human intelligence.
    These tasks include learning, reasoning, problem-solving, perception, and language understanding. The development of AI has gone through multiple stages...
    """

    # 中文文本
    chinese_text = """
    人工智能是计算机科学的一个分支，致力于创建能够执行通常需要人类智能的任务的系统。
    这些任务包括学习、推理、问题解决、感知和语言理解...
    """

    # 处理英文文本
    en_result = await summarizer.generate_summary(
        text=english_text,
        background="AI Overview"
    )
    print("英文摘要：", en_result['summary'])

    # 处理中文文本
    cn_result = await summarizer.generate_summary(
        text=chinese_text,
        background="人工智能概述"
    )
    print("中文摘要：", cn_result['summary'])
```


## 最佳实践

### 1. 选择合适的压缩率

- **新闻文章**：0.2-0.3（保留关键信息）
- **技术文档**：0.1-0.2（突出重点）
- **学术论文**：0.15-0.25（平衡完整性和简洁性）
- **小说/故事**：0.05-0.15（保留主要情节）

## 性能指标
### 摘要质量评估

- **准确性**：基于 TextRank 算法，关键句子提取准确率 > 85%
- **流畅性**：大模型润色，生成自然流畅的摘要
- **完整性**：保持原文主要信息和逻辑结构

## 故障排除

### 常见问题

1. **NLTK 数据下载失败**
   ```python
   # 手动下载 NLTK 数据
   import nltk
   nltk.download('punkt')
   nltk.download('punkt_tab')
   ```

2. **内存不足**
   - 减少文本长度
   - 降低压缩率
   - 使用分段处理

3. **摘要质量不佳**
   - 调整压缩率
   - 优化原文质量
   - 尝试不同的语言设置

4. **处理超时**
   ```python
   # 增加超时时间
   summary = await summarizer.generate_summary(
       text=text,
       title="文档"
   )  # 默认超时为600秒
   ```

### 日志调试

启用详细日志：

```python
import logging
logging.getLogger("core.ai.sumy").setLevel(logging.DEBUG)
```

## 测试指南

### 运行测试

项目提供了完整的测试脚本 `tests/ai/test_sumy_summary.py`，支持多种测试模式：

#### 1. 使用内置示例文本测试

```bash
cd tests/ai
python test_sumy_summary.py
```

这将使用内置的人工智能概述文本进行测试，包括：
- 自动语言检测
- 智能处理策略（根据文本长度自动决策）
- 手动指定句子数测试

#### 2. 使用自定义文件测试

```bash
# 使用文件并自动计算压缩率
 python .\tests\ai\test_sumy_summary.py .\tests\ai\test_data\AI.txt 

```



### 测试输出示例

```
======================================================================
Sumy + LLM 摘要测试 - 内置示例
======================================================================

自动检测语言: chinese

原文统计:
  字符数: 895
  句子数: 13

======================================================================
测试1: 自动智能处理（根据文本长度自动决策）
======================================================================

生成的元数据:
  {
    "title": "人工智能发展概述",
    "summary": "人工智能（AI）是计算机科学的重要分支，旨在研究能模拟人类智能的系统。近年来，深度学习技术的突破使AI在图像识别、语音识别、自然语言处理等领域取得巨大进展。深度学习通过多层神经网络学习数据的高级特征，成功得益于大规模数据集、强大计算能力和改进算法。在NLP领域，Transformer架构和基于Transformer的模型如BERT、GPT在各种任务上刷新记录，展现出强大的推理和问题解决能力。然而，AI发展也带来算法偏见、隐私保护、就业影响等挑战，需要制定伦理准则和监管框架。",
    "category": "技术文档",
    "tags": ["人工智能", "深度学习", "自然语言处理", "机器学习", "算法偏见"]
  }

摘要长度: 256 字符
```

## 重要变更说明

### API 变更（v3.0+）

1. **返回类型变更**：
   - 之前（v2.0）：返回 `LLMResponse` 对象，需要通过 `response.content` 获取JSON字符串并解析
   - 现在（v3.0）：直接返回 `Dict[str, Any]` 字典对象，包含所有元数据字段
   - 好处：无需手动JSON解析，代码更简洁，自动重试和验证

2. **自动JSON验证和重试**：
   - 使用 `chat_with_schema()` 方法，提供：
     - 自动JSON解析（处理markdown代码块）
     - Schema验证（确保所有必需字段存在）
     - 智能重试（最多3次，指数退避：1s → 2s → 4s）

3. **参数名称**：
   - `background`：提供文档背景信息

4. **响应字段**：
   - `title` (str): 文档标题
   - `summary` (str): 摘要内容
   - `category` (str): 文档分类
   - `tags` (List[str]): 关键词标签列表

### 从 v2.0 迁移到 v3.0

**之前的代码（v2.0）：**
```python
response = await summarizer.generate_summary(text=text, background="标题")
metadata = json.loads(response.content)  # 需要手动解析JSON
print(f"摘要: {metadata['summary']}")
```

**现在的代码（v3.0）：**
```python
result = await summarizer.generate_summary(text=text, background="标题")
print(f"摘要: {result['summary']}")  # 直接使用字典
```

### v2.0 的其他特性

4. **新增专业模板**：
   - 使用 `article_metadata_with_sumy` 模板
   - 强调关键句完整覆盖和零遗漏原则
   - 生成更高质量的摘要

## 更新日志

### v3.0.0
- **重大更新**：返回类型从 `LLMResponse` 改为 `Dict[str, Any]`
- **自动化改进**：使用 `chat_with_schema()` 实现自动JSON解析和验证
- **智能重试**：集成指数退避重试机制（最多3次，1s → 2s → 4s）
- **代码简化**：移除所有手动JSON解析代码
- **更好的错误处理**：Schema验证确保所有必需字段存在
- **向后兼容性**：API签名保持一致，仅返回类型改变

### v2.0.0
- **重大更新**：返回格式从纯文本改为 JSON 元数据
- **新增功能**：集成文章分类和标签生成
- **性能优化**：根据文本长度自适应 token 限制
- **模板升级**：使用专业的 sumy 提示词模板
- **时间统计**：增加详细的时间消耗输出

### v1.0.0
- 初始版本发布
- 支持 TextRank 和 Luhn 算法
- 自动语言检测
- 智能压缩率调整
- 性能优化和日志记录
- 完整的测试套件

---

如有问题或建议，请联系开发团队或提交 Issue。