# 🎯 DataFlow - 从这里开始！

**完整的 AI 数据处理引擎 - 后端 API + 前端 Web UI**

---

## ⚡ 超快启动（3 步）

### Step 1: 配置
```bash
cp .env.example .env
# 编辑 .env，设置 LLM_API_KEY=sk-xxx
```

### Step 2: 启动
```bash
./scripts/start_all.sh
```

### Step 3: 初始化
```bash
docker-compose exec api python scripts/init_database.py
docker-compose exec api python scripts/init_es_indices.py
```

### ✅ 完成！
访问: http://localhost:3000

---

## 📚 快速导航

| 内容 | 链接 |
|------|------|
| **Web UI** | http://localhost:3000 |
| **API 文档** | http://localhost:8000/api/docs |
| **完整启动指南** | [FULLSTACK_QUICKSTART.md](FULLSTACK_QUICKSTART.md) |
| **API 文档** | [docs/api/api.md](docs/api/api.md) |
| **前端文档** | [web/README.md](web/README.md) |

---

## 🔧 开发模式

```bash
# 1. 启动基础服务
./scripts/start_dev.sh

# 2. 终端1 - 后端
python -m dataflow.api.main

# 3. 终端2 - 前端
cd web && npm run dev
```

---

## 📊 项目结构

```
dataflow/
├── dataflow/api/      # FastAPI 后端 ✅
├── web/               # Next.js 前端 ✅  
├── docker-compose.yml # Docker 配置 ✅
└── scripts/           # 启动脚本 ✅
```

---

## 🆘 遇到问题？

查看: [FULLSTACK_QUICKSTART.md](FULLSTACK_QUICKSTART.md)

**Made with ❤️ by Zleap Team**
