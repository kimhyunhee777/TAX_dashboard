# -*- coding: utf-8 -*-
"""
최근 1년 내 개정 이력 백필(1회성) 스크립트.

check_amendments.py는 "베이스라인 이후 실제로 바뀐 것"만 알림으로 만들기 때문에, 방금
막 추적을 시작한 조문은 실제로 몇 년째 아무 변화가 없었을 수도 있고, 반대로 최근에
개정됐지만 우리가 추적을 시작하기 *전*에 이미 반영되어버린 경우도 있다 — 이런 경우는
diff로는 절대 못 잡는다.

대신 law.go.kr 조문 원문에는 "<개정 2022.12.31>"처럼 각 항ㆍ호마다 개정 이력 날짜가
이미 박혀 있다. 이 스크립트는 (diff 없이) 그 날짜들만 파싱해서, 최근 RETENTION_DAYS 이내에
개정된 적이 있는 조문에 대해 "최근 개정 이력이 있다"는 알림을 한 번만 만들어준다.

주의: 예전 원문 자체는 없기 때문에 진짜 변경 전/후 비교는 제공하지 않는다 — 현재 조문에서
최근 날짜가 찍힌 문단만 보여준다. 이후로는 check_amendments.py가 실제 diff 기반 알림을
이어서 만든다.
"""
import os
import re
import sys
from datetime import date, timedelta

from common import load_json, save_json

ROOT = os.path.join(os.path.dirname(__file__), "..")
PROVISIONS_PATH = os.path.join(ROOT, "provisions.json")
STATE_PATH = os.path.join(ROOT, "data", "state.json")
ALERTS_PATH = os.path.join(ROOT, "data", "alerts.json")
RETENTION_DAYS = 365

TAG_RE = re.compile(r"<(개정|신설)\s*([^>]*)>")
DATE_RE = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})")


def extract_max_date(lines):
    """조문 텍스트에서 <개정 .../신설 ...> 태그 안의 날짜들 중 가장 최근 날짜를 찾는다."""
    max_date = None
    for line in lines:
        for tag in TAG_RE.finditer(line):
            for dm in DATE_RE.finditer(tag.group(2)):
                y, m, d = map(int, dm.groups())
                try:
                    dt = date(y, m, d)
                except ValueError:
                    continue
                if max_date is None or dt > max_date:
                    max_date = dt
    return max_date


def lines_with_date(lines, target_date_str):
    """target_date_str(예: '2025.12.23')이 태그에 포함된 줄만 뽑는다."""
    return [line for line in lines if target_date_str in line]


def main():
    provisions = load_json(PROVISIONS_PATH, [])
    state = load_json(STATE_PATH, {})
    alerts = load_json(ALERTS_PATH, [])
    existing_ids = {a["id"] for a in alerts}
    cutoff = date.today() - timedelta(days=RETENTION_DAYS)

    added = 0
    for prov in provisions:
        pid = prov["id"]
        cached = state.get(pid)
        if not cached:
            print(f"[skip] {pid}: state.json에 캐시된 원문이 없습니다 (check_amendments.py를 먼저 실행하세요).", file=sys.stderr)
            continue

        lines = cached.get("lines", [])
        max_date = extract_max_date(lines)
        if max_date is None or max_date < cutoff:
            continue

        alert_id = f"{pid}-backfill-{max_date.isoformat()}"
        if alert_id in existing_ids:
            continue

        date_str = f"{max_date.year}.{max_date.month}.{max_date.day}"
        affected = lines_with_date(lines, date_str)
        law, jo, branch = prov["law"], prov["jo"], prov.get("branch") or None
        jo_display = f"{jo}의{branch}" if branch else jo
        title = cached.get("title", prov.get("label", ""))

        alerts.append({
            "id": alert_id,
            "type": "amendment",
            "backfill": True,
            "provisionId": pid,
            "label": prov.get("label", title),
            "law": law,
            "jo": jo,
            "branch": branch or "",
            "detectedAt": f"{max_date.isoformat()}T00:00:00+09:00",
            "title": title,
            "recentAmendmentDate": max_date.isoformat(),
            "affectedLines": affected,
            "plainSummary": f"{law} 제{jo_display}조({title})는 최근 1년 내 개정 이력이 있습니다 (최근 개정일: {date_str}).",
            "tags": prov.get("tags", []),
        })
        added += 1
        print(f"[backfill] {pid}: 최근 개정일 {date_str}")

    save_json(ALERTS_PATH, alerts)
    print(f"총 {added}건 백필 완료.")


if __name__ == "__main__":
    main()
