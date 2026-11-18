"""Backend -> Object Storage -> Serving -> RDS prediction flow.

All outbound calls and writes happen only after the caller passes the
separate API permission/feature checks. Never hold a DB lock during model I/O.
"""

import json
import logging
import mimetypes
import os
import re
import secrets
import urllib.error
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from fastapi import HTTPException

from app.core.database import get_connection
from app.core.wear_policy import DANGER_UM, WARNING_UM, alert_title, wear_level
from app.services.storage import (
    get_image_path,
    get_object_storage_object,
    normalize_object_key,
    using_object_storage,
)

logger = logging.getLogger(__name__)
MAX_IMAGE = 8 * 1024 * 1024
MAX_SENSOR = 20 * 1024 * 1024
WEAR_PRECISION = Decimal("0.00001")


def check_prediction_access(token: str | None):
    """Fail closed: public POST is unavailable unless configured and authorized."""
    if os.getenv("PREDICTION_API_ENABLED", "0") != "1":
        raise HTTPException(503, "Prediction API is disabled")
    expected = os.getenv("PREDICTION_API_TOKEN", "")
    if not expected:
        raise HTTPException(503, "Prediction API token is not configured")
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(401, "Invalid prediction token")


def _db_operation(operation):
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            result = operation(cursor)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def claim_measurement(measurement_id: int):
    def operation(cursor):
        cursor.execute(
            "SELECT status, image_path, sensor_path FROM measurements "
            "WHERE id = %s FOR UPDATE",
            (measurement_id,),
        )
        measurement = cursor.fetchone()
        if measurement is None:
            raise HTTPException(404, "Measurement not found")
        if not measurement["image_path"] or not measurement["sensor_path"]:
            raise HTTPException(422, "Measurement requires image and sensor CSV")
        if measurement["status"] not in ("ready", "failed"):
            raise HTTPException(409, "Measurement is not ready for prediction")
        cursor.execute(
            "UPDATE measurements SET status = 'predicting', error_message = NULL "
            "WHERE id = %s",
            (measurement_id,),
        )
        return measurement["image_path"], measurement["sensor_path"]

    return _db_operation(operation)


def read_input_object(object_key: str, max_bytes: int) -> bytes:
    key = normalize_object_key(object_key)
    if using_object_storage():
        obj = get_object_storage_object(key)
        body = obj["Body"]
        try:
            if int(obj.get("ContentLength", 0)) > max_bytes:
                raise ValueError("Input file exceeds size limit")
            data = body.read(max_bytes + 1)
        finally:
            body.close()
    else:
        path = get_image_path(key)
        if path.stat().st_size > max_bytes:
            raise ValueError("Input file exceeds size limit")
        with path.open("rb") as f:
            data = f.read(max_bytes + 1)
    if not data or len(data) > max_bytes:
        raise ValueError("Input file is empty or too large")
    return data


def _multipart_file(boundary: str, name: str, filename: str, data: bytes) -> bytes:
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    # Use a fixed field name; strip unsafe user-controlled filename characters.
    safe_filename = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(filename).name)
    return (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
        f'filename="{safe_filename}"\r\nContent-Type: {content_type}\r\n\r\n'
    ).encode("ascii") + data + b"\r\n"


def request_serving_prediction(image_key: str, sensor_key: str) -> dict:
    if Path(image_key).suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise ValueError("Unsupported image type")
    if Path(sensor_key).suffix.lower() != ".csv":
        raise ValueError("Unsupported sensor type")
    image = read_input_object(image_key, MAX_IMAGE)
    sensor = read_input_object(sensor_key, MAX_SENSOR)
    boundary = "cnc-wp-" + uuid.uuid4().hex
    body = (
        _multipart_file(boundary, "image", Path(image_key).name, image)
        + _multipart_file(boundary, "sensor_csv", Path(sensor_key).name, sensor)
        + f"--{boundary}--\r\n".encode("ascii")
    )
    base_url = os.getenv("SERVING_URL", "http://cnc-wearpoint-serving:8001")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/predictions",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            if response.status != 200:
                raise RuntimeError("Serving returned an unexpected HTTP status")
            result = json.loads(response.read(64 * 1024))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Serving returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Serving is unavailable") from exc
    if not isinstance(result, dict):
        raise ValueError("Serving response is not a JSON object")
    return result


