# 모델 라이프사이클 테스트 계획

- 작성일: 2026-11-20
- 전제: [MODEL_LIFECYCLE_CURRENT_STATE.md](MODEL_LIFECYCLE_CURRENT_STATE.md)의 사실(S*, C*, A*, B*, D*)과 미확인 항목(U*)을 기준으로 합니다.
- 원칙
  1. **운영 alias(`candidate`)는 바꾸지 않습니다.** 운영 Serving은 교체하거나 재시작하지 않습니다. RDS 이력, MLflow model, artifact는 삭제하지 않습니다. force push도, 의도하지 않은 CI deploy(`v*` 태그 push)도 하지 않습니다.
  2. 순서: **오프라인 테스트 -> 운영 read-only 조회 -> 분리된 TEST 환경에서 mutation**
  3. 운영에 쓰기가 일어나는 단계(Registry에 모델이나 alias 추가 포함)는 모두 **[승인 필요]**로 표시합니다. 사용자가 명시적으로 승인한 뒤에만 실행합니다.
- 상태 값: `PASS` / `FAIL` / `HOLD`(선행 조건이 없거나 승인 대기). 실제 결과가 없으면 `미실행`으로 둡니다.

## 0. 오프라인 테스트 모음 (tests/model_lifecycle/)

다른 작업자가 병렬로 작성 중인 오프라인 테스트입니다. 네트워크, MLflow 서버, 운영 DB 없이 mock과 fake로 실행합니다.

| 파일 | 다루는 범위 |
|---|---|
| `tests/model_lifecycle/test_serving_model_selection.py` (11개) | fake Registry로 service.py를 검증합니다. env 기반 모델 선택(MODEL_NAME/MODEL_ALIAS), lifespan에서 alias를 1회만 해석하는지, `models:/NAME/VERSION` URI, /health와 응답 필드, **alias를 옮겨도 재시작 전까지 version이 그대로인지**(test_alias_move_after_load_does_not_change_served_version_until_restart), tracking URI/alias 없음 시 기동 실패, 출력 컬럼 누락 시 500. Serving 내부 ValueError -> 400 케이스는 **없습니다**. |
| `tests/model_lifecycle/test_backend_model_contract.py` (39개) | validate_model_result의 version과 name 규칙(`"2"`/int 2 허용, `"02"`/`"2.0"`/alias 문자열 거부, Unexpected model name, PREDICTION_MODEL_NAME override, 필수 필드 누락, wear 범위), persist_prediction/replay/monitoring 완료 경로에서 저장되는 model_name/model_version(alias 미저장). HTTP 오류 매핑(400/500/URLError/timeout/RemoteDisconnected)은 **다루지 않습니다**(400 매핑만 기존 tests/test_prediction_execution.py:286-330에 있음). |
| `tests/model_lifecycle/test_registry_integration.py` (9개, 기본 skip) | fake가 아니라 **실제 MLflow Registry에 대한 read-only 조회**입니다. `MODEL_LIFECYCLE_INTEGRATION=1`과 `MLFLOW_TRACKING_URI`가 있고 mlflow가 설치된 venv에서만 실행됩니다. alias 매핑(candidate=1, candidate-opt=2), READY 상태, MLmodel 존재, python_function flavor와 출력 컬럼 호환을 확인합니다. 쓰기 메서드는 proxy로 차단합니다. 운영 Registry를 조회하므로 **AP-1(승인 필요)** 이후에만 실행합니다(REG-01~03의 대안). |

2026-11-20 로컬 실행 결과: `tests/model_lifecycle` 50 passed, 9 skipped(전부 test_registry_integration.py).

실행(로컬, 오프라인):

```bash
cd C:/Users/90/PycharmProjects/cnc-wearpoint-backend
.venv/Scripts/python.exe -m pytest -q tests/model_lifecycle
```

> mlflow는 backend venv에 설치되어 있지 않습니다(확인함). test_serving_model_selection.py는 mlflow를 stub하고, test_registry_integration.py는 skip됩니다.

---

## 1. 분리된 TEST 환경 제안

| 항목 | 운영(건드리지 않음) | TEST(제안) |
|---|---|---|
| Registered model | `cnc-wearpoint-multitask` | **권장 A**: 복제 모델 `cnc-wearpoint-multitask-test` (V1과 V2를 `copy_model_version`으로 복사) / **대안 B**: 같은 모델에 test 전용 alias `test-current`, `test-previous` |
| Alias | `candidate`(V1), `candidate-opt`(V2) | A: `test-current`, `test-previous` / B: `test-current`, `test-previous` (`candidate*`, `champion`, `staging` 같은 이름은 혼동되므로 피함) |
| Serving 컨테이너 | 운영 Serving(이름 U3에서 확인) | `cnc-wearpoint-serving-test`, `-p 127.0.0.1:18001:8001`, `--restart no`, `--cpus 1 --memory 3g`(운영과 CPU 경합 방지) |
| Serving 이미지 | 운영 태그(U3) | 운영과 **같은 digest** (재현성) |
| Docker network | 운영 backend network | 운영 network에 붙이지 않음. 운영 Backend가 `cnc-wearpoint-serving` DNS로 TEST 컨테이너를 찾지 않도록 이름을 다르게 함 |
| Backend | 운영 backend + RDS | 로컬 Backend + 로컬 MySQL(`infra/compose/compose.yaml`), `SERVING_URL=http://127.0.0.1:18001`. TEST Serving이 운영 VM에 있으면 개발 PC에서 `ssh -L 18001:127.0.0.1:18001 <vm>` 터널이 필요합니다(VM 접속이므로 AP-1/AP-3 범위). 로컬 Backend/MySQL을 운영 VM 위에서 띄우지 않습니다. |
| MLflow 자격증명 | admin(.env.inference.local) | read-only 사용자 권장(로드 전용). alias 변경에는 쓰기 권한이 필요하므로 별도 승인 |

