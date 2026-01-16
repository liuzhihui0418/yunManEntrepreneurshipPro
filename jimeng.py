# import http.client
# import json
#
# conn = http.client.HTTPSConnection("yunwu.ai")
# payload = json.dumps({
#    "model": "jimeng-video-3.0",
#    "prompt": """特写 俯拍 镜头静止 2s→陈贵良的侧脸压在交叠的手臂上，趴在堆满试卷的课桌上，双眼紧闭，蓝白色校服袖子可见→演员保持静止睡眠姿态→收音要求：环境静音，仅收录背景中微弱的写字沙沙声→音效：安静的考场环境音→无→实拍环境要求：室内日光灯照明，光线均匀；
# 中近景 平拍 快速拉起+跟拍 5s→陈贵良突然惊醒，猛地抬起头，身体因为惊吓而微微后仰，他眼神惊慌地快速扫视左右，观察着周围埋头写字的同学和安静的考场环境→演员表情由迷糊瞬间转为震惊和恐慌，呼吸变得急促，眼部肌肉紧绷→收音要求：清晰收录演员猛地起身的衣物摩擦声和急促的吸气声→音效：心跳加速声（渐强），周围同学写字的沙沙声→【陈贵良】(OS)："是老子起猛了？"（语气：惊疑，自嘲，语速快）
# - 实拍环境要求：「室内场景，白色日光灯照明，禁止外界噪音」；
# - 技术参数：「帧率：24fps，感光度：ISO 200-400，快门速度：1/50s，白平衡：自动（适配日光灯）」；
# - 合规性：「禁止违规元素，符合短视频平台规范；拍摄内容真实合规」；
# 总时长：7.0s""",
#    "aspect_ratio": "16:9",
#    "size": "1080P",
#    "images": []
# })
# headers = {
#    'Accept': 'application/json',
#    'Authorization': 'Bearer sk-Pr7mUz4qIAfcLgS2onczOTIceK57zGM8SsUIrabhIbJQZIef',
#    'Content-Type': 'application/json'
# }
# conn.request("POST", "/v1/video/create", payload, headers)
# res = conn.getresponse()
# data = res.read()
# print(data.decode("utf-8"))


import http.client
import json

# 建立 HTTPS 连接
conn = http.client.HTTPSConnection("yunwu.ai")

# 请求参数（核心新增 duration 字段设置时长，images 传入首尾帧图片）
payload = json.dumps({
    "model": "jimeng-video-3.0",
    "prompt": """特写 俯拍 镜头静止 2s→陈贵良的侧脸压在交叠的手臂上，趴在堆满试卷的课桌上，双眼紧闭，蓝白色校服袖子可见→演员保持静止睡眠姿态→收音要求：环境静音，仅收录背景中微弱的写字沙沙声→音效：安静的考场环境音→无→实拍环境要求：室内日光灯照明，光线均匀；
中近景 平拍 快速拉起+跟拍 5s→陈贵良突然惊醒，猛地抬起头，身体因为惊吓而微微后仰，他眼神惊慌地快速扫视左右，观察着周围埋头写字的同学和安静的考场环境→演员表情由迷糊瞬间转为震惊和恐慌，呼吸变得急促，眼部肌肉紧绷→收音要求：清晰收录演员猛地起身的衣物摩擦声和急促的吸气声→音效：心跳加速声（渐强），周围同学写字的沙沙声→【陈贵良】(OS)："是老子起猛了？"（语气：惊疑，自嘲，语速快）
- 实拍环境要求：「室内场景，白色日光灯照明，禁止外界噪音」；
- 技术参数：「帧率：24fps，感光度：ISO 200-400，快门速度：1/50s，白平衡：自动（适配日光灯）」；
- 合规性：「禁止违规元素，符合短视频平台规范；拍摄内容真实合规」；
总时长：7.0s""",  # 视频生成描述
    "aspect_ratio": "16:9",  # 视频比例
    "size": "1080P",  # 分辨率
    "duration": 10,  # 关键：设置视频时长，支持 5/10 秒，默认 5
    "images": [
        # 首尾帧配置：传入首帧、尾帧图片的 URL/OSS key（二选一即可）

            "https://yunman-1327419568.cos.ap-guangzhou.myqcloud.com/library/05c52ebf8aba4cd8bd450f4bd0566757.png"  # 首帧图片公网 URL
            # 或用 OSS key："image_key": "tos-cn-i-a9rns2rl98/xxx.png"
        ,

            "https://yunman-1327419568.cos.ap-guangzhou.myqcloud.com/library/8df0f27600d449a7a0f519e4a8ac7aa0.png"

    ]
})

# 请求头（替换 <token> 为你的真实授权令牌）
headers = {
    'Accept': 'application/json',
    'Authorization': 'Bearer sk-Pr7mUz4qIAfcLgS2onczOTIceK57zGM8SsUIrabhIbJQZIef',  # 替换成有效 token
    'Content-Type': 'application/json'
}

# 发送 POST 请求
try:
    conn.request("POST", "/v1/video/create", payload, headers)
    res = conn.getresponse()
    data = res.read()
    # 格式化输出响应结果
    response = json.loads(data.decode("utf-8"))
    print(json.dumps(response, ensure_ascii=False, indent=2))
except Exception as e:
    print(f"请求失败：{str(e)}")
finally:
    conn.close()  # 关闭连接