import os

from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- 数据库配置 ---
# 替换为你刚才设置的密码
db_pass = os.getenv('yunManEntrepreneurshipPro', 'Aini7758258!!')
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://admin:{db_pass}@localhost/building_ai_db'

db = SQLAlchemy(app)


# --- 数据模型 ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


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


# --- 初始化命令 ---
# 在服务器运行 python app.py init 即可初始化数据库
import sys

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'init':
        with app.app_context():
            db.create_all()
            # 创建一个测试用户
            if not User.query.filter_by(username='admin').first():
                admin = User(username='admin', password_hash=generate_password_hash('123456'))
                db.session.add(admin)
                db.session.commit()
                print("数据库已初始化，默认用户 admin / 123456")
    else:
        app.run(host='0.0.0.0', port=5000)