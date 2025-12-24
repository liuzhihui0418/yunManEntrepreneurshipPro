# -*- coding: utf-8 -*-

import base64

from alipay import AliPay

import time

from Cryptodome.PublicKey import RSA



# ==============================================================================

# 配置区域

# ==============================================================================



APP_ID = "2021006117616884"  # 你的APPID



# 【私钥】(刚才检测通过的，这里不用动了，保留你刚才填的)

PRIVATE_KEY_CONTENT = """

MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCLce5pKBVWEjBpIHqE9j9Hh5/KnbnPU

MqL7qKuQXN4ogEkggnejg62UyGXVchgIzzW5k3T2YmQG0bVgzR8el7/cJ8btg8e1d0gRZn+m8LK+0qGXJ

Mdx+6rSGZbcZ6c+yaw+GlTQdnvEhPYq0zexN6SzxoWKkScOfEmyPXEo8vpb5TXFCPHuYn2hxnGhwePp5R

fk5VPqrO5BcgJRd1cNNn+UWdmL54qVaA5CEQrHTaUTwIKmSYZ1BfGy0g0XH7qqxNs+WS9dCk5p7BCMpaK

schkfmqdg/MwRzDmIDNtuufxe/AU7sqlsPoCGn95vR5XlOXcslps0gdLMeZ5IVN5y/tTAgMBAAECggEAY

7oJfZ8zEylTAfw+Y1UREIEIYInI12G6WbVDF0ir4nxKQOfXUxlZoD936JlrAoZw/mgbBQWxAiTf1ddN9D

A4PIs430KnMbBVwrzEU3jmKPDq7YjLliLkqA7RVVi+zRo5I5ulB+wyhm3xT6XDBhbZ7zi6OVvlUa2Gr+x

NCGL0dG9LVCnQMnDeEj9IVJFsVG3Gk4tbdXRK6hoF6/hCVzNl9vBk8Kdftbf5ec19JTq6mf8TcenRNa9u

8Y11PMaPOIVW5raheQFIj6BSLYm0AsAnVrfb8CXzPxijdykXAEgxiPtkspggcoBkN/x2/WfNivE/KqIxF

HQ+vNJgIuH8pWnVoQKBgQDk02teYhhcsOWzhvY070UA5PeEhMYKq50DXbXpH5Y4skr2XnFUD6KC74M3bK

ovsPk5osWwV1SARvh9BgPEsLXs6KDNbYf62GYe4aX2qJ+3Yhnajup7A5rmHwNAU7c8t/UbOdOdYg4Dw/J

qIZEf4zEdBoz8KsHuULdLHBHR6r3R2QKBgQCcATpZ3ITOCvkXwB5kBgUS0l8/RN681VI4qNHHhH/4r4+o

DEDOMHYvh/zj1IyGKFqG3jvD+iQRiPQbZ4Xlw0zGDyst/1250VGjTc3+xqPSmMOFH0qt3AMW/S7aVzmXA

ls0FDjtef0tiYQwE2QdjPxmmWFUpwkZjTOmwA05v7JPCwKBgQCbuSWAfdGGgvxPSLGVJKAZE7k+ff0old

Gs0MFTfSOGQg+xymPliR5XbRgnR9Qp0I5LIvLWJxhik+nXa5h06q1kJIwKQVgg5dPZgEaprefDrQdbLZd

1T+bCZKiZxl8U+zva42eX23seJON8Rou037A0yJh5o7+Gp3eVreySpuW3QQKBgBbEwxxsZ+Gejl5eBtF4

Y3MsywPz7EJJLBfi48Mn3nmQPfo715WAUy96vHkQA3ZtG1FFzBk9P9hjUaVSRaOUDnd1rUqoU6iUGUMpT

uBZY32QGDEssPyQ+M55I0ZwppIYoPEH5osaW84ynN1bZyg89HWQ+zicrGJTTm+O5h9AkCijAoGBALzK5R

IxvqqP8kMKA53HYP3dt8rly1vwyhzke0ULf1Mw1f96TKRcMYV82+HD/ixVIR3Pdr5vURhAP71GEq7yy0X

HC76pO9EdBZp5ok/fvetxLN1TBNEPVuxAzooFBLXCoWhskEZC8tP7JksVKXiLv/kjUwRYwTUpSrBvMcEu

WgYv

"""



# 【支付宝公钥】(这里我专门做了修改)

# 请打开你截图的那个 alipayPublicKey_RSA2.txt 文件

# 全选 -> 复制 -> 直接覆盖粘贴到下面这个引号里

# 不需要管换行，也不要自己加 "-----BEGIN...", 代码会自动加！

