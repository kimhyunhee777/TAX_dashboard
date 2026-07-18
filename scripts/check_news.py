# -*- coding: utf-8 -*-
"""
세법 관련 뉴스 감지 폴러 (Google 뉴스 RSS, 키/과금 불필요).

news_topics.json에 등록된 검색어로 Google 뉴스 RSS를 조회해, 이전에 보지 못한 기사가
새로 나타나면 알림을 생성한다. 저작권 문제를 피하기 위해 기사 본문은 저장하지 않고
제목(헤드라인)과 출처, 링크만 사용한다 — 헤드라인 자체가 이미 짧은 사실 전달 문구라
"쉬운 설명" 대용으로 충분하고, 전문은 링크를 눌러 원문에서 확인하도록 한다.

법령 개정/판례 추적기와 달리, 뉴스는 "지금 관련 업종을 눌렀을 때 바로 보이는 최신 기사
피드"가 목적이라 첫 실행부터 현재 검색되는 기사를 그대로 알림으로 채운다 (법령·판례는
기존 역사 전체를 알림으로 쏟아내면 노이즈가 되지만, 뉴스는 최근 N건만 보여주는 것 자체가
이 기능의 목적이라 다르게 취급).
"""
import hashlib
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests

from common import KST, load_json, save_json, prune_old

RSS_URL = "https://news.google.com/rss/search"
ROOT = os.path.join(os.path.dirname(__file__), "..")
TOPICS_PATH = os.path.join(ROOT, "news_topics.json")
STATE_PATH = os.path.join(ROOT, "data", "news_state.json")
ALERTS_PATH = os.path.join(ROOT, "data", "news_alerts.json")
RETENTION_DAYS = 60

# 세무 실무와 무관한 저품질/반복성 결과를 걸러낸다 (국세청 자료실 게시물, 동영상 안내 등).
EXCLUDE_KEYWORDS = ["동영상자료실", "Web-TV", "포토뉴스", "카드뉴스", "[포토]"]


def item_id(link, title):
    return hashlib.sha256((link or title).encode("utf-8")).hexdigest()[:16]


def search_news(query, display=15):
    resp = requests.get(RSS_URL, params={"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}, timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    results = []
    for item in root.findall(".//item")[:display]:
        raw_title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source = (item.findtext("source") or "").strip()
        if any(k in raw_title for k in EXCLUDE_KEYWORDS):
            continue
        # Google 뉴스 RSS는 "기사 제목 - 출처명" 형태로 제목을 주는데, 출처는 따로 필드로도
        # 오므로 카드에서 중복 표시되지 않도록 제목에서 그 접미사를 떼어낸다.
        title = raw_title
        suffix = f" - {source}"
        if source and title.endswith(suffix):
            title = title[: -len(suffix)]
        try:
            published_at = parsedate_to_datetime(pub_date).astimezone(KST).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            published_at = ""
        results.append({
            "itemId": item_id(link, raw_title),
            "title": title,
            "link": link,
            "source": source,
            "publishedAt": published_at,
        })
    return results


def make_alert(topic, tid, r, now):
    return {
        "id": f"{tid}-{r['itemId']}",
        "type": "news",
        "topicId": tid,
        "label": r["title"],  # 기사 제목을 카드 제목으로 사용 (카드마다 다르게 보이도록)
        "topic": topic.get("label", topic["query"]),  # 어떤 검색 주제로 걸렸는지는 상세에서만 보여줌
        "detectedAt": now,
        "plainSummary": r["title"],
        "source": r["source"],
        "publishedAt": r["publishedAt"],
        "articleUrl": r["link"],
        "tags": topic.get("tags", []),
    }


def main():
    topics = load_json(TOPICS_PATH, [])
    state = load_json(STATE_PATH, {})
    alerts = load_json(ALERTS_PATH, [])
    now = datetime.now(KST).isoformat(timespec="seconds")
    alerted_this_run = set()  # 같은 실행에서 여러 주제에 동시에 걸린 기사 중복 알림 방지

    for topic in topics:
        tid = topic["id"]
        try:
            results = search_news(topic["query"])
        except (requests.RequestException, ET.ParseError) as e:
            print(f"[skip] {tid}: {e}", file=sys.stderr)
            continue

        seen = set(state.get(tid, {}).get("seenIds", []))
        new_results = [r for r in results if r["itemId"] not in seen]

        for r in new_results:
            if r["itemId"] in alerted_this_run:
                continue
            alerted_this_run.add(r["itemId"])
            alerts.append(make_alert(topic, tid, r, now))
            print(f"[news] {tid}: {r['title']}")

        state[tid] = {"seenIds": list(seen | {r["itemId"] for r in results}), "lastCheckedAt": now}

    alerts = prune_old(alerts, RETENTION_DAYS)
    save_json(STATE_PATH, state)
    save_json(ALERTS_PATH, alerts)


if __name__ == "__main__":
    main()
