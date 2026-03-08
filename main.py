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
    "breaking": {"label": "全球突发", "prefix": "【全球突发】", "theme": "Breaking Desk", "color": "#b91c1c"},
    "market": {"label": "市场金融", "prefix": "【市场快讯】", "theme": "Market Pulse", "color": "#1d4ed8"},
    "tech": {"label": "科技突破", "prefix": "【科技情报】", "theme": "Tech Watch", "color": "#7c3aed"},
    "business": {"label": "公司商业", "prefix": "【商业动态】", "theme": "Business Brief", "color": "#0f766e"},
}


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


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

    return json.loads(content[start:end + 1])


def _safe_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def choose_news() -> dict:
    if TEST_NEWS:
        return {
            "title": TEST_NEWS[:120],
            "description": TEST_NEWS,
            "link": SOURCE_ARTICLE_URL,
            "source": "Manual Input",
            "pub_date": "",
        }

    items = fetch_all_feeds()
    items = deduplicate_news(items)
    items = filter_unsent_news(items)

    picked = pick_best_news(items)
    if not picked:
        raise ValueError("没有新的可推送新闻了，请等 RSS 更新或扩充新闻源。")

    print("选中的新新闻：")
    print(json.dumps(picked, ensure_ascii=False, indent=2))
    return picked


def call_deepseek(news_item: dict) -> dict:
    if not DEEPSEEK_API_KEY:
        raise ValueError("没有找到 DEEPSEEK_API_KEY，请先在 GitHub Secrets 里配置。")

    news_text = f"""标题：{news_item.get('title', '')}
摘要：{news_item.get('description', '')}
来源：{news_item.get('source', '')}
发布时间：{news_item.get('pub_date', '')}
链接：{news_item.get('link', '')}
"""

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
你是一个全球资讯编辑台总编。
请先判断下面这条新闻属于哪一类，再按对应媒体风格生成一篇“全球情报专题页”素材。

可选分类只有四种：
- breaking：全球突发
- market：市场金融
- tech：科技突破
- business：公司商业

要求：
1. 先分类，再写作
2. 不要千篇一律
3. 页面内容要丰富，包含背景、时间线、全球影响、关键观察点、来源信息
4. 语言专业、克制、有信息密度
5. 标题和导语要更像成熟媒体，而不是模板句
6. 严格输出 JSON

新闻：
{news_text}

