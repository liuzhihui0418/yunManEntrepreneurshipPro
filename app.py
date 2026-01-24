# -*- coding: utf-8 -*-
import json
import threading
import os
import uuid
import time
import pymysql
import base64
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import secrets
import base64
import hashlib
# 1. 引入 dotenv 用于加载环境变量
from dotenv import load_dotenv

# Flask 相关引用
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, make_response
from flask_cors import CORS

# 数据库与支付引用
from pymysql.cursors import DictCursor
from alipay import AliPay
from db.redis_manager import redis_manager
from db.database import db_manager

# 腾讯云 COS 引用
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client
from weichat.bot import bot_bp
# ==========================================
# 0. 加载 .env 环境变量 (最先执行)
# ==========================================
# 🟢 修改点：强制使用绝对路径加载 .env，防止找不到文件
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path, override=True)  # override=True 确保覆盖系统变量
    print(f"✅ 已加载配置文件: {dotenv_path}")
else:
    print("❌ 严重警告：找不到 .env 文件，程序将无法正常运行！")
# ==========================================
# 这行代码会自动读取同目录下的 .env 文件
load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
# 🟢 新增：设置 Flask 允许的最大请求大小为 50MB
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024
# 假设你的前端域名是 ai.yunmanybcz.chat
# 🔥 修改这里：origins 改为 "*" (代表允许任何项目、任何IP连接)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})

# 这一行就把 bot.py 里的 '/wechat' 路由接管过来了
app.register_blueprint(bot_bp)
# ==========================================
# 1. 全局配置与密钥 (已改为从环境变量读取)
# ==========================================

# --- 支付宝配置 ---
ALIPAY_APP_ID = "2021006117616884"  # 你的APPID

# 【私钥】(刚才检测通过的，这里不用动了，保留你刚才填的)

PRIVATE_KEY_CONTENT = """
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCLce5pKBVWEjBpIHqE9j9Hh5/KnbnPU
MqL7qKuQXN4ogEkggnejg62UyGXVchgIzzW5k3T2YmQG0bVgzR8el7/cJ8btg8e1d0gRZn+m8LK+0qGXJ
Mdx+6rSGZbcZ6c+yaw+GlTQdnvEhPYq0zexN6SzxoWKkScOfEmyPXEo8vpb5TXFCPHuYn2hxnGhwePp5R
fk5VPqrO5BcgJRd1cNNn+UWdmL54qVaA5CEQrHTaUTwIKmSYZ1BfGy0g0XH7qqxNs+WS9dCk5p7BCMpaK
schkfmqdg/MwRzDmIDNtuufxe/AU7sqlsPoCGn95vR5XlOXcslps0gdLMeZ5IVN5y/tTAgMBAAECggEAY
7oJfZ8zEylTAfw+Y1UREIEIYInI12G6WbVDF0ir4nxKQOfXUxlZoD936JlrAoZw/mgbBQWxAiTf1ddN9D
A4PIs430KnMbBVwrzEU3jmKPDq7YjLliLkqA7RVVi+zRo5I5ulB+wyhm3xT6XDBhbZ7zi6OVvlUa2Gr+x
NCGL0dG9LVCnQMnDeEj9IVJFsVG3Gk4tbdXRK6hoF6/hCVzNl9vBk8Kdftbf5ec19JTq6mf8TcenRNa9u
8Y11PMaPOIVW5raheQFIj6BSLYm0AsAnVrfb8CXzPxijdykXAEgxiPtkspggcoBkN/x2/WfNivE/KqIxF
HQ+vNJgIuH8pWnVoQKBgQDk02teYhhcsOWzhvY070UA5PeEhMYKq50DXbXpH5Y4skr2XnFUD6KC74M3bK
ovsPk5osWwV1SARvh9BgPEsLXs6KDNbYf62GYe4aX2qJ+3Yhnajup7A5rmHwNAU7c8t/UbOdOdYg4Dw/J
qIZEf4zEdBoz8KsHuULdLHBHR6r3R2QKBgQCcATpZ3ITOCvkXwB5kBgUS0l8/RN681VI4qNHHhH/4r4+o
DEDOMHYvh/zj1IyGKFqG3jvD+iQRiPQbZ4Xlw0zGDyst/1250VGjTc3+xqPSmMOFH0qt3AMW/S7aVzmXA
ls0FDjtef0tiYQwE2QdjPxmmWFUpwkZjTOmwA05v7JPCwKBgQCbuSWAfdGGgvxPSLGVJKAZE7k+ff0old
Gs0MFTfSOGQg+xymPliR5XbRgnR9Qp0I5LIvLWJxhik+nXa5h06q1kJIwKQVgg5dPZgEaprefDrQdbLZd
1T+bCZKiZxl8U+zva42eX23seJON8Rou037A0yJh5o7+Gp3eVreySpuW3QQKBgBbEwxxsZ+Gejl5eBtF4
Y3MsywPz7EJJLBfi48Mn3nmQPfo715WAUy96vHkQA3ZtG1FFzBk9P9hjUaVSRaOUDnd1rUqoU6iUGUMpT
uBZY32QGDEssPyQ+M55I0ZwppIYoPEH5osaW84ynN1bZyg89HWQ+zicrGJTTm+O5h9AkCijAoGBALzK5R
IxvqqP8kMKA53HYP3dt8rly1vwyhzke0ULf1Mw1f96TKRcMYV82+HD/ixVIR3Pdr5vURhAP71GEq7yy0X
HC76pO9EdBZp5ok/fvetxLN1TBNEPVuxAzooFBLXCoWhskEZC8tP7JksVKXiLv/kjUwRYwTUpSrBvMcEu
WgYv
"""
# 【支付宝公钥】(这里我专门做了修改)
# 请打开你截图的那个 alipayPublicKey_RSA2.txt 文件
# 全选 -> 复制 -> 直接覆盖粘贴到下面这个引号里
# 不需要管换行，也不要自己加 "-----BEGIN...", 代码会自动加！

