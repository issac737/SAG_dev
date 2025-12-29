# DataFlow 模块详细设计文档

**数据流智能引擎 - 模块设计**

*by Zleap Team（智跃团队）*

## 目录

- [1. 概览](#1-概览)
- [2. 基础层模块](#2-基础层模块)
- [3. 业务层模块](#3-业务层模块)
- [4. 应用层模块](#4-应用层模块)
- [5. 数据模型](#5-数据模型)
- [6. 错误处理](#6-错误处理)

---

## 1. 概览

### 1.1 模块架构

```
dataflow/
├── core/                # 核心模块
│   ├── ai/             # AI调用模块
│   ├── agent/          # Agent编排模块
│   ├── storage/        # 存储模块
│   ├── prompt/         # 提示词模块
│   └── config/         # 配置模块
├── modules/            # 应用模块
│   ├── load/           # 数据加载模块
│   ├── extract/        # 事项提取模块
│   ├── search/         # 智能检索模块
│   ├── report/         # 报告生成模块
│   └── chat/           # 智能问答模块
├── models/             # 数据模型
│   ├── source.py
│   ├── article.py
│   ├── event.py
│   └── entity.py
├── utils/              # 工具函数
│   ├── text.py
│   ├── time.py
│   ├── logger.py
│   └── token_estimator.py
└── exceptions/         # 异常定义
    └── errors.py
```

---

## 2. 基础层模块

### 2.1 AI模块（core/ai）

#### 2.1.1 模块职责

- 封装多种LLM提供商（OpenAI, Anthropic, 本地模型）
- 提供统一的调用接口
- 实现重试机制与错误处理
- 支持结构化输出（JSON Schema）
- 支持流式响应

#### 2.1.2 接口设计

```python
# core/ai/llm.py

from typing import Optional, Dict, Any, List, AsyncIterator
from pydantic import BaseModel
from enum import Enum

class LLMProvider(str, Enum):
    """LLM提供商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"

class LLMMessage(BaseModel):
    """消息模型"""
    role: str  # system, user, assistant
    content: str

class LLMResponse(BaseModel):
    """LLM响应模型"""
    content: str
    model: str
    usage: Dict[str, int]  # prompt_tokens, completion_tokens, total_tokens
    finish_reason: str

class LLMClient:
    """LLM客户端基类"""

    def __init__(
        self,
        provider: LLMProvider,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.config = kwargs

    async def chat(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> LLMResponse:
        """
        聊天补全

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            LLM响应

        Raises:
            LLMError: LLM调用失败
        """
        raise NotImplementedError

    async def chat_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        流式聊天补全

        Yields:
            生成的文本片段
        """
        raise NotImplementedError

    async def chat_with_schema(
        self,
        messages: List[LLMMessage],
        response_schema: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> Dict[str, Any]:
        """
        结构化输出（JSON Schema）

        Args:
            messages: 消息列表
            response_schema: JSON Schema定义

        Returns:
            解析后的JSON对象

        Raises:
            LLMError: LLM调用失败
            ValidationError: 响应不符合Schema
        """
        raise NotImplementedError


class LLMRetryClient:
    """带重试机制的LLM客户端"""

    def __init__(
        self,
        client: LLMClient,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0
    ):
        self.client = client
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor

    async def chat(
        self,
        messages: List[LLMMessage],
        **kwargs
    ) -> LLMResponse:
        """
        带重试的聊天补全

        实现指数退避重试策略：
        - 第1次失败：等待1秒
        - 第2次失败：等待2秒
        - 第3次失败：等待4秒
        """
        last_error = None
        delay = self.retry_delay

        for attempt in range(self.max_retries):
            try:
                return await self.client.chat(messages, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= self.backoff_factor

        raise LLMError(f"LLM调用失败，已重试{self.max_retries}次") from last_error


# 工厂函数
def create_llm_client(
    provider: LLMProvider,
    model: str,
    with_retry: bool = True,
    **kwargs
) -> Union[LLMClient, LLMRetryClient]:
    """
    创建LLM客户端

    Args:
        provider: 提供商
        model: 模型名称
        with_retry: 是否启用重试

    Returns:
        LLM客户端实例

    Example:
        >>> client = create_llm_client(
        ...     provider=LLMProvider.OPENAI,
        ...     model="sophnet/Qwen3-30B-A3B-Thinking-2507",
        ...     with_retry=True
        ... )
    """
    if provider == LLMProvider.OPENAI:
        client = OpenAIClient(model=model, **kwargs)
    elif provider == LLMProvider.ANTHROPIC:
        client = AnthropicClient(model=model, **kwargs)
    else:
        raise ValueError(f"不支持的提供商: {provider}")

    if with_retry:
        return LLMRetryClient(client)
    return client
```

#### 2.1.3 使用示例

```python
# 示例1: 基础调用
client = create_llm_client(
    provider=LLMProvider.OPENAI,
    model="sophnet/Qwen3-30B-A3B-Thinking-2507",
    api_key="sk-xxx"
)

response = await client.chat(
    messages=[
        LLMMessage(role="system", content="你是一个专业的摘要生成助手"),
        LLMMessage(role="user", content="请为以下文章生成摘要...")
    ],
    temperature=0.7
)

print(response.content)


# 示例2: 结构化输出
schema = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string"}
    },
    "required": ["summary", "tags", "category"]
}

result = await client.chat_with_schema(
    messages=[...],
    response_schema=schema
)

print(result["summary"])
print(result["tags"])


# 示例3: 流式输出
async for chunk in client.chat_stream(messages=[...]):
    print(chunk, end="", flush=True)
```

---

### 2.2 Storage模块（core/storage）

#### 2.2.1 模块职责

- 封装MySQL、Elasticsearch、Redis的访问
- 提供统一的数据访问接口
- 实现连接池管理
- 支持事务处理

#### 2.2.2 目录结构

```
core/storage/
├── elasticsearch.py          # ES通用客户端
├── mysql.py                  # MySQL客户端
├── redis.py                  # Redis客户端
├── documents/                # ES Document模型层（elasticsearch-dsl）
│   ├── __init__.py
│   ├── entity_vector.py      # 实体向量Document
│   ├── event_vector.py       # 事件向量Document
│   └── article_section.py    # 文章片段Document
└── repositories/             # ES Repository访问层
    ├── __init__.py
    ├── base.py               # Repository基类
    ├── entity_repository.py  # 实体向量查询
    ├── event_repository.py   # 事件向量查询
    └── article_repository.py # 文章片段查询
```

**架构说明：**

| 层次           | 职责         | 技术                       |
| -------------- | ------------ | -------------------------- |
| **Repository** | 业务查询封装 | elasticsearch-dsl Query    |
| **Document**   | 索引模型定义 | elasticsearch-dsl Document |
| **Client**     | 底层连接管理 | elasticsearch-py           |

**设计原则：**
- `documents/` - 定义索引 mapping（类似 SQLAlchemy ORM）
- `repositories/` - 封装业务查询逻辑（向量检索、过滤组合）
- 底层使用 `elasticsearch-dsl` 提供类型安全和链式查询

#### 2.2.3 接口设计

```python
# core/storage/mysql.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

class MySQLClient:
    """MySQL客户端"""

    def __init__(self, database_url: str, **kwargs):
        self.engine = create_async_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            **kwargs
        )
        self.session_factory = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    @asynccontextmanager
    async def session(self) -> AsyncSession:
        """
        获取数据库会话（上下文管理器）

        Example:
            >>> async with mysql.session() as session:
            ...     result = await session.execute(query)
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def close(self):
        """关闭连接池"""
        await self.engine.dispose()


# core/storage/elasticsearch.py

from elasticsearch import AsyncElasticsearch
from typing import List, Dict, Any, Optional

class ElasticsearchClient:
    """Elasticsearch客户端"""

    def __init__(self, hosts: List[str], **kwargs):
        self.client = AsyncElasticsearch(hosts=hosts, **kwargs)

    async def index_document(
        self,
        index: str,
        document: Dict[str, Any],
        doc_id: Optional[str] = None
    ) -> str:
        """
        索引文档

        Args:
            index: 索引名称
            document: 文档内容
            doc_id: 文档ID（可选）

        Returns:
            文档ID
        """
        response = await self.client.index(
            index=index,
            document=document,
            id=doc_id
        )
        return response["_id"]

    async def search(
        self,
        index: str,
        query: Dict[str, Any],
        size: int = 10,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        搜索文档

        Args:
            index: 索引名称
            query: 查询DSL
            size: 返回数量

        Returns:
            文档列表
        """
        response = await self.client.search(
            index=index,
            query=query,
            size=size,
            **kwargs
        )
        return [hit["_source"] for hit in response["hits"]["hits"]]

    async def vector_search(
        self,
        index: str,
        field: str,
        vector: List[float],
        size: int = 10,
        filter_query: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        向量检索

        Args:
            index: 索引名称
            field: 向量字段名
            vector: 查询向量
            size: 返回数量
            filter_query: 过滤条件

        Returns:
            相似文档列表
        """
        knn_query = {
            "field": field,
            "query_vector": vector,
            "k": size,
            "num_candidates": size * 10
        }

        if filter_query:
            knn_query["filter"] = filter_query

        response = await self.client.search(
            index=index,
            knn=knn_query
        )

        return [
            {
                **hit["_source"],
                "_score": hit["_score"]
            }
            for hit in response["hits"]["hits"]
        ]

    async def close(self):
        """关闭连接"""
        await self.client.close()


# core/storage/documents/ - Elasticsearch Document 模型

from elasticsearch_dsl import Document, Text, Keyword, DenseVector, Date, Integer

class EntityVectorDocument(Document):
    """实体向量文档模型（使用 elasticsearch-dsl）"""

    # 字段定义
    entity_id = Keyword(required=True)
    source_config_id = Keyword(required=True)
    type = Keyword(required=True)  # 实体类型：PERSON, ORGANIZATION, TOPIC等
    name = Text(fields={"keyword": Keyword()})
    vector = DenseVector(dims=1536, index=True, similarity="cosine")
    created_time = Date()

    class Index:
        """索引配置"""
        name = "entity_vectors"
        settings = {"number_of_shards": 3, "number_of_replicas": 1}

    def save(self, **kwargs):
        """保存文档"""
        return super().save(**kwargs)


class EventVectorDocument(Document):
    """事件向量文档模型"""

    # 字段定义
    event_id = Keyword(required=True)
    source_config_id = Keyword(required=True)
    article_id = Keyword(required=True)

    # 文本字段（使用默认分词器）
    title = Text(fields={"keyword": Keyword()})
    summary = Text()
    content = Text()

    # 向量字段
    title_vector = DenseVector(dims=1536, index=True, similarity="cosine")
    content_vector = DenseVector(dims=1536, index=True, similarity="cosine")

    # 分类和标签
    category = Keyword()
    tags = Keyword(multi=True)  # 数组字段
    entity_ids = Keyword(multi=True)  # 关联的实体ID列表

    # 时间字段
    start_time = Date()
    end_time = Date()
    created_time = Date()

    class Index:
        """索引配置"""
        name = "event_vectors"
        settings = {"number_of_shards": 3, "number_of_replicas": 1}

    def save(self, **kwargs):
        """保存文档"""
        return super().save(**kwargs)


class ArticleSectionDocument(Document):
    """文章片段文档模型"""

    # 字段定义
    section_id = Keyword(required=True)
    article_id = Keyword(required=True)
    source_config_id = Keyword(required=True)
    rank = Integer()  # 片段排序

    # 文本字段（使用默认分词器）
    heading = Text(fields={"keyword": Keyword()})
    content = Text()

    # 向量字段
    heading_vector = DenseVector(dims=1536, index=True, similarity="cosine")
    content_vector = DenseVector(dims=1536, index=True, similarity="cosine")

    # 元数据
    section_type = Keyword()  # 片段类型：heading, content等
    content_length = Integer()  # 内容长度

    # 时间字段
    created_time = Date()
    updated_time = Date()

    class Index:
        """索引配置"""
        name = "article_sections"
        settings = {"number_of_shards": 3, "number_of_replicas": 1}

    def save(self, **kwargs):
        """保存文档"""
        return super().save(**kwargs)


# core/storage/repositories/ - Repository 业务查询层

from elasticsearch_dsl import Q, Search
from dataflow.core.storage.repositories.base import BaseRepository

class BaseRepository(ABC):
    """Repository 基类"""

    def __init__(self, es_client: AsyncElasticsearch):
        """
        初始化 Repository

        Args:
            es_client: Elasticsearch 异步客户端
        """
        self.es_client = es_client

    async def index_document(
        self, index: str, doc_id: str, document: Dict[str, Any]
    ) -> str:
        """索引单个文档"""
        response = await self.es_client.index(index=index, id=doc_id, document=document)
        return response["_id"]

    async def get_document(self, index: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """获取单个文档"""
        try:
            response = await self.es_client.get(index=index, id=doc_id)
            return response["_source"]
        except Exception:
            return None

    async def delete_document(self, index: str, doc_id: str) -> bool:
        """删除单个文档"""
        try:
            await self.es_client.delete(index=index, id=doc_id)
            return True
        except Exception:
            return False

    async def bulk_index(
        self, index: str, documents: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """批量索引文档"""
        from elasticsearch.helpers import async_bulk

        actions = [
            {
                "_index": index,
                "_id": doc.get("_id") or doc.get("id"),
                "_source": {k: v for k, v in doc.items() if k not in ["_id", "id"]},
            }
            for doc in documents
        ]

        success, failed = await async_bulk(self.es_client, actions, raise_on_error=False)
        return {"success": success, "failed": len(failed) if isinstance(failed, list) else 0}


class EntityVectorRepository(BaseRepository):
    """实体向量 Repository"""

    INDEX_NAME = "entity_vectors"

    async def index_entity(
        self,
        entity_id: str,
        source_config_id: str,
        entity_type: str,
        name: str,
        vector: List[float],
        **kwargs,
    ) -> str:
        """索引单个实体"""
        document = {
            "entity_id": entity_id,
            "source_config_id": source_config_id,
            "type": entity_type,
            "name": name,
            "vector": vector,
            **kwargs,
        }
        return await self.index_document(self.INDEX_NAME, entity_id, document)

    async def search_by_name(
        self, name: str, source_config_id: Optional[str] = None, size: int = 10
    ) -> List[Dict[str, Any]]:
        """按名称搜索实体（模糊匹配）"""
        s = Search(using=self.es_client, index=self.INDEX_NAME)
        s = s.query("match", name=name)

        if source_config_id:
            s = s.filter("term", source_config_id=source_config_id)

        s = s[:size]
        response = await s.execute()
        return [hit.to_dict() for hit in response]

    async def search_similar(
        self,
        query_vector: List[float],
        k: int = 10,
        source_config_id: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """向量相似度搜索"""
        knn_query = {
            "field": "vector",
            "query_vector": query_vector,
            "k": k,
            "num_candidates": k * 10,
        }

        # 添加过滤条件
        filters = []
        if source_config_id:
            filters.append(Q("term", source_config_id=source_config_id))
        if entity_type:
            filters.append(Q("term", type=entity_type))

        if filters:
            knn_query["filter"] = Q("bool", must=filters)

        response = await self.es_client.search(index=self.INDEX_NAME, knn=knn_query)

        return [
            {**hit["_source"], "_score": hit["_score"]}
            for hit in response["hits"]["hits"]
        ]

    async def get_by_source(
        self, source_config_id: str, entity_type: Optional[str] = None, size: int = 100
    ) -> List[Dict[str, Any]]:
        """获取信息源的所有实体"""
        s = Search(using=self.es_client, index=self.INDEX_NAME)
        s = s.filter("term", source_config_id=source_config_id)

        if entity_type:
            s = s.filter("term", type=entity_type)

        s = s[:size]
        response = await s.execute()
        return [hit.to_dict() for hit in response]


class EventVectorRepository(BaseRepository):
    """事件向量 Repository（提供全文检索、向量检索、时间范围查询等）"""
    INDEX_NAME = "event_vectors"

    async def index_event(
        self, event_id: str, source_config_id: str, article_id: str,
        title: str, summary: str, content: str,
        title_vector: List[float], content_vector: List[float],
        **kwargs
    ) -> str:
        """索引单个事件"""
        # 实现略...

    async def search_by_text(
        self, query: str, source_config_id: Optional[str] = None, size: int = 10
    ) -> List[Dict[str, Any]]:
        """全文检索（支持标题、摘要、内容多字段查询）"""
        # 实现略...

    async def search_similar_by_title(
        self, query_vector: List[float], k: int = 10,
        source_config_id: Optional[str] = None, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """通过标题向量搜索相似事件"""
        # 实现略...

    async def search_similar_by_content(
        self, query_vector: List[float], k: int = 10,
        source_config_id: Optional[str] = None, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """通过内容向量搜索相似事件"""
        # 实现略...

    async def search_by_time_range(
        self, start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        source_config_id: Optional[str] = None, size: int = 100
    ) -> List[Dict[str, Any]]:
        """按时间范围搜索事件"""
        # 实现略...

    async def search_by_entities(
        self, entity_ids: List[str],
        source_config_id: Optional[str] = None, size: int = 100
    ) -> List[Dict[str, Any]]:
        """按关联实体搜索事件"""
        # 实现略...


class ArticleSectionRepository(BaseRepository):
    """文章片段 Repository（按文章查询、语义相似检索等）"""
    INDEX_NAME = "article_sections"

    async def index_section(
        self, section_id: str, article_id: str, source_config_id: str,
        rank: int, heading: Optional[str], content: str,
        heading_vector: Optional[List[float]], content_vector: List[float],
        **kwargs
    ) -> str:
        """索引单个文章片段"""
        # 实现略...

    async def get_by_article(
        self, article_id: str, sort_by_rank: bool = True
    ) -> List[Dict[str, Any]]:
        """获取文章的所有片段（按rank排序）"""
        # 实现略...

    async def search_similar_by_content(
        self, query_vector: List[float], k: int = 10,
        source_config_id: Optional[str] = None, section_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """通过内容向量搜索相似片段"""
        # 实现略...

    async def search_by_text(
        self, query: str, source_config_id: Optional[str] = None, size: int = 10
    ) -> List[Dict[str, Any]]:
        """全文检索片段"""
        # 实现略...


# core/storage/redis.py

import redis.asyncio as aioredis
from typing import Optional, Any
import json

class RedisClient:
    """Redis客户端"""

    def __init__(self, host: str = "localhost", port: int = 6379, **kwargs):
        self.client = aioredis.from_url(
            f"redis://{host}:{port}",
            **kwargs
        )

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        value = await self.client.get(key)
        if value:
            return json.loads(value)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None
    ):
        """设置缓存"""
        await self.client.set(
            key,
            json.dumps(value),
            ex=expire
        )

    async def delete(self, key: str):
        """删除缓存"""
        await self.client.delete(key)

    async def close(self):
        """关闭连接"""
        await self.client.close()
```

#### 2.2.4 模块导入

所有存储相关的类都可以从 `dataflow.core.storage` 直接导入：

```python
from dataflow.core.storage import (
    # MySQL
    MySQLClient,
    get_db_session,

    # Elasticsearch Client
    ElasticsearchClient,
    ESConfig,
    get_es_client,
    close_es_client,

    # Redis
    RedisClient,
    get_redis_client,
    close_redis_client,

    # ES Documents
    EntityVectorDocument,
    EventVectorDocument,
    ArticleSectionDocument,

    # ES Repositories
    BaseRepository,
    EntityVectorRepository,
    EventVectorRepository,
    ArticleSectionRepository,
)
```

#### 2.2.5 使用示例

**1. 使用 Document 模型定义索引**

```python
from dataflow.core.storage.documents import EntityVectorDocument, EventVectorDocument

# 初始化索引（仅需执行一次）
from elasticsearch import AsyncElasticsearch

es_client = AsyncElasticsearch(["http://localhost:9200"])

# 创建索引
await EntityVectorDocument.init(using=es_client)
await EventVectorDocument.init(using=es_client)
```

**2. 使用 Repository 进行数据操作**

```python
from dataflow.core.storage import (
    ElasticsearchClient,
    EntityVectorRepository,
    EventVectorRepository
)

# 初始化客户端和Repository
es_client = await ElasticsearchClient.create(
    hosts=["http://localhost:9200"]
)
entity_repo = EntityVectorRepository(es_client.client)

# 索引实体向量
await entity_repo.index_entity(
    entity_id="person_001",
    source_config_id="source_123",
    entity_type="PERSON",
    name="张三",
    vector=[0.1, 0.2, ...],  # 1536维向量
    created_time="2024-01-01T00:00:00Z"
)

# 按名称搜索
results = await entity_repo.search_by_name(
    name="张三",
    source_config_id="source_123",
    size=10
)

# 向量相似度搜索
similar_entities = await entity_repo.search_similar(
    query_vector=[0.1, 0.2, ...],
    k=10,
    entity_type="PERSON"
)

# 获取信息源的所有实体
entities = await entity_repo.get_by_source(
    source_config_id="source_123",
    entity_type="PERSON"
)
```

**3. 批量索引文档**

```python
# 批量索引实体
documents = [
    {
        "_id": "person_001",
        "entity_id": "person_001",
        "source_config_id": "source_123",
        "type": "PERSON",
        "name": "张三",
        "vector": [0.1, 0.2, ...],
    },
    {
        "_id": "person_002",
        "entity_id": "person_002",
        "source_config_id": "source_123",
        "type": "PERSON",
        "name": "李四",
        "vector": [0.3, 0.4, ...],
    }
]

result = await entity_repo.bulk_index(
    index=entity_repo.INDEX_NAME,
    documents=documents
)
print(f"成功: {result['success']}, 失败: {result['failed']}")
```

**4. 组合查询示例**

```python
from elasticsearch_dsl import Search, Q

# 复杂组合查询：全文检索 + 过滤
s = Search(using=es_client.client, index="entity_vectors")

# 全文检索
s = s.query("match", name="张三")

# 添加过滤条件
s = s.filter("term", source_config_id="source_123")
s = s.filter("term", type="PERSON")

# 时间范围过滤
s = s.filter("range", created_time={"gte": "2024-01-01", "lte": "2024-12-31"})

# 执行查询
response = await s.execute()
results = [hit.to_dict() for hit in response]
```

**5. 事件向量高级查询示例**

```python
from dataflow.core.storage import EventVectorRepository
from datetime import datetime

event_repo = EventVectorRepository(es_client.client)

# 1. 全文检索事件
events = await event_repo.search_by_text(
    query="人工智能",
    source_config_id="source_123",
    size=10
)

# 2. 按时间范围查询
recent_events = await event_repo.search_by_time_range(
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 12, 31),
    source_config_id="source_123"
)

# 3. 按关联实体查询事件
related_events = await event_repo.search_by_entities(
    entity_ids=["person_001", "person_002"],
    source_config_id="source_123"
)

# 4. 标题向量相似搜索
similar_by_title = await event_repo.search_similar_by_title(
    query_vector=[0.1, 0.2, ...],
    k=10,
    category="科技"
)

# 5. 内容向量相似搜索
similar_by_content = await event_repo.search_similar_by_content(
    query_vector=[0.1, 0.2, ...],
    k=10,
    category="科技"
)
```

**6. 文章片段查询示例**

```python
from dataflow.core.storage import ArticleSectionRepository

section_repo = ArticleSectionRepository(es_client.client)

# 1. 获取文章的所有片段（按顺序）
sections = await section_repo.get_by_article(
    article_id="article_001",
    sort_by_rank=True
)

# 2. 全文检索片段
results = await section_repo.search_by_text(
    query="深度学习",
    source_config_id="source_123",
    size=10
)

# 3. 语义相似搜索
similar_sections = await section_repo.search_similar_by_content(
    query_vector=[0.1, 0.2, ...],
    k=10,
    section_type="content"
)
```

---

### 2.3 Prompt模块（core/prompt）

#### 2.3.1 模块职责

- 管理提示词模板
- 支持变量替换
- 支持多语言
- 版本管理

#### 2.3.2 接口设计

```python
# core/prompt/manager.py

from typing import Dict, Any, Optional
from pathlib import Path
import yaml

class PromptTemplate:
    """提示词模板"""

    def __init__(self, template: str, variables: Optional[List[str]] = None):
        self.template = template
        self.variables = variables or []

    def render(self, **kwargs) -> str:
        """
        渲染模板

        Args:
            **kwargs: 变量值

        Returns:
            渲染后的文本

        Example:
            >>> template = PromptTemplate(
            ...     "请为以下文章生成摘要:\n{content}",
            ...     variables=["content"]
            ... )
            >>> prompt = template.render(content="文章内容...")
        """
        # 检查必需变量
        missing = set(self.variables) - set(kwargs.keys())
        if missing:
            raise ValueError(f"缺少必需变量: {missing}")

        return self.template.format(**kwargs)


class PromptManager:
    """提示词管理器"""

    def __init__(self, prompts_dir: Path):
        self.prompts_dir = prompts_dir
        self.templates: Dict[str, PromptTemplate] = {}
        self.load_templates()

    def load_templates(self):
        """从YAML文件加载模板"""
        for yaml_file in self.prompts_dir.glob("*.yaml"):
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                for name, config in data.items():
                    self.templates[name] = PromptTemplate(
                        template=config["template"],
                        variables=config.get("variables", [])
                    )

    def get(self, name: str) -> PromptTemplate:
        """获取模板"""
        if name not in self.templates:
            raise KeyError(f"模板不存在: {name}")
        return self.templates[name]

    def render(self, name: str, **kwargs) -> str:
        """渲染模板"""
        template = self.get(name)
        return template.render(**kwargs)


# 示例YAML配置文件: prompts/extract.yaml
"""
article_summary:
  template: |
    你是一个专业的文章摘要生成助手。

    请为以下文章生成一个简洁的摘要（100-200字）：

    标题：{title}
    内容：{content}

    要求：
    1. 概括文章的核心内容
    2. 突出关键信息
    3. 语言简洁流畅
  variables:
    - title
    - content

event_extract:
  template: |
    你是一个专业的信息提取助手。

    请从以下文本中提取事项信息：

    {content}

    背景信息：{background}

    提取要求：
    1. 识别具体的事件、任务、问题
    2. 提取时间、地点、人物等实体
    3. 按照JSON格式输出
  variables:
    - content
    - background
"""
```

---

### 2.4 Utils工具模块（utils）

#### 2.4.1 模块职责

- 提供通用的工具函数和类
- 文本处理、时间处理、日志管理等
- Token 估算工具
- 跨模块可复用的基础功能

#### 2.4.2 目录结构

```
utils/
├── __init__.py
├── text.py              # 文本处理工具
├── time.py              # 时间处理工具
├── logger.py            # 日志管理
└── token_estimator.py   # Token估算工具
```

#### 2.4.3 TokenEstimator - Token估算器

`TokenEstimator` 是一个通用的 token 数量估算工具类，支持针对不同 LLM 模型的估算策略。

**模块位置**: [dataflow/utils/token_estimator.py](dataflow/utils/token_estimator.py)

##### 接口设计

```python
# utils/token_estimator.py

class TokenEstimator:
    """通用Token估算器"""

    def __init__(self, model_type: str = "generic"):
        """
        初始化Token估算器

        Args:
            model_type: 模型类型
                - "gpt": GPT系列模型（OpenAI）
                - "claude": Claude系列模型（Anthropic）
                - "llama": LLaMA系列模型
                - "generic": 通用估算（保守策略）
        """
        self.model_type = model_type

    def estimate_tokens(self, text: str) -> int:
        """
        估算文本的token数量

        采用基于字符统计的启发式估算方法：
        1. 统计中文字符、英文单词、特殊字符数量
        2. 根据模型类型应用不同的转换系数
        3. 返回估算的token总数

        Args:
            text: 文本内容

        Returns:
            估算的token数量（至少返回1，如果文本非空）

        Example:
            >>> estimator = TokenEstimator(model_type="gpt")
            >>> tokens = estimator.estimate_tokens("这是一段测试文本 with English words.")
            >>> print(f"估算token数: {tokens}")
        """
        # 实现见源码
```

##### 模型估算策略

不同模型类型使用不同的估算系数：

| 模型类型    | 中文字符系数    | 英文单词系数 | 特殊字符系数   |
| ----------- | --------------- | ------------ | -------------- |
| **gpt**     | 0.7 token/字符  | 1 token/词   | 0.5 token/字符 |
| **claude**  | 0.65 token/字符 | 1.1 token/词 | 0.5 token/字符 |
| **llama**   | 0.8 token/字符  | 1.3 token/词 | 0.5 token/字符 |
| **generic** | 0.8 token/字符  | 1 token/词   | 0.5 token/字符 |

> 注意：这是启发式估算，实际token数量取决于具体的tokenizer实现。生产环境建议使用 `tiktoken` 等精确的 tokenizer 库。

##### 使用场景

1. **文档切片 (Load模块)**
   - 在 `MarkdownParser` 中用于智能切片，确保每个片段不超过 token 限制

2. **上下文管理 (Extract模块)**
   - 估算 LLM 输入的 token 数量，避免超过上下文窗口限制
   - 决定是否需要对长文本进行分块处理

3. **成本预估**
   - 在调用 LLM API 之前，估算 token 消耗量用于成本控制

##### 使用示例

```python
from dataflow.utils import TokenEstimator

# 示例1: 基础使用
estimator = TokenEstimator(model_type="gpt")
text = "这是一篇关于人工智能的文章，包含了深度学习和自然语言处理的内容。"
tokens = estimator.estimate_tokens(text)
print(f"估算token数: {tokens}")


# 示例2: 在MarkdownParser中使用
from dataflow.utils import TokenEstimator

class MarkdownParser:
    def __init__(self, max_tokens: int = 1000, model_type: str = "generic"):
        self.max_tokens = max_tokens
        self.token_estimator = TokenEstimator(model_type)

    def should_split_section(self, content: str) -> bool:
        """判断章节是否需要切分"""
        estimated_tokens = self.token_estimator.estimate_tokens(content)
        return estimated_tokens > self.max_tokens


# 示例3: 批量估算
estimator = TokenEstimator(model_type="claude")
texts = [
    "短文本",
    "这是一段中等长度的文本内容，包含多个句子。",
    "这是一段很长的文本..." * 100
]

for i, text in enumerate(texts):
    tokens = estimator.estimate_tokens(text)
    print(f"文本{i+1}: {tokens} tokens")
```

##### 与 estimate_tokens 函数的区别

模块中还提供了一个简单的 `estimate_tokens` 函数（见 Extract 模块文档 line 1858），两者的区别：

| 特性         | TokenEstimator 类    | estimate_tokens 函数 |
| ------------ | -------------------- | -------------------- |
| **方式**     | 面向对象，可配置     | 函数式，简单快速     |
| **模型支持** | 4种预设策略          | 通用策略             |
| **可扩展性** | 易于扩展新模型       | 功能固定             |
| **适用场景** | 需要针对特定模型优化 | 快速估算             |

**推荐用法**：
- 如需针对特定 LLM 模型优化估算精度 → 使用 `TokenEstimator` 类
- 仅需快速粗略估算 → 使用 `estimate_tokens` 函数

---

## 3. 业务层模块

### 3.1 Agent模块（core/agent）

#### 3.1.1 模块职责

- 任务编排与执行
- 提示词注入
- 输入输出管理
- 任务评估

#### 3.1.2 接口设计

```python
# core/agent/base.py

from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from abc import ABC, abstractmethod

class AgentTask(BaseModel):
    """Agent任务"""
    task_id: str
    task_type: str
    input_data: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None

class AgentResult(BaseModel):
    """Agent执行结果"""
    task_id: str
    success: bool
    output_data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class BaseAgent(ABC):
    """Agent基类"""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_manager: PromptManager,
        system_prompt: Optional[str] = None
    ):
        self.llm = llm_client
        self.prompts = prompt_manager
        self.system_prompt = system_prompt or self.default_system_prompt()

    @abstractmethod
    def default_system_prompt(self) -> str:
        """默认系统提示词"""
        pass

    @abstractmethod
    async def execute(self, task: AgentTask) -> AgentResult:
        """执行任务"""
        pass

    async def _call_llm(
        self,
        user_prompt: str,
        response_schema: Optional[Dict[str, Any]] = None
    ) -> Any:
        """调用LLM"""
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]

        if response_schema:
            return await self.llm.chat_with_schema(
                messages=messages,
                response_schema=response_schema
            )
        else:
            response = await self.llm.chat(messages=messages)
            return response.content
```

---

## 4. 应用层模块

### 4.1 Load模块（modules/load）

#### 4.1.1 功能说明

- 读取各种格式的文档（Markdown, PDF, HTML, TXT）
- 生成文章摘要、标签、分类
- 内容切块（按标题、长度）
- 存储到数据库

#### 4.1.2 接口设计

```python
# modules/load/loader.py

from typing import List, Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel

class LoadConfig(BaseModel):
    """加载配置"""
    type: str  # "path" | "url" | "text"
    origin: List[str]  # 文档路径列表或URL列表
    filter: bool = False  # 是否智能过滤
    background: str = ""  # 背景信息
    description: str = ""  # 任务描述
    chunk_size: int = 1000  # 切块大小
    chunk_overlap: int = 200  # 切块重叠

class Article(BaseModel):
    """文章模型"""
    id: str
    source_config_id: str
    title: str
    content: str
    summary: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    headings: Optional[List[str]] = None

class ArticleSection(BaseModel):
    """文章片段模型"""
    id: str
    article_id: str
    rank: int
    type: str
    heading: Optional[str] = None
    content: str
    length: int

class DocumentLoader:
    """文档加载器"""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_manager: PromptManager,
        storage: MySQLClient
    ):
        self.llm = llm_client
        self.prompts = prompt_manager
        self.storage = storage

    async def load(
        self,
        config: LoadConfig,
        source_config_id: str
    ) -> List[Article]:
        """
        加载文档

        Args:
            config: 加载配置
            source_config_id: 信息源ID

        Returns:
            文章列表
        """
        articles = []

        for source in config.origin:
            # 1. 读取文档
            content = await self._read_document(source, config.type)

            # 2. 生成元数据（摘要、标签、分类）
            metadata = await self._generate_metadata(
                content=content,
                background=config.background
            )

            # 3. 提取标题
            headings = self._extract_headings(content)

            # 4. 创建文章记录
            article = Article(
                id=str(uuid.uuid4()),
                source_config_id=source_config_id,
                title=metadata["title"],
                content=content,
                summary=metadata["summary"],
                category=metadata["category"],
                tags=metadata["tags"],
                headings=headings
            )

            # 5. 切块
            sections = await self._chunk_content(
                article_id=article.id,
                content=content,
                headings=headings,
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap
            )

            # 6. 存储
            await self._save_article(article, sections)

            articles.append(article)

        return articles

    async def _read_document(self, source: str, source_type: str) -> str:
        """读取文档"""
        if source_type == "path":
            return await self._read_file(Path(source))
        elif source_type == "url":
            return await self._fetch_url(source)
        else:  # text
            return source

    async def _generate_metadata(
        self,
        content: str,
        background: str
    ) -> Dict[str, Any]:
        """生成文章元数据（LLM）"""
        prompt = self.prompts.render(
            "article_metadata",
            content=content[:2000],  # 限制长度
            background=background
        )

        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "category": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["title", "summary", "category", "tags"]
        }

        return await self.llm.chat_with_schema(
            messages=[LLMMessage(role="user", content=prompt)],
            response_schema=schema
        )

    def _extract_headings(self, content: str) -> List[str]:
        """提取Markdown标题"""
        import re
        pattern = r'^(#{1,6})\s+(.+)$'
        headings = []
        for line in content.split('\n'):
            match = re.match(pattern, line.strip())
            if match:
                headings.append(line.strip())
        return headings

    async def _chunk_content(
        self,
        article_id: str,
        content: str,
        headings: List[str],
        chunk_size: int,
        chunk_overlap: int
    ) -> List[ArticleSection]:
        """
        切块策略：
        1. 优先按标题切分
        2. 超过chunk_size的再按长度切分
        """
        sections = []
        # 实现切块逻辑...
        return sections

    async def _save_article(
        self,
        article: Article,
        sections: List[ArticleSection]
    ):
        """保存到数据库"""
        async with self.storage.session() as session:
            # 保存article
            # 保存sections
            pass
```

#### 4.1.3 使用示例

```python
config = LoadConfig(
    type="path",
    origin=["./docs/article1.md", "./docs/article2.md"],
    filter=False,
    background="这是技术文档",
    chunk_size=1000
)

loader = DocumentLoader(llm, prompts, mysql)
articles = await loader.load(config, source_config_id="user-001")

print(f"成功加载 {len(articles)} 篇文章")
```

---

### 4.2 Extract模块（modules/extract）

#### 4.2.1 功能说明

- 从文章片段中提取事项
- 识别实体（9种类型）
- 生成向量
- 存储到数据库和Elasticsearch

#### 4.2.2 接口设计

```python
# modules/extract/extractor.py

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class EntityExtractionStrategy(BaseModel):
    """实体提取策略配置"""

    # 方法控制
    use_llm: bool = True           # 是否使用LLM提取（TOPIC, ACTION等语义实体）
    use_ner: bool = True           # 是否使用NER提取（PERSON, LOCATION等基础实体）
    use_rule: bool = True          # 是否使用规则提取（标题、时间格式等）

    # 同义词扩展
    expand_synonyms: bool = True   # 是否扩展同义词
    synonym_method: str = "hybrid" # "dict" | "embedding" | "hybrid"
    synonym_threshold: float = 0.85 # 向量相似度阈值

    # 实体质量控制
    min_entity_length: int = 2     # 最短实体长度
    max_entity_length: int = 50    # 最长实体长度
    min_confidence: float = 0.6    # LLM提取的最小置信度

    # 去重与标准化
    normalize_entities: bool = True # 是否标准化实体名称
    deduplicate: bool = True       # 是否去重


class CustomEntityType(BaseModel):
    """自定义实体类型定义"""

    type: str = Field(..., description="类型标识符（如：project_stage）")
    name: str = Field(..., description="类型名称（如：项目阶段）")
    description: str = Field(..., description="类型描述，用于指导LLM提取")
    dimension: str = "CUSTOM"      # DEFAULT | CUSTOM
    weight: float = 1.0            # 默认权重（0.0-9.99）

    # LLM提取配置
    extraction_prompt: Optional[str] = None  # 自定义提取提示词模板
    extraction_examples: Optional[List[Dict[str, str]]] = None  # Few-shot示例

    # 验证配置
    validation_rule: Optional[Dict[str, Any]] = None  # 验证规则（正则、枚举等）
    metadata_schema: Optional[Dict[str, Any]] = None  # 元数据JSON Schema


class LLMContextConfig(BaseModel):
    """LLM上下文配置"""

    # Token限制
    max_tokens_per_call: int = 6000     # 单次LLM调用最大输入token（留余量给输出）
    max_output_tokens: int = 2000       # 最大输出token
    estimate_tokens_method: str = "tiktoken"  # "tiktoken" | "simple"

    # 分块策略（当section超长时）
    chunk_strategy: str = "sliding_window"  # "sliding_window" | "paragraph" | "sentence"
    chunk_size: int = 4000              # 分块大小（tokens）
    chunk_overlap: int = 500            # 分块重叠（tokens）

    # 上下文控制
    include_article_context: bool = True  # 是否包含文章标题、摘要作为上下文
    include_adjacent_sections: bool = False  # 是否包含相邻section作为上下文
    max_context_tokens: int = 1000      # 上下文最大token数


class BatchProcessingConfig(BaseModel):
    """批处理配置"""

    parallel: bool = True              # 是否并发处理
    max_concurrent: int = 10           # 最大并发数
    batch_size: int = 5                # 批量大小（多个section合并调用LLM）
    retry_on_failure: bool = True      # 失败时是否重试
    max_retries: int = 3               # 最大重试次数


class ExtractConfig(BaseModel):
    """提取配置（增强版）"""

    # 基础配置
    article_ids: List[str]             # 文章ID列表
    source_config_id: str                       # 信息源ID
    background: str = ""               # 背景信息

    # 过滤模式
    filter_mode: str = "all"           # "all" | "intelligent" | "rule_based"
    min_quality_score: float = 0.6     # 事项最小质量分数

    # 自定义实体类型
    custom_entity_types: List[CustomEntityType] = []

    # 策略配置
    entity_strategy: EntityExtractionStrategy = Field(default_factory=EntityExtractionStrategy)
    llm_context: LLMContextConfig = Field(default_factory=LLMContextConfig)
    batch_processing: BatchProcessingConfig = Field(default_factory=BatchProcessingConfig)

    # 输出控制
    save_to_db: bool = True            # 是否保存到数据库
    save_to_es: bool = True            # 是否索引到ES
    return_vectors: bool = False       # 是否返回向量（内存占用大）

class SourceEvent(BaseModel):
    """事项模型"""
    id: str
    source_config_id: str
    type: str
    title: str
    summary: str
    content: str
    keywords: List[str]
    category: str
    priority: str
    status: str
    entities: List[str]  # 实体ID列表
    tags: List[str]

class Entity(BaseModel):
    """实体模型"""
    id: str
    source_config_id: str
    type: str  # TITLE, SUMMARY, CONTENT, TIME, LOCATION, PERSON, ORGANIZATION, TOPIC, ACTION
    name: str
    normalized_name: str
    description: Optional[str] = None
    synonyms: List[str] = []
    weight: float = 1.0

class EventExtractor:
    """事项提取器"""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_manager: PromptManager,
        mysql_client: MySQLClient,
        es_client: ElasticsearchClient
    ):
        self.llm = llm_client
        self.prompts = prompt_manager
        self.mysql = mysql_client
        self.es = es_client

    async def extract(
        self,
        config: ExtractConfig,
        source_config_id: str
    ) -> List[SourceEvent]:
        """
        提取事项

        Args:
            config: 提取配置
            source_config_id: 信息源ID

        Returns:
            事项列表
        """
        events = []

        # 1. 获取文章片段
        sections = await self._load_sections(config.article_ids)

        # 2. 并发提取（可选）
        if config.parallel:
            tasks = [
                self._extract_from_section(section, config, source_config_id)
                for section in sections
            ]
            results = await asyncio.gather(*tasks)
            events = [e for result in results for e in result]
        else:
            for section in sections:
                section_events = await self._extract_from_section(
                    section, config, source_config_id
                )
                events.extend(section_events)

        # 3. 智能过滤（可选）
        if config.filter_mode == "intelligent":
            events = await self._intelligent_filter(events)

        return events

    async def _extract_from_section(
        self,
        section: ArticleSection,
        config: ExtractConfig,
        source_config_id: str
    ) -> List[SourceEvent]:
        """从单个片段提取事项"""

        # 1. 调用LLM提取事项
        prompt = self.prompts.render(
            "event_extract",
            content=section.content,
            background=config.background,
            heading=section.heading or ""
        )

        schema = {
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "content": {"type": "string"},
                            "keywords": {"type": "array"},
                            "category": {"type": "string"},
                            "priority": {"type": "string"},
                            "status": {"type": "string"},
                            "entities": {
                                "type": "object",
                                "properties": {
                                    "PERSON": {"type": "array"},
                                    "ORGANIZATION": {"type": "array"},
                                    "LOCATION": {"type": "array"},
                                    "TOPIC": {"type": "array"},
                                    "ACTION": {"type": "array"},
                                    "TIME": {"type": "array"}
                                }
                            }
                        }
                    }
                }
            }
        }

        result = await self.llm.chat_with_schema(
            messages=[LLMMessage(role="user", content=prompt)],
            response_schema=schema
        )

        # 2. 处理实体
        events = []
        for event_data in result["events"]:
            # 创建/查找实体
            entity_ids = await self._process_entities(
                event_data["entities"],
                source_config_id
            )

            # 创建事项
            event = SourceEvent(
                id=str(uuid.uuid4()),
                source_config_id=source_config_id,
                type="ARTICLE",
                title=event_data["title"],
                summary=event_data["summary"],
                content=event_data["content"],
                keywords=event_data["keywords"],
                category=event_data["category"],
                priority=event_data["priority"],
                status=event_data["status"],
                entities=entity_ids,
                tags=[]
            )

            events.append(event)

        # 3. 存储
        await self._save_events(events)

        return events

    async def _process_entities(
        self,
        entities_data: Dict[str, List[str]],
        source_config_id: str
    ) -> List[str]:
        """
        处理实体：
        1. 标准化实体名称
        2. 查找已存在的实体
        3. 创建新实体
        4. 生成向量并索引到ES
        """
        entity_ids = []

        for entity_type, names in entities_data.items():
            for name in names:
                # 标准化
                normalized = self._normalize_entity_name(name)

                # 查找已存在
                entity = await self._find_entity(
                    source_config_id, entity_type, normalized
                )

                if not entity:
                    # 创建新实体
                    entity = Entity(
                        id=str(uuid.uuid4()),
                        source_config_id=source_config_id,
                        type=entity_type,
                        name=name,
                        normalized_name=normalized,
                        weight=self._get_entity_weight(entity_type)
                    )

                    # 生成向量
                    vector = await self._generate_vector(name)

                    # 存储
                    await self._save_entity(entity, vector)

                entity_ids.append(entity.id)

        return entity_ids

    def _normalize_entity_name(self, name: str) -> str:
        """标准化实体名称"""
        # 去除空格、转小写、去除特殊符号等
        return name.strip().lower()

    def _get_entity_weight(self, entity_type: str) -> float:
        """获取实体类型权重"""
        weights = {
            "TITLE": 1.0,
            "SUMMARY": 1.0,
            "CONTENT": 1.0,
            "TIME": 0.9,
            "LOCATION": 1.0,
            "PERSON": 1.1,
            "ORGANIZATION": 1.2,
            "TOPIC": 1.5,
            "ACTION": 1.2
        }
        return weights.get(entity_type, 1.0)


# Token估算与分块辅助函数

def estimate_tokens(text: str, method: str = "tiktoken") -> int:
    """
    估算文本的token数量

    Args:
        text: 文本内容
        method: 估算方法 ("tiktoken" | "simple")

    Returns:
        token数量
    """
    if method == "tiktoken":
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except ImportError:
            # Fallback to simple method
            pass

    # Simple method: 1 token ≈ 4 characters (for English)
    # For Chinese: 1 token ≈ 1.5 characters
    chinese_char_count = len([c for c in text if ord(c) > 0x4e00 and ord(c) < 0x9fff])
    english_char_count = len(text) - chinese_char_count

    return int(chinese_char_count / 1.5 + english_char_count / 4)


def split_content_by_tokens(
    content: str,
    chunk_size: int,
    chunk_overlap: int,
    strategy: str = "sliding_window"
) -> List[str]:
    """
    按token数量分块

    Args:
        content: 内容文本
        chunk_size: 分块大小（tokens）
        chunk_overlap: 分块重叠（tokens）
        strategy: 分块策略
            - "sliding_window": 滑动窗口（固定chunk_size）
            - "paragraph": 按段落分块（不超过chunk_size）
            - "sentence": 按句子分块（不超过chunk_size）

    Returns:
        分块后的文本列表
    """
    if strategy == "sliding_window":
        return _sliding_window_split(content, chunk_size, chunk_overlap)
    elif strategy == "paragraph":
        return _paragraph_split(content, chunk_size, chunk_overlap)
    elif strategy == "sentence":
        return _sentence_split(content, chunk_size, chunk_overlap)
    else:
        raise ValueError(f"不支持的分块策略: {strategy}")


def _sliding_window_split(
    content: str,
    chunk_size: int,
    chunk_overlap: int
) -> List[str]:
    """滑动窗口分块"""
    chunks = []

    # 简单按字符分块（粗略估算）
    # 中文: 1.5字符/token, 英文: 4字符/token, 取平均2.5
    char_per_token = 2.5
    chunk_chars = int(chunk_size * char_per_token)
    overlap_chars = int(chunk_overlap * char_per_token)

    start = 0
    while start < len(content):
        end = start + chunk_chars
        chunk = content[start:end]
        chunks.append(chunk)

        if end >= len(content):
            break

        start = end - overlap_chars

    return chunks


def _paragraph_split(
    content: str,
    chunk_size: int,
    chunk_overlap: int
) -> List[str]:
    """按段落分块"""
    paragraphs = content.split('\n\n')
    chunks = []
    current_chunk = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        if current_tokens + para_tokens <= chunk_size:
            current_chunk.append(para)
            current_tokens += para_tokens
        else:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_tokens = para_tokens

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


def _sentence_split(
    content: str,
    chunk_size: int,
    chunk_overlap: int
) -> List[str]:
    """按句子分块"""
    import re
    # 简单句子分割（中英文）
    sentences = re.split(r'([。！？.!?])', content)
    # 重新组合句子和标点
    sentences = [''.join(sentences[i:i+2]) for i in range(0, len(sentences)-1, 2)]

    chunks = []
    current_chunk = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = estimate_tokens(sentence)

        if current_tokens + sentence_tokens <= chunk_size:
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
        else:
            if current_chunk:
                chunks.append(''.join(current_chunk))
            current_chunk = [sentence]
            current_tokens = sentence_tokens

    if current_chunk:
        chunks.append(''.join(current_chunk))

    return chunks


async def extract_with_context_limit(
    section: ArticleSection,
    article: Article,
    config: ExtractConfig,
    extractor: EventExtractor
) -> List[SourceEvent]:
    """
    处理LLM上下文限制的提取流程

    流程：
    1. 估算token数量
    2. 如果超限，按策略分块
    3. 分别调用LLM提取
    4. 合并去重

    Args:
        section: 文章片段
        article: 文章信息
        config: 提取配置
        extractor: 提取器实例

    Returns:
        事项列表
    """
    # 1. 构建上下文并估算token
    context = _build_context(section, article, config)
    context_tokens = estimate_tokens(
        context,
        method=config.llm_context.estimate_tokens_method
    )
    content_tokens = estimate_tokens(
        section.content,
        method=config.llm_context.estimate_tokens_method
    )
    total_tokens = context_tokens + content_tokens

    # 2. 判断是否需要分块
    if total_tokens <= config.llm_context.max_tokens_per_call:
        # 直接提取
        return await extractor._extract_from_section(
            section, config, config.source_config_id
        )

    # 3. 需要分块处理
    chunks = split_content_by_tokens(
        content=section.content,
        chunk_size=config.llm_context.chunk_size,
        chunk_overlap=config.llm_context.chunk_overlap,
        strategy=config.llm_context.chunk_strategy
    )

    # 4. 并发提取各分块
    all_events = []
    for i, chunk in enumerate(chunks):
        chunk_section = ArticleSection(
            id=f"{section.id}_chunk_{i}",
            article_id=section.article_id,
            rank=section.rank,
            heading=section.heading,
            content=chunk,
            type=section.type,
            length=len(chunk)
        )

        events = await extractor._extract_from_section(
            chunk_section, config, config.source_config_id
        )
        all_events.extend(events)

    # 5. 去重（同一事项可能在多个chunk中被识别）
    deduplicated_events = _deduplicate_events(
        all_events,
        similarity_threshold=0.9
    )

    return deduplicated_events


def _build_context(
    section: ArticleSection,
    article: Article,
    config: ExtractConfig
) -> str:
    """
    构建上下文

    包括：
    - 文章标题、摘要
    - 当前章节标题
    - 用户提供的背景信息
    """
    context_parts = []

    if config.llm_context.include_article_context:
        context_parts.append(f"文章：{article.title}")
        if article.summary:
            context_parts.append(f"摘要：{article.summary}")

    if section.heading:
        context_parts.append(f"章节：{section.heading}")

    if config.background:
        context_parts.append(f"背景：{config.background}")

    return " | ".join(context_parts)


def _deduplicate_events(
    events: List[SourceEvent],
    similarity_threshold: float = 0.9
) -> List[SourceEvent]:
    """
    去重事项

    使用标题和内容的文本相似度进行去重

    Args:
        events: 事项列表
        similarity_threshold: 相似度阈值（0-1）

    Returns:
        去重后的事项列表
    """
    if len(events) <= 1:
        return events

    # 简单实现：基于标题完全匹配去重
    # 生产环境应使用更复杂的相似度算法（编辑距离、向量相似度等）
    seen_titles = set()
    deduplicated = []

    for event in events:
        normalized_title = event.title.strip().lower()
        if normalized_title not in seen_titles:
            seen_titles.add(normalized_title)
            deduplicated.append(event)

    return deduplicated
```

### 4.3 Search模块（modules/search）

**完整设计见 [ALGORITHM_DESIGN.md](./ALGORITHM_DESIGN.md)**

简要接口：

```python
# modules/search/searcher.py

class SearchConfig(BaseModel):
    """检索配置"""
    query: str  # 查询文本
    source_config_id: str
    breadth: int = 2  # 横向扩展层数
    depth: int = 3  # 纵向扩展跳数
    threshold: float = 0.5  # 相关度阈值
    top_k: int = 10  # 返回数量

class SearchResult(BaseModel):
    """检索结果"""
    events: List[SourceEvent]
    scores: Dict[str, float]  # event_id -> score
    metadata: Dict[str, Any]

class EventSearcher:
    """事项检索器"""

    async def search(self, config: SearchConfig) -> SearchResult:
        """执行检索"""
        pass
```

---

## 5. 数据模型

完整的Pydantic模型定义：

```python
# models/source.py
# models/article.py
# models/event.py
# models/entity.py
```

---

## 6. 错误处理

```python
# exceptions/errors.py

class DataFlowError(Exception):
    """基础异常"""
    pass

class LLMError(DataFlowError):
    """LLM调用异常"""
    pass

class StorageError(DataFlowError):
    """存储异常"""
    pass

class ValidationError(DataFlowError):
    """数据验证异常"""
    pass
```

---

## 下一步

- 阅读 [核心算法设计文档](./algorithm.md)
- 阅读 [API接口文档](./document.md)
