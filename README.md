# CNC WearPoint Backend

CNC 가공 과정에서 수집한 이미지·센서 데이터와 AI 모델의 예측 결과를 활용해 **공구 마모 상태를 진단하는 CNC WearPoint 서비스의 FastAPI 백엔드**입니다.

React 기반 프론트엔드와 FastAPI를 연동하고, MySQL을 이용해 가공 조건, 측정 데이터, 실제 마모값 및 AI 모델의 최신 예측 결과를 관리합니다.

현재 로컬 개발 환경을 기반으로 기능을 검증하고 있으며, NHN Cloud 환경에서는 App 서버와 RDS를 분리한 인프라 구성을 진행하고 있습니다.

## 관련 문서

프로젝트의 세부 설계와 운영 관련 내용은 목적에 따라 별도 문서로 관리합니다.

- [클라우드 인프라 구성](docs/infrastructure.md)
  NHN Cloud VPC, Subnet, Routing, Security Group, App VM 및 RDS 구성

- [데이터베이스 구성 및 이전 가이드](docs/database.md)
  CNC WearPoint 서비스 DB와 MLflow 메타데이터 DB의 구조, 검증 및 RDS 이전 현황

- [로컬 배포 및 인프라 파일 구성 안내](docs/deployment/infrastructure.md)
  Docker Compose 실행 방법과 배포 관련 파일 구조

---

## 1. 개발 환경

현재 백엔드 개발 환경은 다음과 같습니다.

| 항목 | 구성 |
|---|---|
| Language | Python 3.12.10 |
| Backend | FastAPI |
| Database | MySQL |
| Package Manager | uv |
| Container | Docker |
| API Documentation | Swagger |

### 사전 준비

