# DataFlow API 接口文档

**数据流智能引擎 - API接口文档**

*by Zleap Team（智跃团队）*

## 目录

- [1. 概览](#1-概览)
- [2. Python SDK](#2-python-sdk)
- [3. RESTful API](#3-restful-api)
- [4. 错误码](#4-错误码)

---

## 1. 概览

### 1.1 接口类型

DataFlow 提供两种使用方式：

1. **Python SDK**（推荐）：直接在Python代码中使用
2. **RESTful API**（可选）：通过HTTP接口调用

### 1.2 认证方式

```python
# Python SDK
from dataflow import DataFlow

client = DataFlow(
    source_config_id="your-user-id",
    api_key="your-api-key"  # 可选，如果启用了API服务
)

# RESTful API
# Header: Authorization: Bearer <api_key>
```

---

## 2. Python SDK

### 2.1 安装

```bash
pip install dataflow
# 或使用 uv
uv pip install dataflow
```

### 2.2 Load - 数据加载

#### 2.2.1 load()

**功能**：载入文档并生成摘要、切块

**签名**：

```python
async def load(
    config: LoadConfig,
    source_config_id: str
) -> List[Article]
```

**参数**：

```python
class LoadConfig:
    type: str  # "path" | "url" | "text"
    origin: List[str]  # 数据源列表
    filter: bool = False  # 是否智能过滤
    background: str = ""  # 背景信息
    description: str = ""  # 任务描述
    chunk_size: int = 1000  # 切块大小
    chunk_overlap: int = 200  # 切块重叠
```

**返回**：

```python
class Article:
    id: str
    source_config_id: str
    title: str
    summary: str
    category: str
    tags: List[str]
    headings: List[str]
    status: str
    created_time: datetime
```

**示例**：

```python
from dataflow import DataFlow, LoadConfig

client = DataFlow(source_config_id="user-001")

# 加载本地文档
config = LoadConfig(
    type="path",
    origin=["./docs/article1.md", "./docs/article2.md"],
    background="这是AI技术文档",
    chunk_size=1000
)

articles = await client.load(config)

for article in articles:
    print(f"文章：{article.title}")
    print(f"摘要：{article.summary}")
    print(f"标签：{article.tags}")
```

**错误**：

- `FileNotFoundError`: 文件不存在
- `ValidationError`: 配置参数错误
- `LLMError`: LLM调用失败

---

### 2.3 Extract - 事项提取

#### 2.3.1 extract()

**功能**：从文章中提取事项和实体

**签名**：

```python
async def extract(
    config: ExtractConfig,
    source_config_id: str
) -> List[SourceEvent]
```

**参数**：

```python
class ExtractConfig:
    article_ids: List[str]  # 文章ID列表
    parallel: bool = True  # 是否并发处理
    filter_mode: str = "all"  # "all" | "intelligent"
    background: str = ""  # 背景信息
    custom_entity_types: Optional[List[str]] = None  # 自定义实体类型
```

**返回**：

```python
class SourceEvent:
    id: str
    source_config_id: str
    type: str  # "ARTICLE" | "CHAT"
    title: str
    summary: str
    content: str
    keywords: List[str]
    category: str  # "TECHNICAL" | "BUSINESS" | "PERSONAL" | "OTHER"
    priority: str  # "HIGH" | "MEDIUM" | "LOW"
    status: str  # "TODO" | "IN_PROGRESS" | "DONE" | "UNKNOWN"
    entities: Dict[str, List[str]]  # 实体字典
    tags: List[str]
    created_time: datetime
```

**示例**：

```python
# 提取事项
config = ExtractConfig(
    article_ids=["article-001", "article-002"],
    parallel=True,
    filter_mode="intelligent",
    background="这是关于AI项目的文档"
)

events = await client.extract(config)

for event in events:
    print(f"事项：{event.title}")
    print(f"类别：{event.category}")
    print(f"实体：{event.entities}")
```

---

### 2.4 Search - 智能检索

#### 2.4.1 search()

**功能**：根据查询检索相关事项

**签名**：

```python
async def search(
    config: SearchConfig
) -> SearchResult
```

**参数**：

```python
class SearchConfig:
    query: str  # 查询文本
    source_config_id: str  # 信息源ID
    breadth: int = 2  # 横向扩展层数
    depth: int = 3  # 纵向扩展跳数
    threshold: float = 0.5  # 相关度阈值 (0-1)
    top_k: int = 10  # 返回数量
    filters: Optional[Dict[str, Any]] = None  # 过滤条件
```

**返回**：

```python
class SearchResult:
    events: List[SourceEvent]  # 事项列表
    scores: Dict[str, float]  # {event_id: score}
    metadata: Dict[str, Any]  # 元数据
```

**示例**：

```python
# 基础检索
config = SearchConfig(
    query="302.ai的大模型微调方案",
    source_config_id="user-001",
    top_k=10
)

result = await client.search(config)

for event in result.events:
    score = result.scores[event.id]
    print(f"[{score:.2f}] {event.title}")
    print(f"  摘要：{event.summary}")


# 高级检索（多跳召回）
config = SearchConfig(
    query="LLM训练优化",
    source_config_id="user-001",
    breadth=3,  # 横向扩展3层
    depth=2,    # 纵向跳2次
    threshold=0.6,  # 相关度阈值0.6
    filters={
        "category": ["TECHNICAL"],
        "priority": ["HIGH", "MEDIUM"]
    }
)

result = await client.search(config)
```

---

### 2.5 Report - 报告生成

#### 2.5.1 report()

**功能**：根据事项生成报告

**签名**：

```python
async def report(
    config: ReportConfig
) -> Report
```

**参数**：

```python
class ReportConfig:
    event_ids: List[str]  # 事项ID列表（可选，与query二选一）
    query: Optional[str] = None  # 查询文本（可选）
    source_config_id: str  # 信息源ID
    title: str  # 报告标题
    type: str = "GENERAL"  # "GENERAL" | "SUMMARY" | "ANALYSIS"
    style: str = "formal"  # "formal" | "casual" | "technical"
    length: str = "medium"  # "short" | "medium" | "long"
    focus_topics: Optional[List[str]] = None  # 关注话题
    order_by: str = "original"  # "original" | "intelligent"
```

**返回**：

```python
class Report:
    id: str
    source_config_id: str
    title: str
    summary: str
    content: str  # Markdown格式
    type: str
    event_ids: List[str]
    config: Dict[str, Any]
    created_time: datetime
```

**示例**：

```python
# 方式1：基于事项ID生成报告
config = ReportConfig(
    event_ids=["event-001", "event-002", "event-003"],
    source_config_id="user-001",
    title="AI项目进展报告",
    type="SUMMARY",
    style="formal",
    length="medium"
)

report = await client.report(config)
print(report.content)


# 方式2：基于查询生成报告
config = ReportConfig(
    query="302.ai项目的所有技术问题和解决方案",
    source_config_id="user-001",
    title="技术问题汇总",
    type="ANALYSIS",
    focus_topics=["大模型", "微调", "部署"],
    order_by="intelligent"  # 智能排序
)

report = await client.report(config)
```

---

### 2.6 Chat - 智能问答

#### 2.6.1 chat()

**功能**：基于事项进行问答

**签名**：

```python
async def chat(
    config: ChatConfig
) -> ChatResponse
```

**参数**：

```python
class ChatConfig:
    query: str  # 用户问题
    source_config_id: str  # 信息源ID
    context_depth: int = 2  # 上下文深度
    context_breadth: int = 5  # 上下文广度
    conversation_id: Optional[str] = None  # 会话ID（用于多轮对话）
```

**返回**：

```python
class ChatResponse:
    answer: str  # 回答
    sources: List[SourceEvent]  # 来源事项
    conversation_id: str  # 会话ID
    metadata: Dict[str, Any]  # 元数据
```

**示例**：

```python
# 单轮问答
config = ChatConfig(
    query="302.ai的大模型部署遇到了什么问题？",
    source_config_id="user-001"
)

response = await client.chat(config)
print(response.answer)
print("\n来源：")
for source in response.sources:
    print(f"- {source.title}")


# 多轮对话
conversation_id = None

# 第1轮
response1 = await client.chat(ChatConfig(
    query="302.ai有哪些项目？",
    source_config_id="user-001"
))
conversation_id = response1.conversation_id

# 第2轮（带上下文）
response2 = await client.chat(ChatConfig(
    query="这些项目的进展如何？",  # "这些项目"指代第1轮中的项目
    source_config_id="user-001",
    conversation_id=conversation_id
))
```

---

### 2.7 完整示例

```python
import asyncio
from dataflow import DataFlow, LoadConfig, ExtractConfig, SearchConfig

async def main():
    # 初始化客户端
    client = DataFlow(source_config_id="user-001")

    # 1. 加载文档
    print("=== 加载文档 ===")
    load_config = LoadConfig(
        type="path",
        origin=["./docs/ai_project.md"],
        background="这是AI项目文档"
    )
    articles = await client.load(load_config)
    print(f"成功加载 {len(articles)} 篇文章")

    # 2. 提取事项
    print("\n=== 提取事项 ===")
    extract_config = ExtractConfig(
        article_ids=[a.id for a in articles],
        parallel=True,
        filter_mode="intelligent"
    )
    events = await client.extract(extract_config)
    print(f"提取 {len(events)} 个事项")

    # 3. 检索事项
    print("\n=== 检索事项 ===")
    search_config = SearchConfig(
        query="大模型部署问题",
        source_config_id="user-001",
        depth=2,
        top_k=5
    )
    result = await client.search(search_config)
    print("检索结果：")
    for event in result.events:
        score = result.scores[event.id]
        print(f"  [{score:.2f}] {event.title}")

    # 4. 生成报告
    print("\n=== 生成报告 ===")
    from dataflow import ReportConfig
    report_config = ReportConfig(
        event_ids=[e.id for e in result.events],
        source_config_id="user-001",
        title="大模型部署问题汇总",
        type="ANALYSIS"
    )
    report = await client.report(report_config)
    print(report.content)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 3. RESTful API

### 3.1 基础信息

**Base URL**: `http://localhost:8000/api/v1`

**认证**:

```
Header: Authorization: Bearer <api_key>
```

**通用响应格式**：

```json
{
  "success": true,
  "data": {...},
  "error": null
}
```

### 3.2 端点列表

#### 3.2.1 POST /load

加载文档

**请求**：

```json
{
  "config": {
    "type": "path",
    "origin": ["./docs/article.md"],
    "filter": false,
    "background": "AI文档",
    "chunk_size": 1000
  },
  "source_config_id": "user-001"
}
```

**响应**：

```json
{
  "success": true,
  "data": {
    "articles": [
      {
        "id": "article-001",
        "title": "深度学习入门",
        "summary": "本文介绍...",
        "tags": ["AI", "深度学习"],
        "created_time": "2024-01-01T00:00:00Z"
      }
    ]
  }
}
```

---

#### 3.2.2 POST /extract

提取事项

**请求**：

```json
{
  "config": {
    "article_ids": ["article-001"],
    "parallel": true,
    "filter_mode": "intelligent",
    "background": "AI项目"
  },
  "source_config_id": "user-001"
}
```

**响应**：

```json
{
  "success": true,
  "data": {
    "events": [
      {
        "id": "event-001",
        "title": "部署大模型服务",
        "summary": "需要在生产环境部署...",
        "category": "TECHNICAL",
        "priority": "HIGH",
        "entities": {
          "TOPIC": ["大模型", "部署"],
          "ACTION": ["部署", "配置"]
        }
      }
    ]
  }
}
```

---

#### 3.2.3 POST /search

检索事项

**请求**：

```json
{
  "config": {
    "query": "大模型微调方案",
    "source_config_id": "user-001",
    "breadth": 2,
    "depth": 3,
    "threshold": 0.5,
    "top_k": 10
  }
}
```

**响应**：

```json
{
  "success": true,
  "data": {
    "events": [...],
    "scores": {
      "event-001": 0.95,
      "event-002": 0.87
    },
    "metadata": {
      "total_recalled": 25,
      "after_filtering": 10
    }
  }
}
```

---

#### 3.2.4 POST /report

生成报告

**请求**：

```json
{
  "config": {
    "event_ids": ["event-001", "event-002"],
    "source_config_id": "user-001",
    "title": "技术问题汇总",
    "type": "SUMMARY",
    "style": "formal",
    "length": "medium"
  }
}
```

**响应**：

```json
{
  "success": true,
  "data": {
    "report": {
      "id": "report-001",
      "title": "技术问题汇总",
      "content": "# 技术问题汇总\n\n## 1. 问题概述\n...",
      "created_time": "2024-01-01T00:00:00Z"
    }
  }
}
```

---

#### 3.2.5 POST /chat

智能问答

**请求**：

```json
{
  "config": {
    "query": "302.ai项目有哪些技术难点？",
    "source_config_id": "user-001",
    "context_depth": 2,
    "conversation_id": null
  }
}
```

**响应**：

```json
{
  "success": true,
  "data": {
    "answer": "根据相关事项，302.ai项目主要面临以下技术难点：\n1. 大模型部署...\n2. 数据处理...",
    "sources": [
      {
        "id": "event-001",
        "title": "大模型部署问题"
      }
    ],
    "conversation_id": "conv-001"
  }
}
```

---

## 4. 错误码

### 4.1 HTTP状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

### 4.2 业务错误码

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "配置参数验证失败: chunk_size必须大于0",
    "details": {...}
  }
}
```

**错误码列表**：

| 错误码 | 说明 |
|--------|------|
| `VALIDATION_ERROR` | 参数验证错误 |
| `FILE_NOT_FOUND` | 文件不存在 |
| `LLM_ERROR` | LLM调用失败 |
| `STORAGE_ERROR` | 数据库错误 |
| `AUTH_ERROR` | 认证失败 |
| `RATE_LIMIT_ERROR` | 请求频率超限 |
| `INTERNAL_ERROR` | 内部错误 |

---

## 5. 速率限制

| 端点 | 限制 |
|------|------|
| `/load` | 10次/分钟 |
| `/extract` | 20次/分钟 |
| `/search` | 100次/分钟 |
| `/report` | 10次/分钟 |
| `/chat` | 50次/分钟 |

---

## 6. 下一步

- 阅读 [开发指南](./development.md)
- 阅读 [部署指南](./deployment.md)
