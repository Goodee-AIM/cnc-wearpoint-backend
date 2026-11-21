# 모델 라이프사이클 현재 상태 (CNC WearPoint)

- 작성일: 2026-11-20
- 범위: MLflow Registry -> Object Storage(S3) -> Serving -> Backend -> RDS(MySQL) -> Frontend
- 작성 방식: 저장소 코드를 로컬에서 읽고 오프라인으로 분석했습니다. 운영 상태는 사용자가 운영 VM에서 직접 실행한 **read-only 조회 결과(2026-11-20)** 로 보강했습니다(0절). 분석 과정에서 운영 Alias, Serving, RDS, Object Storage는 변경하지 않았습니다.
- 표기 규칙
  - **[코드 검증]**: 이 저장소의 코드나 파일에서 확인한 내용입니다(`파일:라인` 근거 포함).
  - **[핸드오프]**: 사용자 인계 내용이며, 여기서는 검증하지 않았습니다.
  - **[미확인]**: 운영 환경에서 read-only로 확인해야 하는 내용입니다(확인 명령은 6절 참고).
  - **[운영 확인]**: 2026-11-20 운영 VM에서 사용자가 실행한 read-only 조회 결과입니다(0절).

관련 문서: [MODEL_LIFECYCLE_TEST_PLAN.md](MODEL_LIFECYCLE_TEST_PLAN.md), [MODEL_PROMOTION_ROLLBACK_RUNBOOK.md](MODEL_PROMOTION_ROLLBACK_RUNBOOK.md)

---

## 0. 운영 read-only 조회 결과 (2026-11-20, 사용자 실행) **[운영 확인]**

조회 명령: `docker ps`, `curl http://127.0.0.1:8001/health`, `docker inspect`, `docker logs`, 운영 Serving 컨테이너 안에서 `MlflowClient` GET 전용 호출(`get_registered_model`, `search_model_versions`, `get_model_version`, `get_logged_model`, `get_run`, artifact 목록/`MLmodel` 읽기). Alias 변경·재시작·삭제는 하지 않았습니다.

### 0.1 실행 중인 컨테이너

| 컨테이너 | 이미지 | 비고 |
|---|---|---|
| cnc-wearpoint-serving | `quay.io/melona240/cnc-wearpoint-serving:f38806e72295aa73a72ad1daea83ff4335426072` | 2026-11-20T00:16:44Z 시작, restart=unless-stopped, `127.0.0.1:8001` |
| cnc-wearpoint-backend | `quay.io/melona240/cnc-wearpoint-backend:v0.1.12` | |
| cnc-wearpoint-frontend | `quay.io/melona240/cnc-wearpoint-frontend:a94bf01…` | |

- Serving 이미지 `f38806e` 이후 `ml/serving/**` 변경 커밋이 없으므로, 운영 Serving 이미지의 `/app` 코드는 현재 저장소의 `ml/serving`과 같습니다(`git log f38806e..HEAD -- ml/serving` 결과 없음).

### 0.2 Serving 상태와 실행 정의

| 항목 | 값 |
|---|---|
| `/health` | `{"status":"ok","model_name":"cnc-wearpoint-multitask","model_alias":"candidate","model_version":"1","model_loaded":true}` |
| env | `MODEL_NAME=cnc-wearpoint-multitask`, `MODEL_ALIAS=candidate`, `MLFLOW_TRACKING_URI=https://aimw.duckdns.org/mlflow/` (`MODEL_VERSION` 없음) |
| 실행 정의 | `/opt/cnc-wearpoint/serving/compose.yaml` (compose project `cnc-wearpoint-serving`, **저장소 밖, 수동 운영**) |
| compose 내용(비밀값 제외) | image SHA 고정, `env_file: /etc/cnc-wearpoint/inference.env`, `OMP_NUM_THREADS=4`, `MKL_NUM_THREADS=4`, `INFERENCE_BATCH_SIZE=2`, `mem_limit: 3g`, ports `127.0.0.1:8001:8001`, external network `compose_default` |
| 로그 | 기동 시 load 완료까지만 출력, **로드한 model_version을 로그로 남기지 않음**. `/predictions` 200 OK 다수 |

해석:
- 운영 Serving은 **V1을 로드**하고 있으며 Alias(`candidate`)로 기동 시 version을 해석합니다(2.1의 S3와 일치).
- Serving은 Backend와 **별도 compose project**(`/opt/cnc-wearpoint/serving`)입니다. Backend 배포 job은 `/opt/cnc-wearpoint/backend`에서만 `up --remove-orphans`를 실행하므로 **Backend 배포가 Serving을 재생성하거나 제거하지 않습니다**(2.7의 미확인 항목 해소).
- Serving은 기동 시 **공개 URL(`https://aimw.duckdns.org/mlflow/`)과 nginx/TLS를 거쳐** MLflow에 접속합니다. nginx, 인증서, DNS 장애 시 Serving 재시작이 실패합니다(S5의 fail-hard와 결합).

> **변경 기록 (2026-11-20 오후):** 모니터링 추론 지연(추론 평균 약 5.2초, 대기 최대 43초) 대응으로 Serving env `MODEL_ALIAS`를 `candidate-opt`로 바꿔 **V2로 전환**했습니다(방식 A, Registry Alias 변경 없음). 전환 후 `/health` = `model_alias: candidate-opt, model_version: 2`. 전환 근거: 로컬 비교에서 V1/V2 출력 9개 필드 완전 동일, 지연 시간 2.28초 → 0.23초(TEST_PLAN INF-00). 전환 후 운영 측정(최근 20건): 추론 0.8~1.7초(평균 약 1.1초), 대기 0.1~2.1초, 전부 `model_version` 2. 이 절의 위 표는 전환 전 상태입니다.

