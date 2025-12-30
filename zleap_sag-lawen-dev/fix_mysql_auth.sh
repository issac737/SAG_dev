#!/bin/bash
# MySQL 认证插件修复脚本

echo "====================================="
echo "MySQL 认证插件修复脚本"
echo "====================================="

# 查找 MySQL 容器
MYSQL_CONTAINER=$(docker ps --format "{{.Names}}" | grep -i mysql | head -n 1)

if [ -z "$MYSQL_CONTAINER" ]; then
    echo "❌ 未找到运行中的 MySQL 容器"
    echo ""
    echo "请手动连接到 MySQL 并执行以下命令:"
    echo ""
    echo "  mysql -h host.docker.internal -u root -p"
    echo ""
    echo "然后执行:"
    echo "  ALTER USER 'dataflow'@'%' IDENTIFIED WITH mysql_native_password BY 'dataflow_pass';"
    echo "  FLUSH PRIVILEGES;"
    exit 1
fi

echo "找到 MySQL 容器: $MYSQL_CONTAINER"
echo ""
echo "请输入 MySQL root 密码:"
read -s ROOT_PASSWORD

echo ""
echo "正在修复认证插件..."

# 执行修复 SQL
docker exec -i $MYSQL_CONTAINER mysql -u root -p"$ROOT_PASSWORD" <<EOF
-- 检查用户
SELECT user, host, plugin FROM mysql.user WHERE user='dataflow';

-- 修改认证方式
ALTER USER 'dataflow'@'%' IDENTIFIED WITH mysql_native_password BY 'dataflow_pass';

-- 如果不存在则创建
CREATE USER IF NOT EXISTS 'dataflow'@'%' IDENTIFIED WITH mysql_native_password BY 'dataflow_pass';
GRANT ALL PRIVILEGES ON dataflow.* TO 'dataflow'@'%';

-- 刷新权限
FLUSH PRIVILEGES;

-- 验证
SELECT '✅ 修复完成' AS status;
SELECT user, host, plugin FROM mysql.user WHERE user='dataflow';
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 修复成功!"
    echo ""
    echo "现在可以重新运行你的命令了:"
    echo "  python dataflow/evaluation/benchmark.py --foundation search --dataset hotpotqa --bench-size 10 --enable-qa"
else
    echo ""
    echo "❌ 修复失败,请检查 root 密码是否正确"
fi
