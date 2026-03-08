import os
import io
import json
import time
import textwrap
from html import escape
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from feeds import fetch_all_feeds
from selector import deduplicate_news, pick_best_news
from state import filter_unsent_news, mark_news_sent


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK")

REPORT_URL = os.getenv("REPORT_URL", "https://mazikai666.github.io/market-intel-bot/")
DEFAULT_PIC_URL = os.getenv("DEFAULT_PIC_URL", REPORT_URL + "cover.jpg")
PUSH_TO_WECOM = os.getenv("PUSH_TO_WECOM", "false").lower() == "true"

TEST_NEWS = os.getenv("TEST_NEWS", "").strip()
SOURCE_ARTICLE_URL = os.getenv("SOURCE_ARTICLE_URL", "").strip()

REPORT_HTML_FILE = "report.html"
REPORT_META_FILE = "report_meta.json"
COVER_FILE = "cover.jpg"
IMAGES_DIR = "images"

CATEGORY_META = {
    "breaking": {"label": "全球突发", "prefix": "【全球突发】", "color": "#b91c1c"},
    "market": {"label": "市场金融", "prefix": "【市场快讯】", "color": "#1d4ed8"},
    "tech": {"label": "科技突破", "prefix": "【科技情报】", "color": "#7c3aed"},
    "business": {"label": "公司商业", "prefix": "【商业动态】", "color": "#0f766e"},
}


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def extract_json_from_text(content: str) -> dict:
    content = (content or "").strip()
    if not content:
        raise ValueError("DeepSeek 返回为空。")

    if content.startswith("```json"):
        content = content[len("```json"):].strip()
    elif content.startswith("```"):
        content = content[len("```"):].strip()
    if content.endswith("```"):
        content = content[:-3].strip()

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"无法提取 JSON：{content}")

    return json.loads(content[start:end + 1])


def safe_font(size: int, bold: bool = False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def choose_news() -> dict:
    if TEST_NEWS:
        return {
            "title": TEST_NEWS[:120],
            "description": TEST_NEWS,
            "link": SOURCE_ARTICLE_URL,
            "source": "Manual Input",
            "pub_date": "",
            "language": "en",
        }

    items = fetch_all_feeds()
    items = deduplicate_news(items)
    items = filter_unsent_news(items)

    picked = pick_best_news(items)
    if not picked:
        raise ValueError("没有新的可推送新闻了。")

    print("选中的新闻：")
    print(json.dumps(picked, ensure_ascii=False, indent=2))
    return picked


def call_deepseek(news_item: dict) -> dict:
    if not DEEPSEEK_API_KEY:
        raise ValueError("没有找到 DEEPSEEK_API_KEY。")

    news_text = f"""Title: {news_item.get('title', '')}
Summary: {news_item.get('description', '')}
Source: {news_item.get('source', '')}
Published: {news_item.get('pub_date', '')}
Link: {news_item.get('link', '')}
"""

    prompt = f"""
You are a global news editor.

You will receive an English news item from an international source.
Read it carefully, understand it, then write the final output in fluent Chinese.
Do not translate mechanically. Digest first, then rewrite as a polished Chinese intelligence-style feature page.

Allowed categories:
- breaking
- market
- tech
- business

Return strict JSON only.

English source:
{news_text}

Return:
{{
  "category": "breaking or market or tech or business",
  "title": "中文标题，18字以内",
  "subtitle": "中文副标题，一句话",
  "deck": "中文导语，2到3句",
  "key_points": ["重点1", "重点2", "重点3"],
  "background": "背景与来龙去脉",
  "why_now": "为什么现在值得关注",
  "timeline": [
    {{"time": "节点1", "event": "事件1"}},
    {{"time": "节点2", "event": "事件2"}},
    {{"time": "节点3", "event": "事件3"}}
  ],
  "section_1_title": "第一部分标题",
  "section_1_body": "第一部分正文",
  "section_2_title": "第二部分标题",
  "section_2_body": "第二部分正文",
  "global_impact": "全球影响",
  "market_or_industry_impact": "市场或产业影响",
  "watch_points": ["观察点1", "观察点2", "观察点3"],
  "watchlist": [
    {{"name": "对象1", "view": "偏多/偏空/关注/中性", "reason": "一句原因"}},
    {{"name": "对象2", "view": "偏多/偏空/关注/中性", "reason": "一句原因"}},
    {{"name": "对象3", "view": "偏多/偏空/关注/中性", "reason": "一句原因"}}
  ],
  "outlook_1d": "未来1天",
  "outlook_3d": "未来3天",
  "outlook_7d": "未来7天",
  "risk_warning": "一句风险提示",
  "sources": [
    {{"name": "来源1", "note": "为什么值得看"}},
    {{"name": "来源2", "note": "为什么值得看"}}
  ]
}}
"""

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a strict JSON-only global editor."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.75,
        "response_format": {"type": "json_object"},
    }

    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=90,
    )
    resp.raise_for_status()
    result = resp.json()
    data = extract_json_from_text(result["choices"][0]["message"]["content"])

    if data.get("category") not in CATEGORY_META:
        data["category"] = "breaking"
    return data


def generate_fallback_cover(data: dict, filename: str = COVER_FILE) -> str:
    category = data.get("category", "breaking")
    color = CATEGORY_META.get(category, CATEGORY_META["breaking"])["color"]

    title = data.get("title", "全球情报")
    subtitle = data.get("subtitle", "")

    w, h = 1600, 900
    img = Image.new("RGB", (w, h), "#07111f")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, w, h], fill="#07111f")
    draw.ellipse([980, -120, 1700, 560], fill=color)
    draw.ellipse([-250, 470, 520, 1200], fill="#0f2348")
    draw.rounded_rectangle([60, 60, w - 60, h - 60], radius=36, outline="#27406e", width=2)

    title_font = safe_font(76, bold=True)
    sub_font = safe_font(30, bold=False)

    y = 230
    for line in textwrap.wrap(title, width=12)[:3]:
        draw.text((100, y), line, font=title_font, fill="#ffffff")
        y += 96

    for line in textwrap.wrap(subtitle, width=34)[:2]:
        draw.text((100, y + 8), line, font=sub_font, fill="#d1d5db")
        y += 44

    img.save(filename, format="JPEG", quality=92)
    return filename


def normalize_img_url(src: str, base_url: str) -> str:
    return urljoin(base_url, src) if src else ""


def is_good_image_url(url: str) -> bool:
    lowered = url.lower()
    bad = ["logo", "icon", "avatar", "ads", "sprite", "badge", "emoji"]
    return not any(k in lowered for k in bad)


def download_image(url: str, out_path: str, timeout: int = 25) -> bool:
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        if "image" not in resp.headers.get("Content-Type", ""):
            return False

        img = Image.open(io.BytesIO(resp.content))
        w, h = img.size
        if w < 500 or h < 280:
            return False

        img.convert("RGB").save(out_path, format="JPEG", quality=90)
        return True
    except Exception:
        return False


