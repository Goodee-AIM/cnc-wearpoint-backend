# 모델 생명주기 검증 보고서 (평가 → 승격 → 배포 → 롤백 검증 완료)

- 최종 갱신: 2026-11-21 (0장 추가). 1장 이후는 2026-11-20 작성 당시 기록이며, 위험 표(4장)만 상태를 갱신했습니다.
- 작성일: 2026-11-20
- 대상: `cnc-wearpoint-multitask` Version 1(`candidate`) / Version 2(`candidate-opt`)
- 범위: 저장소 분석, 오프라인 테스트, 사용자가 실행한 운영 read-only 조회
- **운영 변경 없음**: Alias 변경, Serving 재시작·교체, RDS 이력 삭제, MLflow 모델·artifact 삭제를 하지 않았습니다.
- 관련 문서: [현재 상태](MODEL_LIFECYCLE_CURRENT_STATE.md) · [테스트 계획](MODEL_LIFECYCLE_TEST_PLAN.md) · [승격·롤백 절차](MODEL_PROMOTION_ROLLBACK_RUNBOOK.md)

---

## 0. 2026-11-21 운영 검증 결과

평가, 승격, 배포, 롤백을 실제 운영 환경에서 한 차례 끝까지 실행했습니다. 운영 VM 작업과 MLflow 쓰기는 사용자가 직접 실행했고, 결과는 사용자가 공유한 출력과 운영 공개 API 교차 확인을 근거로 기록했습니다.

### 0.1 결론

| 질문 | 답 | 근거 |
|---|---|---|
| V1/V2의 성능이 같은 기준으로 비교됐는가 | **예.** 같은 Test Set 396건, 같은 정답 유형 대응 규칙으로 평가했고, 지표가 Registry에 기록됨 | 0.2절 |
| V1과 V2의 예측은 같은가 | **이 평가 환경에서는 396건 모두 행 단위로 같음** (예측 마모량 차이 0, 확률 차이 0, 유형 불일치 0) | `compare --version 1 --other 2` |
| 운영 Serving은 어느 모델을 쓰는가 | **`production` alias → Version 2** (run `98c32cdb968d4f57b77330db6c13baf4`), 이미지 `serving:v0.1.2` | 운영 `/health` |
| 승격과 롤백이 실제로 동작하는가 | **예.** 승격 V1→V2, 롤백 V2→V1, 복귀 V1→V2를 실행하고 매번 Serving 재시작 후 run_id로 확인 | 0.3절 |
| 롤백 기준은 어디에 남는가 | Registry 태그 `lifecycle.production.previous_version` (현재 `1`) | `model_lifecycle.py status` |

### 0.2 평가

- 도구: `ml/lifecycle/build_manifest.py`(manifest 생성), `ml/lifecycle/model_lifecycle.py evaluate / compare`
- 평가 데이터: 모델팀 Test Set **Set4·9·11·16, 396건**
  - 원본: 로컬 `storage/SetN/SetN/{images,sensordata}` (git 제외, 읽기 전용)
  - 정답과 짝: `matwi-research/data/raw/labels.csv`, crop: 같은 위치의 `sets.csv`
- manifest: `ml/lifecycle/eval/test_sets_manifest.csv`, sha256 `02ca2a44a0d153df6ee00ba233db87e1e425d7372a849c60c722800f01cfebf5`
  - 정답이나 파일이 없는 21행은 제외하고 사유를 기록
  - 파일 누락 0건, 중복 0건, crop 범위 초과 0건
  - 센서 CSV 396개 모두 Serving의 `read_and_cut_sensor` 통과
- crop: Set4·9·11은 `(1150,670,1750,1070)`, Set16은 `(1790,2045,2390,2445)` (`sets.csv`의 학습용 crop)
- 정답 유형 대응: `adhesion=other_wear, flank_wear+adhesion=other_wear`
  - 근거: 모델팀 `multimodal_type.ipynb`의 이진 분류 기준
- 실행 환경: 로컬 Windows `.venv-eval`, Python 3.12.10, torch 2.15.0+cpu, torchvision 0.29.2+cpu, mlflow 3.18.0, CUDA 없음

