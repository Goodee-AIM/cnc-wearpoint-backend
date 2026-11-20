# 모델 생명주기 검증 보고서 (P0 완료 / P1 준비)

- 작성일: 2026-11-20
- 대상: `cnc-wearpoint-multitask` Version 1(`candidate`) / Version 2(`candidate-opt`)
- 범위: 저장소 분석, 오프라인 테스트, 사용자가 실행한 운영 read-only 조회
- **운영 변경 없음**: Alias 변경, Serving 재시작·교체, RDS 이력 삭제, MLflow 모델·artifact 삭제를 하지 않았습니다.
- 관련 문서: [현재 상태](MODEL_LIFECYCLE_CURRENT_STATE.md) · [테스트 계획](MODEL_LIFECYCLE_TEST_PLAN.md) · [승격·롤백 절차](MODEL_PROMOTION_ROLLBACK_RUNBOOK.md)

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

| # | 위험 | 영향 | 제안 |
|---|---|---|---|
| R1 | `register_candidate.py` 기본값이 운영 MLflow에 등록하고 **운영 `candidate` Alias를 무조건 덮어씀** | 실수로 실행하면 다음 Serving 재시작 때 운영 모델이 조용히 바뀜 | `--alias` 기본값 제거 또는 `--no-alias` 기본, 기존 Alias 확인 후 확인 프롬프트 |
| R2 | V1/V2 평가 지표가 Registry에 없음 | 승격 근거가 없음 | 고정 평가 데이터로 평가 스크립트를 만들고 결과를 MLflow에 기록(평가 → 판정 → 승인 → 배포 단계 분리) |
| R3 | Serving이 로드한 버전을 로그에 남기지 않음 | 사후 감사가 `/health` 호출에만 의존 | 기동 시 `model_name/alias/version/model_id`를 로그로 출력 |
| R4 | Serving 기동이 공개 URL(`https://aimw.duckdns.org/mlflow/`) 경유 + fail-hard | nginx·TLS·DNS 장애 중 재시작하면 Serving 전체 중단 | 내부 주소 사용 검토, 장애 중 재시작 금지를 절차에 명시(반영됨) |
| R5 | Serving 실행 정의가 저장소 밖에만 있음 | 재구성·롤백 재현성 부족 | `/opt/cnc-wearpoint/serving/compose.yaml`을 비밀값 제외하고 저장소에 보관 |
| R6 | `ml/serving`에 `.dockerignore` 없음 + `COPY . .` | 로컬 빌드 시 `.env.inference.local`(MLflow 자격증명)이 이미지에 포함 | `.dockerignore` 추가 (CI 빌드는 영향 없음) |
| R7 | 이미지 `/app`에 V2 코드가 있고, V1 artifact에도 같은 이름의 모듈이 있음 | 런타임에 어느 코드가 쓰이는지 불명확(U5). V1/V2 코드는 결과가 같아야 하므로 실제 영향은 작을 것으로 추정 | read-only 확인 후 문서화 |
| R8 | alias 변경 이력이 어디에도 남지 않음 | 언제 누가 바꿨는지 추적 불가 | 승격·롤백 시 snapshot 기록(절차에 반영), 장기적으로 model version tag나 감사 로그 사용 |

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
