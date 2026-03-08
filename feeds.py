import requests
import xml.etree.ElementTree as ET


FEED_SOURCES = [
    {
        "name": "Reuters World",
        "category_hint": "breaking",
        "url": "https://feeds.reuters.com/reuters/worldNews",
    },
    {
        "name": "Reuters Markets",
        "category_hint": "market",
        "url": "https://feeds.reuters.com/news/wealth",
    },
    {
        "name": "CoinDesk",
        "category_hint": "market",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    },
    {
        "name": "TechCrunch",
        "category_hint": "tech",
        "url": "https://techcrunch.com/feed/",
    },
]


def _get_text(elem, tag_names):
    for tag in tag_names:
        found = elem.find(tag)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def fetch_rss_feed(source: dict, timeout: int = 20) -> list[dict]:
    try:
        resp = requests.get(
            source["url"],
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"抓取 RSS 失败 {source['name']}: {e}")
        return []

    try:
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"解析 RSS 失败 {source['name']}: {e}")
        return []

    items = []
    for item in root.findall(".//item")[:15]:
        title = _get_text(item, ["title"])
        link = _get_text(item, ["link"])
        description = _get_text(item, ["description"])
        pub_date = _get_text(item, ["pubDate"])

        if not title or not link:
            continue

        items.append(
            {
                "source": source["name"],
                "category_hint": source["category_hint"],
                "title": title,
                "link": link,
                "description": description,
                "pub_date": pub_date,
            }
        )
    return items


def fetch_all_feeds() -> list[dict]:
    all_items = []
    for source in FEED_SOURCES:
        all_items.extend(fetch_rss_feed(source))
    return all_items