| 범위 | n | MAE (µm) | RMSE (µm) | 유형 정확도 |
|---|---:|---:|---:|---:|
| 전체 | 396 | 25.037 | 46.794 | 0.942 |
| Set4 | 97 | 15.307 | 25.349 | 0.887 |
| Set9 | 100 | 22.188 | 25.187 | 0.940 |
| Set11 | 100 | 19.747 | 68.876 | 0.990 |
| Set16 | 99 | 42.793 | 51.928 | 0.949 |

- V1과 V2의 수치는 위 표와 완전히 같습니다.
- 현재 Registry 태그(`eval.run_id`)가 가리키는 평가 run: V1 `f9ff0550fac44dfdaca2da1981c22049`, V2 `2867a49de76848e19c7b67108a28b0b3`
  - MLflow Default 실험(ID 0)에 기록됐습니다.
  - 두 run의 `eval/predictions.csv`는 `compare`가 실제로 내려받아 비교했으므로 존재가 확인됐습니다. manifest artifact는 코드상 함께 올라가지만 직접 확인하지는 않았습니다.
  - Set별 지표 기록 기능을 넣기 전에 한 첫 평가 run(V1 `263b8d1f…`, V2 `6f964502…`)도 전체 지표가 같았습니다.

해석할 때 주의할 점:
- Set11은 RMSE/MAE가 3.5배라 극소수의 큰 오차가 전체를 끌어올립니다. 정답 wear 최댓값이 750µm(다른 Set은 최대 300µm)인 행이 유력하지만, 아직 확인하지 않았습니다.
- Set16은 MAE가 가장 큽니다. 소재(RVS 304)와 crop이 다른데, 어느 쪽이 원인인지는 구분하지 않았습니다.
- 유형 정답 분포는 flank_wear 280건, other_wear 116건입니다. 모두 flank_wear로 찍어도 정확도가 약 70.7%이니, 0.942는 이 기준선과 비교해서 봐야 합니다.

### 0.3 승격·배포·롤백 실행 기록 (실제 순서)

| # | 작업 | 실행 위치 | 확인 결과 |
|---|---|---|---|
| 0 | 설정 백업: `compose.yaml.bak-20261121`, `inference.env.bak-20261121` | VM | 파일 생성 |
| 1 | Serving 이미지 교체 `f38806e…` → `serving:v0.1.2` (digest `sha256:c9652af7…`, 커밋 `46e4048`, `ml/serving` 코드는 `c180e3a`와 같음). alias는 `candidate-opt` 유지 | VM | `/health`: candidate-opt, v2, run `98c32cdb…`. 로그 `Loaded model … version=2 run_id=98c32cdb…` |
| 2 | `promote --version 1 --alias production` (dry-run 후 실행). 처음 생긴 alias라 직전 버전 없음 | 로컬 | production → v1 |
| 3 | `promote --version 2 --alias production`. MAE가 같아 판단 조건 통과 | 로컬 | production → v2, `previous_version = 1` |
| 4 | `MODEL_ALIAS=candidate-opt` → `production`, `up -d --force-recreate` | VM | `/health`: production, v2, run `98c32cdb…`. 재생성 직후 일시적으로 `Connection reset by peer`가 났다가 정상화 |
| 5 | `rollback --alias production` (v2 → v1), 재시작 | 로컬 + VM | `/health`: v1, run `f61d462aabe8483290e8906117271c63` (Registry V1의 run_id와 일치) |
| 6 | `rollback --alias production` (v1 → v2), 재시작 | 로컬 + VM | `/health`: production, v2, run `98c32cdb…` |

- 각 단계 후 운영 공개 API `/api/monitoring/inference/current`로 따로 확인했습니다. 모니터링 추론이 계속 완료되고 있었고, 복귀 후 `model_version`은 모두 2였습니다.
- 최종 상태: alias `candidate → v1`, `candidate-opt → v2`, `production → v2`, 태그 `lifecycle.production.previous_version = 1`. Serving은 이미지 `v0.1.2`, `MODEL_ALIAS=production`, RestartCount 0입니다.

### 0.4 함께 반영된 변경