> **변경 기록 (2026-11-21):** 이미지를 `quay.io/melona240/cnc-wearpoint-serving:v0.1.2`(digest `sha256:c9652af7…`, 커밋 `46e4048`)로 교체하고, `MODEL_ALIAS`를 `production`으로 바꿨습니다. Registry에 `production` alias를 새로 만들었습니다(현재 v2, `lifecycle.production.previous_version = 1`). 현재 `/health` = `model_alias: production, model_version: 2, model_run_id: 98c32cdb968d4f57b77330db6c13baf4`. 백업 파일은 `/opt/cnc-wearpoint/serving/compose.yaml.bak-20261121`, `/etc/cnc-wearpoint/inference.env.bak-20261121`입니다(교체 전 상태: `f38806e`, `candidate-opt`). 평가·승격·롤백 기록은 [검증 보고서 0장](MODEL_LIFECYCLE_VERIFICATION_REPORT.md)을 참고하세요.

### 0.3 MLflow Registry (mlflow 3.18.0)

| 항목 | Version 1 | Version 2 |
|---|---|---|
| Alias | `candidate` | `candidate-opt` |
| status | READY | READY |
| run_id | `f61d462aabe8483290e8906117271c63` | `98c32cdb968d4f57b77330db6c13baf4` |
| source (logged model) | `models:/m-04bfd5b99f9f48258157026e5e204491` | `models:/m-3e81fad641f64fb9bb5fb63348b37521` |
| 생성(MLmodel utc_time_created) | 2026-11-16 08:37:38 UTC | 2026-11-17 08:46:17 UTC |
| flavor | `python_function` (loader `mlflow.pyfunc.model`) | `python_function` (동일) |
| signature | 입력 6개(image_path, sensor_path, crop×4) / 출력 9개 | **V1과 동일** |
| metadata | batch_size=2, checkpoint=epoch_010.pth, device=cpu | 동일 |
| `artifacts/epoch_010.pth` | 45,870,091 bytes | 45,870,091 bytes (크기 동일, 해시 미확인) |
| `code/inference.py` / `mlflow_model.py` / `preprocessing.py` | 4188 / 2228 / 6522 bytes | 5537 / 2789 / 6697 bytes |
| `requirements.txt` / `conda.yaml` | 63 / 183 bytes | 175 / 311 bytes |
| run metrics / logged model metrics·params | **없음** | **없음** |
| model version tags | 없음 | 없음 |

해석:
- **핸드오프의 "V2 artifact에 `data/model.pt2`가 있다"는 사실이 아닙니다.** V2는 V1과 같은 pyfunc 구조이며 `model.pt2`가 없습니다.
- 파일 크기 대조 결과 **로컬 `testdata/mlflow_candidate_v1` = Registry V1**(MLmodel 1852, code 4188/2228/6522, requirements 63 bytes 일치), **저장소 `ml/serving/{inference,mlflow_model,preprocessing}.py` = Registry V2의 `code/`**(5537/2789/6697 bytes 일치)입니다. 즉 V2는 현재 저장소 코드를 `register_candidate.py`로 등록한 것으로 판단됩니다.
- V1→V2 코드 차이(로컬 diff): `preprocessing.py`는 줄바꿈 문자만 다름(내용 동일), `inference.py`는 이미지 특징을 요청당 1회만 계산해 재사용하는 **속도 최적화**(eval 모드에서 수학적으로 동일한 연산), `mlflow_model.py`는 `INFERENCE_BATCH_SIZE` env 지원 추가.
- 두 버전 모두 run/logged model에 **평가 지표가 없어 Registry만으로는 성능 비교가 불가능**합니다. V1/V2 비교는 동일 입력 추론 결과(동등성)와 지연 시간 측정으로 새로 해야 합니다.

---

## 1. 전체 아키텍처

```
[MLflow Tracking/Registry]  App VM, systemd, 127.0.0.1:5000, /mlflow/ 프록시 + auth      [핸드오프]
   │  메타데이터: RDS MySQL (registered_models / model_versions / registered_model_aliases)
   │  아티팩트:   s3://cnc-wearpoint-mlflow/mlflow-artifacts                               [핸드오프]
   ▼
[Serving 컨테이너]  ml/serving/service.py, FastAPI, port 8001                              [코드 검증]
   │  기동 시 1회: alias -> version 해석, 이후 models:/NAME/VERSION 을 pyfunc로 로드
   ▼  POST /predictions (multipart: image, sensor_csv)
[Backend]  app/services/prediction_execution.py (SERVING_URL, 기본값 http://cnc-wearpoint-serving:8001)
   │  응답 검증 -> model_name, model_version 저장
   ▼
[RDS: cnc_wearpoint]  predictions, monitoring_inference_runs
   ▼
[Frontend]  Set 목록 API가 measurement별 최신 prediction의 model_version을 반환 (app/api/routers/sets.py:108,117-125)
```

---

## 2. (a) 코드에서 검증한 사실

### 2.1 Serving 모델 선택과 alias 해석 시점

