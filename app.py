import threading
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
import os
import uuid
from concurrent.futures import ThreadPoolExecutor # 引入线程池
# 引入管理器
from db.redis_manager import redis_manager
from db.database import db_manager
import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime, timedelta
from flask import request, jsonify  # 确保引入了 request 和 jsonify
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)
# 在 app = Flask(__name__) 下面添加：
# 创建一个最大只有 5 个工人的线程池
executor = ThreadPoolExecutor(max_workers=5)
# --- 启动钩子：数据预热 ---
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


# --- 用户验证接口 ---
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


# ================= 管理员后台接口 =================

@app.route('/admin')
def admin_login_page():
    return render_template('admin_login.html')


@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    is_valid = redis_manager.validate_admin_login(username, password)

    if is_valid:
        resp = jsonify({'success': True, 'redirect': '/admin/dashboard'})
        resp.set_cookie('admin_token', str(uuid.uuid4()), max_age=86400)
        return resp
    else:
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


# --- 单个创建邀请码 ---
@app.route('/admin/codes', methods=['POST'])
def create_code():
    data = request.get_json()
    code = data.get('code')
    if not code:
        code = str(uuid.uuid4())[:8].upper()

    expires_days = int(data.get('expires_days', 7))
    note = data.get('note', '')

    # 1. 【极速响应】直接写入 Redis
    try:
        redis_manager.add_single_code(code, expires_days)
        # 清除缓存
        redis_manager.r.delete("admin:dashboard_stats")
        redis_manager.r.delete("admin:codes_list")
    except Exception as e:
        return jsonify({'success': False, 'message': f'Redis写入失败: {e}'})

    # 2. 【异步处理】后台线程写 MySQL
    def background_write_mysql(c, d, n):
        print(f"开始异步写入 MySQL: {c}")
        db_manager.create_invite_code(c, d, n)
        print(f"MySQL 写入完成: {c}")

        # 使用线程池提交任务
        executor.submit(background_write_mysql, code, expires_days, note)

    return jsonify({'success': True, 'message': '创建成功 (后台同步中)'})


# --- 批量创建邀请码 ---
@app.route('/admin/codes/batch', methods=['POST'])
def create_batch_codes():
    data = request.get_json()
    count = data.get('count', 1)
    prefix = data.get('prefix', '')
    expires_days = int(data.get('expires_days', 7))
    note = data.get('note', '')

    # 验证数量
    if count < 1 or count > 50:
        return jsonify({'success': False, 'message': '创建数量必须在1-50之间'}), 400

    created_codes = []

    try:
        # 批量创建邀请码
        for i in range(count):
            if prefix:
                # 使用前缀+随机后缀
                random_suffix = str(uuid.uuid4())[:8].upper()
                code = f"{prefix}_{random_suffix}"
            else:
                # 完全随机生成
                code = str(uuid.uuid4())[:8].upper()

                # 1. Redis (不变)
                redis_manager.add_single_code(code, expires_days)
                created_codes.append(code)

                # 2. 替换原本的 threading.Thread
                # 定义任务函数 (需要把函数移到循环外或者作为独立函数，这里为了简便直接用 lambda 或者 wrapper)
                # 建议直接调用 db_manager
                executor.submit(db_manager.create_invite_code, code, expires_days, note)

        # [新增] 强制清除总数缓存，这样回到列表页时总数才会增加
        redis_manager.r.delete("admin:total_codes_count")
        # 清除缓存
        redis_manager.r.delete("admin:dashboard_stats")
        redis_manager.r.delete("admin:codes_list")

        return jsonify({
            'success': True,
            'message': f'成功创建 {len(created_codes)} 个邀请码',
            'created_count': len(created_codes),
            'codes': created_codes
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'创建失败: {e}'}), 500


# --- 分页接口 ---
@app.route('/admin/api/dashboard/paginated', methods=['GET'])
def get_paginated_dashboard():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    data = db_manager.get_dashboard_stats_with_pagination(page, page_size)
    return jsonify({'success': True, **data})


@app.route('/admin/codes/paginated', methods=['GET'])
def get_paginated_codes():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    search = request.args.get('search', '')

    data = db_manager.get_codes_with_pagination(page, page_size, search)
    return jsonify({'success': True, **data})