| 변경 | 커밋 / 배포 | 내용 |
|---|---|---|
| 안전한 등록 기본값, 평가·승격·롤백 도구, Serving의 로드 버전 로그·`/health` run_id, `.dockerignore` | `c180e3a` | R1·R2·R3·R6 해결 (4장) |
| manifest 생성 도구, Set별 crop, `--type-map` | `e675434` | |
| Set별 지표, 개별 예측 artifact, `compare` | `1e0d513` | |
| Serving 이미지 빌드 조건에 `serving-v*` 태그 추가 | `46e4048` → `serving-v0.1.2` | |
| 센서 timestamp를 나노초 정밀도로 검증 (v0.1.12에서 MATWI 원본 CSV가 422로 거절되던 버그 수정) | `e675434` → backend `v0.1.13` | 운영에서 Set4 원본 업로드로 확인 (예측 38.34µm, 정답 45µm, 유형 일치) |

### 0.5 검증되지 않은 사항

| 항목 | 내용 |
|---|---|
| 운영 환경에서의 출력 동일성 | 평가는 Python 3.12.10 / cloudpickle 3.1.3에서 했고, 모델은 3.11.18 / 3.1.2로 저장됐으며 운영 Serving은 Python 3.11 컨테이너입니다. `ml/serving/requirements.txt`가 numpy·pandas·scipy 버전을 고정하지 않아서, 운영 출력과 숫자까지 같은지는 확인하지 않았습니다. |
| Set16 운영 crop | 평가는 학습용 crop으로 했습니다. 운영 Serving은 원본 크기 이미지에 고정 crop `(1150,670,1750,1070)`을 쓰므로, **Set16 원본을 업로드하면 평가와 다른 영역으로 추론합니다.** |
| crop·라벨 정의 | `sets.csv`의 crop이 실제 학습 ROI와 같은지, 유형 대응 규칙이 등록된 멀티태스크 모델의 학습 라벨과 같은지는 검증하지 않았습니다. |
| 학습·평가 데이터 분리 | Set4·9·11·16이 V1 checkpoint 학습에서 제외됐는지는 저장소에서 확인할 수 없습니다(학습 코드 없음). 지표를 일반화 성능으로 해석하려면 이 전제가 필요합니다. |
| V2 checkpoint 해시 (ART-05) | 파일 크기만 같다는 것을 확인했습니다. 대신 396건의 예측이 같다는 결과로 행동 동일성은 확인됐습니다. |
| 재시작 중 실패한 추론 | 재시작할 때마다 수십 초 동안 Serving이 응답하지 않습니다. 그 사이의 모니터링 추론이 `INFERENCE_FAILED`로 기록됐는지는 확인하지 않았습니다. 공개 API는 현재 회차만 보여줍니다. |
| TEST 환경 검증 | 원래 계획(5장)의 TEST 환경 검증(LOAD·INF·SCH·PRO·RB)은 하지 않았습니다. 그 대신 운영에서 롤백 리허설을 했습니다. |

---

> **2026-11-20 오후 갱신:** 이 보고서 작성 후 운영 Serving을 **Version 2(`candidate-opt`)로 전환**했습니다(승격·롤백 절차서 방식 A). 전환 후 운영 측정: 모니터링 추론 평균 약 5.2초 → **약 1.1초**, 대기열 대기 최대 43초 → **약 0.1~2.1초**, `model_version` 2 기록 확인. 아래 표의 "운영 Serving = Version 1"은 전환 전 상태입니다.

## 1. 결론 요약

| 질문 | 답 | 근거 |
|---|---|---|
| 운영 Serving은 어느 버전을 쓰는가 | **Version 1** (`candidate`) | 운영 `/health` `model_version: "1"` |
| Alias를 바꾸면 운영 모델이 바뀌는가 | **바로 바뀌지 않음.** Serving은 기동 시 1회만 Alias를 해석하고 reload 기능이 없음. 다음 재시작(수동·VM 재부팅·restart policy) 때 반영 | `ml/serving/service.py:80-102`; 오프라인 테스트 |
| Serving 배포는 자동인가 | **아니오.** `/opt/cnc-wearpoint/serving/compose.yaml`로 수동 운영. CI는 이미지 빌드·태그만 | 운영 `docker inspect`; `.gitlab-ci.yml:99-137` |
| Backend 배포가 Serving에 영향을 주는가 | **아니오.** 별도 compose project | 운영 compose label |
| V2는 무엇인가 | **같은 가중치(크기 동일) + 최적화된 추론 코드.** pyfunc, signature 동일. `model.pt2` 없음(핸드오프 정정) | 운영 MLmodel·파일 목록; 로컬 diff |
| V1/V2 성능이 같은 기준으로 비교됐는가 | **아니오.** 두 버전 모두 run·logged model에 지표 없음 | 운영 `get_run`/`get_logged_model` |
| 예측 이력에서 버전 추적이 되는가 | **예(version 단위).** `predictions`, `monitoring_inference_runs`에 model_name/model_version 저장. alias·run_id는 저장 안 됨 | `sql/cnc/schema.sql`, 테스트 |

