# DataFlow

**基于SQL-Rag理论实现的数据流智能引擎 - AI驱动的数据处理与聚合检索新范式**

*by Zleap Team（智跃团队）*

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[English](README_EN.md) | 简体中文

---

## 🌟 项目简介

**SQL-RAG** 是以关系型数据库为主要检索方式的聚合检索范式，区别于**GraphRAG**的实体图谱关系关联，Sql-Rag基础数据本身是无状态的，在检索时通过线索匹配模拟神经突触算法进行横行纵向计算召回数据，**DataFlow** 是一个基于**SQL-RAG**的 AI 的数据流索引、数据处理与聚合检索引擎，通过创新的动态实体关联技术，将非结构化数据转化为可检索的结构化事项。

### 💡 核心优势

通过 **SQL + Vector + LLM** 的混合架构，DataFlow 实现了：

- ✅ 无需维护复杂知识图谱
- ✅ 动态计算实体间关联关系
- ✅ 多维度智能匹配与评分
- ✅ 支持多跳深度检索

### 🚀 核心创新

#### 1. 事项为中心（Event-Centric）

将非结构化数据解构为独立、可索引的事项单元，每个事项包含完整的上下文信息。

#### 2. 动态实体关联

告别传统知识图谱的复杂维护，在检索时动态计算实体间的关联关系，降低数据维护成本。

#### 3. 灵活的实体维度（默认 + 自定义）

**默认实体维度**：

- **time** - 时间 `<When>` (权重0.9, 阈值0.900)
  时间节点或时间范围（ISO 8601格式，如2024-01-01T10:00:00+08:00，或描述性时间如每月1号、教师节等）
- **location** - 地点 `<Where>` (权重1.0, 阈值0.750)
  地点位置（明确的物理位置地址或虚拟坐标，如XX大厦23楼会议室、XX群聊）
- **person** - 人员 `<Who>` (权重1.1, 阈值1.000)
  人物角色（参与者、负责人、相关人员）
- **topic** - 话题 `<About>` (权重1.5, 阈值0.600)
  核心话题（事件的核心主题、主要对象、关键议题）
- **action** - 行为 `<How>` (权重1.2, 阈值0.800)
  行为动作（围绕话题产生的影响，包括操作、行为、进展等）
- **tags** - 标签 `<Tag>` (权重1.0, 阈值0.700)
  分类标签（事项的核心领域、分类、属性等基础维度标签）

> **相似度阈值说明**：阈值范围为0.000-1.000，用于控制实体向量检索和去重时的匹配精度。较高的阈值（如人名1.0）要求精确匹配，较低的阈值（如地点0.75、标签0.70）允许更灵活的表达方式。

**自定义实体维度**：

用户可根据业务场景自定义实体类型，并设置其权重和相似度阈值，如：

- **project_stage** - 项目阶段（需求分析、开发、测试、上线），权重1.2，阈值0.85
- **risk_level** - 风险等级（高、中、低），权重1.3，阈值0.90
- **cost_category** - 成本类别（人力、设备、外包），权重1.0，阈值0.75
- 任意符合业务需求的自定义维度...

#### 4. 智能召回机制

- **混合检索**：SQL精确查询 + Vector语义检索
- **多跳扩展**：BFS算法支持深度和广度可配置
- **动态评分**：综合相关度、时间衰减、用户偏好

---

## 📋 功能特性

### 核心模块

| 模块        | 功能描述                                     | 状态     |
| ----------- | -------------------------------------------- | -------- |
| **Load**    | 文档加载与预处理，支持Markdown/PDF/HTML      | ✅ 已实现 |
| **Extract** | 事项提取与实体识别，支持默认和自定义实体维度 | ✅ 已实现 |
| **Search**  | 智能检索，多维度匹配与多跳召回               | ✅ 已实现 |
| **Report**  | 报告生成，支持多种风格和格式                 | 🚧 开发中 |
| **Chat**    | 智能问答，基于事项上下文                     | 🚧 开发中 |

