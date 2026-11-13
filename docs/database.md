# CNC WearPoint — 데이터베이스 구성 및 이전 가이드

> **문서 상태:** RDS 이전 완료 / TLS·CA 검증 완료 / Object Storage 이전 완료 / MLflow Lifecycle 검증 완료  
> **기준일:** 2026-11-13  
> **대상:** CNC WearPoint 서비스 DB, MLflow 메타데이터 DB 및 MLflow 인증 DB

---

## 1. 문서 목적

이 문서는 CNC WearPoint 프로젝트에서 사용하는 **서비스 데이터베이스, MLflow 메타데이터 저장소, MLflow 인증 데이터베이스의 구성과 NHN Cloud RDS 이전 결과**를 정리합니다.

CNC WearPoint에서는 서비스 데이터와 MLflow 데이터를 목적에 따라 서로 다른 Database로 분리하여 관리합니다.

| 데이터베이스 | 목적 | 현재 위치 |
|---|---|---|
| `cnc_wearpoint` | CNC 공구 마모 예측 서비스의 업무 데이터 | NHN Cloud RDS for MySQL |
| `mlflow` | Experiment, Run, Metric, Model Registry 등 MLflow Metadata | NHN Cloud RDS for MySQL |
| `mlflow_auth` | MLflow Basic Auth 사용자 및 권한 정보 | NHN Cloud RDS for MySQL |

로컬 환경의 Docker MySQL은 개발 및 Schema 검증 용도로 유지하며, 현재 운영 환경에서는 **NHN Cloud RDS for MySQL 8.4.6**을 사용합니다.

서비스 이미지, 센서 데이터 및 MLflow Artifact는 Database에 직접 저장하지 않고 **NHN Cloud Object Storage**에 별도로 저장합니다.

```text
RDS for MySQL
├── cnc_wearpoint
├── mlflow
└── mlflow_auth

NHN Object Storage
├── cnc-wearpoint-data
│   ├── images/
│   └── sensors/
│
└── cnc-wearpoint-mlflow
    └── mlflow-artifacts/
```

Database에는 구조화된 업무 데이터와 파일의 경로 또는 Object Key를 저장하고, 실제 대용량 파일은 Object Storage에서 관리합니다.

---

## 2. 데이터베이스 구성

### 2.1 로컬 개발 환경

| 항목 | 현재 기준 |
|---|---|
| 개발 환경 | Windows 11 |
| 컨테이너 환경 | Docker Desktop |
| DB 관리 도구 | DBeaver |
| 로컬 MySQL | MySQL 8.4.13 |
| Docker Container | `cnc-wearpoint-mysql` |
| 로컬 접속 | `127.0.0.1:3306` |
| 서비스 DB | `cnc_wearpoint` |
| MLflow 검증 DB | `mlflow` |

로컬 MySQL은 Schema 검증, 데이터 확인 및 개발 테스트 용도로 사용합니다.

운영 데이터베이스는 NHN Cloud RDS를 사용합니다.

---

### 2.2 MLflow 환경

| 항목 | 현재 기준 |
|---|---|
| MLflow Version | 3.18.0 |
| 기존 Backend Store | SQLite |
| 현재 Backend Store | NHN Cloud RDS MySQL |
| MLflow Metadata DB | `mlflow` |
| MLflow Auth DB | `mlflow_auth` |
| Artifact Store | NHN Cloud Object Storage |
| Artifact Bucket | `cnc-wearpoint-mlflow` |
| 실행 방식 | Python venv + systemd |
| 내부 Listen | `127.0.0.1:5000` |
| 외부 접근 | Nginx `/mlflow/` |
| 인증 | MLflow Basic Auth |

기존 MLflow 환경에서는 SQLite Backend Store와 로컬 Artifact 디렉터리를 사용했습니다.

현재 운영 환경에서는 MLflow Metadata를 RDS MySQL에 저장하고, Artifact는 Object Storage에 저장하도록 전환했습니다.

---

### 2.3 NHN Cloud RDS 환경

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
| TLS | TLS 1.3 |
| CA 검증 | 적용 |

RDS는 외부 인터넷에 직접 노출하지 않고 **Database 전용 Private Subnet**에 배치합니다.

