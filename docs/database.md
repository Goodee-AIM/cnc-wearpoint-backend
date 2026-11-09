# CNC WearPoint — 데이터베이스 구성 및 이전 가이드

> **문서 상태:** 로컬 스키마 검증 완료 / NHN Cloud RDS 인프라 구성 완료 / 데이터 이관 보류
> **기준일:** 2026-11-09
> **대상:** CNC WearPoint 서비스 DB 및 MLflow 메타데이터 DB

## 1. 문서 목적

이 문서는 CNC WearPoint 프로젝트에서 사용하는 **서비스 데이터베이스와 MLflow 메타데이터 저장소의 구성, 검증 현황 및 NHN Cloud RDS 이전 계획**을 정리합니다.

CNC WearPoint에서는 서비스 데이터와 MLflow의 실험·모델 메타데이터를 서로 다른 데이터베이스로 관리합니다.

| 데이터베이스 | 목적 | 관리 위치 |
|---|---|---|
| `cnc_wearpoint` | CNC 공구 마모 예측 서비스의 업무 데이터 | [sql/cnc/schema.sql](../sql/cnc/schema.sql) |
| `mlflow` | MLflow Experiment, Run, Metric, Model Registry 등의 메타데이터 | [sql/mlflow/mlflow.sql](../sql/mlflow/mlflow.sql) |

현재 로컬 환경에서는 Docker 기반 MySQL을 사용해 데이터베이스 구조를 검증했습니다.

NHN Cloud에는 **MySQL 8.4.6 기반 RDS 환경과 Database 전용 Private Network를 구성**했으며, 실제 데이터 이관 및 애플리케이션 연결 전환은 별도의 검증 절차를 거쳐 진행할 예정입니다.

> **MLflow Artifact는 데이터베이스와 별도로 관리됩니다.**
>
> 학습된 모델, 모델 가중치, `MLmodel` 파일 등의 Artifact는 MySQL 스키마 또는 데이터베이스 덤프만으로 이전되지 않습니다.

---

## 2. 데이터베이스 구성

### 2.1 로컬 개발 환경

| 항목 | 현재 기준 |
|---|---|
| 개발 환경 | Windows |
| 컨테이너 환경 | Docker Desktop |
| DB 관리 도구 | DBeaver |
| 로컬 MySQL | MySQL 8.4.13 |
| Docker Container | `cnc-wearpoint-mysql` |
| 로컬 접속 | `127.0.0.1:3306` |
| 서비스 DB | `cnc_wearpoint` |
| MLflow 검증 DB | `mlflow` |

로컬 MySQL 환경은 서비스 데이터베이스 구조와 MLflow 메타데이터 스키마를 검증하기 위해 사용합니다.

### 2.2 MLflow 원본 환경

| 항목 | 기준 |
|---|---|
| MLflow | 3.18.0 |
| 원본 Backend Store | SQLite |
| 원본 SQLite Alembic Revision | `f4a9b2c7d1e6` |
| 향후 Backend Store | MySQL |

MLflow 원본 버전과 SQLite Revision은 이전 점검 당시 확인한 값입니다.

현재 업로드된 SQL 파일만으로 원본 SQLite의 최신 상태를 다시 검증한 것은 아니므로, 실제 데이터 이전 전에 원본 환경을 다시 확인해야 합니다.

### 2.3 NHN Cloud 대상 환경

| 항목 | 구성 |
|---|---|
| 서비스 | NHN Cloud RDS for MySQL |
| MySQL Version | 8.4.6 |
| Instance Type | `m2.c2m4` |
| vCPU | 2 |
| Memory | 4 GB |
| Storage | General SSD 20 GB |
| Subnet | `cnc-wp-db-private` |
| Subnet CIDR | `10.60.0.32/28` |
| Floating IP | 사용하지 않음 |
| Authentication Plugin | `caching_sha2_password` |
| Deletion Protection | 사용 |

RDS는 외부 인터넷에 직접 노출하지 않고 **Database 전용 Private Subnet에 배치**했습니다.

App 서버에서 필요한 데이터베이스 통신만 허용하도록 Network와 Security Group을 분리했습니다.

자세한 네트워크 구조는 [클라우드 인프라 구성 문서](infrastructure.md)를 참고합니다.

---

## 3. 데이터베이스 분리 기준

CNC WearPoint에서는 서비스 데이터와 MLflow 데이터를 하나의 데이터베이스에 혼합하지 않고 논리적으로 분리하여 관리합니다.

```text
MySQL
│
├── cnc_wearpoint
│   └── 서비스 데이터
│
└── mlflow
    └── 실험 및 모델 메타데이터
```