### 技术栈

```text
Frontend:  Next.js 14 + TypeScript + Tailwind CSS
Backend:   Python 3.11+ + FastAPI + SQLAlchemy
Database:  MySQL 8.0 + Elasticsearch 8.0 + Redis 7.0
AI:        OpenAI/Claude/本地模型 + Qwen/Qwen3-Embedding-0.6B
DevOps:    Docker + Docker Compose + UV
```

---

## 🔄 数据处理流程

```text
文档/会话
    ↓
Load模块
    ↓ 生成摘要/标签/分类
    ↓ 智能切块
Extract模块
    ↓ 提取事项
    ↓ 识别实体（默认+自定义维度）
    ↓ 生成向量
存储到DB/ES
    ↓
Search模块
    ↓ 语义检索
    ↓ 实体扩展
    ↓ 多维度匹配
    ↓ 动态评分排序
返回结果
```

---

## 🎯 核心算法

### 动态权重计算

DataFlow 通过实体类型权重和匹配维度计算事项间的相关度：

```python
相关度(A, B) = Σ(匹配维度权重 × 实体相似度) / Σ(所有维度权重)

# 示例：事项A与事项B
# A的实体：{TOPIC: [大模型, 微调], ORGANIZATION: [302.ai]}
# B的实体：{TOPIC: [LLM, 微调], ACTION: [优化]}
#
# 匹配维度：TOPIC (权重1.5)
# TOPIC相似度：Jaccard([大模型,微调], [LLM,微调]) = 0.67
# 相关度 = 0.67 × 1.5 / 1.5 = 0.67
```

### 多跳召回

```python
# 第1跳：从源事项A出发
A(大模型, 微调) → B(微调, 训练数据)
                → C(大模型, 推理优化)

# 第2跳：从B和C继续扩展
B → D(训练数据, 数据标注)
C → E(推理优化, 模型部署)

# 结果：A → B → D 和 A → C → E 两条路径
```

详细算法设计请参考：[algorithm.md](./algorithm.md)

---

## 🚀 快速开始

### 前置要求

- Python 3.11+
- Docker & Docker Compose
- MySQL 8.0+ / Elasticsearch 8.0+ / Redis 7.0+
- OpenAI API Key（或其他LLM提供商）

### 1. 克隆项目

```bash
git clone https://github.com/zleap-team/dataflow.git
cd dataflow
```

### 2. 使用 Docker Compose（推荐）

```bash
# 复制环境变量配置
cp .env.example .env

# 编辑 .env 填入你的配置
# MYSQL_PASSWORD=your_password
# LLM_API_KEY=sk-xxx

# 启动所有服务
docker compose up -d

# 初始化数据库
docker compose exec api uv run python scripts/init_database.py
docker compose exec api uv run python scripts/init_elasticsearch.py

# 查看日志
docker compose logs -f api

# 访问应用
# 前端界面: http://localhost:3000
# API文档: http://localhost:8000/api/docs
```

### 3. 本地开发环境

```bash
# 安装 UV（Python 包管理器）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建虚拟环境
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
uv pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env

# 初始化 NLTK 数据（首次运行必须）
python scripts/init_nltk.py

# 启动依赖服务（MySQL, ES, Redis）
docker compose up -d mysql elasticsearch redis

# 初始化数据库
python scripts/init_database.py

# 运行应用
uvicorn dataflow.api.main:app --reload
```

---

## 💻 使用示例

### Python SDK

