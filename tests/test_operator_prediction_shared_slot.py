"""Pure offline API regression tests for shared manual inference capacity.

No RDS / Object Storage / Serving calls. Uses the existing FastAPI TestClient.
"""
from unittest.mock import Mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.routers import predictions
from app.services import inference_capacity


def _client():
    app = FastAPI()
    app.include_router(predictions.router)
    return TestClient(app)


def _authorize(monkeypatch):
    def check(token):
        if token != "test-private-token":
            raise HTTPException(401, "Bad token")
    monkeypatch.setattr(predictions, "check_prediction_access", check)


def test_operator_endpoint_uses_same_manual_slot_as_set_test():
    from app.api.routers import auto_prediction
    assert predictions._inference_slots is inference_capacity.manual_inference_slots
    assert predictions._inference_slots is auto_prediction._inference_slots
    assert predictions._inference_slots is not inference_capacity.monitoring_inference_slots


def test_success_releases_manual_slot(monkeypatch):
    _authorize(monkeypatch)
    serving = Mock(return_value={"measurement_id": 42, "status": "completed"})
    monkeypatch.setattr(predictions, "execute_prediction", serving)
    slot = inference_capacity.manual_inference_slots
    with _client() as client:
        response = client.post("/api/measurements/42/predict", headers={"X-Prediction-Token": "test-private-token"})
    assert response.status_code == 200
    assert response.json()["measurement_id"] == 42
    serving.assert_called_once_with(42)
    assert slot.acquire(blocking=False)
    slot.release()


def test_busy_slot_returns_429_without_serving_call(monkeypatch):
    _authorize(monkeypatch)
    serving = Mock(side_effect=AssertionError("Serving must not run"))
    monkeypatch.setattr(predictions, "execute_prediction", serving)
    slot = inference_capacity.manual_inference_slots
    assert slot.acquire(blocking=False)
    try:
        with _client() as client:
            response = client.post("/api/measurements/42/predict", headers={"X-Prediction-Token": "test-private-token"})
        assert response.status_code == 429
        assert response.json()["detail"]["code"] == "PREDICTION_BUSY"
        assert response.headers.get("retry-after") == "30"
        serving.assert_not_called()
    finally:
        slot.release()


def test_exception_still_releases_manual_slot(monkeypatch):
    _authorize(monkeypatch)
    monkeypatch.setattr(predictions, "execute_prediction", Mock(side_effect=HTTPException(502, "Serving failed")))
    slot = inference_capacity.manual_inference_slots
    with _client() as client:
        response = client.post("/api/measurements/42/predict", headers={"X-Prediction-Token": "test-private-token"})
    assert response.status_code == 502
    assert slot.acquire(blocking=False)
    slot.release()


def test_invalid_token_cannot_consume_capacity(monkeypatch):
    _authorize(monkeypatch)
    serving = Mock(side_effect=AssertionError("Serving must not run"))
    monkeypatch.setattr(predictions, "execute_prediction", serving)
    slot = inference_capacity.manual_inference_slots
    with _client() as client:
        response = client.post("/api/measurements/42/predict", headers={"X-Prediction-Token": "wrong"})
    assert response.status_code == 401
    serving.assert_not_called()
    assert slot.acquire(blocking=False)
    slot.release()
