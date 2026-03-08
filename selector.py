import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def normalize_title(title: str) -> str:
    title = (title or "").lower().strip()
    title = re.sub(r"[^a-z0-9\s]", " ", title)
    title = re.sub(r"\s+", " ", title)
    return title


def deduplicate_news(items: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for item in items:
        key = normalize_title(item.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)

    return result


def parse_pub_date(pub_date: str) -> datetime | None:
    if not pub_date:
        return None
    try:
        dt = parsedate_to_datetime(pub_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def recency_score(pub_date: str) -> int:
    dt = parse_pub_date(pub_date)
    if not dt:
        return 0

    now = datetime.now(timezone.utc)
    hours = (now - dt).total_seconds() / 3600

    if hours <= 6:
        return 20
    if hours <= 12:
        return 16
    if hours <= 24:
        return 12
    if hours <= 48:
        return 8
    if hours <= 72:
        return 4
    return 0


def keyword_score(text: str) -> int:
    keywords = {
        "war": 12,
        "attack": 11,
        "strike": 10,
        "missile": 10,
        "military": 9,
        "sanctions": 9,
        "ceasefire": 8,
        "fed": 10,
        "inflation": 9,
        "interest rate": 9,
        "tariff": 8,
        "oil": 9,
        "gold": 8,
        "bitcoin": 8,
        "crypto": 7,
        "ai": 8,
        "artificial intelligence": 8,
        "chip": 7,
        "nvidia": 7,
        "openai": 7,
        "merger": 8,
        "acquisition": 8,
        "earnings": 7,
        "bank": 7,
        "recession": 9,
        "china": 6,
        "russia": 7,
        "ukraine": 8,
        "middle east": 9,
        "iran": 8,
        "israel": 8,
    }

    score = 0
    for kw, pts in keywords.items():
        if kw in text:
            score += pts
    return score


def category_bonus(category_hint: str) -> int:
    if category_hint == "breaking":
        return 5
    if category_hint == "market":
        return 4
    if category_hint == "tech":
        return 3
    if category_hint == "business":
        return 2
    return 0


def title_bonus(title: str) -> int:
    t = (title or "").lower()
    bonus_words = [
        "live",
        "breaking",
        "surges",
        "falls",
        "jumps",
        "plunges",
        "beats",
        "misses",
        "launches",
        "deal",
    ]
    return sum(2 for w in bonus_words if w in t)


def score_news(item: dict) -> int:
    title = (item.get("title") or "").lower()
    desc = (item.get("description") or "").lower()
    text = f"{title} {desc}"

    score = 0
    score += keyword_score(text)
    score += category_bonus(item.get("category_hint", ""))
    score += title_bonus(title)
    score += recency_score(item.get("pub_date", ""))

    return score


def sort_news(items: list[dict]) -> list[dict]:
    return sorted(items, key=score_news, reverse=True)


def pick_best_news(items: list[dict]) -> dict | None:
    if not items:
        return None

    ranked = sort_news(items)
    return ranked[0]
