# CNC WearPoint Infrastructure

## 1. 문서 목적

이 문서는 CNC WearPoint 프로젝트의 **NHN Cloud 인프라 구성과 주요 네트워크 통신 구조**를 정리한 문서입니다.

현재 구성된 App 서버와 RDS를 중심으로 VPC, Subnet, Route Table, Security Group 등의 네트워크 구조와 각 자원의 역할을 설명합니다.

인프라를 단순히 구축하는 것보다 **애플리케이션 영역과 데이터베이스 영역을 분리하고, 필요한 통신만 허용하는 구조**를 만드는 것을 주요 설계 방향으로 삼았습니다.

---

## 2. 인프라 구성도

아래 구성도는 CNC WearPoint 서비스의 현재 NHN Cloud 인프라와 주요 네트워크 통신 흐름을 나타냅니다.

![CNC WearPoint Infrastructure](architecture/images/cnc_wp_infrastructure.png)

- [SVG 구성도](architecture/images/cnc_wp_infrastructure.svg)
- [구성도 생성 코드](architecture/diagrams/cnc_wp_infrastructure.py)

구성도는 Python `Diagrams`와 Graphviz를 사용해 코드로 관리하고 있으며, 인프라 변경 시 동일한 코드에서 구성도를 다시 생성할 수 있도록 구성했습니다.

---

## 3. 주요 통신 흐름

현재 인프라의 주요 통신 흐름은 다음과 같습니다.

```text
CNC WearPoint Team
        ↓
     Internet
        ↓
   Floating IP
        ↓
App Security Group
        ↓
     App VM
        ↓
DB Security Group
        ↓
 RDS for MySQL
```

CNC WearPoint 프로젝트 팀은 인터넷을 통해 App 서버의 Floating IP에 접근합니다.

App 서버에 대한 SSH 접속은 Security Group에서 허용된 공인 IP에 한해 접근할 수 있도록 제한했습니다.

App 서버에서 데이터베이스가 필요한 경우에는 외부 인터넷을 사용하지 않고 **VPC 내부 네트워크를 통해 RDS for MySQL에 접근**합니다.

RDS는 별도의 Private Subnet에 배치하고 외부 인터넷에 직접 노출하지 않도록 구성했습니다.

---

## 4. 전체 네트워크 구성

CNC WearPoint 서비스는 다음 VPC를 기준으로 구성했습니다.

| 항목 | 구성 |
|---|---|
| VPC | `cnc-wp-vpc` |
| CIDR | `10.60.0.0/20` |
| App Subnet | `10.60.0.64/27` |
| Database Subnet | `10.60.0.32/28` |

전체 구조는 다음과 같습니다.

```text
cnc-wp-vpc
10.60.0.0/20
│
├── App Network
│   └── cnc-wp-app-private
│       10.60.0.64/27
│
└── Database Network
    └── cnc-wp-db-private
        10.60.0.32/28
```

App과 Database를 서로 다른 Subnet으로 분리하여 각각의 역할과 네트워크 정책을 독립적으로 관리할 수 있도록 했습니다.

VPC는 현재 필요한 범위보다 여유 있는 `/20` 대역으로 구성하여 서비스 확장 시 추가 Subnet을 구성할 수 있는 주소 공간도 확보했습니다.

---

## 5. App Network

### cnc-wp-app-private

애플리케이션 서버를 배치하기 위한 네트워크입니다.

| 항목 | 구성 |
|---|---|
| Subnet | `cnc-wp-app-private` |
| CIDR | `10.60.0.64/27` |
| Route Table | `cnc-wp-app-rt` |
| Internet Gateway | `cnc-wp-igw` |
| 주요 자원 | `cnc-wp-app-01` |

App 서버는 API와 서비스 애플리케이션을 실행하고, 내부 네트워크를 통해 RDS와 통신하는 역할을 담당합니다.

### App VM

| 항목 | 구성 |
|---|---|
| Instance | `cnc-wp-app-01` |
| OS | Ubuntu Server 24.04 LTS |
| Instance Type | `m2.c2m4` |
| vCPU | 2 |
| Memory | 4 GB |
| Root Storage | SSD 150 GB |
| Floating IP | 사용 |
| Deletion Protection | 사용 |

초기 프로젝트 규모에서는 2 vCPU / 4 GB 사양으로 시작하고, 실제 서비스 부하가 증가하면 Instance Type을 확장할 수 있도록 구성했습니다.