동일한 MySQL 계열을 사용하더라도 데이터베이스의 목적을 분리하여 관리함으로써 다음과 같은 장점을 얻을 수 있습니다.

- 서비스 데이터와 MLOps 메타데이터의 역할을 명확하게 구분할 수 있습니다.
- 데이터 백업 및 복구 범위를 구분할 수 있습니다.
- 애플리케이션과 MLflow의 권한을 분리하기 쉽습니다.
- 향후 운영 및 장애 분석 시 영향 범위를 구분하기 쉽습니다.
- 서비스와 MLflow를 독립적으로 확장하거나 이전하기 용이합니다.

---

## 4. CNC WearPoint 서비스 DB

서비스 데이터베이스는 `cnc_wearpoint`를 사용합니다.

주요 테이블은 다음과 같습니다.

| 테이블 | 역할 |
|---|---|
| `tool_sets` | 가공 조건 및 Set 정보 |
| `measurements` | 이미지·센서 측정 데이터 관리 |
| `wear_labels` | 실제 공구 마모값 및 마모 유형 |
| `predictions` | AI 모델의 예측 결과 |
| `alerts` | Warning / Danger 알림 및 이력 |

서비스 DB의 기준 스키마는 다음 파일에서 관리합니다.

```text
sql/cnc/schema.sql
```

해당 파일에는 Table, Column, Constraint, Foreign Key 등의 데이터베이스 구조를 정의합니다.

Docker Compose 환경에서는 신규 MySQL 데이터 디렉터리를 생성할 때 초기 스키마를 구성하는 용도로 사용합니다.

기존 데이터베이스가 이미 존재하는 경우 `schema.sql`을 수정하더라도 기존 테이블 구조가 자동으로 변경되지는 않습니다.

따라서 운영 단계에서의 스키마 변경은 별도의 Migration 절차를 통해 관리해야 합니다.

---

## 5. MLflow 메타데이터 스키마 검증 현황

MLflow의 기존 Backend Store는 SQLite를 사용하고 있습니다.

향후 관리형 데이터베이스 환경을 사용하기 위해 SQLite 구조를 MySQL 기준으로 변환하고 로컬 환경에서 스키마를 검증했습니다.

검증 과정에서는 원본 SQLite 구조와 MySQL DDL을 비교하고, DBeaver의 `SHOW CREATE TABLE` 및 `information_schema`를 이용해 주요 객체를 확인했습니다.

| 항목 | 확인 결과 | 비고 |
|---|---|---|
| 테이블 | **71 / 71개** | 이전 검증 당시 실제 테이블 수 확인 |
| 원본 별도 인덱스 | **89 / 89개** | 이름·컬럼 순서·유일성·정렬 방향 비교 |
| 외래키 | **62 / 62개** | 참조 컬럼 및 삭제·갱신 규칙 비교 |
| CHECK Constraint | **7 / 7개** | 조건식 및 Enforcement 확인 |
| Trigger | **1 / 1개** | 정의 확인 |
| `alembic_version` | **0행** | 임의 Revision 입력을 하지 않은 상태 |

위 결과는 **과거 로컬 환경에서 수행한 구조 비교 결과**입니다.

현재 실행 중인 MySQL 또는 RDS에 대해 동일한 검증을 다시 수행한 결과를 의미하지는 않습니다.

---

## 6. MLflow SQLite → MySQL 변환 사항

### 6.1 데이터 타입

SQLite와 MySQL의 데이터 타입 차이에 따라 일부 타입을 변환했습니다.

- SQLite 실수형 → MySQL `DOUBLE`
- SQLite `BOOLEAN` → MySQL `TINYINT(1)`
- JSON 선언 컬럼 → MySQL Native `JSON`

JSON 데이터는 실제 데이터 이전 시 MySQL에서 정상적으로 처리되는지 추가 검증이 필요합니다.

### 6.2 AUTO_INCREMENT

`experiments.experiment_id` 및 일부 정수형 기본키에는 MySQL의 `AUTO_INCREMENT`를 적용했습니다.

다만 실제 MLflow 3.18.0 서버가 해당 MySQL Schema에서 정상적인 생성·조회·갱신 작업을 수행하는지는 별도의 Integration Test가 필요합니다.

### 6.3 생성 컬럼

`spans.duration_ns`는 다음 형태의 생성 컬럼으로 구성했습니다.

```text
GENERATED ALWAYS AS (...) STORED
```

따라서 실제 데이터를 이전할 때 해당 컬럼에 값을 직접 INSERT하지 않도록 주의해야 합니다.

---

## 7. 원본과 다른 인덱스 정의

