import socket
import pymysql
import subprocess
import sys
from urllib.request import urlopen
from urllib.error import URLError


def check_internet_connection():
    """检查互联网连接"""
    try:
        print("🌐 检查互联网连接...")
        urlopen('https://www.baidu.com', timeout=5)
        print("✅ 互联网连接正常")
        return True
    except URLError:
        print("❌ 互联网连接失败")
        return False


def check_dns_resolution(host):
    """检查DNS解析"""
    try:
        print(f"🔍 检查DNS解析: {host}")
        ip = socket.gethostbyname(host)
        print(f"✅ DNS解析成功: {host} -> {ip}")
        return ip
    except socket.gaierror as e:
        print(f"❌ DNS解析失败: {e}")
        return None


def check_port_connectivity(host, port):
    """检查端口连通性"""
    try:
        print(f"🔌 检查端口连通性: {host}:{port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)  # 增加超时时间
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            print(f"✅ 端口 {port} 连通性正常")
            return True
        else:
            print(f"❌ 端口 {port} 连接失败 (错误码: {result})")
            return False
    except Exception as e:
        print(f"❌ 端口检查异常: {e}")
        return False


def check_firewall():
    """检查防火墙设置"""
    try:
        print("🔥 检查防火墙状态...")
        # Windows 检查防火墙
        if sys.platform == "win32":
            result = subprocess.run(
                ['netsh', 'advfirewall', 'show', 'allprofiles', 'state'],
                capture_output=True, text=True, timeout=10
            )
            if "ON" in result.stdout:
                print("⚠️  防火墙已开启，可能阻止连接")
            else:
                print("✅ 防火墙未开启或未阻止连接")
        return True
    except Exception as e:
        print(f"⚠️  防火墙检查失败: {e}")
        return True


def test_mysql_connection():
    """测试MySQL数据库连接"""
    config = {
        'host': '43.135.26.58',
        'port': 3306,
        'user': 'root',
        'password': 'Aini7758258!!',
        'database': 'invite_code_system',
        'connect_timeout': 10
    }

    print("\n" + "=" * 50)
    print("开始数据库连接诊断...")
    print("=" * 50)

    # 1. 检查互联网连接
    if not check_internet_connection():
        print("💡 建议: 请检查您的网络连接")
        return False

    # 2. 检查DNS解析
    resolved_ip = check_dns_resolution(config['host'])
    if not resolved_ip:
        print("💡 建议: 检查主机名是否正确，或尝试使用IP地址")
        return False

    # 3. 检查防火墙
    check_firewall()

    # 4. 检查端口连通性
    if not check_port_connectivity(config['host'], config['port']):
        print("💡 建议: 端口可能被防火墙阻止或服务未运行")
        print("💡 尝试: 联系服务器管理员确认MySQL服务状态")
        return False

    # 5. 测试数据库连接
    print("\n🔑 测试数据库认证...")
    try:
        conn = pymysql.connect(**config)
        print("✅ 数据库连接成功!")

        # 测试基本查询
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            print(f"✅ MySQL版本: {version[0]}")

            # 检查表是否存在
            cursor.execute("SHOW TABLES LIKE 'invite_codes'")
            table_exists = cursor.fetchone()
            if table_exists:
                print("✅ 邀请码表存在")
            else:
                print("⚠️  邀请码表不存在")

        conn.close()
        return True

    except pymysql.Error as e:
        error_code, error_msg = e.args if len(e.args) == 2 else (e.args[0], str(e))
        print(f"❌ 数据库连接失败: {error_msg}")

        # 常见错误代码处理建议
        error_suggestions = {
            2003: "💡 建议: 检查MySQL服务是否运行，端口是否正确",
            1045: "💡 建议: 检查用户名和密码是否正确",
            1044: "💡 建议: 检查数据库权限和名称",
            1049: "💡 建议: 数据库不存在，请检查数据库名称",
        }

        if error_code in error_suggestions:
            print(error_suggestions[error_code])
        else:
            print("💡 建议: 检查数据库配置参数")

        return False


def alternative_connection_tests():
    """替代连接测试"""
    print("\n" + "=" * 50)
    print("进行替代连接测试...")
    print("=" * 50)

    # 测试其他可能的主机格式
    test_hosts = [
        '43.135.26.58',
        # 'www.yourdomain.com',  # 如果有域名可以添加
    ]

    for host in test_hosts:
        print(f"\n尝试连接: {host}")
        if check_port_connectivity(host, 3306):
            print(f"✅ {host} 端口可访问，可能是认证问题")
            return True

    return False


if __name__ == '__main__':
    print("🚀 开始全面的数据库连接诊断...")

    # 主要连接测试
    if test_mysql_connection():
        print("\n🎉 诊断完成: 数据库连接正常!")
    else:
        print("\n❌ 诊断完成: 数据库连接存在问题")

        # 进行替代测试
        if alternative_connection_tests():
            print("💡 网络可达，问题可能出现在数据库配置或认证上")
        else:
            print("💡 网络不可达，请检查网络设置或联系服务器管理员")

    print("\n📋 建议的解决步骤:")
    print("1. 确认MySQL服务在 43.135.26.58:3306 上运行")
    print("2. 检查用户名/密码/数据库名是否正确")
    print("3. 确认MySQL允许远程连接")
    print("4. 检查服务器防火墙设置")
    print("5. 联系服务器管理员确认服务状态")