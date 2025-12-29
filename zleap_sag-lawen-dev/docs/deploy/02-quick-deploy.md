# 快速部署指南

⚡ 5分钟完成 DataFlow 的生产部署。

## 🎯 部署概览

### 部署流程
```
克隆代码 → 配置环境 → (可选)放置证书 → 启动服务 → 验证
   2分钟      2分钟         1分钟          1分钟      1分钟
```

### 前置条件
- ✅ 已安装 Docker 和 Docker Compose ([参考准备指南](./01-prerequisites.md))
- ✅ 防火墙已开放 80/443 端口
- ✅ 磁盘可用空间 ≥ 20GB

## 🚀 快速开始

### 步骤 1：克隆代码

```bash
# SSH 方式（推荐，需配置 Deploy Key）
git clone git@github.com:your-org/dataflow.git
cd dataflow

# 或 HTTPS 方式
git clone https://github.com/your-org/dataflow.git
cd dataflow
```

### 步骤 2：配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置文件
vim .env  # 或使用 nano .env
```

#### 必需配置项

编辑 `.env`，配置以下内容：

```bash
# ============================================
# LLM 配置（必需）
# ============================================
LLM_API_KEY=sk-xxxxx          # OpenAI API Key 或兼容服务
LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507               # 模型名称
LLM_BASE_URL=https://api.openai.com/v1  # API 地址

# Embedding 配置
EMBEDDING_MODEL_NAME=Qwen/Qwen3-Embedding-0.6B
EMBEDDING_BASE_URL=https://api.openai.com/v1

# ============================================
# 数据库配置（使用默认值即可）
# ============================================
MYSQL_ROOT_PASSWORD=dataflow_root
MYSQL_DATABASE=dataflow
MYSQL_USER=dataflow
MYSQL_PASSWORD=dataflow_pass

# ============================================
# 其他配置（可选）
# ============================================
# API_HOST=0.0.0.0
# API_PORT=8000
```

**重要提示**：
- `LLM_API_KEY` 是必需的，否则无法使用提取功能
- 数据库密码建议修改为强密码（生产环境）
- 如使用其他 LLM 服务（如 Azure, Anthropic），相应修改 `LLM_BASE_URL` 和模型名称

### 步骤 3：配置 SSL 证书（可选）

如果需要 HTTPS，将证书文件放入 `certs/` 目录：

```bash
# 方式 1：复制现有证书
cp /path/to/your/fullchain.pem certs/
cp /path/to/your/privkey.pem certs/

# 方式 2：使用 Let's Encrypt（推荐）
# 参考 SSL 配置文档
```

**注意**：
- 证书文件必须命名为 `fullchain.pem` 和 `privkey.pem`
- 如果不放置证书，系统将使用 HTTP（80端口）
- 可以先使用 HTTP 部署，后续再配置 HTTPS

### 步骤 4：启动服务

```bash
# 使用部署脚本一键启动（推荐）
./scripts/deploy.sh

# 或手动启动
docker compose up -d
```

部署脚本会自动：
1. ✅ 检测 SSL 证书是否存在
2. ✅ 拉取/构建 Docker 镜像
3. ✅ 启动所有服务（MySQL, ES, Redis, API, Web, Nginx）
4. ✅ 等待服务健康检查通过

**首次启动时间**：
- 镜像拉取：2-5 分钟
- 服务启动：1-2 分钟
- **总计**：3-7 分钟

### 步骤 5：验证部署

```bash
# 检查所有服务状态
docker compose ps

# 预期输出：所有服务状态应为 "Up (healthy)"
```

#### 访问验证

1. **前端应用**
   - HTTP: `http://your-server-ip`
   - HTTPS: `https://your-domain.com`（如已配置SSL）

2. **API 文档**
   - Swagger UI: `http://your-server-ip/docs`
   - ReDoc: `http://your-server-ip/redoc`

3. **健康检查**
   ```bash
   curl http://your-server-ip/health
   # 预期输出: {"status": "healthy"}
   ```

## 🎉 部署成功！

如果以上验证都通过，恭喜你已成功部署 DataFlow！

### 接下来可以：

1. **创建信息源**
   - 访问前端 → 设置 → 信息源管理
   - 点击"新建"创建第一个信息源

2. **上传文档**
   - 选择信息源 → 上传文档
   - 支持格式：MD, TXT, PDF, DOCX 等

3. **开始搜索**
   - 访问搜索页面
   - 输入 `@` 选择信息源
   - 输入查询内容开始搜索

## 📋 详细步骤（手动部署）

如果不使用一键脚本，可以手动执行以下命令：

### 构建镜像
```bash
# 构建后端 API
docker compose build api

# 构建前端 Web
docker compose build web

# 构建 ElasticSearch（使用自定义 Dockerfile）
docker compose build elasticsearch
```

### 启动服务
```bash
# 启动所有服务
docker compose up -d

# 查看启动日志
docker compose logs -f

# Ctrl+C 退出日志查看
```

### 初始化数据库
```bash
docker compose exec api uv run python scripts/init_database.py
```