Root Disk는 Docker 이미지, Python 패키지, 애플리케이션 파일, 로그 및 캐시 등에서 발생하는 I/O를 고려하여 **SSD 150 GB**를 사용했습니다.

---

## 6. App Routing

App Subnet은 `cnc-wp-app-rt` Route Table을 사용합니다.

| Destination | Target |
|---|---|
| `10.60.0.0/20` | local |
| `0.0.0.0/0` | `cnc-wp-igw` |

VPC 내부 자원과의 통신은 `local` 경로를 사용하고, 외부 인터넷 통신이 필요한 경우 `cnc-wp-igw` Internet Gateway를 사용합니다.

이를 통해 내부 통신과 외부 통신의 경로를 구분했습니다.

---

## 7. App Security Group

### cnc-wp-app-sg

App VM에 대한 외부 접근을 제어하기 위한 Security Group입니다.

현재 관리 목적의 SSH 접속은 프로젝트 팀이 사용하는 공인 IP만 허용하도록 구성했습니다.

| Direction | Protocol | Port | Source / Destination |
|---|---|---|---|
| Inbound | TCP | 22 | 허용된 공인 IP `/32` |
| Outbound | Any | Any | `0.0.0.0/0` |
| Outbound | Any | Any | `::/0` |

SSH 포트를 전체 인터넷(`0.0.0.0/0`)에 공개하지 않고 필요한 공인 IP만 `/32` 단위로 허용하여 관리 접근 범위를 제한했습니다.

서비스 공개를 위한 HTTP/HTTPS 정책은 실제 서비스 공개 방식에 맞춰 별도로 구성할 예정입니다.

---

## 8. Database Network

### cnc-wp-db-private

RDS for MySQL을 배치하기 위한 Database 전용 Private Subnet입니다.

| 항목 | 구성 |
|---|---|
| Subnet | `cnc-wp-db-private` |
| CIDR | `10.60.0.32/28` |
| Route Table | `cnc-wp-private-rt` |
| Internet Gateway | 연결하지 않음 |
| 주요 자원 | RDS for MySQL |

Database Network에는 Internet Gateway로 연결되는 기본 인터넷 경로를 구성하지 않았습니다.

이를 통해 RDS를 외부 인터넷에 직접 노출하지 않고 **App Network를 통해서만 데이터베이스에 접근하는 구조**로 구성했습니다.

---

## 9. Database Routing

Database Subnet은 `cnc-wp-private-rt` Route Table을 사용합니다.

| Destination | Target |
|---|---|
| `10.60.0.0/20` | local |

App VM과 RDS는 동일한 VPC 내부에 위치하므로 `local` 경로를 통해 통신합니다.

Database Network에는 Internet Gateway를 연결하지 않아 RDS가 외부 인터넷과 직접 통신하는 경로를 두지 않았습니다.

---

## 10. DB Security Group

### cnc-wp-db-sg

RDS에 대한 접근 범위를 제어하기 위한 Security Group입니다.

DB Port를 전체 인터넷에 공개하지 않고 App Subnet에서 발생하는 접근만 허용하도록 구성했습니다.

| Direction | Protocol | Port | Source |
|---|---|---|---|
| Inbound | TCP | MySQL DB Port | `10.60.0.64/27` |

따라서 외부에서 RDS로 직접 접근하는 것이 아니라 다음과 같은 흐름으로 데이터베이스에 접근합니다.

```text
Internet
   │
   X  직접 접근 불가
   │
RDS for MySQL


App VM
   │
   │ VPC 내부 통신
   ▼
DB Security Group
   │
   ▼
RDS for MySQL
```

이 구조를 통해 데이터베이스에 필요한 최소한의 네트워크 접근만 허용하도록 했습니다.

---

## 11. RDS for MySQL

서비스 데이터베이스는 NHN Cloud의 **RDS for MySQL**을 사용합니다.

| 항목 | 구성 |
|---|---|
| Database | RDS for MySQL |
| MySQL Version | 8.4.6 |
| Instance Type | `m2.c2m4` |
| vCPU | 2 |
| Memory | 4 GB |
| Storage Type | General SSD |
| Storage Size | 20 GB |
| Subnet | `cnc-wp-db-private` |
| Floating IP | 사용하지 않음 |
| Authentication Plugin | `caching_sha2_password` |
| Deletion Protection | 사용 |