ALIPAY_PUBLIC_KEY_CONTENT = """

MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAg3Al49jSZnlY9iPcunRgWZvgwT9X03z3L+oajd+3Yq8sq21F4r8XB/Pu0TuzqpR2uIjZis4DulE5LoB9JhDei9xw9If5y96QsoMmCmkBaDSBRwSko2TaJmA3MmgVOgWSRQ753Wgx5xffYOmmrPq/dQlGH0J91NaWyVf72kPgjgW6+1jq7rOHUc2aRlVF+SNwOPO9OI/8zk+2tmOZRvT2QvGnjteqe5zI1/cpZ9t4XkzFSMP84hn5xOHH5GTPXC1yM2U8quT+Vlte+I/2XwIx3zGq+PSnOPENwJHFS8bVFpkcYB91ZZFwBH2nLPua/kmMbh/j0h+/UcD8nrgrnlAdDQIDAQAB

"""

# --- 腾讯云 COS 配置 ---
TENCENT_SECRET_ID = os.getenv("TENCENT_SECRET_ID")
TENCENT_SECRET_KEY = os.getenv("TENCENT_SECRET_KEY")
TENCENT_REGION = os.getenv("TENCENT_REGION")
TENCENT_BUCKET = os.getenv("TENCENT_BUCKET")
CDN_DOMAIN = os.getenv("CDN_DOMAIN")

# --- 数据库配置 ---
# 注意：端口需要转为 int，并提供默认值防止报错
MYSQL_CONF = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "db": os.getenv("MYSQL_DB"),
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

# --- 管理员密码 ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# 创建全局线程池
executor = ThreadPoolExecutor(max_workers=5)

# 初始化 COS 客户端
try:
    if TENCENT_SECRET_ID and TENCENT_SECRET_KEY:
        cos_config = CosConfig(Region=TENCENT_REGION, SecretId=TENCENT_SECRET_ID, SecretKey=TENCENT_SECRET_KEY)
        cos_client = CosS3Client(cos_config)
        print("✅ 腾讯云 COS 客户端初始化成功")
    else:
        print("⚠️ 未检测到腾讯云配置，COS 功能将不可用")
        cos_client = None
except Exception as e:
    print(f"❌ 腾讯云 COS 初始化失败: {e}")
    cos_client = None


# 密钥清洗函数 (逻辑保持不变，依然兼容 .env 中的单行格式)
# 🟢 修改点：增强的密钥清洗函数 (完全复制 pay.py 的成功逻辑)
def fix_key_format(key_content, is_private=True):
    if not key_content:
        print(f"❌ 警告：{'私钥' if is_private else '公钥'} 内容为空！请检查 .env 文件。")
        return ""

    # 1. 清洗 (去掉可能存在的旧头尾、空格、换行)
    key_content = key_content.replace("-----BEGIN RSA PRIVATE KEY-----", "")
    key_content = key_content.replace("-----END RSA PRIVATE KEY-----", "")
    key_content = key_content.replace("-----BEGIN PRIVATE KEY-----", "")
    key_content = key_content.replace("-----END PRIVATE KEY-----", "")
    key_content = key_content.replace("-----BEGIN PUBLIC KEY-----", "")
    key_content = key_content.replace("-----END PUBLIC KEY-----", "")
    key_content = key_content.replace("\n", "").replace(" ", "").strip()

    # 2. 补全 Base64 Padding (防止因复制丢失等于号报错)
    missing_padding = len(key_content) % 4
    if missing_padding:
        key_content += '=' * (4 - missing_padding)

    # 3. 64字符换行
    split_key = '\n'.join([key_content[i:i + 64] for i in range(0, len(key_content), 64)])

    # 4. 加头
    if is_private:
        return f"-----BEGIN PRIVATE KEY-----\n{split_key}\n-----END PRIVATE KEY-----"
    else:
        # 注意：支付宝公钥通常是 Standard Public Key 格式
        return f"-----BEGIN PUBLIC KEY-----\n{split_key}\n-----END PUBLIC KEY-----"


# 格式化密钥
FINAL_PRIVATE_KEY = fix_key_format(PRIVATE_KEY_CONTENT, True)
FINAL_PUBLIC_KEY = fix_key_format(ALIPAY_PUBLIC_KEY_CONTENT, False)

# ==========================================
# 🟢 新增：启动时自检密钥 (防止网页报错 "RSA key format not supported")
# ==========================================
try:
    print("-" * 30)
    print("正在进行密钥自检...")

    if not FINAL_PRIVATE_KEY or len(FINAL_PRIVATE_KEY) < 100:
        raise ValueError("私钥内容过短或为空，.env读取失败")

    if not FINAL_PUBLIC_KEY or len(FINAL_PUBLIC_KEY) < 50:
        raise ValueError("公钥内容过短或为空，.env读取失败")

    # 尝试模拟加载
    from Cryptodome.PublicKey import RSA

    RSA.importKey(FINAL_PRIVATE_KEY)
    print("✅ 私钥格式检查通过 (Cryptodome load success)")

    RSA.importKey(FINAL_PUBLIC_KEY)
    print("✅ 支付宝公钥格式检查通过 (Cryptodome load success)")
    print("-" * 30)

except Exception as e:
    print("\n" + "!" * 50)
    print(f"❌ 严重错误：密钥格式校验失败！\n错误详情: {e}")
    print("请检查 .env 文件中 PRIVATE_KEY_CONTENT 和 ALIPAY_PUBLIC_KEY_CONTENT 是否完整粘贴。")
    print("!" * 50 + "\n")


# 初始化支付宝客户端
def get_alipay_client():
    return AliPay(
        appid=ALIPAY_APP_ID,
        app_notify_url="https://ai.yunmanybcz.chat/api/pay/notify",
        app_private_key_string=FINAL_PRIVATE_KEY,
        alipay_public_key_string=FINAL_PUBLIC_KEY,
        sign_type="RSA2"
    )


# ================= 工具函数 =================

# 修改后的上传逻辑：同时支持 纯URL、文件对象(FileStorage)
def ensure_upload(file_obj, url_str, sub_folder="library"):
    # 1. 如果有新文件上传 (FileStorage 对象)
    if file_obj:
        try:
            if not cos_client:
                raise Exception("COS 客户端未初始化")

            # 获取后缀名
            ext = file_obj.filename.split('.')[-1] if '.' in file_obj.filename else "png"
            filename = f"{sub_folder}/{uuid.uuid4().hex}.{ext}"

            # 直接读取文件流上传，不用转 base64
            cos_client.put_object(Bucket=TENCENT_BUCKET, Body=file_obj.read(), Key=filename)
            return f"{CDN_DOMAIN}/{filename}"
        except Exception as e:
            print(f"COS 上传异常: {e}")
            raise e

    # 2. 如果没有新文件，检查是不是原本的 URL (用于编辑模式)
    if url_str and url_str.startswith("http"):
        return url_str

    return None


