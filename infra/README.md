# CNC WearPoint 인프라 구성 안내

## 1. 디렉터리 구조

이 디렉터리는 CNC WearPoint 프로젝트의 Docker Compose 설정과 향후 클라우드 배포에 필요한 인프라 관련 파일을 관리합니다.

| 경로 | 용도 |
|---|---|
| `compose/compose.yaml` | 현재 로컬 MySQL 실행을 위한 Docker Compose 설정 |
| `compose/compose.restore.yaml` | MySQL 백업·복원 검증을 위한 독립적인 Docker Compose 설정 |
| `k8s/base/backend` | 향후 FastAPI Kubernetes 배포 설정 |
| `k8s/base/mysql` | 향후 MySQL Kubernetes 배포 설정 |
| `k8s/base/mlflow` | 향후 MLflow Kubernetes 배포 설정 |
| `k8s/overlays/nhncloud` | 향후 NHN Cloud 환경별 Kubernetes 설정 |
| `../scripts` | 운영 및 관리 자동화 스크립트 |
| `../docs/deployment` | 서비스 배포 및 클라우드 이전 관련 문서 |

### Kubernetes 확장 계획

현재 Kubernetes 관련 디렉터리는 향후 확장을 위한 자리만 마련한 상태이며, 실제 배포 가능한 설정은 포함되어 있지 않습니다.

컨테이너 이미지, 저장소, 도메인 및 대상 클러스터가 확정되면 Kubernetes 매니페스트를 추가할 예정입니다.

NHN Cloud VM에서 Docker Compose를 먼저 사용하는 경우, 추후 `compose/compose.nhncloud.yaml` 파일을 추가하여 클라우드 환경에 필요한 설정을 분리할 수 있습니다.

인프라 관련 YAML 파일은 `infra/` 디렉터리에서 관리합니다.

향후 GitHub Actions를 도입할 경우 워크플로 파일은 `.github/workflows/` 디렉터리에서 관리합니다.

---

## 2. Docker Compose 실행 방법

모든 명령어는 프로젝트 최상위 디렉터리에서 실행합니다.

**프로젝트 경로**

```text
C:\Users\90\PycharmProjects\cnc-wearpoint-backend
```

### 2.1 Docker Compose 프로젝트 이름

초기 환경 구성 스크립트에서 확인된 프로젝트 이름은 다음과 같습니다.

| 구분 | 프로젝트 이름 |
|---|---|
| 기본 개발 환경 | `cnc-wearpoint-backend` |
| 데이터 복원 검증 환경 | `cnc-wearpoint-restore` |

복원 검증 환경은 기존 컨테이너가 없는 경우 사용하는 별도의 프로젝트 이름입니다.

### 2.2 기본 MySQL 환경 확인

Docker Compose 설정이 올바른지 검사합니다.

```powershell
docker compose --project-directory . --env-file .env -p cnc-wearpoint-backend -f infra/compose/compose.yaml config --quiet
```

현재 컨테이너 상태를 확인합니다.

```powershell
docker compose --project-directory . --env-file .env -p cnc-wearpoint-backend -f infra/compose/compose.yaml ps -a
```

설정 검사에서는 환경변수 값을 화면에 출력하지 않습니다.

### 2.3 MySQL 복원 검증 환경 확인

복원용 Docker Compose 설정을 검사합니다.

```powershell
docker compose --project-directory . --env-file .env -p cnc-wearpoint-restore -f infra/compose/compose.restore.yaml config --quiet
```

기본 개발 환경과 복원 검증 환경은 서로 독립적으로 관리합니다.

따라서 다음 사항을 준수합니다.

- 기본 설정과 복원 설정을 하나의 명령에서 함께 사용하지 않습니다.
- 두 Compose 파일을 `-f` 옵션으로 동시에 지정하지 않습니다.
- `--project-directory`는 프로젝트 최상위 디렉터리를 기준으로 지정합니다.
- 기존 프로젝트 이름을 유지하여 Docker Volume 및 네트워크 연결의 일관성을 보장합니다.

---

## 3. 환경변수 및 데이터 관리

### 3.1 환경변수

`.env`와 `.env.example` 파일은 프로젝트 최상위 디렉터리에서 관리합니다.

- `.env`: 실제 개발 환경 설정 및 접속 정보
- `.env.example`: 팀원에게 제공하는 환경변수 예시

`.env`에는 데이터베이스 비밀번호 등 민감한 정보가 포함될 수 있으므로 GitHub에 업로드하지 않습니다.

### 3.2 데이터베이스 스키마

MySQL 테이블 생성 및 구조 정의 파일은 다음 위치에서 관리합니다.

```text
sql/schema.sql
```

이 파일에는 `cnc_wearpoint` 데이터베이스의 테이블 구조, 컬럼 설명, 테이블 설명 및 제약조건을 정의합니다.

### 3.3 MySQL 백업 파일

현재 로컬 MySQL 백업 파일은 프로젝트 외부의 다음 경로에 보관합니다.

```text
C:\Users\90\CNC-WearPoint-Backups\cnc_wearpoint_backup.sql
```

백업 파일은 애플리케이션 소스코드와 분리하여 관리합니다.

---

## 4. NHN Cloud 확장 및 이전

현재 디렉터리 정리 작업은 로컬 개발 환경의 파일 구성을 정리하기 위한 작업입니다.

이 작업 자체로 데이터베이스가 이전되거나 NHN Cloud에 서비스가 배포되지는 않습니다.

향후 NHN Cloud 환경으로 이전할 경우 기존 Docker Compose 설정을 활용하고, 필요한 환경별 설정을 추가할 예정입니다.

Kubernetes 관련 설정은 실제 도입이 결정된 이후 구성합니다.

### MLflow 데이터 이전 시 주의사항

MLflow를 다른 환경으로 이전할 경우 다음 두 저장소를 모두 고려해야 합니다.

1. **Backend Store:** 학습 실험, 파라미터, 평가 지표, 모델 등록 정보 등 메타데이터
2. **Artifact Store:** 학습된 모델 파일, 가중치 및 기타 학습 산출물

MLflow의 메타데이터와 아티팩트는 별도로 저장될 수 있으므로, 이전 과정에서 두 저장소 모두 누락되지 않도록 관리해야 합니다.

---

## 5. 참고 문서

- [Docker Compose 공식 문서](https://docs.docker.com/reference/cli/docker/compose/)
- [Docker Compose 프로젝트 이름 관리](https://docs.docker.com/compose/how-tos/project-name/)
- [Docker Compose 설정 검사](https://docs.docker.com/reference/cli/docker/compose/config/)
- [MLflow Artifact Store 공식 문서](https://mlflow.org/docs/latest/self-hosting/architecture/artifact-store/)