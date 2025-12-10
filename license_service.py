# license_service.py
import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel
import pymysql
from pymysql.cursors import DictCursor
import requests
import json
from datetime import datetime, timedelta

app = FastAPI()

# ================= 1. MySQL 数据库配置 =================
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "aini7758258!!",  # 你的数据库密码
    "db": "invite_code_system",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

# 云雾 API 配置
YUNWU_BASE = "https://yunwu.ai"


class VerifyReq(BaseModel):
    card_key: str
    machine_id: str
    raw_key: str = None


# ================= 2. 数据库初始化 =================
def init_db():
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS license_bindings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    card_key VARCHAR(255) NOT NULL UNIQUE,
                    machine_id VARCHAR(255) NOT NULL,
                    expiry_date DATETIME,
                    status ENUM('active', 'banned') DEFAULT 'active',
                    raw_key TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
        conn.commit()
        print("✅ 数据库表检测/创建完成")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
    finally:
        if conn: conn.close()


init_db()


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


# ================= 3. 🔥🔥🔥 核心：消耗性验证逻辑 🔥🔥🔥 =================
def activate_new_card_upstream(api_key):
    """
    针对新卡的激活逻辑：
    1. 查使用量：必须为 0 (纯新卡)。
    2. 发请求：强制消耗一点额度。
    """
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    try:
        # --- 第1步：检查卡密是否是全新的 (Usage == 0) ---
        usage_url = f"{YUNWU_BASE}/v1/dashboard/billing/usage?start_date=2023-01-01&end_date=2030-01-01"
        resp_usage = requests.get(usage_url, headers=headers, timeout=10)

        if resp_usage.status_code != 200:
            return False, "❌ 卡密无效，云端查询失败"

        usage_data = resp_usage.json()
        total_usage = usage_data.get('total_usage', 0)

        # ⚠️ 严格校验：只要用过一点点，就不是新卡，拒绝激活
        # (因为如果是你本人激活的，数据库里应该有记录；数据库没记录且已使用，说明是别人用过的卡)
        if total_usage > 0:  # 这里可以根据情况设个阈值，比如 > 0.1
            return False, "❌ 该卡密已被使用过 (非新卡)，无法在新设备激活"

        # --- 第2步：强制消耗额度 (发起一次极小的对话) ---
        # 目的：让 total_usage 变成 > 0，标记该卡已被激活
        payload = {
            "model": "gpt-3.5-turbo",  # 选个便宜的模型
            "messages": [{"role": "user", "content": "verify"}],  # 发个极短的内容
            "max_tokens": 5,  # 限制回复长度，省钱
            "temperature": 0
        }

        chat_url = f"{YUNWU_BASE}/v1/chat/completions"
        resp_chat = requests.post(chat_url, headers=headers, json=payload, timeout=20)

        if resp_chat.status_code == 200:
            # 消费成功！说明卡密有效且已标记为“已使用”
            return True, "验证通过"
        else:
            return False, f"❌ 激活失败，无法扣除余额 (Code: {resp_chat.status_code})"

    except Exception as e:
        return False, f"上游网络连接错误: {str(e)}"


# ================= 4. 验证接口 =================
@app.post("/verify")
def verify_license(req: VerifyReq):
    key = req.card_key.strip()
    mid = req.machine_id.strip()
    raw = req.raw_key

    if not key or not mid:
        return {"code": 400, "msg": "参数缺失"}

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 1. 先查自己数据库：我是不是已经激活过这卡了？
            sql = "SELECT * FROM license_bindings WHERE card_key = %s"
            cursor.execute(sql, (key,))
            row = cursor.fetchone()

            if row:
                # ==============================
                # 🔥 场景 A: 老用户 (库里有记录)
                # ==============================
                bound_mid = row['machine_id']
                db_expiry = row['expiry_date']
                db_status = row['status']

                # 1.1 校验机器码 (一机一码核心)
                if bound_mid != mid:
                    return {
                        "code": 403,
                        "status": "fail",
                        "msg": f"❌ 校验失败：该卡密已绑定设备(尾号{bound_mid[-4:]})，当前设备无法使用。"
                    }

                # 1.2 检查封禁状态
                if db_status != 'active':
                    return {"code": 403, "status": "fail", "msg": "❌ 该授权已被管理员禁用"}

                # 1.3 检查过期
                if db_expiry and datetime.now() > db_expiry:
                    return {"code": 403, "status": "fail", "msg": f"❌ 授权已于 {db_expiry} 过期"}

                return {
                    "code": 200,
                    "status": "success",
                    "msg": "验证成功 (老用户)",
                    "expiry_date": str(db_expiry)
                }

            else:
                # ==============================
                # 🔥 场景 B: 新用户 (库里没记录)
                # ==============================

                # 1. 核心逻辑：去上游查是不是新卡，并消耗额度
                is_valid, reason = activate_new_card_upstream(key)

                if not is_valid:
                    # 如果上游说这卡用过了(usage>0)，或者余额不足扣款失败
                    return {"code": 400, "status": "fail", "msg": reason}

                # 2. 上游验证并扣款成功，开始计算本地过期时间
                default_expiry = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")

                # 3. 写入数据库 (绑定当前机器码)
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
                    "msg": "✅ 激活成功 (首次绑定设备)",
                    "expiry_date": default_expiry
                }

    except Exception as e:
        print(f"Server Error: {e}")
        return {"code": 500, "status": "error", "msg": f"系统内部错误: {str(e)}"}
    finally:
        if conn: conn.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)