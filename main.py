import os
import json
import time
import textwrap
from html import escape

import requests
from PIL import Image, ImageDraw, ImageFont


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK")

TEST_NEWS = "中东局势升级，市场避险情绪上升，原油和黄金上涨，纳指期货走弱。"

REPORT_URL = os.getenv("REPORT_URL", "https://mazikai666.github.io/market-intel-bot/")
DEFAULT_PIC_URL = os.getenv("DEFAULT_PIC_URL", REPORT_URL + "cover.png")
PUSH_TO_WECOM = os.getenv("PUSH_TO_WECOM", "false").lower() == "true"

REPORT_HTML_FILE = "report.html"
REPORT_META_FILE = "report_meta.json"
COVER_FILE = "cover.png"


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
你是一个专业财经媒体编辑。
请基于下面这条新闻，生成一篇“像知名财经媒体写法”的资讯稿素材。

要求：
1. 写法像资讯，不要像 AI 报告
2. 开头要有导语感，能吸引人读下去
3. 语气专业、克制、有信息密度
4. 强调：发生了什么、为什么值得看、对哪些资产影响最大
5. 不要写成八股文，不要写“事件概述/事情缘由”这种机械标题
6. 避免“必然、一定、注定”这类武断词
7. 严格输出 JSON，不要输出任何额外文字

新闻：
{news_text}

