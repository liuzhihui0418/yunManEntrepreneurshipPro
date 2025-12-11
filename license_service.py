import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime, timedelta

app = FastAPI()

# ================= 1. 配置 =================
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "aini7758258!!",
    "db": "invite_code_system",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

# 🔥 配置：一个卡密允许绑定多少台设备
# 1 = 严格一机一码
# 2 = 允许家里和公司各一台
MAX_DEVICES_PER_KEY = 1

# 🔥 配置：默认授权时长 (例如 10 年)
DEFAULT_LICENSE_DAYS = 3650


class VerifyReq(BaseModel):
    card_key: str
    machine_id: str
    raw_key: str = None


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


# ================= 2. 核心验证接口 =================
@app.post("/verify")
def verify_license(req: VerifyReq):
    key = req.card_key.strip()  # 这是解密后的真实 Key
    mid = req.machine_id.strip()  # 当前机器码
    raw = req.raw_key

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # -------------------------------------------------------
            # 步骤 1: 查询该卡密目前所有的绑定记录
            # -------------------------------------------------------
            sql_query = "SELECT * FROM license_bindings WHERE card_key = %s"
            cursor.execute(sql_query, (key,))
            bindings = cursor.fetchall()

            # 提取该卡密已绑定的所有机器码
            bound_machine_ids = [row['machine_id'] for row in bindings]

            # 检查当前卡密状态 (如果有一条被禁用，则整体禁用)
            for row in bindings:
                if row['status'] != 'active':
                    return {"code": 403, "msg": "该授权已被封禁，请联系管理员"}

            # -------------------------------------------------------
            # 步骤 2: 判断逻辑
            # -------------------------------------------------------

            # 情况 A: 当前机器码已经在库里 -> ✅ 验证通过 (老用户)
            if mid in bound_machine_ids:
                # 获取该设备的过期时间 (取第一条记录的时间即可，或者根据具体逻辑)
                expiry = bindings[0]['expiry_date']
                return {
                    "code": 200,
                    "msg": "验证成功",
                    "expiry_date": str(expiry)
                }

            # 情况 B: 机器码不在库里 -> 🆕 尝试激活新设备
            else:
                current_count = len(bound_machine_ids)

                # 检查是否超过最大设备限制
                if current_count >= MAX_DEVICES_PER_KEY:
                    return {
                        "code": 403,
                        "msg": f"激活失败：该卡密已绑定 {current_count}/{MAX_DEVICES_PER_KEY} 台设备，无法在更多设备上使用。"
                    }

                # 未超过限制 -> ✅ 允许激活绑定
                print(f"🆕 [激活] 卡密 {key[:8]}... 绑定新设备: {mid}")

                # 计算过期时间
                # 如果是该卡密的第1个设备，计算新的过期时间
                # 如果是第2个设备，应该继承第1个设备的过期时间 (防止无限续杯)
                if current_count > 0:
                    expiry_date = bindings[0]['expiry_date']
                else:
                    expiry_date = (datetime.now() + timedelta(days=DEFAULT_LICENSE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

                # 插入绑定记录
                insert_sql = """
                    INSERT INTO license_bindings 
                    (card_key, machine_id, expiry_date, status, raw_key) 
                    VALUES (%s, %s, %s, 'active', %s)
                """
                cursor.execute(insert_sql, (key, mid, expiry_date, raw))
                conn.commit()

                return {
                    "code": 200,
                    "msg": "激活成功 (新设备已绑定)",
                    "expiry_date": str(expiry_date)
                }

    except Exception as e:
        print(f"❌ Server Error: {e}")
        return {"code": 500, "msg": "服务器内部验证错误"}
    finally:
        conn.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)