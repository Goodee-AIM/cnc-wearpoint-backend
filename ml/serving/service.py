import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image


MODEL_NAME = os.getenv(
    "MODEL_NAME",
    "cnc-wearpoint-multitask",
)

MODEL_ALIAS = os.getenv(
    "MODEL_ALIAS",
    "candidate",
)

WARNING_THRESHOLD = 150.0
DANGER_THRESHOLD = 200.0

# 고정 카메라 / 고정 촬영 위치 / 고정 해상도 환경에서 사용하는 ROI
FIXED_CROP = (1150, 670, 1750, 1070)

# 기존 데이터처럼 이미 ROI crop이 적용된 이미지 크기
CROPPED_SIZE = (600, 400)

logger = logging.getLogger("uvicorn.error")

model = None
model_version = None
model_run_id = None


def determine_crop(
    image_path: Path,
) -> tuple[int, int, int, int]:
    """
    입력 이미지에 적용할 ROI를 결정합니다.

    - 기존 600x400 ROI 이미지:
      이미지 전체 영역을 사용합니다.
    - 고정 카메라 원본 이미지:
      FIXED_CROP 영역을 사용합니다.
    """
    with Image.open(image_path) as image:
        width, height = image.size

    # 기존 테스트 데이터처럼 이미 crop된 이미지
    if (width, height) == CROPPED_SIZE:
        return 0, 0, width, height

    left, top, right, bottom = FIXED_CROP

    if right > width or bottom > height:
        raise ValueError(
            f"입력 이미지 크기 {width}x{height}에서 "
            f"ROI {FIXED_CROP}를 적용할 수 없습니다."
        )

    return FIXED_CROP


def determine_status(
    wear: float,
) -> str:
    """
    예측 마모량을 기준으로 상태를 결정합니다.
    """
    if wear >= DANGER_THRESHOLD:
        return "danger"

    if wear >= WARNING_THRESHOLD:
        return "warning"

    return "normal"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    서비스 시작 시 MLflow Registry에서 모델을 한 번만 로드하고,
    종료 시 참조를 해제합니다.
    """
    global model, model_version, model_run_id

    tracking_uri = os.environ["MLFLOW_TRACKING_URI"]

    mlflow.set_tracking_uri(
        tracking_uri
    )

    # Resolve alias once, then load the immutable Registry version.
    resolved = MlflowClient().get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)
    model_version = str(resolved.version)
    model_run_id = getattr(resolved, "run_id", None)
    model_uri = f"models:/{MODEL_NAME}/{model_version}"

    model = mlflow.pyfunc.load_model(
        model_uri
    )

    # Record what was actually loaded; the alias may move later.
    logger.info(
        "Loaded model %s alias=%s version=%s run_id=%s",
        MODEL_NAME, MODEL_ALIAS, model_version, model_run_id,
    )

    yield

    model = None
    model_version = None
    model_run_id = None


app = FastAPI(
    title="CNC WearPoint Inference Service",
    lifespan=lifespan,
)


@app.get("/health")
def get_health():
    """
    Inference Service와 모델 로드 상태를 확인합니다.
    """
    return {
        "status": "ok",
        "model_name": MODEL_NAME,
        "model_alias": MODEL_ALIAS,
        "model_version": model_version,
        "model_run_id": model_run_id,
        "model_loaded": model is not None,
    }


@app.post("/predictions")
async def create_prediction(
    image: UploadFile = File(...),
    sensor_csv: UploadFile = File(...),
):
    """
    Tool Image와 Sensor CSV를 입력받아
    새로운 AI prediction을 생성합니다.
    """
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Model is not loaded.",
        )

    image_suffix = Path(
        image.filename or ""
    ).suffix.lower()

    if image_suffix not in {
        ".jpg",
        ".jpeg",
        ".png",
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "JPG, JPEG, PNG 이미지만 "
                "사용할 수 있습니다."
            ),
        )

    sensor_filename = (
        sensor_csv.filename or ""
    ).lower()

    if not sensor_filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Sensor 파일은 CSV "
                "형식이어야 합니다."
            ),
        )

    with tempfile.TemporaryDirectory(
        prefix="cnc-wearpoint-",
    ) as temp_dir:
        temp_dir = Path(temp_dir)

        image_path = (
            temp_dir
            / f"image{image_suffix}"
        )

        sensor_path = (
            temp_dir
            / "sensor.csv"
        )

        image_path.write_bytes(
            await image.read()
        )

        sensor_path.write_bytes(
            await sensor_csv.read()
        )

        try:
            crop = determine_crop(
                image_path
            )

            model_input = pd.DataFrame(
                [
                    {
                        "image_path": str(
                            image_path
                        ),
                        "sensor_path": str(
                            sensor_path
                        ),
                        "crop_left": crop[0],
                        "crop_top": crop[1],
                        "crop_right": crop[2],
                        "crop_bottom": crop[3],
                    }
                ]
            )

            result = model.predict(
                model_input
            ).iloc[0]

            predicted_wear = float(
                result[
                    "predicted_wear_um"
                ]
            )

            predicted_type = str(
                result[
                    "predicted_type"
                ]
            )

            probability = float(
                result[
                    "flank_wear_probability"
                ]
            )

            status = determine_status(
                predicted_wear
            )

            return {
                "predicted_wear_um": (
                    predicted_wear
                ),
                "predicted_type": (
                    predicted_type
                ),
                "flank_wear_probability": (
                    probability
                ),
                "status": status,
                "model_name": MODEL_NAME,
                "model_alias": MODEL_ALIAS,
                "model_version": model_version,
                "model_epoch": int(
                    result["epoch"]
                ),
                "window_count": int(
                    result[
                        "window_count"
                    ]
                ),
                "sampling_hz": float(
                    result[
                        "sampling_hz"
                    ]
                ),
            }

        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc