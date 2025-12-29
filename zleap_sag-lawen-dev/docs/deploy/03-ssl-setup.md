# SSL/HTTPS 配置指南

为 DataFlow 配置 HTTPS 加密访问。

## 📋 概览

DataFlow 支持自动检测 SSL 证书：
- ✅ **有证书**：自动启用 HTTPS，HTTP 重定向到 HTTPS
- ✅ **无证书**：使用 HTTP（适合开发/内网环境）

## 🔒 方式 1：使用现有证书（最简单）

如果你已有 SSL 证书（从云服务商、CA 机构购买），直接复制到项目：

```bash
# 进入项目目录
cd /path/to/dataflow

# 复制证书文件
cp /path/to/your/fullchain.pem certs/
cp /path/to/your/privkey.pem certs/

# 设置权限
chmod 644 certs/*.pem

# 重启服务
docker compose restart nginx
```

**注意事项**：
- 证书文件必须命名为 `fullchain.pem` 和 `privkey.pem`
- `fullchain.pem` 应包含完整证书链（服务器证书 + 中间证书）
- 证书域名必须与访问域名一致

### 验证证书
```bash
# 检查证书有效期
openssl x509 -in certs/fullchain.pem -noout -dates

# 检查证书域名
openssl x509 -in certs/fullchain.pem -noout -text | grep "Subject Alternative Name" -A1

# 检查私钥匹配
openssl x509 -noout -modulus -in certs/fullchain.pem | openssl md5
openssl rsa -noout -modulus -in certs/privkey.pem | openssl md5
# 两个 MD5 值应该相同
```

## 🆓 方式 2：Let's Encrypt 免费证书（推荐）

Let's Encrypt 提供免费的 DV（Domain Validation）证书，有效期 90 天，支持自动续期。

### 前提条件
- ✅ 拥有域名（如 `example.com`）
- ✅ 域名已解析到服务器 IP
- ✅ 服务器 80 端口可从公网访问

### 步骤 1：安装 Certbot
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y certbot

# CentOS/RHEL
sudo yum install -y certbot
```

### 步骤 2：临时停止服务

（Certbot 需要占用 80 端口进行验证）

```bash
cd /path/to/dataflow
docker compose stop nginx
```

### 步骤 3：获取证书
```bash
# 单域名证书
sudo certbot certonly --standalone -d your-domain.com

# 多域名证书（含 www）
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# 通配符证书（需要 DNS验证，稍复杂）
sudo certbot certonly --manual --preferred-challenges dns -d *.your-domain.com
```

**交互提示**：
1. 输入邮箱（用于证书过期提醒）
2. 同意服务条款（输入 `Y`）
3. 是否分享邮箱（可选，输入 `N`）

### 步骤 4：复制证书到项目
```bash
# 查找证书位置
sudo ls /etc/letsencrypt/live/

# 复制证书（替换your-domain.com）
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem certs/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem certs/

