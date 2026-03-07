import os
import time
import json
import requests
from datetime import datetime


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK")


TEST_NEWS = """中东局势升级，市场避险情绪上升，原油和黄金上涨，纳指期货走弱。"""


def call_deepseek(news_text: str) -> dict:
    if not DEEPSEEK_API_KEY:
        raise ValueError("没有找到 DEEPSEEK_API_KEY，请先在 GitHub Secrets 里配置。")

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
你是一个专业的金融市场情报分析助手。
你的任务是根据一条新闻，产出：

1. 一个适合发在企业微信群里的“短消息”
2. 一个适合网页展示的“完整图文分析”

要求：
- 结论必须建立在“事件 -> 背景缘由 -> 市场传导逻辑 -> 短期判断”的链条上
- 避免主观武断表达，不要写“必然”“一定”
- 强调为什么得出这个结论
- 企业微信短消息必须简洁舒服，适合快速阅读
- 完整分析页要分段清楚，适合网页展示
- 严格输出 JSON，不要输出任何额外文字，不要 markdown 代码块

新闻如下：
{news_text}

请严格输出以下 JSON 结构：
{{
  "title": "吸引人的标题",
  "subtitle": "一句副标题，说明主线",
  "short_push": {{
    "headline": "适合企业微信的标题",
    "summary": "2-3句核心摘要",
    "why_it_matters": "1-2句说明为什么重要",
    "key_assets": [
      {{"name": "黄金", "view": "偏多"}},
      {{"name": "原油", "view": "偏多"}},
      {{"name": "纳指期货", "view": "偏空"}}
    ],
    "cta": "查看完整分析"
  }},
  "full_report": {{
    "event_summary": "事件概述，2-3句",
    "background_reason": "事情缘由与背景",
    "market_logic": "市场传导逻辑，讲清楚因果链",
    "impact_1d": "未来1天影响判断",
    "impact_3d": "未来3天影响判断",
    "impact_7d": "未来7天影响判断",
    "affected_assets": [
      {{
        "name": "黄金",
        "view": "偏多",
        "reason": "受影响原因"
      }},
      {{
        "name": "原油",
        "view": "偏多",
        "reason": "受影响原因"
      }},
      {{
        "name": "纳指期货",
        "view": "偏空",
        "reason": "受影响原因"
      }}
    ],
    "risk_warning": "风险提示"
  }}
}}
"""

    data = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是一个严格输出 JSON 的金融分析助手，强调证据链、因果链和清晰表达。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.4
    }

    resp = requests.post(url, headers=headers, json=data, timeout=90)
    resp.raise_for_status()
    result = resp.json()
    content = result["choices"][0]["message"]["content"]
    return json.loads(content)


def build_short_wecom_markdown(data: dict, report_url: str = "") -> str:
    short_push = data.get("short_push", {})
    title = short_push.get("headline", data.get("title", "市场情报快讯"))
    summary = short_push.get("summary", "暂无摘要")
    why_it_matters = short_push.get("why_it_matters", "暂无说明")
    key_assets = short_push.get("key_assets", [])
    cta = short_push.get("cta", "查看完整分析")

    asset_lines = []
    for item in key_assets[:3]:
        name = item.get("name", "未知资产")
        view = item.get("view", "未知")
        symbol = "↑" if view == "偏多" else ("↓" if view == "偏空" else "→")
        asset_lines.append(f"• {name} {symbol} {view}")

    assets_text = "\n".join(asset_lines) if asset_lines else "• 暂无重点资产"

    link_text = f"[{cta}]({report_url})" if report_url else cta

    message = f"""# {title}

> AI 市场情报快讯

**核心结论**
{summary}

**为什么重要**
{why_it_matters}

**重点资产**
{assets_text}