### 初始化 ElasticSearch
```bash
docker compose exec api uv run python scripts/init_elasticsearch.py
```

## 🔧 常见问题

### 1. 服务启动失败

**问题**：`docker compose ps` 显示服务状态为 `Exited`

**解决**：
```bash
# 查看失败服务的日志
docker compose logs api      # 查看 API 日志
docker compose logs web      # 查看 Web 日志
docker compose logs mysql    # 查看 MySQL 日志

# 常见原因：
# - 端口被占用
# - 内存不足
# - 环境变量配置错误
```

### 2. 无法访问前端

**问题**：浏览器无法打开 `http://your-server-ip`

**检查清单**：
```bash
# 1. 检查 Nginx 服务状态
docker compose ps nginx

# 2. 检查防火墙
sudo ufw status  # Ubuntu
sudo firewall-cmd --list-all  # CentOS

# 3. 检查端口占用
sudo netstat -tlnp | grep ':80'

# 4. 检查服务器安全组（云服务器）
# 确保安全组规则允许 80/443 端口入站
```

### 3. API 返回 502 Bad Gateway

**问题**：前端可以访问，但 API 请求失败

**解决**：
```bash
# 检查 API 服务状态
docker compose ps api

# 查看 API 日志
docker compose logs api

# 重启 API 服务
docker compose restart api
```

### 4. 数据库连接失败

**问题**：日志显示 "Can't connect to MySQL server"

**解决**：
```bash
# 等待 MySQL 完全启动（首次需要 1-2 分钟）
docker compose logs mysql

# 查看 MySQL 健康检查
docker compose ps mysql
# 状态应为 "Up (healthy)"

# 手动测试连接
docker compose exec api python -c "from dataflow.database import get_db; print('OK')"
```

### 5. ElasticSearch 内存不足

**问题**：日志显示 "OutOfMemoryError"

**解决**：
```bash
# 修改 docker-compose.yml 中的 ES_JAVA_OPTS
vim docker-compose.yml

# 将 -Xms512m -Xmx512m 改为 -Xms256m -Xmx256m

# 重启服务
docker compose restart elasticsearch
```

### 6. 文件上传失败

**问题**：上传文档时提示超时或失败

**检查**：
```bash
# 1. 检查 uploads 目录权限
ls -la uploads/

# 2. 检查磁盘空间
df -h

# 3. 查看 API 日志
docker compose logs api | grep upload
```

## 🔄 更新部署

### 更新代码
```bash
# 1. 拉取最新代码
git pull

# 2. 重新构建并启动
docker compose up -d --build

# 3. 查看更新日志
docker compose logs -f
```

### 数据保留
以下数据会持久化保存，更新不会丢失：
- ✅ 数据库数据 (`mysql_data` volume)
- ✅ ElasticSearch 索引 (`es_data` volume)
- ✅ Redis 数据 (`redis_data` volume)
- ✅ 上传的文件 (`./uploads` 目录)

## 🛑 停止服务

```bash
# 停止所有服务（保留数据）
docker compose stop

# 停止并删除容器（保留数据）
docker compose down

# 停止并删除所有数据（危险操作！）
docker compose down -v
```

## 📊 服务监控

### 查看服务状态
```bash
# 查看所有服务
docker compose ps

# 查看资源使用
docker stats

# 查看日志
docker compose logs -f [service_name]
```

### 健康检查端点
```bash
# API 健康检查
curl http://localhost/health

# Nginx 健康检查
curl http://localhost/api/health

# 数据库连接检查
docker compose exec api python -c "from dataflow.database import engine; print(engine.url)"
```

## 🎯 生产环境优化

### 1. 修改默认密码
编辑 `.env`，修改数据库密码：
```bash
MYSQL_ROOT_PASSWORD=your_strong_password_here
MYSQL_PASSWORD=your_strong_password_here
```

### 2. 配置 HTTPS
参考 [SSL 配置文档](./03-ssl-setup.md)

### 3. 备份数据
参考 [运维管理文档](./04-maintenance.md#数据备份)

### 4. 配置日志轮转
```bash
# Docker 日志配置
sudo vim /etc/docker/daemon.json

# 添加：
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}

# 重启 Docker
sudo systemctl restart docker
```

### 5. 性能调优
根据服务器配置调整 `docker-compose.yml`：
```yaml
# ElasticSearch 内存
ES_JAVA_OPTS=-Xms1g -Xmx1g  # 生产环境建议 2-4GB

# MySQL 配置
command: |
  --max_connections=200
  --innodb_buffer_pool_size=2G
```

## 📚 下一步

- **[SSL 配置 →](./03-ssl-setup.md)** - 配置 HTTPS 加密
- **[运维管理 →](./04-maintenance.md)** - 日志、备份、监控

## 🆘 获取帮助

如遇到问题：
1. 查看日志：`docker compose logs -f`
2. 检查文档：[故障排查](./04-maintenance.md#故障排查)
3. 提交 Issue：GitHub Issues
