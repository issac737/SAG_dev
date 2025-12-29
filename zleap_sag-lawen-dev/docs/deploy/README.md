# DataFlow 部署指南

生产级 Docker + Nginx 部署方案，支持自动 SSL 配置。

## 📚 文档导航

### 🏠 快速开始
- **[快速部署 →](./02-quick-deploy.md)** - 5分钟快速启动项目（推荐先看这个）

### 📖 详细指南
1. **[服务器准备](./01-prerequisites.md)** - 服务器配置、Docker 安装、环境准备
2. **[快速部署](./02-quick-deploy.md)** - 一键部署脚本、环境配置、启动验证
3. **[SSL 配置](./03-ssl-setup.md)** - HTTPS 证书配置、Let's Encrypt、自动续期
4. **[运维管理](./04-maintenance.md)** - 日志查看、数据备份、故障排查、更新升级

## 🚀 快速预览

### 最简部署（HTTP）
```bash
# 1. 克隆代码
git clone <your-repo-url> dataflow && cd dataflow

# 2. 配置环境
cp .env.example .env
vim .env  # 配置 LLM_API_KEY 等必需参数

# 3. 启动服务
./scripts/deploy.sh

# ✅ 访问：http://your-server-ip
```

### 完整部署（HTTPS）
```bash
# 1-2. 同上

# 3. 配置 SSL 证书
cp /path/to/cert.pem certs/fullchain.pem
cp /path/to/key.pem certs/privkey.pem

# 4. 启动服务（自动启用 HTTPS）
./scripts/deploy.sh

# ✅ 访问：https://your-domain.com
```

## 🏗️ 架构概览

```
Internet (80/443)
       ↓
   [Nginx 反向代理]
    ├─ / → Web 前端 (Next.js:3000)
    └─ /api/* → API 后端 (FastAPI:8000)
           ↓
    [MySQL + ElasticSearch + Redis]
```

### 核心特性
- ✅ **统一入口**：Nginx 统一管理所有请求
- ✅ **智能 SSL**：检测证书自动启用 HTTPS
- ✅ **生产就绪**：日志、监控、健康检查
- ✅ **一键部署**：自动化脚本，5分钟启动
- ✅ **易于运维**：完整文档和管理工具

## 📋 服务器要求

| 项目 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 2核 | 4核+ |
| 内存 | 4GB | 8GB+ |
| 磁盘 | 20GB | 50GB+ |
| 系统 | Ubuntu 20.04+ | Ubuntu 22.04 LTS |
| 网络 | 公网 IP | 固定 IP + 域名 |

## 🔧 核心组件

### 必需服务
- **MySQL 8.0** - 关系数据库
- **ElasticSearch 8.x** - 全文检索 + 向量搜索
- **Redis 7.x** - 缓存 + 消息队列
- **FastAPI** - 后端 API 服务
- **Next.js** - 前端 Web 应用
- **Nginx** - 反向代理 + 负载均衡

### 可选组件
- **SSL 证书** - HTTPS 加密（Let's Encrypt 免费）
- **Docker Compose** - 容器编排（已包含）

## 🌟 部署方式对比

| 方式 | 适用场景 | 难度 | 时间 |
|------|----------|------|------|
| **快速部署** | 开发/测试环境 | ⭐ | 5分钟 |
| **生产部署（HTTP）** | 内网/测试服务 | ⭐⭐ | 10分钟 |
| **生产部署（HTTPS）** | 公网正式服务 | ⭐⭐⭐ | 20分钟 |

## 📝 部署检查清单

### 部署前
- [ ] 服务器满足最低配置要求
- [ ] 已安装 Docker 和 Docker Compose
- [ ] 防火墙开放 80/443 端口
- [ ] 配置 Git Deploy Key（如需自动拉取）
- [ ] 准备 LLM API Key

### 部署后
- [ ] 所有服务健康检查通过
- [ ] 前端页面可正常访问
- [ ] API 文档可访问 (`/docs`)
- [ ] 数据库连接正常
- [ ] 文档上传功能正常
- [ ] 搜索功能正常

## 🆘 常见问题

### Q: 部署失败怎么办？
查看日志：
```bash
docker compose logs -f
```

常见原因：
1. 端口被占用 → 修改 `.env` 中的端口配置
2. 内存不足 → 检查 `docker stats`
3. 网络问题 → 检查防火墙和网络连接

### Q: 如何更新部署？
```bash
git pull
./scripts/deploy.sh
```

### Q: 数据会丢失吗？
不会。使用 Docker volumes 持久化：
- `mysql_data` - 数据库数据
- `es_data` - ElasticSearch 索引
- `redis_data` - Redis 数据
- `./uploads` - 上传文件

### Q: 如何备份数据？
参考 [运维管理文档](./04-maintenance.md#数据备份)

## 📞 获取帮助

- 📖 **完整文档**：查看本目录下的详细文档
- 🐛 **问题反馈**：提交 GitHub Issue
- 💬 **技术交流**：加入社区讨论

## 🎯 下一步

根据你的需求选择：

1. **我想快速体验** → [快速部署指南](./02-quick-deploy.md)
2. **我要生产部署** → 先看[服务器准备](./01-prerequisites.md)，再看[快速部署](./02-quick-deploy.md)
3. **我需要 HTTPS** → 部署后再看 [SSL 配置](./03-ssl-setup.md)
4. **我要学习运维** → [运维管理文档](./04-maintenance.md)

---

**推荐阅读顺序**：
快速部署 → SSL 配置 → 运维管理 → 服务器准备（需要时再看）
