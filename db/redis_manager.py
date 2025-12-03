import redis
import json
import uuid
import time
from db.database import db_manager


class RedisManager:
    def __init__(self):
        # 初始化 Redis 连接池
        self.pool = redis.ConnectionPool(host='127.0.0.1', port=6379, decode_responses=True, max_connections=2000)
        self.r = redis.Redis(connection_pool=self.pool)
        self.session_ttl = 86400  # Session 过期时间 24小时ok

    def sync_mysql_to_redis(self):
        """
        【启动时调用】将 MySQL 中的有效邀请码全部刷入 Redis 缓存
        """
        print(">>> 正在将 MySQL 数据预热到 Redis...")
        try:
            codes = db_manager.get_all_active_codes()
            if not codes:
                print(">>> MySQL 中没有有效邀请码，跳过预热。")
                return

            count = 0
            pipeline = self.r.pipeline()
            for item in codes:
                key = f"invite:{item['code'].upper()}"
                # 将数据存为 Hash 结构
                data = {
                    "active": 1 if item['is_active'] else 0,
                    "is_used": item['is_used'],
                    "max": item['max_uses'],
                    "curr": item['current_uses']
                }

                pipeline.hmset(key, data)
                count += 1

            pipeline.execute()
            print(f">>> 预热完成！共加载 {count} 个邀请码到 Redis")
        except Exception as e:
            print(f"预热数据时发生错误: {e}")

    def validate_and_use_code(self, code):
        """
        【修复版】极速验证 - 同一个邀请码可多次使用
        """
        key = f"invite:{code}"

        # 1. 检查是否存在
        if not self.r.exists(key):
            return {'valid': False, 'message': '邀请码不存在'}

        # 2. 【修复】移除 is_used 检查的 Lua 脚本
        lua_script = """
        local key = KEYS[1]
        local active = tonumber(redis.call('HGET', key, 'active'))
        local max_uses = tonumber(redis.call('HGET', key, 'max'))
        local curr_uses = tonumber(redis.call('HGET', key, 'curr'))

        -- 只检查是否激活，不再检查 is_used
        if active ~= 1 then return -1 end

        if max_uses > 0 then
            -- 只根据使用次数判断
            if curr_uses >= max_uses then return -3 end
            redis.call('HINCRBY', key, 'curr', 1)
            -- 只有达到最大次数时才标记为已使用
            if curr_uses + 1 >= max_uses then
                redis.call('HSET', key, 'is_used', 1)
            end
        else
            -- 无限次使用的邀请码
            redis.call('HINCRBY', key, 'curr', 1)
        end

        return 1
        """

        try:
            cmd = self.r.register_script(lua_script)
            result = cmd(keys=[key])

            if result == 1:
                return {'valid': True, 'message': '验证成功'}
            elif result == -1:
                return {'valid': False, 'message': '邀请码已失效'}
            elif result == -3:  # 现在这个判断才会真正执行到
                return {'valid': False, 'message': '邀请码次数已耗尽'}
            else:
                return {'valid': False, 'message': '系统繁忙'}
        except Exception as e:
            print(f"Redis脚本执行错误: {e}")
            return {'valid': False, 'message': '系统繁忙'}

    # --- Session 管理 ---
    def create_session(self, invite_code):
        session_id = str(uuid.uuid4())
        session_key = f"sess:{session_id}"

        user_info = {
            "code": invite_code,
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
        if data:
            return json.loads(data)
        return None

    def destroy_session(self, session_id):
        self.r.delete(f"sess:{session_id}")


redis_manager = RedisManager()