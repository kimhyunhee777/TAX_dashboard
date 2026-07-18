# -*- coding: utf-8 -*-
"""
오늘 새로 감지된 알림(법령 개정/판례/뉴스)을 모아 이메일 다이제스트로 발송한다.

check_amendments.py / check_precedents.py / check_news.py를 먼저 실행한 뒤 호출하는
것을 전제로 한다 (그 스크립트들이 만든 data/*.json에서 오늘 날짜의 알림만 추린다).

SMTP 환경변수(SMTP_HOST/PORT/USER/PASS, DIGEST_TO)가 설정되어 있지 않으면 조용히
건너뛴다 — 아직 이메일 발송을 설정하지 않은 사람도 다른 기능은 그대로 쓸 수 있게 하기 위함.
"""
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from common import KST, load_json

ROOT = os.path.join(os.path.dirname(__file__), "..")
ALERTS_PATH = os.path.join(ROOT, "data", "alerts.json")
PRECEDENT_ALERTS_PATH = os.path.join(ROOT, "data", "precedent_alerts.json")
NEWS_ALERTS_PATH = os.path.join(ROOT, "data", "news_alerts.json")

SECTIONS = [
    ("amendment", "📜 법령 개정", ALERTS_PATH),
    ("precedent", "⚖️ 판례", PRECEDENT_ALERTS_PATH),
    ("news", "📰 뉴스", NEWS_ALERTS_PATH),
]


def today_items(path, today_str):
    items = load_json(path, [])
    return [a for a in items if (a.get("detectedAt") or "").startswith(today_str)]


def render_item_html(a):
    label = a.get("label") or a.get("title") or "(제목 없음)"
    summary = a.get("plainSummary") or ""
    link = a.get("detailUrl") or a.get("articleUrl") or ""
    link_html = f'<a href="{link}">자세히 보기</a>' if link else ""
    return f"""
    <div style="padding:12px 0; border-bottom:1px solid #eee;">
      <div style="font-weight:700; font-size:14px;">{label}</div>
      <div style="font-size:13px; color:#555; margin-top:4px;">{summary}</div>
      <div style="font-size:12.5px; margin-top:6px;">{link_html}</div>
    </div>
    """


def build_digest_html(sections_with_items):
    body = ["<div style=\"font-family:sans-serif; max-width:600px;\">"]
    body.append("<h2>오늘의 세법 알림 다이제스트</h2>")
    for title, items in sections_with_items:
        body.append(f"<h3>{title} ({len(items)}건)</h3>")
        for a in items:
            body.append(render_item_html(a))
    body.append("</div>")
    return "\n".join(body)


def main():
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT", "587")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    digest_to = os.environ.get("DIGEST_TO")
    digest_from = os.environ.get("DIGEST_FROM") or smtp_user

    if not (smtp_host and smtp_user and smtp_pass and digest_to):
        print("SMTP_HOST/SMTP_USER/SMTP_PASS/DIGEST_TO 중 설정되지 않은 값이 있어 다이제스트 발송을 건너뜁니다.")
        return

    today_str = datetime.now(KST).date().isoformat()
    sections_with_items = []
    total = 0
    for _type, title, path in SECTIONS:
        items = today_items(path, today_str)
        if items:
            sections_with_items.append((title, items))
            total += len(items)

    if total == 0:
        print("오늘 새로 감지된 알림이 없어 다이제스트를 발송하지 않습니다.")
        return

    html = build_digest_html(sections_with_items)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[TAX_dashboard] 오늘의 세법 알림 {total}건"
    msg["From"] = digest_from
    recipients = [addr.strip() for addr in digest_to.split(",") if addr.strip()]
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(digest_from, recipients, msg.as_string())

    print(f"다이제스트 발송 완료: {total}건, 수신자 {len(recipients)}명")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 발송 실패가 전체 워크플로를 막지 않도록 로그만 남기고 종료
        print(f"다이제스트 발송 실패: {e}", file=sys.stderr)
