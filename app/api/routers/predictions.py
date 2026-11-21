"""Model prediction: private server token OR HTTPS HttpOnly operator session."""

from fastapi import APIRouter, HTTPException, Header, Path, Request, Response
from pydantic import BaseModel, Field

from app.core.prediction_session import (
    login_operator, logout_operator, operator_session_exists, require_operator_session,
)
from app.services.prediction_execution import check_prediction_access, execute_prediction
from app.services.inference_capacity import manual_inference_slots as _inference_slots

router = APIRouter(prefix="/api/measurements", tags=["predictions"])
auth_router = APIRouter(prefix="/api/prediction-auth", tags=["prediction-auth"])


class OperatorLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


@auth_router.post("/login")
def login(payload: OperatorLogin, request: Request, response: Response):
    return login_operator(request, response, username=payload.username, password=payload.password)


@auth_router.get("/session")
def session_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": operator_session_exists(request)}


@auth_router.post("/logout")
def logout(request: Request, response: Response):
    return logout_operator(request, response)


@router.post("/{measurement_id}/predict")
def predict_measurement(
    request: Request,
    measurement_id: int = Path(gt=0),
    prediction_token: str | None = Header(default=None, alias="X-Prediction-Token"),
):
    if prediction_token is not None:
        # Preserve current server-to-server callers; never put this token in React.
        check_prediction_access(prediction_token)
    else:
        # A browser calls this endpoint with a short-lived HttpOnly cookie.
        require_operator_session(request)
    # Share capacity with Set test upload/replay/retry and historical alert re-inference.
    # Keep authorization outside the capacity slot: bad requests never consume it.
    if not _inference_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "PREDICTION_BUSY",
                "message": "다른 AI 분석이 진행 중입니다. 잠시 후 다시 시도해 주세요.",
            },
            headers={"Retry-After": "30"},
        )
    try:
        return execute_prediction(measurement_id)
    finally:
        _inference_slots.release()