def validate_model_result(result: dict):
    try:
        wear = Decimal(str(result["predicted_wear_um"]))
        if not wear.is_finite() or not 0 <= wear < Decimal("10000000"):
            raise ValueError("Invalid predicted wear")
        wear = wear.quantize(WEAR_PRECISION, rounding=ROUND_HALF_UP)
        if wear >= Decimal("10000000"):
            raise ValueError("Predicted wear exceeds database precision")
        model_version = str(result["model_version"])
        if not re.fullmatch(r"[1-9][0-9]*", model_version):
            raise ValueError("Missing fixed MLflow Registry model version")
        model_name = str(result["model_name"])
        if not model_name or len(model_name) > 100:
            raise ValueError("Invalid model name")
        expected_model = os.getenv("PREDICTION_MODEL_NAME", "cnc-wearpoint-multitask")
        if model_name != expected_model:
            raise ValueError("Unexpected model name")
        wear_type = str(result["predicted_type"])
        if not wear_type or len(wear_type) > 100:
            raise ValueError("Invalid predicted wear type")
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid Serving prediction result") from exc
    status = wear_level(wear)  # Do NOT use Serving's outdated 50/90 thresholds.
    return wear, wear_type, model_name, model_version, status


def persist_prediction(measurement_id: int, result: dict) -> dict:
    wear, wear_type, model_name, model_version, status = validate_model_result(result)

    def operation(cursor):
        cursor.execute(
            "INSERT INTO predictions (measurement_id, predicted_wear_um, "
            "predicted_type, model_name, model_version, "
            "warning_threshold_um, danger_threshold_um, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (measurement_id, wear, wear_type, model_name, model_version,
             WARNING_UM, DANGER_UM, status),
        )
        prediction_id = cursor.lastrowid
        if status in ("warning", "danger"):
            message = f"{alert_title(status, wear_type)} ({wear:.2f} μm)"
            cursor.execute(
                "INSERT INTO alerts (prediction_id, level, message) VALUES (%s, %s, %s)",
                (prediction_id, status, message),
            )
        cursor.execute(
            "UPDATE measurements SET status = 'completed', error_message = NULL "
            "WHERE id = %s AND status = 'predicting'",
            (measurement_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Measurement state changed during prediction")
        return {
            "measurement_id": measurement_id,
            "prediction_id": prediction_id,
            "predicted_wear_um": float(wear),
            "predicted_type": wear_type,
            "status": status,
            "warning_threshold_um": float(WARNING_UM),
            "danger_threshold_um": float(DANGER_UM),
            "model_name": model_name,
            "model_version": model_version,
            "model_alias": result.get("model_alias"),
            "flank_wear_probability": result.get("flank_wear_probability"),
            "model_epoch": result.get("model_epoch"),
            "window_count": result.get("window_count"),
            "sampling_hz": result.get("sampling_hz"),
        }

    return _db_operation(operation)


def mark_measurement_failed(measurement_id: int):
    def operation(cursor):
        cursor.execute(
            "UPDATE measurements SET status = 'failed', "
            "error_message = 'Prediction processing failed' "
            "WHERE id = %s AND status = 'predicting'",
            (measurement_id,),
        )
    _db_operation(operation)


def execute_prediction(measurement_id: int) -> dict:
    image_key, sensor_key = claim_measurement(measurement_id)
    try:
        result = request_serving_prediction(image_key, sensor_key)
        return persist_prediction(measurement_id, result)
    except Exception:
        logger.exception("Prediction failed (measurement_id=%d)", measurement_id)
        try:
            mark_measurement_failed(measurement_id)
        except Exception:
            logger.exception("Unable to mark failed (measurement_id=%d)", measurement_id)
        raise HTTPException(502, "Prediction failed") from None