App VM에서 필요한 Database 통신만 허용하도록 Application Network와 Database Network를 분리했습니다.

RDS 접속은 TLS 기반으로 구성했으며, FastAPI와 MLflow 모두 NHN Cloud RDS의 CA 인증서를 사용해 서버 인증서를 검증합니다.

---

## 3. 데이터베이스 분리 기준

CNC WearPoint에서는 서비스 데이터와 MLflow 데이터를 하나의 Database에 혼합하지 않고 논리적으로 분리합니다.

```text
RDS for MySQL
│
├── cnc_wearpoint
│   └── 서비스 업무 데이터
│
├── mlflow
│   └── Experiment / Run / Metric / Registry Metadata
│
└── mlflow_auth
    └── MLflow 사용자 / 권한 정보
```

Database를 목적에 따라 분리함으로써 다음과 같은 장점을 얻을 수 있습니다.

- 서비스 데이터와 MLOps Metadata의 역할을 명확하게 구분할 수 있습니다.
- Database별 Backup 및 Restore 범위를 구분할 수 있습니다.
- Application과 MLflow의 권한을 분리하기 쉽습니다.
- 장애 발생 시 영향 범위를 구분하기 쉽습니다.
- MLflow 인증 정보를 별도 Database에서 관리할 수 있습니다.
- 서비스와 MLOps 구성요소를 독립적으로 확장하거나 이전하기 용이합니다.

---

## 4. CNC WearPoint 서비스 DB

서비스 Database는 `cnc_wearpoint`를 사용합니다.

주요 Table은 다음과 같습니다.

| 테이블 | 역할 |
|---|---|
| `tool_sets` | 가공 조건 및 Set 정보 |
| `measurements` | 이미지·센서 측정 데이터 및 파일 경로 관리 |
| `wear_labels` | 실제 공구 마모량 및 마모 유형 |
| `predictions` | AI 모델의 예측 결과 |
| `alerts` | Warning / Danger 알림 및 이력 |

서비스 DB의 기준 Schema는 다음 파일에서 관리합니다.

```text
sql/cnc/schema.sql
```

해당 파일에는 Table, Column, Constraint, Foreign Key 등의 Database 구조를 정의합니다.

기존 Database가 이미 생성된 경우 `schema.sql`을 수정한다고 해서 운영 Database 구조가 자동으로 변경되지는 않습니다.

운영 단계의 Schema 변경은 별도의 Migration 절차를 통해 관리해야 합니다.

---

## 5. 서비스 데이터 RDS 이전 결과

로컬 MySQL의 CNC WearPoint 서비스 데이터를 NHN Cloud RDS의 `cnc_wearpoint` Database로 이전했습니다.

이전 후 주요 Row Count는 다음과 같습니다.

| 테이블 | Row Count |
|---|---:|
| `tool_sets` | 8 |
| `measurements` | 918 |
| `wear_labels` | 824 |
| `predictions` | 0 |
| `alerts` | 0 |

Migration 이후 다음 항목을 확인했습니다.

- Table 생성 확인
- Foreign Key 유지 확인
- Index 유지 확인
- Row Count 비교
- App VM에서 RDS 접속 확인
- FastAPI를 통한 실제 데이터 조회
- HTTPS API를 통한 운영 환경 조회

주요 API 확인 결과:

```text
GET /health
→ HTTP 200

GET /api/sets
→ Set 8개 조회

GET /api/sets/4/measurements
→ Measurement 데이터 및 Wear Label 조회
```

따라서 현재 CNC WearPoint 서비스 Database는 RDS에서 정상적으로 사용되고 있습니다.

---

## 6. 서비스 파일 저장 구조

초기에는 App VM의 로컬 디스크에서 이미지와 Sensor CSV를 관리했습니다.

기존 구조 예시는 다음과 같습니다.

```text
storage/
├── images/
│   ├── set4/
│   ├── set5/
│   └── ...
│
└── sensors/
    ├── set4/
    ├── set5/
    └── ...
```

현재 운영 환경에서는 서비스 파일을 **NHN Cloud Object Storage**로 이전했습니다.

Bucket:

```text
cnc-wearpoint-data
```

Object Key 구조:

```text
images/
├── set4/original/
├── set5/original/
├── ...
└── set11/original/

sensors/
├── set4/
├── set5/
├── ...
└── set11/
```

