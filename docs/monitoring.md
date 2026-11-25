# 공통 모니터링 재생

저장된 MATWI 파일 재생의 공통 시계와 Set별 일정을 서버 DB에 저장합니다.
프런트엔드 연결은 2단계, 서버 알림 생성은 3단계 변경으로 적용했습니다.
이후 센서 재생 2배속, Set별 재생 Gate와 모니터링 추론 Worker(`MONITORING_INFERENCE_ENABLED=1`)가 추가됐습니다.
화면의 Set 1~8은 원본 Set4~11입니다.

## 관련 파일

- `app/api/routers/monitoring.py` 공통 상태 조회 및 운영자 제어(start·pause·reset), 재생 위치 재시작(restart) API
- `app/api/routers/monitoring_inference.py` 현재 재생 위치의 추론 실행 상태 조회 API
- `app/services/monitoring.py` 센서 CSV 시간 검증, 고정 재생 일정, 현재 위치 계산
- `app/services/playback_speed.py` 센서 재생 배속(`PLAYBACK_RATE = 2`)
- `app/services/monitoring_playback_gate.py` Set별 재생 Gate(재생 → 추론 대기 → 결과 3초 표시)
- `app/services/monitoring_inference_queue.py` 모니터링 추론 등록·Serving 호출 Worker
- `app/services/inference_capacity.py` 수동 요청과 모니터링 추론의 추론 Slot 분리
- `app/main.py` API 라우터 등록, Worker 기동
- `.env.example` 운영자 토큰 변수
- `sql/cnc/migrations/20261111_monitoring.sql` 공통 상태·일정 테이블 2개
- `sql/cnc/migrations/20261119_monitoring_inference_runs.sql` `monitoring_state.playback_generation`과 `monitoring_inference_runs`
- `sql/cnc/migrations/20261119_monitoring_playback_gates.sql` `monitoring_playback_gates`
- `sql/cnc/schema.sql` 신규 DB 생성 시 위 테이블 정의 포함
- `tests/test_monitoring.py`, `tests/test_playback_speed.py`, `tests/test_monitoring_playback_gate.py`,
  `tests/test_monitoring_inference_queue.py`, `tests/test_monitoring_inference_recovery.py` 회귀 테스트

## 적용

1. 실제 API가 연결된 DB에서 `sql/cnc/migrations/20261111_monitoring.sql`을 실행합니다.
   Set별 재생 Gate와 추론을 사용하려면 `20261119_monitoring_inference_runs.sql`,
   `20261119_monitoring_inference_alerts.sql`, `20261119_monitoring_playback_gates.sql`을 이 순서로 추가 적용합니다.
   신규 DB는 갱신된 `sql/cnc/schema.sql`로 생성해도 됩니다.
2. 백엔드 `.env`에 충분히 긴 임의 문자열을 `MONITORING_CONTROL_TOKEN`으로 설정합니다.
   운영자만 보관하고 프런트의 `VITE_` 변수에 넣지 않습니다.
3. 이미지와 센서 파일을 준비합니다.
   이미지 경로는 `images/set4/original/파일명.png`, 센서는 `sensors/set4/파일명.csv` 형식이며 Set4~11을 같은 방식으로 사용합니다.
   DB 파일명의 JPG/PNG 확장자 차이는 허용합니다.
   운영(`STORAGE_BACKEND=s3`)에서 이미지 목록과 이미지·센서 파일 응답은 Object Storage를 사용합니다.
   단, 첫 start에서 일정을 만들 때 센서 재생 시간은 `LOCAL_STORAGE_ROOT` 아래의 로컬 센서 파일을 읽어 계산합니다.
   로컬 파일이 없으면 해당 측정은 사진만 표시하는 일정으로 고정되므로, 일정을 새로 만들 때에는 로컬 센서 파일이 있는 환경에서 실행합니다.
