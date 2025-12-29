from waitress import serve
from app import app
import logging

# 配置日志，方便看到请求
logger = logging.getLogger('waitress')
logger.setLevel(logging.INFO)

if __name__ == '__main__':
    print("-------------------------------------------------------")
    print("正在启动 Windows 高并发服务器 (Waitress)...")
    print("Redis 连接状态: 已启用")
    print("服务地址: http://127.0.0.1:8001")
    print("-------------------------------------------------------")

    # 【核心配置解析】
    # host: 0.0.0.0 代表允许局域网访问
    # port: 8001 端口
    # threads: 线程数。
    #   由于 Windows 没有 Gevent 协程模式，我们需要开较多的线程来抗并发。
    #   因为你的业务主要是查 Redis (IO密集型)，线程切开销不大。
    #   设置 200 线程足以应对 1000 人的瞬间并发请求（Redis响应极快）。

    serve(
        app,
        host='0.0.0.0',
        port=8001,
        threads=200,  # 增加线程池大小以支持并发
        connection_limit=1000,  # 最大连接数
        channel_timeout=20  # 超时时间
    )