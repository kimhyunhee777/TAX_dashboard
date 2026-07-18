# -*- coding: utf-8 -*-
"""
세액공제/세액감면 관련 새 판례 감지 폴러.

precedents.json에 등록된 검색어로 law.go.kr 판례 목록을 조회해, 이전에 보지 못한
판례일련번호가 새로 나타나면 알림을 생성한다.

law.go.kr의 판례 상세 조회 API는 국세법령정보시스템에서 수집된 세무 판례의 경우
본문(판시사항/판결요지)을 제공하지 않는다 (법원이 직접 등록한 일부 대법원 판례만
본문 조회가 가능). 대신 검색 결과에 포함된 사건명이 쟁점을 요약하는 문장으로
되어 있어("OOO 세액공제 대상 여부" 같은 식) 그 자체를 "쉬운 설명"으로 사용한다.
"""
import os
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import requests

from common import KST, load_json, save_json, prune_old

BASE_URL = "https://www.law.go.kr/DRF"
ROOT = os.path.join(os.path.dirname(__file__), "..")
PRECEDENTS_PATH = os.path.join(ROOT, "precedents.json")
STATE_PATH = os.path.join(ROOT, "data", "precedent_state.json")
ALERTS_PATH = os.path.join(ROOT, "data", "precedent_alerts.json")
RETENTION_DAYS = 365


def parse_judgment_date(date_str):
    try:
        y, m, d = date_str.split(".")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def build_detail_url(case_id):
    """OC(개인 API 키)를 노출하지 않는 판례 조회 링크를 직접 구성한다.
    (검색 API가 돌려주는 판례상세링크에는 우리 OC가 쿼리 파라미터로 박혀있어 그대로 쓰면 안 됨)"""
    if not case_id:
        return ""
    return f"{BASE_URL}/lawService.do?target=prec&ID={case_id}&type=HTML"


def search_precedents(query, oc, display=10):
    resp = requests.get(
        f"{BASE_URL}/lawSearch.do",
        params={"OC": oc, "target": "prec", "type": "XML", "query": query, "display": display},
        timeout=20,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    results = []
    for p in root.findall("prec"):
        results.append({
            "caseId": (p.findtext("판례일련번호") or "").strip(),
            "caseName": (p.findtext("사건명") or "").strip(),
            "caseNumber": (p.findtext("사건번호") or "").strip(),
            "judgmentDate": (p.findtext("선고일자") or "").strip(),
            "courtName": (p.findtext("법원명") or "").strip(),
            "caseType": (p.findtext("사건종류명") or "").strip(),
            "sourceName": (p.findtext("데이터출처명") or "").strip(),
        })
    return results


def main():
    oc = os.environ.get("LAW_API_OC")
    if not oc:
        print("LAW_API_OC 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)

    topics = load_json(PRECEDENTS_PATH, [])
    state = load_json(STATE_PATH, {})
    alerts = load_json(ALERTS_PATH, [])
    now = datetime.now(KST).isoformat(timespec="seconds")

    for topic in topics:
        tid = topic["id"]
        try:
            results = search_precedents(topic["query"], oc)
        except (requests.RequestException, ET.ParseError) as e:
            print(f"[skip] {tid}: {e}", file=sys.stderr)
            continue

        is_first_run = tid not in state
        seen = set(state.get(tid, {}).get("seenIds", []))
        new_results = [r for r in results if r["caseId"] and r["caseId"] not in seen]

        if is_first_run:
            # 첫 실행: 전체 이력을 다 알림으로 쏟아내면 노이즈가 되므로, 최근
            # RETENTION_DAYS 이내에 선고된 판례만 골라 "최근 판례" 알림으로 채운다.
            cutoff = date.today() - timedelta(days=RETENTION_DAYS)
            new_results = [
                r for r in new_results
                if (parse_judgment_date(r["judgmentDate"]) or date.min) >= cutoff
            ]

        for r in new_results:
            alerts.append({
                "id": f"{tid}-{r['caseId']}",
                "type": "precedent",
                "topicId": tid,
                "label": topic.get("label", topic["query"]),
                "detectedAt": now,
                "plainSummary": r["caseName"],
                "caseNumber": r["caseNumber"],
                "judgmentDate": r["judgmentDate"],
                "courtName": r["courtName"],
                "caseType": r["caseType"],
                "sourceName": r["sourceName"],
                "detailUrl": build_detail_url(r["caseId"]),
                "tags": topic.get("tags", []),
            })
            print(f"[new-precedent] {tid}: {r['caseName']}")

        state[tid] = {
            "seenIds": list(seen | {r["caseId"] for r in results if r["caseId"]}),
            "lastCheckedAt": now,
        }

    alerts = prune_old(alerts, RETENTION_DAYS)
    save_json(STATE_PATH, state)
    save_json(ALERTS_PATH, alerts)


if __name__ == "__main__":
    main()