| # | 내용 | 근거 |
|---|---|---|
| S1 | 모델은 env `MODEL_NAME`(기본 `cnc-wearpoint-multitask`)과 `MODEL_ALIAS`(기본 `candidate`)로만 선택합니다. `MODEL_VERSION`이나 `MODEL_URI`를 지정하는 override는 없습니다. | ml/serving/service.py:13-21 |
| S2 | `MLFLOW_TRACKING_URI`는 필수입니다. `os.environ[...]`로 읽기 때문에 값이 없으면 기동 시 KeyError가 납니다. | ml/serving/service.py:88 |
| S3 | **alias는 FastAPI lifespan(기동 시)에 한 번만 해석합니다.** `MlflowClient().get_model_version_by_alias`로 version을 얻은 뒤 `models:/{name}/{version}`을 로드합니다. 요청 처리 중에는 alias를 다시 해석하지 않습니다. | ml/serving/service.py:80-102 (94행 주석 "Resolve alias once, then load the immutable Registry version") |
| S4 | 로드는 `mlflow.pyfunc.load_model`을 통한 범용 pyfunc 경로뿐입니다. flavor 분기나 로드 후 signature 검사는 없습니다. | ml/serving/service.py:100-102 |
| S5 | 로드 실패 시 retry나 fallback이 없습니다. MLflow 접속 불가, auth 실패, alias 없음, S3 다운로드 실패 중 어느 경우든 lifespan에서 예외가 나고 프로세스가 종료됩니다. 따라서 `model_loaded=false`와 503 분기는 실제 서비스 중에는 사실상 도달하지 않습니다. | ml/serving/service.py:95-102, 126, 139-143 |
| S6 | `/health`는 항상 `status: "ok"`를 반환하며 model_name, model_alias(env 문자열), model_version(기동 시 해석한 값), model_loaded를 포함합니다. reload, readiness, admin 엔드포인트는 없습니다. route는 `/health`와 `/predictions` 두 개뿐입니다. | ml/serving/service.py:116-127, 130 |
| S7 | 응답의 `model_name`과 `model_alias`는 env 값을 그대로 돌려주는 것이고, Registry에서 다시 읽은 값이 아닙니다. | ml/serving/service.py:13-21, 257-259 |

**결론 (alias 변경이 hot-swap되는지): 되지 않습니다.** alias를 옮겨도 실행 중인 Serving은 기동 시 해석한 version을 계속 사용합니다. 새 version은 Serving 프로세스(컨테이너)를 재시작해야 반영됩니다(S3). 또 실행 중인 Serving은 alias 이름(env)과 이전 version을 함께 보고합니다. 그래서 alias가 이미 다른 version으로 옮겨졌어도 `/health`만 보면 정상처럼 보입니다(S6, S7).

> 주의: 반대로 **의도하지 않은 재시작**이 일어나면(VM reboot, Docker restart policy, compose up 등) 그 시점에 `candidate`가 가리키는 version이 조용히 로드됩니다. alias를 옮기는 것은 곧 "다음 재시작 때 운영에 반영되는 변경"입니다.

### 2.2 Serving 입출력 계약

| # | 내용 | 근거 |
|---|---|---|
| C1 | `POST /predictions`는 multipart `image`(.jpg/.jpeg/.png)와 `sensor_csv`(.csv)를 받습니다. 두 파일을 temp dir에 저장한 뒤 1행 DataFrame(image_path, sensor_path, crop_left/top/right/bottom)을 만듭니다. 이미지가 600x400이면 전체 이미지를 쓰고, 아니면 FIXED_CROP(1150,670,1750,1070)을 씁니다. | ml/serving/service.py:27-30, 36-62, 130-218 |
| C2 | `model.predict(df).iloc[0]`에서 predicted_wear_um, predicted_type, flank_wear_probability, epoch, window_count, sampling_hz 컬럼을 읽습니다. 이 컬럼이 없으면 KeyError가 나고 HTTP 500이 됩니다. | ml/serving/service.py:203-273 |
| C3 | crop/predict 블록 안의 ValueError는 HTTP 400으로 바뀝니다(pyfunc의 "Missing required columns" 포함). 그 밖의 예외는 500입니다. | ml/serving/service.py:198-279; ml/serving/mlflow_model.py:41-45 (참고: mlflow_model.py:74-82의 FileNotFoundError는 ValueError가 아니므로 500) |
| C4 | `/predictions`는 `async def`이지만 동기 `model.predict`를 직접 호출합니다. 이 때문에 event loop가 막혀 추론 중에는 `/health`도 응답이 늦어집니다. uvicorn은 단일 프로세스(`--workers` 없음)입니다. | ml/serving/service.py:130-134, 220; ml/serving/Dockerfile:22 |
| C5 | pyfunc wrapper의 `load_context`는 `inference.load_model`을 호출합니다. 이 함수는 `torch.load(weights_only=True)`를 쓰고, 체크포인트 **epoch == 10**이 아니면 ValueError를 냅니다. | ml/serving/mlflow_model.py:16-24; ml/serving/inference.py:52-55 |
| C6 | 이미지: `python:3.11-slim`, requirements 설치, `COPY . .`, port 8001 | ml/serving/Dockerfile:1, 16, 18, 20, 22 |
| C7 | torch==2.15.0+cpu, torchvision==0.29.2+cpu, mlflow==3.18.0은 pin되어 있습니다. numpy, scipy, Pillow, fastapi, uvicorn, python-multipart는 unpinned이고 pandas는 하한(`>=2.0`)만 있으므로 같은 commit을 다시 빌드해도 결과가 달라질 수 있습니다. | ml/serving/requirements.txt:9-10, 12-21 |

### 2.3 V1 아티팩트(로컬 사본: testdata/mlflow_candidate_v1)

