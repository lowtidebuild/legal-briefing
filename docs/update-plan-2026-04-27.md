# Update Plan — 2026-04-27

**상태**: VERIFIED DRAFT
**브랜치**: main
**검증 일시**: 2026-04-27 KST
**범위**: v2 MVP의 증분 업데이트. 아키텍처 재설계나 대규모 데이터 모델 변경은 별도 PR로 분리한다.

---

## 0. 검증 요약

Claude Code 초안의 큰 방향은 맞다. Cooley Newsroom은 법률 인사이트 피드라기보다 PR/딜 announcement 피드에 가깝고, selector 프롬프트가 특정 로펌명을 직접 호명해 LLM 선택 편향을 만든다.

다만 초안 그대로 구현하면 위험한 부분도 있다.

1. JD Supra URL 3개가 잘못되었거나 미검증 상태였다. `https://www.jdsupra.com/topics/.../feed/` 형식 대신 공식 RSS syndication URL 또는 `_rss/` topic URL을 써야 한다.
2. `event_key` 결정론화는 맞는 방향이지만 P0로 넣기에는 위험하다. 현재 `event_key`는 article page 파일명과 Sheets dedup 키로 쓰이고 있어 기존 30일 데이터와 호환 전략이 필요하다.
3. `pipeline.max_per_domain` 같은 새 설정은 현재 [pipeline/config.py](../pipeline/config.py)에 존재하지 않는다. config dataclass와 테스트를 같이 바꿔야 한다.
4. `pub_date == ""` 백도어는 실제로 존재한다. 다만 RSS뿐 아니라 Tier C scraper도 빈 날짜를 만들 수 있으므로 전 소스 공통 정책으로 고쳐야 한다.
5. 본문 fetch, Gemini schema, Claude tool use는 유효한 개선 후보지만 외부 의존과 SDK 버전 리스크가 있어 P0에서 제외한다.

**현재 출력 베이스라인** (`output/data/daily/*.json`, 2026-03-02~2026-04-22):

| 지표 | 값 |
|---|---:|
| 총 게시 노드 | 204 |
| Cooley - Media (Newsroom) | 17건 (8.3%) |
| 최다 source | The Register - Security 32건, GamesIndustry.biz 30건, PC Gamer 22건 |
| 최다 category | AI_EMERGING 47건, PRIVACY_SECURITY 45건 |
| 중복 `event_key` | 0건 |
| 빈 `pub_date` 게시 노드 | 2건 |

해석: Cooley가 수량상 압도적 1위는 아니지만, 실제 제목 샘플이 FTC/FCC/CCPA/USPTO/딜/수상 언급 중심이라 "스폰서 받은 것 같은" 인상은 충분히 재현된다. 즉 문제는 단순 빈도보다 **피드 성격 + 프롬프트 편향**의 결합이다.

---

# Section A. P0 — 출처 다양화와 편향 제거

## A-1. Cooley Media 피드 교체

**현상**: [config.yaml](../config.yaml)에 `Cooley - Media (Newsroom)`가 tier_a로 들어 있다. 이 피드는 분석보다 자기 홍보성 newsroom 항목이 많아 게임 법무 브리핑의 신뢰도를 떨어뜨린다.

**결정**: `Cooley - Media (Newsroom)`는 제거한다. Cooley를 완전히 배제한다는 뜻은 아니고, JD Supra 등 practitioner aggregate를 통해 관련성 있는 글만 다시 들어오게 한다.

**검증된 대체 피드**:

| 이름 | URL | tier | 검증 |
|---|---|---|---|
| JD Supra - Privacy | `https://www.jdsupra.com/resources/syndication/docsRSSfeed.aspx?ftype=Privacy&premium=1` | tier_a | HTTP 200, `application/rss+xml` |
| JD Supra - Intellectual Property | `https://www.jdsupra.com/resources/syndication/docsRSSfeed.aspx?ftype=IntellectualProperty&premium=1` | tier_a | HTTP 200, `application/rss+xml` |
| JD Supra - Antitrust & Trade Regulation | `https://www.jdsupra.com/resources/syndication/docsRSSfeed.aspx?ftype=AntitrustTradeRegulation&premium=1` | tier_a | HTTP 200, `application/rss+xml` |
| Gamma Law - Insights | `https://gammalaw.com/feed/` | tier_a | HTTP 200, `application/rss+xml` |
| Pillsbury - Internet & Technology Law | `https://www.internetandtechnologylaw.com/feed/` | tier_a | HTTP 200, `application/rss+xml` |
| IPWatchdog | `https://ipwatchdog.com/feed/` | tier_b | HTTP 200, `application/rss+xml` |

