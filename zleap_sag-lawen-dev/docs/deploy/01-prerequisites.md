# 服务器准备

部署前的服务器配置和环境准备指南。

## 📋 服务器要求

### 最低配置
- **CPU**: 2核
- **内存**: 4GB
- **磁盘**: 20GB SSD
- **系统**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- **网络**: 公网 IP（如需外网访问）

### 推荐配置（生产环境）
- **CPU**: 4核+
- **内存**: 8GB+
- **磁盘**: 50GB+ SSD
- **系统**: Ubuntu 22.04 LTS
- **网络**: 固定公网 IP + 域名

## 🐳 安装 Docker

### Ubuntu/Debian
```bash
# 更新系统
sudo apt-get update
sudo apt-get upgrade -y

# 安装依赖
# 1. 卸载 Ubuntu 的 docker.io
  sudo apt-get remove docker.io containerd runc -y
  sudo apt-get autoremove -y

  # 2. 安装依赖
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg lsb-release

  # 3. 添加 Docker 官方 GPG 密钥
  sudo mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg
  --dearmor -o /etc/apt/keyrings/docker.gpg

  # 4. 添加 Docker 官方仓库
  echo \
    "deb [arch=$(dpkg --print-architecture)
  signed-by=/etc/apt/keyrings/docker.gpg]
  https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | sudo tee
  /etc/apt/sources.list.d/docker.list > /dev/null

  # 5. 安装 Docker + Compose V2
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io
  docker-compose-plugin

  # 6. 验证
  docker --version           # Docker version 27.x.x
  docker compose version     # Docker Compose version v2.x.x（注意是空格）

  # 7. 使用（注意是空格，不是连字符）
  docker compose up -d
  docker compose ps
  docker compose logs ersion
```

### CentOS/RHEL
```bash
# 安装依赖
sudo yum install -y yum-utils

# 添加 Docker 仓库
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 安装 Docker
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 启动 Docker
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
sudo docker --version
docker compose version
```

### 配置 Docker（可选但推荐）
```bash
# 将当前用户添加到 docker 组（避免每次使用 sudo）
sudo usermod -aG docker $USER

# 重新登录以使更改生效
exit
# 重新连接 SSH

# 验证无需 sudo 运行
docker ps
```

## 🔥 配置防火墙

### UFW (Ubuntu)
```bash
# 安装 UFW
sudo apt-get install -y ufw

# 允许 SSH（重要！避免锁定）
sudo ufw allow 22/tcp

# 允许 HTTP 和 HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 启用防火墙
sudo ufw enable

# 查看状态
sudo ufw status
```

### Firewalld (CentOS/RHEL)
```bash
# 启动防火墙
sudo systemctl start firewalld
sudo systemctl enable firewalld

# 允许 HTTP 和 HTTPS
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https

# 重新加载
sudo firewall-cmd --reload

# 查看状态
sudo firewall-cmd --list-all
```

##  🔑 配置 Git Deploy Key

如果需要从私有仓库拉取代码，配置 Deploy Key：

### 生成 SSH 密钥
```bash
# 生成新的 SSH 密钥
ssh-keygen -t ed25519 -C "deploy@dataflow" -f ~/.ssh/dataflow_deploy

# 查看公钥
cat ~/.ssh/dataflow_deploy.pub
```

### 添加到 GitHub/GitLab
1. 复制上面的公钥内容
2. 进入仓库设置 → Deploy Keys
3. 添加新的 Deploy Key
4. 粘贴公钥，勾选"只读"权限
5. 保存

### 配置 SSH
```bash
# 创建 SSH 配置
cat >> ~/.ssh/config << 'EOF'
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/dataflow_deploy
    StrictHostKeyChecking no
EOF

# 设置权限
chmod 600 ~/.ssh/config
chmod 600 ~/.ssh/dataflow_deploy

# 测试连接
ssh -T git@github.com
# 应该看到: Hi xxx! You've successfully authenticated...
```

