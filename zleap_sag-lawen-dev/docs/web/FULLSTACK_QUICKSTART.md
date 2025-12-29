# 🚀 DataFlow 全栈快速启动指南

**从零到运行，5 分钟启动完整应用！**

---

## 📋 前置要求

✅ Docker & Docker Compose  
✅ Node.js 18+ (开发模式需要)  
✅ Python 3.11+ (开发模式需要)  
✅ OpenAI API Key

---

## 🎯 方式一：一键 Docker 启动（推荐）

### 步骤 1：配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，至少配置以下内容：
# LLM_API_KEY=sk-your-openai-api-key
# LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507
```

### 步骤 2：一键启动

```bash
# 使用启动脚本（推荐）
./scripts/start_all.sh

# 或手动执行
docker-compose up -d
```

### 步骤 3：初始化数据库

```bash
# 初始化 MySQL 表结构
docker-compose exec api python scripts/init_database.py

# 初始化 Elasticsearch 索引
docker-compose exec api python scripts/init_es_indices.py
```

### 步骤 4：访问应用

🎉 **完成！** 访问：

- **Web UI**: http://localhost:3000
- **API 文档**: http://localhost:8000/api/docs
- **健康检查**: http://localhost:8000/health

---

## 💻 方式二：开发模式（本地运行）

适合前后端开发调试，支持热重载。

### 步骤 1：启动基础服务

```bash
# 启动 MySQL, Elasticsearch, Redis
./scripts/start_dev.sh

# 或手动执行
docker-compose -f docker-compose.dev.yml up -d
```

### 步骤 2：启动后端 API（终端 1）

```bash
# 安装 Python 依赖
uv pip install -e "."

# 配置环境变量
cp .env.example .env
# 编辑 .env 配置 LLM_API_KEY

# 启动后端（自动重载）
python -m dataflow.api.main
```

### 步骤 3：启动前端（终端 2）

```bash
# 进入 web 目录
cd web

# 安装依赖（首次运行）
npm install

# 配置 API 地址
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# 启动前端（自动重载）
npm run dev
```

### 步骤 4：访问应用

- **Web UI**: http://localhost:3000 （前端开发服务器）
- **API**: http://localhost:8000 （后端 API 服务）

---

## 📦 服务说明

### 完整服务列表

| 服务              | 端口 | 说明               |
| ----------------- | ---- | ------------------ |
| **Web UI**        | 3000 | Next.js 前端应用   |
| **API**           | 8000 | FastAPI 后端服务   |
| **MySQL**         | 3306 | 关系型数据库       |
| **Elasticsearch** | 9200 | 向量检索和全文检索 |
| **Redis**         | 6379 | 缓存服务           |

### 服务依赖关系

```
Web UI (3000)
    ↓
API (8000)
    ↓
┌──────────┬──────────┬──────────┐
│  MySQL   │   ES     │  Redis   │
│  (3306)  │  (9200)  │  (6379)  │
└──────────┴──────────┴──────────┘
```

---

## 🎮 快速测试

### 1. 创建信息源

访问：http://localhost:3000/sources

或使用 API：
```bash
curl -X POST http://localhost:8000/api/v1/sources \
  -H "Content-Type: application/json" \
  -d '{"name": "测试知识库", "description": "我的第一个信息源"}'
```

### 2. 上传文档

访问：http://localhost:3000/documents

或使用 API：
```bash
curl -X POST "http://localhost:8000/api/v1/sources/{source_config_id}/documents/upload" \
  -F "file=@./docs/article.md" \
  -F "auto_process=true"
```

### 3. 执行搜索

访问：http://localhost:3000/search

或使用 API：
```bash
curl -X POST "http://localhost:8000/api/v1/pipeline/search" \
  -H "Content-Type: application/json" \
  -d '{
    "source_config_id": "{source_config_id}",
    "query": "AI技术",
    "mode": "sag",
    "top_k": 5
  }'
```

---

## 🛠️ 管理命令

### Docker 管理

```bash
# 查看所有服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f api
docker-compose logs -f web

# 重启服务
docker-compose restart api
docker-compose restart web

# 停止所有服务
docker-compose down