Object Storage 이전 결과:

| 구분 | 파일 수 |
|---|---:|
| 이미지 | 824 |
| Sensor CSV | 895 |
| 합계 | 1,719 |

총 파일 크기는 약 **5.29 GB**입니다.

Object Storage 업로드 후 Object Count와 전체 Byte Size를 비교하여 업로드 결과를 확인했습니다.

---

## 7. measurements 파일 경로 Migration

Object Storage 전환에 따라 `measurements` Table의 파일 경로도 로컬 경로에서 Object Storage Key 기반으로 변경했습니다.

### 이미지 경로

최종 상태:

| 상태 | Row Count |
|---|---:|
| `images/%` Object Storage Key | 824 |
| 기존 `MATWI/%` 경로 | 9 |
| NULL | 85 |

### Sensor 경로

| 상태 | Row Count |
|---|---:|
| `sensors/%` Object Storage Key | 895 |
| 기존 `MATWI/%` 경로 | 0 |
| NULL | 23 |

예시:

```text
images/set4/original/Test_0015_1_03_215_....png
sensors/set4/Test_0015_1_03_206_....csv
```

DB에는 Object Storage 전체 URL이 아닌 **Object Key를 저장**합니다.

이를 통해 Endpoint 또는 Bucket 접근 방식이 변경되더라도 Database 값을 최소한으로 수정할 수 있도록 구성했습니다.

---

## 8. 이미지 제외 데이터

Database에서 이미지 경로가 존재하지만 실제 Object Storage에는 업로드하지 않은 이미지가 9개 있습니다.

해당 파일은 Migration 실패로 누락된 파일이 아니라 **빈 이미지 또는 심하게 흐린 이미지로 판단되어 의도적으로 제외한 데이터**입니다.

현재는 기존 Path를 유지하고 있습니다.

향후 다음과 같은 상태 Column을 추가하는 방안을 검토합니다.

```text
image_status
image_exclusion_reason
```

예시:

```text
image_status = excluded_quality
image_exclusion_reason = blank_or_blurry
```

이를 통해 단순 누락과 품질 사유에 따른 의도적 제외를 명확하게 구분할 예정입니다.

---

## 9. FastAPI Object Storage 연동

FastAPI는 현재 파일 조회 시 App VM의 로컬 `storage` 디렉터리가 아니라 Object Storage에서 데이터를 읽습니다.

Backend는 S3 Compatible API를 사용해 Object Storage에 접근합니다.

운영 설정 예시:

```text
STORAGE_BACKEND=s3
OBJECT_STORAGE_BUCKET=cnc-wearpoint-data
```

Object Storage 관련 Credential은 Git Repository에 저장하지 않고 별도의 Environment File을 통해 관리합니다.

Backend에서는 다음 파일 조회를 Object Storage 기반으로 처리합니다.

```text
/api/images/...
/api/sensors/...
```

운영 검증에서는 App VM의 Backend Container에서 기존 Local Storage Volume Mount를 제거한 상태에서도 이미지와 Sensor API가 정상적으로 동작하는 것을 확인했습니다.

따라서 현재 운영 환경에서는 서비스 파일 조회가 **Object Storage 기반으로 동작**합니다.

---

## 10. MLflow Metadata Migration

기존 MLflow Backend Store는 SQLite를 사용했습니다.

MLflow Metadata를 MySQL 구조로 변환하고, 로컬 환경에서 Schema를 검증한 뒤 NHN Cloud RDS로 이전했습니다.

현재 MLflow Server의 Backend Store는 다음 Database를 사용합니다.

```text
mlflow
```

MLflow Basic Auth 관련 정보는 다음 Database를 사용합니다.

```text
mlflow_auth
```

MLflow Server는 더 이상 SQLite를 운영 Backend Store로 사용하지 않습니다.

---

## 11. MLflow Schema 검증 기록

SQLite → MySQL 변환 과정에서 기존 구조를 비교했습니다.

과거 로컬 검증 기준 결과는 다음과 같습니다.

