#!/usr/bin/env python3
"""
MySQL 连接测试脚本
测试数据库连接并诊断认证问题
"""

import pymysql
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 从环境变量获取配置
MYSQL_HOST = os.getenv('MYSQL_HOST', 'host.docker.internal')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
MYSQL_USER = os.getenv('MYSQL_USER', 'dataflow')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'dataflow_pass')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'dataflow')

print("=" * 60)
print("MySQL 连接测试")
print("=" * 60)
print(f"主机: {MYSQL_HOST}")
print(f"端口: {MYSQL_PORT}")
print(f"用户: {MYSQL_USER}")
print(f"数据库: {MYSQL_DATABASE}")
print("=" * 60)

try:
    # 尝试连接
    print("\n正在连接 MySQL...")
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

    print("✅ 连接成功!")

    # 查询用户信息
    with connection.cursor() as cursor:
        cursor.execute("SELECT USER(), DATABASE(), VERSION()")
        result = cursor.fetchone()
        print(f"\n当前用户: {result['USER()']}")
        print(f"当前数据库: {result['DATABASE()']}")
        print(f"MySQL 版本: {result['VERSION()']}")

        # 检查认证插件
        cursor.execute(f"SELECT user, host, plugin FROM mysql.user WHERE user='{MYSQL_USER}'")
        user_info = cursor.fetchone()
        if user_info:
            print(f"\n认证插件信息:")
            print(f"  用户: {user_info['user']}")
            print(f"  主机: {user_info['host']}")
            print(f"  认证插件: {user_info['plugin']}")

            if user_info['plugin'] == 'mysql_native_password':
                print("  ✅ 认证插件正确")
            else:
                print(f"  ⚠️  认证插件应该是 'mysql_native_password',当前是 '{user_info['plugin']}'")
                print("\n修复建议:")
                print(f"  执行以下 SQL:")
                print(f"  ALTER USER '{MYSQL_USER}'@'{user_info['host']}' IDENTIFIED WITH mysql_native_password BY '{MYSQL_PASSWORD}';")
                print(f"  FLUSH PRIVILEGES;")

    connection.close()
    print("\n✅ 测试完成,连接已关闭")

except pymysql.err.OperationalError as e:
    print(f"\n❌ 连接失败: {e}")

    if "Plugin 'mysql_native_password' is not loaded" in str(e):
        print("\n📌 问题诊断: mysql_native_password 插件未加载")
        print("\n修复方案:")
        print("\n1. 使用 root 用户连接 MySQL:")
        print(f"   mysql -h {MYSQL_HOST} -P {MYSQL_PORT} -u root -p")
        print("\n2. 执行以下 SQL 命令:")
        print(f"   ALTER USER '{MYSQL_USER}'@'%' IDENTIFIED WITH mysql_native_password BY '{MYSQL_PASSWORD}';")
        print(f"   FLUSH PRIVILEGES;")
        print("\n3. 如果用户不存在,先创建:")
        print(f"   CREATE USER '{MYSQL_USER}'@'%' IDENTIFIED WITH mysql_native_password BY '{MYSQL_PASSWORD}';")
        print(f"   GRANT ALL PRIVILEGES ON {MYSQL_DATABASE}.* TO '{MYSQL_USER}'@'%';")
        print(f"   FLUSH PRIVILEGES;")
    elif "Can't connect" in str(e):
        print("\n📌 问题诊断: 无法连接到 MySQL 服务器")
        print(f"\n请检查:")
        print(f"  1. MySQL 服务是否运行")
        print(f"  2. 主机地址 {MYSQL_HOST} 是否正确")
        print(f"  3. 端口 {MYSQL_PORT} 是否正确")
        print(f"  4. 防火墙是否允许连接")

except Exception as e:
    print(f"\n❌ 发生错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
