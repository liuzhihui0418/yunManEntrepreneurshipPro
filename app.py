from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import os

from db.redis_manager import redis_manager

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# --- 启动钩子：数据预热 ---
# 每次 Gunicorn 启动 Worker 时可能会执行，但为了保证数据一致，
# 建议在部署脚本中单独运行一次 sync，或者在这里加锁。
# 为简单起见，利用第一个请求触发或手动触发，这里演示启动时尝试同步。
try:
    with app.app_context():
        # 注意：多Worker模式下这会执行多次，但Redis HSET是幂等的，没有副作用，仅仅浪费一点启动IO
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


@app.route('/api/validate', methods=['POST'])
def validate_invite_code():
    """【极速版】验证接口"""
    try:
        data = request.get_json()
        code = data.get('invite_code', '').strip().upper()
        if not code: return jsonify({'success': False, 'message': '请输入邀请码'}), 400

        # 1. 全部走 Redis 内存验证 (速度 < 5ms)
        result = redis_manager.validate_and_use_code(code)

        if result['valid']:
            # 2. Redis 创建 Session
            session_id = redis_manager.create_session(code)
            user_info = redis_manager.get_session_info(session_id)

            return jsonify({
                'success': True,
                'session_id': session_id,
                'user': {'name': user_info['name'], 'avatar': user_info['avatar']},
                'message': '验证成功！'
            })
        else:
            return jsonify({'success': False, 'message': result['message']}), 401

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'message': '系统繁忙，请重试'}), 500


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


if __name__ == '__main__':
    # 开发环境才用这个，生产环境请用下面的 gunicorn 启动
    app.run(host='0.0.0.0', port=5000, debug=True)