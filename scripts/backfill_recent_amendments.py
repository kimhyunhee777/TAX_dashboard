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

같은 법령에 등록된 조문이 여러 개(예: 조세특례제한법 11개)라서, 버전 하나당 법령 XML을
조문마다 따로 내려받으면 같은 파일을 N번 중복 요청하게 된다. 그래서 버전 하나당 XML은
한 번만 받고, 그 안에서 아직 못 찾은 조문들을 한꺼번에 로컬에서 비교한다.
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

MAX_VERSIONS_BACK = 20  # 이 개수만큼 거슬러 올라가도 실제 차이를 못 찾으면 포기


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


def fetch_law_xml(mst, oc):
    resp = requests.get(
        f"{BASE_URL}/lawService.do",
        params={"OC": oc, "target": "law", "MST": mst, "type": "XML"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.content


def resolve_law_backfill(law, provs, state, oc):
    """provs: 이 법령에 속한 provisions.json 항목 리스트.
    반환: {pid: (prev_title, prev_lines)} — 실제로 달라진 과거 버전을 찾은 조문만 포함."""
    try:
        versions = list_settled_versions(law, oc)
    except (requests.RequestException, ET.ParseError) as e:
        print(f"[skip-law] {law}: {e}", file=sys.stderr)
        return {}
    if len(versions) < 2:
        return {}

    pending = {}
    for prov in provs:
        pid = prov["id"]
        cached = state.get(pid)
        if not cached:
            print(f"[skip] {pid}: state.json에 캐시된 원문이 없습니다 (check_amendments.py를 먼저 실행하세요).", file=sys.stderr)
            continue
        pending[pid] = {
            "jo": prov["jo"],
            "branch": prov.get("branch") or None,
            "current_norm": strip_amendment_tags_lines(cached.get("lines", [])),
        }

    found = {}
    for version in versions[1:1 + MAX_VERSIONS_BACK]:
        if not pending:
            break
        try:
            xml_bytes = fetch_law_xml(version["mst"], oc)
        except requests.RequestException as e:
            print(f"[skip-version] {law} {version['mst']}: {e}", file=sys.stderr)
            continue

        for pid in list(pending.keys()):
            info = pending[pid]
            try:
                title, lines = extract_article_text(xml_bytes, info["jo"], info["branch"])
            except ET.ParseError as e:
                print(f"[skip-version] {law} {version['mst']} {pid}: {e}", file=sys.stderr)
                continue
            if title is None:
                del pending[pid]  # 이 버전엔 조문이 아직 없었음(신설 이전) — 더 과거로 가도 마찬가지
                continue
            if strip_amendment_tags_lines(lines) != info["current_norm"]:
                found[pid] = (title, lines)
                del pending[pid]

    return found


def main():
    oc = os.environ.get("LAW_API_OC")
    if not oc:
        print("LAW_API_OC 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)

    provisions = load_json(PROVISIONS_PATH, [])
    state = load_json(STATE_PATH, {})
    alerts = load_json(ALERTS_PATH, [])
    now = datetime.now(KST).isoformat(timespec="seconds")

    by_law = {}
    for prov in provisions:
        by_law.setdefault(prov["law"], []).append(prov)

    added = 0
    for law, provs in by_law.items():
        results = resolve_law_backfill(law, provs, state, oc)
        for prov in provs:
            pid = prov["id"]
            if pid not in results:
                continue
            prev_title, prev_lines = results[pid]
            cached = state[pid]
            current_lines = cached.get("lines", [])

            alert_id = f"{pid}-recent-{cached.get('hash', '')[:12]}"
            if any(a["id"] == alert_id for a in alerts):
                continue

            jo, branch = prov["jo"], prov.get("branch") or None
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