- **방식 A가 권장인 이유**: 방식 B는 운영 registered model에 alias를 추가하므로, `registered_model_aliases`에 운영 모델의 행이 생깁니다. 방식 A는 운영 모델의 메타데이터를 전혀 바꾸지 않습니다. 단, 이 경우 TEST Serving 응답의 model_name이 `cnc-wearpoint-multitask-test`가 됩니다(S7). 그래서 TEST Backend에 `PREDICTION_MODEL_NAME=cnc-wearpoint-multitask-test`를 설정해야 합니다(B3). 설정하지 않으면 `Unexpected model name`으로 거부됩니다.
- `copy_model_version`은 새 registered model version을 만들 뿐 artifact를 지우거나 덮어쓰지 않습니다. 그래도 이 단계는 **Registry 쓰기이므로 [승인 필요]**입니다. 같은 artifact source를 참조하는지, 복사본을 만드는지는 MLflow 3.18 동작으로 확인합니다(미확인).
- **절대 사용 금지**: 인자 없이 `register_candidate.py`를 실행하는 것. 운영 URI와 운영 `candidate`를 덮어씁니다(register_candidate.py:20-22, 36-40, 164-168).
- 대안(완전 오프라인): 로컬 MLflow(sqlite + file store, 임시 디렉터리)에 testdata/mlflow_candidate_v1을 등록하고 로컬 Serving을 띄웁니다. 이 경우 python_model.pkl을 unpickle하므로 **신뢰할 수 있는 별도 venv에서만** 실행하고 사용자가 결정합니다(이 문서 작성 과정에서는 실행하지 않았습니다).

### 승인 필요 단계 요약

| 단계 | 내용 | 영향 |
|---|---|---|
| AP-1 | 운영 VM/RDS/MLflow/S3에 read-only 조회 (카테고리 1~2, SCH-05, test_registry_integration.py) | 쓰기 없음. VM 접속 권한 필요 |
| AP-2 | TEST registered model 생성(`copy_model_version`) 또는 test alias 추가 (1장 표, LOAD-01 선행 조건) | MLflow Registry(RDS) 쓰기 |
| AP-3 | VM에서 TEST Serving 컨테이너 기동/재시작/삭제 (카테고리 3~8) | 운영 VM 자원 사용, MLflow artifact proxy를 통한 S3 다운로드 |
| AP-4 | TEST alias 이동 (카테고리 6, 7: PRO-01, RB-01) | Registry 쓰기(test 리소스만) |
| AP-5 | 테스트 종료 후 TEST alias와 model 정리 | 삭제가 필요하면 별도 승인. 기본은 **보존** |

---

## 2. 테스트 케이스

각 테스트의 형식: Test ID / 목적 / 선행 조건 / 실행 명령 / 기대 결과 / 실제 결과 / 상태 / 재시도·롤백 방법

### 카테고리 1. Registry 메타데이터 read

#### REG-01 운영 alias 매핑 snapshot
- 목적: 테스트 전 기준 상태(`candidate`, `candidate-opt` -> version)를 기록합니다. alias 이력 테이블이 없으므로(D5) 직접 남겨야 합니다.
- 선행 조건: AP-1, App VM 접속, read-only MLflow 사용자
- 실행 명령:
  ```bash
  for a in candidate candidate-opt; do
    curl -s -u "$RO_USER:$RO_PASS" "http://127.0.0.1:5000/api/2.0/mlflow/registered-models/alias?name=cnc-wearpoint-multitask&alias=$a"; echo
  done | tee ~/lifecycle-snapshot/aliases_$(date +%Y%m%dT%H%M%S).json
  ```
  SQL로 확인할 경우: `SELECT workspace,name,alias,version FROM registered_model_aliases WHERE name='cnc-wearpoint-multitask';`
- 기대 결과: candidate -> 1, candidate-opt -> 2 (핸드오프와 일치)
- 실제 결과: 2026-11-20 운영 read-only 조회(사용자 실행, Serving 컨테이너 안 MlflowClient GET): `aliases: {'candidate': '1', 'candidate-opt': '2'}` (CURRENT_STATE 0.3절)
- 상태: PASS
- 재시도·롤백 방법: 조회만 하므로 롤백할 것이 없습니다. 401이면 자격증명을, 404면 모델명을 확인합니다.

