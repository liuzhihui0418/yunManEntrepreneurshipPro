import json
import pymysql
from dbutils.pooled_db import PooledDB
import datetime
import uuid

# 数据库管理器类
class DatabaseManager:
    def __init__(self):
        # 数据库配置
        self.db_config = {
            'host': '127.0.0.1',
            'port': 3306,
            'user': 'root',
            'password': 'aini7758258!!',
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

    # ================= 辅助优化方法 =================
    def _get_cached_count(self, cache_key, sql_query, params=None):
        """
        通用计数缓存方法
        """
        # 【修复 1/6】加上 db. 前缀
        from db.redis_manager import redis_manager

        try:
            cached_count = redis_manager.r.get(cache_key)
            if cached_count:
                return int(cached_count)
        except Exception:
            pass

        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql_query, params)
                row = cursor.fetchone()
                if isinstance(row, dict):
                    count = list(row.values())[0]
                else:
                    count = row[0]

                # 写入缓存，有效期 600秒
                try:
                    redis_manager.r.setex(cache_key, 600, count)
                except:
                    pass
                return count
        finally:
            conn.close()

    # ================= 原有基础方法 =================

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

    def check_admin_login(self, username, password):
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = "SELECT id, username FROM admin_users WHERE username=%s AND password=%s"
                cursor.execute(sql, (username, password))
                return cursor.fetchone()
        finally:
            conn.close()

    # ================= 业务方法 (优化) =================

    def create_invite_code(self, code, days, note=""):
        # 【修复 2/6】加上 db. 前缀
        from db.redis_manager import redis_manager

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

                try:
                    redis_manager.r.delete("admin:total_codes_count")
                except:
                    pass
                return True
        except Exception as e:
            print(f"创建失败: {e}")
            return False
        finally:
            conn.close()

    def get_dashboard_stats(self):
        # 【修复 3/6】加上 db. 前缀
        from db.redis_manager import redis_manager

        cache_key = "admin:dashboard_stats"
        try:
            cached_data = redis_manager.r.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            print(f"读取缓存失败: {e}")

        conn = self.get_connection()
        stats = {}
        usage_data = []
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT COUNT(*) as c FROM invite_codes")
                stats['total_codes'] = cursor.fetchone()['c']

                cursor.execute("SELECT COUNT(*) as c FROM invite_codes WHERE is_active = 1 AND current_uses > 0")
                stats['active_users'] = cursor.fetchone()['c']

                cursor.execute("SELECT COUNT(*) as c FROM invite_codes WHERE DATE(used_at) = CURDATE()")
                stats['today_usage'] = cursor.fetchone()['c']

                cursor.execute(
                    "SELECT COUNT(*) as c FROM invite_codes WHERE expires_at > NOW() AND expires_at < DATE_ADD(NOW(), INTERVAL 3 DAY)")
                stats['expiring_codes'] = cursor.fetchone()['c']

                cursor.execute("SELECT * FROM invite_codes ORDER BY created_at DESC LIMIT 20")
                usage_data = list(cursor.fetchall())

                for row in usage_data:
                    if row.get('created_at'): row['created_at'] = str(row['created_at'])
                    if row.get('expires_at'): row['expires_at'] = str(row['expires_at'])
                    if row.get('used_at'):
                        row['used_at'] = str(row['used_at'])
                    else:
                        row['used_at'] = None

            result = {'stats': stats, 'usage_data': usage_data}
            try:
                redis_manager.r.setex(cache_key, 30, json.dumps(result))
            except:
                pass
            return result

        except Exception as e:
            print(f"查询仪表盘数据失败: {e}")
            return {'stats': {'total_codes': 0, 'active_users': 0, 'today_usage': 0, 'expiring_codes': 0},
                    'usage_data': []}
        finally:
            conn.close()

    def get_all_codes(self):
        # 【修复 4/6】加上 db. 前缀
        from db.redis_manager import redis_manager

        cache_key = "admin:codes_list"
        try:
            cached_data = redis_manager.r.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception:
            pass

        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT * FROM invite_codes ORDER BY created_at DESC LIMIT 100")
                rows = list(cursor.fetchall())

                for row in rows:
                    if row.get('created_at'): row['created_at'] = str(row['created_at'])
                    if row.get('expires_at'): row['expires_at'] = str(row['expires_at'])
                    if row.get('used_at'):
                        row['used_at'] = str(row['used_at'])
                    else:
                        row['used_at'] = None

                try:
                    redis_manager.r.setex(cache_key, 60, json.dumps(rows))
                except Exception:
                    pass
                return rows
        finally:
            conn.close()

    # ================= 分页方法 (集成进类并优化) =================

    def get_dashboard_stats_with_pagination(self, page=1, page_size=20):
        # 【修复 5/6】加上 db. 前缀
        from db.redis_manager import redis_manager

        cache_key = f"admin:dashboard_stats_page_{page}_size_{page_size}"
        try:
            cached_data = redis_manager.r.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except:
            pass

        conn = self.get_connection()
        stats = {}
        usage_data = []

        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 统计信息
                stats['total_codes'] = self._get_cached_count(
                    "admin:total_codes_count",
                    "SELECT COUNT(*) FROM invite_codes"
                )

                cursor.execute("SELECT COUNT(*) as c FROM invite_codes WHERE is_active = 1 AND current_uses > 0")
                stats['active_users'] = cursor.fetchone()['c']

                cursor.execute("SELECT COUNT(*) as c FROM invite_codes WHERE DATE(used_at) = CURDATE()")
                stats['today_usage'] = cursor.fetchone()['c']

                cursor.execute(
                    "SELECT COUNT(*) as c FROM invite_codes WHERE expires_at > NOW() AND expires_at < DATE_ADD(NOW(), INTERVAL 3 DAY)")
                stats['expiring_codes'] = cursor.fetchone()['c']

                # 分页查询数据
                offset = (page - 1) * page_size
                cursor.execute("SELECT * FROM invite_codes ORDER BY created_at DESC LIMIT %s OFFSET %s",
                               (page_size, offset))
                usage_data = list(cursor.fetchall())

                total_count = stats['total_codes']

                for row in usage_data:
                    if row.get('created_at'): row['created_at'] = str(row['created_at'])
                    if row.get('expires_at'): row['expires_at'] = str(row['expires_at'])
                    if row.get('used_at'):
                        row['used_at'] = str(row['used_at'])
                    else:
                        row['used_at'] = None

                result = {
                    'stats': stats,
                    'usage_data': usage_data,
                    'pagination': {
                        'current_page': page,
                        'page_size': page_size,
                        'total_items': total_count,
                        'total_pages': (total_count + page_size - 1) // page_size
                    }
                }

                try:
                    redis_manager.r.setex(cache_key, 30, json.dumps(result))
                except:
                    pass
                return result

        except Exception as e:
            print(f"查询仪表盘数据失败: {e}")
            return {'stats': {}, 'usage_data': [], 'pagination': {'current_page': 1, 'total_items': 0}}
        finally:
            conn.close()

    def get_codes_with_pagination(self, page=1, page_size=20, search=None):
        # 【修复 6/6】加上 db. 前缀
        from db.redis_manager import redis_manager

        cache_key = f"admin:codes_list_page_{page}_size_{page_size}_search_{search or 'all'}"
        try:
            cached_data = redis_manager.r.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except:
            pass

        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                where_conditions = []
                params = []

                if search:
                    where_conditions.append("code LIKE %s")
                    params.append(f"%{search}%")

                where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

                if search:
                    count_sql = f"SELECT COUNT(*) as total FROM invite_codes {where_clause}"
                    cursor.execute(count_sql, params)
                    total_count = cursor.fetchone()['total']
                else:
                    total_count = self._get_cached_count(
                        "admin:total_codes_count",
                        "SELECT COUNT(*) FROM invite_codes"
                    )

                offset = (page - 1) * page_size
                sql = f"SELECT * FROM invite_codes {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s"
                query_params = params + [page_size, offset]

                cursor.execute(sql, query_params)
                rows = list(cursor.fetchall())

                for row in rows:
                    if row.get('created_at'): row['created_at'] = str(row['created_at'])
                    if row.get('expires_at'): row['expires_at'] = str(row['expires_at'])
                    if row.get('used_at'):
                        row['used_at'] = str(row['used_at'])
                    else:
                        row['used_at'] = None

                result = {
                    'codes': rows,
                    'pagination': {
                        'current_page': page,
                        'page_size': page_size,
                        'total_items': total_count,
                        'total_pages': (total_count + page_size - 1) // page_size
                    }
                }

                try:
                    redis_manager.r.setex(cache_key, 60, json.dumps(result))
                except:
                    pass
                return result
        except Exception as e:
            print(f"查询邀请码列表失败: {e}")
            return {'codes': [], 'pagination': {'current_page': 1, 'total_items': 0}}
        finally:
            conn.close()

# 实例化在最后
db_manager = DatabaseManager()