## 2. 테스트 결과

### 2.1 오프라인 자동 테스트 (2026-11-20 로컬)

| 파일 | 결과 | 검증 내용 |
|---|---|---|
| `tests/model_lifecycle/test_serving_model_selection.py` | PASS (11) | Alias 1회 해석, `models:/NAME/VERSION` 로드, Alias 이동 후에도 재시작 전까지 버전 유지, `/health`·응답의 model 필드, 로드 실패 시 fallback 없음, 출력 컬럼 누락 시 500 |
| `tests/model_lifecycle/test_backend_model_contract.py` | PASS (39) | version `"1"`/`"2"` 허용, 잘못된 모델명·버전 형식 거부, 저장 시 model_name/model_version 기록, alias 미저장, DB 접근 전 검증 |
| `tests/model_lifecycle/test_registry_integration.py` | SKIP (9, 기본값) | 실제 Registry GET 전용 조회. `MODEL_LIFECYCLE_INTEGRATION=1` + `MLFLOW_TRACKING_URI` + mlflow 설치 환경에서만 실행. 쓰기 호출은 allow-list로 차단 |
| 전체 스위트 | **255 passed, 10 skipped** | 기존 테스트 영향 없음 |

### 2.2 테스트 계획 항목 상태 (38건)

| 상태 | 건수 | 항목 |
|---|---|---|
| PASS | 11 | REG-01·02·03·05, ART-01·03, LOAD-04, SCH-01·02, PRO-04, FAIL-06 |
| FAIL | 0 | |
| HOLD | 27 | 아래 3장 |

REG-01·02·03, ART-03은 운영 read-only 조회로 PASS 처리했습니다.

### 2.3 이미 완료된 테스트 (재실행하지 않음)

- 2026-11-13 toy 회귀 모델 V1/V2(run `300d0736…`, `e0ab3ace…`)로 `champion` Alias V1→V2→V1 이동과 버전별 로드 PASS (핸드오프 기준). Registry Alias 메커니즘의 근거이며, **multitask Serving 경로(재시작 필요성, Backend 저장)는 검증하지 않은 테스트**입니다. 해당 run이 MLflow에 남아 있는지는 미확인(REG-04).

## 3. 미검증 사항 (HOLD 사유별)

| 분류 | 항목 | 필요한 것 |
|---|---|---|
| 로컬에서 가능 (승인 대기) | INF-00 V1/V2 동일 입력 동등성·지연 시간 | 로컬 별도 가상환경에 torch CPU 설치 |
| 운영 read-only 조회 | ART-02 V1 artifact 무결성, ART-05 V2 checkpoint 해시, REG-04 toy run, U5 런타임 import 경로, U6 Backend env, U7 버전별 예측 분포, U10 이미지 캐시, U12 진행 중 작업 | 사용자 실행 조회 |
| TEST 환경 필요 (승인 필요) | LOAD-01~03, INF-01~03, SCH-03~05, PRO-01~03, RB-01~03, FAIL-01~05·07·08 | TEST registered model 또는 test alias(Registry 쓰기), TEST Serving 컨테이너(운영 VM 자원) |

## 4. 발견한 위험과 개선 제안 (우선순위순)

상태 열은 2026-11-21 기준입니다.

