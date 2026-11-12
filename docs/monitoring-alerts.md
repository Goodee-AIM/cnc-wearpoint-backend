# 공통 알림 3단계 적용과 확인

공통 재생 알림은 백엔드 worker가 기록하고, 모든 접속자가 현재 세션의 DB 이력으로 전체·미확인
건수를 집계합니다. 브라우저 접속이나 알림 페이지 진입을 생성 조건으로 사용하지 않습니다.

## 파일 적용

현재 1단계 백엔드와 2단계 프런트 코드에 덮어쓰는 변경 파일입니다.
기존 로컬 수정 파일은 별도로 백업한 뒤 적용합니다.

| 압축 안 경로 | 적용할 실제 폴더 |
| --- | --- |
| `backend/` 안의 파일 | `C:\Users\93\Downloads\웹통합\cnc-wearpoint-backend\` |
| `frontend/` 안의 파일 | `C:\Users\93\Downloads\웹통합\matwi-frontend\` |

8001 백엔드와 5173 프런트 서버를 Ctrl+C로 종료한 뒤 파일을 복사합니다.
`.env`와 데이터 저장 폴더는 배포 파일에 포함하지 않습니다.

## DB 테이블 추가

기존 alerts는 prediction_id가 필수이므로 예측값이 없는 라벨 알림은 새 테이블
`monitoring_alert_events`에 저장합니다. 기존 alerts 데이터와 확인 이력은 유지합니다.
`sql/cnc/migrations/20261111_monitoring_alerts.sql`을 기존과 같은 DB에 적용합니다.
다음 코드는 백엔드 작업 폴더의 PowerShell에서 실행합니다.

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

백엔드 서버 PowerShell에서 실행합니다.

```powershell
$env:MONITORING_CONTROL_TOKEN = "local-monitoring-test"
$env:MONITORING_ALERT_WORKER_ENABLED = "1"
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

프런트 서버 PowerShell에서 실행합니다. 기존 설치한 패키지를 그대로 사용합니다.

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8001"
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

## 시각과 확인 조건

- 새 공통 알림의 created_at은 UTC 기준 재생 일정의 발생 시각입니다.
- recorded_at은 worker가 DB에 기록한 UTC 시각입니다. worker 재시작 시 지난 구간을 따라잡습니다.
- 처음 적용하면 이미 재생한 구간의 경고·위험 이력이 추가될 수 있습니다.
- 확인은 detail_confirmed_at만 변경하며 반복 요청은 최초 확인 시각을 유지합니다.
- 예측 ID가 없는 라벨 알림도 발생 이력과 전체 건수에 포함합니다.
- 예측 결과가 있는 알림만 확인 시각을 저장할 수 있습니다. 나중에 예측 결과가 등록되면
  기존 라벨 알림을 확인할 수 있으며 이때 발생 시각과 건수는 유지합니다.
- 기존 alerts의 naive 시각은 기존 한국어 화면과 같은 한국 시각으로 해석합니다.
  기존 시각이 UTC라면 `.env`에서 `LEGACY_ALERTS_UTC_OFFSET_MINUTES=0`으로 설정합니다.
  기본값은 한국 시각에 해당하는 540입니다. 기존 DB 시각은 직접 변경하지 않습니다.
- API는 UTC offset을 포함한 시각을 반환하므로 한국 브라우저에서 한국 시각으로 표시됩니다.

## 기록 범위

Set4~9는 원본 라벨 마모량 50/90 μm 기준으로 기록합니다. Set10~11은 최신 예측의
warning_threshold_um과 danger_threshold_um을 사용합니다. 정상 판정은 알림을 생성하지 않습니다.
같은 세션·회차·Set·사진 순번의 발생 건은 한 번만 기록합니다. 상태 행의 DB 잠금과 UNIQUE 키로
여러 worker가 실행돼도 중복 저장을 막습니다. pause와 reset 직전에도 지난 구간을 기록합니다.
reset은 발생 이력을 유지하며 새 세션의 1회차를 즉시 재생합니다. 현재 세션만 집계하므로 전체·확인·미확인 건수는 초기화됩니다. 첫 측정이 경고라면 worker가 곧 새 알림을 기록하므로 0건 화면이 오래 유지되지는 않습니다.
기존 alerts와 이전 session의 알림은 DB에 보존하고 현재 세션 목록과 건수에서는 제외합니다.