请输出：
{{
  "category": "breaking 或 market 或 tech 或 business",
  "title": "标题，18字以内",
  "subtitle": "一句副标题，点出主线",
  "deck": "导语，2到3句",
  "key_points": ["重点1", "重点2", "重点3"],
  "background": "背景与来龙去脉",
  "why_now": "为什么现在值得关注",
  "timeline": [
    {{"time": "节点1", "event": "事件1"}},
    {{"time": "节点2", "event": "事件2"}},
    {{"time": "节点3", "event": "事件3"}}
  ],
  "global_impact": "全球影响范围",
  "section_1_title": "第一部分标题",
  "section_1_body": "第一部分正文",
  "section_2_title": "第二部分标题",
  "section_2_body": "第二部分正文",
  "market_or_industry_impact": "市场或产业反应",
  "watch_points": ["观察点1", "观察点2", "观察点3"],
  "outlook_1d": "未来1天",
  "outlook_3d": "未来3天",
  "outlook_7d": "未来7天",
  "watchlist": [
    {{"name": "对象1", "view": "偏多/偏空/关注/中性", "reason": "一句原因"}},
    {{"name": "对象2", "view": "偏多/偏空/关注/中性", "reason": "一句原因"}},
    {{"name": "对象3", "view": "偏多/偏空/关注/中性", "reason": "一句原因"}}
  ],
  "risk_warning": "一句风险提示",
  "sources": [
    {{"name": "来源1", "note": "为什么值得看"}},
    {{"name": "来源2", "note": "为什么值得看"}}
  ],
  "cover": {{
    "theme": "封面主题",
    "strapline": "封面小字，12字以内",
    "tags": ["标签1", "标签2", "标签3"]
  }}
}}
"""

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个严格输出 JSON 的全球资讯总编。只返回 JSON 对象本身。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.75,
        "response_format": {"type": "json_object"},
    }

    resp = requests.post(url, headers=headers, json=data, timeout=90)
    resp.raise_for_status()
    result = resp.json()
    parsed = extract_json_from_text(result["choices"][0]["message"]["content"])

    category = parsed.get("category", "breaking")
    if category not in CATEGORY_META:
        parsed["category"] = "breaking"
    return parsed


def generate_cover_image(data: dict, filename: str = COVER_FILE) -> str:
    category = data.get("category", "breaking")
    meta = CATEGORY_META.get(category, CATEGORY_META["breaking"])

    title = data.get("title", "全球情报")
    subtitle = data.get("subtitle", "")
    cover = data.get("cover", {})
    strapline = cover.get("strapline", meta["theme"])
    theme = cover.get("theme", meta["label"])
    tags = cover.get("tags", [])[:3]
    accent = meta["color"]

    width, height = 1600, 900
    img = Image.new("RGB", (width, height), "#07111f")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, height], fill="#07111f")
    draw.ellipse([980, -120, 1700, 560], fill=accent)
    draw.ellipse([-250, 470, 520, 1200], fill="#0f2348")
    draw.rounded_rectangle([65, 65, width - 65, height - 65], radius=38, outline="#27406e", width=2)

    draw.rounded_rectangle([90, 110, 310, 142], radius=12, fill=accent)
    draw.rounded_rectangle([326, 110, 560, 142], radius=12, fill="#1f2937")

    title_font = _safe_font(74, bold=True)
    subtitle_font = _safe_font(30, bold=False)
    strap_font = _safe_font(26, bold=True)
    theme_font = _safe_font(28, bold=True)
    tag_font = _safe_font(24, bold=True)

    draw.text((100, 180), strapline, font=strap_font, fill="#cfe4ff")
    draw.text((100, 228), theme, font=theme_font, fill="#ffffff")

    wrapped_title = textwrap.wrap(title, width=12)
    y = 328
    for line in wrapped_title[:3]:
        draw.text((100, y), line, font=title_font, fill="#ffffff")
        y += 96

    wrapped_sub = textwrap.wrap(subtitle, width=34)
    y += 10
    for line in wrapped_sub[:2]:
        draw.text((100, y), line, font=subtitle_font, fill="#d1d5db")
        y += 44

    img.save(filename, format="JPEG", quality=92)
    return filename


def normalize_img_url(src: str, base_url: str) -> str:
    if not src:
        return ""
    return urljoin(base_url, src)


def is_good_image_url(url: str) -> bool:
    lowered = url.lower()
    bad_keywords = ["logo", "icon", "avatar", "ads", "sprite", "badge", "emoji"]
    return not any(k in lowered for k in bad_keywords)


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

        img = img.convert("RGB")
        img.save(out_path, format="JPEG", quality=90)
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

    for selector in [
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
        ('meta[property="twitter:image"]', "content"),
    ]:
        tag = soup.select_one(selector[0])
        if tag and tag.get(selector[1]):
            candidates.append(normalize_img_url(tag.get(selector[1]), article_url))

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
        out_path = os.path.join(IMAGES_DIR, f"source_{len(saved) + 1}.jpg")
        if download_image(img_url, out_path):
            saved.append(out_path)

    return saved


def choose_cover_image(source_images: list[str], generated_cover: str = COVER_FILE) -> str:
    if source_images:
        first_img = source_images[0]
        try:
            with Image.open(first_img) as img:
                img = img.convert("RGB")
                img.save(COVER_FILE, format="JPEG", quality=92)
            return COVER_FILE
        except Exception:
            pass
    return generated_cover


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
    key_points_html = "".join(f"<li>{escape(i)}</li>" for i in data.get("key_points", [])[:3])

    timeline = data.get("timeline", [])
    watch_points = data.get("watch_points", [])
    sources = data.get("sources", [])
    watchlist = data.get("watchlist", [])

    timeline_html = "".join(
        f"<div class='timeline-item'><div class='timeline-time'>{escape(i.get('time','时间待定'))}</div><div class='timeline-event'>{escape(i.get('event','事件待补充'))}</div></div>"
        for i in timeline[:5]
    ) or "<div class='timeline-item'><div class='timeline-time'>Now</div><div class='timeline-event'>当前暂无时间线细节。</div></div>"

    watch_points_html = "".join(f"<li>{escape(p)}</li>" for p in watch_points[:5]) or "<li>暂无补充观察点。</li>"

    sources_html = "".join(
        f"<div class='source-item'><div class='source-name'>{escape(s.get('name','来源'))}</div><div class='source-note'>{escape(s.get('note',''))}</div></div>"
        for s in sources[:5]
    ) or "<div class='source-item'><div class='source-name'>AI Desk</div><div class='source-note'>当前未提供外部来源说明。</div></div>"

    watch_html = ""
    for item in watchlist:
        name = escape(item.get("name", "未知对象"))
        view = escape(item.get("view", "中性"))
        reason = escape(item.get("reason", ""))
        cls = "up" if view in ["偏多", "利多"] else ("down" if view in ["偏空", "利空"] else "flat")
        watch_html += f"""
        <div class="asset-card">
          <div class="asset-top">
            <div class="asset-name">{name}</div>
            <div class="badge {cls}">{view}</div>
          </div>
          <div class="asset-reason">{reason}</div>
        </div>
        """

    normalized_images = [escape(p.replace(os.sep, "/")) for p in source_images]
    body_images = normalized_images[1:] if len(normalized_images) > 1 else []

    if len(body_images) >= 1:
        image_block_1 = f'<div class="inline-visual"><img src="{body_images[0]}" alt="source image 1"></div>'
    else:
        image_block_1 = '<div class="card story"><h2>现场线索</h2><p>当前未抓取到更多可用原图。</p></div>'

    image_block_2 = '<div class="card story"><h2>进一步观察</h2><p>系统已优先使用原文头图作为封面，其余原图会按价值择优展示。</p></div>'

    gallery_section = ""
    gallery_images = body_images[1:] if len(body_images) > 1 else []
    if gallery_images:
        gallery_items = "".join(
            f'<div class="gallery-item"><img src="{rel}" alt="source image"></div>'
            for rel in gallery_images
        )
        gallery_section = f"""
        <section class="card">
          <h2>更多图片</h2>
          <div class="gallery">{gallery_items}</div>
        </section>
        """

    label = {
        "breaking": "关键地区与对象",
        "market": "重点资产与方向",
        "tech": "值得跟进的技术与公司",
        "business": "值得盯住的公司与行业",
    }.get(category, "重点观察对象")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title}</title>
<style>
body{{margin:0;background:#07111f;color:#e5edf7;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.8}}
.shell{{max-width:1280px;margin:0 auto;padding:20px 16px 56px}}
.hero{{display:grid;grid-template-columns:1.5fr .9fr;gap:18px;align-items:stretch}}
.hero-cover{{min-height:420px;border-radius:28px;overflow:hidden;box-shadow:0 18px 42px rgba(0,0,0,.24);background:#0f172a}}
.hero-cover img{{width:100%;height:100%;object-fit:cover;display:block}}
.hero-panel{{background:linear-gradient(180deg,rgba(17,24,39,.95),rgba(15,23,42,.98));border:1px solid rgba(148,163,184,.15);border-radius:28px;padding:26px;box-shadow:0 18px 42px rgba(0,0,0,.18)}}
.eyebrow{{color:#cfe4ff;font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}}
.category-pill{{display:inline-block;margin-top:14px;padding:7px 12px;border-radius:999px;background:{accent};color:#fff;font-size:13px;font-weight:700}}
h1{{margin:14px 0 0;font-size:40px;line-height:1.2;letter-spacing:-.03em;color:#fff}}
.subtitle{{margin-top:12px;color:#cbd5e1;font-size:18px}}
.deck{{margin-top:18px;color:#e2e8f0;font-size:18px}}
.tag-row{{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}}
.tag{{padding:7px 12px;border-radius:999px;background:rgba(59,130,246,.16);border:1px solid rgba(125,211,252,.18);color:#dbeafe;font-size:13px;font-weight:600}}
.split,.content-grid{{display:grid;grid-template-columns:1.3fr .9fr;gap:18px;margin-top:18px}}
.content-grid{{grid-template-columns:1.15fr .85fr}}
.story-grid{{display:grid;grid-template-columns:1.12fr .88fr;gap:18px;margin-top:18px}}
.card{{background:#0f172a;border:1px solid rgba(148,163,184,.14);border-radius:24px;padding:22px;box-shadow:0 10px 28px rgba(0,0,0,.15)}}
.card h2{{margin:0 0 14px;font-size:22px;color:#fff}}
.summary-list,.watch-list{{margin:0;padding-left:18px}}
.summary-list li,.watch-list li{{margin-bottom:12px;font-size:17px;color:#dbe7f5}}
.meta-block{{display:grid;gap:14px}}
.meta-item{{padding:16px;border-radius:18px;background:rgba(2,6,23,.35);border:1px solid rgba(148,163,184,.12)}}
.meta-label{{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#7dd3fc;margin-bottom:8px;font-weight:700}}
.meta-value{{color:#e5edf7;font-size:16px}}
.story p{{margin:0 0 16px;font-size:18px;color:#dbe7f5}}
.inline-visual{{border-radius:22px;overflow:hidden;min-height:300px;background:#111827;border:1px solid rgba(148,163,184,.14)}}
.inline-visual img{{width:100%;height:100%;object-fit:cover;display:block}}
.timeline{{display:grid;gap:14px}}
.timeline-item{{padding:14px 16px;border-radius:18px;background:rgba(2,6,23,.35);border:1px solid rgba(148,163,184,.12)}}
.timeline-time{{color:#7dd3fc;font-size:13px;font-weight:700;margin-bottom:8px}}
.timeline-event{{color:#e5edf7;font-size:16px}}
.outlook-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:14px}}
.mini{{background:rgba(2,6,23,.35);border:1px solid rgba(148,163,184,.12);border-radius:18px;padding:16px}}
.mini h3{{margin:0 0 10px;color:#fff;font-size:18px}}
.watch-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}
.asset-card{{background:rgba(2,6,23,.35);border:1px solid rgba(148,163,184,.12);border-radius:18px;padding:16px}}
.asset-top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}}
.asset-name{{font-size:18px;font-weight:700;color:#fff}}
.badge{{border-radius:999px;padding:4px 10px;font-size:12px;font-weight:700}}
.badge.up{{background:#dcfce7;color:#166534}}
.badge.down{{background:#fee2e2;color:#991b1b}}
.badge.flat{{background:#e5e7eb;color:#374151}}
.asset-reason{{color:#cbd5e1;font-size:15px}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:14px}}
.gallery-item{{border-radius:20px;overflow:hidden;min-height:220px;background:#111827;border:1px solid rgba(148,163,184,.14)}}
.gallery-item img{{width:100%;height:100%;object-fit:cover;display:block}}
.source-grid{{display:grid;gap:12px}}
.source-item{{padding:14px 16px;border-radius:18px;background:rgba(2,6,23,.35);border:1px solid rgba(148,163,184,.12)}}
.source-name{{color:#fff;font-weight:700;margin-bottom:6px}}
.source-note{{color:#cbd5e1;font-size:15px}}
.risk{{background:linear-gradient(180deg,rgba(127,29,29,.28),rgba(69,10,10,.24));border:1px solid rgba(252,165,165,.2)}}
@media (max-width:980px){{.hero,.split,.content-grid,.story-grid{{grid-template-columns:1fr}}.outlook-grid{{grid-template-columns:1fr}}h1{{font-size:32px}}}}
</style>
</head>
<body>
<div class="shell">
<section class="hero">
<div class="hero-cover"><img src="cover.jpg" alt="cover"></div>
<div class="hero-panel">
<div class="eyebrow">GLOBAL INTELLIGENCE DESK</div>
<div class="category-pill">{escape(meta["label"])}</div>
<h1>{title}</h1>
<div class="subtitle">{subtitle}</div>
<div class="deck">{deck}</div>
<div class="tag-row"><div class="tag">全球新闻</div><div class="tag">专题页</div><div class="tag">重点观察</div></div>
</div>
</section>

<section class="split">
<div class="card"><h2>三点看懂这条资讯</h2><ul class="summary-list">{key_points_html}</ul></div>
<div class="card"><h2>为什么现在重要</h2><div class="meta-block"><div class="meta-item"><div class="meta-label">Now in focus</div><div class="meta-value">{why_now}</div></div><div class="meta-item"><div class="meta-label">Category</div><div class="meta-value">{escape(meta["label"])}</div></div></div></div>
</section>

<section class="content-grid">
<div class="card story"><h2>背景与来龙去脉</h2><p>{background}</p></div>
<div class="card"><h2>时间线</h2><div class="timeline">{timeline_html}</div></div>
</section>

<section class="story-grid">
<div class="card story"><h2>{section_1_title}</h2><p>{section_1_body}</p></div>
{image_block_1}
</section>

<section class="story-grid">
<div class="card story"><h2>{section_2_title}</h2><p>{section_2_body}</p></div>
{image_block_2}
</section>

<section class="content-grid">
<div class="card story"><h2>全球影响范围</h2><p>{global_impact}</p></div>
<div class="card story"><h2>市场或产业反应</h2><p>{market_or_industry_impact}</p></div>
</section>

<section class="content-grid">
<div class="card"><h2>关键观察点</h2><ul class="watch-list">{watch_points_html}</ul></div>
<div class="card"><h2>接下来 1 到 7 天怎么看</h2><div class="outlook-grid"><div class="mini"><h3>1天</h3><div>{outlook_1d}</div></div><div class="mini"><h3>3天</h3><div>{outlook_3d}</div></div><div class="mini"><h3>7天</h3><div>{outlook_7d}</div></div></div></div>
</section>

<section class="card"><h2>{label}</h2><div class="watch-grid">{watch_html}</div></section>
{gallery_section}

<section class="content-grid">
<div class="card"><h2>资料与来源</h2><div class="source-grid">{sources_html}</div></div>
<section class="card risk"><h2>还要留意什么变量</h2><div>{risk_warning}</div></section>
</section>
</div>
</body>
</html>"""