`sql_span_cost_daily_rollups.idx_span_cost_rollups_lookup`은 MySQL의 Index Key Length 제한을 고려해 일부 컬럼에 Prefix Index를 적용했습니다.

| 컬럼 | 원본 SQLite | 로컬 MySQL |
|---|---|---|
| `experiment_id` | 전체 길이 | 전체 길이 |
| `rollup_day` | 전체 길이 | 전체 길이 |
| `metric_name` | 전체 길이 | 전체 길이 |
| `grouping_set` | 전체 길이 | 전체 길이 |
| `model_name` | 전체 길이 | 앞 200글자 |
| `model_provider` | 전체 길이 | 앞 200글자 |

따라서 원본 인덱스의 이름과 주요 컬럼 구성은 유지했지만 **모든 인덱스가 SQLite와 완전히 동일한 물리적 구조를 사용하는 것은 아닙니다.**

실제 쿼리 성능은 데이터 이전 이후 별도로 확인해야 합니다.

또한 `spans`에는 원본에도 존재하는 동일 컬럼 구성의 보조 인덱스 한 쌍이 있으며, 현재 임의로 삭제하지 않았습니다.

---

## 8. 인덱스 수량 해석

원본 SQLite의 별도 Index와 MySQL이 생성하는 Unique Constraint 및 Foreign Key 지원 Index는 구분해서 확인해야 합니다.

기존 비교 결과에서는 원본 별도 Index를 **89개**로 확인했습니다.

현재 `sql/mlflow/mlflow.sql`에서 `PRIMARY KEY`를 제외한 `KEY`와 `UNIQUE KEY` 정의를 정적으로 집계하면 **107개**입니다.

이는 다음 두 값을 서로 다른 기준으로 집계했기 때문입니다.

```text
원본 SQLite 비교 대상 Index
→ 89개

MySQL Dump 내부 KEY / UNIQUE KEY
→ 107개
```

따라서 Index 수량만 비교하여 임의로 Index를 추가하거나 삭제하지 않습니다.

Schema 구조와 실제 Query Pattern을 함께 확인한 뒤 변경 여부를 판단해야 합니다.

---

## 9. MLflow SQL 스냅샷 점검

현재 [sql/mlflow/mlflow.sql](../sql/mlflow/mlflow.sql)은 MLflow MySQL 구조를 기록하기 위한 **로컬 Schema Snapshot**입니다.

파일에서 확인한 주요 객체는 다음과 같습니다.

| 항목 | 정의 수 |
|---|---:|
| `CREATE TABLE` | 71 |
| `KEY` / `UNIQUE KEY` | 107 |
| Foreign Key | 62 |
| CHECK Constraint | 7 |
| Trigger | 1 |
| `DROP TABLE IF EXISTS` | 71 |
| `LOCK TABLES` | 71 |
| `INSERT INTO` | 0 |
| `CREATE DATABASE` | 0 |
| `USE` | 0 |

`INSERT INTO`가 없다는 것은 해당 파일에 Table Data가 포함되어 있지 않다는 의미입니다.

현재 실행 중인 데이터베이스의 모든 Table이 비어 있다는 의미는 아닙니다.

또한 해당 Dump에는 다음과 같이 실제 환경 적용 시 주의가 필요한 요소가 포함되어 있습니다.

- `DROP TABLE IF EXISTS`
- `LOCK TABLES`
- Trigger `DEFINER=root@localhost`
- `CREATE DATABASE` 및 `USE` 없음

따라서 이 파일을 **RDS에 그대로 실행하는 배포용 Migration Script로 사용하지 않습니다.**

현재 파일은 MySQL Schema 구조를 확인하고 기록하기 위한 Snapshot으로 관리합니다.

---

## 10. MLflow 원본 데이터 및 Artifact

기존 MLflow 환경을 점검했을 당시 확인한 주요 데이터는 다음과 같습니다.

| 구분 | 과거 확인 값 |
|---|---|
| Experiment | 6개 |
| Run | 28개 |
| Registered Model | 4개 |
| Model Version | 15개 |
| 주요 모델 | `MATWI-MOMENT-Regressor` |
| 주요 모델 버전 | 1 / 2 / 3 |
| Logged Model | 3개 |
| SQLite Size | 약 1.9 MB |
| Artifact Size | 약 1.1 GB |
| Artifact URI | `mlflow-artifacts:/` |

위 값은 **이전 원본 환경을 확인했을 당시의 기록**입니다.

최종 Migration 직전에는 다시 확인해야 합니다.

특히 MLflow는 다음 두 영역을 별도로 이전해야 합니다.

### Backend Store

MySQL로 이전할 대상입니다.

