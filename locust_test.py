from locust import HttpUser, task, between


class WebsiteUser(HttpUser):
    # 模拟用户在两个操作之间的等待时间（0.5秒到1秒之间）
    # 如果想测极限压力，可以把这个去掉，或者设为 constant(0)
    wait_time = between(0.5, 1)

    # 任务1：访问首页 (权重1，偶尔访问)
    @task(1)
    def index(self):
        self.client.get("/")

    # 任务2：疯狂点击登录 (权重3，主要测这个)
    @task(3)
    def login(self):
        # 模拟 POST 请求提交验证码
        response = self.client.post("/api/validate", json={
            "invite_code": "TEST9999"  # 这里填刚才创建的无限次测试码
        })

        # 如果返回 json 里的 success 是 True，算成功，否则算失败
        if response.status_code == 200:
            if response.json().get("success"):
                response.success()
            else:
                response.failure("业务逻辑错误: " + response.json().get("message", "未知"))