| 항목 | 확인 결과 | 비고 |
|---|---:|---|
| 테이블 | 71 / 71개 | 당시 원본 기준 |
| 원본 별도 인덱스 | 89 / 89개 | 컬럼 및 순서 비교 |
| 외래키 | 62 / 62개 | 참조 관계 확인 |
| CHECK Constraint | 7 / 7개 | 조건 확인 |
| Trigger | 1 / 1개 | 정의 확인 |
| `alembic_version` | 0행 | 수동 Revision 입력 안 함 |

위 수치는 SQLite → MySQL 구조 변환 과정의 검증 기록입니다.

현재 운영 RDS 상태에 대한 Object Count를 의미하지는 않습니다.

---

## 12. SQLite → MySQL 변환 사항

### 12.1 데이터 타입

SQLite와 MySQL의 데이터 타입 차이에 따라 일부 타입을 변환했습니다.

```text
SQLite 실수형
→ MySQL DOUBLE

SQLite BOOLEAN
→ MySQL TINYINT(1)

JSON 선언 Column
→ MySQL JSON
```

### 12.2 AUTO_INCREMENT

`experiments.experiment_id` 및 일부 정수형 Primary Key에는 MySQL의 `AUTO_INCREMENT`를 적용했습니다.

### 12.3 Generated Column

`spans.duration_ns`는 Generated Column으로 구성했습니다.

```text
GENERATED ALWAYS AS (...) STORED
```

따라서 데이터를 직접 Migration하는 경우 Generated Column에 값을 직접 INSERT하지 않도록 주의해야 합니다.

---

## 13. 원본과 다른 Index 정의

`sql_span_cost_daily_rollups.idx_span_cost_rollups_lookup`은 MySQL의 Index Key Length 제한을 고려해 일부 Column에 Prefix Index를 적용했습니다.

| 컬럼 | 원본 SQLite | MySQL |
|---|---|---|
| `experiment_id` | 전체 길이 | 전체 길이 |
| `rollup_day` | 전체 길이 | 전체 길이 |
| `metric_name` | 전체 길이 | 전체 길이 |
| `grouping_set` | 전체 길이 | 전체 길이 |
| `model_name` | 전체 길이 | 앞 200글자 |
| `model_provider` | 전체 길이 | 앞 200글자 |

따라서 논리적 Index 목적은 유지하지만 모든 Index가 SQLite와 완전히 동일한 물리적 구조를 갖는 것은 아닙니다.

---

## 14. Index 수량 해석

SQLite의 별도 Index와 MySQL이 생성하는 Unique Constraint 및 Foreign Key 지원 Index는 구분해서 확인해야 합니다.

기존 비교 결과:

```text
원본 SQLite 비교 대상 Index
→ 89개

MySQL Snapshot KEY / UNIQUE KEY
→ 107개
```

단순 Index 개수 차이만으로 Index를 추가하거나 삭제하지 않습니다.

실제 Query Pattern과 실행 계획을 함께 검토해야 합니다.

---

## 15. MLflow SQL Snapshot

현재 다음 파일은 MLflow MySQL 구조를 기록하기 위한 **Schema Snapshot**입니다.

```text
sql/mlflow/mlflow.sql
```

기존 Snapshot에서 확인한 주요 객체:

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

`INSERT INTO`가 없다는 것은 해당 SQL Snapshot에 Table Data가 포함되지 않았다는 의미입니다.

해당 파일은 운영 RDS에 그대로 적용하는 Migration Script가 아니라 **구조 확인 및 기록용 Snapshot**으로 관리합니다.

---

## 16. MLflow Artifact Store

MLflow의 Metadata와 Artifact는 서로 다른 저장소에서 관리합니다.

### Backend Store

RDS MySQL:

```text
mlflow
```

저장 항목 예시:

- Experiment
- Run
- Parameter
- Metric
- Tag
- Dataset
- Model Registry
- Model Version
- Alias
- 기타 MLflow Metadata

### Artifact Store

NHN Cloud Object Storage:

```text
Bucket:
cnc-wearpoint-mlflow

Prefix:
mlflow-artifacts/
```

저장 항목 예시:

- 학습 모델
- Model Weight
- `MLmodel`
- Environment 정보
- 기타 Run Artifact

MLflow Server는 S3 Compatible API를 이용해 Object Storage를 Artifact Store로 사용합니다.

---

## 17. MLflow Object Storage E2E 검증

