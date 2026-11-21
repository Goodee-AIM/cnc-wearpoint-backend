# 모델 승격·롤백 Runbook (Docker VM)

- 작성일: 2026-11-20
- 대상: 운영 Docker VM의 Serving 컨테이너(Kubernetes 아님). Registered model `cnc-wearpoint-multitask`
- 근거: [MODEL_LIFECYCLE_CURRENT_STATE.md](MODEL_LIFECYCLE_CURRENT_STATE.md), 테스트: [MODEL_LIFECYCLE_TEST_PLAN.md](MODEL_LIFECYCLE_TEST_PLAN.md)
- 표기
  - **[운영 변경 / 승인 필요]**: 운영 상태(Registry, 컨테이너, 서비스)를 바꾸는 명령입니다. 사용자가 명시적으로 승인한 뒤에만 실행합니다.
  - **[조회]**: read-only 명령입니다.
- 이 runbook에서 **하지 않는 것**: RDS 행 삭제(predictions, monitoring_inference_runs, registered_model_aliases 이력 포함), MLflow model/version/artifact 삭제, force push, `v*`/`serving-v*` 태그 push(CI 배포와 승격을 일으킴), `register_candidate.py` 기본값 실행

---

## 현행 절차 (2026-11-21~): `production` alias + `model_lifecycle.py`

운영 Serving은 `MODEL_ALIAS=production`을 사용합니다. 아래 3·5장의 방식 A/B는 이 체계를 도입하기 전의 수동 절차입니다. 지금은 다음 순서를 따릅니다. 2026-11-21에 실제로 실행해 검증했습니다([검증 보고서 0.3절](MODEL_LIFECYCLE_VERIFICATION_REPORT.md)).

1. **평가 [Registry 태그 쓰기]** — 로컬 torch 환경(`.venv-eval`)에서, 고정 manifest와 같은 `--type-map`을 사용합니다.
   `python ml/lifecycle/model_lifecycle.py evaluate --version N --manifest ml/lifecycle/eval/test_sets_manifest.csv --type-map "adhesion=other_wear,flank_wear+adhesion=other_wear"`
2. **비교 [조회]** — `compare --version <현재> --other N`, `status`
3. **승격 [운영 변경 / 승인 필요]** — `promote --version N --alias production --dry-run`으로 확인한 뒤 실제로 실행합니다. 평가가 없거나, 같은 데이터셋 기준으로 MAE가 더 나쁘면 거부됩니다(`--force`로만 무시 가능).
4. **반영 [운영 변경 / 승인 필요]** — VM에서 `sudo docker compose -f /opt/cnc-wearpoint/serving/compose.yaml up -d --force-recreate`를 실행합니다. Serving은 기동할 때만 alias를 읽고, 재시작하는 동안 추론이 수십 초 끊깁니다.
5. **검증 [조회]** — `curl -s http://127.0.0.1:8001/health`에서 `model_alias: production`, `model_version`, `model_run_id`가 Registry와 같은지 확인하고, 로그의 `Loaded model …` 줄도 봅니다.
6. **롤백 [운영 변경 / 승인 필요]** — `rollback --alias production`을 실행한 뒤 4~5단계를 반복합니다. 직전 버전은 Registry 태그 `lifecycle.production.previous_version`에 남아 있고, 롤백할 때마다 현재 버전과 서로 맞바뀝니다.

- 모든 명령에는 `MLFLOW_TRACKING_URI`(또는 `--tracking-uri`)를 직접 지정해야 합니다. 운영 기본값은 없습니다.
- MLflow·nginx 장애 중에는 재시작하지 않습니다(Serving은 기동할 때 MLflow 접속에 실패하면 시작되지 않음).

---

## 0. 반드시 알아야 할 동작 (코드 근거)