ALIPAY_PUBLIC_KEY_CONTENT = """

MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAg3Al49jSZnlY9iPcunRgWZvgwT9X03z3L+oajd+3Yq8sq21F4r8XB/Pu0TuzqpR2uIjZis4DulE5LoB9JhDei9xw9If5y96QsoMmCmkBaDSBRwSko2TaJmA3MmgVOgWSRQ753Wgx5xffYOmmrPq/dQlGH0J91NaWyVf72kPgjgW6+1jq7rOHUc2aRlVF+SNwOPO9OI/8zk+2tmOZRvT2QvGnjteqe5zI1/cpZ9t4XkzFSMP84hn5xOHH5GTPXC1yM2U8quT+Vlte+I/2XwIx3zGq+PSnOPENwJHFS8bVFpkcYB91ZZFwBH2nLPua/kmMbh/j0h+/UcD8nrgrnlAdDQIDAQAB

"""





# ==============================================================================

# 核心修复逻辑 (私钥和公钥都进行清洗)

# ==============================================================================



def fix_key_format(key_content, is_private=True):

    """

    深度清洗并修复密钥格式：

    1. 去除所有头尾和空格

    2. 自动补充 Base64 padding

    3. 强制按64字符换行

    4. 加上正确的 PEM 头

    """

    # 1. 清洗 (去掉可能存在的旧头尾、空格、换行)

    key_content = key_content.replace("-----BEGIN RSA PRIVATE KEY-----", "")

    key_content = key_content.replace("-----END RSA PRIVATE KEY-----", "")

    key_content = key_content.replace("-----BEGIN PRIVATE KEY-----", "")

    key_content = key_content.replace("-----END PRIVATE KEY-----", "")

    key_content = key_content.replace("-----BEGIN PUBLIC KEY-----", "")

    key_content = key_content.replace("-----END PUBLIC KEY-----", "")

    key_content = key_content.replace("\n", "").replace(" ", "").strip()



    # 2. 补全 Base64 Padding

    missing_padding = len(key_content) % 4

    if missing_padding:

        key_content += '=' * (4 - missing_padding)



    # 3. 64字符换行

    split_key = '\n'.join([key_content[i:i + 64] for i in range(0, len(key_content), 64)])



    # 4. 加头

    if is_private:

        # 私钥使用 PKCS8 格式

        return f"-----BEGIN PRIVATE KEY-----\n{split_key}\n-----END PRIVATE KEY-----"

    else:

        # 公钥使用 Standard Public Key 格式 (对应 MIIBIj 开头)

        return f"-----BEGIN PUBLIC KEY-----\n{split_key}\n-----END PUBLIC KEY-----"





def run_pay():

    print("--------------------------------------------------")

    print("正在进行双重密钥检查...")



    # 1. 修复私钥

    final_private_key = fix_key_format(PRIVATE_KEY_CONTENT, is_private=True)

    # 2. 修复公钥 (新增步骤)

    final_public_key = fix_key_format(ALIPAY_PUBLIC_KEY_CONTENT, is_private=False)



    # === 诊断步骤 ===

    try:

        RSA.importKey(final_private_key)

        print("✅ 私钥格式检查通过！")

    except Exception as e:

        print(f"❌ 私钥还有问题: {e}")

        return



    try:

        RSA.importKey(final_public_key)

        print("✅ 公钥格式检查通过！")

    except Exception as e:

        print(f"❌ 公钥格式错误: {e}")

        print("请检查 ALIPAY_PUBLIC_KEY_CONTENT 是否复制了 alipayPublicKey_RSA2.txt 里的完整内容！")

        return



    print("--------------------------------------------------")

    print("格式检查完毕，正在生成支付链接...")



    try:

        alipay = AliPay(

            appid=APP_ID,

            app_notify_url=None,

            app_private_key_string=final_private_key,

            alipay_public_key_string=final_public_key,  # 使用修复后的公钥

            sign_type="RSA2",

            debug=False

        )



        out_trade_no = "pay_demo_" + str(int(time.time()))

        order_string = alipay.api_alipay_trade_page_pay(

            out_trade_no=out_trade_no,

            total_amount="10",

            subject="YunManGongFangAI",

            return_url="https://www.baidu.com"

        )



        pay_url = "https://openapi.alipay.com/gateway.do?" + order_string



        print("\n" + "=" * 20 + " 成功！复制下面的链接 " + "=" * 20)

        print("\n" + pay_url + "\n")

        print("=" * 60)



    except Exception as e:

        print(f"\n❌ 运行失败: {e}")





if __name__ == "__main__":

    run_pay()