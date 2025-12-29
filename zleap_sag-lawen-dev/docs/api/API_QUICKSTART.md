# DataFlow API 快速开始

**5 分钟快速启动 DataFlow API 服务**

---

## 🚀 快速启动（3 步）

### 步骤 1：安装依赖

```bash
# 克隆项目（如果还没有）
git clone https://github.com/zleap-team/dataflow.git
cd dataflow

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖（使用 uv 更快）
uv pip install -e "."

# 或使用 pip
pip install -e "."
```

### 步骤 2：配置环境

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，至少配置：
# - LLM_API_KEY: 你的 OpenAI API Key
# - MYSQL_PASSWORD: 数据库密码
```

**最小配置**（使用本地数据库）：
```bash
# .env
LLM_API_KEY=sk-your-openai-api-key
MYSQL_PASSWORD=your_mysql_password
```

### 步骤 3：启动服务

```bash
# 方式 1：开发模式（推荐，自动重载）
python -m dataflow.api.main

# 方式 2：生产模式
python scripts/start_api.py

# 方式 3：使用 uvicorn
uvicorn dataflow.api.main:app --reload
```

**启动成功后**，访问：
- 📚 API 文档: http://localhost:8000/api/docs
- 📖 ReDoc: http://localhost:8000/api/redoc
- ✅ 健康检查: http://localhost:8000/health

---

## 🎯 快速测试

### 1. 创建信息源

```bash
curl -X POST http://localhost:8000/api/v1/sources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "测试知识库",
    "description": "我的第一个数据源"
  }'
```

**响应示例**：
```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "测试知识库",
    "description": "我的第一个数据源",
    "created_time": "2024-01-01T00:00:00"
  },
  "message": "信息源创建成功"
}
```

💡 **记住这个 `id`，后续步骤需要用到！**

### 2. 查看默认实体类型

```bash
curl http://localhost:8000/api/v1/entity-types/defaults
```

返回 6 种默认实体维度：
- ⏰ **time** - 时间
- 📍 **location** - 地点
- 👤 **person** - 人员
- 💡 **topic** - 话题
- 🎯 **action** - 行为
- 🏷️ **tags** - 标签

### 3. 创建自定义实体类型

```bash
curl -X POST "http://localhost:8000/api/v1/sources/{source_config_id}/entity-types" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "priority",
    "name": "优先级",
    "description": "任务的优先级（高、中、低）",
    "weight": 1.3
  }'
```

### 4. 上传文档

```bash
# 创建测试文档
cat > test_doc.md << EOF
# AI 技术简介

## 机器学习
机器学习是人工智能的核心技术。

## 深度学习
深度学习使用神经网络模型。
EOF

# 上传文档
curl -X POST "http://localhost:8000/api/v1/sources/{source_config_id}/documents/upload" \
  -F "file=@test_doc.md" \
  -F "auto_process=true"
```

### 5. 执行搜索

```bash
curl -X POST "http://localhost:8000/api/v1/pipeline/search" \
  -H "Content-Type: application/json" \
  -d '{
    "source_config_id": "{source_config_id}",
    "query": "机器学习",
    "mode": "llm",
    "top_k": 5
  }'
```

---

## 🐳 使用 Docker（推荐生产环境）

### Docker Compose 一键启动

```bash
# 复制环境变量
cp .env.example .env
# 编辑 .env 配置

# 启动所有服务（API + MySQL + ES + Redis）
docker-compose up -d

# 查看日志
docker-compose logs -f api

# 初始化数据库
docker-compose exec api python scripts/init_database.py
docker-compose exec api python scripts/init_es_indices.py
```

访问：http://localhost:8000/api/docs

---

## 📚 API 功能速览

### 核心接口

| 模块 | 接口 | 功能 |
|------|------|------|
| **信息源** | `POST /api/v1/sources` | 创建信息源 |
| **实体维度** | `POST /api/v1/sources/{id}/entity-types` | 自定义实体类型 |
| **文档** | `POST /api/v1/sources/{id}/documents/upload` | 上传文档 |
| **流程** | `POST /api/v1/pipeline/run` | 异步执行完整流程 |
| **任务** | `GET /api/v1/tasks/{id}` | 查询任务状态 |

### 流程组合（可分可合）

```bash
# 方式 1：完整流程（Load → Extract → Search）
POST /api/v1/pipeline/run

# 方式 2：单独执行
POST /api/v1/pipeline/load      # 只 Load
POST /api/v1/pipeline/extract   # 只 Extract
POST /api/v1/pipeline/search    # 只 Search

# 方式 3：文档上传自动处理
POST /api/v1/sources/{id}/documents/upload?auto_process=true
```

---

## 🔧 常见问题

### Q1: 启动失败 - 端口被占用

```bash
# 查看占用进程
lsof -i :8000

# 或修改端口
API_PORT=8001 python -m dataflow.api.main
```

### Q2: 数据库连接失败

```bash
# 检查 MySQL 是否运行
mysql -u root -p

# 检查配置
cat .env | grep MYSQL
```

### Q3: LLM API 调用失败

```bash
# 检查 API Key
echo $LLM_API_KEY

# 测试连接
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $LLM_API_KEY"
```

### Q4: 文档上传失败

```bash
# 检查上传目录权限
mkdir -p ./uploads
chmod 755 ./uploads

# 检查文件大小限制
# 修改 .env: MAX_UPLOAD_SIZE=209715200  # 200MB
```

---

## 📖 完整文档

- **API 详细文档**: [docs/api.md](./api.md)
- **项目 README**: [docs/README.md](./README.md)
- **架构设计**: [docs/architecture.md](./architecture.md)
- **数据库设计**: [docs/database.md](./database.md)

---

## 🎉 下一步

1. ✅ **浏览 API 文档**: http://localhost:8000/api/docs
2. 📝 **创建第一个信息源**
3. 📤 **上传文档测试**
4. 🔍 **执行搜索查询**
5. 🚀 **集成到你的 Web UI**

---

## 💡 提示

- 开发时使用 `DEBUG=true` 查看详细日志
- 生产环境配置 `API_WORKERS=4` 启用多进程
- 使用 Redis 缓存提升性能
- 定期备份数据库

---

## 🆘 需要帮助？

- 📧 Email: contact@zleap.ai
- 💬 GitHub Issues: https://github.com/zleap-team/dataflow/issues
- 📖 完整文档: [docs/](./README.md)

---

**Made with ❤️ by Zleap Team**