# 停止并删除数据（危险！）
docker-compose down -v
```

### 数据库管理

```bash
# 进入 MySQL 容器
docker-compose exec mysql mysql -u dataflow -p

# 重新创建数据库
docker-compose exec api python scripts/recreate_database.py

# 查看 Elasticsearch 状态
curl http://localhost:9200/_cluster/health
```

---

## 🐛 故障排查

### Web UI 无法连接 API

1. 检查 API 是否启动：`curl http://localhost:8000/health`
2. 检查环境变量：`cat web/.env.local`
3. 确保 CORS 已配置（API 已默认允许所有来源）

### API 启动失败

1. 检查数据库连接：`docker-compose ps mysql`
2. 查看 API 日志：`docker-compose logs api`
3. 检查环境变量：`cat .env`

### 数据库连接失败

```bash
# 检查 MySQL 是否运行
docker-compose ps mysql

# 查看 MySQL 日志
docker-compose logs mysql

# 测试连接
docker-compose exec mysql mysql -u dataflow -pdataflow_pass
```

### 前端构建失败

```bash
cd web

# 清理缓存
rm -rf .next node_modules

# 重新安装依赖
npm install

# 重新构建
npm run build
```

---

## 📂 项目结构

```
dataflow/
├── dataflow/              # Python 后端
│   ├── api/               # FastAPI 接口 ✅
│   ├── core/              # 核心模块
│   ├── modules/           # 功能模块
│   └── ...
│
├── web/                   # Next.js 前端 ✅
│   ├── app/               # 页面路由
│   ├── components/        # React 组件
│   ├── lib/               # 工具函数
│   └── ...
│
├── docker-compose.yml     # 生产环境配置 ✅
├── docker-compose.dev.yml # 开发环境配置 ✅
├── Dockerfile.api         # 后端 Dockerfile ✅
├── web/Dockerfile         # 前端 Dockerfile ✅
│
├── scripts/               # 启动脚本 ✅
│   ├── start_all.sh       # 一键启动全栈
│   ├── start_dev.sh       # 启动开发环境
│   └── ...
│
└── docs/                  # 文档
    ├── api/               # API 文档
    └── ...
```

---

## 🎯 开发工作流

### 典型开发流程

```bash
# 1. 启动基础服务
./scripts/start_dev.sh

# 2. 启动后端（终端 1）
python -m dataflow.api.main

# 3. 启动前端（终端 2）
cd web && npm run dev

# 4. 开始开发
# - 后端修改自动重载
# - 前端修改自动刷新
```

### 测试流程

```bash
# 后端测试
pytest

# 前端测试（如果有）
cd web && npm test
```

---

## 🚀 部署到生产

### 使用 Docker Compose

```bash
# 1. 配置生产环境变量
cp .env.example .env
# 编辑 .env 设置所有必要的配置

# 2. 构建并启动
docker-compose up -d --build

# 3. 初始化数据库
docker-compose exec api python scripts/init_database.py
docker-compose exec api python scripts/init_es_indices.py

# 4. 检查状态
docker-compose ps
docker-compose logs -f
```

### 性能优化建议

1. **API Worker 数量**：在 `.env` 中设置 `API_WORKERS=4`
2. **资源限制**：在 docker-compose.yml 中添加 `resources` 配置
3. **Nginx 反向代理**：生产环境建议使用 Nginx
4. **HTTPS**：配置 SSL 证书

---

## 📚 相关文档

- [API 文档](docs/api/api.md)
- [API 快速开始](docs/api/API_QUICKSTART.md)
- [前端 README](web/README.md)
- [项目 README](docs/README.md)

---

## 🆘 需要帮助？

- **GitHub**: https://github.com/zleap-team/dataflow
- **Email**: contact@zleap.ai
- **文档**: [docs/README.md](docs/README.md)

---

## 🎉 完成！

现在你可以：

✅ 通过 Web UI 管理信息源  
✅ 上传文档自动处理  
✅ 执行智能搜索  
✅ 监控任务状态  
✅ 配置自定义实体维度  

**开始体验 DataFlow 的强大功能吧！** 🚀

---

**Made with ❤️ by Zleap Team**

