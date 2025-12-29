# DataFlow API 文档

**FastAPI 接口 - 为 Web UI 提供完整的后端支持**

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 使用 uv（推荐）
uv pip install -e "."

# 或使用 pip
pip install -e "."
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
# 数据库配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=dataflow
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=dataflow

# Elasticsearch
ES_HOST=localhost
ES_PORT=9200

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# LLM API
LLM_API_KEY=sk-your-api-key
LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507
LLM_BASE_URL=https://api.openai.com/v1  # 可选，使用中转API

# Embedding API
EMBEDDING_API_KEY=sk-your-api-key
EMBEDDING_MODEL_NAME=Qwen/Qwen3-Embedding-0.6B

# API 配置
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
DEBUG=false

# 文件上传
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE=104857600  # 100MB
```

### 3. 启动 API 服务

```bash
# 方式 1：直接运行（开发模式，自动重载）
python -m dataflow.api.main

# 方式 2：使用启动脚本（生产模式）
python scripts/start_api.py

# 方式 3：使用 uvicorn
uvicorn dataflow.api.main:app --host 0.0.0.0 --port 8000 --reload

# 方式 4：生产环境（多进程）
uvicorn dataflow.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. 访问 API 文档

启动后访问：

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **OpenAPI JSON**: http://localhost:8000/api/openapi.json
- **健康检查**: http://localhost:8000/health

---

## 📚 API 功能模块

### 1. 信息源管理 (`/api/v1/sources`)

管理不同的信息源（数据源）

#### 创建信息源

```bash
curl -X POST http://localhost:8000/api/v1/sources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "我的知识库",
    "description": "AI技术文档集合",
    "config": {
      "focus": ["AI", "机器学习"],
      "language": "zh"
    }
  }'
```

#### 获取信息源列表

```bash
curl -X GET "http://localhost:8000/api/v1/sources?page=1&page_size=20"
```

#### 获取信息源详情

```bash
curl -X GET "http://localhost:8000/api/v1/sources/{source_config_id}"
```

#### 更新信息源

```bash
curl -X PATCH "http://localhost:8000/api/v1/sources/{source_config_id}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "新名称",
    "description": "新描述"
  }'
```

#### 删除信息源

```bash
curl -X DELETE "http://localhost:8000/api/v1/sources/{source_config_id}"
```

---

### 2. 实体维度管理 (`/api/v1/entity-types`)

管理自定义实体类型（扩展默认的 6 种维度）

#### 获取默认实体类型

```bash
curl -X GET "http://localhost:8000/api/v1/entity-types/defaults"
```

返回 6 种默认实体：
- **time** - 时间（权重0.9，阈值0.900）
- **location** - 地点（权重1.0，阈值0.750）
- **person** - 人员（权重1.1，阈值1.000）
- **topic** - 话题（权重1.5，阈值0.600）
- **action** - 行为（权重1.2，阈值0.800）
- **tags** - 标签（权重1.0，阈值0.700）

#### 创建自定义实体类型

```bash
curl -X POST "http://localhost:8000/api/v1/sources/{source_config_id}/entity-types" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "project_stage",
    "name": "项目阶段",
    "description": "项目的生命周期阶段（需求分析、设计、开发、测试、上线）",
    "weight": 1.2,
    "similarity_threshold": 0.85,
    "extraction_examples": [
      {"input": "当前处于需求分析阶段", "output": "需求分析阶段"},
      {"input": "项目已进入测试阶段", "output": "测试阶段"}
    ]
  }'
```

#### 获取实体类型列表

```bash
curl -X GET "http://localhost:8000/api/v1/sources/{source_config_id}/entity-types?include_defaults=true"
```

#### 更新实体类型

```bash
curl -X PATCH "http://localhost:8000/api/v1/entity-types/{entity_type_id}" \
  -H "Content-Type: application/json" \
  -d '{
    "weight": 1.5,
    "is_active": true
  }'
```

#### 删除实体类型

```bash
curl -X DELETE "http://localhost:8000/api/v1/entity-types/{entity_type_id}"
```

---

### 3. 文档管理 (`/api/v1/documents`)

上传和管理文档

#### 上传单个文档

```bash
curl -X POST "http://localhost:8000/api/v1/sources/{source_config_id}/documents/upload" \
  -F "file=@./docs/article.md" \
  -F "background=这是AI技术文档" \
  -F "auto_process=true"
```

