import os
import json
import time
import requests


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK")

TEST_NEWS = "中东局势升级，市场避险情绪上升，原油和黄金上涨，纳指期货走弱。"

REPORT_URL = os.getenv("REPORT_URL", "https://mazikai666.github.io/market-intel-bot/")
DEFAULT_PIC_URL = os.getenv("DEFAULT_PIC_URL", "https://picsum.photos/900/500")
PUSH_TO_WECOM = os.getenv("PUSH_TO_WECOM", "false").lower() == "true"

REPORT_HTML_FILE = "report.html"
REPORT_META_FILE = "report_meta.json"


def extract_json_from_text(content: str) -> dict:
    if not content or not content.strip():
        raise ValueError("DeepSeek 返回为空，请检查 API 响应。")

    content = content.strip()

    if content.startswith("```json"):
        content = content[len("```json"):].strip()
    elif content.startswith("```"):
        content = content[len("```"):].strip()

    if content.endswith("```"):
        content = content[:-3].strip()

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"无法从 DeepSeek 返回中提取 JSON：{content}")

    json_text = content[start:end + 1]
    print("清洗后的 JSON 文本：")
    print(json_text)

    return json.loads(json_text)


def call_deepseek(news_text: str) -> dict:
    if not DEEPSEEK_API_KEY:
        raise ValueError("没有找到 DEEPSEEK_API_KEY，请先在 GitHub Secrets 里配置。")

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
你是一个专业的市场情报编辑。
请基于下面这条新闻，生成一个适合“企业微信图文消息 + 网页分析报告”的内容。

要求：
1. 不要写成公告，不要写成长文堆砌
2. 图文卡片摘要要简洁、抓眼球、舒服
3. 完整报告要强调：事件 -> 缘由 -> 市场传导 -> 结论 -> 风险
4. 不要写太空泛的话
5. 避免“必然”“一定”这类过度武断表达
6. 严格输出 JSON，不要输出任何额外内容

新闻：
{news_text}

请输出：
{{
  "title": "20字以内，像财经快讯标题",
  "description": "80到120字，适合企业微信图文卡片摘要，要包含发生了什么、为什么重要、影响了什么资产",
  "report_title": "完整分析页面的大标题",
  "event_summary": "事件概述，2到3句",
  "background_reason": "事情缘由与背景，说明为什么这件事值得市场关注",
  "market_logic": "市场传导逻辑，讲清楚因果链",
  "impact_1d": "未来1天影响判断",
  "impact_3d": "未来3天影响判断",
  "impact_7d": "未来7天影响判断",
  "risk_warning": "风险提示"
}}
"""

    data = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是一个严格输出 JSON 的市场情报编辑。只返回 JSON 对象本身，不要加解释，不要加代码块。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.5,
    }

    resp = requests.post(url, headers=headers, json=data, timeout=90)
    resp.raise_for_status()
    result = resp.json()

    content = result["choices"][0]["message"]["content"]
    print("DeepSeek 原始返回：")
    print(repr(content))

    return extract_json_from_text(content)


def build_html_report(data: dict) -> str:
    report_title = data.get("report_title", "市场情报完整分析")
    event_summary = data.get("event_summary", "")
    background_reason = data.get("background_reason", "")
    market_logic = data.get("market_logic", "")
    impact_1d = data.get("impact_1d", "")
    impact_3d = data.get("impact_3d", "")
    impact_7d = data.get("impact_7d", "")
    risk_warning = data.get("risk_warning", "")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{report_title}</title>
  <style>
    body {{
      margin: 0;
      background: #f6f8fb;
      color: #1f2937;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.75;
    }}
    .wrap {{
      max-width: 820px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    .hero {{
      background: linear-gradient(135deg, #0f172a, #1d4ed8);
      color: white;
      border-radius: 20px;
      padding: 28px 24px;
      box-shadow: 0 10px 30px rgba(0,0,0,.12);
    }}
    .hero h1 {{
      margin: 0;
      font-size: 30px;
      line-height: 1.3;
    }}
    .card {{
      background: white;
      border-radius: 18px;
      padding: 22px 20px;
      margin-top: 18px;
      box-shadow: 0 6px 18px rgba(15,23,42,.06);
    }}
    .card h2 {{
      margin: 0 0 12px;
      font-size: 20px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }}
    .mini {{
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 14px;
      padding: 16px;
    }}
    .risk {{
      background: #fff7ed;
      border: 1px solid #fed7aa;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>{report_title}</h1>
    </div>

    <div class="card">
      <h2>事件概述</h2>
      <p>{event_summary}</p>
    </div>

    <div class="card">
      <h2>事情缘由</h2>
      <p>{background_reason}</p>
    </div>

    <div class="card">
      <h2>市场传导逻辑</h2>
      <p>{market_logic}</p>
    </div>

    <div class="card">
      <h2>短期判断</h2>
      <div class="grid">
        <div class="mini">
          <h3>1天</h3>
          <p>{impact_1d}</p>
        </div>
        <div class="mini">
          <h3>3天</h3>
          <p>{impact_3d}</p>
        </div>
        <div class="mini">
          <h3>7天</h3>
          <p>{impact_7d}</p>
        </div>
      </div>
    </div>

    <div class="card risk">
      <h2>风险提示</h2>
      <p>{risk_warning}</p>
    </div>
  </div>
</body>
</html>
"""
    return html


def save_html_report(html: str, filename: str = REPORT_HTML_FILE) -> str:
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    return filename


def save_report_meta(data: dict, filename: str = REPORT_META_FILE) -> str:
    meta = {
        "title": data.get("title", "市场快讯"),
        "description": data.get("description", "暂无摘要"),
        "url": REPORT_URL,
        "picurl": DEFAULT_PIC_URL
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return filename


def load_report_meta(filename: str = REPORT_META_FILE) -> dict:
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def push_news_to_wecom(title: str, description: str, url: str, picurl: str, max_retries: int = 3) -> str:
    if not WECOM_WEBHOOK:
        raise ValueError("没有找到 WECOM_WEBHOOK，请先在 GitHub Secrets 里配置。")

    payload = {
        "msgtype": "news",
        "news": {
            "articles": [
                {
                    "title": title,
                    "description": description,
                    "url": url,
                    "picurl": picurl
                }
            ]
        }
    }

    last_error = None
    for i in range(max_retries):
        try:
            print(f"企业微信图文推送尝试第 {i + 1} 次...")
            resp = requests.post(WECOM_WEBHOOK, json=payload, timeout=20)
            resp.raise_for_status()
            print("企业微信返回：", resp.text)
            return resp.text
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"第 {i + 1} 次图文推送失败：{e}")
            time.sleep(5)

    raise last_error


def generate_report():
    print("开始调用 DeepSeek...")
    data = call_deepseek(TEST_NEWS)
    print("DeepSeek 解析后的结果：")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    html = build_html_report(data)
    html_file = save_html_report(html)
    meta_file = save_report_meta(data)

    print(f"已生成 HTML 报告：{html_file}")
    print(f"已生成报告元数据：{meta_file}")


def push_existing_report():
    meta = load_report_meta()
    print("读取 report_meta.json：")
    print(json.dumps(meta, ensure_ascii=False, indent=2))

    result = push_news_to_wecom(
        title=meta["title"],
        description=meta["description"],
        url=meta["url"],
        picurl=meta["picurl"],
    )
    print("推送结果：", result)


def main():
    generate_report()

    if PUSH_TO_WECOM:
        print("开始发送企业微信图文消息...")
        push_existing_report()
    else:
        print("当前只生成报告，不推送企业微信。")


if __name__ == "__main__":
    main()