#### REG-02 version 메타데이터 조회
- 목적: V1과 V2의 status(READY), source, run_id, 생성 시각을 확인합니다.
- 선행 조건: AP-1
- 실행 명령: `curl -s -u ... 'http://127.0.0.1:5000/api/2.0/mlflow/model-versions/get?name=cnc-wearpoint-multitask&version=1'` (version=2도 같은 방식). SQL: `SELECT version,status,source,run_id,storage_location,FROM_UNIXTIME(creation_time/1000) FROM model_versions WHERE name='cnc-wearpoint-multitask' ORDER BY version;`
- 기대 결과: 두 version 모두 READY. V1의 run_id는 `f61d462aabe8483290e8906117271c63`, source에 `m-04bfd5b99f9f48258157026e5e204491`가 포함됨(A2)
- 실제 결과: 2026-11-20 운영 read-only 조회(사용자 실행, Serving 컨테이너 안 MlflowClient GET): V1 READY, run `f61d462a…`, source `models:/m-04bfd5b9…` / V2 READY, run `98c32cdb…`, source `models:/m-3e81fad6…`. 두 run과 logged model 모두 **metrics·params 없음**
- 상태: PASS (단, 평가 지표 부재는 별도 gap)
- 재시도·롤백 방법: 조회만 합니다.

#### REG-03 V2 MLmodel flavor와 signature 확인 (승격 blocker)
- 목적: V2에 `python_function` flavor가 있는지, 입력이 image_path/sensor_path/crop_*인지, 출력에 predicted_wear_um/predicted_type/flank_wear_probability/epoch/window_count/sampling_hz가 있는지 확인합니다(C2, A3).
- 선행 조건: REG-02에서 얻은 V2 source 경로
- 실행 명령: `curl -s -u ... 'http://127.0.0.1:5000/api/2.0/mlflow-artifacts/artifacts/<V2 path>/MLmodel'` (MLmodel 파일만 GET)
- 기대 결과: flavors에 `python_function`이 있고 signature가 V1과 호환됨. **그렇지 않으면 현재 service.py로는 V2를 서빙할 수 없다고 판정**하고 INF와 PRO 카테고리를 HOLD합니다.
- 실제 결과: 2026-11-20 운영 read-only 조회(사용자 실행, Serving 컨테이너 안 MlflowClient GET): V2 flavor `python_function`(loader `mlflow.pyfunc.model`), signature 입력 6개·출력 9개 **V1과 동일**, metadata batch_size=2/checkpoint=epoch_010.pth. `model.pt2` 없음(핸드오프 정보 정정)
- 상태: PASS (blocker 해소)
- 재시도·롤백 방법: 조회만 합니다.

#### REG-04 toy lifecycle run 보존 여부 (완료 근거 보강)
- 목적: 2026-11-13 toy 테스트(완료, 핸드오프 기준)의 run이 남아 있는지 확인합니다. **다시 실행하지 않습니다.**
- 선행 조건: AP-1
- 실행 명령: `SELECT run_uuid,status,lifecycle_stage FROM runs WHERE run_uuid IN ('300d0736b0e44e37aa15f801b441b2a8','e0ab3ace2c9b45c4b8a1a199a1639411');` 와 `SELECT run_uuid,`key`,value FROM latest_metrics WHERE run_uuid IN (...);`
- 기대 결과: metric이 핸드오프 값과 일치(MAE 29.8926/23.4643 등). run이 없으면 핸드오프 기록만 근거로 남깁니다.
- 실제 결과: 미실행 (toy V1->V2->V1 alias 이동과 load PASS는 핸드오프 기준 **완료**)
- 상태: HOLD (V1/V2 run 존재는 확인. toy run 2건은 미조회)
- 재시도·롤백 방법: 조회만 합니다.

#### REG-05 Serving 모델 선택 로직 (오프라인)
- 목적: Serving이 env alias를 1회 해석하고 `models:/NAME/VERSION`을 로드하는지, MODEL_VERSION override가 없는지 확인합니다(S1, S3).
- 선행 조건: 없음
- 실행 명령: `.venv/Scripts/python.exe -m pytest -q tests/model_lifecycle/test_serving_model_selection.py`
- 기대 결과: 모든 테스트 PASS
- 실제 결과: 2026-11-20 로컬 실행 11 passed (test_serving_model_selection.py)
- 상태: PASS
- 재시도·롤백 방법: 코드 변경이 없으므로 롤백할 것이 없습니다.

### 카테고리 2. V1/V2 artifact 존재와 무결성

#### ART-01 V1 로컬 사본 무결성 (오프라인)
- 목적: testdata 사본의 hash를 기록합니다(A4).
- 선행 조건: 없음
- 실행 명령: `sha256sum testdata/mlflow_candidate_v1/artifacts/epoch_010.pth testdata/mlflow_candidate_v1/python_model.pkl`
- 기대 결과: `a6bf94e5…cb7bd` (45870091 bytes), `e846b592…4387d`
- 실제 결과: 일치(분석 단계에서 sha256sum으로 확인)
- 상태: PASS
- 재시도·롤백 방법: 조회만 합니다.

#### ART-02 운영 V1 S3 객체와 로컬 사본 비교
- 목적: 운영 artifact가 testdata와 같은지 확인합니다(U8).
- 선행 조건: AP-1, read-only S3 키
- 실행 명령: `aws s3api head-object --bucket cnc-wearpoint-mlflow --key mlflow-artifacts/4/models/m-04bfd5b99f9f48258157026e5e204491/artifacts/artifacts/epoch_010.pth` (정확한 key는 `aws s3 ls --recursive`로 먼저 확인)
- 기대 결과: ContentLength 45870091. ETag만으로 sha256을 비교할 수 없으면(multipart upload) TEST 환경에서 다운로드한 뒤 sha256을 비교합니다.
- 실제 결과: 미실행
- 상태: HOLD (AP-1)
- 재시도·롤백 방법: 조회만 합니다.

#### ART-03 V2 artifact 목록과 크기
- 목적: V2 artifact(MLmodel, artifacts/epoch_010.pth, code/, requirements.txt 등)가 존재하고 비어 있지 않은지 확인합니다. (핸드오프의 `data/model.pt2`는 운영 조회로 없음을 확인)
- 선행 조건: REG-02
- 실행 명령: `aws s3 ls --recursive s3://cnc-wearpoint-mlflow/mlflow-artifacts/<exp>/models/<V2 model_id>/` (목록만)
- 기대 결과: 모든 파일이 존재하고 크기가 0보다 큼. 파일 구성을 REG-03의 flavor와 대조합니다.
- 실제 결과: 2026-11-20 운영 read-only 조회(사용자 실행, Serving 컨테이너 안 MlflowClient GET): V2 파일 목록 MLmodel 1853, artifacts/epoch_010.pth 45870091, code/inference.py 5537, code/mlflow_model.py 2789, code/preprocessing.py 6697, conda.yaml 311, python_env.yaml 121, python_model.pkl 200, requirements.txt 175 (모두 0보다 큼). code/ 3개 파일 크기는 저장소 `ml/serving`과 일치
- 상태: PASS
- 재시도·롤백 방법: 조회만 합니다.

#### ART-04 V2 requirements와 Serving 이미지 호환성
- 목적: V2의 requirements(175 bytes, V1은 63 bytes)가 Serving 이미지(torch 2.15.0+cpu, mlflow 3.18.0)와 맞는지 확인합니다. V2는 pyfunc이므로 `.pt2` 호환성 문제는 해당 없음(REG-03). V2는 `register_candidate.py`가 `ml/serving/requirements.txt`를 pip_requirements로 넘겨 등록한 것으로 보여 일치 가능성이 높습니다.
- 선행 조건: ART-03
- 실행 명령: V2의 requirements.txt와 python_env.yaml을 GET하고 ml/serving/requirements.txt와 비교합니다.
- 기대 결과: torch major/minor 일치. 다르면 INF 카테고리 결과를 해석할 때 위험으로 표시합니다.
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 조회만 합니다.

#### ART-05 V1/V2 checkpoint 동일성과 코드 차이 (오프라인 + read-only)
- 목적: V2가 "같은 가중치 + 최적화된 추론 코드"인지 확정합니다.
- 선행 조건: ART-03. 로컬 `testdata/mlflow_candidate_v1`(=V1), 저장소 `ml/serving`(=V2 code)
- 실행 명령: 로컬 `diff --strip-trailing-cr testdata/mlflow_candidate_v1/code/<f> ml/serving/<f>`; checkpoint 해시는 TEST 환경(또는 운영 Serving 컨테이너의 임시 폴더)에서 V2 `artifacts/epoch_010.pth`만 내려받아 `sha256sum` 후 삭제
- 기대 결과: preprocessing 내용 동일, inference는 이미지 특징 재사용 최적화만, mlflow_model은 INFERENCE_BATCH_SIZE 지원만. V2 checkpoint sha256 = `a6bf94e5…cb7bd`
- 실제 결과: 코드 diff는 2026-11-20 로컬 확인(기대와 일치). checkpoint는 크기만 일치(45870091), 해시 미확인
- 상태: HOLD (해시)
- 재시도·롤백 방법: 조회만 합니다. 내려받은 임시 파일은 삭제합니다.

#### INF-00 V1/V2 동일 입력 동등성·지연 시간 (로컬 오프라인, 운영 무관)
- 목적: 같은 이미지+CSV에 대해 V1 코드와 V2 코드(같은 checkpoint)의 출력이 수치 오차 안에서 같은지, V2가 실제로 빠른지 확인합니다. Registry 지표가 없으므로 이것이 승격 근거가 됩니다.
- 선행 조건: 로컬에 별도 가상환경(torch 2.15.0+cpu, torchvision 0.29.2+cpu, mlflow 3.18.0 등 `ml/serving/requirements.txt`). 운영 접속 불필요
- 실행 명령: 두 코드 디렉터리를 각각 import 경로로 두고 `inference.load_model` + `predict_record`를 `testdata` 입력으로 N회 실행해 결과와 시간을 비교(스크립트는 추가 예정)
- 기대 결과: predicted_wear_um 차이 < 1e-4 µm, flank_wear_probability 차이 < 1e-6, predicted_type·window_count·cut index 동일. V2 평균 지연 시간 < V1
- 실제 결과: 2026-11-20 로컬 실행(별도 venv, torch 2.15.0+cpu/torchvision 0.29.2+cpu, threads=4, batch_size=2, 입력 `testdata/01046_set16.png` + `Test_0015_1_00_286…csv`, 같은 checkpoint). **9개 출력 필드 모두 완전히 동일**(predicted_wear_um 173.6270366098689, flank_wear_probability 1.2488e-06, other_wear, window_count 174, cut 16518~105786 등, 차이 0). 지연 시간 V1 평균 2.28초 → V2 평균 0.23초(5회, **약 9.8배**). 입력 1쌍 기준이며 연산 순서만 바뀐 동일 연산이므로 결과 동일성은 코드 구조로도 뒷받침됨
- 상태: PASS
- 재시도·롤백 방법: 로컬 전용이므로 롤백할 것이 없습니다.

