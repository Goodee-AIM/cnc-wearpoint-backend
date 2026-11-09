# CNC WearPoint 로컬 배포 및 인프라 파일 구성 안내

## 1. 문서 목적

이 문서는 CNC WearPoint 프로젝트의 **로컬 개발 환경에서 사용하는 Docker Compose 설정과 배포 관련 파일 구조**를 설명합니다.

Docker Compose 실행 방법, 환경변수 관리, 데이터베이스 초기화 파일 및 향후 배포 관련 파일의 관리 위치를 정리합니다.

NHN Cloud의 VPC, Subnet, Routing, Security Group, App VM 및 RDS 구성과 같은 실제 클라우드 인프라 설계는 [클라우드 인프라 구성 문서](../infrastructure.md)를 참고합니다.

---

## 2. 디렉터리 구조

`infra/` 디렉터리는 CNC WearPoint 프로젝트의 Docker Compose 설정과 향후 배포에 필요한 인프라 관련 파일을 관리합니다.

이 문서에서 사용하는 경로와 명령어는 저장소 루트를 기준으로 합니다.

| 경로 | 용도 |
|---|---|
| [infra/compose/compose.mysql.yaml](../../infra/compose/compose.mysql.yaml) | 현재 로컬 MySQL 실행을 위한 Docker Compose 설정 |
| [infra/k8s/base/backend](../../infra/k8s/base/backend) | 향후 FastAPI Kubernetes 배포 설정을 관리할 위치 |
| [infra/k8s/base/mysql](../../infra/k8s/base/mysql) | 향후 MySQL Kubernetes 배포 설정을 관리할 위치 |
| [infra/k8s/base/mlflow](../../infra/k8s/base/mlflow) | 향후 MLflow Kubernetes 배포 설정을 관리할 위치 |
| [infra/k8s/overlays/nhncloud](../../infra/k8s/overlays/nhncloud) | 향후 NHN Cloud Kubernetes 환경별 설정을 관리할 위치 |
| [scripts](../../scripts) | 운영 및 관리 자동화 스크립트를 관리할 위치 |
| [docs/deployment](.) | 로컬 실행 및 서비스 배포 관련 문서 |
| [docs/infrastructure.md](../infrastructure.md) | NHN Cloud 인프라 및 네트워크 구성 문서 |

### Kubernetes 확장 계획

현재 Kubernetes 관련 디렉터리는 향후 확장을 고려해 구조만 마련한 상태이며, 실제 배포 가능한 Kubernetes 설정은 아직 포함하지 않습니다.

컨테이너 이미지 저장소, 도메인, 대상 클러스터 및 배포 방식이 확정되면 Kubernetes Manifest를 추가할 예정입니다.

Kubernetes 관련 YAML 파일은 `infra/k8s/` 하위에서 관리하고, 환경별 설정이 필요한 경우 Overlay를 사용하여 분리할 계획입니다.

향후 GitHub Actions를 도입할 경우 CI/CD Workflow는 `.github/workflows/` 디렉터리에서 관리합니다.

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

`.env`에는 데이터베이스 비밀번호와 같은 민감정보가 포함될 수 있으므로 **GitHub에 커밋하지 않습니다.**

환경별 비밀번호, API Key, Token 등의 민감정보 역시 소스코드에 직접 작성하지 않고 환경변수로 관리합니다.

---

## 5. 데이터베이스 초기화 파일

### 5.1 CNC WearPoint 서비스 DB

서비스 데이터베이스의 기본 스키마는 다음 파일에서 관리합니다.

```text
sql/cnc/schema.sql
```

| 파일 | 역할 |
|---|---|
| [sql/cnc/schema.sql](../../sql/cnc/schema.sql) | `cnc_wearpoint`의 테이블, 컬럼 설명 및 제약조건을 정의하는 신규 DB 초기화 SQL |
| [sql/mlflow/mlflow.sql](../../sql/mlflow/mlflow.sql) | MLflow 메타데이터 DB의 로컬 구조 스냅샷 |

기본 MySQL Compose는 다음 파일을 MySQL 초기화 디렉터리에 읽기 전용으로 연결합니다.

```text
./sql/cnc/schema.sql
→
/docker-entrypoint-initdb.d/01-schema.sql
```

해당 초기화 SQL은 **MySQL 데이터 디렉터리가 비어 있는 최초 컨테이너 생성 시점에 적용**됩니다.

이미 생성된 Docker Volume을 사용하고 있는 경우 `schema.sql`을 수정하더라도 기존 데이터베이스의 구조가 자동으로 변경되지는 않습니다.