1. **alias는 Serving 기동 시 한 번만 해석됩니다.** 실행 중에는 alias를 옮겨도 반영되지 않고, 컨테이너를 재시작해야 반영됩니다(ml/serving/service.py:94-102). reload API는 없습니다(service.py:116-130).
2. 반대로, alias를 옮긴 상태에서 **어떤 이유로든 재시작이 일어나면** 새 version이 로드됩니다(VM reboot, restart policy, compose up).
3. 모델은 env `MODEL_NAME`과 `MODEL_ALIAS`로만 선택합니다. version을 직접 지정하는 env는 없습니다(service.py:13-21).
4. 기동은 fail-hard입니다. MLflow, S3(V1 기준 MLflow artifact proxy 경유, 현재 상태 문서 A9), auth 장애나 alias가 없으면 프로세스가 종료됩니다(service.py:88-102). fallback version은 없습니다.
5. `/health`의 `model_alias`는 env 문자열이고, `model_version`은 기동 시 해석한 값입니다(service.py:121-127). **판정 기준은 `model_version`입니다.**
6. Backend는 양의 정수 version이면 모두 허용하고 model_name이 `PREDICTION_MODEL_NAME`과 같아야 합니다. 저장하는 것은 model_name과 model_version뿐입니다(app/services/prediction_execution.py:219-227, 258-264).
7. Serving은 단일 uvicorn 프로세스입니다(ml/serving/Dockerfile:22). 재시작하는 동안은 서비스가 완전히 중단됩니다.
8. CI에는 Serving 배포 job이 없습니다(.gitlab-ci.yml:118-137). 반면 Backend `v*` 태그가 붙으면 `/opt/cnc-wearpoint/backend`에서 `docker compose up -d --remove-orphans`가 실행됩니다(.gitlab-ci.yml:64-65). **[2026-11-20 운영 확인]** Serving은 별도 compose project(`/opt/cnc-wearpoint/serving/compose.yaml`, name `cnc-wearpoint-serving`)이므로 Backend 배포의 영향을 받지 않습니다.

## 1. 미확인 항목 (승격 전에 반드시 채울 것)

> **2026-11-20 운영 확인 값 (read-only 조회, CURRENT_STATE 0.2절)**
> - 관리 방식: compose, project `cnc-wearpoint-serving`, file `/opt/cnc-wearpoint/serving/compose.yaml`, service 이름 `serving`, container `cnc-wearpoint-serving`
> - 이미지: `quay.io/melona240/cnc-wearpoint-serving:f38806e72295aa73a72ad1daea83ff4335426072` (SHA 고정)
> - env 파일: `/etc/cnc-wearpoint/inference.env` (`MODEL_NAME`, `MODEL_ALIAS=candidate`, `MLFLOW_TRACKING_URI=https://aimw.duckdns.org/mlflow/`, MLflow 자격증명). compose `environment`: `OMP_NUM_THREADS=4`, `MKL_NUM_THREADS=4`, `INFERENCE_BATCH_SIZE=2`
> - restart=unless-stopped, `mem_limit: 3g`, `127.0.0.1:8001:8001`, network `compose_default`(external)
> - 현재 로드: version 1 (`/health`)
>
> - **env 파일은 root 전용(읽기 권한 없음)이므로 `docker compose`는 반드시 `sudo`로 실행합니다.** 일반 사용자로 실행하면 `open /etc/cnc-wearpoint/inference.env: permission denied`로 실패하고 컨테이너는 바뀌지 않습니다(2026-11-20 실제 발생).
> - env 변경은 `docker restart`로 반영되지 않습니다(환경변수는 컨테이너 생성 시 고정). `--force-recreate`로 재생성합니다.
> - **2026-11-20 방식 A로 V2 전환 수행:** `MODEL_ALIAS=candidate` → `candidate-opt`, 재생성 후 `/health` = `{"model_alias":"candidate-opt","model_version":"2","model_loaded":true}`. 백업: `/etc/cnc-wearpoint/inference.env.bak-<TS>`, `compose.yaml.bak-<TS>`. Registry Alias는 변경하지 않음(`candidate`→1 유지).
>
> 아래 표와 절차의 `<serving compose dir>`는 `/opt/cnc-wearpoint/serving`, `<serving service>`는 `serving`, `<env 파일>`은 `/etc/cnc-wearpoint/inference.env`입니다.