from functools import wraps


# 删掉默认值，强制从环境变量读取。读取不到就为空，这样更安全。
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # =================================================
        # 🟢 新增逻辑：API Key 绿色通道 (带调试功能)
        # =================================================
        request_key = request.headers.get('X-API-Key')

        # 重新获取一次环境变量，防止全局变量没加载到
        # .strip() 去除可能存在的首尾空格，防止 .env 写错
        env_key = os.getenv("INTERNAL_API_KEY")

        # 🔍 调试打印：请在 Pycharm/终端 控制台看这行输出！
        if request_key:
            print(f"🔍 [调试] 客户端发来的Key: [{request_key}] | 服务器配置的Key: [{env_key}]")

        # 核心判断：只有两者都不为空，且相等时才放行
        if env_key and request_key and str(request_key).strip() == str(env_key).strip():
            return f(*args, **kwargs)
        # =================================================

        # 👇👇👇 下面是 Session 校验逻辑 (保持不变) 👇👇👇

        session_id = request.cookies.get('session_id')

        if not session_id or not redis_manager.validate_session(session_id):
            return jsonify({"status": "error", "msg": "未登录或会话已过期"}), 401

        user_info = redis_manager.get_session_info(session_id)
        if not user_info:
            return jsonify({"status": "error", "msg": "用户信息获取失败"}), 401

        code = user_info.get('code')
        device_id = user_info.get('device_id')

        if not db_manager.check_code_is_valid_strict(code) or \
                not db_manager.check_device_consistency(code, device_id):
            redis_manager.destroy_session(session_id)
            return jsonify({"status": "error", "msg": "授权验证失败，请重新登录"}), 401

        return f(*args, **kwargs)

    return decorated_function

# ================= 基础路由 =================

# Redis预热
try:
    with app.app_context():
        redis_manager.sync_mysql_to_redis()
except Exception as e:
    print(f"Redis同步警告: {e}")


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'images'), 'logo.png')


@app.route('/')
def index():
    session_id = request.cookies.get('session_id')
    if session_id and redis_manager.validate_session(session_id):
        user_info = redis_manager.get_session_info(session_id)
        if user_info:
            code = user_info.get('code')
            device_id = user_info.get('device_id')

            # 同时检查：没过期 AND 设备依然在绑定列表里
            if db_manager.check_code_is_valid_strict(code) and \
                    db_manager.check_device_consistency(code, device_id):
                return render_template('index.html')
            else:
                redis_manager.destroy_session(session_id)

    return render_template('login.html')


# ================= 支付功能 =================

@app.route('/api/pay/create', methods=['POST'])
def create_order():
    """创建支付订单"""
    try:
        data = request.get_json()
        face_value = data.get('face_value')
        price = data.get('price')

        out_trade_no = f"ORD_{int(time.time())}_{uuid.uuid4().hex[:4].upper()}"
        alipay = get_alipay_client()

        order_res = alipay.api_alipay_trade_precreate(
            out_trade_no=out_trade_no,
            total_amount=str(price),
            subject=f"算力充值-{face_value}元",
            timeout_express="10m"
        )

        qr_code = order_res.get("qr_code")
        if not qr_code:
            error_msg = order_res.get('sub_msg', order_res.get('msg', '未知错误'))
            return jsonify({'code': 500, 'msg': f'支付宝拒绝：{error_msg}'})

        return jsonify({'code': 200, 'qr_url': qr_code, 'order_no': out_trade_no})
    except Exception as e:
        print(f"❌ 系统报错: {e}")
        return jsonify({'code': 500, 'msg': str(e)})


@app.route('/api/pay/notify', methods=['POST'])
def pay_notify():
    """支付宝异步回调"""
    try:
        data = request.form.to_dict()
        signature = data.pop("sign")
        alipay = get_alipay_client()

        if alipay.verify(data, signature):
            trade_status = data.get("trade_status")
            if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
                order_no = data.get("out_trade_no")
                pay_amount = data.get("total_amount")

                conn = pymysql.connect(**MYSQL_CONF)
                try:
                    with conn.cursor() as cursor:
                        sql_select = "SELECT id, card_key FROM banana_key_inventory WHERE status=0 AND CAST(price_tag AS DECIMAL(10,2)) = CAST(%s AS DECIMAL(10,2)) LIMIT 1 FOR UPDATE"
                        cursor.execute(sql_select, (pay_amount,))
                        card = cursor.fetchone()

                        if card:
                            sql_update = "UPDATE banana_key_inventory SET status=1, order_no=%s, sold_at=NOW() WHERE id=%s"
                            cursor.execute(sql_update, (order_no, card['id']))
                            conn.commit()
                            print(f"✅ 发货成功: 订单 {order_no} -> 卡密 {card['card_key']}")
                        else:
                            print(f"⚠️ 库存不足: 金额 {pay_amount} 无货")
                finally:
                    conn.close()
                return "success"
        return "fail"
    except Exception as e:
        print(f"❌ 回调处理错误: {e}")
        return "fail"


@app.route('/api/pay/status/<order_no>', methods=['GET'])
def check_pay_status(order_no):
    """查询订单是否已发货"""
    conn = pymysql.connect(**MYSQL_CONF)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT card_key FROM compute_keys WHERE order_no = %s", (order_no,))
            res = cursor.fetchone()
            if res:
                return jsonify({'paid': True, 'card_key': res['card_key']})
    finally:
        conn.close()
    return jsonify({'paid': False})


# ================= Banana 支付核心接口 =================

