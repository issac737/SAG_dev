# 运维管理指南

DataFlow 的日常运维、监控和故障排查指南。

## 📊 服务管理

### 查看服务状态
```bash
# 查看所有服务
docker compose ps

# 查看资源使用
docker stats

# 查看特定服务
docker compose ps api
```

### 启停服务
```bash
# 启动所有服务
docker compose up -d

# 停止所有服务
docker compose stop

# 重启特定服务
docker compose restart api
docker compose restart nginx

# 重启所有服务
docker compose restart
```

### 更新部署
```bash
# 方式 1：使用脚本
git pull
./scripts/deploy.sh

# 方式 2：手动更新
git pull
docker compose build
docker compose up -d

# 查看更新日志
docker compose logs -f
```

## 📝 日志管理

### 查看日志
```bash
# 实时查看所有日志
docker compose logs -f

# 查看特定服务日志
docker compose logs -f api
docker compose logs -f web
docker compose logs -f nginx

# 查看最近 100 行
docker compose logs --tail=100 api

# 查看指定时间范围
docker compose logs --since="2024-01-01T00:00:00" api
```

### 导出日志
```bash
# 导出到文件
docker compose logs api > api-logs-$(date +%Y%m%d).log

# 压缩保存
docker compose logs api | gzip > api-logs-$(date +%Y%m%d).log.gz
```

### 日志轮转（防止日志占满磁盘）
编辑 `/etc/docker/daemon.json`：
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

重启 Docker：
```bash
sudo systemctl restart docker
docker compose up -d
```

## 💾 数据备份

### MySQL 备份
```bash
# 完整备份
docker compose exec mysql mysqldump -u root -pdataflow_root --all-databases > backup-$(date +%Y%m%d).sql

# 压缩备份
docker compose exec mysql mysqldump -u root -pdataflow_root --all-databases | gzip > backup-$(date +%Y%m%d).sql.gz

# 只备份 dataflow 数据库
docker compose exec mysql mysqldump -u root -pdataflow_root dataflow > dataflow-$(date +%Y%m%d).sql
```

### 恢复 MySQL
```bash
# 从备份恢复
cat backup-20240101.sql | docker compose exec -T mysql mysql -u root -pdataflow_root

# 从压缩备份恢复
gunzip < backup-20240101.sql.gz | docker compose exec -T mysql mysql -u root -pdataflow_root
```

### ElasticSearch 备份
```bash
# 创建快照仓库
docker compose exec api python << 'EOF'
from dataflow.database.elasticsearch import es_client
es_client.snapshot.create_repository(
    name="backup_repo",
    body={"type": "fs", "settings": {"location": "/usr/share/elasticsearch/backups"}}
)
EOF

# 创建快照
docker compose exec api python << 'EOF'
from dataflow.database.elasticsearch import es_client
es_client.snapshot.create(repository="backup_repo", snapshot="snapshot_$(date +%Y%m%d)")
EOF
```

### 文件备份
```bash
# 备份上传的文件
tar -czf uploads-$(date +%Y%m%d).tar.gz uploads/

# 备份配置文件
tar -czf config-$(date +%Y%m%d).tar.gz .env docker-compose.yml nginx/
```

### 自动备份脚本
```bash
# 创建备份脚本
cat > /usr/local/bin/dataflow-backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backup/dataflow"
DATE=$(date +%Y%m%d)

mkdir -p $BACKUP_DIR

# 备份MySQL
docker compose -f /path/to/dataflow/docker-compose.yml exec -T mysql \
    mysqldump -u root -pdataflow_root --all-databases | \
    gzip > $BACKUP_DIR/mysql-$DATE.sql.gz

# 备份uploads
tar -czf $BACKUP_DIR/uploads-$DATE.tar.gz -C /path/to/dataflow uploads/

# 清理7天前的备份
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete

echo "备份完成: $DATE"
EOF

chmod +x /usr/local/bin/dataflow-backup.sh

# 每天凌晨2点自动备份
(crontab -l; echo "0 2 * * * /usr/local/bin/dataflow-backup.sh") | crontab -
```

## 🔍 监控与健康检查

### 健康检查端点
```bash
# API 健康检查
curl http://localhost/health
# 预期: {"status": "healthy"}

# 检查所有服务健康状态
docker compose ps
# 所有服务应显示 "(healthy)"
```

### 资源监控
```bash
# 实时监控
docker stats

# 磁盘使用
df -h

# 查看Docker占用
docker system df

# 内存使用
free -h

# 查看端口占用
sudo netstat -tlnp
```