```python
import asyncio
from dataflow import DataFlow, LoadConfig, ExtractConfig, SearchConfig

async def main():
    # 初始化客户端（source_config_id 是信息源ID，用于隔离不同来源的数据）
    client = DataFlow(source_config_id="source-001")

    # 1. 加载文档
    articles = await client.load(LoadConfig(
        type="path",
        origin=["./docs/article1.md", "./docs/article2.md"],
        background="AI技术文档",
        chunk_size=1000
    ))
    print(f"✓ 加载 {len(articles)} 篇文章")

    # 2. 提取事项（支持自定义实体维度和详细配置）
    events = await client.extract(ExtractConfig(
        article_ids=[article.id for article in articles],
        source_config_id="source-001",
        background="AI项目开发文档",
        filter_mode="intelligent",
        min_quality_score=0.7,

        # 自定义实体类型
        custom_entity_types=[
            CustomEntityType(
                type="project_stage",
                name="项目阶段",
                description="项目的生命周期阶段（需求分析、设计、开发、测试、上线）",
                weight=1.2,
                extraction_examples=[
                    {"input": "当前处于需求分析阶段", "output": "需求分析阶段"}
                ]
            ),
            CustomEntityType(
                type="risk_level",
                name="风险等级",
                description="事项的风险评估等级（高、中、低）",
                weight=1.1
            )
        ]
    ))
    print(f"✓ 提取 {len(events)} 个事项")

    # 3. 智能检索
    result = await client.search(SearchConfig(
        query="大模型优化方案",
        depth=2,        # 多跳深度
        breadth=3,      # 每跳广度
        threshold=0.5,  # 相关度阈值
        top_k=5
    ))

    # 4. 展示结果
    for event in result.events:
        score = result.scores[event.id]
        print(f"[{score:.2f}] {event.title}")
        print(f"  类别: {event.category}")
        print(f"  摘要: {event.summary}")
        print()

if __name__ == "__main__":
    asyncio.run(main())
```

### RESTful API

```bash
# 加载文档
curl -X POST http://localhost:8000/api/v1/load \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "type": "path",
      "origin": ["./docs/article.md"]
    },
    "source_config_id": "source_config-001"
  }'

# 提取事项
curl -X POST http://localhost:8000/api/v1/extract \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "article_ids": ["article-001"],
      "parallel": true
    },
    "source_config_id": "source_config-001"
  }'

# 智能检索
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "query": "大模型微调方案",
      "source_config_id": "source_config-001",
      "depth": 2,
      "top_k": 10
    }
  }'
```

---

## 📊 数据模型

### 核心表结构

```sql
-- 实体类型定义表
CREATE TABLE entity_type (
    id CHAR(36) PRIMARY KEY,
    source_config_id CHAR(36) DEFAULT NULL,       -- NULL表示系统默认类型
    type VARCHAR(50) NOT NULL,             -- 类型标识符：time, location, person等
    name VARCHAR(100) NOT NULL,            -- 类型名称
    is_default BOOLEAN DEFAULT FALSE,      -- 是否系统默认类型
    description TEXT,                      -- 类型描述
    weight DECIMAL(3,2) DEFAULT 1.00,      -- 默认权重
    similarity_threshold DECIMAL(4,3) DEFAULT 0.800, -- 相似度匹配阈值（0.000-1.000）
    extra_data JSON DEFAULT NULL,          -- 扩展数据：{"extraction_prompt": "", "validation_rule": {}}
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE KEY uk_source_type (source_config_id, type)
);

-- 实体表
CREATE TABLE entity (
    id CHAR(36) PRIMARY KEY,
    source_config_id CHAR(36) NOT NULL,
    event_id CHAR(36) NOT NULL,            -- 事项ID（外键）
    entity_type_id CHAR(36) NOT NULL,      -- 实体类型ID（外键）
    type VARCHAR(50) NOT NULL,             -- 类型标识符（冗余字段，便于查询）
    name VARCHAR(500) NOT NULL,            -- 实体名称
    normalized_name VARCHAR(500) NOT NULL, -- 标准化名称（用于匹配）
    description TEXT,                      -- 实体描述
    extra_data JSON DEFAULT NULL,          -- 扩展数据：{"synonyms": [], "weight": 1.0, "confidence": 1.0}
    KEY idx_event_id (event_id),
    KEY idx_entity_type_id (entity_type_id)
);

-- 事项表
CREATE TABLE source_event (
    id CHAR(36) PRIMARY KEY,
    source_config_id CHAR(36) NOT NULL,           -- 信息源ID
    article_id CHAR(36) NOT NULL,          -- 文章ID
    title VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL,
    content TEXT NOT NULL,
    rank INT NOT NULL DEFAULT 0,           -- 事项序号（同一来源内排序）
    start_time DATETIME,
    end_time DATETIME,
    references JSON DEFAULT NULL,          -- 原始片段引用
    extra_data JSON DEFAULT NULL,          -- 扩展数据：{"category": "", "priority": "", "status": "", "tags": []}
    created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_source_config_id (source_config_id),
    KEY idx_article_id (article_id),
    KEY idx_article_rank (article_id, rank)
);
```

