# license_service.py
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import pymysql  # 换成 MySQL 驱动
from pymysql.cursors import DictCursor
import requests
from datetime import datetime

app = FastAPI()

# ================= 1. MySQL 数据库配置 =================
DB_CONFIG = {
    "host": "127.0.0.1",  # 脚本在服务器本机运行，连本地即可
    "port": 3306,  # MySQL 默认端口
    "user": "root",  # 你的用户名
    "password": "Aini7758258",  # 🔥 你的数据库密码 (强烈建议修改)
    "db": "invite_code_system",  # 你的数据库名
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

YUNWU_URL = "https://yunwu.ai/v1/dashboard/billing/usage"


class VerifyReq(BaseModel):
    card_key: str
    machine_id: str


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
@app.post("/verify")
def verify_license(req: VerifyReq):
    key = req.card_key.strip()
    mid = req.machine_id.strip()

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 1. 查库：是否绑定过？
            sql = "SELECT machine_id FROM license_bindings WHERE card_key = %s"
            cursor.execute(sql, (key,))
            row = cursor.fetchone()

            # === 情况 A: 库里有记录 (老用户) ===
            if row:
                bound_mid = row['machine_id']
                if bound_mid == mid:
                    return {"code": 200, "status": "success", "msg": "验证成功 (老设备)"}
                else:
                    return {"code": 403, "status": "fail", "msg": f"激活失败：该码已绑定其他设备 (尾号{bound_mid[-4:]})"}

            # === 情况 B: 库里没记录 (新用户) ===
            else:
                # 2. 查上游
                is_valid, reason = check_upstream_validity(key)
                if not is_valid:
                    return {"code": 400, "status": "fail", "msg": reason}

                # 3. 写入绑定
                insert_sql = "INSERT INTO license_bindings (card_key, machine_id) VALUES (%s, %s)"
                cursor.execute(insert_sql, (key, mid))
                conn.commit()
                return {"code": 200, "status": "success", "msg": "激活成功 (首次绑定)"}

    except Exception as e:
        return {"code": 500, "status": "error", "msg": f"系统错误: {str(e)}"}
    finally:
        if conn: conn.close()


if __name__ == "__main__":
    # 本地监听 9000，等待 Nginx 转发
    uvicorn.run(app, host="127.0.0.1", port=9000)