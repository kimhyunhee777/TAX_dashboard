# TAX_dashboard — 세법 개정 알림

세법 개정을 놓치지 않고 클라이언트에게 알아듣기 쉬운 형태로 안내하기 위한 알림 피드입니다.
매일 자동으로 `provisions.json`에 등록된 조문을 확인해서, 원문이 바뀌면 알림을 생성합니다.
LLM을 쓰지 않고 규칙 기반(diff)으로 설명 문구를 만들기 때문에 API 키/과금 없이 동작합니다.

## 구조

- `provisions.json` — 추적할 법령/조문 목록 (직접 편집해서 늘려가세요)
- `clients.json` — 클라이언트별 관심 태그 (직접 편집)
- `data/state.json` — 조문별 마지막 확인 결과 (스크립트가 자동 갱신, 직접 수정하지 마세요)
- `data/alerts.json` — 알림 피드 (스크립트가 자동 갱신, `index.html`이 그대로 fetch)
- `scripts/check_amendments.py` — 개정 감지 스크립트
- `api/lawtext.py` — law.go.kr 원문 조회 프록시 (Vercel 서버리스, "원문 보기" 링크용)
- `.github/workflows/check-amendments.yml` — 매일 07:00 KST 자동 실행

## 준비 과정

1. **법제처 오픈API OC 발급**: https://www.law.go.kr 오픈API 신청에서 OC(신청ID)를 발급받습니다.
2. **GitHub Secret 등록**: 저장소 Settings → Secrets and variables → Actions에 `LAW_API_OC` 등록 (자동 개정 감지 워크플로가 사용).
3. **Vercel 배포**: 이 저장소를 Vercel에 연결하고, 프로젝트 환경변수에도 `LAW_API_OC`를 동일하게 등록 (`api/lawtext.py`의 "원문 보기" 프록시가 사용).
4. **provisions.json / clients.json 채우기**: 지금은 실무에서 자주 쓰이는 세액공제·세액감면 조문(조세특례제한법·법인세법) 14건이 들어있습니다. 필요에 따라 추가/삭제하고, `clients.json`은 실제 클라이언트와 태그로 교체하세요.
   - 조문에 가지번호가 있는 경우(예: 제29조의8) `"jo": "29", "branch": "8"`처럼 `branch` 필드를 추가하세요. 가지번호가 없는 본조(예: 제24조)는 `branch` 필드를 생략하면 됩니다.

## 로컬에서 확인하기

```bash
pip install -r scripts/requirements.txt
LAW_API_OC=발급받은값 python scripts/check_amendments.py
```

처음 실행하면 `data/state.json`에 베이스라인만 저장되고 알림은 생기지 않습니다. 이후 실행에서
조문 원문이 바뀌면 `data/alerts.json`에 알림이 추가됩니다. `index.html`을 정적 서버로 열어
알림 피드, 클라이언트 필터, 벨 배지를 확인할 수 있습니다.

GitHub Actions 워크플로는 Actions 탭에서 "Run workflow"로 수동 실행해 바로 확인할 수도 있습니다.

## 알려진 한계

- law.go.kr "현행법령" 서비스는 시행된 조문만 보여줍니다. 공포는 됐지만 아직 시행 전인 개정은
  시행일이 될 때까지 감지되지 않을 수 있습니다.
- 설명 문구는 diff 기반 템플릿이라 자연스러운 문장은 아닙니다. 품질을 높이고 싶다면
  `scripts/check_amendments.py`의 `build_plain_summary()` 함수를 LLM 호출로 교체하면 됩니다.
- 로그인/알림 발송(이메일·카카오) 기능은 없습니다. 사이트 방문 시 배지로만 확인됩니다.
- **판례(法院 판결례)는 추적하지 않습니다.** 이 기능은 "같은 조문의 텍스트가 바뀌었는지"를 비교하는 구조라 법령 개정에만 맞고, 판례는 애초에 "변경"되는 대상이 아니라 새 판결이 계속 쌓이는 형태라서 데이터 모델 자체가 다릅니다(law.go.kr도 법령과 판례는 별도 API). 판례까지 필요하면 "새 판례 알림"용 별도 기능으로 추가하는 걸 권장합니다.