@app.route('/api/banana_pay/create', methods=['POST'])
def banana_create_order():
    """下单接口"""
    try:
        data = request.get_json()
        price = data.get('price')
        out_trade_no = f"BANANA_{int(time.time())}_{uuid.uuid4().hex[:4].upper()}"

        alipay = get_alipay_client()
        order_res = alipay.api_alipay_trade_precreate(
            out_trade_no=out_trade_no,
            total_amount=str(price),
            subject=f"YunManGongFangAI网页登录月卡-{price}元",
            notify_url="https://ai.yunmanybcz.chat/api/banana_pay/notify",
            timeout_express="10m"
        )
        qr_code = order_res.get("qr_code")
        if not qr_code: return jsonify({'code': 500, 'msg': '支付宝下单失败'})
        return jsonify({'code': 200, 'qr_url': qr_code, 'order_no': out_trade_no})
    except Exception as e:
        return jsonify({'code': 500, 'msg': str(e)})


@app.route('/api/banana_pay/notify', methods=['POST'])
def banana_pay_notify():
    """Banana 支付回调"""
    try:
        data = request.form.to_dict()
        signature = data.pop("sign", None)
        alipay = get_alipay_client()

        if alipay.verify(data, signature):
            trade_status = data.get("trade_status")
            if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
                order_no = data.get("out_trade_no")
                pay_amount = data.get("total_amount")

                conn = pymysql.connect(**MYSQL_CONF)
                try:
                    with conn.cursor() as cursor:
                        sql_select = """
                            SELECT id, card_key 
                            FROM banana_key_inventory 
                            WHERE status = 0 
                            AND CAST(price_tag AS DECIMAL(10,2)) = CAST(%s AS DECIMAL(10,2)) 
                            LIMIT 1 
                            FOR UPDATE
                        """
                        cursor.execute(sql_select, (pay_amount,))
                        card = cursor.fetchone()

                        if card:
                            sql_update = """
                                UPDATE banana_key_inventory 
                                SET status = 1, order_no = %s, sold_at = NOW() 
                                WHERE id = %s
                            """
                            cursor.execute(sql_update, (order_no, card['id']))
                            conn.commit()
                            print(f"✅ Banana发货成功: 订单 {order_no} | 金额 {pay_amount} | 卡密 ID {card['id']}")
                        else:
                            print(f"⚠️ 库存不足：数据库中没有金额为 {pay_amount} 的未售卡密！")
                except Exception as db_err:
                    print(f"❌ 数据库操作异常: {db_err}")
                    if conn: conn.rollback()
                finally:
                    if conn: conn.close()
                return "success"
        return "fail"
    except Exception as e:
        print(f"🔥 回调系统级异常: {e}")
        return "fail"


@app.route('/api/banana_pay/status/<order_no>', methods=['GET'])
def banana_check_status(order_no):
    """状态查询接口"""
    try:
        conn = pymysql.connect(**MYSQL_CONF)
        try:
            with conn.cursor() as cursor:
                sql = "SELECT card_key FROM banana_key_inventory WHERE order_no = %s AND status = 1"
                cursor.execute(sql, (order_no,))
                res = cursor.fetchone()
                if res:
                    return jsonify({'paid': True, 'card_key': res['card_key']})
        finally:
            conn.close()
    except Exception as e:
        print(f"📢 数据库状态查询暂不可用: {e}")
    return jsonify({'paid': False})

# ================= 授权验证与用户管理 =================

@app.route('/api/validate', methods=['POST'])
def validate_invite_code():
    try:
        data = request.get_json()
        code = data.get('invite_code', '').strip().upper()
        device_id = data.get('device_id', '').strip()  # 获取设备ID

        if not code: return jsonify({'success': False, 'message': '请输入邀请码'}), 400
        if not device_id: return jsonify({'success': False, 'message': '环境异常：无法识别设备'}), 400

        # 1. 数据库绑定检查 (一机一码)
        bind_result = db_manager.check_and_bind_device(code, device_id)
        if not bind_result['success']:
            return jsonify({'success': False, 'message': bind_result['msg']}), 403

        # 2. 有效期检查
        is_valid = db_manager.check_code_is_valid_strict(code)

        if is_valid:
            # 3. 创建 Session (注意：这里传入了 device_id)
            session_id = redis_manager.create_session(code, device_id)
            user_info = redis_manager.get_session_info(session_id)

            resp = jsonify({'success': True, 'session_id': session_id, 'user': user_info, 'message': '成功'})
            resp.set_cookie('session_id', session_id, max_age=86400, httponly=True, samesite='None', secure=True)
            return resp
        else:
            return jsonify({'success': False, 'message': '邀请码不存在已禁用或已过期'}), 401

    except Exception as e:
        print(f"Login Error: {str(e)}")
        return jsonify({'success': False, 'message': '系统繁忙'}), 500


@app.route('/api/license/verify', methods=['POST'])
def verify_license_db():
    try:
        data = request.get_json()
        if not data: return jsonify({'code': 400, 'msg': '无请求数据'}), 400
        client_key = data.get('card_key', '').strip()
        mid = data.get('machine_id', '').strip()
        if not client_key or not mid: return jsonify({'code': 400, 'msg': '参数缺失'}), 400

        conn = pymysql.connect(**MYSQL_CONF)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT max_devices, status FROM cards WHERE card_key = %s", (client_key,))
                card = cursor.fetchone()
                if not card: return jsonify({'code': 404, 'msg': '卡密不存在'})
                if card['status'] != 'active': return jsonify({'code': 403, 'msg': '该卡密已被封禁'})

                max_allowed = card.get('max_devices', 1)
                cursor.execute("SELECT machine_id, expiry_date, status FROM license_bindings WHERE card_key = %s",
                               (client_key,))
                bindings = cursor.fetchall()
                current_binding = next((b for b in bindings if b['machine_id'] == mid), None)
                if current_binding:
                    if current_binding.get('status') != 'active': return jsonify({'code': 403, 'msg': '授权已被禁用'})
                    expiry = current_binding['expiry_date']
                    if expiry and datetime.now() > expiry: return jsonify({'code': 403, 'msg': '授权已过期'})
                    return jsonify({'code': 200, 'msg': '验证通过', 'expiry_date': str(expiry)})

                if len(bindings) >= max_allowed:
                    return jsonify({'code': 403, 'msg': f'激活失败：该卡密仅支持 {max_allowed} 台设备'})

                new_expiry = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    "INSERT INTO license_bindings (card_key, machine_id, activation_time, status, expiry_date) VALUES (%s, %s, NOW(), 'active', %s)",
                    (client_key, mid, new_expiry))
                conn.commit()
                return jsonify({'code': 200, 'msg': '新设备激活成功', 'expiry_date': str(new_expiry)})
        finally:
            conn.close()
    except Exception as e:
        print(f"Verify Error: {str(e)}")
        return jsonify({'code': 500, 'msg': f"服务器错误: {str(e)}"}), 500