请输出：
{{
  "title": "更像财经媒体标题，18字以内",
  "subtitle": "一句副标题，点出市场主线",
  "deck": "导语，2到3句，像媒体开头摘要",
  "key_points": [
    "重点1",
    "重点2",
    "重点3"
  ],
  "why_now": "为什么这件事现在值得关注",
  "market_impact": "对市场意味着什么，用资讯风格写1段",
  "outlook_1d": "未来1天",
  "outlook_3d": "未来3天",
  "outlook_7d": "未来7天",
  "watchlist": [
    {{"name": "黄金", "view": "偏多", "reason": "一句原因"}},
    {{"name": "原油", "view": "偏多", "reason": "一句原因"}},
    {{"name": "纳指期货", "view": "偏空", "reason": "一句原因"}}
  ],
  "risk_warning": "一句风险提示",
  "cover": {{
    "theme": "封面主题，如 地缘风险 / AI突破 / 美联储观察",
    "strapline": "封面小字，12字以内",
    "tags": ["标签1", "标签2", "标签3"]
  }}
}}
"""

    data = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是一个严格输出 JSON 的财经资讯编辑。只返回 JSON 对象本身。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.6,
        "response_format": {"type": "json_object"}
    }

    resp = requests.post(url, headers=headers, json=data, timeout=90)
    resp.raise_for_status()
    result = resp.json()

    content = result["choices"][0]["message"]["content"]
    print("DeepSeek 原始返回：")
    print(repr(content))

    return extract_json_from_text(content)


def _safe_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def generate_cover_image(data: dict, filename: str = COVER_FILE) -> str:
    title = data.get("title", "市场情报")
    subtitle = data.get("subtitle", "")
    cover = data.get("cover", {})
    strapline = cover.get("strapline", "Market Intel")
    theme = cover.get("theme", "市场快讯")
    tags = cover.get("tags", [])[:3]

    width, height = 1600, 900
    img = Image.new("RGB", (width, height), "#0b1220")
    draw = ImageDraw.Draw(img)

    # background gradient-ish blocks
    draw.rectangle([0, 0, width, height], fill="#0b1220")
    draw.ellipse([950, -120, 1650, 580], fill="#153b8a")
    draw.ellipse([-180, 420, 520, 1120], fill="#10264f")
    draw.rounded_rectangle([70, 70, width - 70, height - 70], radius=36, outline="#27406e", width=2)

    # decorative bars
    draw.rounded_rectangle([90, 110, 290, 140], radius=12, fill="#1d4ed8")
    draw.rounded_rectangle([310, 110, 520, 140], radius=12, fill="#334155")

    title_font = _safe_font(74, bold=True)
    subtitle_font = _safe_font(30, bold=False)
    strap_font = _safe_font(26, bold=True)
    theme_font = _safe_font(28, bold=True)
    tag_font = _safe_font(24, bold=True)

    draw.text((100, 180), strapline, font=strap_font, fill="#93c5fd")
    draw.text((100, 230), theme, font=theme_font, fill="#ffffff")

    wrapped_title = textwrap.wrap(title, width=12)
    y = 330
    for line in wrapped_title[:3]:
        draw.text((100, y), line, font=title_font, fill="#ffffff")
        y += 98

    wrapped_sub = textwrap.wrap(subtitle, width=32)
    y += 10
    for line in wrapped_sub[:2]:
        draw.text((100, y), line, font=subtitle_font, fill="#cbd5e1")
        y += 44

    tag_x = 100
    tag_y = height - 145
    for tag in tags:
        box_w = max(150, 32 + len(tag) * 28)
        draw.rounded_rectangle([tag_x, tag_y, tag_x + box_w, tag_y + 54], radius=24, fill="#111827")
        draw.text((tag_x + 18, tag_y + 12), tag, font=tag_font, fill="#e5e7eb")
        tag_x += box_w + 18

    # market style line motif
    points = [(980, 640), (1060, 600), (1140, 620), (1230, 520), (1320, 560), (1400, 470), (1490, 510)]
    draw.line(points, fill="#60a5fa", width=8)
    for p in points:
        draw.ellipse([p[0]-8, p[1]-8, p[0]+8, p[1]+8], fill="#bfdbfe")

    img.save(filename, format="PNG")
    return filename


def build_html_report(data: dict) -> str:
    title = escape(data.get("title", "市场情报"))
    subtitle = escape(data.get("subtitle", ""))
    deck = escape(data.get("deck", ""))
    why_now = escape(data.get("why_now", ""))
    market_impact = escape(data.get("market_impact", ""))
    outlook_1d = escape(data.get("outlook_1d", ""))
    outlook_3d = escape(data.get("outlook_3d", ""))
    outlook_7d = escape(data.get("outlook_7d", ""))
    risk_warning = escape(data.get("risk_warning", ""))
    key_points = data.get("key_points", [])
    watchlist = data.get("watchlist", [])

    key_points_html = "".join(
        f'<li>{escape(item)}</li>' for item in key_points[:3]
    )

    watch_html = ""
    for item in watchlist:
        name = escape(item.get("name", "未知资产"))
        view = escape(item.get("view", "中性"))
        reason = escape(item.get("reason", ""))
        cls = "up" if view == "偏多" else ("down" if view == "偏空" else "flat")
        watch_html += f"""
        <div class="asset-card">
          <div class="asset-top">
            <div class="asset-name">{name}</div>
            <div class="badge {cls}">{view}</div>
          </div>
          <div class="asset-reason">{reason}</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      background: #f3f6fb;
      color: #111827;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.8;
    }}
    .wrap {{
      max-width: 980px;
      margin: 0 auto;
      padding: 24px 16px 56px;
    }}
    .hero-image {{
      width: 100%;
      border-radius: 24px;
      display: block;
      box-shadow: 0 16px 40px rgba(15,23,42,.12);
    }}
    .headline {{
      margin-top: 26px;
      background: #fff;
      border-radius: 22px;
      padding: 28px 26px;
      box-shadow: 0 8px 24px rgba(15,23,42,.06);
    }}
    .headline h1 {{
      margin: 0;
      font-size: 38px;
      line-height: 1.28;
      letter-spacing: -0.02em;
    }}
    .sub {{
      margin-top: 12px;
      font-size: 18px;
      color: #475569;
    }}
    .deck {{
      margin-top: 18px;
      font-size: 19px;
      color: #1f2937;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.3fr 0.9fr;
      gap: 18px;
      margin-top: 18px;
    }}
    .card {{
      background: #fff;
      border-radius: 20px;
      padding: 22px 22px;
      box-shadow: 0 8px 24px rgba(15,23,42,.06);
    }}
    .card h2 {{
      margin: 0 0 14px;
      font-size: 22px;
    }}
    .summary-list {{
      margin: 0;
      padding-left: 20px;
    }}
    .summary-list li {{
      margin-bottom: 10px;
      font-size: 17px;
    }}
    .story p {{
      margin: 0 0 16px;
      font-size: 18px;
      color: #1f2937;
    }}
    .outlook-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
      margin-top: 18px;
    }}
    .mini {{
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 16px;
      padding: 16px;
    }}
    .mini h3 {{
      margin: 0 0 10px;
      font-size: 17px;
    }}
    .watch-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 14px;
    }}
    .asset-card {{
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 16px;
      padding: 16px;
    }}
    .asset-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
    }}
    .asset-name {{
      font-size: 18px;
      font-weight: 700;
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
      color: #475569;
      font-size: 15px;
    }}
    .risk {{
      background: #fff7ed;
      border: 1px solid #fed7aa;
    }}
    @media (max-width: 760px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
      .outlook-grid {{
        grid-template-columns: 1fr;
      }}
      .headline h1 {{
        font-size: 30px;
      }}
      .deck {{
        font-size: 17px;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <img class="hero-image" src="cover.png" alt="cover">

    <section class="headline">
      <h1>{title}</h1>
      <div class="sub">{subtitle}</div>
      <div class="deck">{deck}</div>
    </section>

    <section class="grid">
      <div class="card">
        <h2>这篇资讯最值得看的三点</h2>
        <ul class="summary-list">
          {key_points_html}
        </ul>
      </div>

      <div class="card">
        <h2>市场在看什么</h2>
        <div class="story">
          <p>{why_now}</p>
        </div>
      </div>
    </section>

    <section class="card story">
      <h2>为什么这件事会牵动市场</h2>
      <p>{market_impact}</p>
    </section>

    <section class="card">
      <h2>接下来 1 到 7 天怎么看</h2>
      <div class="outlook-grid">
        <div class="mini">
          <h3>1天</h3>
          <div>{outlook_1d}</div>
        </div>
        <div class="mini">
          <h3>3天</h3>
          <div>{outlook_3d}</div>
        </div>
        <div class="mini">
          <h3>7天</h3>
          <div>{outlook_7d}</div>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>值得盯住的资产</h2>
      <div class="watch-grid">
        {watch_html}
      </div>
    </section>

    <section class="card risk">
      <h2>还要留意什么变量</h2>
      <div>{risk_warning}</div>
    </section>
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
        "description": data.get("deck", data.get("description", "暂无摘要")),
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

    generate_cover_image(data, COVER_FILE)
    html = build_html_report(data)

    save_html_report(html)
    save_report_meta(data)

    print(f"已生成 HTML 报告：{REPORT_HTML_FILE}")
    print(f"已生成封面图：{COVER_FILE}")
    print(f"已生成报告元数据：{REPORT_META_FILE}")


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
