# DataFlow 开发指南

**数据流智能引擎 - 开发指南**

*by Zleap Team（智跃团队）*

## 目录

- [1. 环境搭建](#1-环境搭建)
- [2. 项目结构](#2-项目结构)
- [3. 开发规范](#3-开发规范)
- [4. 测试指南](#4-测试指南)
- [5. 贡献指南](#5-贡献指南)

---

## 1. 环境搭建

### 1.1 系统要求

- **操作系统**: Linux / macOS / Windows (WSL2)
- **Python**: 3.11+
- **MySQL**: 8.0+
- **Elasticsearch**: 8.0+
- **Redis**: 7.0+
- **Docker**: 20.10+ (可选)

### 1.2 安装 UV

UV 是推荐的 Python 包管理工具：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 验证安装
uv --version
```

### 1.3 克隆项目

```bash
git clone https://github.com/zleap-team/dataflow.git
cd dataflow
```

### 1.4 创建虚拟环境

```bash
# 使用 UV 创建虚拟环境
uv venv

# 激活虚拟环境
# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 1.5 安装依赖

```bash
# 安装开发依赖
uv pip install -e ".[dev]"

# 或者使用 requirements.txt
uv pip install -r requirements-dev.txt
```

### 1.6 配置环境变量

创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
# 数据库配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=dataflow

# Elasticsearch配置
ES_HOSTS=http://localhost:9200
ES_USER=elastic
ES_PASSWORD=your_password

# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# LLM配置
LLM_PROVIDER=openai  # openai | anthropic | local
LLM_API_KEY=sk-xxx
LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507
LLM_BASE_URL=  # 可选，自定义API端点

# Embedding配置
EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_MODEL_NAME=Qwen/Qwen3-Embedding-0.6B

# 应用配置
DEBUG=true
LOG_LEVEL=INFO
```

### 1.7 启动依赖服务

#### 方式1: Docker Compose（推荐）

```bash
docker-compose up -d
```

`docker-compose.yml`:

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root_password
      MYSQL_DATABASE: dataflow
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql

  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
    volumes:
      - es_data:/usr/share/elasticsearch/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  mysql_data:
  es_data:
  redis_data:
```

#### 方式2: 手动安装

参考各服务的官方文档安装。

### 1.8 初始化数据库

```bash
# 执行数据库迁移
python scripts/init_database.py

# 或使用Alembic（如果使用）
alembic upgrade head
```

### 1.9 创建Elasticsearch索引

```bash
python scripts/init_elasticsearch.py
```

### 1.10 验证环境

```bash
# 运行测试
pytest tests/test_setup.py

# 启动开发服务器（如果有API）
uvicorn dataflow.api.main:app --reload
```

---

## 2. 项目结构

```
dataflow/
├── dataflow/                # 主代码目录
│   ├── __init__.py
│   ├── core/                 # 核心模块
│   │   ├── __init__.py
│   │   ├── ai/               # AI模块
│   │   │   ├── __init__.py
│   │   │   ├── llm.py       # LLM客户端
│   │   │   ├── embedding.py # Embedding
│   │   │   └── providers/   # 不同提供商实现
│   │   ├── agent/            # Agent模块
│   │   │   ├── __init__.py
│   │   │   └── base.py
│   │   ├── storage/          # 存储模块
│   │   │   ├── __init__.py
│   │   │   ├── mysql.py
│   │   │   ├── elasticsearch.py
│   │   │   └── redis.py
│   │   ├── prompt/           # 提示词模块
│   │   │   ├── __init__.py
│   │   │   └── manager.py
│   │   └── config/           # 配置模块
│   │       ├── __init__.py
│   │       └── settings.py
│   ├── modules/              # 应用模块
│   │   ├── __init__.py
│   │   ├── load/             # 加载模块
│   │   │   ├── __init__.py
│   │   │   └── loader.py
│   │   ├── extract/          # 提取模块
│   │   │   ├── __init__.py
│   │   │   └── extractor.py
│   │   ├── search/           # 检索模块
│   │   │   ├── __init__.py
│   │   │   └── searcher.py
│   │   ├── report/           # 报告模块
│   │   │   ├── __init__.py
│   │   │   └── generator.py
│   │   └── chat/             # 问答模块
│   │       ├── __init__.py
│   │       └── chatter.py
│   ├── models/               # 数据模型
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── source.py
│   │   ├── article.py
│   │   ├── event.py
│   │   └── entity.py
│   ├── utils/                # 工具函数
│   │   ├── __init__.py
│   │   ├── text.py
│   │   ├── time.py
│   │   └── logger.py
│   ├── exceptions/           # 异常定义
│   │   ├── __init__.py
│   │   └── errors.py
│   └── api/                  # API层（可选）
│       ├── __init__.py
│       ├── main.py
│       └── routes/
├── tests/                    # 测试目录
│   ├── __init__.py
│   ├── conftest.py          # Pytest配置
│   ├── unit/                # 单元测试
│   ├── integration/         # 集成测试
│   └── fixtures/            # 测试数据
├── scripts/                  # 脚本目录
│   ├── init_database.py
│   └── init_elasticsearch.py
├── prompts/                  # 提示词文件
│   ├── load.yaml
│   ├── extract.yaml
│   ├── search.yaml
│   └── report.yaml
├── docs/                     # 文档目录
│   ├── architecture.md
│   ├── database.md
│   └── ...
├── .env.example             # 环境变量示例
├── .gitignore
├── pyproject.toml           # 项目配置（UV/Poetry）
├── requirements.txt
├── requirements-dev.txt
├── docker-compose.yml
├── Dockerfile
├── README.md
└── LICENSE
```

---

## 3. 开发规范

### 3.1 代码风格

使用 **Black** + **Ruff** 进行代码格式化和检查：

```bash
# 格式化代码
black dataflow/

# 代码检查
ruff check dataflow/

# 自动修复
ruff check --fix dataflow/
```

**配置** (`pyproject.toml`):

```toml
[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
select = [
    "E",  # pycodestyle errors
    "W",  # pycodestyle warnings
    "F",  # pyflakes
    "I",  # isort
    "B",  # flake8-bugbear
    "C4", # flake8-comprehensions
]
ignore = ["E501"]  # line too long (由Black处理)
```

### 3.2 类型注解

使用 **mypy** 进行类型检查：

```bash
mypy dataflow/
```

**示例**：

```python
from typing import List, Dict, Any, Optional

async def load_articles(
    paths: List[str],
    source_config_id: str,
    config: Optional[Dict[str, Any]] = None
) -> List[Article]:
    """加载文章"""
    ...
```

### 3.3 文档字符串

使用 **Google风格** 文档字符串：

```python
def calculate_relevance(
    source_event: SourceEvent,
    candidate_event: SourceEvent,
    entity_weights: Dict[str, float]
) -> float:
    """
    计算两个事项之间的相关度

    Args:
        source_event: 源事项
        candidate_event: 候选事项
        entity_weights: 实体类型权重配置

    Returns:
        相关度分数（0-1）

    Raises:
        ValueError: 如果事项不包含任何实体

    Example:
        >>> score = calculate_relevance(event_a, event_b, ENTITY_TYPE_WEIGHTS)
        >>> print(f"相关度: {score:.2f}")
    """
    ...
```

### 3.4 命名规范

| 类型      | 规范        | 示例                  |
| --------- | ----------- | --------------------- |
| 模块      | 小写+下划线 | `event_extractor.py`  |
| 类        | 大驼峰      | `EventExtractor`      |
| 函数/方法 | 小写+下划线 | `extract_events()`    |
| 常量      | 大写+下划线 | `ENTITY_TYPE_WEIGHTS` |
| 私有方法  | 前缀`_`     | `_process_entities()` |

### 3.5 异常处理

自定义异常并合理捕获：

```python
# exceptions/errors.py
class DataFlowError(Exception):
    """基础异常"""
    pass

class LLMError(DataFlowError):
    """LLM调用异常"""
    pass

# 使用
try:
    result = await llm.chat(messages)
except LLMError as e:
    logger.error(f"LLM调用失败: {e}")
    # 重试或fallback逻辑
```

### 3.6 日志规范

使用结构化日志：

```python
import logging

logger = logging.getLogger(__name__)

# 不同级别
logger.debug("调试信息")
logger.info("一般信息")
logger.warning("警告信息")
logger.error("错误信息", exc_info=True)

# 结构化日志（使用structlog）
logger.info(
    "event_extracted",
    event_id=event.id,
    source_config_id=source_config_id,
    entity_count=len(entities)
)
```

---

## 4. 测试指南

### 4.1 测试框架

使用 **Pytest** + **pytest-asyncio**：

```bash
# 安装测试依赖
uv pip install pytest pytest-asyncio pytest-cov

# 运行所有测试
pytest

# 运行指定测试
pytest tests/unit/test_extractor.py

# 查看覆盖率
pytest --cov=dataflow --cov-report=html
```

### 4.2 测试结构

```python
# tests/unit/test_extractor.py

import pytest
from dataflow.modules.extract import EventExtractor

@pytest.fixture
async def extractor(mysql_client, llm_client):
    """测试用提取器"""
    return EventExtractor(llm_client, mysql_client)

@pytest.mark.asyncio
async def test_extract_events_basic(extractor):
    """测试基础事项提取"""
    section = ArticleSection(
        id="section-001",
        content="302.ai团队在6月1日部署了大模型服务"
    )

    events = await extractor.extract_from_section(section)

    assert len(events) > 0
    assert "302.ai" in events[0].content
    assert events[0].entities["ORGANIZATION"] == ["302.ai"]

@pytest.mark.asyncio
async def test_extract_events_with_llm_error(extractor, mocker):
    """测试LLM错误处理"""
    # Mock LLM客户端抛出异常
    mocker.patch.object(
        extractor.llm,
        'chat_with_schema',
        side_effect=LLMError("API调用失败")
    )

    with pytest.raises(LLMError):
        await extractor.extract_from_section(section)
```

### 4.3 Fixture配置

```python
# tests/conftest.py

import pytest
from dataflow.core.storage import MySQLClient
from dataflow.core.ai import LLMClient

@pytest.fixture(scope="session")
async def mysql_client():
    """测试数据库客户端"""
    client = MySQLClient("mysql://test:test@localhost/test_db")
    yield client
    await client.close()

@pytest.fixture
async def llm_client():
    """测试LLM客户端（Mock）"""
    from unittest.mock import AsyncMock
    client = AsyncMock(spec=LLMClient)
    client.chat_with_schema.return_value = {
        "events": [{
            "title": "测试事项",
            "summary": "测试摘要",
            ...
        }]
    }
    return client
```

### 4.4 集成测试

```python
# tests/integration/test_full_pipeline.py

@pytest.mark.asyncio
async def test_full_pipeline(client):
    """测试完整流程：加载 → 提取 → 检索"""

    # 1. 加载文档
    articles = await client.load(LoadConfig(
        type="text",
        origin=["测试文章内容..."]
    ))

    # 2. 提取事项
    events = await client.extract(ExtractConfig(
        article_ids=[a.id for a in articles]
    ))

    # 3. 检索
    result = await client.search(SearchConfig(
        query="测试查询",
        source_config_id="test-source"
    ))

    assert len(result.events) > 0
```

### 4.5 测试覆盖率目标

- **单元测试覆盖率**: > 80%
- **集成测试**: 覆盖主要流程
- **核心算法**: 100%覆盖

---

## 5. 贡献指南

### 5.1 开发流程

1. **Fork项目并克隆**

```bash
git clone https://github.com/your-username/dataflow.git
cd dataflow
```

2. **创建功能分支**

```bash
git checkout -b feature/your-feature-name
```

3. **开发功能并编写测试**

4. **运行测试和代码检查**

```bash
# 格式化代码
black dataflow/
ruff check --fix dataflow/

# 类型检查
mypy dataflow/

# 运行测试
pytest --cov=dataflow
```

5. **提交代码**

```bash
git add .
git commit -m "feat: 添加xxx功能"
```

**Commit消息规范**（遵循 [Conventional Commits](https://www.conventionalcommits.org/)):

- `feat:` 新功能
- `fix:` 修复bug
- `docs:` 文档更新
- `style:` 代码格式（不影响功能）
- `refactor:` 重构
- `test:` 测试相关
- `chore:` 构建/工具链相关

6. **推送并创建Pull Request**

```bash
git push origin feature/your-feature-name
```

### 5.2 Code Review要点

- 代码符合规范（Black + Ruff）
- 有完整的测试覆盖
- 有清晰的文档字符串
- 无明显性能问题
- 异常处理合理

### 5.3 Pre-commit钩子

安装pre-commit：

```bash
uv pip install pre-commit
pre-commit install
```

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.12.0
    hooks:
      - id: black

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.1
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

---

## 6. 常见问题

### 6.1 MySQL连接失败

**问题**: `Can't connect to MySQL server`

**解决**:
```bash
# 检查MySQL是否运行
docker ps | grep mysql

# 检查端口
netstat -an | grep 3306

# 检查.env配置
cat .env | grep MYSQL
```

### 6.2 Elasticsearch索引错误

**问题**: `index_not_found_exception`

**解决**:
```bash
# 重新初始化索引
python scripts/init_elasticsearch.py
```

### 6.3 LLM调用超时

**问题**: `asyncio.TimeoutError`

**解决**:
```python
# 增加超时时间
client = create_llm_client(
    provider="openai",
    model="sophnet/Qwen3-30B-A3B-Thinking-2507",
    timeout=60  # 增加到60秒
)
```

---

## 7. 下一步

- 阅读 [部署指南](./deployment.md)
- 查看 [API文档](./document.md)