4. 로컬은 `uv sync` 후 `uv run python -m uvicorn app.main:app --reload`로 실행합니다.
   VM은 GitLab CI의 `deploy_backend`가 `/opt/cnc-wearpoint/backend`의 Docker Compose로 Backend Container를 갱신합니다.
   토큰과 모니터링 환경변수는 운영 env 파일(`/etc/cnc-wearpoint/*.env`)로 컨테이너에 전달합니다.
5. Set별 재생 Gate와 추론을 사용하려면 `MONITORING_INFERENCE_ENABLED=1`, `MONITORING_ALERT_WORKER_ENABLED=0`을 함께 설정합니다.
   `MONITORING_INFERENCE_ENABLED=1`인데 `MONITORING_ALERT_WORKER_ENABLED`가 `1`(기본값)이면 앱이 기동되지 않습니다.
   Serving 주소(`SERVING_URL`)와 모델 이름(`PREDICTION_MODEL_NAME`) 설정도 필요합니다.

실제 RDS의 MySQL 잠금과 마이그레이션 적용은 운영 환경에서 별도로 확인해야 합니다.
자동화 테스트는 SQLite 어댑터와 Mock으로 API 트랜잭션과 동작을 검증합니다.

## API 확인

Postman에서 로컬의 `http://127.0.0.1:8000` 또는 운영의
`https://aimw.duckdns.org`를 기본 주소로 사용합니다.
start·pause·reset 요청에는 `X-Monitoring-Control-Token` 헤더로 운영자 토큰을 전달합니다.
본문은 필요 없습니다.

| 순서 | 메서드 | 경로 | 확인할 결과 |
| --- | --- | --- | --- |
| 1 | GET | `/api/monitoring/state` | 초기 `status`가 `idle`, `sets`에 Set4~11 8개 |
| 2 | POST | `/api/monitoring/start` | `running`, `session_id`, 현재 측정과 파일 URL |
| 3 | GET | `/api/monitoring/state` | 잠시 후 `elapsed_ms` 증가 |
| 4 | GET | `/api/monitoring/state` | 다른 클라이언트에서도 같은 session과 서버 기준 위치 |
| 5 | POST | `/api/monitoring/pause` | 전체 시계 일시정지 |
| 6 | GET | `/api/monitoring/state` | 시간이 지나도 `elapsed_ms` 고정 |
| 7 | POST | `/api/monitoring/start` | 같은 session에서 이어서 재생 |
| 8 | POST | `/api/monitoring/restart` | 같은 session, `playback_generation` +1, 모든 Set이 처음부터 재생 |
| 9 | POST | `/api/monitoring/reset` | 새 session, 1회차, 기존 일정으로 즉시 `running` |
| 10 | POST | `/api/monitoring/start` | 이미 reset으로 시작한 같은 session 반환 |
| 11 | GET | `/api/monitoring/inference/current` | 추론 활성화 시 현재 위치의 실행 상태. 비활성화 시 503 |

첫 시작은 연결된 센서 CSV를 검증하여 일정을 만듭니다. 파일이 많으면 준비 시간이
길어질 수 있습니다. VM에서 첫 준비를 실행할 때에는 HTTP 프록시의 시간 제한을
거치지 않고 같은 API 로직을 실행할 수 있습니다.

```bash
sudo docker exec cnc-wearpoint-backend python -c \
  'from app.api.routers.monitoring import start; result = start(); print(result["status"], result["session_id"])'
```

이 명령은 SSH로 접속한 VM 운영자가 실행합니다.
운영자 토큰이 없는 start·pause·reset은 403, 서버 토큰 미설정은 503으로 응답합니다.
`restart`는 토큰을 요구하지 않습니다. 프런트 하단의 분석 시작 버튼이 이 API를 호출하며, 일정이 없으면 409를 반환합니다.
테이블이 없으면 적용할 migration 파일명과 함께 503을 반환합니다.
DB 측정과 연결된 이미지가 전혀 없으면 409를 반환하고 시작하지 않습니다.

## 재생 규칙

