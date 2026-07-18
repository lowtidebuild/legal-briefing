# Game Legal Briefing 운영 Runbook

이 문서는 예약 실행의 상태를 판정하고, 외부 전달 없이 복구 범위를 정하기 위한 운영 절차다. 실제 이메일·Sheets가 포함된 수동 실행은 별도 승인을 받은 뒤에만 한다.

## 정상 실행 순서

1. Python 3.11 lock 설치
2. 전체 pytest gate
3. 수집·선별·분류·요약 생성 (`main.py --delivery none`)
4. daily JSON, run manifest, run report 커밋·push
5. GitHub Pages artifact 업로드 및 배포
6. Pages 성공 시에만 기존 manifest 전달
7. delivery receipt 커밋·push

`main.py`에는 메일·Sheets 쓰기 경로가 없다. Pages 단계가 실패하면 workflow의 delivery step은 `success()` 조건 때문에 실행되지 않는다.

## 수동 workflow 모드

| 입력 | 용도 | 외부 전달 |
|---|---|---|
| 기본값 | 정상 생성 → Pages → 전달 | Pages 성공 후 실행 |
| `web_only=true` | 공개 웹 canary | 실행 안 함 |
| `render_date=YYYY-MM-DD` | 저장된 날짜 재렌더 | 실행 안 함 |
| `force_delivery=true` | 확인된 partial run의 미완료 단계 재개 | 완료 단계는 반복 안 함 |

`force_delivery`는 일반 재실행 옵션이 아니다. delivery receipt가 `partial`이고 실패 원인과 이미 완료된 단계를 확인한 경우에만 사용한다. 이메일 상태가 `ambiguous`이면 자동 재전달하지 않는다.

## 상태 판정

- `SUCCESS`: 생성 필수 단계 정상, Tier A 비정상 비율 50% 미만, primary 429·selector fallback 없음
- `DEGRADED`: 결과는 생성됐지만 Tier A 비정상 50% 이상, primary 429, LLM fallback batch 또는 deterministic selector fallback 발생
- `NO_UPDATES`: 수집과 selector는 정상이지만 법률 관련성 기준을 통과한 기사가 0건. 빈 daily JSON을 게시하고 메일·Sheets는 생략
- `FAIL`: 유효한 수집 결과 없음, Sheets dedup read 실패, quality gate 실패, manifest 불일치 또는 필수 발행·전달 실패

확인 파일:

- `output/data/runs/YYYY-MM-DD.json`: source·LLM·quality·stage 상태
- `output/data/run_manifests/YYYY-MM-DD.json`: 전달 대상 SHA-256
- `output/data/delivery_receipts/YYYY-MM-DD.json`: Pages·email·Sheets 완료 상태

## 장애별 대응

### 소스 403·404·timeout

run report의 source name과 상태를 확인한다. 한 소스의 실패는 전체 수집을 중단하지 않는다. URL 교체·삭제는 브라우저 또는 명시적 User-Agent 요청으로 live 검증된 항목만 별도 작은 diff로 반영한다.

### Gemini 429 또는 fallback

결과가 있으면 `DEGRADED`다. model별 `attempts`, `successes`, `rate_limits`, `fallback_batches`를 확인한다. 같은 run에서 primary를 반복 호출하지 말고 다음 예약 실행까지 quota 회복을 기다리는 것이 기본값이다.

### `NO_UPDATES`

장애가 아니다. 소스 status가 정상이고 selector fallback이 없으면 그대로 종료한다. 이메일·Sheets를 수동 실행하지 않는다.

### Pages 실패

delivery가 실행되지 않았는지 Actions step에서 확인한다. 생성 데이터가 커밋돼 있으면 아래 명령으로 저장 결과만 재렌더할 수 있다.

```bash
python3 scripts/render_existing.py --date YYYY-MM-DD
```

Pages 성공 전에는 `deliver_existing.py`를 실행하지 않는다.

### Email `ambiguous`

SMTP 서버가 수신한 뒤 연결 오류가 났을 가능성이 있으므로 자동 재시도하지 않는다. 수신 여부를 별도 확인한 뒤 운영자가 다음 조치를 결정한다. `force_delivery`로도 ambiguous 이메일은 다시 보내지 않는다.

### Sheets `failed`

receipt에서 email이 `completed`, Sheets가 `failed`인지 확인한다. 원인을 고친 뒤 `force_delivery=true`로 재개하면 email은 건너뛰고 Sheets만 실행한다. Sheets 동기화는 기존 `event_key`를 읽어 이미 들어간 행은 다시 append하지 않는다.

### content hash 충돌

동일 `run_id`의 daily JSON과 manifest hash가 다르면 전달을 중단한다. receipt나 manifest를 임의 수정하지 말고, 변경된 daily JSON이 의도된 것인지 먼저 확인한다. 별도 날짜/run으로 다시 생성하는 것이 기본 복구 방식이다.

## Canary 순서

1. 로컬 `python3 -m pytest -q`
2. 로컬 sample integration과 기존 날짜 render
3. GitHub test workflow 성공 확인
4. 수동 `web_only=true` 실행
5. Pages의 최신 날짜·기사 링크와 `output/data/runs/YYYY-MM-DD.json` 확인
6. 별도 승인 후에만 실제 이메일·Sheets가 포함된 기본 manual run

다음 중 하나라도 해당하면 full run을 중단한다:

- 테스트 또는 event key 경로 안전성 실패
- primary 호출 예산 초과 또는 run status `FAIL`
- selected item의 legal hook 누락
- Pages 전에 delivery가 실행 가능한 workflow 구조
- report·log에 수신자, credential, Sheet ID, prompt 또는 기사 본문 노출

## 로컬 안전 검증

```bash
python3 -m pytest -q
python3 main.py --dry-run --sample-data --delivery none --output /tmp/legal-briefing-canary
python3 scripts/render_existing.py --date YYYY-MM-DD --output /tmp/legal-briefing-render
```

마지막 명령은 지정한 output 경로에 해당 날짜의 daily JSON이 있을 때만 실행한다. 운영 `output/`을 덮어쓰지 않도록 임시 디렉터리를 사용한다.
