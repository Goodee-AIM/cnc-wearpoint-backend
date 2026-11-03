# CNC WearPoint Backend

CNC 공구 마모 진단 서비스의 FastAPI 백엔드입니다.

현재는 React ↔ FastAPI 통신과 기본 API 테스트를 완료한 초기 개발 단계입니다.

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
| `/docs` | Swagger API 문서 |

정상 응답 예시:

```json
{"status": "ok"}
```

프론트엔드 개발 서버는 기본적으로 `http://localhost:5173`을 사용합니다. 포트가 다르다면 백엔드 `.env`의 `CORS_ORIGINS`를 수정해야 합니다.

## 4. 자동 테스트

```powershell
uv run python -m pytest -q
```

현재 `/health`, `/api/test`에 대한 기본 테스트를 제공합니다.

예상 결과:

```text
2 passed
```

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
- MySQL 및 MLflow 연동 예정
- AI 예측 API 구현 예정