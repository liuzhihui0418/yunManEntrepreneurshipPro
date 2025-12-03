import time
import threading
from collections import OrderedDict


class LRUCache:
    def __init__(self, max_size=1000, ttl=300):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl  # 缓存过期时间（秒）
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    # 移动到最新位置
                    self.cache.move_to_end(key)
                    return value
                else:
                    # 过期删除
                    del self.cache[key]
            return None

    def set(self, key, value):
        with self.lock:
            if key in self.cache:
                del self.cache[key]
            elif len(self.cache) >= self.max_size:
                # 删除最旧的
                self.cache.popitem(last=False)
            self.cache[key] = (value, time.time())

    def delete(self, key):
        with self.lock:
            if key in self.cache:
                del self.cache[key]


# 全局缓存实例
invite_code_cache = LRUCache(max_size=500, ttl=60)  # 缓存1分钟