# Game Legal Briefing — GPT 5.6 Sol Pro 리뷰 개선 기획

**상태**: IMPLEMENTED — LOCAL VERIFIED
**작성일**: 2026-07-18 KST
**대상 저장소**: `lowtidebuild/legal-briefing`
**기준 브랜치**: `main`
**구현 전 기준 테스트**: `python3 -m pytest -q` → `107 passed, 1 warning`
**구현 후 검증**: 시스템 Python 및 clean Python 3.11에서 각각 `170 passed`
**외부 리뷰 판정**: GPT 5.6 Sol + Pro, `PASS_WITH_FINDINGS`
**문서 목적**: Pro 리뷰에서 수용한 4개 HIGH, 2개 MEDIUM 항목을 무료 운영 원칙을 유지하면서 구현 가능한 작업 단위로 전환한다.

---

## 0. 이 문서의 사용 방법

이 문서는 후속 구현 작업의 범위 계약이다. 구현자는 이 문서에 적힌 순서, 비목표, 완료 기준을 기준으로 작업한다.

- 한 세션에서는 아래의 구현 세션 하나만 완료하는 것을 기본으로 한다.
- 각 세션은 독립적으로 테스트하고 커밋할 수 있어야 한다.
- 사용자 요청 없이 이메일을 보내거나 Sheets에 실제 데이터를 쓰지 않는다.
- `web_only` 또는 `--dry-run` 검증과 실제 전달 검증을 구분한다.
- 기존 `output/data/daily/*.json`과 공개 상세 페이지 URL을 불필요하게 마이그레이션하지 않는다.
- 대규모 프레임워크, DB, 유료 큐, 외부 관측 서비스는 도입하지 않는다.
- 구현 중 새 사실이 이 문서의 전제와 충돌하면 임의로 범위를 넓히지 말고 문서를 갱신한 뒤 진행한다.

---

## 1. 결론

현재 앱은 구조적으로 붕괴한 상태가 아니다. 로컬 테스트는 통과하고 GitHub Actions도 최근에는 성공한다. 문제는 **성공한 실행 안에서 대량의 오류와 fallback이 발생하고, 그 사실이 서비스 상태로 드러나지 않는 것**이다.

2026-07-17 실행의 검증된 기준값은 다음과 같다.

| 지표 | 값 | 해석 |
|---|---:|---|
| GitHub Actions 최근 68회 | 성공 62 / 실패 6 | 워크플로 자체는 대체로 안정적 |
| 마지막 실제 Actions 실패 | 2026-04-29 | 최근 화면의 `fail` 대부분은 job 실패가 아님 |
| Gemini 3.5 Flash 성공 | 8 | 일부만 primary 성공 |
| Gemini 3.5 Flash 429 | 39 | 현재 호출 구조가 5 RPM 한도와 불일치 |
| Flash-Lite 성공 | 13 | 21개 유효 결과 중 13개가 fallback |
| Tier A 무응답/빈 결과 | 30 / 44 | 핵심 소스 커버리지 저하 |
| RSS HTTP 403 | 29 | 요청 방식 또는 차단/폐기 소스 혼재 |
| RSS HTTP 404 | 5 | URL 변경 또는 제거 후보 |
| 게시 기사 | 10 | 수량은 채웠지만 품질 문제가 있음 |
| `AI_EMERGING` | 6 / 10 | 일반 AI 뉴스가 법률 브리핑을 잠식 |

목표 상태는 다음과 같다.

```text
현재
fetch -> 정확히 10건 선택 -> 10회 분류 -> 10회 요약
      -> 이메일/Sheets -> git push -> Pages 배포

목표
상태가 구분된 fetch
  -> 법률 관련 기사만 최대 10건 선택
  -> 분류 1회 배치
  -> 이벤트 중복 제거
  -> 요약 1~2회 배치
  -> 품질 검증
  -> 불변 run manifest 생성
  -> git push + Pages 배포
  -> run_id 확인 후 이메일/Sheets 전달
  -> SUCCESS / DEGRADED / NO_UPDATES / FAIL 요약
```

---

## 2. 목표와 성공 지표

### 2.1 운영 안정성

- 정상 10건 실행의 primary LLM 호출을 3회로 줄인다.
  - 선택 1회
  - 분류 1회
  - 요약 1회
- 요약 응답 크기 때문에 분할이 필요해도 정상 호출은 최대 4회로 제한한다.
- 429 응답에 1초/2초 재시도를 반복하지 않는다.
- Gemini SDK에 설정된 요청 timeout을 실제 HTTP 요청에 적용한다.
- primary가 제한되면 같은 실행에서 매 기사마다 primary를 다시 두드리지 않는다.
- production 실행 전 전체 pytest가 통과해야 한다.

### 2.2 콘텐츠 품질

- `top_n: 10`은 발행 의무 수량이 아니라 상한이다.
- 법률 연결고리가 없는 기사는 LLM이 선택하더라도 게시하지 않는다.
- 후보가 부족하면 1~9건만 게시할 수 있다.
- 실질적인 법률 업데이트가 없으면 `NO_UPDATES`로 종료할 수 있다.
- `AI`라는 단어만으로는 법률 브리핑 후보가 되지 않는다.
- 제목·설명에 포함된 게임/기술 신호와 법률 신호를 구분한다.

### 2.3 보안과 데이터 일관성