# ==========================================
# 🔥 核心：数据库验证接口 (Flask版，直接复制)
# ==========================================
@app.route('/api/license/verify', methods=['POST'])
def verify_license_db():
    # 1. 数据库配置
    MYSQL_CONF = {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "aini7758258!!",
        "db": "invite_code_system",
        "charset": "utf8mb4",
        "cursorclass": DictCursor
    }

    try:
        # 获取客户端数据
        data = request.get_json()
        if not data:
            return jsonify({'code': 400, 'msg': '无数据'}), 400

        key = data.get('card_key', '').strip()  # 卡密
        mid = data.get('machine_id', '').strip()  # 设备ID
        raw = data.get('raw_key', '')  # 原始key

        print(f"📨 [DB验证] 收到请求 | Key: {key[:30]}... | Mid: {mid}")

        if not key or not mid:
            return jsonify({'code': 400, 'msg': '卡密或设备ID不能为空'}), 400

        # 连接数据库
        conn = pymysql.connect(**MYSQL_CONF)
        try:
            with conn.cursor() as cursor:
                # --- 步骤 A: 查卡是否存在（通过 card_key 字段）---
                sql_card = "SELECT * FROM cards WHERE card_key = %s"
                cursor.execute(sql_card, (key,))
                card = cursor.fetchone()

                if not card:
                    print(f"❌ 数据库中没有找到卡密: {key[:30]}...")
                    return jsonify({'code': 404, 'msg': '卡密错误，请充值或者联系管理员'})

                print(f"✅ 找到卡信息: ID={card.get('id')}, 状态={card.get('status')}")

                if card.get('status') != 'active':
                    return jsonify({'code': 403, 'msg': '卡密已封禁'})

                max_dev = card.get('max_devices') or 1

                # cards 表没有 expiry_date 字段，使用默认 10 年有效期
                card_expiry = datetime.now() + timedelta(days=3650)

                # --- 步骤 B: 查绑定情况 ---
                cursor.execute("SELECT * FROM license_bindings WHERE card_key = %s", (key,))
                bindings = cursor.fetchall()
                print(f"🔗 已绑定设备数: {len(bindings)}")

                # 检查是否是老设备
                existing_device = None
                for b in bindings:
                    if b.get('machine_id') == mid:
                        existing_device = b
                        break

                # 🔥🔥🔥 如果是老设备 🔥🔥🔥
                if existing_device:
                    print(f"🔍 找到已绑定设备: {mid}")

                    # 检查设备状态是否被封禁
                    if existing_device.get('status') != 'active':
                        print(f"🚫 设备已被封禁: {mid}")
                        return jsonify({
                            'code': 403,
                            'msg': '该设备已被封禁，无法使用',
                            'expiry_date': str(existing_device.get('expiry_date', card_expiry))
                        })

                    # 检查设备绑定是否过期
                    device_expiry = existing_device.get('expiry_date')
                    expiry_date = card_expiry  # 默认使用卡的有效期

                    if device_expiry:
                        if isinstance(device_expiry, str):
                            try:
                                device_expiry = datetime.strptime(device_expiry, "%Y-%m-%d %H:%M:%S")
                            except:
                                try:
                                    device_expiry = datetime.strptime(device_expiry, "%Y-%m-%d")
                                except:
                                    device_expiry = None

                        if device_expiry:
                            expiry_date = device_expiry

                            if datetime.now() > device_expiry:
                                print(f"🚫 老设备已过期: {mid} (过期时间: {device_expiry})")
                                return jsonify({
                                    'code': 403,
                                    'msg': f'授权已于 {device_expiry} 过期，请续费',
                                    'expiry_date': str(device_expiry)
                                })

                    print(f"♻️ 老设备验证通过: {mid}")
                    return jsonify({
                        'code': 200,
                        'msg': '验证成功',
                        'expiry_date': str(expiry_date)
                    })

                # 🔥🔥🔥 如果是新设备 🔥🔥🔥
                else:
                    print(f"🆕 新设备绑定: {mid}")

                    # 检查设备数是否已满
                    if len(bindings) >= max_dev:
                        print(f"⛔ 设备已满: {len(bindings)}/{max_dev}")
                        return jsonify({'code': 403, 'msg': '设备数已满'})

                    # 检查卡密是否已过期（基于卡默认的10年）
                    if datetime.now() > card_expiry:
                        print(f"🚫 卡密已过期: {card_expiry}")
                        return jsonify({
                            'code': 403,
                            'msg': f'该卡密已于 {card_expiry} 过期，无法激活新设备',
                            'expiry_date': str(card_expiry)
                        })

                    # 计算新设备的过期时间
                    expiry_to_use = card_expiry

                    # 如果有已绑定的设备，使用第一个设备的过期时间
                    if bindings:
                        first_binding = bindings[0]
                        device_expiry = first_binding.get('expiry_date')
                        if device_expiry:
                            if isinstance(device_expiry, str):
                                try:
                                    device_expiry = datetime.strptime(device_expiry, "%Y-%m-%d %H:%M:%S")
                                except:
                                    try:
                                        device_expiry = datetime.strptime(device_expiry, "%Y-%m-%d")
                                    except:
                                        device_expiry = None

                            if device_expiry:
                                expiry_to_use = device_expiry

                    print(f"📅 新设备过期时间: {expiry_to_use}")

                    # 写入新设备绑定
                    sql = """
                        INSERT INTO license_bindings 
                        (card_key, machine_id, raw_key, activation_time, status, expiry_date) 
                        VALUES (%s, %s, %s, NOW(), 'active', %s)
                    """

                    cursor.execute(sql, (key, mid, raw, expiry_to_use))
                    conn.commit()

                    print(f"🎉🎉🎉 新设备绑定成功！设备: {mid} 过期时间: {expiry_to_use}")
                    return jsonify({
                        'code': 200,
                        'msg': '激活成功',
                        'expiry_date': str(expiry_to_use)
                    })

        except Exception as db_error:
            print(f"❌ 数据库操作错误: {db_error}")
            if conn:
                conn.rollback()
            return jsonify({'code': 500, 'msg': f'数据库错误: {str(db_error)}'}), 500
        finally:
            if conn:
                conn.close()

    except Exception as e:
        print(f"❌ 验证报错: {e}")
        return jsonify({'code': 500, 'msg': f'服务器错误: {str(e)}'}), 500


if __name__ == '__main__':
    # 启动时预热一次即可
    try:
        with app.app_context():
            redis_manager.sync_mysql_to_redis()
    except Exception as e:
        print(f"预热失败: {e}")

    app.run(host='0.0.0.0', port=5000, debug=True)