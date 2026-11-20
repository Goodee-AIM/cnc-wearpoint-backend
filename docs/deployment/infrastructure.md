# CNC WearPoint 로컬 배포 및 인프라 파일 구성 안내

> **기준일:** 2026-11-20  
> 운영 환경은 Kubernetes가 아닌 **NHN Cloud App VM 1대의 Docker / Docker Compose** 기반입니다.

## 1. 문서 목적

이 문서는 CNC WearPoint 프로젝트의 **로컬 개발 환경에서 사용하는 Docker Compose 설정과 배포 관련 파일 구조**, 그리고 운영 VM의 배포 파일 위치를 설명합니다.

Docker Compose 실행 방법, 환경변수 관리, 데이터베이스 초기화·Migration 파일 및 운영 배포 관련 파일의 관리 위치를 정리합니다.

NHN Cloud의 VPC, Subnet, Routing, Security Group, App VM 및 RDS 구성과 같은 실제 클라우드 인프라 설계는 [클라우드 인프라 구성 문서](../infrastructure.md)를 참고합니다.

---

## 2. 디렉터리 구조

`infra/` 디렉터리는 CNC WearPoint 프로젝트의 Docker Compose 설정을 관리합니다.

이 문서에서 사용하는 경로와 명령어는 저장소 루트를 기준으로 합니다.

| 경로 | 용도 |
|---|---|
| [infra/compose/compose.mysql.yaml](../../infra/compose/compose.mysql.yaml) | 로컬 MySQL 8.4 실행용 Docker Compose 설정 (`sql/cnc/schema.sql`로 초기화) |
| [infra/compose/compose.yaml](../../infra/compose/compose.yaml) | 로컬 MySQL 8.4 실행용 설정. 초기 Baseline인 `sql/schema.sql`을 Mount하므로 현재 Schema 기준으로는 `compose.mysql.yaml`을 사용 |
| [infra/compose/compose.deploy.yaml](../../infra/compose/compose.deploy.yaml) | Backend Build + Frontend 정적 파일(Nginx)을 함께 띄우는 로컬 통합 확인용 설정. 운영 배포에는 사용하지 않음 |
| [infra/compose/nginx.conf](../../infra/compose/nginx.conf) | `compose.deploy.yaml`의 Frontend Nginx Container 설정 (`/api/`, `/health` → Backend) |
| [infra/compose/compose.manual-inputs.yaml](../../infra/compose/compose.manual-inputs.yaml) | 사용자 입력 저장 Volume(`MANUAL_INPUT_ROOT`)을 추가하는 Override. 실제 Backend Compose 파일과 병합해서 사용 |
| [Dockerfile](../../Dockerfile) | Backend 이미지 Build |
| [ml/serving](../../ml/serving) | Model Serving 서비스 코드와 Dockerfile (Python 3.11 + PyTorch CPU, Port 8001) |
| [sql/cnc](../../sql/cnc) | 서비스 DB 기준 Schema와 모니터링 관련 Migration |
| [migrations](../../migrations) | 사용자 업로드·예측 Claim 관련 Migration |
| [scripts](../../scripts) | 운영자 비밀번호 Hash 생성(`hash_prediction_password.py`), 중단된 예측 Claim 복구(`recover_stale_prediction.py`) |
| [.gitlab-ci.yml](../../.gitlab-ci.yml) | Backend / Serving 이미지 Build·승격 및 Backend 운영 배포 Pipeline |
| [.github/workflows/sync-to-gitlab.yml](../../.github/workflows/sync-to-gitlab.yml) | GitHub `main` 및 `v*` / `serving-v*` Tag를 GitLab으로 동기화 |
| [docs/deployment](.) | 로컬 실행 및 서비스 배포 관련 문서 |
| [docs/infrastructure.md](../infrastructure.md) | NHN Cloud 인프라 및 네트워크 구성 문서 |

### Kubernetes 미사용

현재 운영 환경은 Docker / Docker Compose만 사용하며 Kubernetes는 사용하지 않습니다.

이전 문서에서 향후 확장 위치로 안내했던 `infra/k8s/` 디렉터리는 Git에 추적된 적이 없으며(Untracked) 2026-11-20 삭제되었습니다. 저장소에는 Kubernetes Manifest가 없습니다.