### 实体数据示例

```json
// 默认维度：time 实体
{
  "name": "2024年6月1日下午3点",
  "type": "time",
  "normalized_name": "2024-06-01t15:00:00+08:00",
  "description": "302.ai大模型服务部署时间",
  "extra_data": {
    "iso_format": "2024-06-01T15:00:00+08:00",
    "timezone": "Asia/Shanghai",
    "precision": "hour",
    "confidence": 0.95
  }
}

// 默认维度：topic 实体
{
  "name": "大模型微调",
  "type": "topic",
  "normalized_name": "大模型微调",
  "description": "使用LoRA方法对GPT模型进行微调",
  "extra_data": {
    "synonyms": ["LLM微调", "模型微调", "Fine-tuning"],
    "domain": "AI",
    "complexity": "high",
    "weight": 1.5,
    "confidence": 0.92
  }
}

// 自定义维度：project_stage 实体
{
  "name": "需求分析阶段",
  "type": "project_stage",
  "normalized_name": "需求分析阶段",
  "description": "项目的需求分析和调研阶段",
  "extra_data": {
    "stage_order": 1,
    "duration_days": 14,
    "deliverables": ["需求文档", "原型设计"],
    "weight": 1.2,
    "source": "EXTRACTED"
  }
}
```

完整数据库设计：[database.md](./database.md)

---

## 🏗️ 架构设计

### 分层架构

```text
┌─────────────────────────────────────────────┐
│           应用层 (Application)               │
│  Load | Extract | Search | Report | Chat    │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│           业务层 (Business)                  │
│  Agent | Prompt | Config                    │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│           基础层 (Foundation)                │
│  AI | Storage | Utils                       │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│           存储层 (Storage)                   │
│  MySQL | Elasticsearch | Redis              │
└─────────────────────────────────────────────┘
```

### 与 GraphRAG 的对比

| 维度         | GraphRAG         | DataFlow      |
| ------------ | ---------------- | -------------- |
| **实体关系** | 预先构建知识图谱 | 检索时动态关联 |
| **维护成本** | 高（需维护图谱） | 低（无需维护） |
| **扩展性**   | 图谱结构固定     | 灵活适配查询   |
| **权重机制** | 静态边权重       | 动态多维度权重 |
| **关联发现** | 基于已有边       | 基于实体相似度 |

详细架构设计：[architecture.md](./architecture.md)

---

## 📚 完整文档

| 文档                              | 描述                                      |
| --------------------------------- | ----------------------------------------- |
| [系统架构设计](./architecture.md) | 分层架构、模块依赖、技术栈                |
| [数据库设计](./database.md)       | 完整表结构、索引策略、查询优化            |
| [模块详细设计](./module.md)       | 接口设计、数据模型、代码示例、工具类文档  |
| [核心算法设计](./algorithm.md)    | 动态权重、多跳召回、相关度评分            |
| [API接口文档](./document.md)      | Python SDK、RESTful API                   |
| [开发指南](./development.md)      | 环境搭建、开发规范、测试                  |
| [部署指南](./deployment.md)       | Docker部署、配置管理、监控                |

---

## 🛠️ 开发

### 项目结构

