# 공통 알림 적용과 확인

공통 재생 알림은 백엔드 worker가 기록하고, 모든 접속자가 현재 세션의 DB 이력으로 전체·미확인
건수를 집계합니다. 브라우저 접속이나 알림 페이지 진입을 생성 조건으로 사용하지 않습니다.

알림 기록 방식은 재생 모드에 따라 다릅니다.

| 재생 모드 | 기록 주체 | 판정 근거 |
| --- | --- | --- |
| 공통 시계 재생 (`MONITORING_INFERENCE_ENABLED=0`) | 기존 알림 worker (`MONITORING_ALERT_WORKER_ENABLED=1`, `app/services/monitoring_alerts.py`) | Set4~9 원본 라벨, Set10~11 최신 예측 |
| Set별 재생 Gate (`MONITORING_INFERENCE_ENABLED=1`) | 모니터링 추론 Worker의 Gate 전환 (`app/services/monitoring_inference_alerts.py`) | 해당 재생 회차의 실제 AI 추론 결과 |

두 worker를 함께 켤 수 없습니다. `MONITORING_INFERENCE_ENABLED=1`이면 `MONITORING_ALERT_WORKER_ENABLED=0`으로
설정해야 앱이 기동되며, Gate 모드에서는 start·pause·reset·restart도 기존 방식의 알림을 기록하지 않습니다.

## 파일 적용

코드는 저장소의 `app/`에 포함되어 있으며 별도 압축 파일을 덮어쓰지 않습니다.
운영 배포는 Backend 이미지 릴리스(`vX.Y.Z` Tag)로 진행합니다. `.env`와 데이터 저장 폴더는 이미지에 포함하지 않습니다.

## DB 테이블 추가

기존 alerts는 prediction_id가 필수이므로 예측값이 없는 라벨 알림과 모니터링 추론 알림은 새 테이블
`monitoring_alert_events`에 저장합니다. 기존 alerts 데이터와 확인 이력은 유지합니다.
기존 DB에는 다음 migration을 순서대로 한 번씩 적용합니다. 신규 DB는 `sql/cnc/schema.sql`에 모두 포함되어 있습니다.

1. `sql/cnc/migrations/20261111_monitoring_alerts.sql`: `monitoring_alert_events` 생성
2. `sql/cnc/migrations/20261111_monitoring_alert_cycles.sql`: `cycle_number`와 회차 포함 UNIQUE 키
3. `sql/cnc/migrations/20261119_monitoring_inference_runs.sql` 적용 후
   `sql/cnc/migrations/20261119_monitoring_inference_alerts.sql`: `playback_generation`, `inference_run_id` 컬럼,
   UNIQUE 키를 (session, generation, cycle, set, position)으로 변경, 추론 알림의 확인 허용

다음 코드는 백엔드 작업 폴더의 PowerShell에서 실행합니다. 파일명만 바꿔 각 migration에 사용합니다.

```powershell
@'
from pathlib import Path
from app.core.database import get_connection

connection = get_connection()
cursor = connection.cursor()
try:
    cursor.execute("SELECT DATABASE()")
    if cursor.fetchone()[0] != "cnc_wearpoint":
        raise RuntimeError("Expected database: cnc_wearpoint")
    sql = Path("sql/cnc/migrations/20261111_monitoring_alerts.sql").read_text(encoding="utf-8-sig")
    for statement in sql.split(";"):
        if statement.strip():
            cursor.execute(statement)
    connection.commit()
    cursor.execute("SHOW TABLES LIKE 'monitoring_alert_events'")
    print(cursor.fetchall())
finally:
    cursor.close()
    connection.close()
'@ | uv run python -
```

## 서버 실행

백엔드 서버 PowerShell에서 실행합니다. 공통 시계 재생과 기존 알림 worker를 사용하는 예입니다.

```powershell
$env:MONITORING_CONTROL_TOKEN = "local-monitoring-test"
$env:MONITORING_ALERT_WORKER_ENABLED = "1"
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Set별 재생 Gate와 추론 알림을 확인하려면 Serving을 백엔드와 다른 Port(예: 8002)로 실행한 뒤 다음처럼 설정합니다.

```powershell
$env:MONITORING_CONTROL_TOKEN = "local-monitoring-test"
$env:MONITORING_INFERENCE_ENABLED = "1"
$env:MONITORING_ALERT_WORKER_ENABLED = "0"
$env:SERVING_URL = "http://127.0.0.1:8002"   # 로컬 Serving 주소에 맞춥니다.
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

프런트 서버 PowerShell에서 실행합니다. 기존 설치한 패키지를 그대로 사용합니다.

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8001"
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

## 시각과 확인 조건