- Experiment
- Run
- Parameter
- Metric
- Tag
- Model Registry
- Model Version
- 기타 MLflow Metadata

### Artifact Store

Backend Store와 별도로 관리해야 합니다.

- 학습 모델
- Model Weight
- `MLmodel`
- 기타 실험 결과 파일

따라서 MySQL 데이터만 이전했다고 해서 MLflow 전체 Migration이 완료되는 것은 아닙니다.

---

## 11. Git 저장소 내 파일 관리

현재 관련 파일은 다음과 같이 관리합니다.

```text
cnc-wearpoint-backend/
├── README.md
│
├── docs/
│   ├── database.md
│   ├── infrastructure.md
│   │
│   ├── architecture/
│   │   ├── diagrams/
│   │   │   └── cnc_wp_infrastructure.py
│   │   └── images/
│   │       ├── cnc_wp_infrastructure.png
│   │       └── cnc_wp_infrastructure.svg
│   │
│   └── deployment/
│       └── infrastructure.md
│
├── infra/
│   └── compose/
│       └── compose.mysql.yaml
│
└── sql/
    ├── cnc/
    │   └── schema.sql
    │
    └── mlflow/
        └── mlflow.sql
```

각 문서는 다음 역할로 구분합니다.

| 문서 | 역할 |
|---|---|
| `README.md` | 프로젝트 소개 및 빠른 시작 |
| `docs/infrastructure.md` | NHN Cloud Network 및 Infrastructure 설계 |
| `docs/database.md` | 서비스 DB와 MLflow DB 구성 및 Migration 현황 |
| `docs/deployment/infrastructure.md` | Docker Compose 및 배포 관련 파일 관리 |

---

## 12. Git 데이터 관리 원칙

Git 저장소에는 애플리케이션을 재현하고 구조를 이해하는 데 필요한 Source Code, Schema 및 문서를 중심으로 관리합니다.

다음 파일은 Git에 포함하지 않습니다.

- `.env`
- Database Password
- API Key 및 Token
- 실제 Database Backup
- 실제 데이터 Dump
- 원본 이미지 및 Sensor Data
- 대용량 Dataset
- Model Artifact
- 운영 환경에 종속된 민감정보

`sql/mlflow/mlflow.sql`은 데이터가 없는 Schema Snapshot으로 관리하고 있습니다.

Dump 파일을 커밋하기 전에는 다음 내용을 확인합니다.

- `INSERT INTO`
- Password 및 Token
- Trigger `DEFINER`
- `DROP TABLE`
- 환경 전용 Path
- 기타 민감정보

---

## 13. MLflow Schema Snapshot 재생성 예시

향후 로컬 MLflow MySQL Schema를 다시 기록해야 하는 경우 다음과 같은 방식으로 구조만 Dump할 수 있습니다.

> 아래 명령은 구조 Snapshot 생성 예시이며 현재 저장된 `mlflow.sql`을 생성한 명령의 기록을 의미하지 않습니다.

Docker Container 내부에서 실행합니다.

```bash
mysqldump \
  -u root \
  -p \
  --no-data \
  --triggers \
  --skip-add-drop-table \
  --skip-add-locks \
  --no-tablespaces \
  --set-gtid-purged=OFF \
  --default-character-set=utf8mb4 \
  --result-file=/tmp/mlflow.sql \
  mlflow
```

Windows PowerShell에서 파일을 복사합니다.

```powershell
New-Item -ItemType Directory -Force .\sql\mlflow

docker cp `
  cnc-wearpoint-mysql:/tmp/mlflow.sql `
  .\sql\mlflow\mlflow.sql
```

새 Snapshot을 생성한 경우 기존 파일과의 차이를 확인한 뒤 Git에 반영합니다.

`--no-data`는 Table Data만 제외하는 옵션이므로, 생성된 Dump가 자동으로 안전한 운영용 Migration Script가 되는 것은 아닙니다.

Trigger, `DEFINER`, 적용 대상 Database 및 기타 환경 종속 설정은 별도로 확인해야 합니다.

---

## 14. NHN Cloud RDS 이전 계획

RDS Infrastructure와 실제 Database Migration은 별개의 단계로 관리합니다.

현재 RDS와 Network 환경은 구성했지만, **서비스 DB 및 MLflow 데이터를 RDS로 이전하는 작업은 아직 완료하지 않았습니다.**

