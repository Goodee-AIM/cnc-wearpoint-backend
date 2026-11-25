# 사용자 입력 탭 (현재 Set test)

> 2026-11-20 기준: 사용자 입력 탭은 현재 화면의 **Set test**로 바뀌었고, 업로드는
> `POST /api/measurements/auto-predict`(업로드 + Serving 추론)로 처리한다.
> 이 문서의 `/api/manual-inputs` 저장 API는 백엔드에 남아 있지만 현재 프런트 Set test는 호출하지 않는다.
> 자동 예측 API 계약은 `docs/deployment/auto_prediction.md`를 참고한다.

## 동작

- UI Set 1~8(원본 번호 4~11), 자동 모니터링, 알림 이력, reset API는 그대로 유지한다.
- 왼쪽 Set 목록의 `Set test`로 진입하면 업로드 팝업이 열린다. 팝업은 × 버튼으로 닫고 파일 입력 버튼으로 언제든 다시 열 수 있으며, AI 추론 중에도 열 수 있다.
- 이미지(PNG/JPEG) 1개와 센서 CSV 1개를 선택하고 업로드한다. 여러 파일·폴더 선택은 현재 화면에서 제공하지 않는다.
- CSV는 헤더 없는 숫자 5열과 시간 1열이며, UTF-8 형식이다. 브라우저는 시간순 두 행 이상, 전체 기간 0 초과를 확인하고 이미지 디코딩을 확인한다. 서버는 Serving과 같은 기준(중복·역행 timestamp 불가, 일정한 간격, 512행 이상, 600x400 또는 1750x1070 이상 이미지)으로 다시 검증한다.
- 업로드하면 이미지·센서 재생과 AI 추론이 동시에 시작된다. 재생은 2배속이며 그래프는 최근 5초 구간을 표시한다. 추론 결과는 재생이 끝난 뒤 표시한다.
- 팝업이 열려 있는 동안 재생을 일시정지하고, 닫으면 같은 위치부터 이어서 재생한다.
- 파일 선택만으로는 진행 중인 분석이 바뀌지 않는다. 새로 업로드하면 기존 재생을 교체하고 이전 요청의 결과는 표시하지 않는다.
- `다시 재생`은 저장된 같은 파일로 새 추론(`replay-predict`)을 요청하고, `초기화`는 현재 테스트를 지운다.
- Set 1~8, 알림 이력 등 다른 화면으로 이동하면 Set test의 재생과 대기 중인 결과를 초기화한다.
- 업로드한 파일과 완료된 결과는 브라우저(IndexedDB)에, 재생 위치는 localStorage에 보관한다. 새로고침하면 화면은 복구하지만 진행 중이던 추론 요청은 이어지지 않는다.
- 기존 Set의 useDashboard는 계속 마운트된 상태이며 백엔드 자동 모니터링도 계속 동작한다.

## 저장

현재 Set test 업로드는 `auto-predict`를 통해 `images/uploads/upload-<UUID>/`, `sensors/uploads/upload-<UUID>/`
(운영: Object Storage)에 저장하고 `measurements`에 `source_type='upload'` 행을 만든다. 추론 결과는 `predictions`에,
경고·위험이면 `alerts`에도 저장한다. 공통 모니터링 세션·알림(`monitoring_alert_events`)과는 독립적이다.

이전 `/api/manual-inputs` 저장소(현재 프런트 미사용)의 동작은 다음과 같다.

- 기본 저장 위치는 백엔드 실행 폴더의 `manual-inputs/`(`MANUAL_INPUT_ROOT`로 변경)이며 `.gitignore`에 포함된다.
- 원본 파일 두 개와 metadata.json을 별도 UUID 폴더에 저장한다. monitoring reset과 독립적이다.
- 기본 총 파일 용량 제한은 512MB(`MANUAL_INPUT_QUOTA_MB`로 변경)이며 초과 시 507을 반환한다. 파일 자동 삭제는 없다.
- 이미지는 PNG/JPEG/WebP, 8MB까지, CSV는 20MB까지 허용한다. 서버는 형식 시그니처와 CSV 전체를 검사한다.
- 파일명은 표시용으로만 저장하며, 실제 저장 경로는 서버가 만든 UUID와 고정 파일명을 사용한다.
- metadata의 예측 필드는 `pending`/null로 고정이며 이 저장소는 추론을 실행하지 않는다.
- 사용자별 계정/권한 구분은 없고 목록은 서비스 사용자 사이에 공유된다.

