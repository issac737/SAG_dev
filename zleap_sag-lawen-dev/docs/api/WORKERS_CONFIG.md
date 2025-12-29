# API Workers 配置说明

## 概述

DataFlow API 支持根据环境自动选择单/多 worker 模式：
- **本地开发（macOS）**：单 worker，支持热重载
- **服务器生产（Linux）**：多 worker，充分利用 CPU

## 配置方式

### 环境变量

- `API_WORKERS`: Worker 进程数量
  - `1`: 单 worker 模式（开发环境）
  - `> 1`: 多 worker 模式（生产环境）

### 默认配置

| 环境 | 配置文件 | Workers | 说明 |
|------|---------|---------|------|
| 本地开发 | `docker-compose.yml` | 1 | 避免 macOS Docker 端口转发问题 |
| 服务器生产 | `docker-compose.all.yml` | 4 | 默认 4 workers，可通过环境变量覆盖 |
| HTTPS 生产 | `docker-compose.https.yml` | 4 | 默认 4 workers，可通过环境变量覆盖 |

## 使用方式

### 本地开发

```bash
# 使用默认配置（单 worker）
docker compose up -d

# 查看启动日志
docker logs dataflow_api
# 输出：
# 🔧 Uvicorn 配置:
#    Host: 0.0.0.0
#    Port: 8000
#    Workers: 1
# 🚀 启动开发模式 (单 worker, 热重载)...
```

### 服务器部署

#### 使用默认 4 workers

```bash
docker compose -f docker-compose.https.yml up -d
```

#### 自定义 workers 数量

**方法 1 - 环境变量**：
```bash
# 启动时指定
API_WORKERS=8 docker compose -f docker-compose.https.yml up -d
```

**方法 2 - .env 文件**：
```bash
# 在项目根目录创建/编辑 .env 文件
echo "API_WORKERS=8" >> .env

# 启动服务
docker compose -f docker-compose.https.yml up -d
```

**方法 3 - 修改 docker-compose 文件**：
```yaml
environment:
  - API_WORKERS=8  # 直接写死
```

## Workers 数量建议

### 计算公式

```
推荐 Workers = (CPU 核心数 × 2) + 1
```

### 参考表

| CPU 核心数 | 推荐 Workers | 说明 |
|-----------|-------------|------|
| 1 核 | 1-2 | 小型服务 |
| 2 核 | 2-4 | 轻量级部署 |
| 4 核 | 4-8 | 中型服务 |
| 8 核 | 8-16 | 大型服务 |
| 16 核+ | 16-32 | 高性能服务 |

### 性能考虑

- **I/O 密集型**（数据库查询、API 调用）：`CPU × 2 + 1`
- **CPU 密集型**（数据处理、计算）：`CPU × 1`
- **混合负载**：`CPU × 1.5`

## 特性对比

| 特性 | 单 Worker | 多 Worker |
|------|-----------|-----------|
| **并发处理** | 数百个连接 | 数千个连接 |
| **CPU 利用** | 单核 | 多核 |
| **内存占用** | 低 | 高（每个 worker 独立进程） |
| **热重载** | ✅ 支持 | ❌ 不支持 |
| **启动速度** | 快 | 慢（需启动多个进程） |
| **故障隔离** | ❌ 单点故障 | ✅ Worker 间隔离 |
| **适用场景** | 开发、小型部署 | 生产、高并发 |

## 监控与调优

### 查看 Worker 状态

```bash
# 查看进程
docker exec dataflow_api ps aux | grep uvicorn

# 查看日志
docker logs -f dataflow_api
```

### 性能指标

观察以下指标来调整 workers 数量：

1. **CPU 使用率**
   - < 50%: 可能 workers 过多，浪费资源
   - > 80%: workers 不足，需要增加

2. **响应时间**
   - 响应时间持续增加：需要更多 workers
   - 响应时间稳定：配置合理

3. **内存使用**
   - 每个 worker 约占用 100-200MB
   - 确保总内存不超过系统的 80%

## 故障排查

### macOS 本地无法访问 API

**症状**：`curl: (56) Recv failure: Connection reset by peer`

**原因**：macOS Docker Desktop 的多 worker 端口转发问题

**解决**：确保 `docker-compose.yml` 中 `API_WORKERS=1`

### 服务器性能不佳

**症状**：请求排队、响应慢

**解决**：
1. 增加 workers 数量
2. 检查 CPU 和内存资源
3. 优化数据库连接池

### Worker 崩溃

**症状**：日志显示 worker 进程退出

**解决**：
1. 检查内存是否充足
2. 查看详细错误日志
3. 考虑减少 workers 数量

## 最佳实践

1. **开发环境**：始终使用单 worker
2. **测试环境**：使用 2-4 workers 进行压力测试
3. **生产环境**：根据 CPU 核心数调整
4. **监控告警**：设置 CPU、内存、响应时间告警
5. **逐步调整**：从保守配置开始，根据监控数据逐步优化