- 공통 시계 재생의 새 알림 created_at은 UTC 기준 재생 일정의 발생 시각입니다. 재생은 2배속이므로 원본 센서 기준 경과 시간을 배속으로 나누어 실제 시각으로 환산합니다. 재개 이전에 새로 추가된 결과는 감지 시각으로 기록합니다.
- Set별 재생 Gate의 알림 created_at은 해당 측정의 추론 결과가 `showing`(화면 표시)으로 바뀐 UTC 시각입니다.
- recorded_at은 worker가 DB에 기록한 UTC 시각입니다. 공통 시계 재생의 worker는 재시작 시 지난 구간을 따라잡습니다.
- 처음 적용하면 이미 재생한 구간의 경고·위험 이력이 추가될 수 있습니다.
- 확인은 detail_confirmed_at만 변경하며 반복 요청은 최초 확인 시각을 유지합니다.
- 예측 ID가 없는 라벨 알림도 발생 이력과 전체 건수에 포함합니다.
- 예측 결과가 있는 알림과 모니터링 추론 알림(`inference_run_id` 있음)만 확인 시각을 저장할 수 있습니다. 목록 응답의 `can_acknowledge`로 구분합니다.
  라벨 알림은 나중에 예측 결과가 등록되면 확인할 수 있으며 이때 발생 시각과 건수는 유지합니다.
- 기존 alerts의 naive 시각은 기존 한국어 화면과 같은 한국 시각으로 해석합니다.
  기존 시각이 UTC라면 `.env`에서 `LEGACY_ALERTS_UTC_OFFSET_MINUTES=0`으로 설정합니다.
  기본값은 한국 시각에 해당하는 540입니다. 기존 DB 시각은 직접 변경하지 않습니다.
- API는 UTC offset을 포함한 시각을 반환하므로 한국 브라우저에서 한국 시각으로 표시됩니다.

## 기록 범위

판정 기준은 Warning 150 μm, Danger 200 μm입니다(`app/core/wear_policy.py`). 정상 판정은 알림을 생성하지 않습니다.
저장된 과거 알림 행의 판정과 기준값은 변경하지 않습니다.

공통 시계 재생에서는 Set4~9를 원본 라벨 마모량, Set10~11을 최신 예측 마모량으로 판정합니다.
같은 세션·회차·Set·사진 순번의 발생 건은 한 번만 기록합니다. 상태 행의 DB 잠금과 UNIQUE 키로
여러 worker가 실행돼도 중복 저장을 막습니다. pause, reset, restart 직전에도 지난 구간을 기록합니다.

Set별 재생 Gate에서는 해당 재생 회차(session, playback_generation, cycle, Set, position, measurement_id)의
추론이 `completed`이고 경고·위험일 때만 `source: prediction`으로 기록합니다. 정답 라벨이나 다른 회차의 예측으로 대신하지 않으며,
추론 실패·취소는 알림을 만들지 않습니다. Gate 전환과 같은 트랜잭션에서 기록하고 UNIQUE 키로 중복을 막습니다.

reset은 발생 이력을 유지하며 새 세션의 1회차를 즉시 재생합니다. 현재 세션만 집계하므로 전체·확인·미확인 건수는 초기화됩니다.
첫 측정이 경고라면 worker가 곧 새 알림을 기록하므로 0건 화면이 오래 유지되지는 않습니다.
restart는 세션을 유지하므로 건수를 유지합니다. Set별 재생 Gate에서는 `playback_generation`으로 이전 1회차와 구분해 새 알림을 기록합니다.
공통 시계 재생의 worker는 세대를 구분하지 않으므로, restart 후에는 같은 세션에서 이미 기록한 회차·Set·순번을 다시 기록하지 않습니다.
기존 alerts와 이전 session의 알림은 DB에 보존하고 현재 세션 목록과 건수에서는 제외합니다.

회차가 달라지면 같은 측정/예측 ID를 참조하는 새 알림 행이 생성되며, 확인 상태는 각 행에 따로 저장됩니다.
API의 신규 알림에는 `cycle_number`가 있습니다. 공통 시계 재생의 worker는 재시작 후 지난 회차의 누락된 경고/위험도 복구하며,
예측이 뒤늦게 들어오면 도달한 과거 회차에도 알림이 추가될 수 있습니다.

반복 기능을 처음 적용할 때는 기존 서버에서 reset 후 종료하고 새 Backend 이미지로 교체합니다.
이전 단발 재생의 긴 누적 시간을 여러 회차로 해석하는 것을 방지합니다.
reset은 알림 이력을 삭제하지 않습니다.

## API와 실기 테스트

| 메서드 | 경로 | 기능 |
| --- | --- | --- |
| GET | `/api/monitoring/alerts` | 현재 세션 이력과 total, unread, current_total, current_unread, filtered_total, session_id 조회 |
| PATCH | `/api/monitoring/alerts/monitoring:ID/acknowledge` | 신규 알림 확인 |
| PATCH | `/api/monitoring/alerts/legacy:ID/acknowledge` | 기존 alerts의 확인 시각 기록 |

목록은 `monitoring_alert_events`의 현재 세션 행만 반환합니다(`legacy_max_id`는 항상 0). 기존 alerts 행의 확인 API는 호환을 위해 유지합니다.

두 브라우저에서 `http://127.0.0.1:5173`에 접속하고 알림 페이지를 엽니다.
일반 API 요청 PowerShell에서 잠시 공통 재생을 멈춥니다.

