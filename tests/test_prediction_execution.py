"""Offline tests: no MySQL, Object Storage, MLflow, or inference requests."""

from decimal import Decimal
from unittest.mock import Mock

TEST_CLAIM = "1" * 32

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.predictions import router
from app.services import prediction_execution as prediction


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def token_env(monkeypatch):
    monkeypatch.setenv("PREDICTION_API_ENABLED", "1")
    monkeypatch.setenv("PREDICTION_API_TOKEN", "test-private-token")


def fake_db(measurement=None, prediction_row=None):
    class Conn:
        def __init__(self):
            self.cursor_obj = Mock()
            self.cursor_obj.fetchone.side_effect = [measurement, prediction_row]
            self.cursor_obj.lastrowid = 901
            self.cursor_obj.rowcount = 1
            self.commits = 0
            self.rollbacks = 0

        def cursor(self, dictionary=False):
            assert dictionary
            return self.cursor_obj

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            pass

    return Conn()


def test_disabled_by_default_returns_503_without_touching_db(client, monkeypatch):
    monkeypatch.delenv("PREDICTION_API_ENABLED", raising=False)
    connect = Mock(side_effect=AssertionError("DB must not be accessed"))
    monkeypatch.setattr(prediction, "get_connection", connect)
    response = client.post("/api/measurements/319/predict")
    assert response.status_code == 503
    connect.assert_not_called()


def test_invalid_token_is_denied(client, token_env, monkeypatch):
    connect = Mock(side_effect=AssertionError("DB must not be accessed"))
    monkeypatch.setattr(prediction, "get_connection", connect)
    assert client.post("/api/measurements/319/predict").status_code == 401
    assert client.post("/api/measurements/319/predict", headers={"X-Prediction-Token": "bad"}).status_code == 401
    assert client.post("/api/measurements/-1/predict", headers={"X-Prediction-Token": "test-private-token"}).status_code == 422
    connect.assert_not_called()


def test_claim_missing_or_busy(monkeypatch):
    for record, expected in [
        (None, 404),
        ({"image_path": None, "sensor_path": "s.csv", "status": "ready"}, 422),
        ({"image_path": "a.png", "sensor_path": "s.csv", "status": "predicting"}, 409),
        ({"image_path": "a.png", "sensor_path": "s.csv", "status": "completed"}, 409),
    ]:
        conn = fake_db(record)
        monkeypatch.setattr(prediction, "get_connection", lambda: conn)
        with pytest.raises(prediction.HTTPException) as error:
            prediction.claim_measurement(319)
        assert error.value.status_code == expected
        assert conn.rollbacks == 1
        assert conn.commits == 0


