import re


def normalize_title(title: str) -> str:
    title = title.lower().strip()
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]", " ", title)
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
        "war": 10,
        "strike": 9,
        "attack": 9,
        "sanctions": 8,
        "fed": 9,
        "inflation": 8,
        "rate": 7,
        "bitcoin": 7,
        "crypto": 6,
        "ai": 7,
        "nvidia": 6,
        "merger": 7,
        "earnings": 6,
        "oil": 8,
        "gold": 7,
        "china": 5,
        "russia": 6,
        "middle east": 8,
    }

    score = 0
    for kw, pts in keywords.items():
        if kw in text:
            score += pts

    if item.get("category_hint") == "breaking":
        score += 5
    if item.get("category_hint") == "market":
        score += 3

    return score


def pick_best_news(items: list[dict]) -> dict | None:
    if not items:
        return None

    ranked = sorted(items, key=score_news, reverse=True)
    return ranked[0]