| 항목 | 값(확인 후 기입) | 확인 방법 |
|---|---|---|
| Serving 컨테이너 이름 | `<serving>` (Backend 기본 SERVING_URL로 보면 `cnc-wearpoint-serving`로 추정) | `docker ps` |
| 관리 방식 | compose(project=?, file=?) / `docker run` | `docker inspect` label `com.docker.compose.project`, `com.docker.compose.project.config_files` |
| 이미지 태그와 digest | | `docker inspect --format '{{.Config.Image}} {{.Image}}'` |
| restart policy | | `{{json .HostConfig.RestartPolicy}}` |
| env 파일 위치 | | compose 파일 또는 `docker inspect` |
| V2 flavor 호환성 | TEST-PLAN REG-03 / LOAD-02 결과 | |

**위 표가 채워지지 않으면 운영 승격을 진행하지 않습니다.** 특히 V2가 python_function과 V1 signature 호환을 만족하지 못하면(현재 미확인) 승격할 수 없습니다.

---

## 2. 사전 점검 (모두 [조회])

```bash
# P-1 TEST-PLAN 통과 여부: REG-03, LOAD-02, INF-02, SCH-03, PRO-02, RB-01 = PASS

# P-2 현재 로드된 version (승격 전 기준값)
docker exec <serving> python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8001/health',timeout=5).read().decode())"

# P-3 Registry snapshot (alias 이력 테이블이 없으므로 직접 보관)
mkdir -p ~/lifecycle-snapshot && TS=$(date +%Y%m%dT%H%M%S)
for a in candidate candidate-opt; do
  curl -s -u "$RO_USER:$RO_PASS" "http://127.0.0.1:5000/api/2.0/mlflow/registered-models/alias?name=cnc-wearpoint-multitask&alias=$a"; echo
done > ~/lifecycle-snapshot/aliases_$TS.json

# P-4 컨테이너 설정 백업 (비밀번호 포함 가능: 권한 600으로 보관, 공유 금지)
docker inspect <serving> > ~/lifecycle-snapshot/serving_inspect_$TS.json && chmod 600 ~/lifecycle-snapshot/serving_inspect_$TS.json
# compose로 관리하는 경우 compose 파일과 env 파일 사본
sudo cp -p /opt/cnc-wearpoint/serving/compose.yaml /etc/cnc-wearpoint/inference.env ~/lifecycle-snapshot/   # env 파일은 비밀값 포함: 권한 600 유지, 외부 공유 금지

# P-5 롤백용 이미지가 로컬에 있는지
docker images quay.io/melona240/cnc-wearpoint-serving --digests

# P-6 진행 중 작업 (cnc_wearpoint DB, read-only)
#   SELECT id,status,prediction_started_at FROM measurements WHERE status='predicting';
#   SELECT run_id,status,started_at FROM monitoring_inference_runs WHERE status IN ('queued','running');

# P-7 version별 저장 기준선
#   SELECT model_name, model_version, COUNT(*), MAX(predicted_at) FROM predictions
#    WHERE model_name <> 'rf-csv-demo' GROUP BY 1,2;

# P-8 MLflow, S3 정상 여부 (재시작 시 기동에 필요)
curl -s -o /dev/null -w '%{http_code}\n' -u "$RO_USER:$RO_PASS" 'http://127.0.0.1:5000/api/2.0/mlflow/registered-models/get?name=cnc-wearpoint-multitask'

# P-9 같은 시간대에 Backend 배포(v* 태그)가 예정되어 있지 않은지 확인 (GitLab pipeline 화면)
```

진행 조건: P-2의 model_version이 기대값(현재 1)과 같을 것, P-6에 진행 중 작업이 없거나 실패해도 되는 시간대일 것, P-8이 200일 것.

---

## 3. 승격 절차

> 현재 사용자 제약: **운영 alias 변경 금지, 운영 Serving 교체/재시작 금지.** 아래 3장과 5장의 모든 [운영 변경 / 승인 필요] 단계는 이 제약이 사용자에 의해 명시적으로 해제되고 단계별로 승인된 경우에만 실행합니다. 특히 방식 B는 운영 alias `candidate`를 바꾸므로 현재 제약과 정면으로 충돌합니다.

두 가지 방식이 있습니다. **첫 승격에는 방식 A를 권장합니다.** 이유는 운영 alias `candidate`를 V1에 그대로 두기 때문입니다. 그래서 롤백할 때 Registry에 쓸 필요가 없고, 예기치 않은 재시작이 일어나도 이전 설정의 컨테이너는 V1을 로드합니다.

