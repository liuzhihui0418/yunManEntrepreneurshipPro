import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel
import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime, timedelta

app = FastAPI()

# ================= 1. 数据库配置 =================
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "aini7758258!!",  # ⚠️ 请确认密码无误
    "db": "invite_code_system",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}


class VerifyReq(BaseModel):
    card_key: str  # 解密后的真实Key
    machine_id: str
    raw_key: str = None


def get_db_connection():
    # autocommit=True 可以防止忘了 commit，但最好还是手动控制
    conn = pymysql.connect(**DB_CONFIG)
    return conn


# ================= 2. 核心验证接口 =================
@app.post("/api/license/verify")
def verify_license(req: VerifyReq):
    print(f"\n📨 [收到请求] Key: {req.card_key} | Machine: {req.machine_id}")

    key = req.card_key.strip()
    mid = req.machine_id.strip()
    raw = req.raw_key

    # 🔥 1. 提前初始化时间变量，防止报错
    expiry_str = None

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # ---------------------------------------------------
            # 第一步：检查 Cards 表
            # ---------------------------------------------------
            sql_card = "SELECT * FROM cards WHERE card_key = %s"
            cursor.execute(sql_card, (key,))
            card_info = cursor.fetchone()

            if not card_info:
                return {"code": 404, "msg": "无效的卡密(服务端不存在该卡)"}

            if card_info['status'] != 'active':
                return {"code": 403, "msg": "该卡密已被封禁"}

            max_devices = card_info.get('max_devices') or 1

            # ---------------------------------------------------
            # 第二步：检查 Bindings 表
            # ---------------------------------------------------
            sql_bindings = "SELECT * FROM license_bindings WHERE card_key = %s"
            cursor.execute(sql_bindings, (key,))
            bindings = cursor.fetchall()

            # 检查该机器是否已绑定
            existing_record = next((b for b in bindings if b['machine_id'] == mid), None)

            if existing_record:
                print("♻️  设备已存在，直接返回成功")
                # 🔥 2. 统一取值
                expiry_str = str(existing_record['expiry_date'])
                return {
                    "code": 200,
                    "msg": "验证成功",
                    "expiry_date": expiry_str
                }

            # ---------------------------------------------------
            # 第三步：写入新绑定
            # ---------------------------------------------------
            if len(bindings) >= max_devices:
                return {"code": 403, "msg": "设备数已满"}

            print("📝 正在准备写入 license_bindings...")

            # 🔥 3. 计算过期时间 (赋值给 expiry_str)
            if len(bindings) > 0:
                # 如果有其他设备绑定过，跟随第一个设备的过期时间
                expiry_str = str(bindings[0]['expiry_date'])
            else:
                # 如果是首台设备，从现在起加10年
                expiry_str = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")

            # 🔥 4. 再次检查：确保 expiry_str 不为空
            if not expiry_str:
                raise ValueError("过期时间计算失败")

            insert_sql = """
                INSERT INTO license_bindings 
                (card_key, machine_id, raw_key, activation_time, status, expiry_date) 
                VALUES (%s, %s, %s, NOW(), 'active', %s)
            """
            cursor.execute(insert_sql, (key, mid, raw, expiry_str))

            conn.commit()
            print("🎉🎉🎉 写入成功！🎉🎉🎉")

            return {
                "code": 200,
                "msg": "激活成功",
                "expiry_date": expiry_str
            }

    except pymysql.err.IntegrityError as e:
        print(f"💥 数据库完整性错误: {e}")
        conn.rollback()
        return {"code": 500, "msg": "激活失败：卡密数据不一致"}

    except Exception as e:
        print(f"💥 系统严重错误: {e}")
        conn.rollback()
        # 这里把具体错误返回给前端，方便你看
        return {"code": 500, "msg": f"系统错误: {str(e)}"}

    finally:
        conn.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)