주의:

- Claude 초안의 `https://www.jdsupra.com/topics/privacy-data-security/feed/` 형식은 사용하지 않는다.
- JD Supra topic page의 `_rss/` URL도 동작하지만, 위 syndication URL이 더 명확하다.
- "Pillsbury - Video Game Law Blog"라는 명칭은 현재 피드 검증 기준으로 부정확하다. 실제 feed는 Pillsbury의 Internet & Technology Law 쪽으로 명명한다.
- JD Supra는 세 피드 모두 같은 도메인이므로 A-3의 도메인 캡이 필수다.

## A-2. Selector 프롬프트의 특정 로펌 편향 제거

**현상**: [pipeline/intelligence/selector.py](../pipeline/intelligence/selector.py)는 Cooley, DLA Piper, Norton Rose를 HIGH VALUE 예시로 직접 호명한다. 이 문장은 신규 practitioner source를 상대적으로 불리하게 만들고, 특정 로펌 홍보처럼 보이는 출력을 강화한다.

**수정 방향**:

```python
SELECTOR_PROMPT = """You are a legal analyst specializing in the game industry.

From the article list below, select EXACTLY {top_n} entries most relevant to game law,
regulation, platform rules, privacy, antitrust, consumer protection, or policy.

Selection criteria, in priority order:
1. Direct game industry impact: games, esports, virtual goods, in-game purchases,
   age rating, game platforms, app stores, online safety, monetization, or player data.
2. Regulatory/legal substance over general news: enforcement actions, legislation,
   litigation, official guidance, platform policy, security incidents, or practitioner analysis.
3. Source diversity: use different outlets across trade press, practitioner publications,
   regulators, tech policy, and security press.
4. No single domain should account for more than {max_per_domain} of {top_n}
   unless there are not enough relevant alternatives.

Practitioner analysis and regulatory body announcements are HIGH VALUE when they tie
to the topics above. Generic law firm deal announcements, awards, hires, and marketing
posts are LOW VALUE unless they directly affect game industry regulation.

You MUST return exactly {top_n} indices.

Articles:
{articles_text}

Return JSON only:
{{"selected_indices": [0, 2, 4, ...]}}"""
```

구현 메모:

- `max_per_domain`을 prompt 변수로 넣으려면 [pipeline/config.py](../pipeline/config.py)의 `PipelineConfig`에 필드를 추가한다.
- description 길이는 P0에서는 유지해도 된다. selector input ranking을 도입하는 P1에서 60~120자 단축을 같이 실험한다.

## A-3. 도메인 캡을 코드에서 강제

프롬프트 가이드만으로는 부족하다. [pipeline/intelligence/selector.py](../pipeline/intelligence/selector.py)에 후처리 캡을 추가한다.

권장 구현:

```python
from collections import Counter
from urllib.parse import urlparse


def _domain_of(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _enforce_domain_cap(
    selected: list[RawArticle],
    pool: list[RawArticle],
    top_n: int,
    max_per_domain: int,
) -> list[RawArticle]:
    capped: list[RawArticle] = []
    domain_counts: Counter[str] = Counter()
    selected_ids: set[int] = set()

    for article in selected:
        domain = _domain_of(article.url)
        if domain_counts[domain] >= max_per_domain:
            continue
        domain_counts[domain] += 1
        capped.append(article)
        selected_ids.add(id(article))

    for article in pool:
        if len(capped) >= top_n:
            break
        if id(article) in selected_ids:
            continue
        domain = _domain_of(article.url)
        if domain_counts[domain] >= max_per_domain:
            continue
        domain_counts[domain] += 1
        capped.append(article)
        selected_ids.add(id(article))

    return capped[:top_n]
```

`select_top_articles(..., max_per_domain=2)`를 기본으로 둔다. `pipeline.max_per_domain`이 없으면 기본값 2를 사용한다.

