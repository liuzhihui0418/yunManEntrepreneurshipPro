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

# 引入自定义管理器
from db.redis_manager import redis_manager
from db.database import db_manager
from pay.pay import fix_key_format, PRIVATE_KEY_CONTENT, ALIPAY_PUBLIC_KEY_CONTENT
from alipay import AliPay

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# --- 1. 全局配置区域 ---
# 将数据库配置提取到全局，所有函数都能访问
MYSQL_CONF = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "aini7758258!!",
    "db": "invite_code_system",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

# 支付宝配置
ALIPAY_APP_ID = "2021006117616884"
FINAL_PRIVATE_KEY = fix_key_format(PRIVATE_KEY_CONTENT, True)
FINAL_PUBLIC_KEY = fix_key_format(ALIPAY_PUBLIC_KEY_CONTENT, False)

# 线程池配置
executor = ThreadPoolExecutor(max_workers=5)

# --- 2. 启动逻辑 ---
try:
    with app.app_context():
        redis_manager.sync_mysql_to_redis()
except Exception as e:
    print(f"Redis同步警告: {e}")


# --- 3. 辅助函数 ---
def get_alipay_client():
    return AliPay(
        appid=ALIPAY_APP_ID,
        app_notify_url="http://139.199.176.16:5000/api/pay/notify",
        app_private_key_string=FINAL_PRIVATE_KEY,
        alipay_public_key_string=FINAL_PUBLIC_KEY,
        sign_type="RSA2"
    )


# --- 4. 路由接口 ---

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'images'), 'logo.png')


@app.route('/')
def index():
    session_id = request.cookies.get('session_id')
    if session_id and redis_manager.validate_session(session_id):
        return render_template('index.html')
    return render_template('login.html')


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
            resp = jsonify({
                'success': True,
                'session_id': session_id,
                'user': {'name': user_info['name'], 'avatar': user_info['avatar']},
                'message': '验证成功！'
            })
            resp.set_cookie('session_id', session_id, max_age=86400)
            return resp
        else:
            return jsonify({'success': False, 'message': result['message']}), 401
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'message': '系统繁忙'}), 500


@app.route('/api/check_session', methods=['GET'])
def check_session():
    session_id = request.cookies.get('session_id')
    if session_id:
        user_info = redis_manager.get_session_info(session_id)
        if user_info:
            return jsonify({'valid': True, 'user': user_info})
    return jsonify({'valid': False})


@app.route('/api/logout', methods=['POST'])
def logout():
    session_id = request.cookies.get('session_id')
    if session_id:
        redis_manager.destroy_session(session_id)
    return jsonify({'success': True})


# --- 管理员后台 ---

@app.route('/admin')
def admin_login_page():
    return render_template('admin_login.html')


@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if redis_manager.validate_admin_login(username, password):
        resp = jsonify({'success': True, 'redirect': '/admin/dashboard'})
        resp.set_cookie('admin_token', str(uuid.uuid4()), max_age=86400)
        return resp
    return jsonify({'success': False, 'message': '账号或密码错误'}), 401


@app.route('/admin/dashboard')
def admin_dashboard_page():
    if not request.cookies.get('admin_token'):
        return redirect('/admin')
    return render_template('admin.html')


@app.route('/admin/api/dashboard', methods=['GET'])
def get_dashboard_data():
    data = db_manager.get_dashboard_stats()
    return jsonify({'success': True, **data})


@app.route('/admin/codes', methods=['GET'])
def get_codes_list():
    codes = db_manager.get_all_codes()
    return jsonify({'success': True, 'codes': codes})


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

        # 异步写入MySQL
        executor.submit(db_manager.create_invite_code, code, expires_days, note)
        return jsonify({'success': True, 'message': '创建成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'错误: {e}'})


# --- 授权验证核心接口 ---
@app.route('/api/license/verify', methods=['POST'])
def verify_license_db():
    try:
        data = request.get_json()
        if not data: return jsonify({'code': 400, 'msg': '无请求数据'}), 400
        client_key = data.get('card_key', '').strip()
        mid = data.get('machine_id', '').strip()

        if not client_key or not mid:
            return jsonify({'code': 400, 'msg': '参数缺失'}), 400

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
                    if current_binding.get('status') != 'active': return jsonify(
                        {'code': 403, 'msg': '该设备授权已被禁用'})
                    expiry = current_binding['expiry_date']
                    if expiry and datetime.now() > expiry: return jsonify({'code': 403, 'msg': '授权已过期'})
                    return jsonify({'code': 200, 'msg': '验证通过', 'expiry_date': str(expiry)})

                if len(bindings) >= max_allowed:
                    return jsonify({'code': 403, 'msg': f'激活失败：额度已满 {max_allowed} 台'})

                new_expiry = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    "INSERT INTO license_bindings (card_key, machine_id, activation_time, status, expiry_date) VALUES (%s, %s, NOW(), 'active', %s)",
                    (client_key, mid, new_expiry))
                conn.commit()
                return jsonify({'code': 200, 'msg': '新设备激活成功', 'expiry_date': str(new_expiry)})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'code': 500, 'msg': f"服务器错误: {str(e)}"}), 500


# --- 支付模块接口 ---

@app.route('/api/pay/create', methods=['POST'])
def create_order():
    data = request.get_json()
    face_value = data.get('face_value')
    price = data.get('price')
    out_trade_no = f"ORD_{int(time.time())}_{uuid.uuid4().hex[:4].upper()}"
    alipay = get_alipay_client()
    order_res = alipay.api_alipay_trade_precreate(
        out_trade_no=out_trade_no,
        total_amount=str(price),
        subject=f"算力额度-{face_value}元"
    )
    qr_code = order_res.get("qr_code")
    if not qr_code: return jsonify({'code': 500, 'msg': '生成支付二维码失败'})
    return jsonify({'code': 200, 'qr_url': qr_code, 'order_no': out_trade_no})


@app.route('/api/pay/notify', methods=['POST'])
def pay_notify():
    data = request.form.to_dict()
    signature = data.pop("sign")
    alipay = get_alipay_client()
    if alipay.verify(data, signature):
        trade_status = data.get("trade_status")
        if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
            order_no = data.get("out_trade_no")
            conn = pymysql.connect(**MYSQL_CONF)
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id, card_key FROM compute_keys WHERE status=0 LIMIT 1 FOR UPDATE")
                    card = cursor.fetchone()
                    if card:
                        cursor.execute("UPDATE compute_keys SET status=1, order_no=%s, sold_at=NOW() WHERE id=%s",
                                       (order_no, card['id']))
                        conn.commit()
            finally:
                conn.close()
            return "success"
    return "fail"


@app.route('/api/pay/status/<order_no>', methods=['GET'])
def check_pay_status(order_no):
    # 现在这里可以正常访问全局的 MYSQL_CONF 了
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)