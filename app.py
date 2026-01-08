# -*- coding: utf-8 -*-
import threading
import os
import uuid
import time
import pymysql
import base64
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

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

# ==========================================
# 0. 加载 .env 环境变量 (最先执行)
# ==========================================
# 这行代码会自动读取同目录下的 .env 文件
load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')

# 允许所有来源跨域
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. 全局配置与密钥 (已改为从环境变量读取)
# ==========================================

# --- 支付宝配置 ---
ALIPAY_APP_ID = os.getenv("ALIPAY_APP_ID")
PRIVATE_KEY_CONTENT = os.getenv("PRIVATE_KEY_CONTENT")
ALIPAY_PUBLIC_KEY_CONTENT = os.getenv("ALIPAY_PUBLIC_KEY_CONTENT")

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
def fix_key_format(key_content, is_private=True):
    if not key_content:
        return ""
    # 清洗掉可能存在的头尾和空格
    key_content = key_content.replace("-----BEGIN RSA PRIVATE KEY-----", "").replace("-----END RSA PRIVATE KEY-----",
                                                                                     "")
    key_content = key_content.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", "")
    key_content = key_content.replace("-----BEGIN PUBLIC KEY-----", "").replace("-----END PUBLIC KEY-----", "")
    key_content = key_content.replace("\n", "").replace(" ", "").strip()

    # 补全 padding
    missing_padding = len(key_content) % 4
    if missing_padding: key_content += '=' * (4 - missing_padding)

    # 重新切分，每64字符一行
    split_key = '\n'.join([key_content[i:i + 64] for i in range(0, len(key_content), 64)])

    if is_private:
        return f"-----BEGIN PRIVATE KEY-----\n{split_key}\n-----END PRIVATE KEY-----"
    else:
        return f"-----BEGIN PUBLIC KEY-----\n{split_key}\n-----END PUBLIC KEY-----"


# 格式化密钥
FINAL_PRIVATE_KEY = fix_key_format(PRIVATE_KEY_CONTENT, True)
FINAL_PUBLIC_KEY = fix_key_format(ALIPAY_PUBLIC_KEY_CONTENT, False)


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

# 辅助函数：上传 Base64 到腾讯云 COS
def ensure_url_logic(data_str: str, max_size_mb: float, sub_folder: str = "library"):
    if not data_str:
        return None

    # 如果已经是 http 开头，说明没修改图片，直接返回
    if data_str.startswith("http"):
        return data_str

    # 解析 Base64
    if "base64," in data_str:
        try:
            if not cos_client:
                raise Exception("COS 客户端未初始化，请检查密钥")

            header, encoded = data_str.split("base64,", 1)
            # 简单的扩展名提取
            ext = "png"
            if "jpeg" in header: ext = "jpg"
            if "video" in header: ext = "mp4"

            file_content = base64.b64decode(encoded)

            # 大小检查
            size_mb = len(file_content) / (1024 * 1024)
            if size_mb > max_size_mb:
                raise ValueError(f"文件过大({size_mb:.1f}MB)，限制{max_size_mb}MB")

            # 生成文件名并上传
            filename = f"{sub_folder}/{uuid.uuid4().hex}.{ext}"
            cos_client.put_object(Bucket=TENCENT_BUCKET, Body=file_content, Key=filename)

            # 返回 CDN 链接
            return f"{CDN_DOMAIN}/{filename}"
        except Exception as e:
            print(f"COS 上传异常: {e}")
            raise e
    return None


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
        return render_template('index.html')
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
        # 1. 获取前端传来的 device_id (必须由前端生成并传递)
        device_id = data.get('device_id', '').strip()

        if not code:
            return jsonify({'success': False, 'message': '请输入邀请码'}), 400

        # 2. 强制要求传输设备指纹
        if not device_id:
            return jsonify({'success': False, 'message': '环境异常：无法识别设备指纹，请刷新页面重试'}), 400

        # ================== 🚀 核心修改开始 ==================
        # 3. 调用数据库进行设备绑定检查
        # 只有这一步通过了，才去跑后面的 Redis 逻辑
        bind_result = db_manager.check_and_bind_device(code, device_id)

        if not bind_result['success']:
            # 如果绑定失败（设备超限），直接返回 403 错误
            return jsonify({'success': False, 'message': bind_result['msg']}), 403
        # ================== 核心修改结束 ==================

        # 4. 设备验证通过，继续执行原有的 Redis 验证逻辑 (次数、过期等)
        result = redis_manager.validate_and_use_code(code)

        if result['valid']:
            session_id = redis_manager.create_session(code)
            user_info = redis_manager.get_session_info(session_id)
            resp = jsonify({'success': True, 'session_id': session_id, 'user': user_info, 'message': '成功'})
            resp.set_cookie(
                'session_id',
                session_id,
                max_age=86400,
                httponly=True,
                samesite='None',
                secure=True
            )
            return resp
        return jsonify({'success': False, 'message': result['message']}), 401

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


# ==========================================
# 🚀 风格角色库 API (已完美移植合并)
# ==========================================

@app.route('/style_library')
def style_library_page():
    # 访问此页面：http://139.199.176.16:5000/style_library
    return render_template('style_library.html')


# 1. 保存/更新角色
@app.route("/api/cloud/character/save", methods=['POST'])
def save_character_db():
    try:
        data = request.get_json()

        label = data.get('label', '').strip()
        name = data.get('name', '').strip()
        desc = data.get('desc', '').strip()
        p_name = data.get('project_name', '').strip()
        image_raw = data.get('image')
        video_raw = data.get('video')

        if not all([label, name, desc, p_name, image_raw, video_raw]):
            return jsonify({"success": False, "msg": "所有字段（标签、名称、描述、图片、视频）都必须填写！"})

        if name in ["@new.character", "New Role"]:
            return jsonify({"success": False, "msg": "请修改默认代号"})

        # 上传处理
        try:
            img_val = ensure_url_logic(image_raw, max_size_mb=2.0)
            vid_val = ensure_url_logic(video_raw, max_size_mb=10.0)
        except ValueError as ve:
            return jsonify({"success": False, "msg": str(ve)})
        except Exception as e:
            return jsonify({"success": False, "msg": f"文件上传失败: {str(e)}"})

        conn = pymysql.connect(**MYSQL_CONF)
        try:
            with conn.cursor() as cursor:
                char_id = data.get('id')
                # 判断新增逻辑
                if not char_id or str(char_id) == '0' or str(char_id) == 'NEW' or (
                        str(char_id).isdigit() and int(char_id) > 10000000):
                    sql = """
                    INSERT INTO character_library (project_name, label, name, `desc`, image_url, video_url) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql, (p_name, label, name, desc, img_val, vid_val))
                else:
                    sql = """
                    UPDATE character_library 
                    SET project_name=%s, label=%s, name=%s, `desc`=%s, image_url=%s, video_url=%s 
                    WHERE id=%s
                    """
                    cursor.execute(sql, (p_name, label, name, desc, img_val, vid_val, char_id))
            conn.commit()
        finally:
            conn.close()

        return jsonify({"success": True})
    except Exception as e:
        print(f"Save Error: {e}")
        return jsonify({"success": False, "msg": str(e)})


# 2. 获取角色列表
@app.route("/api/cloud/character/list", methods=['GET'])
def get_character_list():
    try:
        project_name = request.args.get('project_name')
        conn = pymysql.connect(**MYSQL_CONF)
        try:
            with conn.cursor() as cursor:
                sql = "SELECT id, label, name, `desc`, image_url as image, video_url as video, project_name FROM character_library WHERE project_name = %s ORDER BY id DESC"
                cursor.execute(sql, (project_name,))
                result = cursor.fetchall()
        finally:
            conn.close()
        return jsonify({"status": "success", "data": result})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})


# 3. 删除角色
@app.route("/api/cloud/character/delete", methods=['POST'])
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)