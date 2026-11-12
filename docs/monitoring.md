# 공통 모니터링 1단계 적용

저장된 MATWI 파일 재생의 공통 시계와 Set별 일정을 서버 DB에 저장합니다.
프런트엔드 연결은 2단계, 서버 알림 생성은 3단계 변경과 함께 적용합니다.

## 변경 파일

- `app/api/routers/monitoring.py` 공통 상태 및 운영자 제어 API
- `app/services/monitoring.py` 센서 CSV 시간 검증, 고정 재생 일정, 현재 위치 계산
- `app/main.py` API 라우터 등록
- `.env.example` 운영자 토큰 변수
- `sql/cnc/migrations/20261111_monitoring.sql` 기존 DB에 새 테이블 2개 추가
- `sql/cnc/schema.sql` 신규 DB 생성 시 같은 새 테이블 정의 포함
- `tests/test_monitoring.py` 재접속, 시간 경계, 재개, 중복 요청, 실패 롤백 검증

## 적용

1. 실제 API가 연결된 DB에서 `sql/cnc/migrations/20261111_monitoring.sql`을 실행합니다.
   신규 DB는 갱신된 `sql/cnc/schema.sql`로 생성해도 됩니다.
2. 백엔드 `.env`에 충분히 긴 임의 문자열을 `MONITORING_CONTROL_TOKEN`으로 설정합니다.
   운영자만 보관하고 프런트의 `VITE_` 변수에 넣지 않습니다.
3. `LOCAL_STORAGE_ROOT` 아래에 기존 이미지와 센서 파일을 준비합니다.
   이미지 경로는 `images/set4/original/파일명.png`, 센서는 `sensors/set4/파일명.csv` 형식입니다.
   같은 방식으로 Set4~11을 사용합니다. DB 파일명의 JPG/PNG 확장자 차이는 허용합니다.
4. 로컬은 `uv sync` 후 `uv run python -m uvicorn app.main:app --reload`로 실행합니다.
   VM은 기존 Compose의 백엔드 이미지에 변경 코드를 포함하고 토큰 변수가 컨테이너에
   전달되도록 설정한 뒤 해당 백엔드를 재배포합니다. 실제 사용 중인 파일은
   `infra/compose/compose.backend-rds.yaml`입니다. 이 파일은 현재 GitHub main에 없습니다.

실제 RDS의 MySQL 잠금과 마이그레이션 적용은 운영 환경에서 별도로 확인해야 합니다.
자동화 테스트는 SQLite 어댑터로 API 트랜잭션과 동작을 검증합니다.

## API 확인

Postman에서 로컬의 `http://127.0.0.1:8000` 또는 재배포 후의
`https://aimw.duckdns.org`를 기본 주소로 사용합니다.
POST 요청에는 `X-Monitoring-Control-Token` 헤더로 운영자 토큰을 전달합니다.
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
| 8 | POST | `/api/monitoring/reset` | 새 session, 1회차, 기존 일정으로 즉시 `running` |
| 9 | POST | `/api/monitoring/start` | 이미 reset으로 시작한 같은 session 반환 |

첫 시작은 연결된 센서 CSV를 검증하여 일정을 만듭니다. 파일이 많으면 준비 시간이
길어질 수 있습니다. VM에서 첫 준비를 실행할 때에는 HTTP 프록시의 시간 제한을
거치지 않고 같은 API 로직을 실행할 수 있습니다.

```bash
sudo docker exec cnc-wearpoint-backend python -c \
  'from app.api.routers.monitoring import start; result = start(); print(result["status"], result["session_id"])'
```

이 명령은 SSH로 접속한 VM 운영자가 실행합니다. 일반 접속자는 조회 API만 사용합니다.
운영자 토큰이 없는 POST는 403, 서버 토큰 미설정은 503으로 응답합니다.
테이블이 없으면 적용할 migration 파일명과 함께 503을 반환합니다.
DB 측정과 연결된 이미지가 전혀 없으면 409를 반환하고 시작하지 않습니다.

## 재생 규칙

- 서버 이미지 목록의 숫자 기준 파일명 순서로 Set마다 별도 일정을 고정합니다.
- DB 측정과 서버 이미지가 연결되는 항목을 사용합니다. 예측 유무로 제한하지 않습니다.
- 센서 CSV는 숫자 5열과 시간 1열, 시간 오름차순과 유한한 숫자를 검증합니다.
- 첫 센서 시각부터 마지막 시각까지를 재생 시간으로 사용합니다.
- 센서 없음, 파일 없음, 형식 오류, 재생 시간 0은 사진을 2초 표시합니다.
- 한 회차는 가장 긴 Set 일정의 길이입니다. 먼저 끝난 Set은 마지막 화면에서 기다리고, 회차 경계에서 모든 Set이 함께 처음으로 돌아옵니다.
- `elapsed_ms`는 세션 누적 시간, `cycle_number`는 1부터 시작하는 회차, `cycle_elapsed_ms`는 현재 회차 안의 시간입니다. `total_duration_ms`는 한 회차 길이이며 반복 중 상태는 `running`을 유지합니다.
- pause는 누적 시간을 저장하고 재개 시 이어갑니다. reset은 새 세션의 1회차, 누적 시간 0부터 기존 일정으로 즉시 재생합니다. 준비된 일정이 없을 때만 idle이며 첫 start가 필요합니다.
- 처음부터 재생하려면 `reset`만 실행합니다. 실행 중의 중복 `start`는 같은 session을 반환합니다.
- Set 데이터가 없으면 해당 Set의 상태는 `empty`이고 다른 Set은 계속 진행합니다.
- reset은 기존 일정을 재사용합니다. 데이터 파일 교체 후 일정 재구성은 이 API에서 지원하지 않으므로 운영 중 파일을 바꾸지 않습니다.
- UTC 기준 DB 시각으로 위치를 계산합니다. 새 접속과 API worker 재시작은 시계를 초기화하지 않습니다.
- API가 중지된 동안도 실행 상태의 시계는 계속 흐릅니다.
- 센서 내용이 재생 중 바뀌지 않도록 일정 생성 후 파일을 유지해야 합니다.

응답에는 공통 `server_time`, `session_id`, `revision`, `status`, `elapsed_ms`와
전체 `total_duration_ms`가 있습니다. 각 Set에는 `measurement_id`, `position`,
`total`, `image_name`, `sensor_name`, `image_url`, `sensor_url`,
`playback_mode`, 측정 안에서의 `elapsed_ms`, `duration_ms`가 있습니다.
`position`은 0부터 시작합니다. `empty` Set은 `set_number`, `status`, `total`만 반환합니다.

3단계 적용 후 서버 worker가 이 일정과 session을 사용해 알림을 생성합니다.
새 테이블과 적용 절차는 `docs/monitoring-alerts.md`를 참고합니다.

## 세션별 알림 초기화

reset은 과거 알림 행을 삭제하지 않습니다. 알림 목록과 전체·확인·미확인 건수는 현재 session_id만 집계합니다. 새 세션의 첫 경고부터 건수가 다시 증가합니다. 브라우저 종료나 새로고침은 초기화가 아니며 worker 기록과 회차 증가는 계속됩니다.
