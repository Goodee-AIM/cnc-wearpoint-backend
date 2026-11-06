# CNC WearPoint — 데이터베이스 구성 및 이전 가이드

> **문서 상태:** 과거 로컬 스키마 비교 기록 및 업로드 덤프 정적 점검 / 데이터 이관 보류  
> **기준일:** 2026-11-07  
> **대상:** CNC WearPoint 서비스 DB 및 MLflow 메타데이터 DB

## 1. 목적과 관리 범위

CNC WearPoint는 서비스 데이터와 MLflow의 실험·모델 메타데이터를 **서로 다른 데이터베이스**로 관리합니다. 현재는 Docker 기반 로컬 MySQL에서 구조를 검증하고 있으며, 이후 NHN Cloud RDS for MySQL로 이전할 계획입니다.

| 데이터베이스 | 목적 | 현재 관리 위치 |
| --- | --- | --- |
| `cnc_wearpoint` | CNC 공구 마모 예측 서비스의 업무 데이터 | [sql/cnc/schema.sql](../sql/cnc/schema.sql) |
| `mlflow` | MLflow 실험, Run, 메트릭, 모델 레지스트리 등 메타데이터 | [sql/mlflow/mlflow.sql](../sql/mlflow/mlflow.sql) (업로드된 로컬 스키마 스냅샷) |

**아티팩트 저장소는 DB와 별개입니다.** 학습된 모델, 가중치 등의 파일은 MySQL 스키마 덤프로 이전되지 않습니다.

## 2. 개발 환경 및 기준 버전

| 항목 | 현재 기준 |
| --- | --- |
| 개발 환경 | Windows, Docker Desktop, DBeaver |
| 로컬 MySQL | 8.4.13 / Docker 컨테이너 `cnc-wearpoint-mysql` |
| 로컬 MySQL 접속 | `127.0.0.1:3306` |
| MLflow 원본 | MLflow 3.18.0 / SQLite |
| 원본 SQLite Alembic revision | `f4a9b2c7d1e6` |
| 대상 클라우드 | NHN Cloud RDS for MySQL (도입 예정, 지원 버전 확인 필요) |

위 표의 MLflow 원본 버전과 SQLite revision은 이전 점검 기록이며, 이번 SQL 파일 정적 점검에서 다시 검증한 값이 아닙니다. 업로드된 덤프의 헤더에는 MySQL 클라이언트 8.0.19와 원본 서버 8.4.13이 기록되어 있습니다.

이전 점검 시 로컬 `mlflow` DB의 기본 정렬 규칙은 `utf8mb4_0900_ai_ci`였고, 업로드된 덤프의 테이블은 `InnoDB / utf8mb4 / utf8mb4_0900_bin`을 사용합니다. **현재 DB 및 RDS의 MySQL 버전과 권한·정렬 규칙은 연결·이관 시 다시 확인합니다.**

## 3. MLflow 메타데이터 스키마 검증 현황

아래 비교 결과는 원본 SQLite 스키마를 기준으로 MySQL DDL을 변환한 뒤, 로컬 DBeaver의 `SHOW CREATE TABLE` 및 `information_schema` 조회 결과와 대조했던 기록입니다. 이번에는 업로드된 SQL 파일을 정적으로 점검했으며, 원본 SQLite나 현재 실행 중인 MySQL에 대한 비교·행 수 조회를 다시 수행한 것은 아닙니다.

| 항목 | 확인 결과 | 비고 |
| --- | --- | --- |
| 테이블 | **71 / 71개** | 이전 점검 당시 실제 테이블 수 조회 |
| 원본 별도 인덱스 | **89 / 89개** | 이름·컬럼 순서·유일성·정렬 방향 비교; 아래 차이 1건 |
| 외래키(FK) | **62 / 62개** | 참조 컬럼, `ON DELETE` / `ON UPDATE` 규칙 비교 |
| CHECK 제약조건 | **7 / 7개** | 조건식 일치, 모두 `ENFORCED = YES` |
| 트리거 | **1 / 1개** | `prevent_secrets_aad_mutation` 정의 확인, 동작 테스트 미실시 |
| `alembic_version` 데이터 | **0행** | 이전 점검 당시 의도적으로 버전값을 기록하지 않음 |
| 주요 데이터 테이블 12개 | **모두 0행** | 이전 점검 기록이며 현재 행 수는 별도 조회 필요 |

### 3.1 확인된 변환 사항

- SQLite의 실수형은 검증된 로컬 변환 방침에 따라 MySQL `DOUBLE`로 구성했습니다.
- SQLite의 `BOOLEAN`은 MySQL `TINYINT(1)`로 구성했습니다.
- JSON 선언 컬럼은 MySQL 네이티브 `JSON`으로 구성했습니다. 실제 데이터 적재 시 JSON 유효성을 확인해야 합니다.
- `experiments.experiment_id` 및 일부 일별 집계 테이블의 정수형 기본키에 `AUTO_INCREMENT`를 적용했습니다. MLflow 3.18.0에서의 쓰기 동작은 아직 검증되지 않았습니다.
- `spans.duration_ns`는 `GENERATED ALWAYS AS (...) STORED` 생성 컬럼입니다. 데이터 적재 시 직접 INSERT하지 않습니다.

### 3.2 원본과 다른 인덱스 정의

`sql_span_cost_daily_rollups.idx_span_cost_rollups_lookup`의 마지막 두 컬럼에 MySQL 키 길이 제한을 고려한 **접두부 인덱스**를 적용했습니다.

| 컬럼 | 원본 SQLite | 로컬 MySQL |
| --- | --- | --- |
| `experiment_id`, `rollup_day`, `metric_name`, `grouping_set` | 전체 길이 | 전체 길이 |
| `model_name` | 전체 길이 | 앞 200글자 |
| `model_provider` | 전체 길이 | 앞 200글자 |

따라서 별도 인덱스 **89개의 이름은 모두 존재하지만 89개 모두 완전 동일한 DDL은 아닙니다.** 실제 조회 성능은 추후 검증합니다.

또한 `spans`에는 원본에도 있는 동일 컬럼 구성의 보조 인덱스 1쌍이 존재합니다. 현재 임의 삭제하지 않았습니다.

### 3.3 인덱스 수량 해석

원본 별도 인덱스 89개와 MySQL의 **UNIQUE 제약조건 및 FK 지원 인덱스**는 구분해야 합니다. 이전 비교 기록은 보조 인덱스를 **107개(89 + 추가 18)** 로 설명했으며, 그보다 앞선 집계에는 106개로 기록되어 있었습니다.

현재 업로드된 `mlflow.sql`에서는 `PRIMARY KEY`를 제외한 `KEY` 및 `UNIQUE KEY` 정의가 **107개**입니다. 이는 덤프의 정적 집계이며, 원본 SQLite와의 89개 인덱스 비교나 현재 DB의 실제 인덱스 수를 재검증한 결과는 아닙니다. **수량 차이만으로 인덱스를 추가·삭제하지 않습니다.**

### 3.4 업로드된 덤프의 정적 점검

현재 [MLflow SQL](../sql/mlflow/mlflow.sql)에서 확인한 내용은 다음과 같습니다.

| 항목 | 덤프 내 정의 수 |
| --- | --- |
| `CREATE TABLE` | 71개 |
| `PRIMARY KEY`를 제외한 `KEY` / `UNIQUE KEY` | 107개 |
| 외래키 / CHECK / 트리거 | 62개 / 7개 / 1개 |
| `DROP TABLE IF EXISTS` / `LOCK TABLES` | 71개 / 71개 |
| `INSERT INTO` | 0개 |
| `CREATE DATABASE` / `USE` | 0개 / 0개 |

`INSERT INTO`가 없다는 사실은 이 파일에 테이블 데이터가 포함되지 않았다는 뜻이며, 현재 DB의 모든 테이블이 비어 있다는 증거는 아닙니다. Alembic 버전값도 이 파일만으로 확인할 수 없습니다.

