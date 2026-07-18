# TAX_dashboard — 세법 개정·판례 알림

세법 개정과 관련 판례를 놓치지 않고 클라이언트에게 알아듣기 쉬운 형태로 안내하기 위한 알림
피드입니다. 매일 자동으로 (1) `provisions.json`에 등록된 조문의 원문이 바뀌었는지, (2)
`precedents.json`에 등록된 주제와 관련된 새 판례가 나왔는지 확인해서 알림을 생성합니다.
LLM을 쓰지 않기 때문에 API 키/과금 없이 동작합니다.

## 구조

- `provisions.json` — 추적할 법령/조문 목록 (직접 편집해서 늘려가세요)
- `precedents.json` — 추적할 판례 검색어/주제 목록 (직접 편집)
- `clients.json` — 클라이언트별 관심 태그 (직접 편집)
- `data/state.json` / `data/alerts.json` — 법령 개정 감지 상태/알림 (스크립트가 자동 갱신)
- `data/precedent_state.json` / `data/precedent_alerts.json` — 판례 감지 상태/알림 (스크립트가 자동 갱신)
- `scripts/check_amendments.py` — 법령 개정 감지 스크립트 (diff 기반, 변경 전/후 비교)
- `scripts/check_precedents.py` — 새 판례 감지 스크립트 (사건명을 그대로 "쉬운 설명"으로 사용)
- `api/lawtext.py` — law.go.kr 원문 조회 프록시 (Vercel 서버리스, "원문 보기" 링크용)
- `.github/workflows/check-amendments.yml` — 매일 07:00 KST 자동 실행 (개정 확인 + 판례 확인)

## 준비 과정

1. **법제처 오픈API OC 발급**: https://www.law.go.kr 오픈API 신청에서 OC(신청ID)를 발급받습니다.
2. **GitHub Secret 등록**: 저장소 Settings → Secrets and variables → Actions에 `LAW_API_OC` 등록 (자동 개정 감지 워크플로가 사용).
3. **Vercel 배포**: 이 저장소를 Vercel에 연결하고, 프로젝트 환경변수에도 `LAW_API_OC`를 동일하게 등록 (`api/lawtext.py`의 "원문 보기" 프록시가 사용).
4. **provisions.json / precedents.json / clients.json 채우기**: 지금은 실무에서 자주 쓰이는
   세액공제·세액감면 조문(조세특례제한법·법인세법) 14건과, 그와 관련된 판례 검색어 7건이
   들어있습니다. 필요에 따라 추가/삭제하고, `clients.json`은 실제 클라이언트와 태그로 교체하세요.
   - 조문에 가지번호가 있는 경우(예: 제29조의8) `"jo": "29", "branch": "8"`처럼 `branch` 필드를 추가하세요. 가지번호가 없는 본조(예: 제24조)는 `branch` 필드를 생략하면 됩니다.
   - `precedents.json`의 `query`는 law.go.kr 판례 검색에 그대로 들어가는 검색어입니다. 너무 넓은 단어(예: "세액공제" 단독)는 결과가 너무 많아 알림이 잦아지니, 구체적인 제도명으로 좁혀서 넣는 걸 권장합니다.

## 로컬에서 확인하기

```bash
pip install -r scripts/requirements.txt
LAW_API_OC=발급받은값 python scripts/check_amendments.py
LAW_API_OC=발급받은값 python scripts/check_precedents.py
```

처음 실행하면 각각 `data/state.json` / `data/precedent_state.json`에 베이스라인만 저장되고
알림은 생기지 않습니다. 이후 실행에서 조문 원문이 바뀌거나 새 판례가 나오면 `data/alerts.json`
/ `data/precedent_alerts.json`에 알림이 추가됩니다. `index.html`을 정적 서버로 열어 알림 피드,
클라이언트 필터, 벨 배지를 확인할 수 있습니다.

GitHub Actions 워크플로는 Actions 탭에서 "Run workflow"로 수동 실행해 바로 확인할 수도 있습니다.

## 알려진 한계

- law.go.kr "현행법령" 서비스는 시행된 조문만 보여줍니다. 공포는 됐지만 아직 시행 전인 개정은
  시행일이 될 때까지 감지되지 않을 수 있습니다.
- 설명 문구는 diff 기반 템플릿이라 자연스러운 문장은 아닙니다. 품질을 높이고 싶다면
  `scripts/check_amendments.py`의 `build_plain_summary()` 함수를 LLM 호출로 교체하면 됩니다.
- 로그인/알림 발송(이메일·카카오) 기능은 없습니다. 사이트 방문 시 배지로만 확인됩니다.
- **판례 본문(판시사항/판결요지)은 제공하지 않습니다.** 세무 판례는 대부분 국세법령정보시스템에서
  수집된 자료라 law.go.kr의 판례 상세 조회 API로는 본문을 가져올 수 없고, 검색 결과에 포함된
  사건명·사건번호·선고일자 등 메타데이터만 표시합니다. 다만 이 도메인의 사건명 자체가 쟁점을
  요약하는 문장으로 되어 있어("OOO 세액공제 대상 여부" 등) 실질적으로 쉬운 설명 역할을 합니다.
  전문이 필요하면 알림 카드의 "law.go.kr에서 판례 보기" 링크로 이동해서 확인해야 합니다.