- LLM 원문을 그대로 파일 경로에 사용하지 않는다.
- 새 `event_key`는 `[a-z0-9_]{1,120}`을 만족한다.
- `../`, `/`, `\\`, 절대경로, NUL 등 경로 이탈 입력은 해시 fallback으로 바꾼다.
- article page의 resolved path가 반드시 `output/article` 아래인지 검사한다.
- `event_key`의 연도/분기는 기사 `pub_date`에서 코드로 결정한다.
- 현재 공개 아카이브 565개 저장 노드의 유효한 `event_key`와 상세 페이지는 그대로 렌더링한다.

### 2.4 서비스 운영

- GitHub Actions의 초록불이 다음 중 무엇인지 한눈에 구분되어야 한다.
  - `SUCCESS`: 모든 필수 단계 완료
  - `DEGRADED`: 발행·전달은 됐지만 source/LLM fallback 저하 발생
  - `NO_UPDATES`: 정상 수집·선별 후 게시할 중요 법률 업데이트 없음
  - `FAIL`: 생성, 품질, 배포 또는 필수 전달 단계 실패
- 이메일과 Sheets는 Pages 배포 성공 전에 실행하지 않는다.
- 같은 `run_id`가 완료된 경우 기본 재실행에서 다시 전달하지 않는다.
- raw exception, credential, 수신자 주소는 run report에 저장하지 않는다.

---

## 3. 비목표

이번 개선에서 하지 않는 일:

- 유료 LLM을 기본 provider로 전환
- Groq 또는 다른 무료 provider를 새 기본값으로 추가
- DB, Redis, 메시지 큐, 유료 관측 서비스 도입
- 웹 UI/CSS 전면 개편
- 과거 모든 `event_key` 일괄 변경
- 과거 상세 페이지 URL 마이그레이션
- 모든 403 사이트를 위한 개별 scraper 제작
- 이메일·GitHub Pages·Sheets 간 완전한 분산 트랜잭션 보장
- 영어 요약, 대시보드, jurisdiction tracker 등 제품 기능 확장

SMTP, GitHub Pages, Google Sheets 사이의 완전한 원자성은 무료 정적 구조에서 보장할 수 없다. 이번 목표는 **순서 보장, 중복 방지용 식별자, 실패 상태 가시화, 안전한 수동 복구**다.

---

## 4. 확정 설계 결정

### 결정 1. Gemini 3.5 Flash를 유지하고 호출을 배치화한다

Flash-Lite에 분류·요약을 상시 배정하지 않는다. 정상 경로에서는 Gemini 3.5 Flash가 선택, 분류, 요약을 담당한다. Flash-Lite는 primary 배치 실패 또는 누락 레코드 복구에만 사용한다.

이유:

- 5 RPM 한도 안에 정상 3~4회 호출을 넣을 수 있다.
- primary 품질을 모든 편집 단계에서 유지할 수 있다.
- provider 추가나 라우팅 정책 확장 없이 현재 구조를 활용한다.
- Pro 리뷰가 권고한 가장 작은 수정이다.

### 결정 2. item 식별자는 배열 위치가 아니라 URL hash를 쓴다

배치 요청과 응답은 각 기사에 `item_id`를 포함한다.

```python
item_id = url_hash(article.url)
```

응답 검증 규칙:

- 요청한 `item_id`만 허용한다.
- 중복 `item_id`를 거부한다.
- 누락된 `item_id`를 계산한다.
- 알 수 없는 ID가 포함되면 배치 전체를 신뢰하지 않는다.
- 누락된 항목만 fallback 배치로 한 번 복구한다.
- primary와 fallback 모두 불완전하면 quality failure로 종료한다.

### 결정 3. 10건은 최대치다

selector는 0~10건을 반환할 수 있다. LLM이 선택하지 않은 후보를 코드가 다시 채우지 않는다.

- `_enforce_domain_cap`은 선택된 결과에서 도메인 상한만 적용한다.
- 기존처럼 전체 pool에서 빈자리를 보충하지 않는다.
- 도메인 cap 때문에 수량이 줄어드는 것을 허용한다.
- selector 실패 시 raw first-N으로 fallback하지 않는다.
- deterministic fallback은 명백한 법률 신호가 있는 후보만 사용하고 실행 상태를 `DEGRADED`로 기록한다.
- 후보 수가 `top_n` 이하라도 selector를 생략하지 않는다.

### 결정 4. 법률 관련성은 boolean + 근거 enum으로 표현한다

주관적인 0~100 점수 대신 다음 구조를 사용한다.

```json
{
  "selected": [
    {
      "item_id": "16-char-url-hash",
      "is_legally_relevant": true,
      "legal_hook": "litigation"
    }
  ]
}
```

허용 `legal_hook` 예시:

- `litigation`
- `enforcement`
- `legislation`
- `regulation`
- `official_guidance`
- `platform_policy`
- `privacy_security_incident`
- `ip_dispute`
- `labor_employment`
- `antitrust_transaction`
- `consumer_monetization_compliance`

`AI`, 신기능, 제작 효율, 시장 전망, 성장 마케팅은 그 자체로 legal hook이 아니다.

### 결정 5. `event_key` 필드는 유지하되 코드에서 안전하게 확정한다

새 `article_slug` 필드를 데이터 모델 전체에 추가하지 않는다. 기존 템플릿, manifest, Sheets, daily JSON이 `event_key`를 이미 사용하므로 해당 필드를 안전한 canonical key로 유지한다.

권장 알고리즘:

1. raw 값에서 경로 제어 문자를 먼저 탐지한다.
2. `/`, `\\`, `..`, NUL, 절대경로 형식이 있으면 raw 값을 폐기한다.
3. NFKC 정규화, 소문자화, 영문·숫자·underscore 이외 문자를 underscore로 바꾼다.
4. 연속 underscore를 하나로 줄이고 양끝 underscore를 제거한다.
5. 모델이 붙인 `_2024`, `_2026q1`, `_ongoing` 같은 끝 토큰을 제거한다.
6. `pub_date`에서 계산한 `YYYYqN`을 끝에 붙인다.
7. 빈 값, 과도하게 긴 값, 허용식 불일치는 `compute_event_key(...)` 해시 + year bucket으로 대체한다.
8. 최종 길이는 120자 이하로 제한하되 year bucket은 보존한다.