이 덤프에는 기존 테이블을 삭제하는 구문과 쓰기 잠금 구문이 포함되어 있습니다. 또한 DB 생성·선택 구문이 없으므로 파일을 적용할 때의 연결 대상 DB가 중요합니다. 트리거 `prevent_secrets_aad_mutation`에는 `DEFINER=root@localhost`가 지정되어 있습니다. 따라서 **운영 DB에 그대로 실행하거나 Docker 자동 초기화용으로 연결하는 배포 스크립트로 취급하지 않습니다.** 현재 파일은 구조 확인용 스냅샷으로 보관하고, 실제 적용은 별도 환경에서 검토·검증합니다.

## 4. 원본 데이터 및 아티팩트

원본 MLflow의 주요 데이터는 이전 점검 시 다음과 같이 확인되었습니다.

| 구분 | 원본 확인 값 |
| --- | --- |
| 실험 / Run | 6개 / 28개 |
| 등록 모델 / 모델 버전 | 4개 / 15개 (데모 포함) |
| 주요 프로젝트 모델 | `MATWI-MOMENT-Regressor` (버전 1·2·3) |
| Logged Model | 3개, 관련 폴더 및 `MLmodel` 파일 존재 확인 |
| SQLite 크기 | 약 1.9MB |
| 아티팩트 크기 | 약 1.1GB |
| 아티팩트 URI | `mlflow-artifacts:/` 형식 |

위 값은 **과거 원본 조회 시점의 값**입니다. 최종 이관 시 다시 비교해야 합니다. 모델 로드·추론, 전체 아티팩트 체크섬 검증은 아직 수행하지 않았습니다.

## 5. Git 저장소 내 파일 관리

```text
cnc-wearpoint-backend/
├── README.md                     # 프로젝트 소개 및 빠른 시작
├── docs/
│   ├── database.md               # 이 문서
│   └── deployment/
│       └── infrastructure.md
├── infra/
│   └── compose/                   # Docker Compose 설정
└── sql/
    ├── cnc/
    │   └── schema.sql             # CNC WearPoint 서비스 DB
    └── mlflow/
        └── mlflow.sql             # MLflow 로컬 스키마 스냅샷
```

[sql/mlflow/mlflow.sql](../sql/mlflow/mlflow.sql)은 현재 업로드된 **로컬 스키마의 기록용 스냅샷**이며, RDS 적용과 MLflow 실행 검증을 통과한 배포용 마이그레이션 스크립트가 아닙니다. 덤프에 포함된 `DROP`, `LOCK TABLES`, 트리거 `DEFINER`와 DB 선택 조건을 검토한 뒤 용도에 맞게 관리합니다. 관련 인프라 설명은 [인프라 구성 안내](deployment/infrastructure.md)를 참고합니다.

Git에 올릴 수 있는 것은 검토된 DDL과 문서입니다. **`.env`, 비밀번호·토큰, 데이터 덤프, 실제 아티팩트 파일, 운영 DB 백업은 커밋하지 않습니다.** 트리거의 `DEFINER=root@localhost` 등 환경 의존 설정도 확인합니다.

### 5.1 스키마만 다시 덤프할 때의 예시

아래는 **향후 구조 스냅샷을 다시 생성할 때의 예시**이며, 현재 업로드된 파일을 생성한 명령을 재현한 기록이 아닙니다. 예시에서는 테이블 데이터, `DROP TABLE`, 데이터 쓰기 잠금 구문을 제외합니다. 현재 파일에는 앞서 확인한 `DROP TABLE` 및 `LOCK TABLES`가 남아 있습니다.

**실행 위치:** Docker 컨테이너의 셸 (`mysql>` 프롬프트가 아님)

```bash
mysqldump -u root -p --no-data --triggers --skip-add-drop-table --skip-add-locks --no-tablespaces --set-gtid-purged=OFF --default-character-set=utf8mb4 --result-file=/tmp/mlflow.sql mlflow
```

**실행 위치:** Windows PowerShell, 저장소 루트

```powershell
New-Item -ItemType Directory -Force .\sql\mlflow
docker cp cnc-wearpoint-mysql:/tmp/mlflow.sql .\sql\mlflow\mlflow.sql
```

