"""Model prediction: private server token OR HTTPS HttpOnly operator session."""

from fastapi import APIRouter, Header, Path, Request, Response
from pydantic import BaseModel, Field

from app.core.prediction_session import (
    login_operator, logout_operator, operator_session_exists, require_operator_session,
)
from app.services.prediction_execution import check_prediction_access, execute_prediction

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
    return execute_prediction(measurement_id)