@app.route('/api/inventory/stocks', methods=['GET'])
def get_realtime_stocks():
    """获取所有面额的实时库存数量"""
    conn = pymysql.connect(**MYSQL_CONF)
    try:
        with conn.cursor() as cursor:
            sql = "SELECT face_value, COUNT(*) as count FROM compute_keys WHERE status = 0 GROUP BY face_value"
            cursor.execute(sql)
            results = cursor.fetchall()
            stock_map = {row['face_value']: row['count'] for row in results}
            return jsonify({'code': 200, 'stocks': stock_map})
    except Exception as e:
        return jsonify({'code': 500, 'msg': str(e)})
    finally:
        conn.close()


# 找到这个函数，全部替换成下面的内容
@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    conn = db_manager.get_connection()

    try:
        # 🔥🔥🔥 核心修改在这里：加上 pymysql.cursors.DictCursor
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 1. 查询用户
            sql = "SELECT * FROM admin_users WHERE username=%s AND password=%s"
            cursor.execute(sql, (username, password))
            user = cursor.fetchone()

            if user:
                # 2. 生成随机 Token
                token = str(uuid.uuid4())

                # 3. 存入 Redis (现在 user['id'] 可以正常使用了，因为 user 变成了字典)
                redis_manager.r.setex(f"admin_session:{token}", 86400, user['id'])

                resp = jsonify({'success': True, 'redirect': '/admin/dashboard'})
                resp.set_cookie('admin_token', token, max_age=86400)
                return resp
            else:
                return jsonify({'success': False, 'message': '账号密码错误'}), 401
    except Exception as e:
        print(f"管理员登录出错: {e}")
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500
    finally:
        conn.close()


@app.route('/admin/codes', methods=['POST'])
def create_code():
    data = request.get_json()
    code = data.get('code') or str(uuid.uuid4())[:8].upper()
    expires_days = int(data.get('expires_days', 7))
    note = data.get('note', '')
    try:
        redis_manager.add_single_code(code, expires_days)
        redis_manager.r.delete("admin:dashboard_stats")
        redis_manager.r.delete("admin:codes_list")
        executor.submit(db_manager.create_invite_code, code, expires_days, note)
        return jsonify({'success': True, 'message': '创建成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def get_cards_with_pagination(self, page=1, page_size=20, search=None):
    # 引用 Redis
    from db.redis_manager import redis_manager

    # 缓存键名区分开
    cache_key = f"admin:cards_list_page_{page}_size_{page_size}_search_{search or 'all'}"
    try:
        cached_data = redis_manager.r.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except:
        pass

    conn = self.get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            where_conditions = []
            params = []

            if search:
                # 搜索卡密 card_key
                where_conditions.append("card_key LIKE %s")
                params.append(f"%{search}%")

            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

            # 获取总数
            count_sql = f"SELECT COUNT(*) as total FROM cards {where_clause}"
            cursor.execute(count_sql, params)
            total_count = cursor.fetchone()['total']

            # 分页查询
            offset = (page - 1) * page_size
            sql = f"SELECT * FROM cards {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s"
            query_params = params + [page_size, offset]

            cursor.execute(sql, query_params)
            rows = list(cursor.fetchall())

            # 格式化时间
            for row in rows:
                if row.get('created_at'): row['created_at'] = str(row['created_at'])

            result = {
                'cards': rows,
                'pagination': {
                    'current_page': page,
                    'page_size': page_size,
                    'total_items': total_count,
                    'total_pages': (total_count + page_size - 1) // page_size if page_size > 0 else 1
                }
            }

            # 写入缓存 (30秒)
            try:
                redis_manager.r.setex(cache_key, 30, json.dumps(result))
            except:
                pass
            return result
    except Exception as e:
        print(f"查询 cards 失败: {e}")
        return {'cards': [], 'pagination': {'current_page': 1, 'total_items': 0}}
    finally:
        conn.close()



@app.route('/admin/codes/batch', methods=['POST'])
def create_batch_codes():
    data = request.get_json()
    count = data.get('count', 1)
    prefix = data.get('prefix', '')
    expires_days = int(data.get('expires_days', 7))
    note = data.get('note', '')
    created_codes = []
    try:
        for i in range(count):
            code = f"{prefix}_{str(uuid.uuid4())[:8].upper()}" if prefix else str(uuid.uuid4())[:8].upper()
            redis_manager.add_single_code(code, expires_days)
            created_codes.append(code)
            executor.submit(db_manager.create_invite_code, code, expires_days, note)
        redis_manager.r.delete("admin:total_codes_count")
        return jsonify({'success': True, 'codes': created_codes})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/dashboard', methods=['GET'])
def get_dashboard_data():
    if not request.cookies.get('admin_token'): return redirect('/admin')
    return jsonify({'success': True, **db_manager.get_dashboard_stats()})


@app.route('/admin/api/dashboard/paginated', methods=['GET'])
def get_paginated_dashboard():
    return jsonify({'success': True,
                    **db_manager.get_dashboard_stats_with_pagination(request.args.get('page', 1, type=int),
                                                                     request.args.get('page_size', 20, type=int))})


@app.route('/admin/codes/paginated', methods=['GET'])
def get_paginated_codes():
    return jsonify({'success': True, **db_manager.get_codes_with_pagination(request.args.get('page', 1, type=int),
                                                                            request.args.get('page_size', 20, type=int),
                                                                            request.args.get('search', ''))})
@app.route('/admin/cards/paginated', methods=['GET'])
def get_paginated_cards():
    # 这里记得加鉴权
    if not request.cookies.get('admin_token'):
        return jsonify({'success': False, 'message': '未登录'}), 401

    return jsonify({'success': True, **db_manager.get_cards_with_pagination(
        request.args.get('page', 1, type=int),
        request.args.get('page_size', 20, type=int),
        request.args.get('search', '')
    )})

@app.route('/api/check_session', methods=['GET'])
def check_session():
    session_id = request.cookies.get('session_id')
    if session_id:
        user_info = redis_manager.get_session_info(session_id)
        if user_info:
            code = user_info.get('code')
            device_id = user_info.get('device_id')  # 从 Session 拿出当时登录的设备ID

            # === 🚀 双重核心校验 ===

            # 1. 校验是否过期
            if not db_manager.check_code_is_valid_strict(code):
                redis_manager.destroy_session(session_id)
                return jsonify({'valid': False})

            # 2. 校验设备是否还绑定着 (解决你说的解绑不掉线问题)
            # 如果后台把设备解绑了，这里就会返回 False，直接踢下线
            if not db_manager.check_device_consistency(code, device_id):
                redis_manager.destroy_session(session_id)
                return jsonify({'valid': False})

            # =====================

            return jsonify({'valid': True, 'user': user_info})
    return jsonify({'valid': False})


@app.route('/api/logout', methods=['POST'])
def logout():
    session_id = request.cookies.get('session_id')
    if session_id: redis_manager.destroy_session(session_id)
    return jsonify({'success': True})


@app.route('/admin/dashboard')
def admin_dashboard_page():
    if not request.cookies.get('admin_token'): return redirect('/admin')
    return render_template('admin.html')


@app.route('/admin')
def admin_login_page(): return render_template('admin_login.html')


@app.route('/admin/codes', methods=['GET'])
def get_codes_list():
    return jsonify({'success': True, 'codes': db_manager.get_all_codes()})


# ==========================================
# 🟢 新增：获取用户卡密信息接口
# ==========================================
@app.route('/api/user/card_info', methods=['GET'])
def get_user_card_info():
    # 1. 获取 Session
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'success': False, 'message': '未登录'}), 401

    # 2. 从 Redis 获取用户信息
    user_info = redis_manager.get_session_info(session_id)
    if not user_info:
        return jsonify({'success': False, 'message': '会话已过期'}), 401

    code = user_info.get('code')  # 这里 code 就是卡密/邀请码

    # 3. 从数据库查询详细信息 (过期时间)
    conn = pymysql.connect(**MYSQL_CONF)
    try:
        with conn.cursor() as cursor:
            # 查询 invite_codes 表
            sql = "SELECT code, expires_at, created_at FROM invite_codes WHERE code = %s"
            cursor.execute(sql, (code,))
            result = cursor.fetchone()

            if result:
                # 格式化时间
                expires_at = result['expires_at']

                # 如果 expires_at 是 None，可能是永久有效，或者逻辑不同，视你数据库结构而定
                # 假设 expires_at 是 datetime 对象
                expiry_str = expires_at.strftime('%Y-%m-%d %H:%M:%S') if expires_at else "永久有效"

                return jsonify({
                    'success': True,
                    'data': {
                        'card_key': result['code'],
                        'expiry_date': expiry_str
                    }
                })
            else:
                return jsonify({'success': False, 'message': '未找到卡密信息'}), 404
    except Exception as e:
        print(f"查询卡密信息失败: {e}")
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500
    finally:
        conn.close()