테스트:

- 같은 도메인 5개를 LLM이 선택해도 결과는 최대 2개만 남는다.
- fill 후보가 다른 도메인에서 보충된다.
- 후보가 부족하면 `top_n`보다 적게 반환될 수 있음을 허용할지, 아니면 cap을 완화할지 정책을 명확히 한다. P0 기본은 **후보 부족 시 cap 완화 없이 적게 반환 허용**보다 **기존 동작 유지**가 안전하므로, 마지막 fallback에서 cap을 한 번 완화해 `top_n`을 채운다.

## A-4. 날짜 없는 기사 정책 수정

**현상**: [pipeline/sources/filters.py](../pipeline/sources/filters.py)의 `recency_filter`는 `pub_date`가 빈 기사를 항상 통과시킨다.

**수정 방향**:

1. fetch 이후 recency 이전에 전체 source 공통으로 빈 날짜를 `today`로 채운다.
2. `recency_filter`에서는 `or not article.pub_date`를 제거한다.
3. 날짜 문자열 비교 전 `YYYY-MM-DD` 형식만 통과시키고, 이상한 값은 today로 정규화한다.

권장 위치:

- `pipeline/sources/filters.py`에 `normalize_pub_dates(articles, default_date)` helper 추가.
- [main.py](../main.py)에서 keyword filter 직후, recency filter 직전에 호출.

이 방식은 RSS와 Tier C 모두를 커버한다.

---

# Section B. P1 — 품질과 비용 개선

## B-1. Selector 입력 순서 개선

**현상**: 현재 selector는 `max_input_chars`에 닿으면 원본 피드 순서대로 잘린다. 피드 순서가 사실상 우선순위가 되는 구조다.

**수정 방향**:

- `keyword_filter`는 기존 API를 유지한다.
- 새 helper `score_articles_by_keyword(articles, keywords)`를 추가해 selector 직전에만 사용한다.
- 점수 내림차순 + 도메인 round-robin으로 selector 입력 순서를 재배치한다.
- 잘림이 발생하면 `Selector input truncated: {original} -> {visible}` 로그를 남긴다.

P0 도메인 캡과 결합하면 JD Supra 같은 고볼륨 aggregate가 입력과 출력 양쪽에서 과점하지 못한다.

## B-2. Classify → event dedup → summarize 순서로 변경

현재 흐름:

```text
selector -> classify -> summarize -> assemble -> event_key dedup
```

권장 흐름:

```text
selector -> classify -> event_key/fingerprint dedup -> summarize survivors -> assemble
```

효과:

- 같은 사건을 다룬 여러 기사에 대해 summary 호출을 줄인다.
- dedup으로 버릴 기사에 한국어 요약 비용을 쓰지 않는다.

주의:

- 이 작업은 B-3의 event key 호환 전략과 같이 설계해야 한다.
- `assemble_node`가 summary를 요구하므로, 중간 단계용 lightweight 구조체나 `(article, classification)` pair list를 둔다.

## B-3. Event key 결정론화는 migration 포함으로 처리

Claude 초안의 문제 지적은 맞다. LLM이 자유 텍스트로 만드는 `event_key`는 같은 사건에도 흔들릴 수 있다. 하지만 즉시 `event_key`를 hash로 바꾸면 다음 문제가 생긴다.

- 기존 Sheets의 30일 `event_key`와 새 key가 매칭되지 않는다.
- [pipeline/render/site.py](../pipeline/render/site.py)는 `event_key`를 article page 파일명으로 쓴다.
- 기존 output에는 human-readable key와 hash key가 섞여 있다.

권장 설계:

1. P1에서는 `event_fingerprint` 개념을 먼저 도입한다. dedup에는 fingerprint를 쓰고, article URL slug는 기존 `event_key`를 유지한다.
2. `DedupEntry`에 `event_fingerprint`를 optional로 추가하되, 기존 `event_key`도 30일 retention 동안 계속 읽는다.
3. 30일이 지난 뒤 `event_key` 자체를 deterministic slug/hash로 통합할지 결정한다.

fingerprint 후보:

```python
def compute_event_fingerprint(
    jurisdiction: str,
    actors: list[str],
    object_: str,
    action: str,
    year_bucket: str,
) -> str:
    ...
```

