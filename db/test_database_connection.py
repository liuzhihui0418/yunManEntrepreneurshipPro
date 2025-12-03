#!/usr/bin/env python3
# 测试MySQL连接 - 直接运行版本

import pymysql
import sys


def test_mysql_connection():
    """测试MySQL连接"""
    print("=" * 50)
    print("MySQL 连接测试")
    print("=" * 50)

    try:
        # 测试连接参数
        config = {
            'host': '127.0.0.1',
            'port': 3306,
            'user': 'root',
            'password': 'Aini7758258!!',
            'database': 'invite_code_system',
            'charset': 'utf8mb4',
            'connect_timeout': 10
        }

        print("尝试连接MySQL...")
        print(f"主机: {config['host']}:{config['port']}")
        print(f"用户: {config['user']}")
        print(f"数据库: {config['database']}")

        conn = pymysql.connect(**config)
        print("✅ MySQL连接成功！")

        # 测试查询
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            print(f"✅ MySQL版本: {version[0]}")

            # 检查表是否存在
            cursor.execute("SHOW TABLES LIKE 'invite_codes'")
            table_exists = cursor.fetchone()
            if table_exists:
                print("✅ 表 'invite_codes' 存在")
            else:
                print("⚠️  表 'invite_codes' 不存在")

        conn.close()
        return True

    except pymysql.err.OperationalError as e:
        error_code = e.args[0]
        if error_code == 2003:
            print("❌ 连接被拒绝 - MySQL服务可能未启动")
        elif error_code == 1045:
            print("❌ 访问被拒绝 - 用户名或密码错误")
        elif error_code == 1049:
            print("❌ 数据库不存在")
        else:
            print(f"❌ 连接错误: {e}")
        return False

    except Exception as e:
        print(f"❌ 未知错误: {e}")
        return False


def check_mysql_service():
    """检查MySQL服务状态"""
    print("\n" + "=" * 50)
    print("检查MySQL服务状态")
    print("=" * 50)

    import subprocess
    import os

    # Windows系统检查服务
    if os.name == 'nt':  # Windows
        try:
            # 检查MySQL服务状态
            result = subprocess.run(
                'sc query MySQL80',
                shell=True,
                capture_output=True,
                text=True
            )
            if 'RUNNING' in result.stdout:
                print("✅ MySQL服务正在运行 (MySQL80)")
            else:
                print("❌ MySQL80服务未运行")

            # 检查其他可能的服务名
            for service in ['MySQL57', 'MySQL', 'MYSQL']:
                result = subprocess.run(
                    f'sc query {service}',
                    shell=True,
                    capture_output=True,
                    text=True
                )
                if 'RUNNING' in result.stdout:
                    print(f"✅ MySQL服务正在运行 ({service})")
                    break

        except Exception as e:
            print(f"❌ 服务检查失败: {e}")

    else:  # Linux/Mac
        try:
            result = subprocess.run(
                'systemctl status mysql',
                shell=True,
                capture_output=True,
                text=True
            )
            if 'active (running)' in result.stdout:
                print("✅ MySQL服务正在运行")
            else:
                print("❌ MySQL服务未运行")
        except:
            pass


def test_without_database():
    """测试连接（不指定数据库）"""
    print("\n" + "=" * 50)
    print("测试基础连接（不指定数据库）")
    print("=" * 50)

    try:
        conn = pymysql.connect(
            host='127.0.0.1',
            port=3306,
            user='root',
            password='Aini7758258!!',
            connect_timeout=5
        )
        print("✅ 基础连接成功")

        with conn.cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            databases = cursor.fetchall()
            print("✅ 可用数据库:")
            for db in databases:
                print(f"   - {db[0]}")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ 基础连接失败: {e}")
        return False


if __name__ == "__main__":
    print("开始MySQL连接测试...")

    # 检查服务状态
    check_mysql_service()

    # 测试基础连接
    if test_without_database():
        # 测试完整连接
        test_mysql_connection()
    else:
        print("\n💡 建议操作:")
        print("1. 启动MySQL服务")
        print("2. 检查MySQL安装")
        print("3. 验证用户名密码")