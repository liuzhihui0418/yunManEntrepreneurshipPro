# -*- coding: utf-8 -*-
import os
from flask import Blueprint, request, abort
from wechatpy.enterprise.crypto import WeChatCrypto
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.enterprise import parse_message, create_reply
from openai import OpenAI
from dotenv import load_dotenv

# 加载环境变量 (确保单独运行或被导入时都能拿到配置)
load_dotenv()

# 🔥 定义蓝图 (相当于一个小型的 app)
bot_bp = Blueprint('wechat_bot', __name__)

# ================= 配置区 (从 env 读取) =================
CORP_ID = os.getenv("WX_CORP_ID")
AGENT_ID = os.getenv("WX_AGENT_ID")
TOKEN = os.getenv("WX_TOKEN")
AES_KEY = os.getenv("WX_AES_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

SYSTEM_PROMPT = """
你是一个动态漫社群助教。请基于以下规则回答：
1. 即梦生成视频报500错通常是接口没钱了。
2. 动态漫分镜建议使用16:9。
3. 如果不知道，请让学员联系云漫老师。
"""

# ================= 初始化客户端 =================
# 懒加载：为了防止导入时因缺环境变量报错，加个判断
wx_crypto = None
client = None

if TOKEN and AES_KEY and CORP_ID:
    try:
        wx_crypto = WeChatCrypto(TOKEN, AES_KEY, CORP_ID)
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        print("✅ [Bot] 微信机器人模块加载成功")
    except Exception as e:
        print(f"❌ [Bot] 初始化失败: {e}")

# ================= 路由逻辑 =================
# 注意：这里用 @bot_bp.route，不再是 @app.route
@bot_bp.route('/wechat', methods=['GET', 'POST'])
def wechat_handler():
    if not wx_crypto:
        abort(500, "WeChat Bot Config Missing")

    # 1. 获取参数
    signature = request.args.get('msg_signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')

    # 2. 验证 (GET)
    if request.method == 'GET':
        echostr = request.args.get('echostr', '')
        try:
            decrypted_echo = wx_crypto.check_signature(signature, timestamp, nonce, echostr)
            return decrypted_echo
        except InvalidSignatureException:
            abort(403)

    # 3. 消息处理 (POST)
    if request.method == 'POST':
        try:
            decrypted_xml = wx_crypto.decrypt_message(request.data, signature, timestamp, nonce)
            msg = parse_message(decrypted_xml)

            if msg.type == 'text':
                user_content = msg.content
                print(f"📩 收到消息: {user_content}")

                if client:
                    response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_content},
                        ],
                        stream=False
                    )
                    ai_reply = response.choices[0].message.content
                else:
                    ai_reply = "AI 服务未连接"

                reply = create_reply(ai_reply, msg).render()
                encrypted_xml = wx_crypto.encrypt_message(reply, nonce, timestamp)
                return encrypted_xml
            return "success"
        except (InvalidSignatureException, Exception) as e:
            print(f"🔥 Bot Error: {e}")
            abort(403)