**参数说明**：
- `file`: 文档文件（支持 .md, .txt, .pdf, .html）
- `background`: 背景信息（可选）
- `auto_process`: 是否自动执行 Load+Extract（默认 true）

#### 批量上传文档

```bash
curl -X POST "http://localhost:8000/api/v1/sources/{source_config_id}/documents/upload-multiple" \
  -F "files=@./docs/article1.md" \
  -F "files=@./docs/article2.md" \
  -F "auto_process=true"
```

#### 获取文档列表

```bash
curl -X GET "http://localhost:8000/api/v1/sources/{source_config_id}/documents?page=1&page_size=20"
```

#### 获取文档详情

```bash
curl -X GET "http://localhost:8000/api/v1/documents/{article_id}"
```

#### 删除文档

```bash
curl -X DELETE "http://localhost:8000/api/v1/documents/{article_id}"
```

---

### 4. 统一流程 (`/api/v1/pipeline`)

执行 Load → Extract → Search 完整流程

#### 异步执行完整流程

```bash
curl -X POST "http://localhost:8000/api/v1/pipeline/run" \
  -H "Content-Type: application/json" \
  -d '{
    "source_config_id": "source-001",
    "task_name": "处理AI文档",
    "background": "AI技术文档集合",
    "load": {
      "path": "./docs/article.md",
      "recursive": true,
      "pattern": "*.md"
    },
    "extract": {
      "parallel": true,
      "max_concurrency": 3
    },
    "search": {
      "query": "查找AI相关内容",
      "mode": "sag",
      "top_k": 10
    },
    "output": {
      "mode": "full",
      "format": "json"
    }
  }'
```

**返回示例**：
```json
{
  "success": true,
  "data": {
    "task_id": "task-123456",
    "status": "pending",
    "message": "任务已创建，正在执行中..."
  },
  "message": "流程已启动"
}
```

#### 同步执行完整流程

```bash
curl -X POST "http://localhost:8000/api/v1/pipeline/run-sync" \
  -H "Content-Type: application/json" \
  -d '{
    "source_config_id": "source-001",
    "load": {...},
    "extract": {...},
    "search": {...}
  }'
```

⚠️ **注意**：同步接口会等待所有阶段完成，适合小规模数据。大规模文档建议使用异步接口。

#### 只执行 Load 阶段

```bash
curl -X POST "http://localhost:8000/api/v1/pipeline/load" \
  -H "Content-Type: application/json" \
  -d '{
    "source_config_id": "source-001",
    "path": "./docs/article.md",
    "recursive": true,
    "pattern": "*.md"
  }'
```

#### 只执行 Extract 阶段

```bash
curl -X POST "http://localhost:8000/api/v1/pipeline/extract" \
  -H "Content-Type: application/json" \
  -d '{
    "source_config_id": "source-001",
    "article_id": "article-123",
    "parallel": true,
    "max_concurrency": 3
  }'
```

#### 只执行 Search 阶段

```bash
curl -X POST "http://localhost:8000/api/v1/pipeline/search" \
  -H "Content-Type: application/json" \
  -d '{
    "source_config_id": "source-001",
    "query": "查找AI相关内容",
    "mode": "sag",
    "top_k": 10,
    "threshold": 0.5
  }'
```

---

### 5. 任务管理 (`/api/v1/tasks`)

查询和管理异步任务

#### 查询任务状态

```bash
curl -X GET "http://localhost:8000/api/v1/tasks/{task_id}"
```

**返回示例**：
```json
{
  "success": true,
  "data": {
    "task_id": "task-123456",
    "status": "completed",
    "progress": 1.0,
    "message": "任务完成",
    "result": {
      "load": {...},
      "extract": {...},
      "search": {...}
    }
  }
}
```

#### 获取任务列表

```bash
curl -X GET "http://localhost:8000/api/v1/tasks?page=1&page_size=20&status=completed"
```

#### 取消任务

```bash
curl -X POST "http://localhost:8000/api/v1/tasks/{task_id}/cancel"
```

---

## 🔧 配置说明

### 搜索模式

`mode` 参数支持三种模式：

1. **LLM 模式**（`"llm"`）：大模型智能检索（默认）
2. **RAG 模式**（`"rag"`）：纯向量语义检索
3. **SAG 模式**（`"sag"`）：SQL驱动的混合检索（推荐）