- [Git](https://git-scm.com/downloads)
- [Python 3.12.10](https://www.python.org/downloads/release/python-31210/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — Docker 실행 시 필요

Windows PowerShell에서 uv를 설치합니다.

```powershell
winget install --id astral-sh.uv -e
```

설치 후 터미널을 다시 열고 정상적으로 설치되었는지 확인합니다.

```powershell
uv --version
```

---

## 2. 로컬 실행

아래 명령은 Windows PowerShell과 프로젝트 저장소 루트를 기준으로 합니다.

### 2.1 프로젝트 Clone

```powershell
git clone https://github.com/Goodee-AIM/cnc-wearpoint-backend.git
cd cnc-wearpoint-backend
```

### 2.2 개발 환경 구성

```powershell
uv sync
```

`pyproject.toml`, `uv.lock`, `.python-version`을 기준으로 Python 가상환경과 필요한 패키지를 구성합니다.

`uv sync`를 사용하므로 별도로 `.venv`를 생성하거나 활성화할 필요는 없습니다.

### 2.3 환경변수 설정

```powershell
Copy-Item .env.example .env
```

생성된 `.env` 파일에서 개발 환경에 필요한 값을 설정합니다.

`.env`에는 Database Password 등 민감정보가 포함될 수 있으므로 **GitHub에 커밋하지 않습니다.**

### 2.4 FastAPI 실행

```powershell
uv run python -m uvicorn app.main:app --reload
```

기본 접속 주소:

```text
http://localhost:8000
```

Swagger API 문서:

```text
http://localhost:8000/docs
```

---

## 3. 주요 API

현재 구현된 주요 API는 다음과 같습니다.

| 주소 | 기능 |
|---|---|
| `/health` | 서버 상태 확인 |
| `/api/test` | React ↔ FastAPI 통신 테스트 |
| `/api/sets` | Set 4~11 목록과 Set별 측정 수 조회 |
| `/api/sets/{set_number}/measurements` | 선택한 Set의 측정·원본 정답·최신 예측 조회 |
| `/api/images/{set_id}` | 서버 이미지 목록 조회 |
| `/api/images/{set_id}/{filename}` | 이미지 파일 조회 |
| `/api/sensors/{set_id}/{filename}` | 센서 CSV 파일 조회 |
| `/docs` | Swagger API 문서 |

정상 응답 예시:

```json
{
  "status": "ok"
}
```

프론트엔드 개발 서버는 기본적으로 다음 주소를 사용합니다.

```text
http://localhost:5173
```

프론트엔드 포트가 변경되는 경우 백엔드 `.env`의 `CORS_ORIGINS` 설정도 함께 변경해야 합니다.

### 3.1 Set 및 측정 데이터

Database 구조는 [sql/cnc/schema.sql](sql/cnc/schema.sql)을 기준으로 관리합니다.

Schema 파일은 신규 Database 초기화에 사용하며, 이미 생성된 Database의 Column을 자동으로 변경하지 않습니다.

- Set 목록의 내부 기본키는 `set_id`를 사용합니다.
- API URL의 `set_number`는 원본 데이터셋의 Set 번호인 4~11을 사용합니다.
- 측정 데이터는 `image_id`, `sensor_id`, `original_wear_um`, `original_type`을 사용합니다.
- AI 예측값은 `predicted_wear_um`으로 관리하여 실제 마모값과 구분합니다.
- 예측 결과에는 `model_version`, `prediction_status`, `predicted_at`을 함께 관리합니다.
- 실제값 또는 예측값이 존재하지 않는 경우 관련 필드는 `null`을 반환합니다.
- 최신 예측은 `predicted_at`, `id`의 내림차순을 기준으로 결정합니다.

측정 조회 API는 Pagination을 지원합니다.

| Parameter | 기본값 | 최대값 |
|---|---:|---:|
| `limit` | 200 | 500 |
| `offset` | 0 | - |

예시:

```text
/api/sets/4/measurements?limit=50&offset=0
```

---

## 4. 데모 예측 데이터 등록

AI 모델과 Backend 연동을 검증하기 위해 CSV 형태의 데모 예측 결과를 Database에 등록할 수 있습니다.

프로젝트 루트에 다음 파일을 준비합니다.

```text
rf_test_predictions.csv
```

필수 Column:

```text
Set
ImageName
Predicted_Wear
```

선택 Column:

```text
SensorName
```

예측 결과를 등록합니다.

```powershell
uv run python import_predictions.py
```

현재 데모 모델 정보는 다음과 같습니다.

| 항목 | 값 |
|---|---|
| Model Name | `rf-csv-demo` |
| Model Version | `rf-csv-demo-v1` |
| Warning Threshold | 50 µm |
| Danger Threshold | 90 µm |

동일한 Measurement, Model Name 및 Model Version에 동일한 예측값이 이미 존재하는 경우 중복 저장하지 않습니다.

모델이 변경되거나 새로운 예측 결과를 관리해야 하는 경우 새로운 `model_version`을 사용합니다.

---

## 5. 자동 테스트

전체 테스트는 다음 명령으로 실행합니다.

```powershell
uv run python -m pytest -q
```

현재 테스트에서는 다음 항목을 확인합니다.

- 기본 API 연결
- Set 및 Measurement API 응답 구조
- Pagination 처리
- 잘못된 요청에 대한 오류 처리
- CSV 예측 데이터 등록
- Model Name 및 Version 구분
- 중복 예측 처리
- Warning / Danger 경계값 처리

Database 관련 회귀 테스트는 Mock Connection, Memory DB 및 임시 CSV를 사용하며 **실제 MySQL 데이터를 변경하지 않도록 구성했습니다.**

---

## 6. Docker 실행

Docker Desktop이 실행 중인 환경에서 Backend Container를 생성할 수 있습니다.

### 6.1 Docker Build용 의존성 생성

```powershell
uv export --format requirements-txt --no-dev --no-emit-project --no-hashes --output-file requirements.txt
```

### 6.2 이미지 Build

```powershell
docker build -t cnc-wearpoint-backend:dev .
```

### 6.3 Container 실행

```powershell
docker run --rm --env-file .env -p 127.0.0.1:8000:8000 cnc-wearpoint-backend:dev
```

기존 프로세스가 8000 Port를 사용하고 있는 경우 먼저 해당 프로세스를 종료해야 합니다.

### 6.4 이미지 Version 관리

| Tag | 용도 |
|---|---|
| `dev` | 로컬 개발 및 테스트 |
| `v0.x` | 기능 검증 후 공유하는 Version |

기존 검증 이미지:

```text
quay.io/melona240/cnc-wearpoint-backend:v0.2
```

Docker 이미지는 기능 검증 또는 배포가 필요한 시점에 생성합니다.

---

## 7. 의존성 관리

팀원 간 개발 환경을 동일하게 유지하고 패키지 Version을 재현하기 위해 **uv**를 사용합니다.

| 파일 | 역할 |
|---|---|
| `pyproject.toml` | 프로젝트 의존성 및 개발 도구 정의 |
| `uv.lock` | 실제 사용 Dependency Version 고정 |
| `requirements.txt` | Docker Build용 자동 생성 파일 |

패키지를 추가하거나 삭제할 때는 다음 명령을 사용합니다.

```powershell
uv add <package>
uv remove <package>
```

`requirements.txt`는 직접 수정하지 않고 `uv export`를 통해 생성합니다.

의존성 관리 방식은 FastAPI 공식 Full Stack Template의 구성을 참고했습니다.

참고: [FastAPI Full Stack Template](https://github.com/fastapi/full-stack-fastapi-template)

---

## 8. Database 및 인프라 구성

서비스 Database는 MySQL을 사용하며 서비스 데이터와 MLflow Metadata를 분리하여 관리합니다.

```text
MySQL
│
├── cnc_wearpoint
│   └── 서비스 데이터
│
└── mlflow
    └── 실험 및 모델 메타데이터
```

현재 NHN Cloud에서는 App 서버와 Database 영역을 분리하여 구성하고 있습니다.

```text
CNC WearPoint Team
        │
        ▼
     Internet
        │
        ▼
   Floating IP
        │
        ▼
     App VM
        │
        │ VPC Internal
        ▼
 RDS for MySQL
```

RDS는 외부 인터넷에 직접 노출하지 않고 Private Network에 배치하여 App Network에서 필요한 Database 접근만 허용하도록 설계했습니다.

세부 내용은 다음 문서에서 확인할 수 있습니다.

- [NHN Cloud 인프라 구성](docs/infrastructure.md)
- [Database 구성 및 RDS 이전](docs/database.md)

---

## 9. 개발 상태

현재 프로젝트의 주요 진행 상태는 다음과 같습니다.

### 완료

- FastAPI 기본 Backend 환경 구성
- React ↔ FastAPI 통신 검증
- API Router 및 환경 설정 분리
- pytest 기반 자동 테스트 구성
- Docker 이미지 Build 및 실행 검증
- Quay.io 이미지 공유 검증
- MySQL 기반 Set 및 Measurement 관리
- 실제 마모값 조회
- 최신 AI 예측 결과 조회
- CSV 기반 데모 예측 결과 등록
- CNC WearPoint 서비스 DB Schema 구성
- MLflow Metadata MySQL Schema 구조 검증
- NHN Cloud VPC 및 App / Database Network 설계
- NHN Cloud App VM 및 RDS 기반 인프라 구성

### 진행 예정

- App VM과 RDS 연결 및 Database 권한 검증
- 로컬 서비스 DB의 RDS 이전
- MLflow Backend Store의 MySQL / RDS 연동 검증
- AI 모델과 FastAPI Prediction API 직접 연동
- 실제 서비스 배포 및 운영 환경 검증

---

## 10. 프로젝트 문서 구조

```text
docs/
├── infrastructure.md
│   └── NHN Cloud 인프라 및 네트워크 구성
│
├── database.md
│   └── 서비스 DB 및 MLflow DB 구성과 이전 현황
│
├── architecture/
│   ├── diagrams/
│   │   └── 인프라 구성도 생성 코드
│   └── images/
│       └── 인프라 구성도
│
└── deployment/
    └── infrastructure.md
        └── Docker Compose 및 배포 파일 관리
```

프로젝트의 실행 방법, 설계 근거 및 인프라 구성을 문서별로 분리하여 관리하고 있습니다.