Object Storage 전환 후 실제 MLflow Experiment를 생성하고 Artifact Upload를 수행해 End-to-End 동작을 검증했습니다.

검증 내용:

```text
MLflow Experiment 생성
→ Run 생성
→ Artifact 업로드
→ Object Storage Object 생성 확인
→ MLflow API 조회 확인
```

검증용 Experiment:

```text
cnc-wearpoint-object-storage-test
```

따라서 현재 MLflow Artifact Store는 Object Storage에서 정상적으로 동작합니다.

---

## 18. MLflow Model Lifecycle 검증

실제 최종 CNC 모델이 아직 확정되지 않은 상태에서 MLflow Registry와 운영 Lifecycle을 검증하기 위해 임시 Regression Model을 사용했습니다.

검증 항목:

```text
모델 학습
→ MLflow Run 기록
→ Model Registry 등록
→ Version 생성
→ champion Alias 지정
→ Version 교체
→ Model Load
→ Rollback
```

검증용 Registered Model:

```text
cnc-wearpoint-regressor-lifecycle-test
```

검증 결과:

```text
V1 등록
→ champion = V1

V2 등록
→ champion = V2

V2 Load 확인

Rollback
→ champion = V1

V1 Load 확인
```

이를 통해 MLflow의 다음 기능을 확인했습니다.

- Run 관리
- Metric 기록
- Model Registry
- Model Version
- Alias 관리
- Champion Model 교체
- Rollback
- Registry 기반 Model Load

현재 해당 모델은 Lifecycle 검증용 임시 모델이며 실제 CNC WearPoint 서비스 모델은 아닙니다.

---

## 19. 실제 모델 적용 예정

실제 CNC WearPoint 최종 모델이 확정되면 다음 절차를 수행합니다.

```text
최종 모델 학습
        ↓
MLflow Experiment / Run 기록
        ↓
Model Artifact 저장
        ↓
Model Registry 등록
        ↓
Model Version 생성
        ↓
검증 완료
        ↓
champion Alias 지정
        ↓
FastAPI Model Load
        ↓
Inference 검증
```

FastAPI에서는 향후 다음 형태의 Registry URI를 이용하는 방식을 적용할 수 있습니다.

```text
models:/<model-name>@champion
```

초기 운영 단계에서는 Champion 변경 후 FastAPI 재시작 또는 명시적인 Model Reload 절차를 통해 새 Model을 반영할 예정입니다.

---

## 20. RDS TLS 및 CA 검증

운영 환경의 Database 연결은 암호화된 TLS 연결을 사용합니다.

검증 결과:

```text
TLS Version:
TLSv1.3

Cipher:
TLS_AES_256_GCM_SHA384
```

NHN Cloud RDS의 CA 인증서를 App VM에 배치했습니다.

```text
/etc/mysql/certs/ca.pem
```

FastAPI Container에는 해당 CA 파일을 Read-only Volume으로 Mount합니다.

```text
/etc/mysql/certs/ca.pem
→ /etc/mysql/certs/ca.pem
```

검증 대상:

| 구성요소 | Database | 결과 |
|---|---|---|
| FastAPI | `cnc_wearpoint` | TLS + CA 검증 완료 |
| MLflow | `mlflow` | TLS + CA 검증 완료 |
| MLflow Basic Auth | `mlflow_auth` | TLS + CA 검증 완료 |

현재 환경에서는 CA 인증서 검증을 적용하고 있습니다.

Client Certificate 기반 X509 / mTLS는 향후 보안 강화 단계에서 검토할 수 있습니다.

---

## 21. Git Repository 내 파일 관리

현재 Database 관련 파일은 다음과 같이 관리합니다.

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
│
└── sql/
    ├── cnc/
    │   └── schema.sql
    │
    └── mlflow/
        └── mlflow.sql
