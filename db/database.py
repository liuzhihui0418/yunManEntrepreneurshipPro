import pymysql
from dbutils.pooled_db import PooledDB
import threading
import sys

import pymysql
from dbutils.pooled_db import PooledDB

class DatabaseManager:
    def __init__(self):
        self.db_config = {
            'host': '127.0.0.1',
            'port': 3306,
            'user': 'root',
            'password': 'Aini7758258!!',
            'database': 'invite_code_system',
            'charset': 'utf8mb4',
            'autocommit': True,
            # 【优化点】增加连接池大小
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
        if not self.pool: raise Exception("DB未连接")
        return self.pool.connection()

    def get_all_active_codes(self):
        """【新增】获取所有需要同步到 Redis 的邀请码"""
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 只查还没完全失效的
                sql = "SELECT code, is_used, is_active, max_uses, current_uses FROM invite_codes"
                cursor.execute(sql)
                return cursor.fetchall()
        finally:
            conn.close()

    def validate_invite_code(self, code):
        """简化验证逻辑"""
        code = code.upper().strip()

        if not code:
            return {'valid': False, 'message': '邀请码不能为空'}

        try:
            conn = self.get_connection()
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 直接查询邀请码状态
                query = """
                SELECT code, is_used, is_active, max_uses, current_uses 
                FROM invite_codes 
                WHERE code = %s
                """
                cursor.execute(query, (code,))
                result = cursor.fetchone()

                if not result:
                    return {'valid': False, 'message': '邀请码不存在'}

                # 简化验证逻辑
                if result['is_active'] != 1:
                    return {'valid': False, 'message': '邀请码已失效'}

                if result['is_used'] == 1:
                    return {'valid': False, 'message': '邀请码已被使用'}

                if result['max_uses'] > 0 and result['current_uses'] >= result['max_uses']:
                    return {'valid': False, 'message': '邀请码使用次数已满'}

                return {'valid': True, 'message': '邀请码有效'}

        except Exception as e:
            print(f"数据库错误: {e}")
            return {'valid': False, 'message': f'数据库错误: {str(e)}'}
        finally:
            if 'conn' in locals():
                conn.close()

    def use_invite_code(self, code, used_by="Web用户"):
        """使用邀请码"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                update_sql = """
                UPDATE invite_codes 
                SET current_uses = current_uses + 1,
                    is_used = CASE 
                        WHEN max_uses > 0 AND (current_uses + 1) >= max_uses THEN 1 
                        ELSE is_used 
                    END,
                    used_at = NOW(),
                    used_by = %s
                WHERE code = %s
                """
                cursor.execute(update_sql, (used_by, code))
                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            print(f"使用邀请码错误: {e}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()


# 创建实例
db_manager = DatabaseManager()