- 서버 이미지 목록의 숫자 기준 파일명 순서로 Set마다 별도 일정을 고정합니다.
- DB 측정과 서버 이미지가 연결되는 항목을 사용합니다. 예측 유무로 제한하지 않습니다.
- 센서 CSV는 숫자 5열과 시간 1열, 시간 오름차순과 유한한 숫자를 검증합니다.
- 첫 센서 시각부터 마지막 시각까지를 재생 시간(`duration_ms`, 원본 센서 기준)으로 사용합니다.
- 센서 없음, 파일 없음, 형식 오류, 재생 시간 0은 사진만 표시합니다(`playback_mode: image_only`, 원본 기준 2초).
- 센서 재생은 **2배속**입니다(`app/services/playback_speed.py`의 `PLAYBACK_RATE = 2`). `elapsed_ms`, `duration_ms`는 원본 센서 기준 밀리초이며 실제 시간은 그 절반입니다. 응답의 `playback_rate`로 배속을 알립니다.
- pause는 누적 시간을 저장하고 재개 시 이어갑니다. 누적 시간은 재개 시 다시 배속하지 않습니다.
- reset은 새 세션의 1회차, 누적 시간 0부터 기존 일정으로 즉시 재생합니다. 준비된 일정이 없을 때만 idle이며 첫 start가 필요합니다.
- restart는 세션과 알림 기록을 유지한 채 `playback_generation`을 1 올리고 재생 위치만 처음으로 되돌립니다. 같은 세션의 이전 1회차와 구분하기 위한 값이며 pause·재개에는 바뀌지 않습니다.
- 실행 중의 중복 `start`는 같은 session을 반환합니다.
- Set 데이터가 없으면 해당 Set의 상태는 `empty`이고 다른 Set은 계속 진행합니다.
- reset·restart는 기존 일정을 재사용합니다. 데이터 파일 교체 후 일정 재구성은 이 API에서 지원하지 않으므로 운영 중 파일을 바꾸지 않습니다.
- UTC 기준 DB 시각으로 위치를 계산합니다. 새 접속과 API worker 재시작은 시계를 초기화하지 않습니다.
- API가 중지된 동안도 실행 상태의 시계는 계속 흐릅니다.
- 센서 내용이 재생 중 바뀌지 않도록 일정 생성 후 파일을 유지해야 합니다.

### 공통 시계 재생 (`MONITORING_INFERENCE_ENABLED=0`, 기본값)

- 한 회차는 가장 긴 Set 일정의 길이입니다. 먼저 끝난 Set은 마지막 화면에서 기다리고(`status: completed`), 회차 경계에서 모든 Set이 함께 처음으로 돌아옵니다.
- `elapsed_ms`는 세션 누적 시간, `cycle_number`는 1부터 시작하는 회차, `cycle_elapsed_ms`는 현재 회차 안의 시간입니다. `total_duration_ms`는 한 회차 길이이며 반복 중 상태는 `running`을 유지합니다.

### Set별 재생 Gate (`MONITORING_INFERENCE_ENABLED=1`)

- 각 Set이 공통 시계와 별도로 `monitoring_playback_gates`의 자기 단계에 따라 진행합니다. 응답에 `gated_playback: true`가 포함됩니다.
- 단계(`playback_phase`)는 `playing`(이미지·센서 재생, 2배속) → `waiting`(재생이 끝났고 해당 재생 회차의 추론 결과 대기) → `showing`(결과 3초 표시, 실제 시간 기준) 순서이며, 3초 뒤 다음 측정의 `playing`으로 넘어갑니다.
- 추론이 실패·취소된 경우에도 `showing`으로 3초 표시한 뒤 넘어가므로 한 Set이 멈추지 않습니다. 사진만 있는 측정은 추론하지 않고 재생 후 바로 `showing`으로 넘어갑니다.
- 마지막 측정 다음에는 그 Set만 처음으로 돌아가며 Set별 `cycle_number`가 1 증가합니다. 따라서 Set마다 측정 위치와 회차가 서로 다를 수 있습니다.
- Set 항목에는 `playback_phase`, `playback_rate`, `result_visible`, `cycle_number`, `playback_generation`, `phase_elapsed_ms`(showing 경과)가 추가됩니다. Gate의 세션·세대·측정이 일정과 맞지 않으면 이전 이미지를 반환하지 않고 `playback_phase: unavailable`, `status: empty`로 응답합니다.
- pause 중에는 어떤 Set도 단계가 진행하지 않습니다. start·reset·restart는 Gate를 다시 초기화하거나 재개합니다.