이 단계는 저장된 MATWI 데이터의 반복 재생을 대상으로 합니다.
기존 DB에는 `20261111_monitoring_alert_cycles.sql`을 한 번 적용합니다.
이미 cycle_number와 회차 포함 UNIQUE 키를 적용했다면 다시 실행하지 않습니다.
회차가 달라지면 같은 측정/예측 ID를 참조하는 새 알림 행이 생성되며, 확인 상태는 각 행에 따로 저장됩니다.
API의 신규 알림에는 `cycle_number`가 있고 기존 alerts 이력에는 NULL입니다.
worker는 재시작 후 지난 회차의 누락된 경고/위험도 복구합니다.
예측이 뒤늦게 들어오면 도달한 과거 회차에도 알림이 추가될 수 있습니다.

반복 기능을 처음 적용할 때는 기존 서버에서 reset 후 종료하고 파일을 교체합니다.
이전 단발 재생의 긴 누적 시간을 여러 회차로 해석하는 것을 방지합니다.
reset은 알림 이력을 삭제하지 않습니다.

## API와 실기 테스트

| 메서드 | 경로 | 기능 |
| --- | --- | --- |
| GET | `/api/monitoring/alerts` | 현재 세션 이력과 total, unread, session_id 조회 |
| PATCH | `/api/monitoring/alerts/monitoring:ID/acknowledge` | 신규 알림 확인 |
| PATCH | `/api/monitoring/alerts/legacy:ID/acknowledge` | 기존 alerts의 확인 시각 기록 |

두 브라우저에서 `http://127.0.0.1:5173`에 접속하고 알림 페이지를 엽니다.
일반 API 요청 PowerShell에서 잠시 공통 재생을 멈춥니다.

```powershell
$headers = @{ "X-Monitoring-Control-Token" = "local-monitoring-test" }
Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8001/api/monitoring/pause" -Headers $headers | Select-Object status

Invoke-RestMethod "http://127.0.0.1:8001/api/monitoring/alerts?limit=1" |
    Select-Object total, unread
```

5초 조회 간격과 네트워크 지연이 지난 뒤 두 화면의 전체·미확인 건수와 위 API 결과를
비교합니다. 한 화면에서 예측 결과가 있는 알림을 확인한 뒤 다른 화면도 5초 내외에
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

SELECT id, session_id, set_number, measurement_id, prediction_id, source, level,
       DATE_FORMAT(CONVERT_TZ(created_at, '+00:00', '+09:00'), '%Y-%m-%d %H:%i:%s') AS created_at,
       DATE_FORMAT(CONVERT_TZ(detail_confirmed_at, '+00:00', '+09:00'), '%Y-%m-%d %H:%i:%s') AS detail_confirmed_at
FROM cnc_wearpoint.monitoring_alert_events
ORDER BY id DESC
LIMIT 10;
```

백엔드 48개 테스트, 프런트 12개 회귀 테스트와 Vite 빌드가 통과했습니다.
별도 React 검사에서 브라우저별 관측 값이 달라도 DB 건수가 같고, 확인 상태가 다른
접속자에게 반영되며 프런트가 알림 생성 POST를 보내지 않는 동작을 확인했습니다.
DB 테스트는 SQLite 어댑터를 사용했으며 실제 MySQL/RDS와 브라우저 확인은 위 절차로 진행합니다.
기존 프런트 lint 경고는 남아 있습니다.

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
일반 테스트에서는 실제 MySQL 연결이 필요하므로 이 검사 하나를 건너뜁니다.
수정 환경에서는 일반 테스트 48개가 통과했고 실제 MySQL 검사는 실행하지 못했습니다.

후속 페이지는 첫 응답의 session_id와 event_max_id를 전달합니다. 페이지 조회 도중 reset으로 세션이 바뀌면 409를 반환하므로 첫 페이지부터 다시 조회합니다. 프런트 자동 갱신은 약 5초 간격입니다. 스키마와 기존 데이터 변경은 필요하지 않습니다.

### 페이지 조회와 집계

`GET /api/monitoring/alerts?limit=50&offset=0`으로 한 페이지를 조회합니다. 선택 인자 `set_number`(4~11), `level`(warning/danger), `read_status`(all/read/unread)는 서버에서 필터링합니다.

- `total`, `unread`: `event_max_id` 상한 내 현재 세션 건수. 기존 클라이언트와 호환됩니다.
- `current_total`, `current_unread`: ID 상한·필터와 관계없이 현재 세션 전체의 최신 건수입니다.
- `filtered_total`: ID 상한 내 필터에 맞는 건수입니다. 페이지 수 계산에 사용합니다.
- `items`: 요청한 페이지의 행입니다. 예측 결과 JOIN 전에 대상 페이지를 먼저 선택합니다.

후속 페이지는 `session_id`, `event_max_id`를 유지합니다. Set·단계 필터는 삽입에 따른 페이지 이동을 방지하고, 확인 상태 필터는 확인 처리에 따라 결과가 달라질 수 있습니다. reset 시 409를 반환합니다. 기존 데이터 삭제나 스키마 변경은 없습니다.
