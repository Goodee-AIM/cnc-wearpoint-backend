"""Authenticated, disabled-by-default model prediction endpoint."""

from fastapi import APIRouter, Header, Path

from app.services.prediction_execution import check_prediction_access, execute_prediction

router = APIRouter(prefix="/api/measurements", tags=["predictions"])


@router.post("/{measurement_id}/predict")
def predict_measurement(
    measurement_id: int = Path(gt=0),
    prediction_token: str | None = Header(default=None, alias="X-Prediction-Token"),
):
    check_prediction_access(prediction_token)
    return execute_prediction(measurement_id)