### 카테고리 3. version별 load

#### LOAD-01 TEST Serving에서 V1 load
- 목적: 운영과 같은 이미지에서 V1이 TEST alias로 로드되는지 확인합니다.
- 선행 조건: AP-2(`cnc-wearpoint-multitask-test`, `test-current` -> V1 복사본), AP-3
- 실행 명령: **[승인 필요: AP-3, 운영 VM에서 TEST 컨테이너 기동]**
  ```bash
  docker run -d --name cnc-wearpoint-serving-test --restart no --cpus 1 --memory 3g \
    -p 127.0.0.1:18001:8001 --env-file /opt/cnc-wearpoint/serving-test/.env.test \
    <운영과 같은 serving 이미지 digest>
  # .env.test: MLFLOW_TRACKING_URI, MLFLOW_TRACKING_USERNAME/PASSWORD(read-only),
  #            (V1 artifact는 mlflow-artifacts: proxy 경유이므로 AWS_* 는 보통 불필요. 운영 Serving env와 동일하게 구성, U3)
  #            MODEL_NAME=cnc-wearpoint-multitask-test, MODEL_ALIAS=test-current
  docker logs -f cnc-wearpoint-serving-test   # 기동 완료까지
  curl -s http://127.0.0.1:18001/health
  ```
- 기대 결과: `model_loaded: true`, `model_version`이 TEST 모델의 V1 복사본 version
- 실제 결과: 미실행
- 상태: HOLD (AP-2, AP-3)
- 재시도·롤백 방법: `docker rm -f cnc-wearpoint-serving-test`. 운영에는 영향이 없습니다.

#### LOAD-02 TEST Serving에서 V2 load
- 목적: V2가 `mlflow.pyfunc.load_model`로 로드되는지 확인합니다(S4).
- 선행 조건: REG-03, `test-current` -> V2 복사본(AP-4) 또는 별도 컨테이너 `MODEL_ALIAS=test-v2`
- 실행 명령: **[승인 필요: AP-3]** LOAD-01과 같으며 alias만 다릅니다.
- 기대 결과: python_function flavor가 있으면 로드에 성공합니다. 없으면 **기동 실패(컨테이너 exit)가 예상 결과**이고, 이것으로 V2 승격 불가를 판정합니다.
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 컨테이너를 삭제합니다. 운영에는 영향이 없습니다.

#### LOAD-03 런타임 import 경로 확인
- 목적: artifact code/와 /app 중 어느 mlflow_model.py가 쓰이는지 확인합니다(A6, A8, U5).
- 선행 조건: LOAD-01
- 실행 명령: 실행 중인 프로세스의 sys.modules는 밖에서 볼 수 없습니다. 그래서 **TEST 컨테이너 안에서** 별도 프로세스로 같은 URI를 한 번 더 로드해 확인합니다(메모리를 일시적으로 2배 사용).
  `docker exec cnc-wearpoint-serving-test python -c "import mlflow,sys,os;mlflow.set_tracking_uri(os.environ['MLFLOW_TRACKING_URI']);mlflow.pyfunc.load_model('models:/cnc-wearpoint-multitask-test/<ver>');print(sys.modules['mlflow_model'].__file__)"`
  **[승인 필요: AP-3, TEST 컨테이너만]** 운영 컨테이너에서는 실행하지 않습니다. 보조로 `find / -path /proc -prune -o -name mlflow_model.py -print`를 실행합니다.
- 기대 결과: 경로를 기록합니다. artifact code/이면 INFERENCE_BATCH_SIZE가 무효라는 점을 문서에 반영합니다.
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 조회만 합니다.

#### LOAD-04 로드 실패 시 동작 (오프라인)
- 목적: alias 없음, MLflow 접속 불가, tracking URI 없음일 때 기동이 실패하는지 확인합니다(S2, S5).
- 선행 조건: 없음
- 실행 명령: `.venv/Scripts/python.exe -m pytest -q tests/model_lifecycle/test_serving_model_selection.py`
- 기대 결과: lifespan에서 예외가 전파되어 Serving이 degraded 상태로 뜨지 않음
- 실제 결과: 2026-11-20 로컬 실행 PASS (test_missing_tracking_uri_fails_startup, test_missing_alias_fails_startup_hard_without_fallback). MLflow 접속 불가 자체는 별도 케이스가 없음(같은 lifespan 예외 경로)
- 상태: PASS
- 재시도·롤백 방법: 없음

### 카테고리 4. 같은 입력으로 V1/V2 추론

#### INF-01 고정 입력 세트 준비
- 목적: 비교에 쓸 입력(이미지 + sensor CSV)을 고정합니다. 600x400 crop 이미지와 원본 해상도 이미지를 모두 포함합니다(C1).
- 선행 조건: 없음(로컬 데이터)
- 실행 명령: 입력 N세트의 sha256 목록을 `lifecycle-inputs.sha256`으로 저장합니다.
- 기대 결과: hash 목록을 기록
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 없음

