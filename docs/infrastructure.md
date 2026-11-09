# CNC WearPoint NHN Cloud 인프라 구성

![CNC WearPoint Infrastructure](images/cnc_wp_infrastructure.png)

## 1. 구성 목적

CNC WearPoint의 FastAPI, MLflow, React/Nginx, RDS for MySQL을 NHN Cloud 환경에 배치하기 위한 네트워크 및 인프라 구조이다.

초기에는 단일 App VM과 RDS를 중심으로 구성하고, 향후 Object Storage, GPU 추론 서버, NKS, Kubeflow, Istio, Prometheus/Grafana 등으로 확장할 수 있도록 VPC 주소 공간을 확보하였다.

---

## 2. VPC

- VPC 이름: `cnc-wp-vpc`
- CIDR: `10.60.0.0/20`

현재 필요한 서브넷만 생성하고 나머지 주소 공간은 향후 NKS 및 추가 서비스 확장을 위해 예약한다.

---

## 3. App Network

### Subnet

- 이름: `cnc-wp-app-private`
- CIDR: `10.60.0.64/27`

FastAPI, MLflow, React/Nginx 및 초기 Airflow 등의 애플리케이션 서버를 배치하는 영역이다.

### App VM

- 이름: `cnc-wp-app-01`
- OS: Ubuntu Server 24.04 LTS
- 인스턴스 타입: `m2.c2m4`
- vCPU: 2
- RAM: 4GB
- Root Storage: General SSD 150GB

CPU와 메모리는 초기 규모에 맞춰 작게 시작하고, 사용량 증가 시 인스턴스 타입을 Scale-up하는 방향으로 운영한다.

### Routing

`cnc-wp-app-rt`에는 Internet Gateway가 연결되어 있으며 외부 통신이 필요한 App 영역만 인터넷 경로를 사용한다.

```text
10.60.0.0/20 → local
0.0.0.0/0    → cnc-wp-igw
```

### Security Group

`cnc-wp-app-sg`를 적용한다.

SSH 접속은 전체 인터넷에 개방하지 않고 팀에서 사용하는 공인 IP `/32`만 허용한다.

---

## 4. Database Network

### Subnet

- 이름: `cnc-wp-db-private`
- CIDR: `10.60.0.32/28`

RDS for MySQL을 App 영역과 분리하여 배치한다.

### RDS for MySQL

- MySQL: 8.4.6
- Instance: 2 vCPU / 4GB
- Storage: General SSD 20GB
- 초기 구성: Single
- 향후: HA 구성 검토

### Routing

`cnc-wp-private-rt`를 기본 라우팅 테이블로 사용한다.

Internet Gateway를 연결하지 않고 VPC 내부 통신만 허용한다.

```text
10.60.0.0/20 → local
```

### DB Security Group

`cnc-wp-db-sg`를 사용하며 App 서브넷에서 들어오는 DB 연결만 허용한다.

```text
Source
10.60.0.64/27

Destination
RDS for MySQL

Port
DB Port
```

RDS를 인터넷에 직접 노출하지 않는 것을 기본 정책으로 한다.

---

## 5. 데이터 저장 구조

대용량 파일은 App VM의 Root Storage에 지속적으로 저장하지 않고 Object Storage로 분리할 예정이다.

### RDS for MySQL

- 서비스 데이터
- 측정 메타데이터
- 마모 정답 데이터
- 모델 예측 결과
- 알림 데이터
- MLflow Metadata

### Object Storage

- CNC 이미지
- 센서 관련 대용량 데이터
- MLflow Artifact
- 모델 파일

---

## 6. 향후 확장

현재 VPC 내 주소 공간을 활용하여 다음 서비스를 단계적으로 추가할 예정이다.

### GPU Integration Server

현재 모델 개발에 사용하는 GPU 인스턴스 중 하나를 향후 통합 추론 서버로 활용하는 방안을 검토한다.

### NKS

향후 Kubernetes 기반 운영으로 확장할 경우 NKS Worker 전용 네트워크를 별도로 구성한다.

예정 영역:

```text
10.60.4.0/22
```

NKS 위에서는 다음 서비스를 검토한다.

- FastAPI
- MLflow
- Airflow
- Kubeflow
- Istio
- Prometheus
- Grafana

---

## 7. 네트워크 설계 원칙

- VPC는 향후 확장을 고려해 `/20`으로 확보
- 실제 Subnet은 필요한 크기만 할당
- 기본 Routing Table은 Private 정책 적용
- 인터넷 연결이 필요한 App 영역만 별도 Internet Gateway 사용
- RDS는 외부 인터넷에 직접 노출하지 않음
- Security Group은 필요한 CIDR과 포트만 허용
- 대용량 데이터는 Object Storage로 분리
- NKS, Monitoring, CI/CD 영역은 필요 시 추가