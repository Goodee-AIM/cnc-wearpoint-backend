# CNC WearPoint Backend

CNC 공구 마모 진단 서비스의 FastAPI 백엔드입니다.

현재는 프론트엔드와의 API 통신을 검증한 초기 개발 단계입니다.

## 1. 개발 환경

- Python 3.12.10
- FastAPI
- Uvicorn
- Docker

## 2. 로컬 실행 (Windows PowerShell)

**가상환경 생성 및 활성화**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**패키지 설치**

```powershell
pip install -r requirements.txt
```

**환경변수 설정**

```powershell
Copy-Item .env.example .env
```

**FastAPI 실행**

```powershell
python -m uvicorn main:app --reload
```

## 3. API 확인

| 주소 | 기능 |
|---|---|
| `/health` | 서버 상태 확인 |
| `/api/test` | 프론트엔드 통신 테스트 |
| `/docs` | Swagger API 문서 |

기본 주소: `http://localhost:8000`

## 4. Docker 실행

```bash
docker build -t cnc-wearpoint-backend:v0.1 .
docker run --rm --env-file .env -p 8000:8000 cnc-wearpoint-backend:v0.1
```

현재 Docker 이미지의 버전 태그 `v0.1`은 로컬 빌드 예시입니다.

## 5. 개발 상태

- FastAPI 기본 환경 구성 완료
- React ↔ FastAPI 통신 확인 완료
- MySQL 및 MLflow 연동 예정
- AI 예측 API 구현 예정