## 📦 安装其他工具

### 必需工具
```bash
# Ubuntu/Debian
sudo apt-get install -y git curl wget vim

# CentOS/RHEL
sudo yum install -y git curl wget vim
```

### 可选工具（推荐）
```bash
# htop - 系统监控
sudo apt-get install -y htop  # Ubuntu
sudo yum install -y htop      # CentOS

# ncdu - 磁盘使用分析
sudo apt-get install -y ncdu  # Ubuntu
sudo yum install -y ncdu      # CentOS

# jq - JSON 处理
sudo apt-get install -y jq    # Ubuntu
sudo yum install -y jq        # CentOS
```

## 🌐 域名配置（如需 HTTPS）

### DNS 记录配置
在你的域名提供商（如阿里云、腾讯云、Cloudflare）添加 A 记录：

```
类型：A
主机记录：@ 或 www
记录值：你的服务器公网 IP
TTL：600
```

### 验证 DNS 生效
```bash
# 方式 1：ping
ping yourdomain.com

# 方式 2：nslookup
nslookup yourdomain.com

# 方式 3：dig
dig yourdomain.com
```

DNS 生效通常需要 5-30 分钟。

## ✅ 环境检查

运行以下命令检查环境：

```bash
# 检查 Docker
docker --version
docker compose version
docker ps

# 检查端口
sudo netstat -tlnp | grep -E ':(80|443|3306|6379|9200|8000|3000) '

# 检查磁盘空间
df -h

# 检查内存
free -h

# 检查 CPU
lscpu | grep -E "^CPU\(s\)|^Model name"
```

### 期望输出
```
✅ Docker version 24.0.0+
✅ Docker Compose version v2.20.0+
✅ 端口 80, 443 未被占用
✅ 磁盘可用空间 > 20GB
✅ 内存可用 > 2GB
```

## 🔒 安全加固（生产环境推荐）

### 1. 禁用 root SSH 登录
```bash
sudo vim /etc/ssh/sshd_config

# 修改以下配置
PermitRootLogin no
PasswordAuthentication no  # 仅允许密钥登录

# 重启 SSH
sudo systemctl restart sshd
```

### 2. 配置 fail2ban
```bash
# 安装 fail2ban
sudo apt-get install -y fail2ban  # Ubuntu
sudo yum install -y fail2ban      # CentOS

# 启动服务
sudo systemctl start fail2ban
sudo systemctl enable fail2ban
```

### 3. 定期更新系统
```bash
# Ubuntu
sudo apt-get update && sudo apt-get upgrade -y

# CentOS
sudo yum update -y
```

## 🆘 故障排查

### Docker 安装失败
```bash
# 卸载旧版本
sudo apt-get remove docker docker-engine docker.io containerd runc

# 清理残留
sudo rm -rf /var/lib/docker
sudo rm -rf /var/lib/containerd

# 重新安装
# （参考上面的安装步骤）
```

### 端口已被占用
```bash
# 查看占用进程
sudo lsof -i :80
sudo lsof -i :443

# 停止进程（如 Apache/Nginx）
sudo systemctl stop apache2
sudo systemctl stop nginx
```

### 磁盘空间不足
```bash
# 清理 Docker
docker system prune -a --volumes

# 清理系统缓存
sudo apt-get clean  # Ubuntu
sudo yum clean all  # CentOS
```

## 📝 检查清单

部署前确认：

- [ ] Docker 和 Docker Compose 已安装
- [ ] 防火墙已配置（80, 443 端口开放）
- [ ] 磁盘空间 ≥ 20GB
- [ ] 内存 ≥ 4GB
- [ ] Git 已安装并配置 SSH 密钥（如需）
- [ ] 域名已解析到服务器 IP（如需 HTTPS）
- [ ] 所有必需端口未被占用

## 🎯 下一步

环境准备完成后，继续：
- **[快速部署指南 →](./02-quick-deploy.md)**