def test_happy_path_writes_model_version_and_alert_once(client, token_env, monkeypatch):
    claim = fake_db({"image_path": "images/set7/original/1.png", "sensor_path": "sensors/set7/2.csv", "status": "ready"})
    persist = fake_db({"status": "predicting", "prediction_claim_id": TEST_CLAIM})
    monkeypatch.setattr(prediction.uuid, "uuid4", lambda: Mock(hex=TEST_CLAIM))
    connections = iter([claim, persist])
    monkeypatch.setattr(prediction, "get_connection", lambda: next(connections))
    model_response = {
        "predicted_wear_um": 173.627,
        "predicted_type": "flank_wear",
        "model_name": "cnc-wearpoint-multitask",
        "model_alias": "candidate",
        "model_version": "1",
        "model_epoch": 10,
        "window_count": 174,
        "sampling_hz": 1642.0,
        "status": "danger",  # Serving's outdated 50/90 status must not be trusted.
    }
    serving = Mock(return_value=model_response)
    monkeypatch.setattr(prediction, "request_serving_prediction", serving)
    response = client.post("/api/measurements/319/predict", headers={"X-Prediction-Token": "test-private-token"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "warning"  # Backend's 150/200 threshold.
    assert data["model_version"] == "1"
    assert data["prediction_id"] == 901
    assert data["warning_threshold_um"] == 150
    assert data["danger_threshold_um"] == 200
    assert claim.commits == persist.commits == 1
    sql = [call.args[0] for call in persist.cursor_obj.execute.call_args_list]
    assert any("INSERT INTO predictions" in s for s in sql)
    assert any("INSERT INTO alerts" in s for s in sql)
    assert any("status = 'completed'" in s for s in sql)
    saved = [call.args[1] for call in persist.cursor_obj.execute.call_args_list if "INSERT INTO predictions" in call.args[0]][0]
    assert saved[4] == "1"
    assert saved[5:] == (Decimal("150"), Decimal("200"), "warning")
    serving.assert_called_once_with("images/set7/original/1.png", "sensors/set7/2.csv")


def test_normal_prediction_does_not_insert_alert(monkeypatch):
    conn = fake_db({"status": "predicting", "prediction_claim_id": TEST_CLAIM})
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    result = prediction.persist_prediction(319, {
        "predicted_wear_um": 30.762261940261066,
        "predicted_type": "flank_wear",
        "model_name": "cnc-wearpoint-multitask",
        "model_version": "1",
    }, TEST_CLAIM)
    assert result["status"] == "normal"
    assert not any("INSERT INTO alerts" in call.args[0] for call in conn.cursor_obj.execute.call_args_list)


def test_missing_registry_version_is_not_persisted(monkeypatch):
    conn = fake_db()
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    with pytest.raises(ValueError, match="Invalid Serving prediction result"):
        prediction.persist_prediction(319, {
            "predicted_wear_um": 30,
            "predicted_type": "flank_wear",
            "model_name": "cnc-wearpoint-multitask",
            "model_alias": "candidate",
        }, TEST_CLAIM)
    assert conn.commits == 0


def test_serving_failure_marks_measurement_failed(client, token_env, monkeypatch):
    claim = fake_db({"image_path": "i.png", "sensor_path": "s.csv", "status": "ready"})
    failure = fake_db()
    connections = iter([claim, failure])
    monkeypatch.setattr(prediction, "get_connection", lambda: next(connections))
    monkeypatch.setattr(prediction, "request_serving_prediction", Mock(side_effect=RuntimeError("Service failed")))
    response = client.post("/api/measurements/319/predict", headers={"X-Prediction-Token": "test-private-token"})
    assert response.status_code == 502
    assert claim.commits == failure.commits == 1
    assert "status = 'failed'" in failure.cursor_obj.execute.call_args.args[0]


def test_bad_response_never_commits_prediction(monkeypatch):
    with pytest.raises(ValueError):
        prediction.validate_model_result({"predicted_wear_um": 10, "predicted_type": "x", "model_name": "cnc-wearpoint-multitask", "model_version": "candidate"})


def test_rounding_before_threshold_check(monkeypatch):
    conn = fake_db({"status": "predicting", "prediction_claim_id": TEST_CLAIM})
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    result = prediction.persist_prediction(319, {
        "predicted_wear_um": "149.999999",
        "predicted_type": "flank_wear",
        "model_name": "cnc-wearpoint-multitask",
        "model_version": 2,
    }, TEST_CLAIM)
    assert result["status"] == "warning"


VALID_RESULT = {
    "predicted_wear_um": 175,
    "predicted_type": "flank_wear",
    "model_name": "cnc-wearpoint-multitask",
    "model_version": "1",
}


def test_claim_existing_prediction_is_blocked(monkeypatch):
    conn = fake_db(
        {"status": "ready", "image_path": "i.png", "sensor_path": "s.csv"},
        {"id": 900},
    )
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    with pytest.raises(prediction.HTTPException) as error:
        prediction.claim_measurement(319)
    assert error.value.status_code == 409
    assert conn.rollbacks == 1
    assert not any("UPDATE measurements" in c.args[0] for c in conn.cursor_obj.execute.call_args_list)


def test_late_worker_claim_is_fenced_before_insert(monkeypatch):
    conn = fake_db({"status": "predicting", "prediction_claim_id": "2" * 32})
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    with pytest.raises(RuntimeError, match="no longer active"):
        prediction.persist_prediction(319, VALID_RESULT, TEST_CLAIM)
    assert conn.rollbacks == 1
    assert not any("INSERT INTO predictions" in c.args[0] for c in conn.cursor_obj.execute.call_args_list)


def test_failed_update_uses_original_claim(monkeypatch):
    conn = fake_db()
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    prediction.mark_measurement_failed(319, TEST_CLAIM)
    sql, params = conn.cursor_obj.execute.call_args.args
    assert "prediction_claim_id = %s" in sql
    assert params == ("Prediction processing failed", 319, TEST_CLAIM)


def recovery_row(*, stale=True, claim=TEST_CLAIM, status="predicting", started=True):
    return {
        "status": status,
        "prediction_claim_id": claim,
        "prediction_started_at": "2026-11-18 10:00:00" if started else None,
        "is_stale": stale,
    }


def test_recovery_inspection_is_read_only(monkeypatch):
    conn = fake_db(recovery_row())
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    result = prediction.inspect_prediction_claim(319)
    assert result["is_stale"] is True
    assert result["has_claim_id"] is True
    assert not any("UPDATE" in c.args[0] for c in conn.cursor_obj.execute.call_args_list)


def test_recovery_stale_claim_releases_only_owned_row(monkeypatch):
    conn = fake_db(recovery_row())
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    result = prediction.recover_stale_prediction(319)
    assert result == {"measurement_id": 319, "status": "failed", "recovered": True}
    assert conn.commits == 1
    assert conn.rollbacks == 0
    sql, params = conn.cursor_obj.execute.call_args.args
    assert "status = 'failed'" in sql
    assert "prediction_claim_id = %s" in sql
    assert params == (319, TEST_CLAIM)


@pytest.mark.parametrize("row", [
    recovery_row(stale=False),
    recovery_row(claim=None),
    recovery_row(started=False),
    recovery_row(status="completed"),
])
def test_recovery_rejects_unsafe_states(monkeypatch, row):
    conn = fake_db(row)
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    with pytest.raises(prediction.HTTPException) as error:
        prediction.recover_stale_prediction(319)
    assert error.value.status_code == 409
    assert conn.rollbacks == 1
    assert not any("UPDATE measurements" in c.args[0] for c in conn.cursor_obj.execute.call_args_list)


def test_recovery_does_not_reset_existing_prediction(monkeypatch):
    conn = fake_db(recovery_row(), {"id": 901})
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    with pytest.raises(prediction.HTTPException) as error:
        prediction.recover_stale_prediction(319)
    assert error.value.status_code == 409
    assert conn.rollbacks == 1
    assert not any("UPDATE measurements" in c.args[0] for c in conn.cursor_obj.execute.call_args_list)


def test_recovery_minimum_age_is_enforced(monkeypatch):
    connect = Mock(side_effect=AssertionError("DB must not be accessed"))
    monkeypatch.setattr(prediction, "get_connection", connect)
    with pytest.raises(ValueError, match="30 minutes"):
        prediction.recover_stale_prediction(319, min_age_minutes=5)
    connect.assert_not_called()


def test_serving_400_is_input_rejected_422_and_marks_failed(client, token_env, monkeypatch):
    claim = fake_db({"image_path": "i.png", "sensor_path": "s.csv", "status": "ready"})
    failure = fake_db()
    connections = iter([claim, failure])
    monkeypatch.setattr(prediction, "get_connection", lambda: next(connections))
    monkeypatch.setattr(prediction, "request_serving_prediction",
                        Mock(side_effect=prediction.ServingInputRejected("유효한 절삭 구간이 없습니다.")))
    response = client.post("/api/measurements/319/predict", headers={"X-Prediction-Token": "test-private-token"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "INPUT_REJECTED"
    assert "유효한 절삭 구간이 없습니다." in detail["message"]
    sql, params = failure.cursor_obj.execute.call_args.args
    assert "status = 'failed'" in sql
    assert params[0] == "Input rejected by model"


def _http_error(code, body):
    import io
    import urllib.error
    return urllib.error.HTTPError("http://serving/predictions", code, "x", {}, io.BytesIO(body))


@pytest.mark.parametrize("code,body,expected", [
    (400, '{"detail": "timestamp 간격이 일정하지 않습니다."}'.encode(), "timestamp 간격이 일정하지 않습니다."),
    (400, b"<html>not json</html>", prediction.INPUT_REJECTED_FALLBACK),
    (400, b'{"detail": [{"loc": "x"}]}', prediction.INPUT_REJECTED_FALLBACK),
])
def test_request_serving_maps_400_to_input_rejected(monkeypatch, code, body, expected):
    monkeypatch.setattr(prediction, "read_input_object", lambda key, limit: b"x")
    monkeypatch.setattr(prediction.urllib.request, "urlopen", Mock(side_effect=_http_error(code, body)))
    with pytest.raises(prediction.ServingInputRejected) as error:
        prediction.request_serving_prediction("a.png", "s.csv")
    assert error.value.reason == expected


def test_request_serving_500_stays_retryable_runtime_error(monkeypatch):
    monkeypatch.setattr(prediction, "read_input_object", lambda key, limit: b"x")
    monkeypatch.setattr(prediction.urllib.request, "urlopen", Mock(side_effect=_http_error(500, b"{}")))
    with pytest.raises(RuntimeError, match="HTTP 500"):
        prediction.request_serving_prediction("a.png", "s.csv")