`year_bucket`은 article `pub_date`에서 `YYYYqN`으로 만든다. 날짜가 없으면 A-4에서 이미 today로 채워져 있어야 한다.

## B-4. 본문 fetch는 feature flag로 도입

본문 fetch는 요약 품질에 도움이 되지만, 다음 리스크가 있다.

- `readability-lxml` 의존성 추가
- 사이트별 차단/느린 응답
- full body를 LLM에 넣을 때 비용 증가

권장 정책:

- `pipeline.fetch_body_for_selected: false` 기본값으로 추가한다.
- top_N 선택 이후, summarize 생존 기사에 대해서만 fetch한다.
- timeout 8~12초, max chars 6000~8000.
- 실패 시 RSS description으로 graceful fallback.

P0가 안정화된 뒤 실제 샘플 1주일치로 품질 차이를 보고 켠다.

## B-5. 병렬화

두 병목은 독립적으로 개선 가능하다.

1. RSS fetch 병렬화: [pipeline/sources/rss.py](../pipeline/sources/rss.py)의 `fetch_all_feeds`에 `ThreadPoolExecutor(max_workers=8)` 적용.
2. LLM 호출 병렬화: B-2 순서 변경 후 classify와 summarize 각각에 `max_workers=4` 적용.

주의:

- LLM 병렬화는 rate limit 관측 후 기본값을 정한다.
- dry-run/sample-data 경로에서도 deterministic하게 테스트되어야 한다.

---

# Section C. P2 — 운영 안정성 및 출력 품질

## C-1. Sheets fail-safe

현재 [pipeline/admin/sheets.py](../pipeline/admin/sheets.py)는 Sheets 읽기 실패와 미설정을 모두 `set()`으로 반환한다. 이러면 Sheets API 장애 때 "과거 게시물을 모르는 상태"로 발송될 수 있다.

권장 정책:

- credentials/spreadsheet id가 없으면 `set()` 반환: 로컬/미설정 모드.
- credentials가 있는데 API 실패면 `None` 반환.
- 운영 모드에서 `None`이면 발송과 Sheets sync를 중단하고 `SystemExit(3)`.
- dry-run에서는 경고만 남기고 진행.

## C-2. 헬스체크

운영 모드에서 다음 조건이면 실패로 처리하거나 운영자 알림을 보낸다.

- keyword filter 이후 article 수가 10 미만
- tier_a fetch 실패율 50% 이상
- 최종 nodes가 0개

빈 브리핑이 조용히 지나가는 것을 막는 목적이다.

## C-3. `time_hint` 처리

`time_hint`는 현재 모델에는 있으나 Sheets와 템플릿에 거의 노출되지 않는다. 추출 비용이 이미 들어가므로 제거보다 노출이 낫다.

권장:

- article card/detail에 짧은 metadata로 노출.
- Sheets header에 `time_hint` 추가.
- 값이 `current`, `ongoing`, `months`처럼 낮은 정보량이면 숨긴다.

## C-4. 한국어 source 제목 번역 우회

한국어 source는 `title_ko = article.title`로 둔다. summary만 생성한다.

초기 source set:

```python
KOREAN_SOURCES = {
    "IT Chosun",
    "ZDNet Korea",
    "ETNews",
    "게임메카",
    "디스이즈게임",
    "인벤",
    "게임톡",
    "DDaily",
    "GameChosun",
    "문화체육관광부",
    "게임물관리위원회",
    "공정거래위원회",
}
```

## C-5. `_build_provider` 정리

[main.py](../main.py)의 `_build_provider`와 [pipeline/llm/__init__.py](../pipeline/llm/__init__.py)의 `create_provider`가 fallback 책임을 나눠 갖고 있다. 기능상 급하지는 않지만, `offline_fallback` 옵션을 `create_provider`로 흡수하면 main이 간단해진다.

---

# Section D. P3 — 후순위 후보

다음은 좋은 개선이지만 즉시 사용자 피드백을 해결하지 않는다.