| 단계 | 작업 | 상태 |
|---|---|---|
| 1 | SQLite → MySQL Schema 변환 및 로컬 구조 검증 | 주요 검증 완료 |
| 2 | 로컬 MySQL Schema Snapshot 점검 | 완료 |
| 3 | NHN Cloud VPC 및 Database Private Network 구성 | 완료 |
| 4 | NHN Cloud RDS for MySQL 8.4.6 환경 구성 | 완료 |
| 5 | App VM → RDS Network 연결 및 DB 계정·권한 검증 | 진행 예정 |
| 6 | RDS에서 CNC 서비스 DB Schema 검증 | 진행 예정 |
| 7 | 격리된 환경에서 MLflow 3.18.0 MySQL 연결·조회·쓰기 검증 | 진행 예정 |
| 8 | 원본 SQLite의 Read-only Snapshot 확보 | 진행 예정 |
| 9 | MLflow Metadata 데이터 적재 및 참조 무결성 검증 | 진행 예정 |
| 10 | Artifact 별도 이전 및 파일 무결성 검증 | 진행 예정 |
| 11 | Experiment / Run / Registry / Model Load 검증 | 진행 예정 |
| 12 | 최종 검증 후 Application 및 MLflow 연결 대상 전환 | 진행 예정 |

여기서 중요한 점은 **RDS를 생성했다고 해서 데이터베이스 Migration이 완료된 것은 아니라는 점**입니다.

실제 Migration 완료 여부는 Schema, Data, Application Connection 및 MLflow 동작까지 검증한 이후 판단합니다.

---

## 15. 원본 보호 원칙

Migration 과정에서는 기존 원본 환경을 직접 변경하지 않는 것을 기본 원칙으로 합니다.

기존 MLflow 환경의 다음 파일 및 데이터는 Migration 완료 전까지 유지합니다.

- SQLite Database
- MLflow Artifact
- MLflow Server 설정
- Model 파일
- 기존 Experiment 및 Run 정보

사전 검증 과정에서는 가능하면 Read-only Snapshot을 사용하고, 원본을 삭제하거나 덮어쓰지 않습니다.

이를 통해 Migration 과정에서 문제가 발생하더라도 기존 환경을 기준으로 복구하거나 다시 검증할 수 있도록 합니다.

---

## 16. Alembic 주의사항

기존 점검 기록에서 원본 SQLite의 Alembic Revision은 다음과 같았습니다.

```text
f4a9b2c7d1e6
```

로컬 MySQL의 `alembic_version`은 당시 **0행**으로 확인했습니다.

수동으로 Schema를 변환했다는 이유만으로 Alembic Revision을 임의로 INSERT하거나 `stamp`하지 않습니다.

MLflow 3.18.0이 MySQL Backend Store를 대상으로 수행하는 공식 Migration 동작을 먼저 확인한 후 Revision 관리 방법을 결정합니다.

---

## 17. RDS 이전 시 추가 검증 항목

RDS에 Schema 및 데이터를 적용하기 전에 다음 항목을 확인합니다.

### Database

- MySQL Version
- Character Set
- Collation
- DB User 권한
- Authentication Plugin
- `AUTO_INCREMENT`
- CHECK Constraint
- JSON Column
- Generated Column
- Foreign Key
- Trigger

### MLflow

- Alembic Revision
- Experiment
- Run
- Parameter
- Metric
- Registered Model
- Model Version
- Logged Model
- Artifact URI
- Model Load 및 Inference

### 데이터 무결성

- Migration 전후 Row Count
- Foreign Key 참조 관계
- 주요 Table Sample Data
- Artifact File Count
- Artifact File Size
- 필요 시 Checksum

---

## 18. 현재 상태 요약

현재 데이터베이스 작업 상태는 다음과 같습니다.

```text
Local Environment
│
├── CNC WearPoint MySQL
│   └── Schema 및 데이터 검증
│
└── MLflow
    ├── SQLite 원본
    └── MySQL Schema 변환 및 구조 검증
             │
             ▼
        Migration HOLD
             │
             ▼
NHN Cloud
│
└── RDS for MySQL 8.4.6
    ├── Private Network 구성
    └── 실제 데이터 이전 및 연결 검증 예정
```

현재 상태를 다음과 같이 구분합니다.

**`LOCAL_SCHEMA_VERIFIED / RDS_INFRA_READY / DATA_MIGRATION_HOLD`**

로컬 MySQL에서의 Schema 검증과 NHN Cloud RDS Infrastructure 구성은 완료했지만, 이것이 실제 데이터 Migration 완료를 의미하지는 않습니다.

다음 단계에서는 **App VM과 RDS 간 연결 및 권한 검증을 먼저 수행하고, 이후 CNC 서비스 DB와 MLflow Metadata를 단계적으로 이전하면서 데이터 무결성과 애플리케이션 동작을 확인할 예정입니다.**