#### INF-02 V1 vs V2 동일 입력 추론
- 목적: 같은 입력에 대한 출력 차이를 측정합니다.
- 선행 조건: LOAD-01, LOAD-02 성공(V1용과 V2용 TEST 컨테이너를 각각 18001, 18002 포트로 띄우거나 순서대로 실행)
- 실행 명령:
  ```bash
  curl -s -F image=@in1.jpg -F sensor_csv=@in1.csv http://127.0.0.1:18001/predictions > v1_in1.json
  curl -s -F image=@in1.jpg -F sensor_csv=@in1.csv http://127.0.0.1:18002/predictions > v2_in1.json
  ```
- 기대 결과: 두 응답 모두 HTTP 200. predicted_type 일치율과 |Δpredicted_wear_um|, |Δflank_wear_probability|를 기록합니다. 허용 기준(예: |Δwear| ≤ 1 µm, type 100% 일치)은 **사용자가 정해야 합니다(미정)**. 150/200 경계를 넘는 status 변화는 따로 보고합니다.
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: TEST 컨테이너만 사용하므로 롤백할 것이 없습니다.

#### INF-03 추론 지연과 자원 사용
- 목적: "optimized" V2의 성능 이점을 측정합니다. event loop blocking 때문에 직렬로 처리됩니다(C4).
- 선행 조건: INF-02
- 실행 명령: 입력별로 `curl -w '%{time_total}\n'`을 10회 반복하고 `docker stats --no-stream`을 기록합니다.
- 기대 결과: p50/p95를 기록. 180초 Backend timeout(B1)보다 충분히 작아야 합니다.
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 없음

### 카테고리 5. 응답 schema와 model_version

#### SCH-01 Backend 검증 규칙 (오프라인)
- 목적: `"2"`/int 2 허용, `"02"`/`"2.0"`/`"candidate-opt"` 거부, 다른 model_name 거부, PREDICTION_MODEL_NAME override를 확인합니다(B3, B4).
- 선행 조건: 없음
- 실행 명령: `.venv/Scripts/python.exe -m pytest -q tests/model_lifecycle/test_backend_model_contract.py`
- 기대 결과: PASS
- 실제 결과: 2026-11-20 로컬 실행 39 passed (test_backend_model_contract.py)
- 상태: PASS
- 재시도·롤백 방법: 없음

#### SCH-02 저장 경로의 model_version (오프라인)
- 목적: persist_prediction, replay, monitoring _finish가 Serving의 model_version을 그대로 저장하는지 확인합니다(D3).
- 선행 조건: 없음
- 실행 명령: `.venv/Scripts/python.exe -m pytest -q tests/model_lifecycle/test_backend_model_contract.py tests/test_prediction_execution.py tests/test_manual_replay_prediction.py tests/test_monitoring_inference_queue.py`
- 기대 결과: PASS (기존 6개 파일 67개 테스트는 분석 단계에서 PASS)
- 실제 결과: 위 명령 2026-11-20 로컬 실행 80 passed. version `"2"` 저장 경로는 test_backend_model_contract.py(persist/replay/monitoring)에서 확인
- 상태: PASS
- 재시도·롤백 방법: 없음

#### SCH-03 TEST Serving 실제 응답 schema
- 목적: 실제 응답에 Backend 필수 필드(predicted_wear_um, predicted_type, model_name, model_version)가 있는지, model_version이 양의 정수 문자열인지 확인합니다.
- 선행 조건: INF-02
- 실행 명령: `python -I -c "import json,sys;d=json.load(open(sys.argv[1]));print({k:d.get(k) for k in ['model_name','model_alias','model_version','predicted_wear_um','predicted_type','status']})" v2_in1.json`
- 기대 결과: model_version이 `[1-9][0-9]*`. model_name은 TEST Serving의 MODEL_NAME과 같음
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 없음

#### SCH-04 TEST Backend에서 TEST Serving 저장 E2E
- 목적: 로컬 Backend(로컬 MySQL)가 TEST Serving 응답을 저장하고 predictions.model_version에 남기는지 확인합니다.
- 선행 조건: SCH-03, 로컬 MySQL, `SERVING_URL=http://127.0.0.1:18001`, `PREDICTION_MODEL_NAME=cnc-wearpoint-multitask-test`(방식 A)
- 실행 명령: 로컬 Backend에서 수동 prediction을 1건 실행한 뒤 `SELECT model_name, model_version FROM predictions ORDER BY id DESC LIMIT 1;`
- 기대 결과: TEST 모델명과 해당 version이 저장됨
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 로컬 DB이므로 운영에는 영향이 없습니다.

#### SCH-05 운영 /health와 저장 이력 read-only 확인
- 목적: 운영 Serving이 version 1을 로드하고 있는지, 저장 이력이 그와 일치하는지 확인합니다(U4, U7).
- 선행 조건: AP-1
- 실행 명령: 현재 상태 문서 6절의 `/health`, `SELECT model_name, model_version, COUNT(*) ... GROUP BY` 명령 (`rf-csv-demo` 행은 제외)
- 기대 결과: model_version `"1"`, model_alias `candidate`, model_loaded true. predictions의 multitask 행은 version 1만 있음
- 실제 결과: 미실행
- 상태: HOLD (AP-1)
- 재시도·롤백 방법: 조회만 합니다.

### 카테고리 6. TEST 환경 승격 시뮬레이션