### 性能监控（可选）
安装 Prometheus + Grafana 进行可视化监控（高级话题，参考官方文档）。

## 🔧 故障排查

### 问题 1：服务无法启动

**症状**：`docker compose ps` 显示服务 `Exited`

**排查步骤**：
```bash
# 1. 查看日志
docker compose logs [service-name]

# 2. 检查端口占用
sudo netstat -tlnp | grep -E ':(80|443|3000|8000|3306|6379|9200)'

# 3. 检查磁盘空间
df -h

# 4. 检查内存
free -h

# 5. 重启服务
docker compose restart [service-name]
```

### 问题 2：API 502 Bad Gateway

**症状**：前端可访问，API 返回 502

**排查步骤**：
```bash
# 1. 检查 API 服务状态
docker compose ps api

# 2. 查看 API 日志
docker compose logs api

# 3. 检查 Nginx 配置
docker compose logs nginx

# 4. 测试直接访问（绕过 Nginx）
docker compose exec api curl http://localhost:8000/health

# 5. 重启服务
docker compose restart api nginx
```

### 问题 3：数据库连接失败

**症状**：`Can't connect to MySQL server`

**排查步骤**：
```bash
# 1. 检查 MySQL 服务
docker compose ps mysql

# 2. 查看MySQL 日志
docker compose logs mysql

# 3. 等待 MySQL 启动（首次启动需要1-2分钟）
docker compose logs -f mysql | grep "ready for connections"

# 4. 测试连接
docker compose exec api python -c "from dataflow.database import engine; print(engine.url)"

# 5. 重启 MySQL
docker compose restart mysql
```

### 问题 4：ElasticSearch 内存不足

**症状**：ES 日志显示 `OutOfMemoryError`

**解决方案**：
```bash
# 修改 docker-compose.yml
vim docker-compose.yml

# 找到 ES_JAVA_OPTS，修改为：
ES_JAVA_OPTS=-Xms256m -Xmx256m  # 降低内存使用

# 重启
docker compose up -d elasticsearch
```

### 问题 5：磁盘空间不足

**症状**：`No space left on device`

**解决方案**：
```bash
# 1. 查看磁盘使用
df -h

# 2. 清理 Docker
docker system prune -a --volumes

# 3. 清理日志
sudo journalctl --vacuum-time=7d

# 4. 清理旧备份
find /backup -name "*.gz" -mtime +30 -delete
```

### 问题 6：容器不断重启

**症状**：`docker compose ps` 显示 Restarting

**排查**：
```bash
# 查看重启日志
docker compose logs --tail=100 [service-name]

# 常见原因：
# - 配置错误（检查 .env）
# - 依赖服务未就绪（检查 depends_on）
# - 资源不足（检查 docker stats）
```

## 🔒 安全管理

### 修改默认密码
```bash
# 编辑 .env
vim .env

# 修改以下配置
MYSQL_ROOT_PASSWORD=your_strong_password
MYSQL_PASSWORD=your_strong_password

# 重新部署
docker compose up -d --force-recreate mysql
```

### 更新系统
```bash
# Ubuntu
sudo apt-get update && sudo apt-get upgrade -y

# 重启服务
sudo reboot
```

### 防火墙管理
```bash
# Ubuntu UFW
sudo ufw status
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# CentOS Firewalld
sudo firewall-cmd --list-all
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## 📈 性能优化

### 数据库优化
编辑 `docker-compose.yml`：
```yaml
mysql:
  command: |
    --max_connections=200
    --innodb_buffer_pool_size=1G
    --query_cache_size=64M
```

### ElasticSearch 优化
```yaml
elasticsearch:
  environment:
    - "ES_JAVA_OPTS=-Xms2g -Xmx2g"  # 生产环境建议 2-4GB
```

### Nginx 缓存
已在 `nginx/nginx.conf` 中配置静态资源缓存。

## 📞 常用命令速查

```bash
# 查看状态
docker compose ps
docker stats

# 查看日志
docker compose logs -f [service]

# 重启服务
docker compose restart [service]

# 备份数据库
docker compose exec mysql mysqldump -u root -pdataflow_root --all-databases > backup.sql

# 清理 Docker
docker system prune -a

# 查看磁盘
df -h

# 查看内存
free -h
```

## 🆘 获取帮助

遇到问题时：
1. 查看日志：`docker compose logs -f`
2. 检查本文档的故障排查章节
3. 搜索 GitHub Issues
4. 提交新 Issue（附上日志和环境信息）

## 📚 更多资源

- [Docker 官方文档](https://docs.docker.com/)
- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Nginx 文档](https://nginx.org/en/docs/)