초기 프로젝트 단계에서는 필요한 수준의 사양으로 시작하고, 실제 데이터 증가량과 서비스 부하를 확인하면서 Instance와 Storage를 확장할 수 있도록 구성했습니다.

또한 관리형 RDS를 사용하여 직접 MySQL 서버를 운영하는 방식보다 데이터베이스 운영 및 백업 관리 부담을 줄이는 방향을 선택했습니다.

---

## 12. 네트워크 분리 이유

App 서버와 Database를 하나의 네트워크에 모두 배치할 수도 있지만, CNC WearPoint에서는 역할에 따라 네트워크를 분리했습니다.

### App Network

외부 관리 접근과 서비스 실행이 필요한 애플리케이션 서버를 배치합니다.

### Database Network

외부 인터넷에 직접 노출할 필요가 없는 RDS를 배치합니다.

이를 통해 다음과 같은 효과를 기대할 수 있습니다.

- App과 Database의 역할을 명확하게 분리할 수 있습니다.
- RDS의 직접적인 인터넷 노출을 방지할 수 있습니다.
- Security Group을 통해 필요한 통신만 허용할 수 있습니다.
- 서비스 확장 시 네트워크 정책을 역할별로 관리하기 쉽습니다.

---

## 13. 구성도 표기 기준

구성도를 쉽게 이해할 수 있도록 연결선의 의미를 구분했습니다.

### 실선

**실선 화살표는 주요 통신 흐름을 의미합니다.**

```text
CNC WearPoint Team
→ Internet
→ Floating IP
→ App VM
→ RDS for MySQL
```

그림을 처음 확인할 때는 실선을 따라가면 현재 서비스의 주요 접근 흐름을 확인할 수 있습니다.

### 점선

**점선은 Route Table, Internet Gateway 등 네트워크 설정 또는 연결 관계를 의미합니다.**

따라서 점선을 애플리케이션 요청이 순서대로 이동하는 경로로 해석하지 않습니다.

통신 흐름과 네트워크 설정 관계를 서로 다른 선으로 표현하여 구성도를 처음 보는 사람도 전체 구조를 쉽게 이해할 수 있도록 했습니다.

---

## 14. 주요 설계 기준

### App과 Database의 네트워크를 분리했습니다

서비스를 실행하는 App 서버와 데이터를 저장하는 RDS의 역할을 구분하고 각각 별도의 Subnet에 배치했습니다.

### RDS를 외부에 직접 노출하지 않았습니다

RDS에는 Floating IP를 사용하지 않고 Internet Gateway와 직접 연결되는 경로도 구성하지 않았습니다.

App Network에서 필요한 데이터베이스 통신만 허용합니다.

### 관리 접근 범위를 제한했습니다

App VM의 SSH Port를 전체 인터넷에 공개하지 않고 프로젝트 팀이 사용하는 공인 IP만 허용했습니다.

### 초기 비용과 확장성을 함께 고려했습니다

초기에는 프로젝트 규모에 필요한 수준의 Instance 사양으로 구성하고, 이후 실제 서비스 부하에 따라 CPU와 Memory를 확장할 수 있도록 했습니다.

### 향후 확장을 고려한 주소 공간을 확보했습니다

현재 App 및 Database Subnet에서 사용하는 주소 공간뿐만 아니라 추가 서비스가 필요해질 경우 새로운 Subnet을 구성할 수 있도록 VPC를 `/20` 대역으로 설계했습니다.

---

## 15. 현재 구성 요약

현재 CNC WearPoint의 주요 인프라 흐름은 다음과 같습니다.

```text
CNC WearPoint Team
        │
        │ SSH
        ▼
     Internet
        │
        ▼
   Floating IP
        │
        ▼
cnc-wp-app-sg
        │
        ▼
cnc-wp-app-01
        │
        │ VPC Internal
        ▼
 cnc-wp-db-sg
        │
        ▼
 RDS for MySQL
```

현재 단계에서는 **App 서버와 Database의 역할을 분리하고, RDS를 외부에 직접 노출하지 않으면서 필요한 내부 통신만 허용하는 것**을 핵심으로 인프라를 구성했습니다.

단순히 클라우드 자원을 생성하는 데 그치지 않고, 서비스의 역할과 접근 범위를 고려해 네트워크와 보안 구조를 설계하는 것을 목표로 했습니다.