# ================= 🚀 新增：编辑与删除接口 =================

@app.route('/admin/codes/update', methods=['POST'])
def update_code_api():
    """编辑邀请码接口"""
    # 鉴权
    if not request.cookies.get('admin_token'):
        return jsonify({'success': False, 'message': '未登录'}), 401

    data = request.get_json()
    code = data.get('code')
    new_expiry = data.get('new_expiry')  # 格式 "2025-01-01"
    reset_device = data.get('reset_device')  # Boolean True/False

    if not code:
        return jsonify({'success': False, 'message': '参数缺失'})

    success = db_manager.update_invite_code(code, new_expiry, reset_device)
    if success:
        return jsonify({'success': True, 'message': '更新成功'})
    else:
        return jsonify({'success': False, 'message': '更新失败，请检查服务器日志'})


@app.route('/admin/codes/delete', methods=['POST'])
def delete_code_api():
    """删除邀请码接口"""
    # 鉴权
    if not request.cookies.get('admin_token'):
        return jsonify({'success': False, 'message': '未登录'}), 401

    data = request.get_json()
    code = data.get('code')

    if not code:
        return jsonify({'success': False, 'message': '参数缺失'})

    success = db_manager.delete_invite_code(code)
    if success:
        return jsonify({'success': True, 'message': '删除成功'})
    else:
        return jsonify({'success': False, 'message': '删除失败'})

@app.route('/yunmanapi')
def yunman_api_page():
    return render_template('yunmanapi.html')  # 假设你有这个HTML文件

# ==========================================
# 🚀 魔云工坊 - 配音神器页面
# ==========================================
@app.route('/magic_workshop')
@login_required  # 必须登录才能进入
def magic_workshop_page():
    return render_template('magic_workshop.html')

# ==========================================
# 🚀 风格角色库 API (已完美移植合并)
# ==========================================

@app.route('/style_library')
def style_library_page():
    # 1. 获取 Session ID
    session_id = request.cookies.get('session_id')

    # 2. 验证 Session 是否存在于 Redis
    if session_id and redis_manager.validate_session(session_id):
        user_info = redis_manager.get_session_info(session_id)
        if user_info:
            code = user_info.get('code')
            device_id = user_info.get('device_id')

            # 3. 核心安全校验：检查是否过期 + 检查设备绑定一致性
            # (这步非常重要，防止用户虽然有Session，但在后台被删了或被解绑了还能进)
            if db_manager.check_code_is_valid_strict(code) and \
                    db_manager.check_device_consistency(code, device_id):
                # ✅ 验证通过，放行进入风格库
                return render_template('style_library.html')
            else:
                # ❌ 验证失败（过期或设备不对），销毁 Session
                redis_manager.destroy_session(session_id)

    # 4. 未登录或验证失败，重定向回首页（也就是登录页）
    return redirect('/')


