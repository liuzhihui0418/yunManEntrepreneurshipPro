# gunicorn_config.py
import multiprocessing

# 监听地址 (内网)
bind = "0.0.0.0:5000"
# 开启后台运行 (守护进程)
daemon = False
# 进程数 (核心数*2+1)
workers = multiprocessing.cpu_count() * 2 + 1
# 线程模式 (协程)
worker_class = "gevent"
#并发连接数
worker_connections = 2000
# 日志路径 (自动生成在项目目录下，方便查看)
accesslog = "./access.log"
errorlog = "./error.log"
loglevel = "warning"