```text
dataflow/
├── dataflow/                 # 主代码目录
│   ├── core/                  # 核心模块
│   │   ├── ai/                # LLM调用
│   │   ├── agent/             # Agent编排
│   │   ├── storage/           # 数据访问
│   │   ├── prompt/            # 提示词管理
│   │   └── config/            # 配置管理
│   ├── modules/               # 应用模块
│   │   ├── load/              # 数据加载
│   │   ├── extract/           # 事项提取
│   │   ├── search/            # 智能检索
│   │   ├── report/            # 报告生成
│   │   └── chat/              # 智能问答
│   ├── models/                # 数据模型
│   ├── utils/                 # 工具函数（text, time, logger, token_estimator）
│   └── api/                   # API接口
├── tests/                     # 测试
├── scripts/                   # 脚本
├── prompts/                   # 提示词模板
├── docs/                      # 文档
├── docker-compose.yml         # Docker配置
└── pyproject.toml            # 项目配置
```

### 运行测试

```bash
# 安装测试依赖
uv pip install -e ".[dev]"

# 运行所有测试
pytest

# 查看覆盖率
pytest --cov=dataflow --cov-report=html

# 运行特定测试
pytest tests/unit/test_extractor.py
```

### 代码规范

```bash
# 格式化代码
black dataflow/

# 代码检查
ruff check dataflow/

# 类型检查
mypy dataflow/
```

---

## 🗺️ Roadmap

### V0.1.0 MVP（当前版本）✅

- [x] Load模块：文档加载与预处理
- [x] Extract模块：事项提取与实体识别（支持自动提取）
- [x] Search模块：智能检索与多跳召回
- [x] Python SDK
- [x] RESTful API
- [x] Web UI界面
- [x] Docker部署
- [x] 基础文档

### V0.2.0（计划中）🚧

- [ ] Report模块：报告生成
- [ ] Chat模块：智能问答
- [x] RESTful API ✅
- [ ] CLI工具
- [x] 支持PDF格式 ✅

### V0.3.0（未来规划）📋

- [x] Web UI ✅
- [ ] 多用户管理
- [ ] 权限控制
- [ ] 数据导入导出
- [ ] 性能优化（10x提升）

详细路线图：开发计划详见各模块设计文档

---

## 🤝 贡献指南

我们欢迎所有形式的贡献！

### 如何贡献

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'feat: Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### Commit 规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

- `feat:` 新功能
- `fix:` 修复bug
- `docs:` 文档更新
- `style:` 代码格式
- `refactor:` 重构
- `test:` 测试相关
- `chore:` 构建/工具链相关

### 开发流程

详见：[development.md](./development.md)

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 👥 团队

### Zleap Team（智跃团队）

- 项目官网：<https://zleap.ai>
- GitHub：<https://github.com/zleap-team>
- 邮箱：contact@zleap.ai

---

## 🔧 故障排除

### NLTK 数据问题

如果遇到 `BadZipFile: File is not a zip file` 错误：

```bash
# 方法 1：运行初始化脚本（推荐）
python scripts/init_nltk.py

# 方法 2：手动清理并重新下载
rm -rf ~/nltk_data/tokenizers/punkt*
python scripts/init_nltk.py

# 方法 3：在 Python 中强制重新下载
python -c "import nltk; nltk.download('punkt', force=True)"
```

### Docker 构建时 NLTK 数据问题

Dockerfile 已配置自动下载，如果仍有问题：

```bash
# 重新构建镜像（不使用缓存）
docker build -f Dockerfile.api -t dataflow-api --no-cache .
```

---

## 🙏 致谢

- 感谢 [MineContext](https://github.com/someorg/minecontext) 项目的启发
- 感谢所有贡献者的付出

---

## ⭐ Star History

如果这个项目对你有帮助，请给我们一个 Star ⭐

[![Star History Chart](https://api.star-history.com/svg?repos=zleap-team/dataflow&type=Date)](https://star-history.com/#zleap-team/dataflow&Date)

---

**[⬆ 回到顶部](#dataflow)**

Made with ❤️ by Zleap Team