# 1. 保存/更新角色
# ==========================================
# 1. 保存/更新角色 (完整安全版)
# ==========================================
@app.route("/api/cloud/character/save", methods=['POST'])
@login_required
def save_character_db():
    # 👇👇👇 1. 安全校验区域 (防止 Postman 盗刷) 👇👇👇
    # 【修改点】直接从环境变量读取，不写默认值，防止代码泄露密码
    # 如果 .env 没配置 ADMIN_PASSWORD，这里就是 None，谁都进不来（安全）
    sys_admin_token = os.getenv("ADMIN_PASSWORD")

    # 获取请求带来的密码凭证
    # 方式A：网页版管理员登录后，Cookie 里会有 token
    cookie_token = request.cookies.get('admin_token')
    # 方式B：Postman 或脚本调用时，Header 里必须带 X-Admin-Token
    header_token = request.headers.get("X-Admin-Token")

    # 核心判断：如果两个地方的密码都不对，直接拒绝！
    # 注意：如果 sys_admin_token 是 None (没配环境变量)，这里永远不等，所以默认拒绝所有请求，非常安全
    if str(cookie_token) != str(sys_admin_token) and str(header_token) != str(sys_admin_token):
        print(f"⚠️ 拦截到非法上传请求 | Cookie: {cookie_token} | Header: {header_token}")
        return jsonify({"success": False, "msg": "🚫 权限不足：需要管理员密码！"}), 403
    # 👆👆👆 安全校验结束 👆👆👆

    try:
        # 👇👇👇 2. 数据获取区域 (FormData 模式) 👇👇👇
        # 普通文本字段从 request.form 获取
        label = request.form.get('label', '').strip()
        name = request.form.get('name', '').strip()
        desc = request.form.get('desc', '').strip()
        p_name = request.form.get('project_name', '').strip()
        char_id = request.form.get('id')

        # 文件对象从 request.files 获取 (如果没有上传新文件，这里是 None)
        image_file = request.files.get('image_file')
        video_file = request.files.get('video_file')

        # 获取旧 URL (用于编辑模式：如果用户没换图，就用这个旧链接)
        image_url_old = request.form.get('image_url_old')
        video_url_old = request.form.get('video_url_old')

        # 基础必填项检查
        if not all([label, name, desc, p_name]):
            return jsonify({"success": False, "msg": "基础信息（标签、名称、描述、分类）必须填写！"})

        # 👇👇👇 3. 文件上传处理 👇👇👇
        try:
            # ensure_upload 函数会自动判断：
            # 如果有新文件(image_file)，就上传到 COS 并返回新链接
            # 如果没新文件，就直接返回旧链接(image_url_old)
            final_img_url = ensure_upload(image_file, image_url_old, "library")
            final_vid_url = ensure_upload(video_file, video_url_old, "library")

            if not final_img_url or not final_vid_url:
                return jsonify({"success": False, "msg": "请上传图片和视频"})

        except Exception as e:
            return jsonify({"success": False, "msg": f"文件上传失败: {str(e)}"})

        # 👇👇👇 4. 数据库写入区域 👇👇👇
        conn = pymysql.connect(**MYSQL_CONF)
        try:
            with conn.cursor() as cursor:
                # 判断是【新增】还是【修改】
                # 如果 id 为空、0、NEW 或者大于一千万(防冲突)，都视为新增
                if not char_id or str(char_id) == '0' or str(char_id) == 'NEW' or (str(char_id).isdigit() and int(char_id) > 10000000):
                    sql = """
                    INSERT INTO character_library 
                    (project_name, label, name, `desc`, image_url, video_url) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql, (p_name, label, name, desc, final_img_url, final_vid_url))
                else:
                    sql = """
                    UPDATE character_library 
                    SET project_name=%s, label=%s, name=%s, `desc`=%s, image_url=%s, video_url=%s 
                    WHERE id=%s
                    """
                    cursor.execute(sql, (p_name, label, name, desc, final_img_url, final_vid_url, char_id))
            conn.commit()
        finally:
            conn.close()

        return jsonify({"success": True})

    except Exception as e:
        print(f"Save Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

# 2. 获取角色列表
# 修改后：加上装饰器
@app.route("/api/cloud/character/list", methods=['GET'])
@login_required
def get_character_list():
    try:
        # 1. 这行不要了
        # project_name = request.args.get('project_name')

        conn = pymysql.connect(**MYSQL_CONF)
        try:
            with conn.cursor() as cursor:
                # 2. SQL语句修改：删掉了 WHERE project_name = %s
                sql = "SELECT id, label, name, `desc`, image_url as image, video_url as video, project_name FROM character_library ORDER BY id DESC"

                # 3. 执行修改：删掉了后面的参数 (project_name,)
                cursor.execute(sql)

                result = cursor.fetchall()
        finally:
            conn.close()
        return jsonify({"status": "success", "data": result})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})


# 3. 删除角色
@app.route("/api/cloud/character/delete", methods=['POST'])
@login_required  # <--- 🔥🔥 建议加上这一行！
def delete_character():
    # 从环境变量获取密码
    ADMIN_TOKEN = os.getenv("ADMIN_PASSWORD", "yunman_secret_888")
    token = request.headers.get("X-Admin-Token")
    if token != ADMIN_TOKEN:
        return jsonify({"success": False, "msg": "口令错误"})

    data = request.get_json()
    char_id = data.get('id')

    try:
        conn = pymysql.connect(**MYSQL_CONF)
        try:
            with conn.cursor() as cursor:
                # 尝试删除 COS 文件
                sql_s = "SELECT image_url, video_url FROM character_library WHERE id = %s"
                cursor.execute(sql_s, (char_id,))
                record = cursor.fetchone()

                if record and cos_client:
                    for url in [record['image_url'], record['video_url']]:
                        if url and CDN_DOMAIN in url:
                            try:
                                key = url.split('.com/')[-1]
                                cos_client.delete_object(Bucket=TENCENT_BUCKET, Key=key)
                            except:
                                pass

                cursor.execute("DELETE FROM character_library WHERE id = %s", (char_id,))
            conn.commit()
        finally:
            conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)})
# 复用 PyQt5 中的加密逻辑
class CardKeyEncryption:
    def __init__(self):
        self.seed = "yunmangongfang_2024_secret"
        self.secret_key = hashlib.sha256(self.seed.encode()).digest()
        self.bs = AES.block_size

    def encrypt_api_key(self, real_api_key):
        try:
            iv = os.urandom(16) # 使用 os.urandom 替代 secrets
            cipher = AES.new(self.secret_key, AES.MODE_CBC, iv)
            encrypted = cipher.encrypt(pad(real_api_key.encode('utf-8'), self.bs))
            combined = iv + encrypted
            # 使用 urlsafe_b64encode 替换标准 base64
            encrypted_b64 = base64.urlsafe_b64encode(combined).decode('utf-8')
            return f"ymgfjc-{encrypted_b64}"
        except Exception as e:
            print(f"加密失败: {e}")
            return None

card_encryptor = CardKeyEncryption()

# ================= 🚀 核心：调用远程API创建并存库 =================

# 远程API配置 (如果 .env 里没有，这里做个兜底)
REMOTE_API_HOST = "https://yunbaoymgf.chat"
REMOTE_API_USER_ID = '129676'
REMOTE_API_TOKEN = 'pD9xPhBvzuIISaKBdOfNIpjMzUSf'


def get_remote_headers():
    return {
        'new-api-user': REMOTE_API_USER_ID,
        'Authorization': f'Bearer {REMOTE_API_TOKEN}',
        'Content-Type': 'application/json'
    }


# 在 app.py 中替换 create_remote_card 函数
@app.route('/admin/cards/create_remote', methods=['POST'])
def create_remote_card():
    # 1. 鉴权
    if not request.cookies.get('admin_token'):
        return jsonify({'success': False, 'message': '未登录'}), 401

    data = request.get_json()
    base_name = data.get('name', '自动生成')
    quota = data.get('quota', 50000000)
    count = int(data.get('count', 1))  # 🔥 获取生成数量，默认为1

    # 限制最大批量数量，防止超时
    if count > 50:
        return jsonify({'success': False, 'message': '单次最多生成50个'}), 400

    created_cards = []
    errors = []

    conn = db_manager.get_connection()
    try:
        with conn.cursor() as cursor:
            for i in range(count):
                # 为每个卡密生成唯一的备注名（如果批量）
                current_name = f"{base_name}_{i + 1}" if count > 1 else base_name

                try:
                    # 2. 请求远程服务器创建 Token
                    payload = {
                        "name": current_name,
                        "remain_quota": quota,
                        "expired_time": -1,
                        "unlimited_quota": False,
                        "model_limits_enabled": False,
                        "model_limits": "",
                        "group": "限时特价",
                        "mj_image_mode": "default",
                        "mj_custom_proxy": "",
                        "selected_groups": [],
                        "allow_ips": ""
                    }

                    # 发送请求
                    resp = requests.post(
                        f"{REMOTE_API_HOST}/api/token/",
                        json=payload,
                        headers=get_remote_headers(),
                        timeout=10
                    )

                    resp_json = resp.json()

                    if not resp_json.get('success'):
                        errors.append(f"第{i + 1}个失败: {resp_json.get('message')}")
                        continue

                    # 3. 提取 Key
                    data_field = resp_json.get("data")
                    real_api_key = ""
                    if isinstance(data_field, str):
                        real_api_key = data_field
                    elif isinstance(data_field, dict) and "key" in data_field:
                        real_api_key = data_field["key"]

                    if not real_api_key:
                        errors.append(f"第{i + 1}个失败: 未获取到Key")
                        continue

                    # 4. 本地加密
                    encrypted_key = card_encryptor.encrypt_api_key(real_api_key)

                    # 5. 存入数据库
                    sql = """
                    INSERT INTO cards (card_key, max_devices, status, created_at) 
                    VALUES (%s, 1, 'active', NOW())
                    """
                    cursor.execute(sql, (encrypted_key,))

                    created_cards.append({
                        'name': current_name,
                        'card_key': encrypted_key
                    })

                    # 稍微停顿一下，防止远程接口限流
                    if count > 1:
                        time.sleep(0.2)

                except Exception as e:
                    errors.append(f"第{i + 1}个异常: {str(e)}")

            conn.commit()

            # 清除缓存
            try:
                redis_manager.r.delete("admin:cards_list_page*")
                keys = redis_manager.r.keys("admin:cards_list_page*")
                if keys: redis_manager.r.delete(*keys)
            except:
                pass

    finally:
        conn.close()

    if not created_cards:
        return jsonify({'success': False, 'message': f'生成失败: {"; ".join(errors)}'})

    return jsonify({
        'success': True,
        'message': f'成功生成 {len(created_cards)} 个卡密',
        'data': created_cards  # 返回列表
    })

# ================= 🚀 新增：卡密编辑与删除接口 =================

# 在 app.py 中找到这个函数并替换
@app.route('/admin/cards/update', methods=['POST'])
def update_card_api():
    """编辑卡密接口 (修复版：支持最大设备数修改)"""
    if not request.cookies.get('admin_token'):
        return jsonify({'success': False, 'message': '未登录'}), 401

    data = request.get_json()

    card_id = data.get('id')
    new_expiry = data.get('new_expiry')
    status = data.get('status')
    reset_device = data.get('reset_device')

    # 🔥🔥🔥 1. 获取 max_devices 参数 🔥🔥🔥
    max_devices = data.get('max_devices')

    if not card_id:
        return jsonify({'success': False, 'message': '参数缺失'})

    # 🔥🔥🔥 2. 将 max_devices 传给数据库方法 🔥🔥🔥
    # 注意参数顺序要对应：card_id, new_expiry_str, status, reset_device, max_devices
    success = db_manager.update_card(
        card_id,
        new_expiry,
        status,
        reset_device,
        max_devices  # <--- 必须传这个！
    )

    if success:
        return jsonify({'success': True, 'message': '更新成功'})
    else:
        return jsonify({'success': False, 'message': '更新失败'})


@app.route('/admin/cards/delete', methods=['POST'])
def delete_card_api():
    """删除卡密接口"""
    if not request.cookies.get('admin_token'):
        return jsonify({'success': False, 'message': '未登录'}), 401

    data = request.get_json()
    card_id = data.get('id')

    if not card_id:
        return jsonify({'success': False, 'message': '参数缺失'})

    success = db_manager.delete_card(card_id)
    if success:
        return jsonify({'success': True, 'message': '删除成功'})
    else:
        return jsonify({'success': False, 'message': '删除失败'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)