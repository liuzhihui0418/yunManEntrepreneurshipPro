import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel
import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime, timedelta

app = FastAPI()

# 数据库配置 (请填入你的真实信息)
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "你的数据库密码",
    "db": "invite_code_system",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}


def get_db():
    return pymysql.connect(**DB_CONFIG)


# === 请求模型 ===
# 1. 管理端生成卡密时发来的数据
class AddCardReq(BaseModel):
    card_key: str  # ymgfjc-...
    raw_key: str  # sk-...
    max_devices: int = 1
    amount: float = 0


# 2. 客户端验证时发来的数据
class VerifyReq(BaseModel):
    card_key: str
    machine_id: str


# ==========================================
# 接口 A: 管理员把卡密存入数据库 (供生成器调用)
# ==========================================
@app.post("/admin/add_card")
def add_card(req: AddCardReq):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 1. 先查重
            sql_check = "SELECT id FROM cards WHERE card_key = %s"
            cursor.execute(sql_check, (req.card_key,))
            if cursor.fetchone():
                return {"code": 400, "msg": "卡密已存在"}

            # 2. 插入到仓库表
            sql_insert = """
                INSERT INTO cards (card_key, raw_key, max_devices, total_tokens, status)
                VALUES (%s, %s, %s, %s, 'active')
            """
            cursor.execute(sql_insert, (req.card_key, req.raw_key, req.max_devices, req.amount))
            conn.commit()
            return {"code": 200, "msg": "入库成功"}
    except Exception as e:
        return {"code": 500, "msg": str(e)}
    finally:
        conn.close()


# ==========================================
# 接口 B: 用户软件验证激活 (核心逻辑)
# ==========================================
@app.post("/verify")
def verify_license(req: VerifyReq):
    key = req.card_key.strip()
    mid = req.machine_id.strip()

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # --- 1. 检查卡密是否有效 (查 cards 表) ---
            sql_card = "SELECT * FROM cards WHERE card_key = %s"
            cursor.execute(sql_card, (key,))
            card_info = cursor.fetchone()

            if not card_info:
                return {"code": 404, "msg": "无效的卡密 (未找到记录)"}

            if card_info['status'] != 'active':
                return {"code": 403, "msg": "该卡密已被封禁"}

            # --- 2. 检查这台机器是否已经绑定过 (查 license_bindings 表) ---
            sql_bind = "SELECT * FROM license_bindings WHERE card_key = %s AND machine_id = %s"
            cursor.execute(sql_bind, (key, mid))
            existing_bind = cursor.fetchone()

            # 🟢 情况一：老熟人 (已绑定的机器)
            if existing_bind:
                # 检查是否过期 (如果有过期逻辑)
                # expiry = existing_bind['expiry_date']
                # if expiry < datetime.now(): return ...

                return {
                    "code": 200,
                    "msg": "验证成功",
                    "expiry_date": str(existing_bind['expiry_date']),
                    "raw_key": card_info['raw_key']  # 下发真实Key
                }

            # 🔴 情况二：新设备 (尝试激活)
            else:
                # 2.1 统计该卡密目前已经绑定了多少台
                sql_count = "SELECT COUNT(*) as cnt FROM license_bindings WHERE card_key = %s"
                cursor.execute(sql_count, (key,))
                res = cursor.fetchone()
                current_used = res['cnt']
                limit_max = card_info['max_devices']

                # 2.2 判断是否超限
                if current_used >= limit_max:
                    return {
                        "code": 403,
                        "msg": f"激活失败：该卡密限制 {limit_max} 台设备，当前已激活 {current_used} 台。"
                    }

                # 2.3 未超限 -> 执行绑定
                # 默认给 10 年有效期
                expiry_date = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")

                sql_insert_bind = """
                    INSERT INTO license_bindings (card_key, machine_id, expiry_date, status)
                    VALUES (%s, %s, %s, 'active')
                """
                cursor.execute(sql_insert_bind, (key, mid, expiry_date))
                conn.commit()

                return {
                    "code": 200,
                    "msg": f"新设备激活成功 (第 {current_used + 1}/{limit_max} 台)",
                    "expiry_date": expiry_date,
                    "raw_key": card_info['raw_key']
                }

    except Exception as e:
        print(f"Error: {e}")
        return {"code": 500, "msg": "服务器验证异常"}
    finally:
        conn.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)