| 항목 | 이유 |
|---|---|
| Gemini `response_schema` | SDK/API 버전 검증 필요. prompt 토큰 절감은 가능하지만 P0 리스크 대비 효과가 작음 |
| Claude tool-use JSON 강제 | fallback 안정성 개선 후보. 현재 provider와 Anthropic SDK 버전 확인 후 진행 |
| article page idempotent render | 커밋 노이즈 감소. 기능 영향은 작음 |
| `docs/sources-backlog.md` 자동 생성 | Tier C 운영 가시성 개선. scraper 확장 시 함께 처리 |
| email preview artifact | DX 개선. 운영 품질 문제 발견 시 우선순위 상승 |
| `is_primary` 제거 | JSON schema churn이 있으므로 이벤트 클러스터링 방향이 정해질 때까지 보류 |

---

# 권장 PR 순서

## PR #1 — 사용자 피드백 직접 대응 (P0)

포함:

- `Cooley - Media (Newsroom)` 제거
- 검증된 JD Supra/Gamma/Pillsbury/IPWatchdog 피드 추가
- selector 프롬프트에서 특정 로펌명 제거
- selector domain cap 추가
- `pipeline.max_per_domain` config 추가
- 빈 `pub_date` 공통 정규화 + recency 백도어 제거
- 관련 unit test 추가

검증:

```bash
pytest tests/test_config.py tests/test_filters.py tests/test_rss.py tests/test_selector.py
python main.py --dry-run
jq -r '.[] | .source' output/data/daily/*.json | sort | uniq -c | sort -nr
```

합격 기준:

- prompt에 `Cooley`, `DLA Piper`, `Norton Rose` 문자열이 없다.
- `config.yaml`에 Cooley Media 피드가 없다.
- dry-run 결과에서 동일 도메인이 `pipeline.max_per_domain`을 초과하지 않는다. 후보 부족 시에는 로그로 cap 완화 여부가 보여야 한다.
- 빈 날짜 기사가 recency filter를 무조건 통과하지 않는다.

## PR #2 — 효율과 dedup 품질 (P1)

포함:

- selector 입력 ranking/round-robin
- classify → event dedup → summarize 순서 변경
- `event_fingerprint` migration 설계 및 구현
- RSS fetch 병렬화
- LLM 호출 병렬화
- 본문 fetch feature flag 추가

합격 기준:

- published node당 LLM 호출 수 감소
- wall time 감소
- 기존 30일 data와 Sheets dedup 호환 유지

## PR #3 — 운영 안정성 및 출력 polishing (P2)

포함:

- Sheets fail-safe
- health check
- `time_hint` 노출
- 한국어 title translation short-circuit
- provider factory 정리

## PR #4 — 후순위 DX/SDK 개선 (P3)

포함:

- Gemini schema spike
- Claude tool-use JSON spike
- idempotent render
- source backlog 문서화
- email preview

---

# 정량 지표

PR별로 다음 지표를 기록한다.

| 지표 | 측정 | 목표 |
|---|---|---|
| 단일 source 점유율 | 30일 source count / total | 어떤 source도 25% 이하 |
| 단일 domain 점유율 | 30일 URL domain count / total | 어떤 domain도 25% 이하 |
| 동일 event 재게시 | 30일 window 내 event fingerprint 중복 | 0건 |
| category 편중 | 30일 category count / total | 어떤 category도 50% 이하 |
| LLM 호출 수 / 게시 노드 | selector + classify + summarize calls / nodes | PR #2 후 현재 대비 감소 |
| wall time | dry-run 1회 | PR #2 후 현재 대비 감소 |
| 요약 길이 | 3줄 합산 한국어 글자 수 | 100~250자 권장 |

---

# Out of Scope

- v2 아키텍처 재설계
- multi-agent pipeline 도입
- Tier C 신규 scraper 대량 추가
- Jurisdiction Pulse 대시보드
- 영문 요약 추가
- 디자인 전면 개편

---

# 기본 결정값

사용자 추가 확인 없이 다음 기본값으로 진행한다.

| 항목 | 결정 |
|---|---|
| `pipeline.max_per_domain` | 2 |
| 본문 fetch | 기본 off, P1 feature flag |
| category cap | P1 이후 필요 시 도입. P0 제외 |
| Sheets 장애 정책 | 운영 모드에서는 발송 중단, dry-run은 경고 |
| `time_hint` | P2에서 노출 |
| `is_primary` | 유지. 제거 보류 |
