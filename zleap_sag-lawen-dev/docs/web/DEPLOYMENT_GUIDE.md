# 🚀 DataFlow 部署指南

## 快速部署三步走

### 1. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 设置 LLM_API_KEY
```

### 2. 启动服务
```bash
./scripts/start_all.sh
```

### 3. 初始化数据库
```bash
docker-compose exec api python scripts/init_database.py
```

## 访问应用
- Web UI: http://localhost:3000
- API Docs: http://localhost:8000/api/docs

完整文档: FULLSTACK_QUICKSTART.md