# 修改权限（重要！）
sudo chown $USER:$USER certs/*.pem
chmod 644 certs/*.pem
```

### 步骤 5：启动服务
```bash
# 启动服务（自动检测证书并启用 HTTPS）
docker compose up -d

# 验证 HTTPS
curl -I https://your-domain.com/health
```

### 步骤 6：配置自动续期

Let's Encrypt 证书 90 天过期，需要自动续期：

```bash
# 创建续期脚本
cat > /usr/local/bin/dataflow-renew-cert.sh << 'EOF'
#!/bin/bash
set -e

# 证书路径
DOMAIN="your-domain.com"
PROJECT_DIR="/path/to/dataflow"
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"

# 续期证书
certbot renew --quiet

# 复制新证书
cp $CERT_DIR/fullchain.pem $PROJECT_DIR/certs/
cp $CERT_DIR/privkey.pem $PROJECT_DIR/certs/

# 重启 Nginx
cd $PROJECT_DIR
docker compose restart nginx

echo "证书已更新: $(date)"
EOF

# 设置执行权限
sudo chmod +x /usr/local/bin/dataflow-renew-cert.sh

# 替换实际域名和路径
sudo sed -i 's/your-domain.com/your-actual-domain.com/g' /usr/local/bin/dataflow-renew-cert.sh
sudo sed -i 's|/path/to/dataflow|/actual/path/to/dataflow|g' /usr/local/bin/dataflow-renew-cert.sh
```

**配置定时任务**：
```bash
# 编辑 crontab
sudo crontab -e

# 添加以下行（每天凌晨 3 点检查续期）
0 3 * * * /usr/local/bin/dataflow-renew-cert.sh >> /var/log/dataflow-cert-renew.log 2>&1
```

### 测试续期
```bash
# 测试续期（不会实际续期）
sudo certbot renew --dry-run

# 手动执行续期脚本
sudo /usr/local/bin/dataflow-renew-cert.sh
```

## 🌐 方式 3：云服务商证书

### 阿里云 SSL 证书
1. 登录阿里云控制台 → SSL 证书
2. 购买免费 DV 证书（或付费证书）
3. 填写域名并完成验证
4. 下载证书（选择 Nginx 格式）
5. 解压获得 `.pem` 和 `.key` 文件
6. 复制到项目 `certs/` 目录（重命名为 `fullchain.pem` 和 `privkey.pem`）

### 腾讯云 SSL 证书
1. 登录腾讯云控制台 → SSL 证书管理
2. 申请免费证书
3. 完成域名验证
4. 下载证书（Nginx 格式）
5. 复制到项目 `certs/` 目录

### Cloudflare SSL
如果使用 Cloudflare CDN：
1. Cloudflare → SSL/TLS → 源服务器
2. 创建源服务器证书
3. 选择 15 年有效期
4. 保存证书和私钥
5. 复制到项目 `certs/` 目录

**Cloudflare SSL 模式**：
- **灵活（Flexible）**：浏览器到 CF 加密，CF 到源站不加密（不推荐）
- **完全（Full）**：端到端加密，可用自签名证书
- **完全（严格）Full (Strict)**：端到端加密，需 CA 签名证书（推荐）

## 🔄 证书更新流程

### 手动更新
```bash
# 1. 备份旧证书
cp certs/fullchain.pem certs/fullchain.pem.bak
cp certs/privkey.pem certs/privkey.pem.bak

# 2. 替换新证书
cp /path/to/new/fullchain.pem certs/
cp /path/to/new/privkey.pem certs/

# 3. 重启 Nginx
docker compose restart nginx

# 4. 验证
curl -I https://your-domain.com/health
```

### 自动更新（Let's Encrypt）
已在"方式 2"中配置，无需手动操作。

## 🔍 验证 HTTPS 配置

### 检查证书状态
```bash
# 检查证书有效期
openssl s_client -connect your-domain.com:443 -servername your-domain.com < /dev/null 2>/dev/null | openssl x509 -noout -dates

# 检查证书链
openssl s_client -connect your-domain.com:443 -servername your-domain.com < /dev/null 2>/dev/null | openssl x509 -noout -text
```

### 浏览器测试
访问 `https://your-domain.com`：
- ✅ 浏览器地址栏显示锁图标
- ✅ 点击锁图标可查看证书信息
- ✅ HTTP 自动重定向到 HTTPS

### SSL Labs 测试
访问 https://www.ssllabs.com/ssltest/ 输入你的域名进行全面测试。

**期望评级**：A 或 A+

## ⚠️ 常见问题

### 1. 证书不受信任

**问题**：浏览器提示"您的连接不是私密连接"

**原因**：
- 证书链不完整
- 使用自签名证书
- 证书域名不匹配

**解决**：
```bash
# 检查证书链
openssl s_client -connect localhost:443 -servername your-domain.com < /dev/null

# 确保使用 fullchain.pem（含中间证书）
# 不要使用 cert.pem（只含服务器证书）
```

### 2. Nginx 无法启动

**问题**：`docker compose logs nginx` 显示证书错误

**解决**：
```bash
# 检查证书文件是否存在
ls -lh certs/

# 检查证书格式
file certs/fullchain.pem  # 应显示 "PEM certificate"
file certs/privkey.pem    # 应显示 "PEM RSA private key"

# 检查权限
chmod 644 certs/*.pem
```

### 3. HTTP 没有重定向到 HTTPS

**问题**：访问 `http://domain.com` 不会跳转到 HTTPS

**原因**：Nginx 配置中的重定向规则未生效

**解决**：
检查 `nginx/nginx.conf` 是否包含重定向配置：
```nginx
# 在 HTTP server 块中应有：
if ($ssl_protocol = "") {
    return 301 https://$host$request_uri;
}
```

### 4. 证书即将过期

**问题**：证书还有 30 天过期

**解决**：
```bash
# Let's Encrypt 手动续期
sudo certbot renew --force-renewal

# 复制新证书
sudo cp /etc/letsencrypt/live/your-domain.com/*.pem /path/to/dataflow/certs/

# 重启服务
cd /path/to/dataflow
docker compose restart nginx
```

### 5. Mixed Content 警告

**问题**：HTTPS 页面加载HTTP 资源被阻止

**解决**：
- 确保所有资源（图片、CSS、JS）使用 HTTPS
- 检查 API 请求是否使用相对路径
- 使用 `<meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">`

## 📚 证书管理最佳实践

### 1. 监控证书过期
```bash
# 添加监控脚本
cat > /usr/local/bin/check-cert-expiry.sh << 'EOF'
#!/bin/bash
DOMAIN="your-domain.com"
DAYS=30

expiry=$(openssl s_client -connect $DOMAIN:443 -servername $DOMAIN < /dev/null 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2)
expiry_epoch=$(date -d "$expiry" +%s)
current_epoch=$(date +%s)
days_left=$(( ($expiry_epoch - $current_epoch) / 86400 ))

if [ $days_left -lt $DAYS ]; then
    echo "警告：证书将在 $days_left 天后过期！"
    # 可添加告警通知（邮件/钉钉/飞书等）
fi
EOF

chmod +x /usr/local/bin/check-cert-expiry.sh

# 每天检查
echo "0 9 * * * /usr/local/bin/check-cert-expiry.sh" | crontab -
```

### 2. 备份证书
```bash
# 定期备份证书和私钥
mkdir -p ~/cert-backups
cp certs/*.pem ~/cert-backups/cert-$(date +%Y%m%d).tar.gz
```

### 3. 使用强加密套件
已在 `nginx/nginx.conf` 中配置：
- TLS 1.2 和 1.3
- 现代加密套件
- HSTS 启用

## 🎯 下一步

HTTPS 配置完成后：
- **[运维管理 →](./04-maintenance.md)** - 日志查看、监控、备份

## 🔗 参考资源

- Let's Encrypt: https://letsencrypt.org/
- SSL Labs: https://www.ssllabs.com/ssltest/
- Mozilla SSL Configuration: https://ssl-config.mozilla.org/
