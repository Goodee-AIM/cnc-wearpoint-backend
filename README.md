# CNC WearPoint Backend

CNC 공구 마모 진단 서비스의 FastAPI 백엔드입니다.

React ↔ FastAPI 통신과 MySQL 기반 Set·측정·최신 예측 조회를 제공하는 초기 개발 단계입니다.

관련 문서:

- [데이터베이스 구성 및 이전 가이드](docs/database.md): CNC·MLflow SQL 파일과 검증·이관 현황
- [인프라 구성 안내](docs/deployment/infrastructure.md): Docker Compose 경로와 실행 방법

## 1. 개발 환경

- Python 3.12.10
- FastAPI
- uv (의존성 관리)
- Docker

**사전 준비**

- [Git](https://git-scm.com/downloads)
- [Python 3.12.10](https://www.python.org/downloads/release/python-31210/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Docker 실행 시 필요)

Windows PowerShell에서 uv 설치:

```powershell
winget install --id astral-sh.uv -e
```

설치 후 터미널을 다시 열고 확인합니다.

```powershell
uv --version
```

## 2. 로컬 실행 (Windows PowerShell)

**① 프로젝트 Clone**

```powershell
git clone https://github.com/Goodee-AIM/cnc-wearpoint-backend.git
cd cnc-wearpoint-backend
```

**② 개발 환경 구성**

```powershell
uv sync
```

`pyproject.toml`, `uv.lock`, `.python-version`을 기준으로 Python 가상환경과 패키지를 구성합니다.

별도로 `.venv`를 생성하거나 활성화할 필요는 없습니다.

**③ 환경변수 설정**

```powershell
Copy-Item .env.example .env
```

`.env` 파일에서 환경에 맞는 설정값을 확인합니다.

`.env`는 GitHub에 업로드하지 않습니다.

**④ FastAPI 실행**

```powershell
uv run python -m uvicorn app.main:app --reload
```

기본 주소: http://localhost:8000

## 3. API 확인

| 주소 | 기능 |
|---|---|
| `/health` | 서버 상태 확인 |
| `/api/test` | 프론트엔드 통신 테스트 |
| `/api/sets` | Set4~11 목록과 Set별 측정 수 조회 |
| `/api/sets/{set_number}/measurements` | 선택한 Set의 측정·원본 정답·최신 예측 조회 |
| `/api/images/{set_id}` | 서버 이미지 목록 조회 (`set4`~`set11`) |
| `/api/images/{set_id}/{filename}` | 이미지 파일 조회 |
| `/api/sensors/{set_id}/{filename}` | 센서 CSV 파일 조회 |
| `/docs` | Swagger API 문서 |

정상 응답 예시:

```json
{"status": "ok"}
```

프론트엔드 개발 서버는 기본적으로 `http://localhost:5173`을 사용합니다. 포트가 다르다면 백엔드 `.env`의 `CORS_ORIGINS`를 수정해야 합니다.

### Set·측정 응답 필드

DB 구조는 [sql/cnc/schema.sql](sql/cnc/schema.sql)을 기준으로 합니다. 스키마 파일은 신규 DB 초기화용이며, 이미 존재하는 DB의 컬럼을 자동으로 변경하지 않습니다.

- Set 목록의 내부 기본키는 `set_id`이고, URL의 `set_number`는 원본 데이터셋 번호(4~11)입니다.
- 측정 응답은 `image_id`, `sensor_id`, `original_wear_um`, `original_type`을 사용합니다. 이전 `source_image_id`, `source_sensor_id`, `actual_wear_um`, `actual_type` 이름은 사용하지 않습니다.
- 예측값 `predicted_wear_um`은 원본 정답과 구분합니다. 모델 버전(`model_version`), 판정 상태(`prediction_status`), 예측 시각(`predicted_at`)을 함께 반환합니다.
- 정답이나 예측이 없는 측정의 관련 필드는 `null`입니다. 최신 예측은 `predicted_at`, `id` 내림차순으로 결정합니다.
- 측정 조회는 `limit`(기본 200, 최대 500), `offset`(기본 0)을 지원합니다. 예: `/api/sets/4/measurements?limit=50&offset=0`.

### 데모 CSV 예측 등록

프로젝트 최상위에 `rf_test_predictions.csv`를 준비한 뒤 아래 명령을 실행합니다. 필수 열은 `Set`, `ImageName`, `Predicted_Wear`이며 `SensorName`은 선택입니다. `.env`에 연결한 DB의 `predictions` 테이블에 데이터를 저장합니다.

```powershell
uv run python import_predictions.py
```

데모 모델 이름은 `rf-csv-demo`, 버전은 `rf-csv-demo-v1`입니다. 같은 측정·모델 이름·버전의 동일한 예측은 다시 저장하지 않습니다. 기존 예측값이 달라지면 새 버전을 지정해야 합니다. 경고·위험 기준은 각각 50 µm, 90 µm이며 기준 이상일 때 해당 상태로 저장합니다.

## 4. 자동 테스트

```powershell
uv run python -m pytest -q
```

기본 연결 테스트와 Set·측정 API 응답 계약, 페이지네이션·오류 처리, CSV 예측 등록의 모델 구분·중복 처리·위험도 경계값을 검사합니다. DB를 사용하는 회귀 테스트는 mock 연결, 메모리 DB와 임시 CSV로 실행하며 실제 MySQL 데이터를 수정하지 않습니다.

## 5. Docker 실행 (선택)

Docker Desktop이 실행 중이어야 합니다.

**① Docker 빌드용 의존성 파일 생성**

```powershell
uv export --format requirements-txt --no-dev --no-emit-project --no-hashes --output-file requirements.txt
```

**② 이미지 빌드 및 실행**

```powershell
docker build -t cnc-wearpoint-backend:dev .
docker run --rm --env-file .env -p 127.0.0.1:8000:8000 cnc-wearpoint-backend:dev
```

기존 8000번 포트를 사용하는 서버가 있다면 먼저 종료해야 합니다.

**③ 이미지 버전 관리**

- `dev`: 로컬 개발 및 테스트용
- `v0.x`: 검증 후 Quay.io에 공유하는 버전
- 기존 공개 이미지: `quay.io/melona240/cnc-wearpoint-backend:v0.2`

Docker 이미지는 기능 검증 또는 배포가 필요할 때 빌드합니다.

## 6. 의존성 관리

팀원 간 패키지 버전을 통일하고 개발 환경을 재현하기 위해 **uv**를 사용합니다.

| 파일 | 역할 |
|---|---|
| `pyproject.toml` | 프로젝트 의존성 및 개발 도구 정의 |
| `uv.lock` | 의존성 버전 고정 |
| `requirements.txt` | Docker 빌드용 자동 생성 파일 |

패키지 변경은 `uv add`, `uv remove`로 관리하며, `requirements.txt`는 직접 수정하지 않습니다.

FastAPI 공식 풀스택 템플릿의 의존성 관리 방식을 참고했습니다.

참고: [FastAPI Full Stack Template](https://github.com/fastapi/full-stack-fastapi-template)

## 7. 개발 상태

- FastAPI 기본 환경 구성 완료
- React ↔ FastAPI 통신 검증 완료
- API 라우터 및 환경 설정 분리 완료
- pytest 자동 테스트 구성 완료
- Docker 및 Quay.io 이미지 검증 완료
- MySQL Set·측정·정답·최신 예측 조회 구현
- CSV 데모 예측 결과 등록 지원
- MLflow 연동 예정
- AI 예측 API 구현 예정
