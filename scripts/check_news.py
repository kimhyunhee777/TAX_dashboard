# -*- coding: utf-8 -*-
"""
세법 관련 뉴스 감지 폴러 (Google 뉴스 RSS, 키/과금 불필요).

news_topics.json에 등록된 검색어로 Google 뉴스 RSS를 조회해, 이전에 보지 못한 기사가
새로 나타나면 알림을 생성한다. 저작권 문제를 피하기 위해 기사 본문은 저장하지 않고
제목(헤드라인)과 출처, 링크만 사용한다 — 헤드라인 자체가 이미 짧은 사실 전달 문구라
"쉬운 설명" 대용으로 충분하고, 전문은 링크를 눌러 원문에서 확인하도록 한다.
"""
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import requests

RSS_URL = "https://news.google.com/rss/search"
ROOT = os.path.join(os.path.dirname(__file__), "..")
TOPICS_PATH = os.path.join(ROOT, "news_topics.json")
STATE_PATH = os.path.join(ROOT, "data", "news_state.json")
ALERTS_PATH = os.path.join(ROOT, "data", "news_alerts.json")
KST = timezone(timedelta(hours=9))


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def item_id(link, title):
    return hashlib.sha256((link or title).encode("utf-8")).hexdigest()[:16]


def search_news(query, display=15):
    resp = requests.get(RSS_URL, params={"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}, timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    results = []
    for item in root.findall(".//item")[:display]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source = (item.findtext("source") or "").strip()
        try:
            published_at = parsedate_to_datetime(pub_date).astimezone(KST).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            published_at = ""
        results.append({
            "itemId": item_id(link, title),
            "title": title,
            "link": link,
            "source": source,
            "publishedAt": published_at,
        })
    return results


def main():
    topics = load_json(TOPICS_PATH, [])
    state = load_json(STATE_PATH, {})
    alerts = load_json(ALERTS_PATH, [])
    now = datetime.now(KST).isoformat(timespec="seconds")

    for topic in topics:
        tid = topic["id"]
        try:
            results = search_news(topic["query"])
        except (requests.RequestException, ET.ParseError) as e:
            print(f"[skip] {tid}: {e}", file=sys.stderr)
            continue

        if tid not in state:
            # 첫 실행: 현재 검색되는 기사는 베이스라인으로만 저장, 알림 없음
            state[tid] = {"seenIds": [r["itemId"] for r in results], "lastCheckedAt": now}
            print(f"[baseline] {tid}: {len(results)}건")
            continue

        seen = set(state[tid].get("seenIds", []))
        new_results = [r for r in results if r["itemId"] not in seen]

        for r in new_results:
            alerts.append({
                "id": f"{tid}-{r['itemId']}",
                "type": "news",
                "topicId": tid,
                "label": topic.get("label", topic["query"]),
                "detectedAt": now,
                "plainSummary": r["title"],
                "source": r["source"],
                "publishedAt": r["publishedAt"],
                "articleUrl": r["link"],
                "tags": topic.get("tags", []),
            })
            print(f"[new-news] {tid}: {r['title']}")

        state[tid] = {"seenIds": list(seen | {r["itemId"] for r in results}), "lastCheckedAt": now}

    save_json(STATE_PATH, state)
    save_json(ALERTS_PATH, alerts)


if __name__ == "__main__":
    main()