Kubernetes는 서비스 규모와 운영 요구사항상 필요성이 확인될 경우에만 검토하는 향후 확장 항목입니다.

CI/CD는 GitHub Actions(GitHub → GitLab 동기화)와 GitLab CI(이미지 Build·승격·배포)로 구성되어 있습니다. 자세한 내용은 [8. 운영 배포 구성](#8-운영-배포-구성)과 [README 9. 백엔드 CI/CD](../../README.md#9-백엔드-cicd)를 참고합니다.

---

## 3. Docker Compose 실행 방법

모든 명령어는 프로젝트 최상위 디렉터리에서 실행합니다.

### 3.1 로컬 개발 경로 예시

```text
C:\Users\90\PycharmProjects\cnc-wearpoint-backend
```

개별 팀원의 실제 프로젝트 경로는 환경에 따라 달라질 수 있습니다.

### 3.2 Docker Compose 프로젝트 이름

현재 로컬 MySQL 환경의 Docker Compose 프로젝트 이름은 다음과 같습니다.

| 구분 | 프로젝트 이름 |
|---|---|
| 기본 개발 환경 | `cnc-wearpoint-backend` |

동일한 프로젝트 이름을 유지하여 Docker Network와 Volume을 일관되게 관리합니다.

### 3.3 MySQL Compose 설정 확인

Docker Compose 설정이 올바른지 검사합니다.

```powershell
docker compose --project-directory . --env-file .env -p cnc-wearpoint-backend -f infra/compose/compose.mysql.yaml config --quiet
```

현재 컨테이너 상태를 확인합니다.

```powershell
docker compose --project-directory . --env-file .env -p cnc-wearpoint-backend -f infra/compose/compose.mysql.yaml ps -a
```

설정 검사 명령에서는 환경변수 값을 화면에 직접 출력하지 않습니다.

- `--project-directory .`은 프로젝트 최상위 디렉터리를 기준으로 사용합니다.
- `--env-file .env`를 통해 로컬 환경변수를 불러옵니다.
- `-p cnc-wearpoint-backend`로 Docker Compose 프로젝트 이름을 고정합니다.
- `-f infra/compose/compose.mysql.yaml`로 사용할 Compose 파일을 명시합니다.

---

## 4. 환경변수 관리

`.env`와 `.env.example` 파일은 프로젝트 최상위 디렉터리에서 관리합니다.

| 파일 | 역할 |
|---|---|
| `.env` | 실제 로컬 개발 환경의 접속 정보 및 환경변수 |
| `.env.example` | 팀원에게 제공하는 환경변수 예시 |

기본 MySQL Compose 환경에서는 다음 환경변수를 사용합니다.

```text
MYSQL_ROOT_PASSWORD
DB_NAME
DB_USER
DB_PASSWORD
```

`.env.example`을 복사하여 사용하는 경우 각 개발 환경에 맞는 값을 입력해야 합니다.

Backend의 예측·모니터링 관련 환경변수(`SERVING_URL`, `PREDICTION_*`, `AUTO_PREDICTION_*`, `MONITORING_*` 등)와 기본값은 [README 2.3 환경변수 설정](../../README.md#23-환경변수-설정)을 참고합니다. 예측 관련 기능은 기본값이 모두 비활성화(`0`)입니다.

`.env`에는 데이터베이스 비밀번호와 같은 민감정보가 포함될 수 있으므로 **GitHub에 커밋하지 않습니다.**

환경별 비밀번호, API Key, Token 등의 민감정보 역시 소스코드에 직접 작성하지 않고 환경변수로 관리합니다. 운영 환경의 env 파일은 App VM의 `/etc/cnc-wearpoint/` 및 `/etc/mlflow/`에서 관리합니다([8. 운영 배포 구성](#8-운영-배포-구성)).

---

## 5. 데이터베이스 초기화 파일

### 5.1 CNC WearPoint 서비스 DB

서비스 데이터베이스의 기본 스키마와 Migration은 다음 파일에서 관리합니다.

| 파일 | 역할 |
|---|---|
| [sql/cnc/schema.sql](../../sql/cnc/schema.sql) | `cnc_wearpoint`의 테이블(기본 5개 + 모니터링 테이블), 컬럼 설명 및 제약조건을 정의하는 신규 DB 초기화 SQL |
| [sql/cnc/migrations](../../sql/cnc/migrations) | 기존 DB용 공통 모니터링·알림·모니터링 추론·재생 Gate Migration |
| [migrations](../../migrations) | 기존 DB용 사용자 업로드(`source_type`, `input_issue_reason`)와 예측 Claim(`prediction_claim_id`, `prediction_started_at`) Migration |
| [sql/schema.sql](../../sql/schema.sql) | 2026-11-05 초기 Baseline (현재 Column 이름과 다름, 기준 Schema 아님) |
| [sql/mlflow/mlflow.sql](../../sql/mlflow/mlflow.sql) | MLflow 메타데이터 DB의 로컬 구조 스냅샷 |

기본 MySQL Compose(`compose.mysql.yaml`)는 다음 파일을 MySQL 초기화 디렉터리에 읽기 전용으로 연결합니다.

```text
./sql/cnc/schema.sql
→
/docker-entrypoint-initdb.d/01-schema.sql
```

해당 초기화 SQL은 **MySQL 데이터 디렉터리가 비어 있는 최초 컨테이너 생성 시점에 적용**됩니다.

이미 생성된 Docker Volume을 사용하고 있는 경우 `schema.sql`을 수정하더라도 기존 데이터베이스의 구조가 자동으로 변경되지는 않습니다.

기존 데이터베이스의 스키마 변경이 필요한 경우 Migration SQL을 날짜 순서대로 명시적으로 적용합니다.

> **주의:** 현재 `sql/cnc/schema.sql`에는 루트 `migrations/`의 `measurements` Column(`source_type`, `input_issue_reason`, `prediction_claim_id`, `prediction_started_at`)과 `set_id` NULL 허용 변경이 반영되어 있지 않습니다. 현재 Backend는 이 Column을 사용하므로, 신규 로컬 DB도 초기화 후 루트 `migrations/`의 SQL을 추가로 적용해야 합니다. 테이블과 Column 설명은 [데이터베이스 구성 및 이전 가이드](../database.md#4-cnc-wearpoint-서비스-db)를 참고합니다.

### 5.2 MLflow 스키마

`sql/mlflow/mlflow.sql`은 MLflow 메타데이터 구조를 확인하기 위해 보관하는 로컬 스키마 스냅샷입니다.

현재 CNC 서비스 DB의 Docker 자동 초기화 과정에는 포함하지 않습니다.

MLflow 스키마에는 환경에 따라 주의가 필요한 `DROP TABLE`, `DEFINER`, DB 선택 등의 요소가 포함될 수 있으므로 실제 환경에 적용하기 전에 별도의 검증이 필요합니다.

자세한 내용은 [데이터베이스 구성 및 이전 가이드](../database.md)를 참고합니다.

---

## 6. 로컬 데이터 및 백업 관리

원본 데이터, 데이터베이스 백업 및 대용량 파일은 애플리케이션 소스코드와 분리하여 관리합니다.

현재 로컬 MySQL 백업 파일은 프로젝트 외부에서 관리합니다.

```text
C:\Users\90\CNC-WearPoint-Backups\
```

예시:

```text
C:\Users\90\CNC-WearPoint-Backups\cnc_wearpoint_backup.sql
```

다음과 같은 데이터는 Git 저장소에 직접 포함하지 않는 것을 원칙으로 합니다.

- 실제 데이터베이스 백업
- 원본 이미지 및 센서 데이터
- 대용량 학습 데이터
- 모델 Artifact
- 비밀번호 및 Token이 포함된 설정 파일 (예: `.env`, `ml/serving/.env.inference.local`)
- 개인 또는 운영 환경에 종속된 데이터

Git 저장소에는 애플리케이션 코드, 검토된 DB Schema, 배포 설정 및 문서를 중심으로 관리합니다.

> `ml/serving`에는 `.dockerignore`가 없고 Dockerfile이 `COPY . .`를 실행하므로, 로컬에서 `docker build ml/serving`을 실행하면 Git에서 제외된 `.env.inference.local`이 이미지에 포함될 수 있습니다. CI는 Clean Checkout에서 Build하므로 영향이 없습니다.

---

## 7. NHN Cloud 배포 연계

현재 NHN Cloud에는 CNC WearPoint 서비스를 위한 운영 환경을 구성했습니다.

구성된 주요 영역은 다음과 같습니다.

- CNC WearPoint 전용 VPC
- App Network
- Database Network
- App VM (Docker / Docker Compose)
- RDS for MySQL
- Object Storage
- Internet Gateway
- Route Table
- Security Group

자세한 구성과 네트워크 통신 구조는 [클라우드 인프라 구성 문서](../infrastructure.md)를 참고합니다.

이 저장소의 `infra/compose/` 파일은 **로컬 개발 및 검증 환경**을 기준으로 합니다.

운영 Compose 파일은 저장소가 아니라 App VM에서 관리합니다(`/opt/cnc-wearpoint/backend`, `/opt/cnc-wearpoint/serving/compose.yaml`). 운영 Compose 파일을 저장소에서 관리하는 것은 진행 예정 항목입니다.

---

## 8. 운영 배포 구성

### 8.1 App VM 배포 파일 위치

```text
/opt/cnc-wearpoint/backend/                 # Backend 운영 Compose Project (GitLab CI deploy_backend가 사용)
/opt/cnc-wearpoint/serving/compose.yaml     # Model Serving 실행 정의 (별도 Compose Project, 수동 운영)
/etc/cnc-wearpoint/*.env                    # Backend 등 운영 Secret
/etc/cnc-wearpoint/inference.env            # Serving용 env (root 전용)
/etc/mlflow/mlflow.env                      # MLflow Tracking Server용 env
```

### 8.2 Backend 배포 (GitLab CI)

| 트리거 | GitLab CI Job | 동작 |
|---|---|---|
| `main` Commit | `build_image` | Backend 이미지를 Build하여 Commit SHA Tag로 Quay.io에 게시 |
| `vX.Y.Z` Tag | `promote_image`, `deploy_backend` | 같은 Commit의 SHA 이미지를 `vX.Y.Z`·`latest`로 승격한 뒤 `/opt/cnc-wearpoint/backend`에서 `docker compose pull` / `up -d --no-build --remove-orphans` 실행 |

`deploy_backend`는 VM 내부 `/health`, 외부 HTTPS `/health`, `/api/sets`를 확인합니다. `promote_image`는 같은 Commit의 SHA 이미지를 Pull하므로, `main` Push 후 SHA 이미지가 게시된 다음에 Version Tag를 Push해야 합니다. 2026-11-20 기준 최신 운영 Backend는 `v0.1.12`입니다.

### 8.3 Model Serving 운영 (수동)

| 트리거 | GitLab CI Job | 동작 |
|---|---|---|
| `main` Commit (`ml/serving/**` 변경 시) | `build_serving_image` | Serving 이미지를 Build하여 Commit SHA Tag로 게시 |
| `serving-vX.Y.Z` Tag | `promote_serving_image` | 같은 Commit의 Serving SHA 이미지를 `vX.Y.Z`·`latest`로 승격 |

**Serving 배포 Job은 없습니다.** Serving Container(`cnc-wearpoint-serving`, `127.0.0.1:8001`, 외부 Network `compose_default`)의 이미지 교체와 재생성은 운영 VM에서 수동으로 수행합니다. Backend와 다른 Compose Project이므로 `deploy_backend`가 Serving을 재생성하거나 제거하지 않습니다.

Serving은 기동 시 한 번만 `MODEL_ALIAS`를 MLflow Registry Version으로 해석하며 Reload API는 없습니다. env 파일은 root 전용이므로 `sudo`로 실행하고, 환경변수 변경은 `docker restart`가 아니라 재생성으로 반영합니다.

```bash
cd /opt/cnc-wearpoint/serving
sudo docker compose up -d --force-recreate --pull never serving
curl -s http://127.0.0.1:8001/health
```

2026-11-20부터 운영 Serving은 `MODEL_ALIAS=candidate-opt`(`cnc-wearpoint-multitask` Version 2)를 사용합니다. 모델 전환·롤백은 [모델 승격·롤백 Runbook](../model-lifecycle/MODEL_PROMOTION_ROLLBACK_RUNBOOK.md), Serving 운영 상세는 [README 8.8](../../README.md#88-model-serving-운영)을 따릅니다.

### 8.4 MLflow Tracking Server

MLflow Tracking Server는 Docker가 아닌 App VM의 Python venv + systemd 서비스로 실행합니다(`127.0.0.1:5000`, Nginx `/mlflow/` 경로로 외부 제공). Metadata는 RDS MySQL(`mlflow`, `mlflow_auth`), Artifact는 Object Storage(`cnc-wearpoint-mlflow`)에 저장하며 MLflow Artifact Proxy를 통해 제공합니다.

MLflow를 다른 환경으로 이전할 경우 **Backend Store와 Artifact Store를 구분하여 관리해야 합니다.**

- Backend Store: Experiment, Run, Parameter, Metric, Tag, Model Registry, Model Version, Alias 등 메타데이터
- Artifact Store: 학습된 모델, 모델 가중치, MLmodel 파일, 실험 산출물

Backend Store의 데이터만 MySQL로 이전한다고 해서 MLflow 전체 데이터가 이전되는 것은 아니므로, **메타데이터와 Artifact를 각각 확인하고 누락 없이 이전해야 합니다.**

MLflow 데이터베이스 이전 결과는 [데이터베이스 구성 및 이전 가이드](../database.md)를 참고합니다.

---

## 9. 현재 배포 구조

현재 로컬 개발 환경과 NHN Cloud 운영 환경은 다음과 같이 분리되어 있습니다.

```text
Local Development
│
├── FastAPI (uv run uvicorn)
├── Docker Compose
└── Local MySQL
        │
        │ GitHub Push → GitHub Actions → GitLab CI → Quay.io
        ▼
NHN Cloud
│
├── App VM (Docker / Docker Compose)
│   ├── Host Nginx (HTTPS)
│   ├── Frontend Container
│   ├── Backend Container          ← GitLab CI deploy_backend (vX.Y.Z)
│   ├── Model Serving Container    ← 수동 운영 (/opt/cnc-wearpoint/serving)
│   ├── MLflow Tracking Server     ← systemd
│   └── GitLab Runner (cnc-wp-runner)
│
├── RDS for MySQL
│   ├── cnc_wearpoint
│   ├── mlflow
│   └── mlflow_auth
│
└── Object Storage
    ├── cnc-wearpoint-data
    └── cnc-wearpoint-mlflow
```

Kubernetes는 사용하지 않습니다. 필요성이 확인될 경우 별도로 검토합니다.

---

## 10. 문서 역할 구분

프로젝트의 인프라와 데이터베이스 관련 문서는 다음과 같이 역할을 구분합니다.

| 문서 | 역할 |
|---|---|
| [README.md](../../README.md) | 프로젝트 소개, 로컬 실행, CI/CD 및 Model Serving 운영 개요 |
| [docs/infrastructure.md](../infrastructure.md) | NHN Cloud 인프라, 네트워크 및 보안 구성 |
| [docs/database.md](../database.md) | 서비스 DB 및 MLflow DB 구조와 이전 현황 |
| [docs/deployment/infrastructure.md](.) | Docker Compose 및 배포 관련 파일 관리 방법 |
| [docs/model-lifecycle](../model-lifecycle) | 모델 생명주기 현재 상태, 테스트 계획, 승격·롤백 Runbook, 검증 보고서 |
| [ml/serving/README.md](../../ml/serving/README.md) | Model Serving 서비스 |

문서의 역할을 분리하여 클라우드 인프라 설계, 데이터베이스 구성, 로컬 실행 및 배포 방법이 서로 중복되지 않도록 관리합니다.

---

## 11. 참고 문서

- [Docker Compose 공식 문서](https://docs.docker.com/reference/cli/docker/compose/)
- [Docker Compose 프로젝트 이름 관리](https://docs.docker.com/compose/how-tos/project-name/)
- [Docker Compose 설정 검사](https://docs.docker.com/reference/cli/docker/compose/config/)
- [MLflow Artifact Store 공식 문서](https://mlflow.org/docs/latest/self-hosting/architecture/artifact-store/)
