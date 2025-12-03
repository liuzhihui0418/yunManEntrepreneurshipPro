import multiprocessing

# 监听地址
bind = "0.0.0.0:5000"

# 进程数：核心数 * 2 + 1
workers = multiprocessing.cpu_count() * 2 + 1

# 线程模式：使用 gevent 协程处理高并发
worker_class = "gevent"

# 每个 Worker 最大并发连接数 (1000人并发主要靠这个)
worker_connections = 2000

# 访问日志
accesslog = "-"
errorlog = "-"
loglevel = "warning"

# 超时设置
timeout = 30
keepalive = 2

# 预加载应用，加快启动
preload_app = True