```

각 문서의 역할은 다음과 같습니다.

| 문서 | 역할 |
|---|---|
| `README.md` | 프로젝트 소개 및 전체 구성 |
| `docs/infrastructure.md` | NHN Cloud Network 및 Infrastructure |
| `docs/database.md` | 서비스 DB / MLflow DB / Storage Migration |
| `docs/deployment/infrastructure.md` | 배포 및 Docker Compose 구성 |

---

## 22. Git 데이터 관리 원칙

Git Repository에는 애플리케이션을 재현하고 구조를 이해하는 데 필요한 Source Code, Schema 및 문서를 중심으로 관리합니다.

다음 데이터는 Git에 포함하지 않습니다.

- `.env`
- Database Password
- Object Storage Access Key
- Secret Key
- API Key 및 Token
- 실제 Database Backup
- 실제 데이터 Dump
- 원본 이미지
- Sensor Data
- 대용량 Dataset
- MLflow Model Artifact
- 운영 환경에 종속된 민감정보

서비스 이미지와 Sensor Data는 Object Storage에서 관리합니다.

MLflow Artifact 역시 Git에 저장하지 않고 Object Storage에서 관리합니다.

---

## 23. 환경 변수 및 Credential 관리

운영 Credential은 Git Repository에 저장하지 않습니다.

App VM에서는 목적에 따라 Environment File을 분리하여 관리합니다.

예시:

```text
/etc/cnc-wearpoint/
├── backend.env
├── monitoring.env
└── object-storage.env
```

파일 접근 권한은 배포에 필요한 계정만 읽을 수 있도록 제한합니다.

Object Storage Credential 역시 환경변수로 주입하며 Source Code에 직접 작성하지 않습니다.

---

## 24. MLflow Schema Snapshot 재생성 예시

향후 로컬 MLflow MySQL Schema를 다시 기록해야 하는 경우 다음과 같이 구조만 Dump할 수 있습니다.

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

Windows PowerShell에서 복사:

```powershell
New-Item -ItemType Directory -Force .\sql\mlflow

docker cp `
  cnc-wearpoint-mysql:/tmp/mlflow.sql `
  .\sql\mlflow\mlflow.sql
```

새 Snapshot을 생성한 경우 기존 파일과 차이를 확인한 뒤 Git에 반영합니다.

---

## 25. Migration 보호 원칙

Migration 과정에서는 원본 환경을 바로 삭제하지 않는 것을 기본 원칙으로 합니다.

Migration 완료 후에도 일정 기간 다음 데이터를 Rollback 및 검증 용도로 보존합니다.

- 기존 SQLite Database
- 기존 MLflow Artifact
- 서비스 DB Backup
- 기존 이미지·Sensor 원본
- Migration 전 Path 정보
- 기존 MLflow Server 설정

서비스 DB 파일 경로 Migration 전에는 다음 Backup Table을 생성했습니다.

```text
measurements_path_backup_20261113_object_storage
```

Backup Row Count:

```text
918
```

이를 통해 Object Storage Path Migration 과정에서 문제가 발생할 경우 이전 값을 확인할 수 있도록 구성했습니다.

---

## 26. 현재 운영 데이터 흐름

### 서비스 데이터

```text
Frontend
   │
   │ HTTPS /api/
   ▼
Nginx
   │
   ▼
FastAPI
   │
   ├── TLS 1.3 + CA
   │       ↓
   │   RDS MySQL
   │   cnc_wearpoint
   │
   └── HTTPS / S3 API
           ↓
       Object Storage
       cnc-wearpoint-data
       ├── images
       └── sensors
```

### MLflow

```text
User / Model Developer
          │
          │ HTTPS /mlflow/
          ▼
        Nginx
          │
          ▼
       MLflow
       3.18.0
       │
       ├── TLS 1.3 + CA
       │       ↓
       │   RDS MySQL
       │   ├── mlflow
       │   └── mlflow_auth
       │
       └── S3 Compatible API
               ↓
          Object Storage
          cnc-wearpoint-mlflow
```

---

## 27. 현재 상태 요약

현재 Database 및 Storage 작업 상태는 다음과 같습니다.

```text
Local Development
│
├── MySQL
│   └── Schema / 개발 검증
│
└── Source Code
        │
        ▼
NHN Cloud
│
├── RDS for MySQL 8.4.6
│   ├── cnc_wearpoint
│   ├── mlflow
│   └── mlflow_auth
│
├── TLS 1.3 + CA Verification
│
├── Object Storage
│   ├── cnc-wearpoint-data
│   │   ├── Image 824
│   │   └── Sensor 895
│   │
│   └── cnc-wearpoint-mlflow
│       └── MLflow Artifact
│
├── FastAPI
│   ├── RDS 연결 완료
│   └── Object Storage 파일 조회 완료
│
└── MLflow
    ├── RDS Backend Store 전환 완료
    ├── Basic Auth DB 분리
    ├── Artifact Store 전환 완료
    └── Registry / Alias / Rollback 검증 완료
