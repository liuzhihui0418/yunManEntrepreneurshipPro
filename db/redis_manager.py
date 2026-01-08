import redis
import json
import uuid
import time
import datetime
from db.database import db_manager


class RedisManager:
    def __init__(self):
        # 初始化 Redis 连接池
        self.pool = redis.ConnectionPool(host='127.0.0.1', port=6379, decode_responses=True, max_connections=2000)
        self.r = redis.Redis(connection_pool=self.pool)
        self.session_ttl = 86400  # Session 过期时间 24小时

    def sync_mysql_to_redis(self):
        """
        【启动时调用】将 MySQL 中的 1.邀请码 2.管理员 全部刷入 Redis 缓存
        """
        print(">>> 正在启动数据预热...")
        pipeline = self.r.pipeline()

        # --- 1. 同步邀请码 ---
        try:
            codes = db_manager.get_all_active_codes()
            code_count = 0
            if codes:
                for item in codes:
                    key = f"invite:{item['code'].upper()}"

                    # 处理过期时间
                    expire_ts = 0
                    if item.get('expires_at') and isinstance(item['expires_at'], datetime.datetime):
                        expire_ts = item['expires_at'].timestamp()

                    data = {
                        "active": 1 if item['is_active'] else 0,
                        "is_used": item['is_used'],
                        "max": item['max_uses'],
                        "curr": item['current_uses'],
                        "expire": expire_ts
                    }
                    pipeline.hmset(key, data)
                    code_count += 1
            print(f">>> 邀请码预热完成：共 {code_count} 个")
        except Exception as e:
            print(f"!!! 邀请码预热失败: {e}")

        # --- 2. 同步管理员 (新增逻辑) ---
        try:
            admins = db_manager.get_all_admins()
            admin_count = 0
            if admins:
                for admin in admins:
                    # 使用 admin:用户名 作为 Key
                    key = f"admin:{admin['username']}"
                    data = {
                        "id": admin['id'],
                        "password": admin['password']  # 存入 Redis
                    }
                    pipeline.hmset(key, data)
                    admin_count += 1
            print(f">>> 管理员预热完成：共 {admin_count} 个")
        except Exception as e:
            # 如果 database.py 还没加 get_all_admins 方法，这里会报错，为了不影响启动捕获它
            print(f"!!! 管理员预热失败 (可能是数据库方法未添加): {e}")

        # 提交所有数据
        pipeline.execute()
        print(">>> Redis 数据同步结束")

    def validate_and_use_code(self, code):
        """邀请码验证逻辑 (保持不变)"""
        key = f"invite:{code}"

        if not self.r.exists(key):
            return {'valid': False, 'message': '邀请码不存在'}

        lua_script = """
        local key = KEYS[1]
        local now_ts = tonumber(ARGV[1])

        local active = tonumber(redis.call('HGET', key, 'active'))
        local max_uses = tonumber(redis.call('HGET', key, 'max'))
        local curr_uses = tonumber(redis.call('HGET', key, 'curr'))
        local expire_ts = tonumber(redis.call('HGET', key, 'expire') or 0)

        if active ~= 1 then return -1 end
        if expire_ts > 0 and now_ts > expire_ts then return -2 end

        if max_uses > 0 then
            if curr_uses >= max_uses then return -3 end
            redis.call('HINCRBY', key, 'curr', 1)
            if curr_uses + 1 >= max_uses then
                redis.call('HSET', key, 'is_used', 1)
            end
        else
            redis.call('HINCRBY', key, 'curr', 1)
        end
        return 1
        """

        try:
            cmd = self.r.register_script(lua_script)
            result = cmd(keys=[key], args=[time.time()])

            if result == 1:
                return {'valid': True, 'message': '验证成功'}
            elif result == -1:
                return {'valid': False, 'message': '邀请码已禁用'}
            elif result == -2:
                return {'valid': False, 'message': '邀请码已过期'}
            elif result == -3:
                return {'valid': False, 'message': '邀请码次数已耗尽'}
            else:
                return {'valid': False, 'message': '系统繁忙'}
        except Exception as e:
            print(f"Redis脚本执行错误: {e}")
            return {'valid': False, 'message': '系统繁忙'}

        # --- 【新增】极速写入单条数据 ---
    def add_single_code(self, code, days):
        """创建新码时，直接写入 Redis，不需要全量同步"""
        try:
            key = f"invite:{code.upper()}"
            # 计算过期时间戳
            expire_dt = datetime.datetime.now() + datetime.timedelta(days=days)
            expire_ts = expire_dt.timestamp()

            data = {
                "active": 1,
                "is_used": 0,
                "max": -1,  # 无限次
                "curr": 0,
                "expire": expire_ts
            }
            self.r.hmset(key, data)
            print(f">>> 新邀请码 {code} 已极速写入 Redis")
        except Exception as e:
            print(f"单条写入Redis失败: {e}")

    # --- 新增：管理员 Redis 验证 ---
    def validate_admin_login(self, username, password):
        """
        全内存验证管理员登录，不查数据库
        """
        key = f"admin:{username}"

        # 1. 检查是否存在
        if not self.r.exists(key):
            return False

        # 2. 获取密码比对
        stored_password = self.r.hget(key, "password")

        # 注意：生产环境这里应该比对 Hash，目前为了演示直接比对字符串
        if stored_password == password:
            return True
        return False

    # --- Session 管理 (保持不变) ---
    def create_session(self, invite_code, device_id): # <--- 增加 device_id 参数
        session_id = str(uuid.uuid4())
        session_key = f"sess:{session_id}"
        user_info = {
            "code": invite_code,
            "device_id": device_id, # <--- 将设备指纹存入 Session
            "name": f"用户{hash(invite_code) % 1000}",
            "avatar": "default.png",
            "login_at": time.time()
        }
        self.r.setex(session_key, self.session_ttl, json.dumps(user_info))
        return session_id

    def validate_session(self, session_id):
        return self.r.exists(f"sess:{session_id}")

    def get_session_info(self, session_id):
        data = self.r.get(f"sess:{session_id}")
        if data: return json.loads(data)
        return None

    def destroy_session(self, session_id):
        self.r.delete(f"sess:{session_id}")


redis_manager = RedisManager()