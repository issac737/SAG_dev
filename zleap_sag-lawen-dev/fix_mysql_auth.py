#!/usr/bin/env python3
"""
MySQL 认证插件自动修复脚本
自动将 dataflow 用户的认证方式修改为 mysql_native_password
"""

import pymysql
import os
import sys
from dotenv import load_dotenv
import getpass

# 加载环境变量
load_dotenv()

# 从环境变量获取配置
MYSQL_HOST = os.getenv('MYSQL_HOST', 'host.docker.internal')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
MYSQL_USER = os.getenv('MYSQL_USER', 'dataflow')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'dataflow_pass')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'dataflow')

print("=" * 70)
print("MySQL 认证插件自动修复工具")
print("=" * 70)
print(f"目标服务器: {MYSQL_HOST}:{MYSQL_PORT}")
print(f"目标用户: {MYSQL_USER}")
print(f"目标数据库: {MYSQL_DATABASE}")
print("=" * 70)

# 获取 root 密码
print("\n请输入 MySQL root 用户的密码:")
root_password = getpass.getpass("Root 密码: ")

try:
    print("\n[1/5] 正在使用 root 用户连接到 MySQL...")
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user='root',
        password=root_password,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    print("✅ 连接成功!")

    with connection.cursor() as cursor:
        # 检查 MySQL 版本
        print("\n[2/5] 检查 MySQL 版本...")
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()
        print(f"✅ MySQL 版本: {version['VERSION()']}")

        # 检查用户是否存在
        print(f"\n[3/5] 检查用户 '{MYSQL_USER}' 是否存在...")
        cursor.execute(f"SELECT user, host, plugin FROM mysql.user WHERE user='{MYSQL_USER}'")
        user_info = cursor.fetchone()

        if user_info:
            print(f"✅ 用户已存在")
            print(f"   - 用户: {user_info['user']}")
            print(f"   - 主机: {user_info['host']}")
            print(f"   - 当前认证插件: {user_info['plugin']}")

            # 修改认证方式
            print(f"\n[4/5] 修改用户 '{MYSQL_USER}' 的认证方式为 mysql_native_password...")
            cursor.execute(
                f"ALTER USER '{MYSQL_USER}'@'{user_info['host']}' "
                f"IDENTIFIED WITH mysql_native_password BY '{MYSQL_PASSWORD}'"
            )
            print("✅ 认证方式已修改")
        else:
            print(f"⚠️  用户 '{MYSQL_USER}' 不存在,正在创建...")

            # 创建用户
            print(f"\n[4/5] 创建用户 '{MYSQL_USER}' 并设置认证方式...")
            cursor.execute(
                f"CREATE USER '{MYSQL_USER}'@'%' "
                f"IDENTIFIED WITH mysql_native_password BY '{MYSQL_PASSWORD}'"
            )
            print("✅ 用户已创建")

            # 授予权限
            print(f"   授予数据库 '{MYSQL_DATABASE}' 的所有权限...")
            cursor.execute(f"GRANT ALL PRIVILEGES ON {MYSQL_DATABASE}.* TO '{MYSQL_USER}'@'%'")
            print("✅ 权限已授予")

        # 刷新权限
        print("\n[5/5] 刷新权限...")
        cursor.execute("FLUSH PRIVILEGES")
        print("✅ 权限已刷新")

        # 验证修改
        print("\n" + "=" * 70)
        print("验证修复结果")
        print("=" * 70)
        cursor.execute(f"SELECT user, host, plugin FROM mysql.user WHERE user='{MYSQL_USER}'")
        final_info = cursor.fetchone()
        if final_info:
            print(f"用户: {final_info['user']}")
            print(f"主机: {final_info['host']}")
            print(f"认证插件: {final_info['plugin']}")

            if final_info['plugin'] == 'mysql_native_password':
                print("\n✅ 修复成功! 认证插件已正确设置为 mysql_native_password")
                print("\n现在可以正常使用 dataflow 用户连接数据库了。")
                print("\n建议执行:")
                print("  python dataflow/evaluation/benchmark.py --foundation search --dataset hotpotqa --bench-size 10 --enable-qa")
            else:
                print(f"\n⚠️  警告: 认证插件仍然是 '{final_info['plugin']}',可能需要手动检查")

    connection.close()
    print("\n✅ 连接已关闭")
    print("=" * 70)

except pymysql.err.OperationalError as e:
    print(f"\n❌ 连接失败: {e}")
    error_code = e.args[0] if e.args else 0

    if error_code == 1045:
        print("\n错误原因: root 密码不正确")
        print("请确认 MySQL root 用户的密码是否正确")
    elif error_code == 2003:
        print("\n错误原因: 无法连接到 MySQL 服务器")
        print(f"请检查:")
        print(f"  1. MySQL 服务是否运行")
        print(f"  2. 主机地址 '{MYSQL_HOST}' 是否正确")
        print(f"  3. 端口 {MYSQL_PORT} 是否正确")
    else:
        print(f"\n错误代码: {error_code}")

    sys.exit(1)

except Exception as e:
    print(f"\n❌ 发生错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
