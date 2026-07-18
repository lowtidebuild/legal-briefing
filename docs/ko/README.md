<div align="center">

# Game Legal Briefing

**게임 산업 규제 동향을 자동으로 수집·분류·발송하는 오픈소스 브리핑 도구**

<p>
  <img src="https://img.shields.io/badge/License-Apache_2.0-1F6FEB?style=for-the-badge" alt="Apache 2.0" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/RSS-54개_피드-15803D?style=for-the-badge" alt="54 RSS feeds" />
  <img src="https://img.shields.io/badge/LLM-Gemini_3.5_Flash-8B5CF6?style=for-the-badge" alt="Gemini 3.5 Flash" />
</p>

**[브리핑 수신](#브리핑-수신)** · **[직접 운영하기](#직접-운영하기)** · **[구조](#구조)** · **[로드맵](#로드맵)**

**Language:** [English](../../README.md) | [**한국어**](README.md)

</div>

---

## 뭘 하는 프로젝트인가

게임 업계 미디어, 글로벌 로펌 블로그, 테크 정책 매체, 국내 IT 언론 등 54개 RSS 피드에서 기사를 수집합니다. 게임 법률 연결고리가 확인된 기사만 최대 10건 선별해 한국어로 구조화하고, 웹 배포가 성공한 뒤에만 이메일·Sheets 전달을 별도 실행합니다.

> [!IMPORTANT]
> 법률 자문이 아닙니다. 규제 동향 모니터링용 오픈소스 도구입니다.

## 왜 만들었나

기업용 RegTech(CUBE, Regology 등)은 은행·제약 대상이고 연 수천만 원 이상입니다. 게임 업계 법무팀이 여러 나라 규제 변화를 한눈에 볼 수 있는 도구가 없었습니다.

보통 뉴스 브리퍼는 헤드라인 + 요약에서 끝납니다. 이 프로젝트는 기사마다 **구조화된 메타데이터**를 달아줍니다:

| 항목 | 예시 |
|------|------|
| 관할권 | EU, 한국, 미국, 일본, 영국 등 |
| 카테고리 | 과금/소비자, 연령등급, 개인정보, IP, AI 등 |
| 규제 단계 | 발의 → 공개의견 → 확정 → 집행 → 소송 |
| 사건 식별자 | `eu_lootbox_transparency_directive_2026` |
| 게임 메커닉 | 루트박스, 연령등급, 데이터수집 등 |

쌓이면 쌓일수록 단순 메일링이 아니라 게임 산업 규제 아카이브가 됩니다.

---

## 브리핑 수신

**직접 운영하고 싶지 않고 브리핑만 받고 싶다면:**

매주 월·수·금 오전 10시에 이메일로 발송합니다. 수신을 원하시면 아래로 이메일 주소를 알려주세요.

- GitHub: [@lowtidebuild](https://github.com/lowtidebuild)
- 웹 아카이브: [lowtidebuild.github.io/legal-briefing](https://lowtidebuild.github.io/legal-briefing/)

다음 발송분부터 도착합니다. 무료입니다.

---

## 직접 운영하기

이 프로젝트를 fork해서 본인만의 브리핑 파이프라인을 돌리고 싶다면 아래 순서대로 하면 됩니다.

### 1. 설치

```bash
git clone https://github.com/lowtidebuild/legal-briefing.git
cd legal-briefing
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --require-hashes -r requirements.lock
```

### 2. 샘플 브리핑으로 구조 확인

API 키 없이 한번 돌려볼 수 있습니다:

```bash
python3 main.py --dry-run --sample-data --delivery none
open output/index.html
```

### 3. API 키 세팅

```bash
cp .env.example .env
```

`.env` 파일을 열고 값을 채웁니다:

| 변수 | 용도 | 필수 여부 |
|------|------|----------|
| `GOOGLE_API_KEY` | Gemini API 키 ([여기서 발급](https://aistudio.google.com/app/apikey)) | **필수** |
| `GROQ_API_KEY` | Groq API 키 (다른 프로바이더 구성 시) | 선택 |
| `ANTHROPIC_API_KEY` | Claude API 키 (이전 구성용) | 선택 |
| `SMTP_USER` | Gmail 주소 (`you@gmail.com` 전체) | 이메일 쓸 때 |
| `SMTP_PASS` | Gmail 앱 비밀번호 (16자리, 공백 포함 그대로) | 이메일 쓸 때 |
| `RECIPIENTS` | 수신자 이메일 목록 (콤마로 구분) | 이메일 쓸 때 |
| `GOOGLE_SHEETS_CREDENTIALS` | Sheets 서비스 계정 JSON | Sheets 쓸 때 |
| `GOOGLE_SHEETS_ID` | 스프레드시트 ID | Sheets 쓸 때 |

> **현재 LLM 구성은 `GOOGLE_API_KEY`만 있으면 동작합니다.** 선별·분류는 Gemini 3.5 Flash `low`, 요약은 같은 모델의 `minimal`을 쓰고, 실패하면 Gemini 3.1 Flash-Lite로 전환합니다. 무료 등급 한도를 고려해 배치 호출하며, 이메일과 Sheets는 웹 배포 뒤의 별도 단계입니다.

### 4. 실행

생성 명령은 이메일·Sheets를 절대 실행하지 않습니다:

```bash
python3 main.py --delivery none
```

생성 결과가 커밋되고 GitHub Pages 배포까지 성공하면 workflow가 해시로 고정된 결과만 전달합니다. 수동 전달은 장애 복구 작업이므로 [운영 runbook](../operations-runbook.md)을 따릅니다.

결과물:
- `output/index.html` — 최신 브리핑
- `output/archive/` — 날짜별 아카이브
- `output/article/` — 개별 기사 페이지
- `output/data/daily/*.json` — 구조화된 JSON 데이터
- `output/data/run_manifests/*.json` — 전달 대상 콘텐츠 해시
- `output/data/runs/*.json` — 민감정보 없는 실행 상태 리포트
- `output/data/delivery_receipts/*.json` — 중복 전달 방지 영수증

### 5. GitHub Actions 자동화

fork한 repo에서 자동 발송을 세팅하려면:

1. **GitHub Secrets 등록:** repo Settings → Secrets and variables → Actions → 위 환경변수를 Secret으로 추가
2. **GitHub Pages 켜기:** repo Settings → Pages → Source를 "GitHub Actions"로 선택
3. **자동 실행:** 월/수/금 오전 10:07(KST)에 자동 실행됨 (수동: Actions 탭 → Run workflow)

수동 실행 모드는 서로 분리되어 있습니다:

- `web_only=true`: 생성·웹 배포만 수행하고 이메일·Sheets는 실행하지 않음
- `render_date=YYYY-MM-DD`: 저장된 날짜만 다시 렌더링하고 수집·LLM·전달은 실행하지 않음
- `force_delivery=true`: 이미 확인한 partial 전달만 재개하며 완료 단계는 반복하지 않음

### Google Sheets 연동 (선택사항)

Sheets는 두 가지 역할을 합니다: (1) 관리자가 기사를 확인·수정·삭제하는 로그, (2) EventKey 기반 중복 제거의 기준 DB.

1. [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Library → "Google Sheets API" 사용 설정
2. IAM & Admin → Service Accounts → 계정 만들기 → Keys 탭 → JSON 다운로드
3. 스프레드시트 새로 만들고 → 서비스 계정 이메일에 편집자 권한 공유
4. GitHub Secrets에 `GOOGLE_SHEETS_CREDENTIALS` (JSON 내용 전체 붙여넣기) + `GOOGLE_SHEETS_ID` (스프레드시트 URL에서 `/d/` 뒤의 문자열) 등록

기존 아카이브를 Sheets에 한번에 넣으려면:
```bash
GOOGLE_SHEETS_CREDENTIALS='credentials.json 경로' \
GOOGLE_SHEETS_ID='스프레드시트ID' \
python scripts/backfill_sheets.py
```

### Gmail 앱 비밀번호 발급

1. [Google 계정 보안](https://myaccount.google.com/security) → 2단계 인증 켜기
2. 앱 비밀번호 만들기 → 16자리 비밀번호 복사
3. `SMTP_USER`에 Gmail 주소 전체, `SMTP_PASS`에 16자리(공백 포함) 넣기

---

## 파이프라인

```mermaid
flowchart LR
    A["54개 RSS 피드"] --> B["키워드 필터"]
    B --> B2["최신성 필터 (7일)"]
    B2 --> C["URL 중복 제거"]
    C --> D["AI 선별 (0~10건)"]
    D --> E["배치 분류 + EventKey"]
    E --> F["배치 한국어 제목 + 요약"]
    F --> G["사건 중복 제거"]
    G --> H["Daily JSON + 콘텐츠 해시"]
    H --> I["정적 사이트"]
    I --> L["GitHub Pages"]
    L --> J["중복 방지 이메일"]
    J --> K["중복 방지 Google Sheets"]
```

## 실행 상태

| 상태 | 의미 |
|---|---|
| `SUCCESS` | 소스와 주 모델이 정상 범위에서 생성 완료 |
| `DEGRADED` | 결과는 생성됐지만 소스 건강도, 429, 안전 fallback 중 확인할 항목이 있음 |
| `NO_UPDATES` | 수집·선별은 정상이지만 법률 관련성 기준을 통과한 기사가 없음. 전달 안 함 |
| `FAIL` | 필수 단계 실패. 해당 결과를 전달하면 안 됨 |

GitHub Step Summary에는 소스 상태, 단계별 건수, LLM 호출 카운터, 전달 상태와 조치사항만 표시합니다. prompt·기사 본문·수신자·credential·Sheet ID·raw exception은 기록하지 않습니다.

## 중복 제거 전략

세 단계로 같은 기사나 같은 사건이 반복 발송되는 걸 막습니다:

| 단계 | 방식 | 설명 |
|------|------|------|
| 1 | URL 해시 | 같은 URL 제거 (30일 rolling JSON 인덱스) |
| 2 | 제목 토큰 | 제목 단어 기반 유사도 (같은 기사가 다른 URL로 올라온 경우) |
| 3 | EventKey | AI가 생성한 사건 식별자 (`eu_lootbox_directive_2026`), Sheets가 기준 |

Sheets에서 EventKey를 직접 확인하고 수정할 수 있어서, AI가 다르게 생성한 키도 사람이 통합할 수 있습니다.

## 구조

```text
game-legal-briefing/
├── main.py                 # 외부 전달 없는 생성 진입점
├── config.yaml             # 설정 (54개 RSS 소스, 시크릿 없음)
├── pipeline/
│   ├── sources/            # RSS 수집, 키워드/최신성 필터
│   ├── intelligence/       # AI 선별, 분류, 요약, 중복 제거
│   ├── llm/                # 프로바이더 추상화 (Gemini 모델 폴백)
│   ├── store/              # JSON 저장, 중복 인덱스, 쿼리
│   ├── render/             # 사이트 + 이메일 렌더링 (Jinja2)
│   ├── deliver/            # Gmail SMTP 발송
│   └── admin/              # Google Sheets 동기화 + EventKey 읽기
├── templates/              # 웹 + 이메일 Jinja2 템플릿
├── static/                 # CSS (Pretendard + Noto Serif KR)
├── scripts/                # 기존 결과 전달·렌더·백필 유틸리티
├── tests/                  # pytest 테스트
└── output/                 # 생성된 사이트 + 데이터 (GitHub Pages)
```

## 테스트

```bash
python3 -m pytest -q
python3 main.py --dry-run --sample-data --delivery none --output /tmp/legal-briefing-sample
```

## 로드맵

| 단계 | 내용 |
|:-----|:-----|
| **완료** | MVP 파이프라인, 54개 피드, Gemini 무료 모델 폴백, EventKey 중복 제거, 한국어 제목, 카테고리 그룹핑, Sheets 관리, GitHub Pages, 이메일 발송 |
| **다음** | RSS 없는 정부/규제기관 사이트 스크래퍼, 영문 요약 |
| **이후** | Jurisdiction Pulse 대시보드, 토픽 타임라인 |
| **장기** | 관할권 간 사건 연결, 토픽/단계별 RSS 피드 |

## 라이선스

Apache 2.0
