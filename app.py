import os
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder='static', template_folder='templates')

# --- 数据库配置 ---
db_pass = os.getenv('yunManEntrepreneurshipPro', 'Aini7758258!!')
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://admin:{db_pass}@localhost/building_ai_db'

db = SQLAlchemy(app)

# --- 数据模型 ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

# --- 专门的favicon路由 ---
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'images'),
                             'logo.png', mimetype='image/png')

# --- 路由逻辑 ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password_hash, password):
        return jsonify({"code": 200, "msg": "登录成功！欢迎回来"})
    else:
        return jsonify({"code": 401, "msg": "账号或密码错误"}), 401

# 测试logo是否可访问
@app.route('/test-logo')
def test_logo():
    return send_from_directory('static/images', 'logo.png')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)