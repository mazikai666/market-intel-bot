import json
import os
from typing import List, Dict

STATE_FILE = "state.json"


def load_state() -> Dict:
    if not os.path.exists(STATE_FILE):
        return {"sent_links": []}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "sent_links" not in data or not isinstance(data["sent_links"], list):
            return {"sent_links": []}
        return data
    except Exception:
        return {"sent_links": []}


def save_state(state: Dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def filter_unsent_news(items: List[Dict]) -> List[Dict]:
    state = load_state()
    sent_links = set(state.get("sent_links", []))
    return [item for item in items if item.get("link") and item.get("link") not in sent_links]


def mark_news_sent(link: str) -> None:
    if not link:
        return

    state = load_state()
    sent_links = state.get("sent_links", [])

    if link not in sent_links:
        sent_links.append(link)

    # 只保留最近 200 条，避免文件越来越大
    state["sent_links"] = sent_links[-200:]
    save_state(state)
