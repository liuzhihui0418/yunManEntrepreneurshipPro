import threading
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
import os
import uuid

# 引入管理器
from db.redis_manager import redis_manager
from db.database import db_manager

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

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

    t = threading.Thread(target=background_write_mysql, args=(code, expires_days, note))
    t.start()

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

            # 1. 极速写入 Redis
            redis_manager.add_single_code(code, expires_days)
            created_codes.append(code)

            # 2. 异步写入 MySQL
            def background_write_mysql(c, d, n):
                db_manager.create_invite_code(c, d, n)

            t = threading.Thread(target=background_write_mysql, args=(code, expires_days, note))
            t.start()
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


if __name__ == '__main__':
    # 启动时预热一次即可
    try:
        with app.app_context():
            redis_manager.sync_mysql_to_redis()
    except Exception as e:
        print(f"预热失败: {e}")

    app.run(host='0.0.0.0', port=5000, debug=True)