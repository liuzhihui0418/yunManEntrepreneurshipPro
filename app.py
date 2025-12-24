# -*- coding: utf-8 -*-
import threading
import os
import uuid
import time
import pymysql
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
from pymysql.cursors import DictCursor
from alipay import AliPay

# 引入项目现有的数据库管理器 (保持你原有的引用)
from db.redis_manager import redis_manager
from db.database import db_manager

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# ==========================================
# 1. 全局配置与密钥 (直接写在这里，防止引入报错)
# ==========================================

# 支付宝 APPID
ALIPAY_APP_ID = "2021006117616884"

# 你的应用私钥 (直接填入，确保格式正确)
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

# 支付宝公钥 (直接填入)
ALIPAY_PUBLIC_KEY_CONTENT = """
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAg3Al49jSZnlY9iPcunRgWZvgwT9X03z3L+oajd+3Yq8sq21F4r8XB/Pu0TuzqpR2uIjZis4DulE5LoB9JhDei9xw9If5y96QsoMmCmkBaDSBRwSko2TaJmA3MmgVOgWSRQ753Wgx5xffYOmmrPq/dQlGH0J91NaWyVf72kPgjgW6+1jq7rOHUc2aRlVF+SNwOPO9OI/8zk+2tmOZRvT2QvGnjteqe5zI1/cpZ9t4XkzFSMP84hn5xOHH5GTPXC1yM2U8quT+Vlte+I/2XwIx3zGq+PSnOPENwJHFS8bVFpkcYB91ZZFwBH2nLPua/kmMbh/j0h+/UcD8nrgrnlAdDQIDAQAB
"""


# 密钥清洗函数 (直接放在这里)
def fix_key_format(key_content, is_private=True):
    key_content = key_content.replace("-----BEGIN RSA PRIVATE KEY-----", "").replace("-----END RSA PRIVATE KEY-----",
                                                                                     "")
    key_content = key_content.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", "")
    key_content = key_content.replace("-----BEGIN PUBLIC KEY-----", "").replace("-----END PUBLIC KEY-----", "")
    key_content = key_content.replace("\n", "").replace(" ", "").strip()
    missing_padding = len(key_content) % 4
    if missing_padding: key_content += '=' * (4 - missing_padding)
    split_key = '\n'.join([key_content[i:i + 64] for i in range(0, len(key_content), 64)])
    if is_private:
        return f"-----BEGIN PRIVATE KEY-----\n{split_key}\n-----END PRIVATE KEY-----"
    else:
        return f"-----BEGIN PUBLIC KEY-----\n{split_key}\n-----END PUBLIC KEY-----"


# 格式化后的密钥
FINAL_PRIVATE_KEY = fix_key_format(PRIVATE_KEY_CONTENT, True)
FINAL_PUBLIC_KEY = fix_key_format(ALIPAY_PUBLIC_KEY_CONTENT, False)

# 核心：定义全局数据库配置 (所有函数都能访问)
MYSQL_CONF = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "aini7758258!!",
    "db": "invite_code_system",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

# 创建全局线程池
executor = ThreadPoolExecutor(max_workers=5)


# 初始化支付宝客户端
def get_alipay_client():
    return AliPay(
        appid=ALIPAY_APP_ID,
        app_notify_url="http://139.199.176.16:5000/api/pay/notify",  # 确保你的公网IP正确
        app_private_key_string=FINAL_PRIVATE_KEY,
        alipay_public_key_string=FINAL_PUBLIC_KEY,
        sign_type="RSA2"
    )


# ==========================================
# 2. 系统初始化与基础路由
# ==========================================

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
        return render_template('index.html')
    return render_template('login.html')


# ==========================================
# 3. 核心功能：支付与发货逻辑
# ==========================================

@app.route('/api/pay/create', methods=['POST'])
def create_order():
    """创建支付订单"""
    try:
        data = request.get_json()
        face_value = data.get('face_value')
        price = data.get('price')

        out_trade_no = f"ORD_{int(time.time())}_{uuid.uuid4().hex[:4].upper()}"
        alipay = get_alipay_client()

        # 电脑网站支付模式 (或者用 precreate 扫码模式)
        order_res = alipay.api_alipay_trade_precreate(
            out_trade_no=out_trade_no,
            total_amount=str(price),
            subject=f"算力充值-{face_value}元"
        )

        qr_code = order_res.get("qr_code")
        if not qr_code:
            return jsonify({'code': 500, 'msg': '无法生成支付二维码，请检查密钥配置'})

        return jsonify({'code': 200, 'qr_url': qr_code, 'order_no': out_trade_no})
    except Exception as e:
        print(f"创建订单失败: {e}")
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

                # --- 发货逻辑 ---
                conn = pymysql.connect(**MYSQL_CONF)
                try:
                    with conn.cursor() as cursor:
                        # 锁定一张未使用的卡密
                        cursor.execute("SELECT id, card_key FROM compute_keys WHERE status=0 LIMIT 1 FOR UPDATE")
                        card = cursor.fetchone()

                        if card:
                            cursor.execute(
                                "UPDATE compute_keys SET status=1, order_no=%s, sold_at=NOW() WHERE id=%s",
                                (order_no, card['id'])
                            )
                            conn.commit()
                            print(f"发货成功: 订单 {order_no} -> 卡密 {card['card_key']}")
                        else:
                            print("库存不足，无法发货")
                finally:
                    conn.close()
                return "success"
        return "fail"
    except Exception as e:
        print(f"回调处理错误: {e}")
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


# ==========================================
# 4. 原有功能：授权验证与用户管理
# ==========================================

@app.route('/api/validate', methods=['POST'])
def validate_invite_code():
    try:
        data = request.get_json()
        code = data.get('invite_code', '').strip().upper()
        if not code: return jsonify({'success': False, 'message': '请输入邀请码'}), 400
        result = redis_manager.validate_and_use_code(code)
        if result['valid']:
            session_id = redis_manager.create_session(code)
            user_info = redis_manager.get_session_info(session_id)
            resp = jsonify({'success': True, 'session_id': session_id, 'user': user_info, 'message': '成功'})
            resp.set_cookie('session_id', session_id, max_age=86400)
            return resp
        return jsonify({'success': False, 'message': result['message']}), 401
    except Exception:
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


@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    if redis_manager.validate_admin_login(data.get('username'), data.get('password')):
        resp = jsonify({'success': True, 'redirect': '/admin/dashboard'})
        resp.set_cookie('admin_token', str(uuid.uuid4()), max_age=86400)
        return resp
    return jsonify({'success': False, 'message': '账号密码错误'}), 401


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


@app.route('/api/check_session', methods=['GET'])
def check_session():
    session_id = request.cookies.get('session_id')
    if session_id:
        user_info = redis_manager.get_session_info(session_id)
        if user_info: return jsonify({'valid': True, 'user': user_info})
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)