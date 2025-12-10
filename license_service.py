import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel
import pymysql
from pymysql.cursors import DictCursor
import requests
import json
from datetime import datetime, timedelta

app = FastAPI()

# ================= 1. 数据库配置 =================
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


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


# ================= 2. 核心：首次激活扣费逻辑 =================
def activate_first_time_logic(api_key):
    """
    逻辑：
    1. 查是否是新卡 (Usage = 0)
    2. 强制调用 GPT-4 消耗 Token
    3. 只有消耗成功，才返回 True
    """
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    print(f"🔄 [激活流程] 正在检测卡密新旧: {api_key[:8]}...")

    try:
        # --- 1. 查使用量 (防止有人拿用过的废卡来激活) ---
        usage_url = f"{YUNWU_BASE}/v1/dashboard/billing/usage?start_date=2023-01-01&end_date=2030-01-01"
        resp_usage = requests.get(usage_url, headers=headers, timeout=10)

        if resp_usage.status_code != 200:
            return False, "卡密无效，无法查询余额"

        usage_data = resp_usage.json()
        total_usage = usage_data.get('total_usage', 0)

        # 💡 阈值设为 0.1，容忍极小的误差，但基本上必须是新卡
        if total_usage > 0.5:
            return False, "激活失败：该卡密已被使用过 (非新卡)"

        # --- 2. 强制消耗 Token (真正的激活动作) ---
        print("💸 [激活流程] 正在调用 GPT-4 扣除额度...")

        # 使用 GPT-4 确保单价够高，一定能扣掉钱
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "Activate license key validation sequence."}
            ],
            "max_tokens": 20,  # 消耗约 30-50 tokens
            "temperature": 0.5
        }

        chat_url = f"{YUNWU_BASE}/v1/chat/completions"
        resp_chat = requests.post(chat_url, headers=headers, json=payload, timeout=20)

        if resp_chat.status_code == 200:
            print("✅ [激活流程] 扣费成功！卡密已激活。")
            return True, "Success"
        else:
            print(f"❌ [激活流程] 扣费失败: {resp_chat.text}")
            return False, "激活失败：余额不足或无法扣费"

    except Exception as e:
        return False, f"网络错误: {str(e)}"


# ================= 3. 验证接口 =================
@app.post("/verify")
def verify_license(req: VerifyReq):
    key = req.card_key.strip()
    mid = req.machine_id.strip()
    raw = req.raw_key

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # === 第一步：查数据库 (看看是不是回头客) ===
            sql = "SELECT * FROM license_bindings WHERE card_key = %s"
            cursor.execute(sql, (key,))
            row = cursor.fetchone()

            if row:
                # 🟢 老用户逻辑：只比对机器码，不扣费
                print("🔒 [验证流程] 已存在记录，进行设备比对...")

                bound_mid = row['machine_id']
                db_status = row['status']

                # 1. 机器码不对 -> 滚蛋
                if bound_mid != mid:
                    return {"code": 403, "msg": f"一机一码校验失败：该卡已绑定其他设备(尾号{bound_mid[-4:]})"}

                # 2. 被封禁 -> 滚蛋
                if db_status != 'active':
                    return {"code": 403, "msg": "授权已被禁用"}

                return {
                    "code": 200,
                    "msg": "验证成功",
                    "expiry_date": str(row['expiry_date'])
                }

            else:
                # 🔵 新用户逻辑：必须扣费 + 绑定
                print("🆕 [验证流程] 新卡密，开始激活...")

                # 1. 执行扣费逻辑
                is_success, msg = activate_first_time_logic(key)
                if not is_success:
                    return {"code": 400, "msg": msg}

                # 2. 扣费成功 -> 绑定机器码 -> 存入数据库
                # 设置过期时间 (例如 10 年)
                default_expiry = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")

                insert_sql = """
                    INSERT INTO license_bindings 
                    (card_key, machine_id, expiry_date, status, raw_key) 
                    VALUES (%s, %s, %s, 'active', %s)
                """
                cursor.execute(insert_sql, (key, mid, default_expiry, raw))
                conn.commit()

                print(f"💾 [验证流程] 绑定成功！设备ID: {mid}")

                return {
                    "code": 200,
                    "msg": "激活成功 (已绑定当前设备)",
                    "expiry_date": default_expiry
                }

    except Exception as e:
        print(f"Server Error: {e}")
        return {"code": 500, "msg": "服务器内部错误"}
    finally:
        conn.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)