def save_html_report(html: str, filename: str = REPORT_HTML_FILE) -> str:
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    return filename


def save_report_meta(data: dict, filename: str = REPORT_META_FILE) -> str:
    category = data.get("category", "breaking")
    meta = CATEGORY_META.get(category, CATEGORY_META["breaking"])
    saved = {
        "title": f'{meta["prefix"]}{data.get("title", "全球情报")}',
        "description": data.get("deck", "暂无摘要"),
        "url": REPORT_URL,
        "picurl": DEFAULT_PIC_URL,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)
    return filename


def load_report_meta(filename: str = REPORT_META_FILE) -> dict:
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def push_news_to_wecom(title: str, description: str, url: str, picurl: str, max_retries: int = 3) -> str:
    payload = {
        "msgtype": "news",
        "news": {"articles": [{"title": title, "description": description, "url": url, "picurl": picurl}]},
    }

    last_error = None
    for i in range(max_retries):
        try:
            resp = requests.post(WECOM_WEBHOOK, json=payload, timeout=20)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            last_error = e
            time.sleep(5)

    raise last_error


def generate_report() -> dict:
    news_item = choose_news()
    data = call_deepseek(news_item)

    generate_cover_image(data, COVER_FILE)
    article_url = SOURCE_ARTICLE_URL or news_item.get("link", "")
    source_images = fetch_article_images(article_url, max_images=4) if article_url else []
    choose_cover_image(source_images, COVER_FILE)

    html = build_html_report(data, source_images)
    save_html_report(html)
    save_report_meta(data)
    return news_item


def push_existing_report() -> str:
    meta = load_report_meta()
    return push_news_to_wecom(
        title=meta["title"],
        description=meta["description"],
        url=meta["url"],
        picurl=meta["picurl"],
    )


def main():
    ensure_dir(IMAGES_DIR)
    news_item = generate_report()

    if PUSH_TO_WECOM:
        push_existing_report()
        mark_news_sent(news_item.get("link", ""))
    else:
        print("当前只生成报告，不推送企业微信。")


if __name__ == "__main__":
    main()