| # | 위험 | 영향 | 제안 | 상태 (11-21) |
|---|---|---|---|---|
| R1 | `register_candidate.py` 기본값이 운영 MLflow에 등록하고 **운영 `candidate` Alias를 무조건 덮어씀** | 실수로 실행하면 다음 Serving 재시작 때 운영 모델이 조용히 바뀜 | `--alias` 기본값 제거 또는 `--no-alias` 기본, 기존 Alias 확인 후 확인 프롬프트 | **해결** (`c180e3a`): tracking URI를 직접 지정해야 하고, 기본으로 alias를 옮기지 않으며, 이미 다른 버전을 가리키는 alias는 `--force-alias` 없이는 옮기지 않음 |
| R2 | V1/V2 평가 지표가 Registry에 없음 | 승격 근거가 없음 | 고정 평가 데이터로 평가 스크립트를 만들고 결과를 MLflow에 기록(평가 → 판정 → 승인 → 배포 단계 분리) | **해결**: `evaluate`로 기록, `promote`가 같은 데이터셋 기준 지표를 비교 (0.2절) |
| R3 | Serving이 로드한 버전을 로그에 남기지 않음 | 사후 감사가 `/health` 호출에만 의존 | 기동 시 `model_name/alias/version/model_id`를 로그로 출력 | **해결** (`serving:v0.1.2` 운영 반영): 기동 로그와 `/health`에 version·run_id 표시 |
| R4 | Serving 기동이 공개 URL(`https://aimw.duckdns.org/mlflow/`) 경유 + fail-hard | nginx·TLS·DNS 장애 중 재시작하면 Serving 전체 중단 | 내부 주소 사용 검토, 장애 중 재시작 금지를 절차에 명시(반영됨) | 남음. 이제 승격·롤백마다 재시작이 필요해 노출이 늘어남 |
| R5 | Serving 실행 정의가 저장소 밖에만 있음 | 재구성·롤백 재현성 부족 | `/opt/cnc-wearpoint/serving/compose.yaml`을 비밀값 제외하고 저장소에 보관 | 남음 |
| R6 | `ml/serving`에 `.dockerignore` 없음 + `COPY . .` | 로컬 빌드 시 `.env.inference.local`(MLflow 자격증명)이 이미지에 포함 | `.dockerignore` 추가 (CI 빌드는 영향 없음) | **해결** (`c180e3a`) |
| R7 | 이미지 `/app`에 V2 코드가 있고, V1 artifact에도 같은 이름의 모듈이 있음 | 런타임에 어느 코드가 쓰이는지 불명확(U5). V1/V2 코드는 결과가 같아야 하므로 실제 영향은 작을 것으로 추정 | read-only 확인 후 문서화 | 남음. 다만 V1/V2 예측이 396건 모두 같다는 결과로 영향은 작다고 볼 수 있음 |
| R8 | alias 변경 이력이 어디에도 남지 않음 | 언제 누가 바꿨는지 추적 불가 | 승격·롤백 시 snapshot 기록(절차에 반영), 장기적으로 model version tag나 감사 로그 사용 | 일부 해결: 직전 버전 태그와 version별 `lifecycle.<alias>.promoted_at` 태그. 누가 했는지와 전체 이력은 여전히 없음 |
| R9 | 운영 Serving이 원본 크기 이미지에 고정 crop만 사용 (11-21 발견) | Set16처럼 crop이 다른 Set의 원본은 엉뚱한 영역으로 추론됨 | crop을 입력으로 받거나 Set별 설정으로 처리 | 남음 (결정 필요) |

## 5. 운영 전환(V1 → V2) 선행 조건

1. INF-00 PASS: 동일 입력에서 V1/V2 결과 동등, V2 지연 시간 개선 확인
2. ART-05 PASS: V2 checkpoint 해시가 V1과 같음
3. TEST 환경에서 LOAD·INF·SCH·PRO·RB 통과 (V2 로드, 추론, Backend 저장, 승격, 롤백)
4. 롤백 준비: env 파일과 compose 백업, 현재 이미지 digest 기록, Alias snapshot
5. 작업 시간대: 진행 중 추론 없음, Backend 배포 없음, MLflow·nginx 정상

## 6. 별도 승인이 필요한 작업

| 작업 | 이유 |
|---|---|
| 로컬 가상환경에 torch CPU 설치 후 INF-00 실행 | 로컬 전용이지만 패키지 설치(약 200MB) |
| TEST registered model 생성 또는 test alias 추가 | MLflow Registry(RDS) 쓰기 |
| 운영 VM에서 TEST Serving 컨테이너 기동 | 운영 VM CPU·메모리 사용(3GB 제한 권장) |
| 운영 Serving의 `MODEL_ALIAS` 변경과 재시작 (방식 A) | 운영 모델 교체, 재시작 중 추론 중단 |
| 운영 `candidate` Alias 이동 (방식 B) | 운영 Registry 변경, 현재 제약과 충돌 |
| R1·R3·R5·R6 코드 수정 | 저장소 변경 (Serving 코드 수정은 새 이미지 빌드가 필요) |