기존 데이터베이스의 스키마 변경이 필요한 경우 별도의 Migration 절차를 사용해야 합니다.

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
- 비밀번호 및 Token이 포함된 설정 파일
- 개인 또는 운영 환경에 종속된 데이터

Git 저장소에는 애플리케이션 코드, 검토된 DB Schema, 배포 설정 및 문서를 중심으로 관리합니다.

---

## 7. NHN Cloud 배포 연계

현재 NHN Cloud에는 CNC WearPoint 서비스를 위한 기본 인프라 환경을 구성했습니다.

구성된 주요 영역은 다음과 같습니다.

- CNC WearPoint 전용 VPC
- App Network
- Database Network
- App VM
- RDS for MySQL
- Internet Gateway
- Route Table
- Security Group

자세한 구성과 네트워크 통신 구조는 [클라우드 인프라 구성 문서](../infrastructure.md)를 참고합니다.

현재 이 문서에서 다루는 Docker Compose 환경은 **로컬 개발 및 검증 환경**을 기준으로 합니다.

따라서 로컬 Docker Compose 설정을 그대로 클라우드 운영 설정으로 사용하는 것이 아니라, 실제 NHN Cloud 배포 단계에서는 클라우드 환경에 맞는 환경변수와 배포 설정을 분리하여 관리할 예정입니다.

필요한 경우 다음과 같이 NHN Cloud 전용 Compose 파일을 추가할 수 있습니다.

```text
infra/compose/
├── compose.mysql.yaml
└── compose.nhncloud.yaml
```

다만 클라우드 전용 Compose 파일은 실제 배포 요구사항이 확정된 이후 추가합니다.

---

## 8. MLflow 이전 시 고려사항

MLflow를 로컬 또는 기존 환경에서 NHN Cloud로 이전할 경우 **Backend Store와 Artifact Store를 구분하여 관리해야 합니다.**

### Backend Store

실험 및 모델 관리에 필요한 메타데이터를 저장합니다.

주요 데이터는 다음과 같습니다.

- Experiment
- Run
- Parameter
- Metric
- Tag
- Model Registry
- Model Version

### Artifact Store

학습 과정에서 생성되는 실제 파일을 저장합니다.

예를 들면 다음과 같습니다.

- 학습된 모델
- 모델 가중치
- MLmodel 파일
- 실험 산출물

Backend Store의 데이터만 MySQL로 이전한다고 해서 MLflow 전체 데이터가 이전되는 것은 아닙니다.

따라서 MLflow 이전 시에는 **메타데이터와 Artifact를 각각 확인하고 누락 없이 이전해야 합니다.**

MLflow 데이터베이스 이전에 대한 자세한 내용은 [데이터베이스 구성 및 이전 가이드](../database.md)를 참고합니다.

---

## 9. 향후 배포 구조

현재 단계에서는 로컬 개발 환경과 NHN Cloud 기본 인프라 환경을 분리하여 관리합니다.

```text
Local Development
│
├── FastAPI
├── Docker Compose
└── Local MySQL
        │
        │ 개발 및 검증
        ▼
NHN Cloud
│
├── App VM
└── RDS for MySQL
```

Kubernetes는 현재 즉시 도입하지 않고 프로젝트 규모와 운영 요구사항에 따라 이후 단계에서 적용할 예정입니다.

필요성이 확인되면 `infra/k8s/` 디렉터리를 기준으로 배포 설정을 추가합니다.

---

## 10. 문서 역할 구분

프로젝트의 인프라와 데이터베이스 관련 문서는 다음과 같이 역할을 구분합니다.

| 문서 | 역할 |
|---|---|
| [README.md](../../README.md) | 프로젝트 소개 및 로컬 실행 방법 |
| [docs/infrastructure.md](../infrastructure.md) | NHN Cloud 인프라, 네트워크 및 보안 구성 |
| [docs/database.md](../database.md) | 서비스 DB 및 MLflow DB 구조와 이전 현황 |
| [docs/deployment/infrastructure.md](.) | Docker Compose 및 배포 관련 파일 관리 방법 |

문서의 역할을 분리하여 클라우드 인프라 설계, 데이터베이스 구성, 로컬 실행 및 배포 방법이 서로 중복되지 않도록 관리합니다.

---

## 11. 참고 문서

- [Docker Compose 공식 문서](https://docs.docker.com/reference/cli/docker/compose/)
- [Docker Compose 프로젝트 이름 관리](https://docs.docker.com/compose/how-tos/project-name/)
- [Docker Compose 설정 검사](https://docs.docker.com/reference/cli/docker/compose/config/)
- [MLflow Artifact Store 공식 문서](https://mlflow.org/docs/latest/self-hosting/architecture/artifact-store/)