| # | 내용 | 근거 |
|---|---|---|
| A1 | flavor는 `python_function` 하나뿐입니다(loader_module `mlflow.pyfunc.model`, python_model.pkl, code/, artifact `checkpoint` -> artifacts/epoch_010.pth). pytorch나 torch.export flavor는 없고 model.pt2도 없습니다. | testdata/mlflow_candidate_v1/MLmodel:2-16 |
| A2 | 식별자: model_id `m-04bfd5b99f9f48258157026e5e204491`, run_id `f61d462aabe8483290e8906117271c63`, experiment 4, mlflow 3.18.0, python 3.11.18, 생성 2026-11-16 08:37:38 UTC, model_size_bytes 45870291 | testdata/mlflow_candidate_v1/MLmodel:1, 15, 22-25, 27, 43 |
| A3 | signature 입력은 image_path(str), sensor_path(str), crop_left/top/right/bottom(long)입니다. 출력은 epoch, predicted_wear_um, flank_wear_probability, predicted_type, threshold, window_count, sampling_hz, cut_start_index, cut_end_index_exclusive입니다. metadata는 batch_size=2, checkpoint=epoch_010.pth, device=cpu입니다. | testdata/mlflow_candidate_v1/MLmodel:18-21, 28-41 |
| A4 | 로컬 SHA-256: epoch_010.pth `a6bf94e5bb6ffbf7512dbf060c8040c2cf32697b327e8d1d583d17d55ddcb7bd`(45870091 bytes), python_model.pkl `e846b59285f72262474f52e25542c9ed4eebe90edc9f7776e4878b6d8314387d` | sha256sum 실행 결과 |
| A5 | 패키징된 requirements는 torch와 torchvision이 unpinned입니다. 반면 Serving 이미지는 torch를 pin합니다. 지금의 register_candidate.py는 ml/serving/requirements.txt(torch pin 포함)를 pip_requirements로 넘기므로, V1은 지금 상태의 스크립트/requirements로 등록된 것이 아닙니다. (참고: `dependency_pins=pending` run tag는 지금의 스크립트도 설정하며(register_candidate.py:131), V1 run에 이 tag가 있는지는 testdata로 확인할 수 없습니다.) | testdata/mlflow_candidate_v1/requirements.txt:1-7; ml/serving/register_candidate.py:72,131,147 |
| A6 | 패키징된 code/는 저장소 코드와 다릅니다. mlflow_model.py는 `INFERENCE_BATCH_SIZE` env를 무시하고 self.batch_size(2)를 씁니다(저장소 버전은 env를 읽음). inference.py는 저장소 버전에 ResNet image feature 재사용 최적화가 들어 있습니다. preprocessing.py는 CRLF만 다릅니다. | `diff --strip-trailing-cr ml/serving/*.py testdata/mlflow_candidate_v1/code/*`; ml/serving/mlflow_model.py:48-62,97; ml/serving/inference.py:62-164 |
| A7 | ml/serving/*는 commit 20ad61a(2026-11-17)에서 처음 추가됐습니다. V1(2026-11-16)보다 나중이므로, V1을 등록한 코드는 이 저장소 이력에 없습니다. | git log -- ml/serving; MLmodel:43 |
| A8 | python_model.pkl은 모듈 이름 `mlflow_model.CncWearPointModel`로 클래스를 참조합니다. 런타임에 artifact의 code/와 /app 중 어느 쪽이 import되는지는 미확인입니다(pickle은 해제하지 않고 바이트만 스캔했습니다). | python_model.pkl 바이트 스캔; ml/serving/Dockerfile:7,18 |
| A9 | V1의 `artifact_path`는 `mlflow-artifacts:/4/models/...`입니다. 즉 artifact는 MLflow 서버의 artifact proxy(`--serve-artifacts`)를 통해 업로드/다운로드되며, Serving은 S3에 직접 접근하지 않습니다. 로컬 `.env.inference.local`에도 AWS 관련 키가 없고 MLFLOW_TRACKING_URI/USERNAME/PASSWORD, MODEL_NAME, MODEL_ALIAS, INFERENCE_BATCH_SIZE 키만 있습니다(값은 열람하지 않음). 따라서 S3 장애는 "MLflow 서버의 artifact 다운로드 실패"로 Serving에 나타납니다. 운영 Serving env에 AWS 키가 있는지는 U3에서 확인합니다. | testdata/mlflow_candidate_v1/MLmodel:1; ml/serving/.env.inference.local(키 이름만) |

### 2.4 V1 vs V2 flavor 호환성 위험

> **2026-11-20 운영 조회로 갱신(0.3절):** V2는 V1과 같은 `python_function` flavor, 같은 signature, 같은 크기의 checkpoint를 가집니다. 아래의 "torch.export(`model.pt2`)이면 서빙 불가" 시나리오는 **해당하지 않습니다.** 남은 확인 항목은 (1) 두 checkpoint의 해시 동일 여부, (2) V2의 requirements(175 bytes)가 Serving 이미지 패키지와 맞는지, (3) V1/V2 동일 입력 결과 동등성과 지연 시간, (4) U5(런타임 import 경로)입니다. 아래 원문은 조회 전 분석 기록으로 남깁니다.

- **[핸드오프, 운영 조회로 반박됨]** V2(alias `candidate-opt`)의 artifact에는 MLmodel, `data/model.pt2`, env info, requirements.txt가 있다고 합니다. 그렇다면 torch.export 계열 flavor일 가능성이 있습니다.
- **[코드 검증]** Serving은 `mlflow.pyfunc.load_model`(service.py:100)로 로드하고, 파일 경로 DataFrame을 넘긴 뒤 이름이 정해진 출력 컬럼을 읽습니다(service.py:203-273).
- **판단(코드 근거에 따른 추론이며 V2는 미검증)**: V2에 V1과 같은 입출력 signature를 지키는 custom `python_function` flavor가 없다면 다음 중 하나가 됩니다.
  1. 기동 시 로드 실패: lifespan 예외 -> 컨테이너 종료 -> 수동, 자동, 모니터링 추론이 모두 중단됩니다(S5).
  2. 로드는 되지만 predict에서 KeyError나 shape 오류 -> HTTP 500 -> Backend가 retryable 502 / INFERENCE_FAILED로 처리합니다.
  3. predict 안의 ValueError -> HTTP 400 -> Backend가 **INPUT_REJECTED(재시도 불가)로 잘못 분류**하고 measurement를 failed로 표시합니다(prediction_execution.py:200-202, 391-397; monitoring_inference_queue.py:310-313).
- V2가 이 저장소의 wrapper를 쓰면서 epoch ≠ 10 체크포인트를 담고 있다면 load_context에서 실패합니다(inference.py:54).
- `.pt2`는 torch 버전 간 호환이 보장되지 않습니다. 이미지의 torch 2.15.0+cpu와 맞는지 확인해야 합니다(ml/serving/requirements.txt).
- ~~V2의 실제 flavor와 signature는 미확인(U1)입니다. 승격의 최대 blocker입니다.~~ → **해소(0.3절): V1과 동일한 pyfunc/signature.**

### 2.5 Backend 검증

| # | 내용 | 근거 |
|---|---|---|
| B1 | 호출: `{SERVING_URL}/predictions`, timeout 180초, 응답 최대 64 KiB | app/services/prediction_execution.py:188-199 |
| B2 | 오류 매핑: HTTP 400 -> ServingInputRejected(422 INPUT_REJECTED, retry 없음). 그 밖의 HTTPError -> RuntimeError("Serving returned HTTP N"). URLError/TimeoutError -> RuntimeError("Serving is unavailable"). dict가 아닌 응답 -> ValueError | prediction_execution.py:200-208 |
| B3 | `validate_model_result`의 검사 항목: predicted_wear_um은 유한한 Decimal이고 0 이상 1e7 미만(소수 5자리로 반올림한 뒤 1e7 미만인지 다시 검사). model_version은 `str()` 후 `[1-9][0-9]*`. model_name은 1~100자이며 `PREDICTION_MODEL_NAME`(기본 cnc-wearpoint-multitask)과 같아야 함. predicted_type은 1~100자. Serving의 `status`는 무시하고 150/200 기준으로 다시 계산합니다. KeyError/InvalidOperation/TypeError는 "Invalid Serving prediction result" ValueError로 바뀝니다. | prediction_execution.py:211-234; app/core/wear_policy.py:4-5, 8-17 |
| B4 | 특정 version이나 alias를 pin하는 Backend env는 없습니다. 양의 정수 version이면 모두 허용하고(로컬에서 `"2"`와 int 2는 허용, `"02"`, `"2.0"`, `"candidate-opt"`는 거부됨을 확인), model_alias는 검증하지 않습니다. | prediction_execution.py:219-227 |
| B5 | 응답 수신 중 연결이 끊기는 경우(RemoteDisconnected, ConnectionResetError, IncompleteRead)는 URLError 절에서 잡히지 않습니다. 대신 각 호출자의 generic `except Exception`에서 502 또는 INFERENCE_FAILED로 처리되고, 저장되지 않습니다. | prediction_execution.py:204-205, 398-404; manual_replay_prediction.py:102-104; monitoring_inference_queue.py:314-316 |
| B6 | Serving 재시작 중 요청이 들어오면 measurement는 failed(claim_id로 fence)가 되고 502를 반환합니다. auto-predict와 retry는 INFERENCE_FAILED와 함께 retry cookie를 발급합니다. 모니터링 run은 INFERENCE_FAILED로 기록되고 자동 재큐잉되지 않습니다. | prediction_execution.py:386-404; app/api/routers/auto_prediction.py:184-199, 270-286; monitoring_inference_queue.py:286-319 |
| B7 | Backend가 죽으면 measurement가 `predicting` 상태로 남습니다. 운영자가 scripts/recover_stale_prediction.py로 복구해야 하며 최소 30분이 지나야 합니다. 모니터링 run은 다음 worker가 WORKER_INTERRUPTED로 처리합니다. | prediction_execution.py:34-36, 316-383; scripts/recover_stale_prediction.py:4-5; monitoring_inference_queue.py:104-124 |
| B8 | capacity: 프로세스 안에서 수동과 모니터링이 각각 BoundedSemaphore(1)을 쓰고, 프로세스 사이는 MySQL `GET_LOCK('cnc_wp_monitoring_queue')`로 직렬화합니다. | app/services/inference_capacity.py:10-14; monitoring_inference_queue.py:260-283 |
| B9 | 기존 테스트 6개 파일(67개)이 계약 일부를 다룹니다(파일 구성은 test_prediction_execution 25, test_auto_prediction 18, test_monitoring_inference_queue 13, test_monitoring_inference_recovery 6, test_manual_replay_prediction 3, test_inference_capacity 2 = 67로 추정). 그중 model_version은 `"1"`만 다루고, "Unexpected model name"과 URLError, timeout, RemoteDisconnected 케이스는 없습니다. Serving HTTP 400 -> INPUT_REJECTED 매핑은 다룹니다. | tests/test_prediction_execution.py:89-168, 286-330 외 (pytest 67 passed) |

### 2.6 Audit 컬럼

| # | 내용 | 근거 |
|---|---|---|
| D1 | `predictions`: model_name varchar(100) NOT NULL, model_version varchar(100) NOT NULL. model_alias, run_id, model_uuid, Serving 이미지 컬럼은 **없습니다**. | sql/schema.sql:78-101; sql/cnc/schema.sql:78-91 |
| D2 | `monitoring_inference_runs`: model_name과 model_version은 nullable이고, status='completed'이면 CHECK 제약으로 둘 다 필수입니다. alias 컬럼은 없습니다. | sql/cnc/migrations/20261119_monitoring_inference_runs.sql:35-36, 61-73 |
| D3 | 쓰기 경로: persist_prediction(수동, auto, retry) -> predictions(+ alert). _save_replay -> predictions에 append(alert는 insert하지 않음). monitoring _finish -> monitoring_inference_runs. model_alias는 응답에만 포함되고 저장되지 않습니다. | prediction_execution.py:258-265, 267-272, 292; manual_replay_prediction.py:46, 60-67; monitoring_inference_queue.py:168-174 |
| D4 | `import_predictions.py`는 model_name `rf-csv-demo`, version `rf-csv-demo-v1`을 하드코딩해 넣습니다. version 기준 audit에서는 이 행을 제외해야 합니다. | import_predictions.py:9-10, 146-165 |
| D5 | MLflow `registered_model_aliases(workspace, name, alias, version)`의 PK는 (workspace, name, alias)이고 현재 매핑만 저장합니다. **alias 변경 이력 테이블은 없습니다.** registered_models로 가는 FK에는 ON DELETE CASCADE가 걸려 있습니다. sql/mlflow/mlflow.sql은 데이터 없이 스키마만 담은 dump입니다(INSERT 0건). | sql/mlflow/mlflow.sql:1259-1266, 2188 |
| D6 | Backend `/health`는 Serving의 model과 version을 보고하지 않습니다. | app/api/routers/health.py:6-8 |

정리하면, 저장된 각 prediction이 **어느 Registry version으로 만들어졌는지는 추적할 수 있습니다.** 반면 어느 alias로 서빙됐는지, alias가 언제 옮겨졌는지, 같은 번호의 version이 다시 등록됐는지는 앱 데이터만으로 알 수 없습니다.

### 2.7 CI/CD: Serving과 Backend

| 항목 | Backend | Serving | 근거 |
|---|---|---|---|
| Runner | `cnc-wp-runner`(self-hosted, App VM) | 같음 | .gitlab-ci.yml:1-8; docs/infrastructure.md:150 |
| 빌드 | main의 모든 pipeline에서 `quay.io/melona240/cnc-wearpoint-backend:$CI_COMMIT_SHA` | main에서 `ml/serving/**`가 바뀐 경우에만 `quay.io/melona240/cnc-wearpoint-serving:$CI_COMMIT_SHA` | .gitlab-ci.yml:23-33, 99-114 |
| 승격 | `v*` 태그 -> `:vX.Y.Z`, `:latest` | `serving-v*` 태그 -> SHA 이미지 pull -> `:vX.Y.Z`, `:latest`(해당 SHA 이미지가 없으면 pull 실패) | .gitlab-ci.yml:37-50, 118-137 |
| 배포 | `deploy_backend`: `/opt/cnc-wearpoint/backend`에서 `docker compose pull` / `up -d --no-build --remove-orphans` 실행 후 health 확인 | **배포 job 없음** (pull, restart, recreate 모두 수동) | .gitlab-ci.yml:54-91, 118-137 |
| 모델 alias | CI에서 관리하지 않음 | CI에서 관리하지 않음 | .gitlab-ci.yml 전체 |

- GitHub workflow는 main과 `v*`, `serving-v*` 태그를 GitLab으로 mirror합니다. `v*` 태그를 push하면 곧바로 운영 deploy_backend가 실행됩니다(.github/workflows/sync-to-gitlab.yml:4-10, 25-33).
- `deploy_backend`는 compose 프로젝트 전체에 `up --remove-orphans`를 실행합니다(.gitlab-ci.yml:64-65). **[운영 확인] Serving은 별도 project(`/opt/cnc-wearpoint/serving/compose.yaml`, name `cnc-wearpoint-serving`)이므로 영향을 받지 않습니다(0.2절).**
- 로컬 git tag: `serving-v0.1.0`, `v0.1.0`~`v0.1.12` (git tag -l)
- 저장소의 compose 파일에는 Serving 서비스가 **없습니다**. `infra/compose/compose.deploy.yaml`은 build와 로컬 mysql을 쓰는 구성이라 운영용이 아닙니다(infra/compose/compose.deploy.yaml:1-33). 운영 compose는 저장소 밖 `/opt/cnc-wearpoint/backend`에 있습니다(.gitlab-ci.yml:61; infra/compose/compose.manual-inputs.yaml:1).

### 2.8 등록 스크립트 위험

- `register_candidate.py`의 기본 tracking URI는 운영 `https://aimw.duckdns.org/mlflow/`이고(env `MLFLOW_TRACKING_URI`가 우선), 기본 model은 `cnc-wearpoint-multitask`, 기본 alias는 `candidate`입니다. 등록 직후 **무조건** `set_registered_model_alias`를 호출합니다. no-alias 옵션도, 기존 alias를 확인하는 단계도 없습니다(ml/serving/register_candidate.py:20-22, 34-40, 52-55, 162-168).
- 따라서 기본값으로 실행하면 **운영 `candidate` alias가 새 version으로 옮겨집니다.** 실제 반영은 다음 Serving 재시작 때 일어납니다.

### 2.9 보안 관련

- `ml/serving`에 `.dockerignore`가 없고 Dockerfile이 `COPY . .`(ml/serving/Dockerfile:18)를 실행합니다. 로컬에서 `docker build ml/serving`을 하면 gitignore된 `.env.inference.local`(운영 MLflow admin Basic Auth 자격증명이 평문으로 저장됨)이 이미지에 포함됩니다. CI는 clean checkout에서 빌드하므로 영향이 없습니다(.gitignore:14).
- 이 파일로 로컬 Serving을 띄우면 운영 Registry에 admin으로 접속하게 됩니다. live 확인에는 read-only 사용자를 쓰는 것을 권장합니다.

### 2.10 Stale 문서

| 문서 | 문제 | 근거 |
|---|---|---|
| docs/deployment/infrastructure.md | 삭제된 `infra/k8s/*` 경로와 Kubernetes 계획을 참조합니다. compose를 local 전용으로 설명합니다. infra/k8s는 git에 추적된 적이 없습니다(핸드오프의 "오늘 삭제"는 untracked 디렉터리였던 것으로 보이며, 현재 작업 트리에도 없음). | :21-36, 200-212, 272-274; `git log --all -- infra/k8s` 결과 없음 |
| docs/database.md | `champion` alias와 "FastAPI 재시작 또는 명시적인 Model Reload"를 계획으로 적고 있습니다. 실제로는 `candidate` alias를 쓰고 reload가 없습니다. lifecycle 근거는 삭제된 toy model입니다. | :571-622, 628-656 |
| docs/infrastructure.md | App VM 서비스 목록에 Serving 컨테이너가 빠져 있습니다. | :143-152, 196-208 |
| README.md | toy test 설명이 database.md와 맞지 않습니다(V2에 candidate를 붙였다는 서술). champion 로딩을 미래 계획으로 적고 있습니다. | README.md:388, 600, 612 |
| ml/serving/README.md | 7줄뿐이고 env, run, deploy 설명이 없습니다. | ml/serving/README.md:1-8 |

---

## 3. (b) 핸드오프 정보 (여기서는 검증하지 않음)

- Registered model `cnc-wearpoint-multitask`
  - Version 1, alias `candidate`, READY, 운영 Serving이 사용 중(2026-11-19 기준 version 1 로드됨)
  - Version 2, alias `candidate-opt`, READY, "optimized" candidate. artifact에 MLmodel, data/model.pt2, env info, requirements.txt가 있다고 함 → **[운영 확인] `model.pt2` 없음. V1과 같은 pyfunc 구조(0.3절)**
- Artifact: `s3://cnc-wearpoint-mlflow/mlflow-artifacts`, Registry 메타데이터: RDS MySQL, MLflow: App VM systemd 127.0.0.1:5000, `/mlflow/` 프록시(auth)
- 운영은 Docker VM입니다(k8s 아님. infra/k8s는 2026-11-20 삭제). Backend 운영 이미지는 `e2416e7`, `MONITORING_INFERENCE_ENABLED=1`

### 3.1 완료된 근거: 2026-11-13 toy Registry lifecycle test

multitask V1/V2와는 **별개**인 toy regression 모델 쌍으로 수행한 테스트입니다. 다시 실행하지 않습니다.

| 항목 | V1 | V2 |
|---|---|---|
| run_id | `300d0736b0e44e37aa15f801b441b2a8` | `e0ab3ace2c9b45c4b8a1a199a1639411` |
| MAE | 29.8926 | 23.4643 |
| RMSE | 38.7056 | 31.4381 |
| R2 | 0.8956 | 0.9311 |

- 결과: `champion` alias V1 -> V2 -> V1 이동과 각 단계의 load가 모두 PASS였다고 함. 이후 toy model은 삭제됨
- 저장소 안의 흔적: docs/database.md:571-622(모델명 `cnc-wearpoint-regressor-lifecycle-test`, 서술만 있음), README.md:388, 600. **run ID, metric, 로그는 디스크에 없습니다.** run이 MLflow runs 테이블에 남아 있는지는 미확인입니다(U9).
- 이 테스트는 "Registry alias 이동과 version별 load가 동작한다"는 근거입니다. **multitask Serving 경로(재시작 필요성, pyfunc/flavor 호환성, Backend 저장)를 검증한 것은 아닙니다.**

---

## 4. (c) 운영에서 read-only로 확인해야 할 미확인 사항

| ID | 항목 | 왜 중요한가 |
|---|---|---|
| U1 | V2의 MLmodel flavor와 signature(python_function 유무, 입출력 컬럼), torch 버전 **[해소 0.3]** pyfunc, signature 동일 | 승격 가능 여부를 결정합니다 |
| U2 | 현재 alias 매핑(candidate, candidate-opt -> version)과 model_versions 상태 **[해소 0.3]** candidate→1, candidate-opt→2, 둘 다 READY | 기준 상태 snapshot |
| U3 | 운영 Serving 컨테이너의 이름, 이미지 태그/digest, restart policy, compose project label, env(MODEL_NAME, MODEL_ALIAS, MLFLOW_TRACKING_URI, INFERENCE_BATCH_SIZE) **[해소 0.1/0.2]** 이름·이미지·restart·compose·env 확인 | 재시작과 롤백 절차, deploy_backend 간섭 여부 |
| U4 | 운영 Serving `/health`의 model_version **[해소 0.2]** `model_version: "1"` | 실제로 로드된 version |
| U5 | 런타임에 import된 mlflow_model.py가 artifact code/의 것인지 /app의 것인지 | INFERENCE_BATCH_SIZE가 적용되는지, 이미지 교체가 모델 코드에 영향을 주는지 |
| U6 | Backend env(SERVING_URL, PREDICTION_MODEL_NAME, MONITORING_INFERENCE_ENABLED, AUTO_PREDICTION*, PREDICTION_API_ENABLED) | 계약 |
| U7 | predictions와 monitoring_inference_runs의 version별 분포 | 감사 기준선 |
| U8 | 운영 V1 S3 객체가 testdata와 같은지(ContentLength 45870091, sha256 a6bf94e5…cb7bd) | 무결성 |
| U9 | toy run 300d0736 / e0ab3ace 와 V1 run f61d462a 가 MLflow runs 테이블에 남아 있는지 **[일부 해소]** V1 run `f61d462a…`·V2 run `98c32cdb…` 존재(지표 없음). toy run 2건은 미확인 | 완료 근거 보강 |
| U10 | Quay의 serving 이미지 태그와 VM에 캐시된 이미지(`docker images ... --digests`) | 이미지 롤백 가능 여부 |
| U11 | 배포된 DB 스키마가 저장소와 같은지(SHOW CREATE TABLE) | 감사 컬럼 확인 |
| U12 | 진행 중 작업: measurements.status='predicting', monitoring_inference_runs의 queued/running | 재시작 전 확인 |

## 5. 핵심 Gap 요약

1. ~~V2가 pyfunc와 호환되는지 알 수 없습니다.~~ **[운영 확인으로 해소]** V2는 V1과 같은 pyfunc/signature입니다(0.3절). 대신 **V1/V2 모두 평가 지표가 Registry에 없어** 승격 근거(동등성·성능)를 새로 만들어야 합니다.
2. alias가 기동 시에만 해석되고 reload나 version pin이 없습니다. 승격과 롤백에는 alias 변경과 Serving 재시작이 모두 필요하고, 그동안 서비스가 중단됩니다(service.py:13-21, 94-102; Dockerfile:22). 기동은 fail-hard입니다.
3. Serving 실행 정의(compose, env, restart policy)가 저장소에 없고(운영 `/opt/cnc-wearpoint/serving/compose.yaml`에만 존재), Serving 배포 job도 없습니다(.gitlab-ci.yml:118-137). deploy_backend는 Serving에 영향이 없음을 확인했습니다(0.2절). Serving은 로드한 version을 로그에 남기지 않고, 기동 시 공개 URL 경유로 MLflow에 의존합니다.
4. `register_candidate.py`의 기본값이 운영 URI와 운영 alias를 덮어씁니다(register_candidate.py:20-22, 36-40, 164-168).
5. alias 이력과 model_alias, run_id가 어디에도 저장되지 않습니다(sql/schema.sql:78-101; sql/mlflow/mlflow.sql:1259-1266).
6. 기존 테스트에는 ml/serving에 대한 오프라인 contract test가 없었습니다. tests/model_lifecycle/(untracked, 이번 작업에서 추가)로 보강했으며 2026-11-20 로컬 실행 결과는 50 passed, 9 skipped입니다(skip 9건은 test_registry_integration.py의 실제 Registry read-only 조회로, 기본 skip). Backend의 URLError/timeout/RemoteDisconnected 매핑과 Serving 내부 ValueError -> 400 경로는 여전히 테스트가 없습니다.

## 6. read-only 확인 명령 (사용자가 VM에서 직접 실행, 비밀번호 출력 금지)

아래 명령은 모두 조회만 합니다. `docker compose pull`/`up`/`restart`, alias 변경 API(POST/PATCH/DELETE)는 포함하지 않습니다.

```bash
# U3: Serving 컨테이너
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
docker inspect <serving> --format '{{.Config.Image}} {{.Image}} {{json .HostConfig.RestartPolicy}} {{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.project.config_files"}} {{.State.StartedAt}}'
docker inspect <serving> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(MODEL_NAME|MODEL_ALIAS|MLFLOW_TRACKING_URI|INFERENCE_BATCH_SIZE)='
cd /opt/cnc-wearpoint/backend && docker compose config --services && docker compose ps -a   # pull/up 실행 금지
ls -la /opt/cnc-wearpoint/

# U4: 로드된 version
docker exec <serving> python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8001/health',timeout=5).read().decode())"

# U6: Backend env
docker inspect <backend> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(SERVING_URL|PREDICTION_MODEL_NAME|MONITORING_INFERENCE_ENABLED|AUTO_PREDICTION|PREDICTION_API_ENABLED|BACKEND_IMAGE_TAG)'

# U2/U1: Registry (App VM localhost, 가능하면 read-only 사용자)
curl -s -u "$RO_USER:$RO_PASS" 'http://127.0.0.1:5000/api/2.0/mlflow/registered-models/alias?name=cnc-wearpoint-multitask&alias=candidate'
curl -s -u "$RO_USER:$RO_PASS" 'http://127.0.0.1:5000/api/2.0/mlflow/registered-models/alias?name=cnc-wearpoint-multitask&alias=candidate-opt'
curl -s -u "$RO_USER:$RO_PASS" 'http://127.0.0.1:5000/api/2.0/mlflow/model-versions/get?name=cnc-wearpoint-multitask&version=2'
# source에서 경로를 확인한 뒤 MLmodel만 GET (모델 전체 다운로드 아님)
curl -s -u "$RO_USER:$RO_PASS" 'http://127.0.0.1:5000/api/2.0/mlflow-artifacts/artifacts/<path>/MLmodel'

# U5: 런타임 버전과 코드 경로
docker exec <serving> python -c "import mlflow,torch;print(mlflow.__version__,torch.__version__)"
docker exec <serving> sh -c 'find / -path /proc -prune -o -name mlflow_model.py -print 2>/dev/null'

# U10
docker images quay.io/melona240/cnc-wearpoint-serving --digests
```

```sql
-- U2 (mlflow DB, read-only 사용자)
SELECT workspace, name, alias, version FROM registered_model_aliases WHERE name='cnc-wearpoint-multitask';
SELECT version, current_stage, status, source, run_id, storage_location, FROM_UNIXTIME(creation_time/1000)
  FROM model_versions WHERE name='cnc-wearpoint-multitask' ORDER BY version;
-- U9
SELECT run_uuid, status, lifecycle_stage, experiment_id FROM runs
 WHERE run_uuid IN ('300d0736b0e44e37aa15f801b441b2a8','e0ab3ace2c9b45c4b8a1a199a1639411','f61d462aabe8483290e8906117271c63');
-- U7 (cnc_wearpoint DB, read-only)
SELECT model_name, model_version, COUNT(*), MIN(predicted_at), MAX(predicted_at) FROM predictions GROUP BY 1,2;
SELECT model_name, model_version, status, error_code, COUNT(*) FROM monitoring_inference_runs GROUP BY 1,2,3,4;
-- U11
SHOW CREATE TABLE predictions; SHOW CREATE TABLE monitoring_inference_runs;
-- U12
SELECT id, status, prediction_started_at FROM measurements WHERE status='predicting';
SELECT run_id, status, started_at FROM monitoring_inference_runs WHERE status IN ('queued','running');
```