## API

현재 Set test가 사용하는 API:

| Method | URL | 내용 |
|---|---|---|
| POST | /api/measurements/auto-predict | multipart `image`, `sensor_csv` 업로드 + Serving 추론 + 결과 저장 |
| POST | /api/measurements/{id}/replay-predict | 업로드 성공 건의 같은 파일로 새 추론 (replay Cookie 필요) |
| POST | /api/measurements/{id}/retry | 추론 실패(502) 업로드의 재추론 (retry Cookie 필요) |
| POST | /api/sensors/cutting-segment | 선택한 CSV의 절삭 구간 경계 계산 (DB·Storage 저장 없음) |

백엔드에 남아 있는 이전 사용자 입력 API(현재 프런트 미사용):

| Method | URL | 내용 |
|---|---|---|
| POST | /api/manual-inputs | JSON으로 image_name, sensor_name, image_base64, sensor_base64를 전달 (요청 40MB 이하) |
| GET | /api/manual-inputs | 저장된 입력 목록 |
| GET | /api/manual-inputs/{id} | 입력 메타데이터 |
| GET | /api/manual-inputs/{id}/image | 저장 이미지 |
| GET | /api/manual-inputs/{id}/sensor | 원본 CSV |

이전 API는 별도 multipart 라이브러리 없이 JSON으로 전송한다. Base64로 인해 요청 크기는 원본보다 커진다.
이전에 이 API로 저장한 기록을 브라우저가 기억하고 있으면 재생은 되지만, 새 추론을 하려면 파일을 다시 업로드해야 한다.

## 로컬 확인

1. 백엔드를 재시작한다. reset을 호출하지 않는다. Set test 추론에는 `PREDICTION_API_ENABLED=1`, `AUTO_PREDICTION_ENABLED=1`,
   `AUTO_PREDICTION_ORIGIN`, 32자 이상 `PREDICTION_API_TOKEN`, 실행 중인 Serving이 필요하다. 요청의 Origin·Host가 HTTPS
   `AUTO_PREDICTION_ORIGIN`과 같아야 하고 Cookie도 `Secure`이므로, 브라우저 확인은 같은 HTTPS 주소로 프런트와 백엔드를 제공하는 환경에서 한다.
2. 프런트는 `npm.cmd run build`, `node --test tests/*.test.js`로 확인한다.
3. 업로드 → 이미지/그래프 재생 → 팝업 열기(일시정지)·닫기(재개) → 결과 표시 → 다시 재생 → 새로고침 → 기존 Set 이동 시 초기화를 확인한다.
4. 잘못된 CSV·이미지는 422로 거절되어야 한다. 기존 자동 모니터링 세션/알림이 초기화되지 않아야 한다.

## 운영 배포 시 필수 설정

- 프런트 컨테이너 및 외부 VM Nginx 모두 업로드를 통과하도록 `client_max_body_size`를 설정해야 한다(저장소 Nginx 예시는 `40m`). 실제 운영 VM 설정은 별도로 확인해야 한다.
- `auto-predict`는 Serving 응답을 기다리므로 Nginx 요청 시간 제한이 Backend의 Serving Timeout(180초)보다 짧지 않아야 한다. 프런트는 200초 후 시간 초과로 처리한다.
- 이전 `/api/manual-inputs` 저장소를 계속 운영한다면 `MANUAL_INPUT_ROOT`를 쓰기 가능한 영구 볼륨에 지정해야 컨테이너 재생성 후 파일이 유지된다. `infra/compose/compose.manual-inputs.yaml`은 실제 Compose 파일과 합쳐 사용하는 예시다.

## 검증 범위

2026-11-20 기준 프런트 Node 회귀 테스트 89개, 백엔드 전체 테스트 `277 passed, 10 skipped`.
관련 백엔드 테스트는 `tests/test_manual_inputs.py`, `tests/test_manual_playlists.py`(이전 저장 API),
`tests/test_auto_prediction.py`, `tests/test_manual_replay_capability.py`, `tests/test_manual_replay_prediction.py`,
`tests/test_upload_validation.py`이며 임시 폴더와 Mock을 사용해 기존 DB에 접속하지 않는다.
실제 사용자 브라우저와 운영 Serving·RDS 연동은 별도로 확인한다.