### 모니터링 추론 Worker

- `MONITORING_INFERENCE_ENABLED=1`이면 앱 프로세스마다 Worker가 기동됩니다. 재생 Gate 진행·추론 등록 Loop(1초 간격)와 Serving 호출 Loop를 분리하여, Serving 호출 중에도 다른 Set의 Gate가 계속 진행됩니다.
- 실행은 (session, playback_generation, cycle_number, set_number, position, measurement_id) 단위로 `monitoring_inference_runs`에 한 번만 등록합니다. 같은 측정도 회차·restart가 다르면 새로 추론합니다. 결과는 기존 `predictions` 테이블에 쓰지 않습니다.
- Serving 호출 전후로 현재 재생 위치와 일치하는지 다시 확인합니다. 이미 다른 측정·회차·세대로 넘어간 실행은 `cancelled`, `error_code: STALE_OCCURRENCE`로 끝내며 Serving을 호출하지 않거나 결과를 저장하지 않습니다. pause만으로는 취소하지 않습니다.
- 실패 코드는 `INPUT_REJECTED`(Serving HTTP 400, 같은 파일은 다시 거절됨), `INFERENCE_FAILED`(그 밖의 오류·Timeout), `WORKER_INTERRUPTED`(이전 Worker가 `running` 상태로 중단한 실행을 다음 Worker가 실패 처리)입니다. 결과를 알 수 없는 호출은 자동 재전송하지 않습니다.
- 여러 Backend 프로세스 사이의 Serving 호출은 MySQL `GET_LOCK('cnc_wp_monitoring_queue')`으로 하나씩 처리합니다. 프로세스 안에서는 수동 요청(Set test)과 별도의 모니터링 추론 Slot을 사용하므로 서로 429를 만들지 않습니다.
- `GET /api/monitoring/inference/current`는 현재 각 Set이 보여주는 재생 회차와 정확히 일치하는 실행만 반환합니다. 항목은 `run_id`, 위 식별자 6개, `status`, 완료 시 `predicted_wear_um`·`predicted_type`·`wear_status`·`model_name`·`model_version`, 실패·취소 시 `error_code`입니다.
- 판정 기준은 Warning 150 µm, Danger 200 µm이며 Serving의 판정값 대신 Backend가 다시 계산합니다.
- 운영 Serving은 2026-11-20부터 Version 2(`candidate-opt`)를 사용하며 모니터링 추론 시간은 평균 약 1.1초입니다.

응답에는 공통 `server_time`, `session_id`, `revision`, `playback_generation`, `status`,
`elapsed_ms`, `cycle_number`, `cycle_elapsed_ms`, `loop_enabled`, `playback_rate`와
전체 `total_duration_ms`가 있습니다. 각 Set에는 `measurement_id`, `position`,
`total`, `image_name`, `sensor_name`, `image_url`, `sensor_url`,
`playback_mode`, `message`, 측정 안에서의 `elapsed_ms`, `duration_ms`가 있습니다.
`position`은 0부터 시작합니다. `empty` Set은 `set_number`, `status`, `total`만 반환합니다.

알림 생성은 `docs/monitoring-alerts.md`를 참고합니다. 공통 시계 재생에서는 기존 알림 worker가,
Set별 재생 Gate에서는 추론 결과가 `showing`으로 바뀌는 시점에 알림을 기록합니다.

## 세션별 알림 초기화

reset은 과거 알림 행을 삭제하지 않습니다. 알림 목록과 전체·확인·미확인 건수는 현재 session_id만 집계합니다. 새 세션의 첫 경고부터 건수가 다시 증가합니다. restart는 세션을 유지하므로 알림 건수도 유지합니다. 브라우저 종료나 새로고침은 초기화가 아니며 worker 기록과 회차 증가는 계속됩니다.
