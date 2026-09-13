from __future__ import annotations


ORDER_IMAGE_SCHEMA = {
    "platform": "",
    "source_image": "",
    "orders": [
        {
            "merchant": "",
            "status": "",
            "title": "",
            "spec": "",
            "quantity": "",
            "paid_amount": "",
            "original_amount": "",
            "shipping_fee": "",
            "order_time": "",
            "order_id": "",
            "logistics": "",
            "actions": [],
            "is_partial": False,
            "confidence": 0.0,
            "notes": "",
        }
    ],
    "warnings": [],
}


def build_order_image_prompt(platform: str, source_image: str) -> str:
    platform_name = {
        "pdd": "拼多多",
        "pinduoduo": "拼多多",
        "meituan": "美团",
    }.get(platform, platform)

    return f"""
你是个人消费订单截图识别器。请识别这张{platform_name}订单页面截图中的可见订单卡片，并只输出 JSON。

要求：
1. 只根据截图中看得见的信息提取，不要猜测。
2. 一个订单卡片输出一条 orders 记录。
3. 如果订单被截图顶部或底部截断，仍可输出，但 is_partial 必须为 true。
4. 金额字段只保留数字字符串，例如 "19.09"，不要输出人民币符号。
5. 没看清或不存在的字段填空字符串。
6. confidence 使用 0 到 1 的数字。
7. actions 填可见按钮文字，例如 ["申请退款", "查看物流"]。
8. 不要输出 Markdown，不要解释，不要包裹代码块。

JSON 顶层格式必须是：
{{
  "platform": "{platform}",
  "source_image": "{source_image}",
  "orders": [
    {{
      "merchant": "",
      "status": "",
      "title": "",
      "spec": "",
      "quantity": "",
      "paid_amount": "",
      "original_amount": "",
      "shipping_fee": "",
      "order_time": "",
      "order_id": "",
      "logistics": "",
      "actions": [],
      "is_partial": false,
      "confidence": 0.0,
      "notes": ""
    }}
  ],
  "warnings": []
}}
""".strip()
