"""Login-free same-origin demo inference and narrowly scoped, cookie-based retry.

The browser never sees or transmits the shared PREDICTION_API_TOKEN. Each failed
upload instead gets a time-limited HttpOnly capability cookie for that one row.
Origin checking and HMAC cookies are not general public-API abuse prevention:
configure IP-based Nginx limits before enabling this anonymous API.
"""

import hashlib
import hmac
import os
import time
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from fastapi import APIRouter, File, HTTPException, Path, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.api.routers.measurements import create_measurement
from app.services.prediction_execution import execute_prediction

router = APIRouter(prefix="/api/measurements", tags=["auto-prediction"])

# In-process cap, not a distributed rate limit. Also configure Nginx limits.
_inference_slots = BoundedSemaphore(1)
_RETRY_TTL_SECONDS = 3600


def _authorize_auto_prediction(request: Request) -> None:
    if (
        os.getenv("AUTO_PREDICTION_ENABLED", "0") != "1"
        or os.getenv("PREDICTION_API_ENABLED", "0") != "1"
    ):
        raise HTTPException(503, "Automatic prediction is disabled")

    origin = os.getenv("AUTO_PREDICTION_ORIGIN", "")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or origin != f"https://{parsed.netloc}"
    ):
        raise HTTPException(503, "Automatic prediction origin is not configured")

    # Origin/Host protects browsers from cross-site POST, not forged curl requests.
    if (
        request.headers.get("origin") != origin
        or request.headers.get("host") != parsed.netloc
    ):
        raise HTTPException(403, "Automatic prediction origin is not allowed")


def _retry_signing_key() -> bytes:
    # Domain-separate the HMAC key from the server-to-server API token.
    # Never send this shared secret or derived signing key to the browser.
    private_token = os.getenv("PREDICTION_API_TOKEN", "")
    if len(private_token) < 32:
        raise HTTPException(503, "Automatic prediction retry is not configured")
    return hmac.new(
        private_token.encode("utf-8"), b"cnc-wp-auto-retry-v1", hashlib.sha256
    ).digest()


def _cookie_name(measurement_id: int) -> str:
    return f"__Host-cnc_wp_retry_{measurement_id}"


def _retry_capability(measurement_id: int) -> str:
    expires = int(time.time()) + _RETRY_TTL_SECONDS
    data = f"v1:{measurement_id}:{expires}"
    signature = hmac.new(_retry_signing_key(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}:{signature}"


def _has_retry_capability(request: Request, measurement_id: int) -> bool:
    value = request.cookies.get(_cookie_name(measurement_id), "")
    if len(value) > 256:
        return False
    try:
        version, row_id, expiry, signature = value.split(":")
        now = int(time.time())
        if (
            version != "v1"
            or str(measurement_id) != row_id
            or not expiry.isdecimal()
            or not (now < int(expiry) <= now + _RETRY_TTL_SECONDS)
            or len(signature) != 64
        ):
            return False
        message = f"{version}:{row_id}:{expiry}"
        expected = hmac.new(
            _retry_signing_key(), message.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


def _allow_retry(response: JSONResponse, measurement_id: int) -> None:
    response.set_cookie(
        key=_cookie_name(measurement_id),
        value=_retry_capability(measurement_id),
        max_age=_RETRY_TTL_SECONDS,
        path="/",  # Required by the __Host- prefix.
        secure=True,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"


def _error_body(code: str, message: str, measurement_id: int | None = None) -> dict:
    data = {"code": code, "message": message}
    if measurement_id is not None:
        data["measurement_id"] = measurement_id
    return {"detail": data}


def _busy() -> HTTPException:
    return HTTPException(
        429,
        _error_body("PREDICTION_BUSY", "다른 AI 분석이 진행 중입니다. 잠시 후 다시 시도해 주세요.")["detail"],
        headers={"Retry-After": "30"},
    )


@router.post("/auto-predict", status_code=201)
async def auto_predict(
    request: Request,
    image: UploadFile = File(...),
    sensor_csv: UploadFile = File(...),
):
    """Save inputs, execute Serving inference, persist prediction in one request."""
    _authorize_auto_prediction(request)
    _retry_signing_key()  # Fail closed before any Object Storage / RDS write.

    if not _inference_slots.acquire(blocking=False):
        raise _busy()

    try:
        measurement = await create_measurement(image=image, sensor_csv=sensor_csv)
        measurement_id = measurement["measurement_id"]
        try:
            prediction = await run_in_threadpool(execute_prediction, measurement_id)
        except HTTPException as exc:
            if exc.status_code != 502:
                raise
            # The upload already committed. The retry endpoint still verifies
            # that its DB state is `failed`, preventing reset of active claims.
            response = JSONResponse(
                status_code=502,
                content=_error_body(
                    "INFERENCE_FAILED",
                    "파일은 저장됐지만 AI 분석에 실패했습니다. 재추론을 시도할 수 있습니다.",
                    measurement_id,
                ),
            )
            _allow_retry(response, measurement_id)
            return response

        return {
            "measurement_id": measurement_id,
            "measurement_status": "completed",
            "prediction": prediction,
        }
    finally:
        _inference_slots.release()


@router.post("/{measurement_id}/retry")
async def retry_auto_prediction(
    request: Request,
    measurement_id: int = Path(gt=0),
):
    """Retry one failed upload using its existing Object Storage files and DB row.

    The browser's HttpOnly capability is upload-specific, expires after one
    hour, and is not the private server-wide PREDICTION_API_TOKEN.
    """
    _authorize_auto_prediction(request)
    if not _has_retry_capability(request, measurement_id):
        raise HTTPException(403, "재추론 권한이 없거나 만료됐습니다. 파일을 다시 업로드해 주세요.")
    if not _inference_slots.acquire(blocking=False):
        raise _busy()

    try:
        try:
            prediction = await run_in_threadpool(execute_prediction, measurement_id)
        except HTTPException as exc:
            if exc.status_code == 409:
                raise HTTPException(409, "이미 분석 중이거나 완료된 데이터는 재추론할 수 없습니다.") from exc
            if exc.status_code != 502:
                raise
            response = JSONResponse(
                status_code=502,
                content=_error_body(
                    "INFERENCE_FAILED",
                    "재추론에 실패했습니다. 잠시 후 다시 시도할 수 있습니다.",
                    measurement_id,
                ),
            )
            response.headers["Cache-Control"] = "no-store"
            return response

        response = JSONResponse(
            status_code=200,
            content={
                "measurement_id": measurement_id,
                "measurement_status": "completed",
                "prediction": prediction,
            },
        )
        response.delete_cookie(_cookie_name(measurement_id), path="/", secure=True, httponly=True, samesite="strict")
        response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        _inference_slots.release()
