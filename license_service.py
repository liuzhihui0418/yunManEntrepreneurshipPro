# license_service.py
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import pymysql  # 换成 MySQL 驱动
from pymysql.cursors import DictCursor
import requests
from datetime import datetime, timedelta

app = FastAPI()

# ================= 1. MySQL 数据库配置 =================
DB_CONFIG = {
    "host": "127.0.0.1",  # 脚本在服务器本机运行，连本地即可
    "port": 3306,  # MySQL 默认端口
    "user": "root",  # 你的用户名
    "password": "Aini7758258!!",  # 🔥 你的数据库密码 (强烈建议修改)
    "db": "invite_code_system",  # 你的数据库名
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

YUNWU_URL = "https://yunwu.ai/v1/dashboard/billing/usage"


class VerifyReq(BaseModel):
    card_key: str
    machine_id: str
    raw_key: str = None  # 🔥 新增可选字段

# ================= 2. 自动建表 (MySQL版) =================
def init_db():
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            # 创建绑定关系表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS license_bindings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    card_key VARCHAR(255) NOT NULL UNIQUE,
                    machine_id VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
        conn.commit()
        print("✅ MySQL 表 license_bindings 检测/创建完成")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
    finally:
        if conn: conn.close()


# 启动时运行一次
init_db()


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


def check_upstream_validity(api_key):
    """上游查余额校验"""
    try:
        headers = {'Authorization': f'Bearer {api_key}'}
        resp = requests.get(f"{YUNWU_URL}?start_date=2023-01-01&end_date=2030-01-01", headers=headers, timeout=5)

        if resp.status_code == 200:
            return True, "有效卡密"
        elif resp.status_code == 401:
            return False, "无效的卡密"
        else:
            return False, f"上游接口错误: {resp.status_code}"
    except Exception as e:
        return False, f"网络错误: {str(e)}"


# ================= 3. 核心验证接口 =================


# ================= 核心验证接口 (升级版) =================
@app.post("/verify")
def verify_license(req: VerifyReq):
    # key: 解密后的真实 API Key
    # req.card_key: 这里客户端发来的其实是解密后的。
    # 如果你想存原始加密串，客户端需要多发一个参数，或者我们暂且只存解密后的做唯一标识。

    key = req.card_key.strip()
    mid = req.machine_id.strip()
    raw = req.raw_key  # 获取原始卡密

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 1. 查库：这个卡密是否存在？
            # 这里的 card_key 存的是解密后的 Key (如 sk-xxxx 或 y0Ekim...)
            sql = "SELECT * FROM license_bindings WHERE card_key = %s"
            cursor.execute(sql, (key,))
            row = cursor.fetchone()

            # === 情况 A: 老用户 (库里有) ===
            if row:
                bound_mid = row['machine_id']
                db_expiry = row.get('expiry_date')  # 获取数据库里的过期时间
                db_status = row.get('status')  # 获取状态 (active/banned)

                # 1.1 检查机器码
                if bound_mid != mid:
                    return {"code": 403, "status": "fail", "msg": f"该码已绑定其他设备(尾号{bound_mid[-4:]})"}

                # 1.2 🔥🔥🔥 核心：检查是否被手动禁用 🔥🔥🔥
                if db_status != 'active':
                    return {"code": 403, "status": "fail", "msg": "该授权已被管理员禁用"}

                # 1.3 🔥🔥🔥 核心：检查是否过期 🔥🔥🔥
                if db_expiry and datetime.now() > db_expiry:
                    return {"code": 403, "status": "fail", "msg": f"授权已于 {db_expiry} 过期，请续费"}

                # 全部通过，告诉客户端最新的过期时间
                return {
                    "code": 200,
                    "status": "success",
                    "msg": "验证成功",
                    "expiry_date": str(db_expiry)  # 把数据库的时间传回给客户端
                }

            # === 情况 B: 新用户 (首次激活) ===
            else:
                is_valid, reason = check_upstream_validity(key)
                if not is_valid:
                    return {"code": 400, "status": "fail", "msg": reason}

                # 默认过期时间：当前时间 + 365天 (或者你定死 2099年)
                # 你可以在这里控制新用户的默认时长
                default_expiry = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")

                # 🔥 写入数据库时，把 raw_key 也存进去
                insert_sql = """
                               INSERT INTO license_bindings 
                               (card_key, machine_id, expiry_date, status, raw_key) 
                               VALUES (%s, %s, %s, 'active', %s)
                           """
                cursor.execute(insert_sql, (key, mid, default_expiry, raw))
                conn.commit()

                return {
                    "code": 200,
                    "status": "success",
                    "msg": "激活成功 (首次绑定)",
                    "expiry_date": default_expiry
                }

    except Exception as e:
        return {"code": 500, "status": "error", "msg": f"系统错误: {str(e)}"}
    finally:
        if conn: conn.close()


if __name__ == "__main__":
    # 本地监听 9000，等待 Nginx 转发
    uvicorn.run(app, host="0.0.0.0", port=9000)