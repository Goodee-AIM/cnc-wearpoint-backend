import argparse
import os
import sys
from pathlib import Path

import mlflow
import pandas as pd
from mlflow import MlflowClient
from mlflow.models import infer_signature


BASE_DIR = Path(__file__).resolve().parent

# inference.py / preprocessing.py를 top-level module로 import할 수 있게 합니다.
sys.path.insert(0, str(BASE_DIR))

from mlflow_model import CncWearPointModel


DEFAULT_MODEL_NAME = "cnc-wearpoint-multitask"
DEFAULT_EXPERIMENT_NAME = "CNC-wear-predict-type-classification"
DEFAULT_ALIAS = "candidate"


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--checkpoint",
        required=True,
        help="Path to epoch_010.pth",
    )

    parser.add_argument(
        "--tracking-uri",
        default=os.getenv(
            "MLFLOW_TRACKING_URI",
            "https://aimw.duckdns.org/mlflow/",
        ),
    )

    parser.add_argument(
        "--experiment",
        default=DEFAULT_EXPERIMENT_NAME,
    )

    parser.add_argument(
        "--model-name",
        default=DEFAULT_MODEL_NAME,
    )

    parser.add_argument(
        "--alias",
        default=DEFAULT_ALIAS,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=2,
    )

    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint).resolve()

    if not checkpoint_path.is_file():
        raise FileNotFoundError(
            f"Checkpoint not found: {checkpoint_path}"
        )

    requirements_path = BASE_DIR / "requirements.txt"

    if not requirements_path.is_file():
        raise FileNotFoundError(
            f"requirements.txt not found: {requirements_path}"
        )

    mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_experiment(args.experiment)

    input_example = pd.DataFrame(
        [
            {
                "image_path": "image.png",
                "sensor_path": "sensor.csv",
                "crop_left": 0,
                "crop_top": 0,
                "crop_right": 600,
                "crop_bottom": 400,
            }
        ]
    )

    output_example = pd.DataFrame(
        [
            {
                "epoch": 10,
                "predicted_wear_um": 65.25,
                "flank_wear_probability": 1.0,
                "predicted_type": "flank_wear",
                "threshold": 0.5,
                "window_count": 127,
                "sampling_hz": 1623.98,
                "cut_start_index": 15894,
                "cut_end_index_exclusive": 81382,
            }
        ]
    )

    signature = infer_signature(
        input_example,
        output_example,
    )

    code_paths = [
        str(BASE_DIR / "mlflow_model.py"),
        str(BASE_DIR / "inference.py"),
        str(BASE_DIR / "preprocessing.py"),
    ]

    with mlflow.start_run(
        run_name="register-epoch10-candidate"
    ) as run:
        mlflow.set_tags(
            {
                "model_role": "multitask",
                "checkpoint_epoch": "10",
                "deployment_status": "candidate",
                "inference_batch_size": str(args.batch_size),
                "dependency_pins": "pending",
            }
        )

        model_info = mlflow.pyfunc.log_model(
            name="model",
            python_model=CncWearPointModel(
                batch_size=args.batch_size,
                device="cpu",
            ),
            artifacts={
                "checkpoint": str(checkpoint_path),
            },
            code_paths=code_paths,
            registered_model_name=args.model_name,
            signature=signature,
            pip_requirements=str(requirements_path),
            metadata={
                "checkpoint": checkpoint_path.name,
                "batch_size": args.batch_size,
                "device": "cpu",
            },
        )

        version = model_info.registered_model_version

        if version is None:
            raise RuntimeError(
                "Model was logged but no registered model version was returned."
            )

        client = MlflowClient()

        client.set_registered_model_alias(
            args.model_name,
            args.alias,
            str(version),
        )

        print("MLflow registration complete")
        print(f"run_id={run.info.run_id}")
        print(f"model_name={args.model_name}")
        print(f"version={version}")
        print(f"alias={args.alias}")
        print(f"model_uri=models:/{args.model_name}@{args.alias}")


if __name__ == "__main__":
    main()