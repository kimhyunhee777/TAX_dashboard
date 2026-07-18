# -*- coding: utf-8 -*-
"""
법령 개정 감지 폴러.

provisions.json에 등록된 (법령명, 조문번호)마다 law.go.kr에서 현재 조문 원문을 가져와
data/state.json에 저장된 이전 원문과 비교한다. 텍스트가 달라졌으면 data/alerts.json에
새 알림 레코드를 추가한다. LLM을 쓰지 않고 difflib로 변경분을 비교해 쉬운 설명 문구를
직접 조립하므로 API 키나 과금이 필요 없다.

GitHub Actions에서 매일 실행되며(.github/workflows/check-amendments.yml), 변경이 생긴
data/*.json만 커밋한다.
"""
import difflib
import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from lawtext import BASE_URL, resolve_mst, extract_article_text  # noqa: E402
import requests

ROOT = os.path.join(os.path.dirname(__file__), "..")
PROVISIONS_PATH = os.path.join(ROOT, "provisions.json")
STATE_PATH = os.path.join(ROOT, "data", "state.json")
ALERTS_PATH = os.path.join(ROOT, "data", "alerts.json")
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


def text_hash(lines):
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def build_plain_summary(law, jo_display, title, old_lines, new_lines):
    """difflib로 이전/이후 조문을 줄 단위 비교해 추가/삭제 문장을 뽑고 고정 문구로 조립한다.
    향후 설명 품질을 높이고 싶으면 이 함수만 LLM 호출로 교체하면 된다."""
    diff = list(difflib.ndiff(old_lines, new_lines))
    added = [line[2:].strip() for line in diff if line.startswith("+ ") and line[2:].strip()]
    removed = [line[2:].strip() for line in diff if line.startswith("- ") and line[2:].strip()]

    parts = [f"{law} 제{jo_display}조({title})가 개정되었습니다."]
    if removed:
        parts.append("삭제/변경 전: " + " / ".join(removed[:3]))
    if added:
        parts.append("추가/변경 후: " + " / ".join(added[:3]))
    if not added and not removed:
        parts.append("조문 문구가 변경되었습니다 (세부 내용은 원문을 확인하세요).")
    return " ".join(parts)


def fetch_article(law_name, jo, branch, oc):
    mst = resolve_mst(law_name, oc)
    if not mst:
        raise RuntimeError(f"'{law_name}' 법령을 찾지 못했습니다.")
    resp = requests.get(
        f"{BASE_URL}/lawService.do",
        params={"OC": oc, "target": "law", "MST": mst, "type": "XML"},
        timeout=20,
    )
    resp.raise_for_status()
    title, lines = extract_article_text(resp.content, jo, branch)
    if title is None:
        jo_display = f"{jo}의{branch}" if branch else jo
        raise RuntimeError(f"{law_name} 제{jo_display}조를 찾지 못했습니다.")
    return title, lines


def main():
    oc = os.environ.get("LAW_API_OC")
    if not oc:
        print("LAW_API_OC 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)

    provisions = load_json(PROVISIONS_PATH, [])
    state = load_json(STATE_PATH, {})
    alerts = load_json(ALERTS_PATH, [])
    now = datetime.now(KST).isoformat(timespec="seconds")

    for prov in provisions:
        pid, law, jo, branch = prov["id"], prov["law"], prov["jo"], prov.get("branch") or None
        jo_display = f"{jo}의{branch}" if branch else jo
        try:
            title, lines = fetch_article(law, jo, branch, oc)
        except (RuntimeError, requests.RequestException) as e:
            print(f"[skip] {pid}: {e}", file=sys.stderr)
            continue

        new_hash = text_hash(lines)
        prev = state.get(pid)

        if prev is None:
            # 첫 실행: 베이스라인만 저장, 알림 없음
            state[pid] = {"title": title, "lines": lines, "hash": new_hash, "lastCheckedAt": now}
            print(f"[baseline] {pid}")
            continue

        if prev["hash"] == new_hash:
            state[pid]["lastCheckedAt"] = now
            continue

        # 개정 감지
        summary = build_plain_summary(law, jo_display, title, prev.get("lines", []), lines)
        alerts.append({
            "id": f"{pid}-{now[:10]}",
            "type": "amendment",
            "provisionId": pid,
            "label": prov.get("label", title),
            "law": law,
            "jo": jo,
            "branch": branch or "",
            "detectedAt": now,
            "title": title,
            "originalText": lines,
            "previousText": prev.get("lines", []),
            "plainSummary": summary,
            "tags": prov.get("tags", []),
        })
        state[pid] = {"title": title, "lines": lines, "hash": new_hash, "lastCheckedAt": now}
        print(f"[amendment] {pid}: {summary}")

    save_json(STATE_PATH, state)
    save_json(ALERTS_PATH, alerts)


if __name__ == "__main__":
    main()
