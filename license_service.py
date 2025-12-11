import uvicorn
from fastapi import FastAPI
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
    "password": "aini7758258!!",  # 请确保密码正确
    "db": "invite_code_system",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

# 默认过期天数 (如果在cards表里没有设置时长，则使用此默认值)
DEFAULT_LICENSE_DAYS = 3650


class VerifyReq(BaseModel):
    card_key: str  # 解密后的真实Key (对应数据库 cards.card_key)
    machine_id: str  # 机器码
    raw_key: str = None  # 原始卡密 (对应数据库 cards.raw_key)


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


# ================= 2. 核心验证接口 =================
# 🔥 修改点1: 路由地址要对应客户端请求的完整路径
@app.post("/api/license/verify")
def verify_license(req: VerifyReq):
    # 清洗数据
    key = req.card_key.strip()
    mid = req.machine_id.strip()
    raw = req.raw_key

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # =======================================================
            # 步骤 1: 先去 cards 表查这张卡是否存在、是否被封禁
            # =======================================================
            sql_card = "SELECT * FROM cards WHERE card_key = %s"
            cursor.execute(sql_card, (key,))
            card_info = cursor.fetchone()

            if not card_info:
                return {"code": 404, "msg": "无效的卡密，请检查输入"}

            if card_info['status'] != 'active':
                return {"code": 403, "msg": "该卡密已被封禁或暂停使用"}

            # 🔥 修改点2: 获取该卡允许的最大设备数 (来自数据库设置)
            # 如果数据库该字段为空，默认给 1 台
            max_devices = card_info.get('max_devices') or 1

            # =======================================================
            # 步骤 2: 查询 license_bindings 表，看绑定情况
            # =======================================================
            sql_bindings = "SELECT * FROM license_bindings WHERE card_key = %s"
            cursor.execute(sql_bindings, (key,))
            bindings = cursor.fetchall()

            # 提取已绑定的机器码列表
            bound_machine_ids = [row['machine_id'] for row in bindings]

            # 检查绑定记录的状态 (双重保险，如果绑定记录被单条封禁)
            for row in bindings:
                if row['status'] != 'active':
                    return {"code": 403, "msg": "您的设备授权已被封禁"}

            # =======================================================
            # 步骤 3: 核心判断逻辑
            # =======================================================

            # --- 情况 A: 老用户 (机器码已存在) ---
            if mid in bound_machine_ids:
                # 找到当前机器的这条记录
                current_record = next((item for item in bindings if item["machine_id"] == mid), None)
                expiry = current_record['expiry_date']

                # 可选：更新一下 activation_time 表示最近活跃
                # cursor.execute("UPDATE license_bindings SET activation_time=NOW() WHERE id=%s", (current_record['id'],))
                # conn.commit()

                return {
                    "code": 200,
                    "msg": "验证成功",
                    "expiry_date": str(expiry)
                }

            # --- 情况 B: 新设备 (尝试激活) ---
            else:
                current_count = len(bindings)

                # 🔥 修改点3: 使用 cards 表里的 max_devices 进行判断
                if current_count >= max_devices:
                    return {
                        "code": 403,
                        "msg": f"激活失败：该卡密最多支持 {max_devices} 台设备，当前已绑定 {current_count} 台。"
                    }

                print(f"🆕 [新设备激活] 卡号: {key} | 机器码: {mid}")

                # 计算过期时间
                # 逻辑：如果是该卡的第一台设备，生成过期时间。
                # 如果是第二台设备，为了防止第二台“续命”，应该继承第一台的过期时间。
                if current_count > 0:
                    expiry_date = bindings[0]['expiry_date']
                else:
                    # 这里也可以扩展：如果 cards 表里有 total_tokens 或 duration，可以在这里计算
                    expiry_date = (datetime.now() + timedelta(days=DEFAULT_LICENSE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

                # 🔥 修改点4: 写入数据库
                # 注意：SQL语句必须完全匹配你的截图中的字段
                insert_sql = """
                    INSERT INTO license_bindings 
                    (card_key, machine_id, raw_key, activation_time, status, expiry_date) 
                    VALUES (%s, %s, %s, NOW(), 'active', %s)
                """

                # 执行插入
                cursor.execute(insert_sql, (key, mid, raw, expiry_date))

                # 💥 重点：一定要 commit 否则数据不会写入硬盘
                conn.commit()

                return {
                    "code": 200,
                    "msg": f"激活成功 (设备 {current_count + 1}/{max_devices})",
                    "expiry_date": str(expiry_date)
                }

    except pymysql.err.IntegrityError as e:
        # 捕捉外键错误或唯一键冲突
        print(f"❌ 数据库完整性错误: {e}")
        return {"code": 500, "msg": "绑定失败：数据冲突或卡密无效"}

    except Exception as e:
        print(f"❌ 系统错误: {e}")
        conn.rollback()  # 出错回滚
        return {"code": 500, "msg": f"服务器内部错误: {str(e)}"}

    finally:
        conn.close()


if __name__ == "__main__":
    # 启动服务
    uvicorn.run(app, host="0.0.0.0", port=9000)