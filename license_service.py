# license_service.py
import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel
import pymysql
from pymysql.cursors import DictCursor
import requests
from datetime import datetime, timedelta

app = FastAPI()

# ================= 1. MySQL 数据库配置 =================
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "aini7758258!!",  # 请确保密码正确
    "db": "invite_code_system",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

# 上游查费用的地址 (如果不需要上游验证，可在这个函数里直接返回 True)
YUNWU_URL = "https://yunwu.ai/v1/dashboard/billing/usage"


class VerifyReq(BaseModel):
    card_key: str  # 解密后的真实 Key (用于业务逻辑)
    machine_id: str  # 客户端的机器码
    raw_key: str = None  # 原始加密卡密 (用于留存记录)


# ================= 2. 数据库初始化 =================
def init_db():
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            # 创建表：card_key 是唯一索引，保证一个卡密只能有一条记录
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


# ================= 3. 上游验证逻辑 =================
def check_upstream_validity(api_key):
    """
    这里检查卡密是否有效 (例如去 OpenAI 或云雾查余额)
    如果不需要上游，直接 return True, "有效"
    """
    # === 如果你想自己生成卡密，不依赖第三方，请取消下面这行的注释 ===
    # return True, "系统内置卡密"

    try:
        # 这里以云雾为例
        headers = {'Authorization': f'Bearer {api_key}'}
        resp = requests.get(f"{YUNWU_URL}?start_date=2023-01-01&end_date=2030-01-01", headers=headers, timeout=5)

        if resp.status_code == 200:
            return True, "有效卡密"
        elif resp.status_code == 401:
            return False, "无效的卡密或已失效"
        else:
            # 宽容策略：如果上游挂了，只要格式对，暂时放行 (看你需求)
            return False, f"上游接口异常: {resp.status_code}"
    except Exception as e:
        return False, f"网络校验超时: {str(e)}"


# ================= 4. 核心验证接口 (一机一码逻辑) =================
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
            # 1. 查询数据库中是否存在该卡密
            sql = "SELECT * FROM license_bindings WHERE card_key = %s"
            cursor.execute(sql, (key,))
            row = cursor.fetchone()

            if row:
                # ==============================
                # 🔥 场景 A: 老用户 (已绑定)
                # ==============================
                bound_mid = row['machine_id']
                db_expiry = row['expiry_date']
                db_status = row['status']

                # 1. 核心校验：机器码是否一致？
                if bound_mid != mid:
                    # 机器码不匹配，拒绝访问
                    return {
                        "code": 403,
                        "status": "fail",
                        "msg": f"一机一码校验失败！该卡密已绑定设备(尾号{bound_mid[-4:]})，当前设备无法使用。"
                    }

                # 2. 检查是否被禁用
                if db_status != 'active':
                    return {"code": 403, "status": "fail", "msg": "该授权已被管理员封禁"}

                # 3. 检查是否过期
                if db_expiry and datetime.now() > db_expiry:
                    return {"code": 403, "status": "fail", "msg": f"授权已于 {db_expiry} 过期"}

                # ✅ 验证通过
                return {
                    "code": 200,
                    "status": "success",
                    "msg": "验证成功",
                    "expiry_date": str(db_expiry)
                }

            else:
                # ==============================
                # 🔥 场景 B: 新用户 (首次激活)
                # ==============================

                # 1. 先去上游检查卡密是否有效
                is_valid, reason = check_upstream_validity(key)
                if not is_valid:
                    return {"code": 400, "status": "fail", "msg": reason}

                # 2. 设置过期时间 (例如：激活日起 1 年)
                default_expiry = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")

                # 3. 🔥 关键步骤：写入数据库，完成绑定 (Binding) 🔥
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
                    "msg": "激活成功 (设备已绑定)",
                    "expiry_date": default_expiry
                }

    except Exception as e:
        print(f"Server Error: {e}")
        return {"code": 500, "status": "error", "msg": "服务器内部错误"}
    finally:
        if conn: conn.close()


if __name__ == "__main__":
    # 监听本地 9000 端口
    uvicorn.run(app, host="0.0.0.0", port=9000)