```powershell
$headers = @{ "X-Monitoring-Control-Token" = "local-monitoring-test" }
Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8001/api/monitoring/pause" -Headers $headers | Select-Object status

Invoke-RestMethod "http://127.0.0.1:8001/api/monitoring/alerts?limit=1" |
    Select-Object total, unread, current_total, current_unread
```

5초 조회 간격과 네트워크 지연이 지난 뒤 두 화면의 전체·미확인 건수와 위 API 결과를
비교합니다. 한 화면에서 확인 가능한 알림을 확인한 뒤 다른 화면도 5초 내외에
확인 완료로 바뀌는지 확인합니다. 실시간 새 발생 시 조회 시점에 따른 일시적인 차이는 가능합니다.

아무도 접속하지 않은 상황은 브라우저를 모두 닫고 서버 재생을 재개해 확인합니다.
다음 경고 측정에 도달한 뒤 API 또는 DB를 조회하면 기록이 있어야 합니다.
아직 경고에 도달하지 않았다면 건수가 증가하지 않는 것이 정상입니다.

## SQL 확인

```sql
SELECT COUNT(*) AS total,
       COALESCE(SUM(e.detail_confirmed_at IS NOT NULL), 0) AS confirmed,
       COALESCE(SUM(e.detail_confirmed_at IS NULL), 0) AS unread
FROM cnc_wearpoint.monitoring_alert_events AS e
JOIN cnc_wearpoint.monitoring_state AS s ON s.id = 1 AND s.session_id = e.session_id;

SELECT id, session_id, playback_generation, cycle_number, set_number, measurement_id,
       prediction_id, inference_run_id, source, level,
       DATE_FORMAT(CONVERT_TZ(created_at, '+00:00', '+09:00'), '%Y-%m-%d %H:%i:%s') AS created_at,
       DATE_FORMAT(CONVERT_TZ(detail_confirmed_at, '+00:00', '+09:00'), '%Y-%m-%d %H:%i:%s') AS detail_confirmed_at
FROM cnc_wearpoint.monitoring_alert_events
ORDER BY id DESC
LIMIT 10;
```

2026-11-20 기준 백엔드 전체 테스트는 `277 passed, 10 skipped`, 프런트 Node 회귀 테스트는 89개가 통과합니다.
알림 관련 테스트는 `tests/test_monitoring_alerts.py`, `tests/test_playback_alert_timing.py`(2배속 발생 시각),
`tests/test_monitoring_inference_alerts.py`(추론 알림 기준·중복 방지)입니다.
DB 테스트는 SQLite 어댑터와 Mock을 사용하며 실제 MySQL/RDS와 브라우저 확인은 위 절차로 진행합니다.

## MySQL collation 회귀 확인

문자열 collation이 다른 기존·신규 테이블을 UNION할 때 1271 오류가 발생할 수 있어
공통 조회 SQL의 문자열 표현식을 `utf8mb4_0900_ai_ci`로 명시했습니다.
실제 MySQL 연결에서 읽기 전용 CTE로 혼합 collation을 재현하는 검사는 다음과 같습니다.

```powershell
$env:CNC_TEST_MYSQL_COLLATIONS = "1"
uv run pytest tests/test_monitoring_alerts_mysql.py -q
Remove-Item Env:CNC_TEST_MYSQL_COLLATIONS
```

이 검사는 DB 테이블 생성이나 데이터 삽입 없이 SELECT만 실행합니다.
일반 테스트에서는 실제 MySQL 연결이 필요하므로 이 검사를 건너뜁니다.

후속 페이지는 첫 응답의 session_id와 event_max_id를 전달합니다. 페이지 조회 도중 reset으로 세션이 바뀌면 409를 반환하므로 첫 페이지부터 다시 조회합니다. 프런트 자동 갱신은 약 5초 간격입니다.

### 페이지 조회와 집계

`GET /api/monitoring/alerts?limit=50&offset=0`으로 한 페이지를 조회합니다(`limit` 기본 100, 최대 500). 선택 인자 `set_number`(4~11), `level`(warning/danger), `read_status`(all/read/unread)는 서버에서 필터링합니다. 현재 프런트 알림 이력 페이지는 한 페이지 10건을 요청합니다.

- `total`, `unread`: `event_max_id` 상한 내 현재 세션 건수. 기존 클라이언트와 호환됩니다.
- `current_total`, `current_unread`: ID 상한·필터와 관계없이 현재 세션 전체의 최신 건수입니다.
- `filtered_total`: ID 상한 내 필터에 맞는 건수입니다. 페이지 수 계산에 사용합니다.
- `items`: 요청한 페이지의 행입니다. 예측 결과 JOIN 전에 대상 페이지를 먼저 선택합니다. 각 행에 `inference_run_id`, `can_acknowledge`가 있습니다.

후속 페이지는 `session_id`, `event_max_id`를 유지합니다. Set·단계 필터는 삽입에 따른 페이지 이동을 방지하고, 확인 상태 필터는 확인 처리에 따라 결과가 달라질 수 있습니다. reset 시 409를 반환합니다. 기존 데이터 삭제는 없습니다.
