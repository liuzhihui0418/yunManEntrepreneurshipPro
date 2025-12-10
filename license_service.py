# license_service.py
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import psycopg2
from datetime import datetime
import requests

app = FastAPI()

# ================= 配置区 (请填入你修改后的新密码) =================
# 既然是本机运行，host 写 localhost 即可，速度最快
DB_CONFIG = {
    "dbname": "invite_code_system",  # 你的数据库名，通常默认是 postgres，如果不是请修改
    "user": "root",  # 你的数据库用户名
    "password": "Aini7758258",  # 🔥🔥🔥 请填入你修改后的新密码 🔥🔥🔥
    "host": "43.135.26.58",
    "port": "3306"
}

# 上游查费接口
YUNWU_URL = "https://yunwu.ai/v1/dashboard/billing/usage"


class VerifyReq(BaseModel):
    card_key: str
    machine_id: str


# ================= 数据库工具 =================
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def check_upstream_validity(api_key):
    """双重校验：去云雾查询卡密是否有效/新卡"""
    try:
        headers = {'Authorization': f'Bearer {api_key}'}
        # 查一个很宽的时间范围，只要接口返回 200 且 usage=0 (可选)
        resp = requests.get(f"{YUNWU_URL}?start_date=2023-01-01&end_date=2030-01-01", headers=headers, timeout=5)

        if resp.status_code == 200:
            data = resp.json()
            # 这里你可以加逻辑：比如 total_usage > 0 就不让激活
            # 目前逻辑：只要 Key 能用，就允许激活
            return True, "有效卡密"
        elif resp.status_code == 401:
            return False, "无效的卡密 (401 Unauthorized)"
        else:
            return False, f"上游接口错误: {resp.status_code}"
    except Exception as e:
        return False, f"服务器网络错误: {str(e)}"


# ================= 核心接口 =================
@app.post("/verify")
def verify_license(req: VerifyReq):
    key = req.card_key.strip()
    mid = req.machine_id.strip()

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. 查询数据库：这个卡密是否存在？
        cur.execute("SELECT machine_id FROM license_bindings WHERE card_key = %s", (key,))
        row = cur.fetchone()

        # === 情况 A: 数据库里有记录 (老用户) ===
        if row:
            bound_mid = row[0]
            if bound_mid == mid:
                return {"code": 200, "status": "success", "msg": "验证成功 (已绑定本机)"}
            else:
                return {"code": 403, "status": "fail", "msg": f"激活失败：该码已绑定另一台设备 (尾号{bound_mid[-4:]})"}

        # === 情况 B: 数据库没记录 (新用户) ===
        else:
            # 2. 去上游 (Yunwu) 查一下是不是假码
            is_valid, reason = check_upstream_validity(key)
            if not is_valid:
                return {"code": 400, "status": "fail", "msg": reason}

            # 3. 验证通过，写入数据库绑定当前机器
            cur.execute(
                "INSERT INTO license_bindings (card_key, machine_id) VALUES (%s, %s)",
                (key, mid)
            )
            conn.commit()
            return {"code": 200, "status": "success", "msg": "激活成功 (首次绑定本机)"}

    except Exception as e:
        return {"code": 500, "status": "error", "msg": f"数据库错误: {str(e)}"}
    finally:
        if conn: conn.close()


if __name__ == "__main__":
    # 监听 9000 端口
    uvicorn.run(app, host="0.0.0.0", port=9000)