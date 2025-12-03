import hashlib
import time


class SessionManager:
    def __init__(self):
        self.active_sessions = {}
        self.session_timeout = 24 * 60 * 60  # 24小时超时

    def create_session(self, invite_code, user_info=None):
        """创建新会话"""
        session_id = hashlib.sha256(f"{invite_code}{time.time()}".encode()).hexdigest()

        self.active_sessions[session_id] = {
            'invite_code': invite_code,
            'login_time': time.time(),
            'last_activity': time.time(),
            'user_name': user_info or f"用户{hash(invite_code) % 1000}",
            'user_avatar': invite_code[0] if invite_code else 'U'
        }

        return session_id

    def validate_session(self, session_id):
        """验证会话是否有效"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]

            # 检查会话是否超时
            if time.time() - session['last_activity'] > self.session_timeout:
                del self.active_sessions[session_id]
                return False

            # 更新最后活动时间
            session['last_activity'] = time.time()
            return True

        return False

    def get_session_info(self, session_id):
        """获取会话信息"""
        if self.validate_session(session_id):
            return self.active_sessions[session_id]
        return None

    def destroy_session(self, session_id):
        """销毁会话"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            return True
        return False

    def cleanup_expired_sessions(self):
        """清理过期会话"""
        current_time = time.time()
        expired_sessions = [
            session_id for session_id, session in self.active_sessions.items()
            if current_time - session['last_activity'] > self.session_timeout
        ]

        for session_id in expired_sessions:
            del self.active_sessions[session_id]

        return len(expired_sessions)


# 创建全局会话管理器实例
session_manager = SessionManager()