추가 방어:

```python
candidate = os.path.realpath(os.path.join(article_dir, f"{event_key}.html"))
if os.path.commonpath([article_dir_real, candidate]) != article_dir_real:
    raise ValueError("article path escaped output/article")
```

### 결정 6. 생성, 배포, 전달을 분리한다

`main.py` 한 번의 실행에서 모든 외부 side effect를 처리하지 않는다.

목표 단계:

```text
generate
  - fetch / select / classify / summarize
  - quality gate
  - daily JSON / site / run manifest 생성
  - 이메일과 Sheets는 실행하지 않음

publish
  - generated data commit + push
  - Pages artifact upload + deploy

deliver
  - 배포 성공 확인
  - 동일 run_id 완료 여부 확인
  - 이메일 발송
  - Sheets append
  - delivery receipt 기록
```

`run_id`는 날짜 기준으로 결정한다.

```text
briefing-YYYY-MM-DD
```

동일 날짜의 교정 재배포는 같은 `run_id`를 쓴다. 실제 재전달은 별도 `force_delivery` 승인이 있을 때만 허용한다.

### 결정 7. 완전한 exactly-once 대신 안전한 기본 재실행을 택한다

Gmail SMTP는 idempotency key를 지원하지 않는다. 이메일 전송 성공 직후 receipt 기록 전에 job이 죽으면 중복 가능성을 완전히 제거할 수 없다.

따라서:

- 완료 receipt가 있으면 자동 재전달하지 않는다.
- 상태가 애매한 run은 자동 재전달하지 않고 `DELIVERY_AMBIGUOUS`로 중단한다.
- 운영자가 이전 Actions 로그와 Sheet를 확인한 뒤 `force_delivery`를 선택한다.
- 누락 위험보다 무단 중복 메일 방지를 기본값으로 둔다.

---

## 5. Workstream A — LLM 호출 예산과 장애 처리

### 5.1 현재 문제

- `main.py`가 selector 1회, classification 최대 10회, summary 최대 10회를 호출한다.
- `concurrency: 2` 때문에 5 RPM primary에 burst가 발생한다.
- `GeminiProvider`는 모든 exception을 1초/2초 간격으로 동일하게 재시도한다.
- Google RetryInfo의 30~54초 지시를 무시한다.
- `request_timeout_seconds`는 저장만 되고 실제 SDK client에 적용되지 않는다.
- `FallbackProvider`는 각 기사마다 primary를 다시 시도하므로 circuit breaker 역할을 하지 못한다.

### 5.2 구현 방향

#### A-1. 배치 API 추가

수정 후보:

- `pipeline/intelligence/classifier.py`
- `pipeline/intelligence/summarizer.py`
- `main.py`
- `tests/test_classifier.py`
- `tests/test_summarizer.py`
- 신규 `tests/test_batch_intelligence.py`

새 함수 계약:

```python
def classify_articles(
    articles: list[RawArticle],
    llm: LLMProvider,
) -> list[ClassificationResult]:
    """Return one validated result per input article, preserving input order."""

def summarize_articles(
    articles: list[RawArticle],
    llm: LLMProvider,
    batch_size: int = 10,
) -> list[SummaryResult]:
    """Return one validated Korean summary per input article."""
```

기존 단건 함수는 테스트·fallback용 thin wrapper로 유지할 수 있으나 `main.py` 정상 경로에서는 호출하지 않는다.

#### A-2. 배치 structured schema

분류 스키마:

```json
{
  "type": "object",
  "properties": {
    "results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "item_id": {"type": "string"},
          "category": {"type": "string"},
          "jurisdiction": {"type": "string"},
          "event_type": {"type": "string"},
          "regulatory_phase": {"type": "string"},
          "actors": {"type": "array", "items": {"type": "string"}},
          "object": {"type": "string"},
          "action": {"type": "string"},
          "game_mechanic": {"type": "string"},
          "time_hint": {"type": "string"},
          "event_key": {"type": "string"}
        },
        "required": [
          "item_id", "category", "jurisdiction", "event_type",
          "regulatory_phase", "actors", "object", "action",
          "time_hint", "event_key"
        ]
      }
    }
  },
  "required": ["results"]
}
```

요약도 `item_id`, `title_ko`, `summary_ko` 배열 구조로 맞춘다.

#### A-3. timeout 실제 적용

현재 설치 SDK의 `types.HttpOptions.timeout`은 millisecond 단위다.

```python
self._client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(
        timeout=request_timeout_seconds * 1000,
    ),
)
```

구현 시 Actions의 Python 3.11 환경과 lock된 SDK 버전에서 signature를 다시 확인한다.

#### A-4. 오류 분류

재시도 대상:

- timeout
- 연결 중단
- HTTP 500, 502, 503, 504
- 분당 429 + 유효한 RetryInfo

즉시 실패 또는 fallback 대상:

- 400/401/403
- 잘못된 schema
- daily quota 429
- 동일 RPM 429가 지정 대기 후 다시 발생

RPM 429 처리:

1. RetryInfo가 60초 이하면 해당 시간 + 작은 jitter 후 한 번 재시도한다.
2. 두 번째 429이면 같은 `(provider, model)` circuit을 현재 실행 동안 연다.
3. 이후 배치는 primary를 호출하지 않고 fallback으로 바로 보낸다.
4. primary/fallback 사용 내역을 run report에 집계한다.