#### PRO-01 alias 이동만으로는 반영되지 않음을 확인
- 목적: alias를 옮겨도 실행 중인 Serving의 version이 그대로임을 실제로 확인합니다(S3).
- 선행 조건: LOAD-01(TEST Serving이 V1 로드), AP-4
- 실행 명령:
  ```python
  # [승인 필요: AP-4, TEST 리소스 쓰기] 운영 모델/alias에 대한 호출 금지
  from mlflow import MlflowClient
  c = MlflowClient()
  c.set_registered_model_alias("cnc-wearpoint-multitask-test", "test-previous", "<V1 test ver>")
  c.set_registered_model_alias("cnc-wearpoint-multitask-test", "test-current", "<V2 test ver>")
  ```
  그 다음 `curl -s http://127.0.0.1:18001/health`
- 기대 결과: /health의 model_version은 **여전히 V1**. model_alias는 `test-current`로 표시됨(오해하기 쉬운 상태)
- 실제 결과: 미실행 (오프라인 동등 검증: test_serving_model_selection.py::test_alias_move_after_load_does_not_change_served_version_until_restart, PASS)
- 상태: HOLD
- 재시도·롤백 방법: `test-current`를 V1로 되돌립니다.

#### PRO-02 재시작 후 반영
- 목적: 재시작하면 새 version이 로드되는지, 다운타임이 얼마인지 측정합니다.
- 선행 조건: PRO-01
- 실행 명령: **[승인 필요: AP-3]** `docker restart cnc-wearpoint-serving-test` 를 실행하고, 1초 간격으로 `/health`를 polling해 첫 200 응답까지 걸린 시간을 기록합니다.
- 기대 결과: model_version이 V2 test version. 다운타임(로드 시간)을 기록
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 로드에 실패하면 RB-01을 수행합니다.

#### PRO-03 승격 후 저장 검증
- 목적: 승격 후 TEST Backend가 새 version을 저장하는지 확인합니다.
- 선행 조건: PRO-02, SCH-04 환경
- 실행 명령: 로컬 Backend에서 prediction 1건 실행 후 predictions의 최신 행을 조회합니다.
- 기대 결과: model_version이 V2 test version
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 로컬 DB이므로 운영에는 영향이 없습니다.

#### PRO-04 승격 시뮬레이션 (오프라인)
- 목적: fake Registry로 alias 이동, 재시작 전후 version, test alias 사용 시 `candidate` 불변을 검증합니다.
- 선행 조건: 없음
- 실행 명령: `.venv/Scripts/python.exe -m pytest -q tests/model_lifecycle/test_serving_model_selection.py` (test_registry_integration.py는 fake가 아니라 실제 Registry 조회이므로 여기 해당하지 않음)
- 기대 결과: PASS
- 실제 결과: 2026-11-20 로컬 실행 11 passed (test_alias_move_after_load..., test_test_alias_env_selects_other_version_without_touching_candidate 포함). 롤백(V2 -> V1) 시나리오 자체의 별도 테스트는 없음
- 상태: PASS
- 재시도·롤백 방법: 없음

### 카테고리 7. TEST 환경 롤백 시뮬레이션

#### RB-01 alias 롤백과 재시작
- 목적: V2에서 V1로 돌아가는 절차와 소요 시간을 검증합니다.
- 선행 조건: PRO-02
- 실행 명령: **[승인 필요: AP-4 + AP-3]** `c.set_registered_model_alias("cnc-wearpoint-multitask-test","test-current","<V1 test ver>")` 실행 후 `docker restart cnc-wearpoint-serving-test`, 그리고 /health 확인
- 기대 결과: model_version이 V1 test version. 롤백 소요 시간을 기록
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 실패하면 컨테이너를 삭제하고 V1 alias로 새로 기동합니다.

#### RB-02 로드 불가 version으로 승격했을 때의 롤백
- 목적: V2가 로드되지 않을 때(컨테이너 exit) 복구 경로를 검증합니다.
- 선행 조건: LOAD-02가 실패한 경우, 또는 고의로 존재하지 않는 alias를 사용
- 실행 명령: **[승인 필요: AP-3]** `MODEL_ALIAS=test-missing`으로 기동해 exit를 확인한 뒤 `test-current`(V1)로 다시 기동하고 /health 확인
- 기대 결과: 첫 기동은 exit(non-zero), 재기동 후 V1으로 정상. `--restart no`이므로 crash loop는 없음
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 컨테이너를 삭제합니다.

#### RB-03 이미지 롤백
- 목적: Serving 이미지 태그를 이전 SHA나 vX.Y.Z로 되돌리는 절차를 검증합니다(U10).
- 선행 조건: VM에 이전 이미지가 캐시되어 있어야 함
- 실행 명령: **[승인 필요: AP-3]** 이전 이미지 digest로 TEST 컨테이너를 다시 띄웁니다. VM에 이미지가 없으면 pull이 필요하며 이것도 승인 대상입니다.
- 기대 결과: 같은 alias/version을 이전 이미지로 로드할 수 있음
- 실제 결과: 미실행
- 상태: HOLD
- 재시도·롤백 방법: 컨테이너를 삭제합니다.

### 카테고리 8. 장애 시나리오와 복구