```

현재 상태는 다음과 같이 정리할 수 있습니다.

```text
RDS_MIGRATION_COMPLETE
TLS_CA_VERIFIED
OBJECT_STORAGE_MIGRATION_COMPLETE
MLFLOW_ARTIFACT_STORE_VERIFIED
MLFLOW_LIFECYCLE_VERIFIED
```

서비스 Database Migration과 Object Storage 전환은 완료되었습니다.

MLflow 역시 RDS Backend Store 및 Object Storage Artifact Store 기반으로 동작하며, Model Registry의 Version 및 Alias 전환과 Rollback 동작까지 검증했습니다.

현재 남은 핵심 작업은 **실제 CNC WearPoint 최종 모델을 MLflow Registry에 등록하고 FastAPI가 해당 모델을 불러와 실제 Inference를 수행하도록 연결하는 것**입니다.

---

## 28. 향후 작업

### 실제 모델 적용

- 최종 회귀 모델 확정
- 실제 Training Run MLflow 기록
- Parameter / Metric 기록
- Model Artifact 저장
- Registry 등록
- Model Version 관리
- `champion` Alias 지정
- FastAPI Registry Model Load
- 실제 `/predict` Inference 검증

### 데이터 품질 관리

- 품질 제외 이미지 상태 명시
- `image_status` 추가 검토
- `image_exclusion_reason` 추가 검토
- 누락 데이터와 품질 제외 데이터 구분

### Database 운영

- RDS Backup / Restore 절차 검증
- Schema Migration 관리 방식 정립
- 필요한 Index 성능 점검
- 운영 Query 성능 확인

### 보안 강화

- Credential 주기적 Rotation
- Environment File 권한 점검
- 필요 시 Client Certificate 기반 X509 / mTLS 검토
- Object Storage Credential 최소 권한 정책 적용

---

## 29. 핵심 설계 원칙

CNC WearPoint의 Database와 Storage 구성은 다음 원칙을 기준으로 합니다.

### 구조화 데이터는 RDS

```text
가공 조건
Measurement Metadata
Wear Label
Prediction
Alert
MLflow Metadata
Authentication Metadata
```

### 대용량 파일은 Object Storage

```text
CNC 이미지
Sensor CSV
MLflow Model Artifact
Model Weight
MLmodel
기타 실험 결과 파일
```

### Database에는 파일 자체가 아닌 경로를 저장

```text
measurements.image_path
→ images/set4/original/...

measurements.sensor_path
→ sensors/set4/...
```

이를 통해 Database의 용량 증가를 줄이고, 대용량 파일을 Object Storage에서 독립적으로 관리할 수 있도록 구성했습니다.

또한 서비스 데이터와 MLOps 데이터를 논리적으로 분리하여 장애 범위와 운영 책임을 명확하게 구분했습니다.

---

## 30. 결론

CNC WearPoint의 Database 구조는 로컬 개발용 MySQL에서 시작해 현재 NHN Cloud RDS 기반 운영 구조로 전환되었습니다.

서비스 업무 데이터는 `cnc_wearpoint`, MLflow Metadata는 `mlflow`, MLflow 인증 정보는 `mlflow_auth` Database에서 각각 관리합니다.

이미지와 Sensor Data는 `cnc-wearpoint-data`, MLflow Artifact는 `cnc-wearpoint-mlflow` Object Storage Bucket에 저장합니다.

RDS 연결은 TLS 1.3 및 CA 인증서 검증을 적용했고, FastAPI와 MLflow 모두 운영 환경에서 정상적인 Database 연결을 확인했습니다.

서비스 파일 역시 로컬 Storage 의존성을 제거하고 Object Storage에서 직접 조회하도록 전환했습니다.

따라서 현재 Database 및 Storage Infrastructure는 실제 CNC WearPoint 모델이 확정된 이후 **MLflow Registry → FastAPI Model Serving**을 연결할 수 있는 기반까지 구성된 상태입니다.