#### A-5. 공유 quota gate

analysis provider와 summary provider가 reasoning 설정 때문에 별도 객체여도 같은 Gemini model quota 상태를 공유해야 한다.

작은 `RateLimitGate` 객체를 `main.py`에서 한 번 만들고 provider 생성 시 주입한다.

```python
@dataclass
class RateLimitGate:
    blocked_until_by_model: dict[str, float]
    disabled_models: set[str]
```

API key나 project ID는 gate에 저장하지 않는다.

### 5.3 완료 기준

- 10개 기사 정상 mock 실행에서 Gemini primary 호출이 3회다.
- summary를 2개 배치로 나누면 최대 4회다.
- 요청과 응답 순서가 달라도 원래 기사 순서로 복원된다.
- duplicate/unknown/missing `item_id` 테스트가 있다.
- 429 RetryInfo 45초 mock에서 1초/2초 재시도가 발생하지 않는다.
- circuit open 후 같은 model primary 호출이 증가하지 않는다.
- timeout이 Gemini client에 millisecond로 전달된다.
- primary batch 실패 후 Flash-Lite batch가 성공하면 전체 실행은 계속되고 `DEGRADED`가 된다.

---

## 6. Workstream B — 법률 관련성 게이트

### 6.1 현재 문제

- selector prompt가 `EXACTLY 10`을 강제한다.
- 선택 결과가 부족하면 전체 pool에서 다시 채운다.
- 후보가 10개 이하면 selector 자체를 건너뛴다.
- selector 실패 시 첫 10건을 그대로 게시한다.
- keyword에 `AI`, `security`, `policy`, `EU` 같은 광범위 단어가 있다.
- 현재 quality gate는 한국어 요약, ETC 비율, batch 내 event key 중복만 본다.

### 6.2 구현 방향

#### B-1. selector 계약 변경

```text
select EXACTLY 10
```

을 다음으로 바꾼다.

```text
select up to 10; return fewer or zero when the legal nexus is insufficient
```

선택 결과에는 `legal_hook`을 포함한다. 코드가 허용 enum인지 검증한다.

#### B-2. backfill 제거

`_enforce_domain_cap`은 선택된 기사만 입력받아 cap을 적용한다. 빈자리를 pool에서 채우는 로직과 cap 완화 로직은 제거한다.

#### B-3. deterministic fallback 제한

LLM selector가 실패했을 때 전체 first-N을 게시하지 않는다.

최소 fallback 조건:

- 게임 산업 신호가 있고 법률 신호도 있음, 또는
- 기사 자체가 명백한 규제기관/법원/법률 매체의 집행·소송·법령 기사임

fallback으로 선택했으면 run status를 `DEGRADED`로 기록한다.

#### B-4. 키워드 구조 분리

단일 keyword 목록을 두 그룹으로 나눈다.

```yaml
pipeline:
  game_signals:
    - game
    - gaming
    - esports
    - app store
    - loot box
    - virtual goods
    - in-game purchase

  legal_signals:
    - lawsuit
    - court
    - enforcement
    - regulation
    - legislation
    - antitrust
    - privacy
    - copyright
    - patent
    - labor
    - platform policy
```

기존 `keywords`는 한 번에 삭제하지 않는다. config loader에서 구형 `keywords`를 읽을 수 있게 하되 production config는 새 구조로 전환한다.

#### B-5. `NO_UPDATES`

source 수집과 LLM이 정상인데 통과 기사가 0건이면 실패가 아니다.

- 빈 daily JSON과 run manifest를 생성한다.
- 홈페이지에는 “오늘은 중대한 게임 법률 업데이트가 없습니다” 상태를 렌더링할 수 있다.
- 이메일과 Sheets는 건너뛴다.
- GitHub Summary에는 `NO_UPDATES`를 표시한다.

source 수집 자체가 실패해 0건인 경우와 혼동하지 않는다.

### 6.3 품질 테스트 예시

반드시 제외:

- “Roblox lets users make games with AI on mobile”
- “Netflix uses generative AI to cut production costs”
- “Half of Steam games will use AI by 2028”
- “Mobile game marketing platform expands in China”

포함 가능:

- AI 생성물에 대한 저작권 소송
- FTC의 게임사 아동 개인정보 집행
- 앱스토어 정책 변경이 결제·소비자보호 의무를 변경하는 기사
- 게임사 인수에 대한 경쟁당국 심사
- 게임 노동조합 판결 또는 행정기관 결정

### 6.4 완료 기준

- 후보가 7개여도 selector가 실행된다.
- selector는 0~10개를 반환한다.
- 선택되지 않은 기사가 backfill되지 않는다.
- AI-only fixture가 거부된다.
- 법률 연결고리가 있는 AI/IP fixture는 통과한다.
- 0건은 수집 정상 시 `NO_UPDATES`, 수집 실패 시 `FAIL`로 구분된다.
- 10건 미만도 quality gate를 통과할 수 있다.

---

## 7. Workstream C — `event_key` 안전성과 의미 안정성

### 7.1 현재 문제

- LLM 값은 소문자와 공백 치환만 거친다.
- `event_key`가 바로 HTML 파일명과 URL이 된다.
- schema의 required 목록에 `event_key`가 없다.
- classifier prompt에 `pub_date`가 없다.
- 2026 기사에 2024 suffix가 생성됐다.
- 악의적 RSS description이 prompt를 통해 경로 문자열을 유도할 수 있다.

### 7.2 구현 방향

수정 후보:

- `pipeline/intelligence/classifier.py`
- `pipeline/intelligence/dedup.py`
- `pipeline/store/nodes.py`
- `pipeline/render/site.py`
- `pipeline/render/manifest.py`
- `templates/index.html`
- 신규 `tests/test_event_key_safety.py`
- `tests/test_site.py`
- `tests/test_manifest.py`

구현 요소:

1. classifier prompt에 `Publication date: {pub_date}`를 넣는다.
2. `event_key`를 schema required에 추가한다.
3. `canonicalize_event_key(...)`를 코드에 추가한다.
4. `assemble_node` 전에 canonical key를 확정한다.
5. article render 직전에 containment를 다시 검사한다.
6. manifest URL도 canonical key만 사용한다.

### 7.3 호환성

- 현재 공개 아카이브 565개 노드의 event key는 모두 `[a-z0-9_]{1,120}`을 만족한다.
- 기존 daily JSON을 읽을 때 key를 새 규칙으로 재작성하지 않는다.
- 새로 생성되는 node에만 canonicalization을 적용한다.
- 과거 상세 페이지는 기존 key로 계속 렌더링한다.
- 새로운 date suffix 때문에 기존 Sheets key와 달라질 가능성은 기존 30일 `event_fingerprint`로 보완한다.
- migration을 위해 과거 Sheets 행을 일괄 수정하지 않는다.

### 7.4 필수 테스트

- `../index`
- `../../outside`
- `/tmp/escaped`
- `C:\\temp\\escaped`
- NUL 포함 문자열
- 공백과 hyphen이 섞인 정상 문자열
- 200자 이상 문자열
- 빈 event key
- 2026-07-17 기사 + 모델 suffix `_2024`
- 정상 기존 key가 불필요하게 hash로 변하지 않음
- resolved article path가 `output/article` 밖이면 예외

### 7.5 완료 기준

- 어떤 LLM 문자열도 `output/article` 밖으로 파일을 만들 수 없다.
- 새 event key의 suffix가 기사 날짜와 일치한다.
- 기존 565개 노드 렌더 테스트가 통과한다.
- daily JSON, index link, manifest link가 동일한 canonical key를 사용한다.

---

## 8. Workstream D — Source health와 관측 가능성

### 8.1 현재 문제

`fetch_feed`는 다음을 모두 `[]`로 바꾼다.

- 실제 빈 feed
- HTTP 403
- HTTP 404
- timeout
- parse error
- worker error

따라서 `30/44 empty`가 무엇을 의미하는지 코드가 설명하지 못한다.

### 8.2 source 결과 모델

`pipeline/sources/rss.py`에 다음과 같은 결과를 추가한다.

```python
class SourceStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    HTTP_403 = "http_403"
    HTTP_404 = "http_404"
    HTTP_OTHER = "http_other"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    WORKER_ERROR = "worker_error"

@dataclass
class SourceFetchResult:
    source_name: str
    tier: str
    status: SourceStatus
    article_count: int
    articles: list[RawArticle]
```

raw exception 전체는 report에 저장하지 않는다. 로그에는 민감하지 않은 source name, status, HTTP code만 남긴다.

### 8.3 요청 정책

- 명시적 User-Agent를 보낸다.
- redirect는 표준 urllib 동작을 유지한다.
- 한 source timeout은 현재 30초에서 10~15초 범위로 줄인다.
- Tier C의 두 30초 순차 timeout이 전체 실행을 60초 지연하지 않도록 제한된 동시 실행을 적용한다.
- 404 source는 구현 세션에서 live 재검증 후 URL 교체 또는 제거한다.
- 403은 User-Agent로 회복되는지 source별로 검증한 뒤 유지/대체/제거한다.
- 403이라고 바로 scraper를 만들지 않는다.

### 8.4 run report

신규 `pipeline/run_report.py`를 단일 모듈로 둔다.

보고 항목:

- `run_id`
- `briefing_date`
- 최종 status
- source status별 개수와 source name
- raw / keyword / recent / URL dedup / selected / event dedup / published count
- LLM model별 attempts, successes, 429, fallback batch count
- quality gate 결과
- git/Pages/email/Sheets 단계 상태
- duration

저장 정책:

- GitHub `$GITHUB_STEP_SUMMARY`에 사람이 읽는 표를 쓴다.
- machine-readable JSON에는 allowlisted 필드만 쓴다.
- credential, prompt 원문, 기사 본문, recipient, Sheet ID, raw exception은 넣지 않는다.
- 공개 저장 여부는 구현 시 하나로 고정한다. 기본안은 `output/data/runs/{date}.json`이며 민감값이 없음을 테스트한다.

### 8.5 상태 규칙

`SUCCESS`:

- 모든 configured mandatory phase 완료
- LLM primary가 정상 call budget 안에서 완료
- source health가 degraded threshold 미만

`DEGRADED`:

- 결과 발행과 전달은 완료
- primary 429 또는 fallback batch 발생
- Tier A 비정상 비율 50% 이상
- deterministic selector fallback 사용

`NO_UPDATES`:

- source fetch와 selector는 정상
- 법률 관련성 기준을 통과한 기사가 0건
- 이메일/Sheets는 의도적으로 미실행

`FAIL`:

- source 수집 자체가 유효 데이터를 만들지 못함
- configured Sheets dedup read 실패
- primary와 fallback batch 모두 불완전
- quality gate 실패
- git push 또는 Pages deploy 실패
- configured mandatory delivery 실패

### 8.6 완료 기준