### 방식 A: Serving env의 MODEL_ALIAS를 승격 대상 alias로 바꾸기 (Registry 변경 없음)

A-1 (조회) 승격 대상 alias가 의도한 version을 가리키는지 확인합니다. 예: `candidate-opt` -> 2. 이 alias는 승격 기간 동안 **누구도 옮기지 않도록** 팀에 공지합니다.

A-2 **[운영 변경 / 승인 필요]** Serving을 새 env로 다시 만듭니다.

- compose로 관리하는 경우(경로는 1장에서 확인):
  ```bash
  cd <serving compose dir>
  # env 파일에서 MODEL_ALIAS=candidate 를 MODEL_ALIAS=candidate-opt 로 변경 (원본은 P-4에서 백업함)
  sudo docker compose up -d --force-recreate --pull never serving   # Serving 서비스만. pull 하지 않음
  ```
  > 실행 전 (조회) `docker compose config --images <serving service>`(비밀값이 출력되지 않는 옵션만 사용)로 compose의 이미지 참조를 확인하고, 그 태그가 VM에서 P-4의 `.Image` digest와 같은 이미지로 해석되는지 `docker image inspect <참조> --format '{{.Id}}'`로 비교합니다. `:latest`처럼 움직이는 태그라 다른 이미지가 로컬에 있으면 env 변경과 함께 Serving 이미지도 바뀝니다.
  > 운영 확인 결과 Serving은 별도 project이므로 Backend 배포가 이 변경을 되돌리지 않습니다. `MODEL_ALIAS`는 compose `environment`가 아니라 env 파일(`/etc/cnc-wearpoint/inference.env`)에 있으므로 **env 파일을 수정**합니다. 셸에서 임시로 env를 덮어쓰는 방식은 쓰지 않습니다.
- `docker run`으로 관리하는 경우(이전 컨테이너는 삭제하지 않고 이름만 바꿔 보관):
  ```bash
  docker stop <serving>
  docker rename <serving> <serving>-prev-$TS
  docker update --restart no <serving>-prev-$TS      # 보관용 컨테이너가 자동 기동되지 않도록
  docker run -d --name <serving> <P-4의 network/env/restart/port 설정과 동일> \
    -e MODEL_ALIAS=candidate-opt <P-4와 같은 이미지 digest>
  ```
  (메모리 경합을 피하려고 이전 컨테이너는 먼저 stop합니다. 새 컨테이너가 로드를 마칠 때까지 서비스가 중단됩니다.)

A-3 검증(4장)

### 방식 B: 운영 alias `candidate`를 옮기기 (Registry 변경)

B-1 **[운영 변경 / 승인 필요]** 이전 version을 가리키는 보존용 alias를 만듭니다(롤백 대상 기록). Registry 쓰기 권한이 필요합니다.
```python
from mlflow import MlflowClient
c = MlflowClient()  # MLFLOW_TRACKING_URI=http://127.0.0.1:5000 (App VM), 쓰기 권한 사용자
c.set_registered_model_alias("cnc-wearpoint-multitask", "prod-previous", "1")
```
B-2 **[운영 변경 / 승인 필요]** `c.set_registered_model_alias("cnc-wearpoint-multitask", "candidate", "2")`
> 이 시점부터 Serving을 **즉시** 재시작해야 합니다. 그렇지 않으면 "alias는 V2, Serving은 V1"인 상태가 생기고, 이후 예기치 않은 재시작이 일어나면 V2가 로드됩니다.

B-3 **[운영 변경 / 승인 필요]** `docker restart <serving>` (compose인 경우 `docker compose restart <serving service>`)

B-4 검증(4장)

> `register_candidate.py`로 승격하지 않습니다. 이 스크립트는 새 version을 **만들고** alias를 무조건 덮어씁니다(ml/serving/register_candidate.py:135-168).

---

## 4. 검증 (모두 [조회])

