"""Fast, no-network unit checks for the opt-in historical re-inference API."""
import asyncio
import threading

import pytest
from fastapi import HTTPException

from app.api.routers import historical_reinfer as subject


def run(coro):
    return asyncio.run(coro)


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HISTORICAL_REINFER_ENABLED", raising=False)
    with pytest.raises(HTTPException) as info:
        run(subject.reinfer_saved_alert(object(), "monitoring:123"))
    assert info.value.status_code == 503


def _allow(monkeypatch):
    monkeypatch.setenv("HISTORICAL_REINFER_ENABLED", "1")
    monkeypatch.setattr(subject, "_authorize_auto_prediction", lambda request: None)
    monkeypatch.setattr(subject, "_load_target", lambda number: {
        "measurement_id": 77, "set_number": 5, "inference_run_id": "saved-run",
    })
    monkeypatch.setattr(subject, "manual_inference_slots", threading.BoundedSemaphore(1))


def test_validates_alert_kind_before_any_inference(monkeypatch):
    _allow(monkeypatch)
    for invalid in ("legacy:2", "monitoring:0", "monitoring:1/../../2", "abc"):
        with pytest.raises(HTTPException) as error:
            run(subject.reinfer_saved_alert(object(), invalid))
        assert error.value.status_code == 400


def test_manual_busy_rejects_without_running_model(monkeypatch):
    _allow(monkeypatch)
    slot = subject.manual_inference_slots
    assert slot.acquire(blocking=False)
    monkeypatch.setattr(subject, "_infer_once", lambda target: pytest.fail("model must not run"))
    try:
        with pytest.raises(HTTPException) as error:
            run(subject.reinfer_saved_alert(object(), "monitoring:123"))
        assert error.value.status_code == 429
    finally:
        slot.release()


def test_success_releases_manual_slot(monkeypatch):
    _allow(monkeypatch)
    monkeypatch.setattr(subject, "_infer_once", lambda target: {
        "predicted_wear_um": 183.4, "wear_status": "warning", "persisted": False,
    })
    value = run(subject.reinfer_saved_alert(object(), "monitoring:123"))
    assert value["alert_id"] == "monitoring:123"
    assert value["prediction"]["persisted"] is False
    assert value["prediction"]["predicted_wear_um"] == 183.4
    assert subject.manual_inference_slots.acquire(blocking=False)
    subject.manual_inference_slots.release()


def test_serving_error_still_releases_manual_slot(monkeypatch):
    _allow(monkeypatch)
    def broken(target):
        raise RuntimeError("Serving failed")
    monkeypatch.setattr(subject, "_infer_once", broken)
    with pytest.raises(RuntimeError, match="Serving failed"):
        run(subject.reinfer_saved_alert(object(), "monitoring:123"))
    assert subject.manual_inference_slots.acquire(blocking=False)
    subject.manual_inference_slots.release()


def test_infer_only_uses_server_resolved_keys(monkeypatch):
    target = {"measurement_id": 77, "set_number": 5, "inference_run_id": "saved-run"}
    calls = []
    def keys(record):
        calls.append(("keys", record))
        return "images/set5/original/x.jpg", "sensors/set5/x.csv"
    def serving(img, csv):
        calls.append(("serving", img, csv))
        return {"output": "sample"}
    monkeypatch.setattr(subject, "_keys", keys)
    monkeypatch.setattr(subject, "request_serving_prediction", serving)
    monkeypatch.setattr(subject, "validate_model_result", lambda raw: (183.4, "flank", "model", "3", "warning"))
    result = subject._infer_once(target)
    assert calls == [("keys", {"set_number": 5, "measurement_id": 77}),
                     ("serving", "images/set5/original/x.jpg", "sensors/set5/x.csv")]
    assert result["reference_inference_run_id"] == "saved-run"
    assert result["persisted"] is False


def test_load_target_is_read_only_and_fenced_to_current_session(monkeypatch):
    from contextlib import contextmanager
    calls = []
    expected = {"measurement_id": 77, "set_number": 5,
                "inference_run_id": "record-run"}
    class Cursor:
        def execute(self, sql, params):
            calls.append((sql, params))
            assert sql.strip().upper().startswith("SELECT")
        def fetchone(self):
            return expected
    @contextmanager
    def fake_cursor():
        yield Cursor()
    monkeypatch.setattr(subject, "monitoring_cursor", fake_cursor)
    monkeypatch.setattr(subject, "read_state", lambda cursor: {"session_id": "current-session"})
    assert subject._load_target(123) is expected
    assert calls[0][1] == (123, "current-session")
    assert "r.status = 'completed'" in calls[0][0]
    assert "r.playback_generation = e.playback_generation" in calls[0][0]
    assert "e.inference_run_id IS NOT NULL" in calls[0][0]
