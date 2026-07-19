# -*- coding: utf-8 -*-
"""세 감지 스크립트(check_amendments/check_precedents/check_news)가 공유하는 유틸리티."""
import json
import os
import re
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

_AMENDMENT_TAG_RE = re.compile(r"<(개정|신설|전문개정)[^>]*>")


def strip_amendment_tags(text):
    """조문 끝에 붙는 "<개정 2020.1.1, ...>" 같은 이력 꼬리표를 뗀다.
    이 태그는 법령 본문이 아니라 개정 이력 기록일 뿐이고, law.go.kr이 만드는 통합본마다
    누적 방식이 항상 일관되지는 않아서(타법개정 등으로 병렬 계보가 생기는 경우), 이 태그만
    다르고 실제 조문 내용은 같은 경우를 "개정됨"으로 잘못 판단하지 않기 위해 비교 시 제외한다."""
    return _AMENDMENT_TAG_RE.sub("", text).strip()


def strip_amendment_tags_lines(lines):
    return [strip_amendment_tags(line) for line in lines]


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def prune_old(alerts, retention_days, date_field="detectedAt"):
    """오래된 알림을 걷어내 데이터 파일이 무한정 커지는 것을 막는다."""
    cutoff = datetime.now(KST) - timedelta(days=retention_days)
    kept = []
    for a in alerts:
        try:
            detected = datetime.fromisoformat(a[date_field])
        except (KeyError, ValueError):
            kept.append(a)
            continue
        if detected >= cutoff:
            kept.append(a)
    return kept
