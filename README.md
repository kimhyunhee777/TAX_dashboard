# TAX_dashboard — 세법 개정·판례·뉴스 알림

세법 개정, 관련 판례, 관련 뉴스를 놓치지 않고 클라이언트에게 알아듣기 쉬운 형태로 안내하기
위한 알림 피드입니다. 매일 자동으로 (1) `provisions.json`에 등록된 조문의 원문이 바뀌었는지,
(2) `precedents.json`에 등록된 주제와 관련된 새 판례가 나왔는지, (3) `news_topics.json`에
등록된 검색어로 새 뉴스 기사가 나왔는지 확인해서 알림을 생성합니다. LLM을 쓰지 않기 때문에
API 키/과금 없이 동작합니다 (뉴스는 Google 뉴스 RSS를 사용하며 이것도 키가 필요 없습니다).

## 구조

- `provisions.json` — 추적할 법령/조문 목록 (직접 편집해서 늘려가세요)
- `precedents.json` — 추적할 판례 검색어/주제 목록 (직접 편집)
- `news_topics.json` — 추적할 뉴스 검색어/주제 목록 (직접 편집)
- `clients.json` — 업종별 관심 태그 (제조업/소비재·유통업/IT·서비스업 등, 직접 편집)
- `data/state.json` / `data/alerts.json` — 법령 개정 감지 상태/알림 (스크립트가 자동 갱신)
- `data/precedent_state.json` / `data/precedent_alerts.json` — 판례 감지 상태/알림 (스크립트가 자동 갱신)
- `data/news_state.json` / `data/news_alerts.json` — 뉴스 감지 상태/알림 (스크립트가 자동 갱신)
- `scripts/check_amendments.py` — 법령 개정 감지 스크립트 (diff 기반, 변경 전/후 비교)
- `scripts/check_precedents.py` — 새 판례 감지 스크립트 (사건명을 그대로 "쉬운 설명"으로 사용)
- `scripts/check_news.py` — 새 뉴스 감지 스크립트 (헤드라인만 저장, 본문은 저장하지 않음)
- `api/lawtext.py` — law.go.kr 원문 조회 프록시 (Vercel 서버리스, "원문 보기" 링크용)
- `.github/workflows/check-amendments.yml` — 매일 07:00 KST 자동 실행 (개정/판례/뉴스 확인)

## 준비 과정

1. **법제처 오픈API OC 발급**: https://www.law.go.kr 오픈API 신청에서 OC(신청ID)를 발급받습니다.
2. **GitHub Secret 등록**: 저장소 Settings → Secrets and variables → Actions에 `LAW_API_OC` 등록 (자동 개정 감지 워크플로가 사용).
3. **Vercel 배포**: 이 저장소를 Vercel에 연결하고, 프로젝트 환경변수에도 `LAW_API_OC`를 동일하게 등록 (`api/lawtext.py`의 "원문 보기" 프록시가 사용).
4. **provisions.json / precedents.json / news_topics.json / clients.json 채우기**: 지금은
   실무에서 자주 쓰이는 세액공제·세액감면 조문(조세특례제한법·법인세법) 14건, 관련 판례 검색어
   7건, 관련 뉴스 검색어 4건이 들어있습니다. `clients.json`은 개별 회사가 아니라 업종 6종
   (제조업/소비재·유통업/IT·서비스업/건설업/수출·해외법인/개인사업자·자영업)으로 구성되어
   있어서, 클라이언트가 어떤 업종인지에 따라 관련 조문·판례·뉴스만 걸러볼 수 있습니다. 필요에
   따라 자유롭게 추가/삭제하세요.
   - 조문에 가지번호가 있는 경우(예: 제29조의8) `"jo": "29", "branch": "8"`처럼 `branch` 필드를 추가하세요. 가지번호가 없는 본조(예: 제24조)는 `branch` 필드를 생략하면 됩니다.
   - `precedents.json`/`news_topics.json`의 `query`는 각각 law.go.kr 판례 검색·Google 뉴스 검색에 그대로 들어가는 검색어입니다. 너무 넓은 단어(예: "세액공제" 단독)는 결과가 너무 많아 알림이 잦아지니, 구체적인 제도명으로 좁혀서 넣는 걸 권장합니다.
   - 특정 업종 하나에 묶기 애매한 일반 뉴스(예: 매년 발표되는 세법개정안)는 `"tags": ["전체"]`로 넣으면 업종 필터와 무관하게 모든 업종에서 보입니다.

## 로컬에서 확인하기

```bash
pip install -r scripts/requirements.txt
LAW_API_OC=발급받은값 python scripts/check_amendments.py
LAW_API_OC=발급받은값 python scripts/check_precedents.py
python scripts/check_news.py   # 뉴스는 OC 불필요
```

처음 실행하면 각각의 `data/*_state.json`에 베이스라인만 저장되고 알림은 생기지 않습니다.
이후 실행에서 조문 원문이 바뀌거나, 새 판례·뉴스가 나오면 각 `data/*_alerts.json`에 알림이
추가됩니다. `index.html`을 정적 서버로 열어 알림 피드, 업종 필터, 벨 배지를 확인할 수 있습니다.

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
- **뉴스도 헤드라인만 저장합니다.** 기사 본문은 언론사 저작물이라 그대로 가져와 저장하지
  않고, 제목·출처·발행일과 원문 링크만 보관합니다("기사 원문 보기"를 눌러야 전문을 볼 수
  있음). Google 뉴스 RSS를 사용하므로 링크가 news.google.com 리다이렉트 주소로 뜨는 점도
  참고하세요.
