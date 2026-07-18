# -*- coding: utf-8 -*-
"""
Vercel Python 서버리스 함수: GET /api/lawtext
쿼리: law (법령명, 예: 법인세법), jo (조문번호, 예: 25)
법제처 국가법령정보센터 Open API(law.go.kr)로 해당 법령의 특정 조문 원문을 조회해 반환한다.
law.go.kr은 CORS 헤더를 보내지 않아 브라우저에서 직접 호출할 수 없으므로 이 함수가 프록시 역할을 한다.
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import os
import re
import xml.etree.ElementTree as ET
import requests

BASE_URL = "https://www.law.go.kr/DRF"
_IMG_TAG_RE = re.compile(r"</?img[^>]*>")
_WHITESPACE_RE = re.compile(r"[ \t]+")

_MST_CACHE = {}  # law name -> MST (법령일련번호), warm-instance cache only


def resolve_mst(law_name, oc):
    if law_name in _MST_CACHE:
        return _MST_CACHE[law_name]

    resp = requests.get(
        f"{BASE_URL}/lawSearch.do",
        params={"OC": oc, "target": "law", "type": "XML", "query": law_name},
        timeout=15,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    for law_el in root.findall("law"):
        name = (law_el.findtext("법령명한글") or "").strip()
        status = (law_el.findtext("현행연혁코드") or "").strip()
        mst = law_el.findtext("법령일련번호")
        if name == law_name and status == "현행" and mst:
            _MST_CACHE[law_name] = mst
            return mst

    return None


def extract_article_text(xml_bytes, jo_number, branch_number=None):
    """지정한 조문번호(+선택적으로 가지번호)에 해당하는 <조문단위> 블록에서 제목과 본문 텍스트를 뽑아낸다.
    branch_number가 없으면 가지번호 없는 본조만(예: 제24조), 있으면 그 가지조문만(예: 제29조의8) 매칭한다."""
    root = ET.fromstring(xml_bytes)
    target = str(jo_number)
    target_branch = str(branch_number).strip() if branch_number not in (None, "") else None

    for unit in root.iter("조문단위"):
        jo_el = unit.find("조문번호")
        branch_el = unit.find("조문가지번호")
        if jo_el is None or (jo_el.text or "").strip() != target:
            continue
        branch_text = (branch_el.text or "").strip() if branch_el is not None else ""
        if target_branch is None:
            if branch_text:
                continue  # 가지번호 미지정 시 본조만 사용 (예: 제25조의2는 제외)
        elif branch_text != target_branch:
            continue

        status_el = unit.find("조문여부")
        if status_el is not None and (status_el.text or "").strip() not in ("", "조문"):
            continue  # "전문" 등 실제 조문이 아닌 자리표시자 블록은 건너뜀

        title = (unit.findtext("조문제목") or "").strip()
        if not title:
            continue  # 제목 없는 빈 블록은 건너뛰고 실제 조문을 계속 탐색

        lines = []
        for el in unit.iter():
            if el.tag in ("조문내용", "항내용", "호내용", "목내용") and el.text:
                text = _IMG_TAG_RE.sub("", el.text)
                text = "\n".join(_WHITESPACE_RE.sub(" ", ln).strip() for ln in text.splitlines())
                text = re.sub(r"\n{2,}", "\n", text).strip()
                if text:
                    lines.append(text)
        return title, lines

    return None, []


def handle_request(query, oc):
    """쿼리 파라미터(dict[str, list[str]])를 받아 (status, payload)를 반환. 로컬 dev 서버와 공유."""
    law_name = (query.get("law") or [""])[0].strip()
    jo = (query.get("jo") or [""])[0].strip()
    branch = (query.get("branch") or [""])[0].strip()

    if not law_name or not jo:
        return 400, {"error": "law, jo 파라미터가 필요합니다."}
    if not oc:
        return 500, {"error": "서버에 LAW_API_OC 환경변수가 설정되어 있지 않습니다."}

    try:
        mst = resolve_mst(law_name, oc)
        if not mst:
            return 404, {"error": f"'{law_name}' 법령을 찾지 못했습니다."}

        resp = requests.get(
            f"{BASE_URL}/lawService.do",
            params={"OC": oc, "target": "law", "MST": mst, "type": "XML"},
            timeout=20,
        )
        resp.raise_for_status()
        title, lines = extract_article_text(resp.content, jo, branch or None)
    except requests.RequestException as e:
        return 502, {"error": f"법령정보센터 조회 중 오류가 발생했습니다: {e}"}
    except ET.ParseError as e:
        return 502, {"error": f"법령정보센터 응답을 해석하지 못했습니다: {e}"}

    jo_display = f"{jo}의{branch}" if branch else jo
    if title is None:
        return 404, {"error": f"{law_name} 제{jo_display}조를 찾지 못했습니다."}

    return 200, {"law": law_name, "jo": jo, "branch": branch, "title": title, "lines": lines}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        status, payload = handle_request(query, os.environ.get("LAW_API_OC"))
        self._send_json(payload, status)

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
