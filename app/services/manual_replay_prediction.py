"""Repeat an existing Set test upload without re-uploading or rewriting its row.

New predictions are appended to `predictions` (already one-to-many by schema).
The original `measurements` row and previous prediction/alert rows are unchanged.
"""
import logging

from fastapi import HTTPException

from app.core.database import get_connection
from app.core.wear_policy import WARNING_UM, DANGER_UM
from app.services.prediction_execution import request_serving_prediction, validate_model_result

logger = logging.getLogger(__name__)


def _read_uploaded_measurement(measurement_id):
    conn = get_connection()
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT source_type, status, image_path, sensor_path "
            "FROM measurements WHERE id = %s", (measurement_id,)
        )
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(404, "Measurement not found")
        if row["source_type"] != "upload":
            raise HTTPException(403, "Only uploaded Set test measurements can be replayed")
        if row["status"] != "completed":
            raise HTTPException(409, "Uploaded measurement has not completed its first inference")
        if not row["image_path"] or not row["sensor_path"]:
            raise HTTPException(422, "Uploaded measurement requires both files")
        return row["image_path"], row["sensor_path"]
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()


def _save_replay(measurement_id, image_key, sensor_key, raw):
    wear, wear_type, model, version, level = validate_model_result(raw)
    conn = get_connection()
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        # A target row must still refer to the exact same uploaded pair.
        cursor.execute(
            "SELECT source_type, status, image_path, sensor_path "
            "FROM measurements WHERE id = %s FOR SHARE", (measurement_id,)
        )
        row = cursor.fetchone()
        if (row is None or row["source_type"] != "upload" or row["status"] != "completed"
                or row["image_path"] != image_key or row["sensor_path"] != sensor_key):
            raise HTTPException(409, "Uploaded input changed during inference")
        cursor.execute(
            "INSERT INTO predictions (measurement_id, predicted_wear_um, predicted_type, "
            "model_name, model_version, warning_threshold_um, danger_threshold_um, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (measurement_id, wear, wear_type, model, version, WARNING_UM, DANGER_UM, level),
        )
        prediction_id = cursor.lastrowid
        conn.commit()
        return {
            "measurement_id": measurement_id,
            "prediction_id": prediction_id,
            "predicted_wear_um": float(wear),
            "predicted_type": wear_type,
            "status": level,
            "warning_threshold_um": float(WARNING_UM),
            "danger_threshold_um": float(DANGER_UM),
            "model_name": model,
            "model_version": version,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()


def execute_manual_replay_prediction(measurement_id: int):
    """Re-run Serving on saved Object Storage keys; append a NEW prediction row.

    This is not `execute_prediction`, whose claim prevents repeat inference.
    """
    try:
        image_key, sensor_key = _read_uploaded_measurement(measurement_id)
        result = request_serving_prediction(image_key, sensor_key)
        return _save_replay(measurement_id, image_key, sensor_key, result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Set test replay inference failed (measurement_id=%s)", measurement_id)
        raise HTTPException(502, "Set test replay prediction failed") from None