- 403, 404, timeout, empty가 서로 다른 상태로 기록된다.
- Step Summary만 읽어도 user action이 필요한 source를 알 수 있다.
- 2026-07-17 fixture를 적용하면 `DEGRADED`가 된다.
- report JSON에 secret-like field와 raw exception이 없다.
- source 한 곳의 실패가 전체 fetch worker를 중단하지 않는다.

---

## 9. Workstream E — 발행과 전달의 경계

### 9.1 목표 파일

신규 후보:

- `pipeline/run_manifest.py`
- `scripts/deliver_existing.py`
- `tests/test_run_manifest.py`
- `tests/test_delivery_idempotency.py`

수정 후보:

- `main.py`
- `pipeline/admin/sheets.py`
- `pipeline/deliver/mailer.py`
- `.github/workflows/briefing.yml`
- `pipeline/config.py`

### 9.2 run manifest

생성 결과의 불변 manifest 예시:

```json
{
  "schema_version": 1,
  "run_id": "briefing-2026-07-20",
  "briefing_date": "2026-07-20",
  "item_count": 7,
  "daily_data_path": "output/data/daily/2026-07-20.json",
  "content_sha256": "...",
  "generation_status": "ready",
  "created_at": "2026-07-20T01:10:00Z"
}
```

manifest 생성 후 daily JSON 내용이 바뀌면 delivery를 거부한다.

### 9.3 delivery receipt

```json
{
  "schema_version": 1,
  "run_id": "briefing-2026-07-20",
  "content_sha256": "...",
  "pages": "completed",
  "email": "completed",
  "sheets": "completed",
  "completed_at": "2026-07-20T01:15:00Z"
}
```

recipient나 credential 식별자는 넣지 않는다.

### 9.4 CLI 분리

권장 CLI:

```bash
# 생성만. 외부 전달 없음.
python main.py --delivery none

# 기존 날짜의 생성물을 배포 후 전달.
python scripts/deliver_existing.py \
  --date 2026-07-20 \
  --run-id briefing-2026-07-20
```

기존 `--dry-run`과 `--sample-data`는 유지한다. `--delivery none`과 의미가 겹치지 않도록 최종 CLI 이름은 구현 세션에서 한 번 정리하고 README를 갱신한다.

### 9.5 workflow 순서

```yaml
steps:
  - checkout
  - setup Python
  - install locked dependencies
  - run pytest
  - generate with delivery disabled
  - commit and push generated data
  - configure Pages
  - upload Pages artifact
  - deploy Pages
  - deliver existing run
  - commit delivery receipt
  - write Step Summary
```

규칙:

- `web_only=true`이면 deliver step을 실행하지 않는다.
- `render_date`이면 기존 파일만 렌더하고 기본적으로 전달하지 않는다.
- `force_delivery`는 기본값 `false`다.
- Pages deploy가 실패하면 이메일과 Sheets step은 실행되지 않는다.
- Sheets가 configured 상태에서 실패하면 exit code가 0이면 안 된다.
- email 성공, Sheets 실패는 receipt에 partial 상태로 기록하고 job을 실패 처리한다.
- partial/ambiguous run은 자동 재전달하지 않는다.

### 9.6 dedup 정책

- URL/event fingerprint dedup은 committed daily manifest를 기준으로 유지한다.
- Sheets는 보조적인 human-admin authority 역할을 계속한다.
- generation 중 dedup candidate는 생성할 수 있지만 외부 전달 완료로 오인하지 않는다.
- Pages 실패 후 다음 실행은 committed daily JSON을 다시 렌더할 수 있어야 한다.
- 실패한 과거 날짜의 전달은 `deliver_existing.py`를 사용하고 명시적 승인을 요구한다.

### 9.7 완료 기준

- workflow 그래프에서 Pages deploy가 email/Sheets보다 앞에 있다.
- Pages 실패 mock에서 email과 Sheets 호출이 0회다.
- 동일 완료 `run_id` 재실행에서 email과 Sheets 호출이 0회다.
- hash가 다른 동일 run_id는 충돌로 중단한다.
- Sheets append 실패가 workflow 실패로 전파된다.
- partial delivery 상태가 Step Summary에 표시된다.
- `web_only`와 `render_date`는 이메일을 보내지 않는다.

---

## 10. Workstream F — 의존성과 CI gate

### 10.1 현재 문제

- 모든 dependency가 `>=` 하한만 갖는다.
- 예약 실행마다 최신 resolver 결과가 설치된다.
- workflow가 pytest 없이 바로 production side effect를 실행한다.
- SDK release가 예약 실행 당일 처음 검증될 수 있다.

### 10.2 구현 방향

최소 파일 구조:

```text
requirements.txt       # 사람이 관리하는 direct dependencies
requirements.lock      # Python 3.11 clean environment에서 검증한 전체 고정 버전
.github/workflows/test.yml
```

정책:

- production은 `pip install -r requirements.lock`을 사용한다.
- lock 갱신은 별도 변경으로 수행한다.
- lock 갱신 PR에서 pytest와 sample-data integration을 통과해야 한다.
- 예약 workflow에서도 production 실행 전에 pytest를 다시 수행한다.
- `pip install --upgrade pip` 자체가 필요하면 pip 버전도 workflow에서 고정하거나 검증된 범위로 둔다.

### 10.3 별도 test workflow

`.github/workflows/test.yml`:

- trigger: `pull_request`, `push`
- data-only bot commit에는 다시 실행되지 않도록 `output/data/**`를 `paths-ignore` 처리
- permissions: `contents: read`
- secrets 불필요
- Python 3.11
- locked dependencies 설치
- `python -m pytest -q`
- `python main.py --dry-run --sample-data`
- output safety test

production workflow:

- 기존 schedule/dispatch 유지
- 같은 lock 사용
- pytest 통과 후에만 live pipeline 실행

### 10.4 완료 기준

- clean Python 3.11 환경에서 lock install이 성공한다.
- PR workflow는 secrets 없이 통과한다.
- pytest 실패 시 production pipeline step이 실행되지 않는다.
- dependency를 임의 최신 버전으로 올려도 lock이 바뀌지 않으면 예약 실행 환경이 바뀌지 않는다.

---

## 11. 구현 세션 계획

### Session 1 — Security boundary와 CI safety net

범위:

- `event_key` canonicalization
- article path containment
- schema required + pub_date 전달
- event key/파일 경로 테스트
- 별도 test workflow 추가
- dependency lock 생성

이유: 외부 입력이 파일 경로가 되는 문제를 먼저 막고, 이후 변경을 보호할 CI를 만든다.

필수 검증:

```bash
python3 -m pytest -q
python main.py --dry-run --sample-data
python scripts/render_existing.py --date <existing-date>
```

이 세션에서는 live API, 이메일, Sheets를 사용하지 않는다.

### Session 2 — Batch intelligence와 rate-limit 처리

범위:

- batch classification
- batch summarization
- item_id 검증
- real timeout
- RetryInfo 처리
- shared rate-limit gate
- fallback batch
- LLM metrics

필수 검증:

- 정상 10건 call count 3
- summary split call count 4
- primary 429 fixture
- fallback fixture
- missing/duplicate/unknown ID fixture
- 전체 pytest

이 세션에서는 실제 무료 API 호출을 기본 검증으로 요구하지 않는다. live canary는 Session 6에서 별도 승인 후 한다.

### Session 3 — Legal relevance와 가변 발행 수

범위:

- selector up-to-N
- legal_hook schema
- no backfill
- deterministic safe fallback
- game/legal signal 분리
- `NO_UPDATES`
- quality tests

필수 검증:

- AI-only 제외 fixture
- AI 법률분쟁 포함 fixture
- 0, 3, 7, 10건 결과
- selector failure 시 DEGRADED
- 이메일이 0건일 때 호출되지 않음

### Session 4 — Source health와 run report

범위:

- SourceStatus/SourceFetchResult
- User-Agent
- timeout 조정
- Tier C 제한 동시 실행
- Step Summary
- sanitized JSON report
- SUCCESS/DEGRADED/NO_UPDATES/FAIL 결정 함수

필수 검증:

- 403/404/timeout/empty 분리
- raw exception 비노출
- 2026-07-17 상태 fixture는 DEGRADED
- one-source failure isolation

source URL 변경은 live 검증된 항목만 별도 작은 diff로 포함한다.

### Session 5 — Generate / Publish / Deliver 분리

범위:

- run manifest
- content hash
- delivery script
- delivery receipt
- Sheets 실패 전파
- workflow 단계 재배치
- `force_delivery`/`web_only`/`render_date` 계약

필수 검증:

- Pages 실패 시 외부 전달 0회
- 동일 run_id 중복 전달 0회
- partial failure 상태
- web-only 무전달
- 전체 pytest와 workflow syntax

### Session 6 — 문서화, canary, 운영 확인

범위:

- README pipeline/CLI/상태 의미 갱신
- `TODOS.md`의 기존 parallelization 항목 정리
- 운영 runbook 작성
- GitHub Step Summary 시각 확인
- Pages desktop/mobile 기본 확인

검증 순서:

1. 로컬 전체 테스트
2. GitHub test workflow
3. manual `web_only=true` canary
4. public page와 run report 확인
5. 별도 사용자 승인 후에만 실제 이메일/Sheets가 포함된 full run

full run 전 중단 조건:

- primary 호출 예산이 4회를 초과
- event key safety test 실패
- selected item에 legal hook 누락
- run status가 FAIL
- Pages 배포 전 delivery step 실행 가능
- 수신자 또는 credential이 report/log에 노출

---

## 12. 테스트 매트릭스

| 계층 | 테스트 | 필수 결과 |
|---|---|---|
| Unit | event key traversal/absolute path | 안전한 hash fallback 또는 명시적 거부 |
| Unit | event year canonicalization | pub_date의 연도/분기와 일치 |
| Unit | batch response reorder | input 순서로 정확히 복원 |
| Unit | batch missing/duplicate ID | 누락 복구 또는 quality failure |
| Unit | RetryInfo 429 | 1/2초 retry 없음 |
| Unit | circuit gate | open 후 primary 재호출 없음 |
| Unit | relevance AI-only | 제외 |
| Unit | relevance AI litigation | 포함 가능 |
| Unit | source status | 403/404/timeout/empty 구분 |
| Unit | run status | 각 enum 결정이 deterministic |
| Unit | delivery idempotency | 완료 run 재전달 없음 |
| Integration | sample-data dry-run | 외부 side effect 없이 site 생성 |
| Integration | historical render | 기존 daily JSON 565개 호환 |
| Integration | mocked 10-item run | primary 3~4 calls, 0~10 nodes |
| Workflow | PR test | secrets 없이 통과 |
| Workflow | production test failure | pipeline/delivery 미실행 |
| Workflow | Pages failure | email/Sheets 미실행 |
| Canary | web_only | 공개 페이지 배포, 무전달 |
| Live | approved full run | deploy 후 email/Sheets, receipt 완료 |

---

## 13. 운영자용 GitHub Summary 예시

