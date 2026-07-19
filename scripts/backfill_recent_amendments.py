# -*- coding: utf-8 -*-
"""
최근 개정 이력 백필(1회성) 스크립트 — law.go.kr 연혁법령(eflaw) API로 실제 "변경 전" 원문을 가져온다.

check_amendments.py는 "우리가 베이스라인을 잡은 이후 실제로 바뀐 것"만 알림으로 만들기 때문에,
방금 막 추적을 시작한 조문은 그 전에 이미 일어난 개정을 diff로 잡아낼 방법이 없다.

law.go.kr은 법령의 모든 과거 공식본(연혁법령)을 법령일련번호(MST)로 조회할 수 있게 해준다.
이 스크립트는 각 법령의 "현재 시행 중인 버전"과 "그 바로 이전 버전"의 MST를 찾아, 두 버전에서
같은 조문을 각각 가져와 실제로 비교한다 — 즉 진짜 변경 전/후 원문 diff를 만들 수 있다
(초기 버전은 이 데이터가 없어서 "원문 이력 없음"이라고만 표시했었는데, 이제는 필요 없다).
"""
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from lawtext import BASE_URL, extract_article_text  # noqa: E402

from common import KST, load_json, save_json, strip_amendment_tags_lines
from check_amendments import build_plain_summary

ROOT = os.path.join(os.path.dirname(__file__), "..")
PROVISIONS_PATH = os.path.join(ROOT, "provisions.json")
STATE_PATH = os.path.join(ROOT, "data", "state.json")
ALERTS_PATH = os.path.join(ROOT, "data", "alerts.json")


def list_settled_versions(law_name, oc):
    """현행/연혁(이미 시행된) 버전만 시행일자 내림차순으로 정렬해 돌려준다 (시행예정 미래 버전 제외)."""
    resp = requests.get(
        f"{BASE_URL}/lawSearch.do",
        params={"OC": oc, "target": "eflaw", "type": "XML", "query": law_name, "display": 100},
        timeout=20,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    entries = []
    for law_el in root.findall("law"):
        name = (law_el.findtext("법령명한글") or "").strip()
        status = (law_el.findtext("현행연혁코드") or "").strip()
        if name != law_name or status not in ("현행", "연혁"):
            continue
        entries.append({
            "mst": law_el.findtext("법령일련번호"),
            "efdate": law_el.findtext("시행일자") or "",
        })
    entries.sort(key=lambda e: e["efdate"], reverse=True)
    return entries


def fetch_article_at_mst(mst, jo, branch, oc):
    resp = requests.get(
        f"{BASE_URL}/lawService.do",
        params={"OC": oc, "target": "law", "MST": mst, "type": "XML"},
        timeout=20,
    )
    resp.raise_for_status()
    return extract_article_text(resp.content, jo, branch)


def main():
    oc = os.environ.get("LAW_API_OC")
    if not oc:
        print("LAW_API_OC 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)

    provisions = load_json(PROVISIONS_PATH, [])
    state = load_json(STATE_PATH, {})
    alerts = load_json(ALERTS_PATH, [])
    now = datetime.now(KST).isoformat(timespec="seconds")

    prev_mst_cache = {}  # law_name -> 이전 버전 MST (같은 법령 여러 조문에 재사용)
    added = 0

    for prov in provisions:
        pid, law, jo, branch = prov["id"], prov["law"], prov["jo"], prov.get("branch") or None
        cached = state.get(pid)
        if not cached:
            print(f"[skip] {pid}: state.json에 캐시된 원문이 없습니다 (check_amendments.py를 먼저 실행하세요).", file=sys.stderr)
            continue

        if law not in prev_mst_cache:
            try:
                versions = list_settled_versions(law, oc)
            except (requests.RequestException, ET.ParseError) as e:
                print(f"[skip-law] {law}: {e}", file=sys.stderr)
                prev_mst_cache[law] = None
                versions = []
            prev_mst_cache[law] = versions[1]["mst"] if len(versions) >= 2 else None

        prev_mst = prev_mst_cache[law]
        if not prev_mst:
            continue

        try:
            prev_title, prev_lines = fetch_article_at_mst(prev_mst, jo, branch, oc)
        except (requests.RequestException, ET.ParseError) as e:
            print(f"[skip] {pid}: 이전 버전 조회 실패 ({e})", file=sys.stderr)
            continue

        current_lines = cached.get("lines", [])
        if prev_title is None:
            continue  # 이전 공식본에 이 조문이 없었음(신설 직후 등)
        if strip_amendment_tags_lines(prev_lines) == strip_amendment_tags_lines(current_lines):
            continue  # <개정 ...> 이력 꼬리표만 다르고 실제 조문 내용은 그 사이 안 바뀜

        alert_id = f"{pid}-recent-{prev_mst}"
        if any(a["id"] == alert_id for a in alerts):
            continue

        jo_display = f"{jo}의{branch}" if branch else jo
        title = cached.get("title", prov.get("label", ""))
        summary = build_plain_summary(law, jo_display, title, prev_lines, current_lines)

        alerts.append({
            "id": alert_id,
            "type": "amendment",
            "provisionId": pid,
            "label": prov.get("label", title),
            "law": law,
            "jo": jo,
            "branch": branch or "",
            "detectedAt": now,
            "title": title,
            "originalText": current_lines,
            "previousText": prev_lines,
            "plainSummary": summary,
            "tags": prov.get("tags", []),
        })
        added += 1
        print(f"[backfill] {pid}: {summary}")

    save_json(ALERTS_PATH, alerts)
    print(f"총 {added}건 백필 완료.")


if __name__ == "__main__":
    main()
