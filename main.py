import os
import time
import json
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
你是一个金融市场情报分析助手。
请根据下面这条新闻，输出严格 JSON，不要输出任何多余文字，不要加 markdown，不要写“作为AI”。

新闻：
“中东局势升级，市场避险情绪上升，原油和黄金上涨，纳指期货走弱。”

请输出以下格式：
{
  "title": "一句吸引人的快讯标题",
  "event_summary": "用2-3句话概述发生了什么",
  "background_reason": "说明事情缘由、背景，以及为什么这件事会引起市场关注",
  "market_logic": "说明这件事是如何一步步传导到金融市场的，尽量写清因果链",
  "impact_1d": "未来1天的影响判断",
  "impact_3d": "未来3天的影响判断",
  "impact_7d": "未来7天的影响判断",
  "affected_assets": [
    {"name": "资产名", "view": "偏多/偏空/震荡", "reason": "受影响原因"}
  ],
  "risk_warning": "一句风险提示"
}
"""

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个严格输出 JSON 的金融分析助手，强调因果逻辑，避免空泛主观表达。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }

    resp = requests.post(url, headers=headers, json=data, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    return result["choices"][0]["message"]["content"]


def format_wecom_message(content):
    data = json.loads(content)

    title = data.get("title", "市场情报快讯")
    event_summary = data.get("event_summary", "暂无事件概述")
    background_reason = data.get("background_reason", "暂无背景说明")
    market_logic = data.get("market_logic", "暂无传导逻辑")
    impact_1d = data.get("impact_1d", "暂无判断")
    impact_3d = data.get("impact_3d", "暂无判断")
    impact_7d = data.get("impact_7d", "暂无判断")
    affected_assets = data.get("affected_assets", [])
    risk_warning = data.get("risk_warning", "请注意市场波动风险")

    asset_lines = []
    for item in affected_assets:
        name = item.get("name", "未知资产")
        view = item.get("view", "未知")
        reason = item.get("reason", "暂无原因")
        asset_lines.append(f"- {name}：{view}（{reason}）")

    assets_text = "\n".join(asset_lines) if asset_lines else "- 暂无重点资产"

    message = f"""# {title}

> AI 市场情报快讯

**事件概述**  
{event_summary}

**事情缘由**  
{background_reason}

**市场传导逻辑**  
{market_logic}

**短期判断（1天）**  
{impact_1d}

**短期判断（3天）**  
{impact_3d}

**短期判断（7天）**  
{impact_7d}

**重点资产**  
{assets_text}

**风险提示**  
{risk_warning}
"""
    return message


def push_to_wecom(text, max_retries=3):
    if not WECOM_WEBHOOK:
        raise ValueError("没有找到 WECOM_WEBHOOK，请先在 GitHub Secrets 里配置。")

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": text
        }
    }

    last_error = None

    for i in range(max_retries):
        try:
            print(f"企业微信推送尝试第 {i+1} 次...")
            resp = requests.post(WECOM_WEBHOOK, json=payload, timeout=20)
            resp.raise_for_status()
            print("企业微信返回：", resp.text)
            return resp.text
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"第 {i+1} 次推送失败：{e}")
            time.sleep(5)

    raise last_error


def main():
    print("开始调用 DeepSeek...")
    content = call_deepseek()
    print("DeepSeek 返回内容：")
    print(content)

    message = format_wecom_message(content)
    print("格式化后的企业微信消息：")
    print(message)

    print("开始推送到企业微信...")
    result = push_to_wecom(message)
    print("推送结果：", result)


if __name__ == "__main__":
    main()