위 `docker cp` 명령은 저장소의 기존 `sql/mlflow/mlflow.sql` 스냅샷을 교체합니다. 보관 중인 파일이 필요한 경우 먼저 별도로 보존하고, 새 덤프의 차이를 검토한 뒤 교체합니다.

덤프 파일을 커밋하기 전에 `INSERT INTO`, 비밀정보, `DEFINER`, `DROP` 문 및 환경 전용 경로를 확인합니다. `--no-data`는 테이블 데이터만 제외하며, 나머지 옵션을 함께 사용하더라도 덤프가 자동으로 안전한 배포 스크립트가 되지는 않습니다. 트리거 DEFINER와 적용 대상 DB는 별도로 확인해야 합니다.

## 6. NHN Cloud RDS 이전 계획

| 단계 | 작업 | 현재 상태 |
| --- | --- | --- |
| 1 | 로컬 SQLite → MySQL 스키마 변환 및 정적 검증 | 주요 검증 완료 |
| 2 | 격리된 테스트 DB에서 MLflow 3.18.0 연결·조회·쓰기 및 생성 컬럼 검증 | 미진행 |
| 3 | NHN Cloud RDS for MySQL 생성, 버전·권한·네트워크 확인 | 미진행 |
| 4 | RDS에 호환성 검증된 스키마 구성 및 재검증 | 미진행 |
| 5 | 원본 SQLite의 읽기 전용·일관된 스냅샷 확보 | 미진행 |
| 6 | FK 의존성 순서로 메타데이터 적재, 행 수·참조 무결성 검증 | 미진행 |
| 7 | 아티팩트 별도 이전 및 URI·파일 무결성 검증 | 미진행 |
| 8 | MLflow 3.18.0에서 실험·Run·레지스트리·모델 로드·추론 확인 | 미진행 |
| 9 | 최종 검증 후 애플리케이션 연결 대상 전환 | 미진행 |

**원본 보호 원칙:** 기존 NHN 서버의 SQLite DB·아티팩트·설정 파일을 삭제하거나 수정하지 않습니다. 사전 검증은 읽기 전용으로 진행하고, 이관 시에도 원본을 훼손하지 않는 스냅샷을 사용합니다.

### 6.1 Alembic 주의사항

이전 점검 기록에서 원본 SQLite의 revision은 `f4a9b2c7d1e6`이었고 로컬 MySQL의 `alembic_version`은 **0행**이었습니다. 현재 버전값은 실제 연결 대상에서 다시 확인해야 합니다. 스키마를 수동 변환했다는 이유로 revision을 임의 INSERT하거나 `stamp`하지 않습니다. MLflow 3.18.0의 **MySQL 대상 공식 스키마/마이그레이션 동작**을 격리된 환경에서 먼저 확인한 뒤 결정합니다.

### 6.2 배포 시 추가 확인

- RDS에서 지원하는 MySQL 버전 및 문자 집합·정렬 규칙
- RDS 사용자 권한과 트리거 DEFINER 재설정 (`root@localhost` 그대로 사용 금지)
- `AUTO_INCREMENT`, CHECK, JSON, 생성 컬럼, FK 검사·삭제 동작
- `mlflow-artifacts:/` 프록시 URI를 포함한 아티팩트 접근 경로
- 모델 레지스트리 버전·실험·Run·Logged Model 참조 관계와 실제 모델 로드
- 모델/아티팩트 원본 대비 파일 수·크기·체크섬 및 이관 전후 행 수

## 7. 검증 상태 요약

**기존 점검 기록: `LOCAL_SCHEMA_VERIFIED / DATA_MIGRATION_HOLD`**

과거의 로컬 MySQL 구조 비교 기록과 이번 업로드 덤프의 정적 집계는 MLflow 3.18.0 운영 호환성이나 데이터 이관 완료를 뜻하지 않습니다. 현재 DB 상태와 원본 비교는 필요한 시점에 다시 확인합니다. 다음 우선순위는 **격리된 환경에서 MLflow 3.18.0 동작 검증**이며, 전체 데이터 적재는 RDS 구성 후 진행할 수 있습니다.
