# -*- coding: utf-8 -*-
"""세 감지 스크립트(check_amendments/check_precedents/check_news)가 공유하는 유틸리티."""
import json
import os
from datetime import datetime, timezone, timedelta

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