### 输出模式

`output.mode` 参数：

- **full**：返回完整数据（包含所有字段）
- **id_only**：只返回 ID 列表（节省带宽）

---

## 💡 使用示例

### 完整工作流示例

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# 1. 创建信息源
response = requests.post(f"{BASE_URL}/sources", json={
    "name": "AI技术文档库",
    "description": "收集AI相关技术文档",
})
source_config_id = response.json()["data"]["id"]

# 2. 创建自定义实体类型
requests.post(f"{BASE_URL}/sources/{source_config_id}/entity-types", json={
    "type": "tech_stack",
    "name": "技术栈",
    "description": "使用的技术和框架",
    "weight": 1.3,
})

# 3. 上传文档
files = {"file": open("./docs/article.md", "rb")}
data = {"auto_process": "true"}
response = requests.post(
    f"{BASE_URL}/sources/{source_config_id}/documents/upload",
    files=files,
    data=data,
)

# 4. 执行完整流程
response = requests.post(f"{BASE_URL}/pipeline/run", json={
    "source_config_id": source_config_id,
    "task_name": "处理AI文档",
    "load": {
        "path": "./docs/",
        "recursive": True,
    },
    "extract": {
        "parallel": True,
    },
    "search": {
        "query": "深度学习模型优化",
        "mode": "sag",
        "top_k": 5,
    },
})
task_id = response.json()["data"]["task_id"]

# 5. 查询任务状态
while True:
    response = requests.get(f"{BASE_URL}/tasks/{task_id}")
    status = response.json()["data"]["status"]
    if status in ["completed", "failed"]:
        break
    time.sleep(2)

# 6. 获取结果
result = response.json()["data"]["result"]
print(result)
```

---

## 🐳 Docker 部署

### 使用 Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MYSQL_HOST=mysql
      - ES_HOST=elasticsearch
      - REDIS_HOST=redis
      - LLM_API_KEY=${LLM_API_KEY}
    depends_on:
      - mysql
      - elasticsearch
      - redis
    command: python scripts/start_api.py
  
  mysql:
    image: mysql:8.0
    # ... 配置

  elasticsearch:
    image: elasticsearch:8.0.0
    # ... 配置

  redis:
    image: redis:7.0
    # ... 配置
```

启动：
```bash
docker-compose up -d
```

---

## 🔐 安全建议

### 生产环境

1. **配置 CORS**：限制允许的域名
2. **添加认证**：实现 API Key 或 JWT 认证
3. **限流**：添加请求频率限制
4. **HTTPS**：使用 SSL/TLS 加密
5. **监控**：添加日志和性能监控

### 环境变量管理

```bash
# 不要将 .env 提交到 Git
echo ".env" >> .gitignore

# 生产环境使用密钥管理服务
# AWS Secrets Manager / Azure Key Vault / HashiCorp Vault
```

---

## 📊 性能优化

### 1. 异步处理

对于大规模文档，使用异步接口：
- `/pipeline/run` 而不是 `/pipeline/run-sync`
- 通过 `/tasks/{task_id}` 查询进度

### 2. 批量操作

使用批量上传接口减少请求次数：
- `/documents/upload-multiple`

### 3. 缓存

API 内部使用 Redis 缓存：
- LLM 响应缓存
- 实体扩展缓存
- 搜索结果缓存

---

## 🐛 故障排查

### API 无法启动

1. 检查端口占用：`lsof -i :8000`
2. 检查数据库连接：确保 MySQL/ES/Redis 正常运行
3. 检查环境变量：`.env` 文件配置正确

### 文档上传失败

1. 检查文件大小：不超过 `MAX_UPLOAD_SIZE`
2. 检查文件格式：支持 .md, .txt, .pdf, .html
3. 检查上传目录权限：`UPLOAD_DIR` 可写

### 任务执行失败

1. 查看任务详情：`/tasks/{task_id}`
2. 检查 LLM API：配置正确且有额度
3. 查看服务器日志：`docker-compose logs api`

---

## 📞 技术支持

- **文档**: [完整文档](../README.md)
- **GitHub**: https://github.com/zleap-team/dataflow
- **邮箱**: contact@zleap.ai

---

**Made with ❤️ by Zleap Team**