```bash
# V-1 기동 완료 대기와 로드된 version
docker logs --since 10m <serving> | tail -n 50
docker exec <serving> python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8001/health',timeout=5).read().decode())"
#   기대: model_loaded=true, model_version="2" (model_alias는 env 문자열일 뿐이므로 판정에 쓰지 않음)

# V-2 Backend에서 Serving에 접근되는지 (요청 없이 health만 조회)
docker exec <backend> python -c "import urllib.request;print(urllib.request.urlopen('http://cnc-wearpoint-serving:8001/health',timeout=5).read().decode())"

# V-3 Backend health (CI deploy_backend와 같은 확인)
curl -s http://127.0.0.1:8000/health
```

```sql
-- V-4 승격 시각(T) 이후 저장 확인 (첫 수동/자동/모니터링 추론이 일어난 뒤)
SELECT model_name, model_version, COUNT(*), MIN(predicted_at), MAX(predicted_at)
  FROM predictions WHERE predicted_at >= '<T>' GROUP BY 1,2;
SELECT model_name, model_version, status, error_code, COUNT(*)
  FROM monitoring_inference_runs WHERE started_at >= '<T>' GROUP BY 1,2,3,4;
-- 기대: model_version='2'만 있음, status='failed'/INFERENCE_FAILED/INPUT_REJECTED가 늘지 않음
```

V-5 결과와 승인자, 시각, 사용한 방식(A/B), 이전/이후 version을 운영 기록에 남깁니다(DB에 alias 이력이 없으므로).

판정: V-1이 실패하거나, V-4에서 failed 또는 INPUT_REJECTED가 늘면 **즉시 5장 롤백**을 수행합니다.

---

## 5. 롤백 절차

### 방식 A로 승격한 경우 (Registry 쓰기 불필요)

**[운영 변경 / 승인 필요]**
- compose: env 파일을 P-4 백업으로 되돌린 뒤(`MODEL_ALIAS=candidate`) `sudo docker compose up -d --force-recreate --pull never serving`
- docker run:
  ```bash
  docker stop <serving> && docker rename <serving> <serving>-failed-$TS
  docker rename <serving>-prev-$TS <serving>
  docker update --restart <P-4의 원래 policy> <serving>
  docker start <serving>
  ```
  보관해 둔 컨테이너는 기동하면서 `candidate`를 **다시 해석합니다.** `candidate`가 계속 V1이면 V1이 로드됩니다. 시작 전에 P-3과 같은 조회로 `candidate`가 1을 가리키는지 확인합니다.

### 방식 B로 승격한 경우

**[운영 변경 / 승인 필요]**
```python
from mlflow import MlflowClient
c = MlflowClient()  # B-1과 같은 연결(App VM 로컬, 쓰기 권한 사용자)
# 먼저 (조회) c.get_model_version_by_alias("cnc-wearpoint-multitask", "prod-previous").version 이 "1"인지 확인
c.set_registered_model_alias("cnc-wearpoint-multitask", "candidate", "1")   # prod-previous가 가리키는 값
```
그 다음 **[운영 변경 / 승인 필요]** `docker restart <serving>`을 실행합니다.

### 이미지 롤백 (Serving 코드 문제인 경우)

**[운영 변경 / 승인 필요]** P-5에서 확인한 이전 digest로 컨테이너를 다시 만듭니다. `:latest`는 `serving-v*` 태그가 붙을 때마다 옮겨지므로(.gitlab-ci.yml:129-133) 롤백 기준으로 쓰지 않습니다. **SHA 태그나 digest**를 사용합니다.

### 롤백 후 검증

4장 V-1~V-4를 반복합니다. 기대 결과는 model_version `"1"`입니다.

### 보존 원칙

- 이전 컨테이너(`-prev-`, `-failed-`), P-4 백업 파일, 이전 이미지는 **안정화 기간(권장 7일)이 끝날 때까지 삭제하지 않습니다.** 삭제할 때도 별도 승인을 받습니다.
- V2 기간에 저장된 predictions와 monitoring_inference_runs 행은 **삭제하거나 수정하지 않습니다.** model_version으로 구분할 수 있습니다.
- MLflow version 2, `candidate-opt`, `prod-previous` alias는 삭제하지 않습니다.

---

## 6. 장애 대응

