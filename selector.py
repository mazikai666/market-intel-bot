import re


def normalize_title(title: str) -> str:
    title = title.lower().strip()
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


def score_news(item: dict) -> int:
    title = (item.get("title") or "").lower()
    desc = (item.get("description") or "").lower()
    text = f"{title} {desc}"

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

    if item.get("category_hint") == "breaking":
        score += 4
    if item.get("category_hint") == "market":
        score += 3
    if item.get("category_hint") == "tech":
        score += 2

    return score


def pick_best_news(items: list[dict]) -> dict | None:
    if not items:
        return None

    ranked = sorted(items, key=score_news, reverse=True)
    return ranked[0]
