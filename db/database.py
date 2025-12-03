import json

import pymysql
from dbutils.pooled_db import PooledDB
import datetime
import uuid

class DatabaseManager:
    def __init__(self):
        self.db_config = {
            'host': '43.135.26.58',
            'port': 3306,
            'user': 'root',
            'password': 'Aini7758258!!',
            'database': 'invite_code_system',
            'charset': 'utf8mb4',
            'autocommit': True,
            'maxconnections': 20,
            'connect_timeout': 10
        }
        self.pool = None
        self._init_pool()

    def _init_pool(self):
        try:
            self.pool = PooledDB(creator=pymysql, **self.db_config)
            print("MySQL 连接池初始化成功")
        except Exception as e:
            print(f"MySQL 初始化失败: {e}")

    def get_connection(self):
        if not self.pool: self._init_pool()
        return self.pool.connection()

    # --- Redis 预热用 ---
    def get_all_active_codes(self):
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = "SELECT code, is_used, is_active, max_uses, current_uses, expires_at FROM invite_codes"
                cursor.execute(sql)
                return cursor.fetchall()
        finally:
            conn.close()

    def get_all_admins(self):
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = "SELECT id, username, password FROM admin_users"
                cursor.execute(sql)
                return cursor.fetchall()
        finally:
            conn.close()

    # --- 管理员功能 ---
    def check_admin_login(self, username, password):
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = "SELECT id, username FROM admin_users WHERE username=%s AND password=%s"
                cursor.execute(sql, (username, password))
                return cursor.fetchone()
        finally:
            conn.close()

    def create_invite_code(self, code, days, note=""):
        conn = self.get_connection()
        try:
            expires_at = datetime.datetime.now() + datetime.timedelta(days=days)
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO invite_codes (code, max_uses, current_uses, is_active, is_used, expires_at, note)
                VALUES (%s, -1, 0, 1, 0, %s, %s)
                """
                cursor.execute(sql, (code, expires_at, note))
                conn.commit()
                return True
        except Exception as e:
            print(f"创建失败: {e}")
            return False
        finally:
            conn.close()

    # --- 【关键修复点在此】 ---
    def get_dashboard_stats(self):
        """
        优化版：优先从 Redis 读取缓存，缓存失效才查数据库
        """
        cache_key = "admin:dashboard_stats"
        from db.redis_manager import redis_manager
        # 1. 尝试从 Redis 获取缓存
        try:
            cached_data = redis_manager.r.get(cache_key)
            if cached_data:
                # print(">>> 命中缓存，直接返回")
                return json.loads(cached_data)
        except Exception as e:
            print(f"读取缓存失败: {e}")

        # 2. 缓存不存在，执行原有的慢速 SQL 查询
        conn = self.get_connection()
        stats = {}
        usage_data = []
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # ... 原有的 5 个 SQL 查询逻辑保持不变 ...
                # 1. 总数
                cursor.execute("SELECT COUNT(*) as c FROM invite_codes")
                stats['total_codes'] = cursor.fetchone()['c']
                # 2. 活跃
                cursor.execute("SELECT COUNT(*) as c FROM invite_codes WHERE is_active = 1 AND current_uses > 0")
                stats['active_users'] = cursor.fetchone()['c']
                # 3. 今日
                cursor.execute("SELECT COUNT(*) as c FROM invite_codes WHERE DATE(used_at) = CURDATE()")
                stats['today_usage'] = cursor.fetchone()['c']
                # 4. 过期
                cursor.execute(
                    "SELECT COUNT(*) as c FROM invite_codes WHERE expires_at > NOW() AND expires_at < DATE_ADD(NOW(), INTERVAL 3 DAY)")
                stats['expiring_codes'] = cursor.fetchone()['c']
                # 5. 列表
                cursor.execute("SELECT * FROM invite_codes ORDER BY created_at DESC LIMIT 20")
                usage_data = list(cursor.fetchall())

                # 时间序列化处理
                for row in usage_data:
                    if row.get('created_at'): row['created_at'] = str(row['created_at'])
                    if row.get('expires_at'): row['expires_at'] = str(row['expires_at'])
                    if row.get('used_at'):
                        row['used_at'] = str(row['used_at'])
                    else:
                        row['used_at'] = None

            result = {'stats': stats, 'usage_data': usage_data}

            # 3. 【关键】将结果写入 Redis 缓存，有效期 30 秒
            # 这样 30 秒内的所有刷新请求都不会查数据库，速度极快
            redis_manager.r.setex(cache_key, 30, json.dumps(result))

            return result

        except Exception as e:
            print(f"查询仪表盘数据失败: {e}")
            import traceback
            traceback.print_exc()
            return {'stats': {'total_codes': 0, 'active_users': 0, 'today_usage': 0, 'expiring_codes': 0},
                    'usage_data': []}
        finally:
            conn.close()

    def get_all_codes(self):
        """
        优化版：增加 Redis 缓存，解决列表加载转圈慢的问题
        """
        # 1. 【延迟导入】防止循环引用报错
        from db.redis_manager import redis_manager

        cache_key = "admin:codes_list"

        # 2. 尝试从 Redis 读取缓存
        try:
            cached_data = redis_manager.r.get(cache_key)
            if cached_data:
                # print(">>> 列表命中缓存")
                return json.loads(cached_data)
        except Exception as e:
            print(f"列表缓存读取失败: {e}")

        # 3. 缓存没有，去查远程数据库（原来的逻辑）
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT * FROM invite_codes ORDER BY created_at DESC LIMIT 100")
                rows = list(cursor.fetchall())

                # 数据清洗：将时间对象转为字符串
                for row in rows:
                    if row.get('created_at'): row['created_at'] = str(row['created_at'])
                    if row.get('expires_at'): row['expires_at'] = str(row['expires_at'])
                    if row.get('used_at'):
                        row['used_at'] = str(row['used_at'])
                    else:
                        row['used_at'] = None

                # 4. 【写入缓存】有效期 60 秒
                try:
                    redis_manager.r.setex(cache_key, 60, json.dumps(rows))
                except Exception as e:
                    print(f"写入列表缓存失败: {e}")

                return rows
        finally:
            conn.close()


db_manager = DatabaseManager()