import os
from pathlib import Path

import mlflow.pyfunc
import pandas as pd


REQUIRED_COLUMNS = {
    "image_path",
    "sensor_path",
    "crop_left",
    "crop_top",
    "crop_right",
    "crop_bottom",
}


class CncWearPointModel(mlflow.pyfunc.PythonModel):
    def __init__(self, batch_size=2, device="cpu"):
        self.batch_size = int(batch_size)
        self.device = device
        self.model = None
        self.checkpoint = None

    def load_context(self, context):
        from inference import load_model

        checkpoint_path = context.artifacts["checkpoint"]

        self.model, self.checkpoint = load_model(
            checkpoint_path,
            self.device,
        )

    def predict(self, context, model_input, params=None):
        from inference import predict_record

        if not isinstance(model_input, pd.DataFrame):
            model_input = pd.DataFrame(model_input)

        missing = REQUIRED_COLUMNS - set(model_input.columns)

        if missing:
            raise ValueError(
                f"Missing required columns: {sorted(missing)}"
            )

        # 등록 당시 batch_size를 기본값으로 사용하되,
        # 실행 환경에서 INFERENCE_BATCH_SIZE가 설정되어 있으면
        # 해당 값을 우선 사용합니다.
        batch_size = int(
            os.getenv(
                "INFERENCE_BATCH_SIZE",
                str(self.batch_size),
            )
        )

        if batch_size < 1:
            raise ValueError(
                "INFERENCE_BATCH_SIZE must be positive."
            )

        results = []

        for row in model_input.to_dict(orient="records"):
            image_path = Path(
                str(row["image_path"])
            )

            sensor_path = Path(
                str(row["sensor_path"])
            )

            if not image_path.is_file():
                raise FileNotFoundError(
                    f"Image file not found: {image_path}"
                )

            if not sensor_path.is_file():
                raise FileNotFoundError(
                    f"Sensor file not found: {sensor_path}"
                )

            crop = (
                int(row["crop_left"]),
                int(row["crop_top"]),
                int(row["crop_right"]),
                int(row["crop_bottom"]),
            )

            result = predict_record(
                model=self.model,
                checkpoint=self.checkpoint,
                image_path=image_path,
                sensor_path=sensor_path,
                crop=crop,
                batch_size=batch_size,
            )

            results.append(result)

        return pd.DataFrame(results)