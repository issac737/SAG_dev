# DataFlow 部署指南

**数据流智能引擎 - 部署指南**

*by Zleap Team（智跃团队）*

---

## 1. 部署方式

| 方式               | 优点               | 缺点         | 适用场景  |
| ------------------ | ------------------ | ------------ | --------- |
| **Docker Compose** | 简单快速           | 单机部署     | 开发/测试 |
| **Kubernetes**     | 自动扩缩容、高可用 | 复杂度高     | 生产环境  |
| **本地开发**       | 灵活调试           | 依赖管理复杂 | 开发环境  |

---

## 2. Docker Compose 部署（推荐）

### 2.1 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- 至少 4GB 可用内存

### 2.2 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/zleap-team/dataflow.git
cd dataflow

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入配置

# 3. 启动所有服务
docker-compose up -d

# 4. 初始化数据库
docker-compose exec api python scripts/init_database.py
docker-compose exec api python scripts/init_elasticsearch.py

# 5. 查看日志
docker-compose logs -f api

# 6. 验证部署
curl http://localhost:8000/health
```

### 2.3 核心配置文件

**docker-compose.yml** (精简版):

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    ports:
      - "${MYSQL_PORT}:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    ports:
      - "${ES_PORT}:9200"
    volumes:
      - es_data:/usr/share/elasticsearch/data

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports:
      - "${REDIS_PORT}:6379"
    volumes:
      - redis_data:/data

  api:
    build: .
    environment:
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=${MYSQL_USER}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD}
      - MYSQL_DATABASE=${MYSQL_DATABASE}
      - ES_HOSTS=http://elasticsearch:9200
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - LLM_PROVIDER=${LLM_PROVIDER}
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_MODEL=${LLM_MODEL}
    ports:
      - "${API_PORT}:8000"
    depends_on:
      mysql:
        condition: service_healthy
      elasticsearch:
        condition: service_started
      redis:
        condition: service_started
    command: uvicorn dataflow.api.main:app --host 0.0.0.0 --port 8000

volumes:
  mysql_data:
  es_data:
  redis_data:
```

**Dockerfile**:

```dockerfile
FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y curl build-essential && rm -rf /var/lib/apt/lists/*

# 安装uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY pyproject.toml requirements.txt ./

# 安装Python依赖
RUN uv pip install --system -r requirements.txt

# 复制项目文件
COPY . .

# 安装项目
RUN uv pip install --system -e .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "dataflow.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**.env.example**:

```ini
# MySQL配置
MYSQL_ROOT_PASSWORD=strong_root_password
MYSQL_DATABASE=dataflow
MYSQL_USER=dataflow
MYSQL_PASSWORD=strong_password
MYSQL_PORT=3306

# Elasticsearch配置
ES_PORT=9200

# Redis配置
REDIS_PORT=6379
REDIS_PASSWORD=strong_redis_password

# API配置
API_PORT=8000

# LLM配置
LLM_PROVIDER=openai
LLM_API_KEY=sk-xxx
LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507
```

### 2.4 常用命令

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 查看日志
docker-compose logs -f [service_name]

# 重启服务
docker-compose restart [service_name]

# 查看服务状态
docker-compose ps

# 进入容器
docker-compose exec [service_name] bash

# 查看资源使用
docker stats
```

---

## 3. UV 包管理器

### 3.1 UV 简介

**UV** 是由 Astral 团队开发的超快速 Python 包管理器和项目管理工具，使用 Rust 编写。

### 3.3 UV 核心命令

#### 虚拟环境管理

```bash
# 创建虚拟环境
uv venv                    # 创建 .venv 目录
uv venv myenv              # 创建指定名称的虚拟环境
uv venv --python 3.11      # 指定 Python 版本

# 激活虚拟环境
source .venv/bin/activate           # macOS/Linux
.venv\Scripts\activate              # Windows PowerShell
.venv\Scripts\activate.bat          # Windows CMD

# 停用虚拟环境
deactivate
```

#### 依赖安装

```bash
# 安装单个包
uv pip install requests
uv pip install "fastapi>=0.100.0"

# 从 requirements.txt 安装
uv pip install -r requirements.txt

# 从 pyproject.toml 安装
uv pip install -e .                 # 开发模式安装
uv pip install -e ".[dev]"          # 安装开发依赖
uv pip install -e ".[dev,test]"     # 安装多个可选依赖

# 使用 uv sync（推荐）
uv sync                    # 同步 pyproject.toml 的所有依赖
uv sync --all-extras       # 同步所有可选依赖
```

#### 依赖管理

```bash
# 列出已安装的包
uv pip list
uv pip list --format=json

# 显示包信息
uv pip show requests

# 冻结依赖
uv pip freeze > requirements.txt

# 卸载包
uv pip uninstall requests
uv pip uninstall -r requirements.txt

# 升级包
uv pip install --upgrade requests
uv pip install --upgrade-package requests
```

#### 项目初始化

```bash
# 初始化新项目
uv init myproject
cd myproject

# 添加依赖
uv add fastapi
uv add --dev pytest

# 移除依赖
uv remove fastapi
```

### 3.4 UV 最佳实践

#### 1. 使用 uv sync 管理依赖

```bash
# 不要使用
uv pip install -e ".[dev]"

# 推荐使用
uv sync --all-extras
```

优势：
- 自动生成 `uv.lock` 锁文件
- 确保所有环境依赖一致
- 更快的依赖解析

#### 2. 项目开发工作流

```bash
# 1. 克隆项目
git clone https://github.com/zleap-team/dataflow.git
cd dataflow

# 2. 创建虚拟环境
uv venv

# 3. 激活虚拟环境
source .venv/bin/activate  # macOS/Linux

# 4. 同步所有依赖（包括dev和api）
uv sync --all-extras

# 5. 运行应用
python -m dataflow
```

#### 3. 依赖锁定

```bash
# 生成锁文件
uv sync  # 自动生成 uv.lock

# 从锁文件安装（CI/CD）
uv sync --frozen  # 不更新 uv.lock
```

#### 4. 与 Docker 集成

**Dockerfile 优化**:

```dockerfile
FROM python:3.11-slim

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY pyproject.toml uv.lock* ./

# 安装依赖（使用 uv 的系统模式）
RUN uv pip install --system -e ".[api]"

# 复制项目文件
COPY . .

CMD ["uvicorn", "dataflow.api.main:app", "--host", "0.0.0.0"]
```

---

## 4. 本地开发环境

### 4.1 完整开发环境搭建

```bash
# 1. 安装 UV（参考 3.2 节）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 克隆项目
git clone https://github.com/zleap-team/dataflow.git
cd dataflow

# 3. 创建虚拟环境
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 4. 同步所有依赖（推荐方式）
uv sync --all-extras

# 或者使用传统方式
# uv pip install -e ".[dev,api]"

# 5. 配置环境变量
cp .env.example .env
# 编辑 .env 填入配置

# 6. 启动依赖服务（MySQL, ES, Redis）
docker-compose up -d mysql elasticsearch redis

# 7. 等待服务启动（约30秒）
sleep 30

# 8. 初始化数据库
python scripts/init_database.py
python scripts/init_elasticsearch.py

# 9. 运行应用
uvicorn dataflow.api.main:app --reload --host 0.0.0.0 --port 8000

# 10. 验证服务
curl http://localhost:8000/health
```

### 4.2 开发命令速查

```bash
# 依赖管理
uv sync                          # 同步依赖
uv pip list                      # 列出已安装的包
uv pip install package_name      # 安装新包

# 代码质量
black dataflow/                 # 代码格式化
ruff check dataflow/            # 代码检查
mypy dataflow/                  # 类型检查
pytest                           # 运行测试

# 服务管理
docker-compose up -d             # 启动依赖服务
docker-compose logs -f api       # 查看API日志
docker-compose restart api       # 重启API服务
docker-compose down              # 停止所有服务

# 数据库操作
python scripts/init_database.py    # 初始化MySQL
python scripts/init_elasticsearch.py  # 初始化ES
python scripts/migrate.py          # 数据库迁移
```

---

## 5. 配置管理

### 5.1 环境配置优先级

```
环境变量 > .env文件 > 默认配置
```

### 5.2 多环境配置

```bash
# 开发环境
cp .env.development .env

# 生产环境
cp .env.production .env
```

**.env.production** 示例:

```ini
DEBUG=false
LOG_LEVEL=INFO
MYSQL_HOST=mysql-prod.example.com
LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507

# 生产环境安全配置
MYSQL_PASSWORD=<strong_password>
REDIS_PASSWORD=<strong_password>
```

---

## 6. 监控与日志

### 6.1 日志管理

```bash
# 查看API日志
docker-compose logs -f api

# 查看MySQL日志
docker-compose logs -f mysql

# 查看所有服务日志
docker-compose logs -f
```

### 6.2 健康检查

```bash
# API健康检查
curl http://localhost:8000/health

# MySQL健康检查
docker-compose exec mysql mysqladmin ping -h localhost

# Elasticsearch健康检查
curl http://localhost:9200/_cluster/health?pretty

# Redis健康检查
docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} ping
```

### 6.3 性能监控（可选）

**使用 Prometheus + Grafana**:

```yaml
# docker-compose.yml 添加
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
```

---

## 7. 数据备份与恢复

### 7.1 MySQL 备份

```bash
# 备份
docker-compose exec mysql mysqldump -uroot -p${MYSQL_ROOT_PASSWORD} dataflow > backup_$(date +%Y%m%d).sql

# 恢复
docker-compose exec -T mysql mysql -uroot -p${MYSQL_ROOT_PASSWORD} dataflow < backup_20240101.sql
```

### 7.2 Elasticsearch 快照

```bash
# 创建快照
curl -X PUT "localhost:9200/_snapshot/my_backup/snapshot_$(date +%Y%m%d)"

# 恢复快照
curl -X POST "localhost:9200/_snapshot/my_backup/snapshot_20240101/_restore"
```

---

## 8. 故障排查

### 8.1 常见问题

| 问题               | 排查步骤                                               | 解决方案      |
| ------------------ | ------------------------------------------------------ | ------------- |
| **API无响应**      | 1. `docker-compose ps`<br>2. `docker-compose logs api` | 重启服务      |
| **数据库连接失败** | 1. 检查MySQL容器<br>2. 检查配置                        | 修复配置/重启 |
| **ES索引错误**     | `curl localhost:9200/_cat/indices`                     | 重建索引      |
| **内存不足**       | `docker stats`                                         | 增加资源限制  |

### 8.2 诊断命令

```bash
# 查看容器资源使用
docker stats

# 查看容器日志
docker-compose logs -f [service_name]

# 进入容器调试
docker-compose exec [service_name] bash

# 检查网络连接
docker-compose exec api ping mysql
docker-compose exec api ping elasticsearch
```

---

## 9. 性能优化

### 9.1 数据库优化

```sql
-- 添加索引
CREATE INDEX idx_event_source_category ON source_event(source_config_id, category);
CREATE INDEX idx_entity_type_name ON entity(type, normalized_name(255));
```

### 9.2 缓存策略

| 数据类型 | 缓存时间 | Redis Key              |
| -------- | -------- | ---------------------- |
| 实体扩展 | 24小时   | `entity:expand:{name}` |
| LLM结果  | 7天      | `llm:summary:{hash}`   |
| 检索结果 | 1小时    | `search:{query_hash}`  |

### 9.3 并发配置

**连接池配置**:
```python
# dataflow/core/storage/mysql.py
engine = create_async_engine(
    database_url,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True
)
```

---

## 10. 生产环境清单

部署前检查:

- [ ] 配置文件已更新（生产环境配置）
- [ ] 数据库已初始化
- [ ] Elasticsearch索引已创建
- [ ] SSL证书已配置（HTTPS）
- [ ] 日志轮转已配置
- [ ] 备份策略已配置
- [ ] 防火墙规则已配置
- [ ] 性能测试已完成

---

## 11. 相关文档

- [系统架构设计](./architecture.md) - 分层架构与技术栈
- [开发指南](./development.md) - 本地开发环境搭建
