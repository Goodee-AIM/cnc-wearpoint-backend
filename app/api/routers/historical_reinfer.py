"""Opt-in, read-only Serving re-inference of one saved monitoring alert.

Does not modify monitoring playback, prediction records, or alert history.
Uses the same process-local slot as Set test. Configure shared reverse-proxy
rate limits and a single backend process (or add distributed slot control)
before production rollout.
"""

import os
import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Path, Request
from starlette.concurrency import run_in_threadpool

from app.api.routers.auto_prediction import _authorize_auto_prediction
from app.api.routers.monitoring import monitoring_cursor, read_state
from app.services.inference_capacity import manual_inference_slots
from app.services.monitoring_inference_queue import _keys
from app.services.prediction_execution import (
    request_serving_prediction, validate_model_result,
)

router = APIRouter(prefix="/api/monitoring/alerts", tags=["historical-reinfer"])


def _load_target(alert_number: int):
    """Resolve a CURRENT-session, completed AI inference alert by server-side ID.

    The browser cannot pick a measurement_id or Object Storage key. SQL is
    SELECT-only; the original inference occurrence must match this alert.
    """
    with monitoring_cursor() as cursor:
        session = read_state(cursor)["session_id"]
        if not session:
            raise HTTPException(409, "Monitoring session unavailable")
        cursor.execute(
            """
            SELECT e.measurement_id, e.set_number, e.image_name, e.sensor_name,
                   e.inference_run_id
            FROM monitoring_alert_events AS e
            JOIN monitoring_inference_runs AS r
              ON r.run_id = e.inference_run_id
             AND r.session_id = e.session_id
             AND r.measurement_id = e.measurement_id
             AND r.set_number = e.set_number
             AND r.playback_generation = e.playback_generation
             AND r.cycle_number = e.cycle_number
             AND r.position = e.position
             AND r.status = 'completed'
            WHERE e.id = %s AND e.session_id = %s
              AND e.source = 'prediction' AND e.inference_run_id IS NOT NULL
            """,
            (alert_number, session),
        )
        record = cursor.fetchone()
    if record is None:
        raise HTTPException(404, "This session has no completed AI-inference alert with that ID")
    return record


def _infer_once(target):
    image_key, sensor_key = _keys({
        "set_number": target["set_number"],
        "measurement_id": target["measurement_id"],
    })
    raw = request_serving_prediction(image_key, sensor_key)
    wear, wear_type, model, version, level = validate_model_result(raw)
    return {
        "request_id": str(uuid4()),
        "reference_inference_run_id": target["inference_run_id"],
        "measurement_id": target["measurement_id"],
        "set_number": target["set_number"],
        "predicted_wear_um": float(wear),
        "predicted_type": wear_type,
        "wear_status": level,
        "model_name": model,
        "model_version": version,
        "persisted": False,
    }


@router.post("/{record_id}/re-infer")
async def reinfer_saved_alert(request: Request, record_id: str = Path()):
    """One isolated Serving call for a user-selected inference alert.

    Slot is shared with manual upload/retry/replay. 429 when occupied; never
    start unbounded work. Does not replay or restart a shared monitoring set.
    """
    if os.getenv("HISTORICAL_REINFER_ENABLED", "0") != "1":
        raise HTTPException(503, "Historical re-inference is disabled")
    _authorize_auto_prediction(request)
    match = re.fullmatch(r"monitoring:([1-9][0-9]*)", record_id)
    if not match:
        raise HTTPException(400, "Only saved monitoring-inference alerts can be re-inferred")
    target = _load_target(int(match.group(1)))
    if not manual_inference_slots.acquire(blocking=False):
        raise HTTPException(429, "Manual/Set test inference is busy; retry later")
    try:
        result = await run_in_threadpool(_infer_once, target)
        return {"alert_id": record_id, "prediction": result}
    finally:
        manual_inference_slots.release()
