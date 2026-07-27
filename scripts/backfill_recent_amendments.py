# -*- coding: utf-8 -*-
"""
최근 개정 이력 백필(1회성) 스크립트 — law.go.kr 연혁법령(eflaw) API로 실제 "변경 전" 원문을 가져온다.

check_amendments.py는 "우리가 베이스라인을 잡은 이후 실제로 바뀐 것"만 알림으로 만들기 때문에,
방금 막 추적을 시작한 조문은 그 전에 이미 일어난 개정을 diff로 잡아낼 방법이 없다.

law.go.kr은 법령의 모든 과거 공식본(연혁법령)을 법령일련번호(MST)로 조회할 수 있게 해준다.
이 스크립트는 조문별로 "현재 버전"부터 과거 버전을 하나씩 거슬러 올라가며, 실제로 내용이
달라지는 첫 버전을 찾는다. 법 전체를 기준으로 "바로 이전 버전" 하나만 보면, 그 조문과 무관한
다른 조문이 그 사이에 개정돼서 법 전체가 새 버전이 됐을 때 진짜 변경 전 상태를 놓친다
(예: 조세특례제한법 제29조의7·8이 바뀐 뒤 다른 조문 개정으로 법이 한 번 더 개정되면, "바로
이전 버전"에는 이미 제29조의7·8의 변경 내용이 들어있어 diff가 안 잡힘). 그래서 조문별로
내용이 실제로 달라질 때까지 거슬러 올라간다. <개정/신설/전문개정 ...> 이력 꼬리표만 다르고
본문은 같은 버전은 "실제 변경"으로 치지 않는다(strip_amendment_tags_lines로 비교).
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


MAX_VERSIONS_BACK = 20  # 이 개수만큼 거슬러 올라가도 실제 차이를 못 찾으면 포기


def find_last_real_change(law, jo, branch, current_lines, versions, oc):
    """versions[1:]을 오래된 방향이 아니라 최신 순서 그대로 하나씩 조회하면서, 현재 조문과
    실제 내용(개정 이력 꼬리표 제외)이 달라지는 첫 버전을 찾아 (title, lines)를 반환한다.
    못 찾으면 (None, None)."""
    current_norm = strip_amendment_tags_lines(current_lines)
    for version in versions[1:1 + MAX_VERSIONS_BACK]:
        try:
            title, lines = fetch_article_at_mst(version["mst"], jo, branch, oc)
        except (requests.RequestException, ET.ParseError) as e:
            print(f"[skip-version] {law} {version['mst']}: {e}", file=sys.stderr)
            continue
        if title is None:
            break  # 이 버전엔 조문이 아직 없었음(신설 이전) — 더 과거로 가도 마찬가지이므로 중단
        if strip_amendment_tags_lines(lines) != current_norm:
            return title, lines
    return None, None


def main():
    oc = os.environ.get("LAW_API_OC")
    if not oc:
        print("LAW_API_OC 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)

    provisions = load_json(PROVISIONS_PATH, [])
    state = load_json(STATE_PATH, {})
    alerts = load_json(ALERTS_PATH, [])
    now = datetime.now(KST).isoformat(timespec="seconds")

    versions_cache = {}  # law_name -> settled versions list (조문 여러 개가 공유)
    added = 0

    for prov in provisions:
        pid, law, jo, branch = prov["id"], prov["law"], prov["jo"], prov.get("branch") or None
        cached = state.get(pid)
        if not cached:
            print(f"[skip] {pid}: state.json에 캐시된 원문이 없습니다 (check_amendments.py를 먼저 실행하세요).", file=sys.stderr)
            continue

        if law not in versions_cache:
            try:
                versions_cache[law] = list_settled_versions(law, oc)
            except (requests.RequestException, ET.ParseError) as e:
                print(f"[skip-law] {law}: {e}", file=sys.stderr)
                versions_cache[law] = []

        versions = versions_cache[law]
        if len(versions) < 2:
            continue

        current_lines = cached.get("lines", [])
        prev_title, prev_lines = find_last_real_change(law, jo, branch, current_lines, versions, oc)
        if prev_title is None:
            continue  # 실제로 달라진 과거 버전을 못 찾음 (조회 범위 내에 변경 없음, 또는 신설 직후)

        alert_id = f"{pid}-recent-{state[pid].get('hash', '')[:12]}"
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