def fetch_article_images(article_url: str, max_images: int = 4) -> list[str]:
    if not article_url:
        return []

    ensure_dir(IMAGES_DIR)

    try:
        resp = requests.get(article_url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    candidates = []

    for selector, attr in [
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
        ('meta[property="twitter:image"]', "content"),
    ]:
        tag = soup.select_one(selector)
        if tag and tag.get(attr):
            candidates.append(normalize_img_url(tag.get(attr), article_url))

    for img in soup.select("article img, main img, figure img, img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("srcset")
        if not src:
            continue
        if img.get("srcset"):
            src = img.get("srcset").split(",")[-1].strip().split(" ")[0]
        full = normalize_img_url(src, article_url)
        if full:
            candidates.append(full)

    unique = []
    seen = set()
    for u in candidates:
        if not u or u in seen:
            continue
        seen.add(u)
        if is_good_image_url(u):
            unique.append(u)

    saved = []
    for img_url in unique:
        if len(saved) >= max_images:
            break
        out_path = os.path.join(IMAGES_DIR, f"source_{len(saved)+1}.jpg")
        if download_image(img_url, out_path):
            saved.append(out_path)

    return saved


def choose_cover_image(source_images: list[str]) -> str:
    if source_images:
        try:
            with Image.open(source_images[0]) as img:
                img.convert("RGB").save(COVER_FILE, format="JPEG", quality=92)
            return COVER_FILE
        except Exception:
            pass
    return COVER_FILE


def render_watch_cards(items: list[dict]) -> str:
    html = ""
    for item in items[:6]:
        name = escape(item.get("name", "未知对象"))
        view = escape(item.get("view", "中性"))
        reason = escape(item.get("reason", ""))
        cls = "up" if view in ["偏多", "利多"] else ("down" if view in ["偏空", "利空"] else "flat")
        html += f"""
        <div class="watch-card">
          <div class="watch-top">
            <div class="watch-name">{name}</div>
            <div class="badge {cls}">{view}</div>
          </div>
          <div class="watch-reason">{reason}</div>
        </div>
        """
    return html


def render_timeline(items: list[dict]) -> str:
    if not items:
        return "<div class='timeline-item'><div class='timeline-time'>Now</div><div class='timeline-event'>当前暂无时间线细节。</div></div>"

    html = ""
    for item in items[:5]:
        t = escape(item.get("time", "时间待定"))
        e = escape(item.get("event", "事件待补充"))
        html += f"""
        <div class="timeline-item">
          <div class="timeline-time">{t}</div>
          <div class="timeline-event">{e}</div>
        </div>
        """
    return html


def render_list(items: list[str], empty_text: str) -> str:
    if not items:
        return f"<li>{empty_text}</li>"
    return "".join(f"<li>{escape(x)}</li>" for x in items[:5])


def render_sources(items: list[dict]) -> str:
    if not items:
        return "<div class='source-item'><div class='source-name'>AI Desk</div><div class='source-note'>当前未提供额外来源说明。</div></div>"

    html = ""
    for item in items[:5]:
        name = escape(item.get("name", "来源"))
        note = escape(item.get("note", ""))
        html += f"""
        <div class="source-item">
          <div class="source-name">{name}</div>
          <div class="source-note">{note}</div>
        </div>
        """
    return html


def build_html_report(data: dict, source_images: list[str]) -> str:
    category = data.get("category", "breaking")
    meta = CATEGORY_META.get(category, CATEGORY_META["breaking"])
    accent = meta["color"]

    title = escape(data.get("title", "全球情报"))
    subtitle = escape(data.get("subtitle", ""))
    deck = escape(data.get("deck", ""))
    background = escape(data.get("background", ""))
    why_now = escape(data.get("why_now", ""))
    global_impact = escape(data.get("global_impact", ""))
    section_1_title = escape(data.get("section_1_title", "第一观察"))
    section_1_body = escape(data.get("section_1_body", ""))
    section_2_title = escape(data.get("section_2_title", "第二观察"))
    section_2_body = escape(data.get("section_2_body", ""))
    market_or_industry_impact = escape(data.get("market_or_industry_impact", ""))
    outlook_1d = escape(data.get("outlook_1d", ""))
    outlook_3d = escape(data.get("outlook_3d", ""))
    outlook_7d = escape(data.get("outlook_7d", ""))
    risk_warning = escape(data.get("risk_warning", ""))
    key_points_html = render_list(data.get("key_points", []), "暂无重点。")
    watch_points_html = render_list(data.get("watch_points", []), "暂无额外观察点。")
    timeline_html = render_timeline(data.get("timeline", []))
    sources_html = render_sources(data.get("sources", []))
    watch_html = render_watch_cards(data.get("watchlist", []))

    normalized_images = [escape(p.replace(os.sep, "/")) for p in source_images]
    body_images = normalized_images[1:] if len(normalized_images) > 1 else []

    right_image = (
        f'<div class="image-card"><img src="{body_images[0]}" alt="source image"></div>'
        if body_images else
        '<div class="card muted"><h2>现场画面</h2><p>当前没有抓到更多可用原图。</p></div>'
    )

    gallery_html = ""
    if len(body_images) > 1:
        gallery_items = "".join(
            f'<div class="gallery-item"><img src="{img}" alt="source image"></div>'
            for img in body_images[1:]
        )
        gallery_html = f"""
        <section class="card">
          <h2>更多图片</h2>
          <div class="gallery">{gallery_items}</div>
        </section>
        """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
body{{margin:0;background:#08111d;color:#e7edf6;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.8}}
.shell{{max-width:1280px;margin:0 auto;padding:20px 16px 56px}}
.hero{{display:grid;grid-template-columns:1.45fr .95fr;gap:18px}}
.hero-cover{{min-height:430px;border-radius:28px;overflow:hidden;background:#111827;box-shadow:0 18px 42px rgba(0,0,0,.25)}}
.hero-cover img{{width:100%;height:100%;object-fit:cover;display:block}}
.hero-panel{{background:linear-gradient(180deg,rgba(17,24,39,.95),rgba(15,23,42,.98));border:1px solid rgba(148,163,184,.14);border-radius:28px;padding:26px}}
.eyebrow{{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#cfe4ff;font-weight:700}}
.pill{{display:inline-block;margin-top:14px;padding:7px 12px;border-radius:999px;background:{accent};font-size:13px;font-weight:700;color:#fff}}
h1{{margin:14px 0 0;font-size:42px;line-height:1.18;letter-spacing:-.03em;color:#fff}}
.subtitle{{margin-top:12px;color:#cbd5e1;font-size:18px}}
.deck{{margin-top:18px;color:#e5edf7;font-size:18px}}
.grid2{{display:grid;grid-template-columns:1.15fr .85fr;gap:18px;margin-top:18px}}
.gridSplit{{display:grid;grid-template-columns:1.05fr .95fr;gap:18px;margin-top:18px}}
.card{{background:#0f172a;border:1px solid rgba(148,163,184,.14);border-radius:24px;padding:22px;box-shadow:0 10px 28px rgba(0,0,0,.14)}}
.card h2{{margin:0 0 14px;font-size:22px;color:#fff}}
.card p{{margin:0;color:#dbe7f5;font-size:18px}}
.muted p{{color:#b8c5d6}}
ul{{margin:0;padding-left:18px}}
li{{margin-bottom:12px;font-size:17px;color:#dbe7f5}}
.timeline{{display:grid;gap:14px}}
.timeline-item{{padding:14px 16px;border-radius:18px;background:rgba(2,6,23,.35);border:1px solid rgba(148,163,184,.12)}}
.timeline-time{{color:#7dd3fc;font-size:13px;font-weight:700;margin-bottom:8px}}
.timeline-event{{color:#e5edf7;font-size:16px}}
.image-card{{min-height:320px;border-radius:24px;overflow:hidden;background:#111827;border:1px solid rgba(148,163,184,.14)}}
.image-card img{{width:100%;height:100%;object-fit:cover;display:block}}
.outlook{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.outlook .item{{background:rgba(2,6,23,.35);border:1px solid rgba(148,163,184,.12);border-radius:18px;padding:16px}}
.outlook .item h3{{margin:0 0 10px;font-size:18px;color:#fff}}
.watch-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}
.watch-card{{background:rgba(2,6,23,.35);border:1px solid rgba(148,163,184,.12);border-radius:18px;padding:16px}}
.watch-top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}}
.watch-name{{font-size:18px;font-weight:700;color:#fff}}
.watch-reason{{color:#cbd5e1;font-size:15px}}
.badge{{border-radius:999px;padding:4px 10px;font-size:12px;font-weight:700}}
.badge.up{{background:#dcfce7;color:#166534}}
.badge.down{{background:#fee2e2;color:#991b1b}}
.badge.flat{{background:#e5e7eb;color:#374151}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}}
.gallery-item{{border-radius:20px;overflow:hidden;min-height:220px;background:#111827;border:1px solid rgba(148,163,184,.14)}}
.gallery-item img{{width:100%;height:100%;object-fit:cover;display:block}}
.sources{{display:grid;gap:12px}}
.source-item{{padding:14px 16px;border-radius:18px;background:rgba(2,6,23,.35);border:1px solid rgba(148,163,184,.12)}}
.source-name{{color:#fff;font-weight:700;margin-bottom:6px}}
.source-note{{color:#cbd5e1;font-size:15px}}
.risk{{background:linear-gradient(180deg,rgba(127,29,29,.28),rgba(69,10,10,.24));border:1px solid rgba(252,165,165,.2)}}
@media (max-width:980px){{.hero,.grid2,.gridSplit{{grid-template-columns:1fr}}.outlook{{grid-template-columns:1fr}}h1{{font-size:32px}}}}
</style>
</head>
<body>
<div class="shell">
  <section class="hero">
    <div class="hero-cover"><img src="cover.jpg" alt="cover"></div>
    <div class="hero-panel">
      <div class="eyebrow">GLOBAL INTELLIGENCE DESK</div>
      <div class="pill">{escape(meta["label"])}</div>
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="deck">{deck}</div>
    </div>
  </section>

  <section class="grid2">
    <div class="card">
      <h2>三点看懂这条资讯</h2>
      <ul>{key_points_html}</ul>
    </div>
    <div class="card">
      <h2>为什么现在重要</h2>
      <p>{why_now}</p>
    </div>
  </section>

  <section class="grid2">
    <div class="card">
      <h2>背景与来龙去脉</h2>
      <p>{background}</p>
    </div>
    <div class="card">
      <h2>时间线</h2>
      <div class="timeline">{timeline_html}</div>
    </div>
  </section>

  <section class="gridSplit">
    <div class="card">
      <h2>{section_1_title}</h2>
      <p>{section_1_body}</p>
    </div>
    {right_image}
  </section>

  <section class="grid2">
    <div class="card">
      <h2>{section_2_title}</h2>
      <p>{section_2_body}</p>
    </div>
    <div class="card">
      <h2>全球影响范围</h2>
      <p>{global_impact}</p>
    </div>
  </section>

  <section class="grid2">
    <div class="card">
      <h2>市场或产业反应</h2>
      <p>{market_or_industry_impact}</p>
    </div>
    <div class="card">
      <h2>关键观察点</h2>
      <ul>{watch_points_html}</ul>
    </div>
  </section>

  <section class="card">
    <h2>接下来 1 到 7 天怎么看</h2>
    <div class="outlook">
      <div class="item"><h3>1天</h3><div>{outlook_1d}</div></div>
      <div class="item"><h3>3天</h3><div>{outlook_3d}</div></div>
      <div class="item"><h3>7天</h3><div>{outlook_7d}</div></div>
    </div>
  </section>

  <section class="card">
    <h2>重点观察对象</h2>
    <div class="watch-grid">{watch_html}</div>
  </section>

  {gallery_html}

  <section class="grid2">
    <div class="card">
      <h2>资料与来源</h2>
      <div class="sources">{sources_html}</div>
    </div>
    <div class="card risk">
      <h2>风险与不确定性</h2>
      <p>{risk_warning}</p>
    </div>
  </section>
</div>
</body>
</html>"""


def save_html_report(html: str):
    with open(REPORT_HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def save_report_meta(data: dict):
    category = data.get("category", "breaking")
    meta = CATEGORY_META.get(category, CATEGORY_META["breaking"])
    payload = {
        "title": f'{meta["prefix"]}{data.get("title", "全球情报")}',
        "description": data.get("deck", "暂无摘要"),
        "url": REPORT_URL,
        "picurl": DEFAULT_PIC_URL,
    }
    with open(REPORT_META_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_report_meta() -> dict:
    with open(REPORT_META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def push_news_to_wecom(meta: dict):
    payload = {
        "msgtype": "news",
        "news": {"articles": [meta]},
    }

    last_error = None
    for _ in range(3):
        try:
            resp = requests.post(WECOM_WEBHOOK, json=payload, timeout=20)
            resp.raise_for_status()
            return
        except requests.exceptions.RequestException as e:
            last_error = e
            time.sleep(5)

    raise last_error


def generate_report() -> dict:
    news_item = choose_news()
    data = call_deepseek(news_item)

    generate_fallback_cover(data, COVER_FILE)

    article_url = SOURCE_ARTICLE_URL or news_item.get("link", "")
    source_images = fetch_article_images(article_url, max_images=4) if article_url else []
    choose_cover_image(source_images)

    html = build_html_report(data, source_images)
    save_html_report(html)
    save_report_meta(data)
    return news_item


def main():
    ensure_dir(IMAGES_DIR)
    news_item = generate_report()

    if PUSH_TO_WECOM:
        meta = load_report_meta()
        push_news_to_wecom(meta)
        mark_news_sent(news_item.get("link", ""))
    else:
        print("当前只生成报告，不推送企业微信。")


if __name__ == "__main__":
    main()