FAIL-01~04는 운영 VM의 TEST 컨테이너를 기동/재시작하므로 모두 **[승인 필요: AP-3]**입니다. FAIL-05, 06, 08은 오프라인, FAIL-07은 로컬 DB입니다.

| Test ID | 목적 | 선행 조건 | 실행 명령 | 기대 결과 | 실제 결과 | 상태 | 재시도·롤백 방법 |
|---|---|---|---|---|---|---|---|
| FAIL-01 | 모델 로드 실패(alias 없음, auth 실패) | TEST 컨테이너 | 잘못된 alias 또는 잘못된 비밀번호로 `docker run` | 컨테이너 exit, 로그에 원인 기록(S5) | 미실행 (오프라인: test_serving_model_selection.py) | HOLD | 올바른 env로 다시 기동 |
| FAIL-02 | Object Storage 장애 | TEST 컨테이너 | V1 artifact는 `mlflow-artifacts:` proxy 경유(현재 상태 A9)이므로 Serving env의 AWS 키를 바꿔도 S3 장애가 재현되지 않습니다. MLflow 서버 쪽 S3 설정은 운영이므로 건드리지 않습니다. 대신 Registry 메타데이터 조회는 성공하고 artifact 다운로드만 실패하는 상황을 오프라인 fake로 재현하거나, U3에서 운영 Serving이 S3 직접 접근(AWS_* env)을 쓰는 것으로 확인된 경우에만 TEST 컨테이너의 AWS 키를 무효로 둡니다 | artifact 다운로드 실패로 exit. **실행 중인** Serving은 메모리에 로드한 모델로 계속 동작(로드는 기동 시 1회) | 미실행 | HOLD | env를 복구하고 다시 기동. 운영은 S3 장애 중 **재시작 금지** |
| FAIL-03 | MLflow 서버 장애 | TEST 컨테이너 | MLFLOW_TRACKING_URI를 닫힌 포트로 두고 기동 | 기동 시 exit. 실행 중인 Serving은 영향 없음 | 미실행 | HOLD | 위와 같음 |
| FAIL-04 | 추론 중 Serving 재시작(in-flight) | SCH-04 환경 | 로컬 Backend 요청 처리 중 `docker restart cnc-wearpoint-serving-test` | 수동 요청은 502 + measurement failed. auto/retry는 INFERENCE_FAILED + retry cookie. 모니터링은 INFERENCE_FAILED로 기록되고 재큐잉 없음(B5, B6) | 미실행 (오프라인 커버 없음: URLError/timeout 매핑 테스트는 아직 없음) | HOLD | retry cookie로 재시도. 수동은 다시 요청 |
| FAIL-05 | 출력 schema 불일치 | 오프라인 | fake model이 컬럼 누락이나 ValueError를 내도록 설정 | 누락이면 500 -> Backend 502(retryable). ValueError면 400 -> INPUT_REJECTED(재시도 불가, 잘못된 분류)(C2, C3) | 부분 PASS: 컬럼 누락 -> 500은 test_serving_model_selection.py::test_model_without_expected_output_columns_is_500_not_400, Backend 400 -> INPUT_REJECTED는 tests/test_prediction_execution.py:286-330. Serving 내부 ValueError -> 400 테스트는 없음 | HOLD | 해당 version을 승격하지 않음 |
| FAIL-06 | 모델명 불일치 | 오프라인 | Serving MODEL_NAME과 Backend PREDICTION_MODEL_NAME을 다르게 설정 | `Unexpected model name`으로 measurement failed, 결과 폐기 | 2026-11-20 로컬 PASS (test_unexpected_model_name_is_rejected, test_persist_prediction_rejects_wrong_model_before_db_access) | PASS | env를 정정 |
| FAIL-07 | Backend 중단 후 `predicting` 잔류 | 로컬 DB | 추론 중 로컬 Backend를 kill | measurement가 predicting으로 남음. 30분 후 scripts/recover_stale_prediction.py로 복구. 모니터링 run은 WORKER_INTERRUPTED(B7) | 기존 테스트 커버(tests/test_monitoring_inference_recovery.py, test_prediction_execution.py recovery) | HOLD | 복구 스크립트 실행 |
| FAIL-08 | 응답 수신 중 연결 끊김(RemoteDisconnected/IncompleteRead) | 오프라인 | urlopen mock이 RemoteDisconnected를 발생시키도록 설정 | generic except에서 502/INFERENCE_FAILED로 처리되고 저장 없음(B5) | 미실행 (해당 테스트 없음, 추가 필요) | HOLD | 재시도 |

---

## 3. 종료 조건과 판정

- V2 승격 검토 가능 조건: REG-03, LOAD-02, INF-02, SCH-03, PRO-02, RB-01이 모두 PASS이고, INF-02 허용 기준을 사용자가 승인한 경우
- 하나라도 FAIL이면 승격하지 않고, 운영 상태를 그대로 둡니다(아무것도 바뀌지 않았으므로 롤백 불필요).
- 테스트 리소스(`cnc-wearpoint-multitask-test`, test alias, TEST 컨테이너)는 기본적으로 **보존**합니다. 컨테이너는 삭제해도 되지만, Registry 리소스를 삭제하려면 별도 승인(AP-5)이 필요합니다.
- 결과 기록 위치: 이 문서의 "실제 결과"와 "상태" 칸, 그리고 snapshot 파일(`~/lifecycle-snapshot/` on VM)