```text
Game Legal Briefing — briefing-2026-07-20

Status: DEGRADED
Published: 7 items (maximum 10)

Sources
- OK: 26
- Empty: 4
- HTTP 403: 8
- HTTP 404: 2
- Timeout: 1

LLM
- Gemini 3.5 Flash: 3 attempts / 2 successes / 1 rate limit
- Gemini 3.1 Flash-Lite: 1 fallback batch / 1 success

Stages
- Generate: completed
- Git push: completed
- Pages: completed
- Email: completed
- Sheets: completed

Action required
- Verify or replace the two HTTP 404 feed URLs.
- Primary model used fallback; no immediate rerun required.
```

`DEGRADED`는 실패가 아니다. 결과는 발행·전달됐지만 품질 또는 커버리지 저하가 있었음을 뜻한다. 이 구분이 현재 사용자가 느끼는 “초록불인데 fail이 많음” 문제를 해결한다.

---

## 14. 위험과 대응

| 위험 | 가능성 | 영향 | 대응 |
|---|---|---|---|
| 10건 summary batch가 응답 크기 한도를 넘음 | 중 | 중 | production-shaped fixture, 필요 시 5건씩 2회 |
| batch 일부 ID 누락 | 중 | 높음 | ID 완전성 검증, 누락분만 fallback 1회 |
| 새 event key가 기존 Sheets key와 달라짐 | 중 | 중 | 30일 event fingerprint 병행, 과거 데이터 무수정 |
| source User-Agent로도 403 지속 | 높음 | 낮음~중 | source별 교체/제거, scraper는 별도 범위 |
| email 성공 후 receipt 전 실패 | 낮음 | 중 | ambiguous 상태 자동 재전달 금지, 수동 확인 |
| lock 파일이 macOS와 Linux에서 다르게 동작 | 중 | 중 | Python 3.11 Linux clean environment에서 생성·검증 |
| Step Summary가 성공처럼 오인됨 | 중 | 중 | status enum과 action required 문구 고정 |
| NO_UPDATES가 수집 실패를 숨김 | 낮음 | 높음 | source health 정상일 때만 NO_UPDATES 허용 |

---

## 15. 롤백 전략

- 각 Session은 별도 커밋으로 유지한다.
- 문제 발생 시 해당 Session 커밋만 `git revert`할 수 있어야 한다.
- 기존 daily JSON schema를 유지해 코드 롤백 후에도 저장 데이터를 읽을 수 있게 한다.
- event key는 기존 저장값을 재작성하지 않는다.
- live delivery 문제가 있으면 workflow dispatch의 `web_only=true`로 즉시 전환한다.
- Pages는 `render_date`로 기존 정상 daily JSON을 재렌더할 수 있어야 한다.
- fallback model 설정은 제거하지 않는다.
- rollback을 위해 두 개의 장기 코드 경로를 유지하는 feature flag는 만들지 않는다.

---

## 16. 문서와 운영 변경

구현 완료 시 갱신할 문서:

- `README.md`
  - 실제 pipeline 순서
  - 최대 10건 정책
  - 상태 enum
  - generate/deliver CLI
  - free-tier call budget
- `docs/ko/README.md`
  - 한국어 운영 설명 동기화
- `TODOS.md`
  - 기존 “LLM call parallelization” 항목 제거 또는 batch architecture로 교체
- 신규 `docs/operations-runbook.md`
  - DEGRADED 해석
  - 404 source 조치
  - Pages 실패 복구
  - ambiguous delivery 확인
  - force delivery 승인 절차

README의 현재 pipeline 도식은 `classification + summary` 병렬/개별 호출과 email-before-deploy 구조를 반영하지 못하므로 구현 완료 후 반드시 수정한다.

---

## 17. 최종 완료 정의

다음 조건을 모두 만족해야 이 개선 프로젝트를 완료로 본다.

- [ ] 전체 pytest 통과
- [ ] PR/test workflow 통과
- [ ] production workflow가 locked dependencies 사용
- [ ] production 실행 전 pytest 수행
- [ ] 10건 기준 primary 호출 3~4회
- [ ] RetryInfo-aware 429 처리
- [ ] configured timeout 실제 적용
- [ ] selector가 0~10건 반환
- [ ] AI-only 품질 fixture 차단
- [ ] `event_key` path traversal 불가능
- [ ] 새 event key 날짜 suffix가 pub_date와 일치
- [ ] 기존 565개 node 렌더 호환
- [ ] source status 세분화
- [ ] GitHub Step Summary에 최종 상태와 action required 표시
- [ ] Pages deploy가 email/Sheets보다 먼저 실행
- [ ] 동일 완료 run_id 자동 재전달 차단
- [ ] Sheets configured failure가 workflow 실패로 전파
- [ ] web_only canary 성공
- [ ] public page와 manifest 검증
- [ ] 실제 email/Sheets full run은 사용자 승인 후 1회 검증
- [ ] secret/recipient/raw prompt가 report에 없음

---

## 18. 구현자가 임의로 바꾸면 안 되는 결정

- 비용을 이유로 paid provider를 기본값으로 바꾸지 않는다.
- 정상 경로의 primary는 Gemini 3.5 Flash다.
- Flash-Lite는 fallback이다.
- `top_n`을 채우기 위해 법률성이 낮은 기사를 backfill하지 않는다.
- existing daily JSON 전체를 마이그레이션하지 않는다.
- Pages 배포 전에 이메일을 보내지 않는다.
- ambiguous delivery를 자동 재전송하지 않는다.
- run report에 credential, recipient, prompt/body 원문을 넣지 않는다.
- UI 리디자인이나 신규 제품 기능을 이 remediation에 섞지 않는다.

이 결정의 변경이 필요하면 코드부터 바꾸지 말고, 근거·영향·대안을 이 문서에 추가하고 사용자 승인을 받은 뒤 진행한다.
