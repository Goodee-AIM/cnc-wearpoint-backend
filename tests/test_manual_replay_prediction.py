from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from app.services import manual_replay_prediction as replay


def make_conn(source="upload", status="completed", image="images/uploads/some/original.png", sensor="sensors/uploads/some/sensor.csv"):
    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.fetchone.return_value = {"source_type": source, "status": status, "image_path": image, "sensor_path": sensor}
    cur.lastrowid = 991
    return conn


def test_replay_twice_reuses_storage_inputs_but_inserts_new_prediction_each_time(monkeypatch):
    connections = [make_conn() for _ in range(4)]
    remaining = iter(connections)
    monkeypatch.setattr(replay, "get_connection", lambda: next(remaining))
    calls = []
    def serving(image_key, sensor_key):
        calls.append((image_key, sensor_key))
        return {"predicted_wear_um": 175, "predicted_type": "flank", "model_name": "model", "model_version": "1"}
    monkeypatch.setattr(replay, "request_serving_prediction", serving)
    monkeypatch.setattr(replay, "validate_model_result", lambda _: (Decimal("175"), "flank", "model", "1", "warning"))
    out1 = replay.execute_manual_replay_prediction(920)
    out2 = replay.execute_manual_replay_prediction(920)
    assert out1["measurement_id"] == out2["measurement_id"] == 920
    assert out1["warning_threshold_um"] == 150
    assert out1["danger_threshold_um"] == 200
    assert len(calls) == 2 and calls[0] == calls[1]
    # Each time a fresh INSERT; original measurement and previous predictions untouched.
    for db in (connections[1], connections[3]):
        statements = [call.args[0] for call in db.cursor.return_value.execute.call_args_list]
        assert sum(sql.startswith("INSERT INTO predictions") for sql in statements) == 1
        assert not any("UPDATE measurements" in sql or "UPDATE predictions" in sql for sql in statements)
        db.commit.assert_called_once()
    assert out1["status"] == out2["status"] == "warning"


def test_reject_dataset_or_incomplete_upload_without_serving(monkeypatch):
    for source, status, http_status in [("dataset", "completed", 403), ("upload", "failed", 409)]:
        monkeypatch.setattr(replay, "get_connection", lambda: make_conn(source, status))
        monkeypatch.setattr(replay, "request_serving_prediction", lambda *_: pytest.fail("must not call Serving"))
        with pytest.raises(HTTPException) as e:
            replay.execute_manual_replay_prediction(920)
        assert e.value.status_code == http_status


def test_changed_pair_fails_before_write(monkeypatch):
    connections = iter([make_conn(), make_conn(image="different.png")])
    monkeypatch.setattr(replay, "get_connection", lambda: next(connections))
    monkeypatch.setattr(replay, "request_serving_prediction", lambda *_: {})
    monkeypatch.setattr(replay, "validate_model_result", lambda _: (Decimal("0"), "flank", "model", "1", "normal"))
    with pytest.raises(HTTPException) as e:
        replay.execute_manual_replay_prediction(920)
    assert e.value.status_code == 409