| 상황 | 증상 | 원인/근거 | 대응 |
|---|---|---|---|
| 모델 로드 실패 | 컨테이너 exit 또는 restart loop, Backend 502 / "Serving is unavailable" | lifespan 예외(service.py:95-102). flavor 비호환, epoch≠10(inference.py:54), torch 버전 불일치 | 즉시 5장 롤백. restart policy가 `always`이면 loop가 계속되므로 먼저 `docker update --restart no <serving>`(승인 필요) 실행 후 롤백 |
| 추론 실패(500) | Backend 502, auto/retry는 INFERENCE_FAILED + retry cookie | 출력 컬럼 누락 등(service.py:220-279) | V-4에서 실패 건수 확인 후 롤백. 사용자는 retry cookie로 재시도 |
| 추론 400 | INPUT_REJECTED, 재시도 불가, measurement failed | 모델 안의 ValueError -> 400(service.py:198-279). 모델 문제를 입력 문제로 잘못 분류할 수 있음 | 승격 직후 INPUT_REJECTED가 늘면 모델 문제로 보고 롤백. 실패한 measurement는 롤백 후 다시 요청 |
| 모델명 불일치 | "Unexpected model name", measurement failed | MODEL_NAME ≠ PREDICTION_MODEL_NAME(prediction_execution.py:225-227) | **[운영 변경 / 승인 필요]** Serving env의 MODEL_NAME을 P-4 백업 값으로 되돌리고 재생성(5장 방식 A 롤백과 같은 절차) |
| Object Storage(S3) 장애 | 실행 중인 Serving은 정상, **재시작하면 기동 실패** | artifact는 기동 시에만 다운로드(service.py:100) | 장애 중에는 승격, 롤백, 재시작을 **모두 보류**. restart policy 때문에 재시작될 수 있으니 VM 작업을 피함. 이미 내려간 상태라면 S3가 복구된 뒤 기동 |
| MLflow/RDS(Registry) 장애 | 위와 같음(alias 해석 실패) | service.py:95-97 | 위와 같음. 장애 중에는 **어떤 롤백도 불가능**합니다. 방식 B의 alias 롤백은 Registry 쓰기가 안 되고, 방식 A의 env 롤백도 재기동 시 alias 해석에 MLflow가 필요하기 때문입니다. 실행 중인 컨테이너를 유지하고(재시작 금지), MLflow 복구 후 롤백 여부를 판단합니다 |
| in-flight 요청 | 재시작 순간의 요청 실패 | 단일 프로세스, drain 없음(Dockerfile:22) | 수동: 502, measurement failed -> 다시 요청. auto/retry: retry cookie. 모니터링: INFERENCE_FAILED로 기록되고 **재큐잉 없음**(monitoring_inference_queue.py:286-319). 해당 구간 예측은 누락으로 기록. Backend가 중단된 경우 `predicting` 잔류 건은 30분 후 `scripts/recover_stale_prediction.py`로 복구(prediction_execution.py:34-36). 조회 모드(`--apply` 없음)는 [조회], `--apply --confirm-workers-checked`는 운영 DB 쓰기이므로 **[운영 변경 / 승인 필요]** |
| Backend 배포가 Serving에 영향 | backend `v*` 배포 후 Serving이 recreate되거나 사라짐 | **2026-11-20 확인: 별도 project라 영향 없음.** 다만 같은 `compose_default` 네트워크를 쓰므로 backend project를 `down`하면 네트워크가 사라질 수 있음 | backend project에 `docker compose down` 금지(`up`만 사용). 승격·롤백 기간에는 `v*` 태그 push를 피함 |

---

## 7. 승격 후 후속 조치 (제안이며, 이 runbook 범위 밖)

- Serving의 compose/run 정의와 env 템플릿을 저장소에 넣습니다(비밀값 제외).
- 실행 중인 version과 Registry alias가 다르면 경고하는 점검(cron, read-only)을 추가합니다.
- `register_candidate.py`의 기본 alias와 URI를 안전한 값으로 바꾸고 `--no-alias` 옵션을 추가합니다(코드 변경이므로 별도 작업).
- `ml/serving/.dockerignore`를 추가합니다(`.env.inference.local`이 이미지에 들어가는 것 방지).
- 운영 전용 alias(예: `production`)를 `candidate`와 분리하는 방안을 검토합니다.
- docs/deployment/infrastructure.md(k8s 참조), docs/database.md(champion/reload)를 정리합니다.