**详情**
{link_text}
"""
    return message


def build_html_report(data: dict) -> str:
    title = data.get("title", "市场情报分析")
    subtitle = data.get("subtitle", "")
    full_report = data.get("full_report", {})

    event_summary = full_report.get("event_summary", "")
    background_reason = full_report.get("background_reason", "")
    market_logic = full_report.get("market_logic", "")
    impact_1d = full_report.get("impact_1d", "")
    impact_3d = full_report.get("impact_3d", "")
    impact_7d = full_report.get("impact_7d", "")
    risk_warning = full_report.get("risk_warning", "")
    affected_assets = full_report.get("affected_assets", [])

    asset_cards = ""
    for asset in affected_assets:
        name = asset.get("name", "未知资产")
        view = asset.get("view", "未知")
        reason = asset.get("reason", "暂无说明")

        if view == "偏多":
            badge_class = "up"
        elif view == "偏空":
            badge_class = "down"
        else:
            badge_class = "flat"

        asset_cards += f"""
        <div class="asset-card">
            <div class="asset-top">
                <div class="asset-name">{name}</div>
                <div class="badge {badge_class}">{view}</div>
            </div>
            <div class="asset-reason">{reason}</div>
        </div>
        """

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background: #f5f7fb;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      color: #1f2937;
      line-height: 1.75;
    }}
    .container {{
      max-width: 860px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    .hero {{
      background: linear-gradient(135deg, #111827, #1f3b73);
      color: #fff;
      border-radius: 18px;
      padding: 28px 24px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.15);
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-size: 28px;
      line-height: 1.3;
    }}
    .hero p {{
      margin: 0;
      color: rgba(255,255,255,0.85);
      font-size: 16px;
    }}
    .meta {{
      margin-top: 12px;
      font-size: 13px;
      color: rgba(255,255,255,0.7);
    }}
    .card {{
      background: #fff;
      border-radius: 16px;
      padding: 22px 20px;
      margin-top: 18px;
      box-shadow: 0 6px 20px rgba(15, 23, 42, 0.06);
    }}
    .card h2 {{
      margin: 0 0 12px;
      font-size: 20px;
      color: #111827;
    }}
    .pill-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 8px;
    }}
    .pill {{
      background: #eef2ff;
      color: #3730a3;
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 13px;
      font-weight: 600;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-top: 12px;
    }}
    .mini-card {{
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 14px;
      padding: 16px;
    }}
    .mini-card h3 {{
      margin: 0 0 8px;
      font-size: 16px;
    }}
    .asset-list {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
      margin-top: 12px;
    }}
    .asset-card {{
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 14px;
      padding: 16px;
    }}
    .asset-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
    }}
    .asset-name {{
      font-size: 17px;
      font-weight: 700;
      color: #111827;
    }}
    .badge {{
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 700;
    }}
    .badge.up {{
      background: #dcfce7;
      color: #166534;
    }}
    .badge.down {{
      background: #fee2e2;
      color: #991b1b;
    }}
    .badge.flat {{
      background: #e5e7eb;
      color: #374151;
    }}
    .asset-reason {{
      font-size: 14px;
      color: #4b5563;
    }}
    .risk {{
      background: #fff7ed;
      border: 1px solid #fed7aa;
      color: #9a3412;
    }}
    .footer {{
      margin-top: 24px;
      text-align: center;
      color: #6b7280;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <section class="hero">
      <h1>{title}</h1>
      <p>{subtitle}</p>
      <div class="meta">生成时间：{now}</div>
    </section>

    <section class="card">
      <h2>事件概述</h2>
      <p>{event_summary}</p>
    </section>

    <section class="card">
      <h2>事情缘由</h2>
      <p>{background_reason}</p>
    </section>

    <section class="card">
      <h2>市场传导逻辑</h2>
      <p>{market_logic}</p>
      <div class="pill-row">
        <span class="pill">事件发生</span>
        <span class="pill">风险偏好变化</span>
        <span class="pill">资金流向重估</span>
        <span class="pill">资产价格反应</span>
      </div>
    </section>

    <section class="card">
      <h2>短期影响判断</h2>
      <div class="grid">
        <div class="mini-card">
          <h3>1天</h3>
          <p>{impact_1d}</p>
        </div>
        <div class="mini-card">
          <h3>3天</h3>
          <p>{impact_3d}</p>
        </div>
        <div class="mini-card">
          <h3>7天</h3>
          <p>{impact_7d}</p>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>重点资产</h2>
      <div class="asset-list">
        {asset_cards}
      </div>
    </section>

    <section class="card risk">
      <h2>风险提示</h2>
      <p>{risk_warning}</p>
    </section>

    <div class="footer">
      本页面由 AI 自动生成，用于市场情报整理与阅读辅助。
    </div>
  </div>
</body>
</html>
"""
    return html


def save_html_report(html: str, filename: str = "report.html") -> str:
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    return filename


def push_to_wecom_markdown(text: str, max_retries: int = 3) -> str:
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
            print(f"企业微信推送尝试第 {i + 1} 次...")
            resp = requests.post(WECOM_WEBHOOK, json=payload, timeout=20)
            resp.raise_for_status()
            print("企业微信返回：", resp.text)
            return resp.text
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"第 {i + 1} 次推送失败：{e}")
            time.sleep(5)

    raise last_error


def main():
    print("开始调用 DeepSeek...")
    data = call_deepseek(TEST_NEWS)
    print("DeepSeek 返回 JSON：")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    html = build_html_report(data)
    filename = save_html_report(html)
    print(f"HTML 报告已生成：{filename}")

    # 这里先留空链接，等你后面接 GitHub Pages 再填
    report_url = ""

    wecom_message = build_short_wecom_markdown(data, report_url=report_url)
    print("格式化后的企业微信消息：")
    print(wecom_message)

    print("开始推送到企业微信...")
    result = push_to_wecom_markdown(wecom_message)
    print("推送结果：", result)


if __name__ == "__main__":
    main()
