# 모델 라이프사이클 (최소 구성)

`model_lifecycle.py` 하나로 **평가 → 승격(게이트) → 롤백**을 실행합니다. 모든 명령에 `--tracking-uri` 또는 `MLFLOW_TRACKING_URI`를 반드시 지정해야 합니다(운영 기본값 없음).

```bash
export MLFLOW_TRACKING_URI=https://aimw.duckdns.org/mlflow/   # 대상 Registry를 명시

python ml/lifecycle/model_lifecycle.py status
python ml/lifecycle/model_lifecycle.py evaluate --version 2 --manifest eval/manifest.csv
python ml/lifecycle/model_lifecycle.py promote  --version 2 --alias production --dry-run
python ml/lifecycle/model_lifecycle.py promote  --version 2 --alias production
python ml/lifecycle/model_lifecycle.py rollback --alias production
```

## 단계별 동작

| 명령 | 하는 일 | Registry 변경 |
|---|---|---|
| `status` | alias, 버전별 평가 지표, 롤백 기록을 보여줍니다 | 없음 |
| `evaluate` | 지정 버전으로 manifest 전체를 추론해 MAE·RMSE·유형 정확도를 계산합니다. 결과는 평가 run(metrics + manifest artifact)과 version 태그(`eval.*`)로 기록합니다 | version 태그만 |
| `promote` | 게이트를 통과하면 alias를 옮기고, 직전 버전을 `lifecycle.<alias>.previous_version` 태그에 남깁니다 | alias + 태그 |
| `rollback` | alias를 직전 버전으로 되돌립니다. 다시 실행하면 원래 버전으로 돌아갑니다 | alias + 태그 |

`evaluate`는 Serving과 같은 환경(torch, `ml/serving` 코드)에서 실행해야 합니다. 같은 ROI 규칙(`service.determine_crop`)을 사용합니다.

## 승격 게이트 (`promote`)
- 대상 버전에 평가 결과(`eval.mae_um`, `eval.dataset_sha256`)가 없으면 거부합니다.
- 현재 alias 버전과 **같은 manifest**(sha256 일치)로 평가된 경우에만 비교합니다. 대상의 MAE가 더 나쁘면 거부합니다.
- 비교할 수 없거나(평가 안 됨, 다른 데이터셋) MAE가 더 나쁜데도 승격하려면 `--force`를 붙여야 합니다.
- `--max-mae <µm>`: 절대 기준을 추가합니다.
- `--dry-run`: 판단 결과만 출력하고 Registry는 바꾸지 않습니다.

## 반영 시점 (중요)
Serving은 **기동할 때 한 번만** `MODEL_ALIAS`를 해석합니다. 승격이나 롤백 후에는 Serving 컨테이너를 재시작해야 실제로 반영되고, 재시작하는 동안 추론이 잠시 중단됩니다. 재시작한 뒤에는 `/health`의 `model_version`과 `model_run_id`로 확인합니다. 운영 Serving은 `/opt/cnc-wearpoint/serving/compose.yaml`(수동 운영)에서 관리합니다.

## Manifest 형식
```csv
image_path,sensor_path,wear_um,type
images/set4/xxx.png,sensors/set4/xxx.csv,105.0,flank_wear
```
상대 경로는 manifest 파일 위치를 기준으로 해석합니다. `wear_um`/`type`은 `wear_labels.original_wear_um`/`original_type`과 같은 정답값입니다. 승격 비교는 **같은 manifest 파일**로 평가한 경우에만 의미가 있으니, 평가용 manifest는 고정해서 보관하세요.

## 이번 범위에서 제외한 것
무중단 reload, CI의 Serving 자동 배포, `predictions`에 alias/run_id 기록(DB 마이그레이션), 드리프트 모니터링, 재학습 파이프라인.
