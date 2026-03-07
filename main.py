import os
import requests


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK")


def call_deepseek():
    if not DEEPSEEK_API_KEY:
        raise ValueError("没有找到 DEEPSEEK_API_KEY，请先在 GitHub Secrets 里配置。")

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = """
你是一个金融情报分析助手。
请根据下面这条新闻，输出一个简洁的 JSON，不要输出任何多余文字。

新闻：
“中东局势升级，市场避险情绪上升，原油和黄金上涨，纳指期货走弱。”

请输出：
{
  "title": "一句话标题",
  "summary": "一句话摘要",
  "impact_assets": ["资产1", "资产2"],
  "impact_1d": "1天影响判断",
  "impact_3d": "3天影响判断",
  "impact_7d": "7天影响判断"
}
"""

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个严格输出 JSON 的助手。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    resp = requests.post(url, headers=headers, json=data, timeout=60)
    resp.raise_for_status()
    result = resp.json()

    return result["choices"][0]["message"]["content"]


def push_to_wecom(text):
    if not WECOM_WEBHOOK:
        raise ValueError("没有找到 WECOM_WEBHOOK，请先在 GitHub Secrets 里配置。")

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": text
        }
    }

    resp = requests.post(WECOM_WEBHOOK, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.text


def main():
    content = call_deepseek()

    message = f"""# 市场情报测试消息

以下是 DeepSeek 返回的分析结果：

```json
{content}
```"""

    result = push_to_wecom(message)
    print("推送结果：", result)


if __name__ == "__main__":
    main()
