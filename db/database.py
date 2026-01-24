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

    # ================= 🚀 新增：一机一码(双端)验证逻辑 =================
    def check_and_bind_device(self, code, device_id):
        """
        验证设备绑定状态
        :param code: 邀请码
        :param device_id: 前端传来的设备指纹
        :return: {'success': True/False, 'msg': '提示信息'}
        """
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 1. 锁定该行数据，防止并发问题 (FOR UPDATE)
                sql = "SELECT bound_devices FROM invite_codes WHERE code = %s LIMIT 1 FOR UPDATE"
                cursor.execute(sql, (code,))
                result = cursor.fetchone()

                if not result:
                    return {'success': False, 'msg': '邀请码不存在'}

                # 2. 解析当前绑定的设备列表
                bound_devices_raw = result.get('bound_devices')

                # 兼容 JSON 类型和 String 类型
                if bound_devices_raw:
                    if isinstance(bound_devices_raw, list):
                        bound_list = bound_devices_raw
                    elif isinstance(bound_devices_raw, str):
                        try:
                            bound_list = json.loads(bound_devices_raw)
                        except:
                            bound_list = []
                    else:
                        bound_list = []
                else:
                    bound_list = []

                # ============ 核心策略配置 ============
                MAX_DEVICES = 1  # 允许绑定的最大设备数
                # ====================================

                # 情况 A: 当前设备已经在名单里 -> 直接通过
                if device_id in bound_list:
                    return {'success': True, 'msg': '验证通过'}

                # 情况 B: 不在名单里，但还有空位 -> 绑定并通过
                if len(bound_list) < MAX_DEVICES:
                    bound_list.append(device_id)
                    new_json_str = json.dumps(bound_list)

                    # 更新数据库
                    update_sql = "UPDATE invite_codes SET bound_devices = %s WHERE code = %s"
                    cursor.execute(update_sql, (new_json_str, code))
                    conn.commit()
                    print(f"✅ 邀请码 {code} 新绑定设备: {device_id}")
                    return {'success': True, 'msg': '新设备绑定成功'}

                # 情况 C: 名单满了，且是新设备 -> 拒绝
                else:
                    return {
                        'success': False,
                        'msg': f'登录失败：该邀请码已绑定 {len(bound_list)} 台设备，无法在当前新设备使用。'
                    }

        except Exception as e:
            print(f"❌ 设备绑定检查出错: {e}")
            return {'success': False, 'msg': '设备验证服务繁忙，请重试'}
        finally:
            conn.close()

    # ================= 🚀 新增：严格检查邀请码状态 =================
    def check_code_is_valid_strict(self, code):
        """
        严格检查邀请码是否有效（直接查库，解决手动改库不生效的问题）
        """
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = "SELECT is_active, expires_at FROM invite_codes WHERE code = %s"
                cursor.execute(sql, (code,))
                res = cursor.fetchone()

                if not res: return False  # 码不存在
                if res['is_active'] != 1: return False  # 被禁用

                # 检查过期时间
                if res['expires_at'] and res['expires_at'] < datetime.datetime.now():
                    return False  # 已过期

                return True
        except Exception as e:
            print(f"Check Code Strict Error: {e}")
            return False
        finally:
            conn.close()

    # ================= 🚀 新增：编辑与删除逻辑 =================

    def update_invite_code(self, code, new_expiry_str=None, reset_device=False):
        """
        更新邀请码：修改过期时间 或 解绑设备
        """
        # 【修复引用】
        from db.redis_manager import redis_manager

        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                # 1. 如果需要解绑设备，将 bound_devices 重置为 "[]"
                if reset_device:
                    cursor.execute("UPDATE invite_codes SET bound_devices = '[]' WHERE code = %s", (code,))

                # 2. 如果提供了新的过期时间
                if new_expiry_str:
                    # 前端传来的通常是 '2024-12-31' 格式，我们加上时间变成 '2024-12-31 23:59:59'
                    if len(new_expiry_str) == 10:
                        new_expiry_str += " 23:59:59"
                    cursor.execute("UPDATE invite_codes SET expires_at = %s WHERE code = %s", (new_expiry_str, code))

                conn.commit()

                # 清除缓存
                try:
                    redis_manager.r.delete("admin:codes_list")
                    # 删除以 admin:codes_list_page 开头的分页缓存
                    keys = redis_manager.r.keys("admin:codes_list_page*")
                    if keys: redis_manager.r.delete(*keys)
                except:
                    pass
                return True
        except Exception as e:
            print(f"更新邀请码失败: {e}")
            return False
        finally:
            conn.close()

    def delete_invite_code(self, code):
        """
        删除邀请码
        """
        # 【修复引用】
        from db.redis_manager import redis_manager

        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM invite_codes WHERE code = %s", (code,))
                conn.commit()

                # 清除缓存
                try:
                    redis_manager.r.delete("admin:dashboard_stats")
                    redis_manager.r.delete("admin:total_codes_count")
                    # 删除分页缓存
                    keys = redis_manager.r.keys("admin:codes_list_page*")
                    if keys: redis_manager.r.delete(*keys)
                except:
                    pass
                return True
        except Exception as e:
            print(f"删除失败: {e}")
            return False
        finally:
            conn.close()

    def get_cards_with_pagination(self, page=1, page_size=20, search=None):
        """
        分页查询 cards 表 (关联 license_bindings 获取过期时间)
        """
        from db.redis_manager import redis_manager

        # 缓存键名区分开
        cache_key = f"admin:cards_list_page_{page}_size_{page_size}_search_{search or 'all'}"
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
                    where_conditions.append("c.card_key LIKE %s")
                    params.append(f"%{search}%")

                where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

                # 1. 获取总数
                count_sql = f"SELECT COUNT(*) as total FROM cards c {where_clause}"
                cursor.execute(count_sql, params)
                total_row = cursor.fetchone()
                total_count = total_row['total'] if total_row else 0

                # 2. 分页查询 (🔥 重点：子查询获取过期时间)
                # 如果没激活，expiry_date 就是 NULL，前端会显示 '-'
                offset = (page - 1) * page_size

                sql = f"""
                    SELECT 
                        c.*,
                        (SELECT expiry_date FROM license_bindings lb WHERE lb.card_key = c.card_key ORDER BY id DESC LIMIT 1) as expiry_date
                    FROM cards c
                    {where_clause}
                    ORDER BY c.created_at DESC 
                    LIMIT %s OFFSET %s
                """
                query_params = params + [page_size, offset]

                cursor.execute(sql, query_params)
                rows = list(cursor.fetchall())

                # 3. 格式化时间
                for row in rows:
                    if row.get('created_at'):
                        row['created_at'] = str(row['created_at'])

                    # 🔥 格式化过期时间 (如果有的话)
                    # 数据库里是 datetime 对象，转成字符串 "YYYY-MM-DD"
                    if row.get('expiry_date'):
                        row['expiry_date'] = str(row['expiry_date']).split(' ')[0]
                    else:
                        row['expiry_date'] = ''

                result = {
                    'cards': rows,
                    'pagination': {
                        'current_page': page,
                        'page_size': page_size,
                        'total_items': total_count,
                        'total_pages': (total_count + page_size - 1) // page_size if page_size > 0 else 1
                    }
                }

                # 写入缓存 (30秒)
                try:
                    redis_manager.r.setex(cache_key, 30, json.dumps(result))
                except:
                    pass
                return result
        except Exception as e:
            print(f"查询 cards 失败: {e}")
            return {'cards': [], 'pagination': {'current_page': 1, 'total_items': 0}}
        finally:
            conn.close()

    # ================= 🚀 新增：检查设备绑定一致性 =================
    def check_device_consistency(self, code, device_id):
        """
        检查当前请求的设备ID，是否在数据库的白名单里
        用于防止：后台解绑后，老设备依然在线的问题
        """
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = "SELECT bound_devices FROM invite_codes WHERE code = %s"
                cursor.execute(sql, (code,))
                result = cursor.fetchone()

                if not result or not result['bound_devices']:
                    return False  # 码不存在或没有任何绑定设备（说明被解绑了）

                bound_list = []
                try:
                    # 兼容 JSON 字符串和 List 对象
                    raw = result['bound_devices']
                    if isinstance(raw, str):
                        bound_list = json.loads(raw)
                    elif isinstance(raw, list):
                        bound_list = raw
                except:
                    return False

                # 核心判断：当前 Session 里的设备 ID，必须在数据库绑定列表里
                if device_id in bound_list:
                    return True
                return False
        except Exception as e:
            print(f"设备一致性检查失败: {e}")
            return False
        finally:
            conn.close()

    # ================= 🚀 新增：编辑与删除卡密逻辑 =================

    def update_card(self, card_id, new_expiry_str=None, status=None, reset_device=False, max_devices=None):
        """
        更新卡密信息（修复版）
        """
        from db.redis_manager import redis_manager

        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 1. 查找卡密 Key
                cursor.execute("SELECT card_key FROM cards WHERE id = %s", (card_id,))
                res = cursor.fetchone()
                if not res: return False

                # 🔥🔥🔥 直接取值，不用判断 tuple 🔥🔥🔥
                card_key = res['card_key']

                # 2. 更新 cards 表 (状态 和 最大设备数)
                card_updates = []
                card_params = []

                if status:
                    card_updates.append("status = %s")
                    card_params.append(status)

                # 🔥 新增：更新最大设备数
                if max_devices is not None:
                    card_updates.append("max_devices = %s")
                    card_params.append(int(max_devices))

                if card_updates:
                    sql = f"UPDATE cards SET {', '.join(card_updates)} WHERE id = %s"
                    card_params.append(card_id)
                    cursor.execute(sql, card_params)

                # 3. 处理过期时间和设备重置 (同步更新 license_bindings 表)
                if new_expiry_str:
                    if len(new_expiry_str) == 10:
                        new_expiry_str += " 23:59:59"
                    cursor.execute("UPDATE license_bindings SET expiry_date = %s WHERE card_key = %s",
                                   (new_expiry_str, card_key))

                if reset_device:
                    cursor.execute("DELETE FROM license_bindings WHERE card_key = %s", (card_key,))

                conn.commit()

                # 清除缓存
                try:
                    keys = redis_manager.r.keys("admin:cards_list_page*")
                    if keys: redis_manager.r.delete(*keys)
                except:
                    pass
                return True
        except Exception as e:
            print(f"更新卡密失败: {e}")
            return False
        finally:
            conn.close()

    def delete_card(self, card_id):
        """
        删除卡密及其绑定关系（修复版）
        """
        from db.redis_manager import redis_manager

        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 1. 获取卡密 Key
                cursor.execute("SELECT card_key FROM cards WHERE id = %s", (card_id,))
                res = cursor.fetchone()
                if not res: return False

                # 🔥🔥🔥 直接取值，不用判断 tuple 🔥🔥🔥
                card_key = res['card_key']

                # 2. 删除绑定关系
                cursor.execute("DELETE FROM license_bindings WHERE card_key = %s", (card_key,))

                # 3. 删除卡密本体
                cursor.execute("DELETE FROM cards WHERE id = %s", (card_id,))

                conn.commit()

                # 清除缓存
                try:
                    keys = redis_manager.r.keys("admin:cards_list_page*")
                    if keys: redis_manager.r.delete(*keys)
                except:
                    pass
                return True
        except Exception as e:
            print(f"删除卡密失败: {e}")
            return False
        finally:
            conn.close()

# 实例化在最后
db_manager = DatabaseManager()