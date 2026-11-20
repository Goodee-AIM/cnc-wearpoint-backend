"""Offline Backend <-> Serving model contract tests (V1 / V2 versions).

No MySQL, Object Storage, MLflow or Serving requests. Complements
tests/test_prediction_execution.py, which already covers: version '1' happy
path, missing model_version, model_version 'candidate', int version 2 rounding.
"""

from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pytest

from app.services import manual_replay_prediction as replay
from app.services import monitoring_inference_queue as queue
from app.services import prediction_execution as prediction

CLAIM = "2" * 32
MODEL = "cnc-wearpoint-multitask"


def result(**overrides):
    base = {
        "predicted_wear_um": 120.5,
        "predicted_type": "flank_wear",
        "model_name": MODEL,
        "model_alias": "candidate",
        "model_version": "1",
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def fake_db(measurement=None, prediction_row=None):
    class Conn:
        def __init__(self):
            self.cursor_obj = Mock()
            self.cursor_obj.fetchone.side_effect = [measurement, prediction_row]
            self.cursor_obj.lastrowid = 902
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


@pytest.fixture(autouse=True)
def default_model_name(monkeypatch):
    monkeypatch.delenv("PREDICTION_MODEL_NAME", raising=False)


@pytest.mark.parametrize("version", ["1", "2", 2, "10"])
def test_registry_versions_are_accepted_for_expected_model(version):
    wear, wear_type, name, out_version, status = prediction.validate_model_result(
        result(model_version=version))
    assert name == MODEL
    assert out_version == str(version)
    assert wear == Decimal("120.50000")
    assert status == "normal"


@pytest.mark.parametrize("alias", ["candidate", "candidate-opt", None, "anything"])
def test_model_alias_is_not_validated(alias):
    _, _, _, version, _ = prediction.validate_model_result(
        result(model_version="2", model_alias=alias))
    assert version == "2"


@pytest.mark.parametrize("version", ["0", "02", "2.0", "-1", "", " 2", "candidate-opt",
                                     "v2", "models:/cnc-wearpoint-multitask/2", None])
def test_bad_version_strings_are_rejected(version):
    payload = result()
    payload["model_version"] = version
    with pytest.raises(ValueError):
        prediction.validate_model_result(payload)


@pytest.mark.parametrize("name", ["cnc-wearpoint-multitask-lifecycle-test",
                                  "cnc-wearpoint-regressor-lifecycle-test", "rf-csv-demo",
                                  "CNC-WEARPOINT-MULTITASK"])
def test_unexpected_model_name_is_rejected(name):
    with pytest.raises(ValueError, match="Unexpected model name"):
        prediction.validate_model_result(result(model_name=name, model_version="2"))


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_invalid_model_name_is_rejected(name):
    with pytest.raises(ValueError, match="Invalid model name"):
        prediction.validate_model_result(result(model_name=name))


def test_prediction_model_name_env_overrides_expected_name(monkeypatch):
    monkeypatch.setenv("PREDICTION_MODEL_NAME", "cnc-wearpoint-multitask-lifecycle-test")
    _, _, name, version, _ = prediction.validate_model_result(
        result(model_name="cnc-wearpoint-multitask-lifecycle-test", model_version="2"))
    assert (name, version) == ("cnc-wearpoint-multitask-lifecycle-test", "2")
    with pytest.raises(ValueError, match="Unexpected model name"):
        prediction.validate_model_result(result())


@pytest.mark.parametrize("missing", ["predicted_wear_um", "predicted_type", "model_name"])
def test_missing_required_fields_are_rejected(missing):
    payload = result(model_version="2")
    del payload[missing]
    with pytest.raises(ValueError, match="Invalid Serving prediction result"):
        prediction.validate_model_result(payload)


@pytest.mark.parametrize("wear", ["nan", "inf", -1, 10_000_000, "abc"])
def test_invalid_wear_values_are_rejected(wear):
    with pytest.raises(ValueError):
        prediction.validate_model_result(result(predicted_wear_um=wear, model_version="2"))


def test_persist_prediction_stores_v2_name_and_version_but_not_alias(monkeypatch):
    conn = fake_db({"status": "predicting", "prediction_claim_id": CLAIM})
    monkeypatch.setattr(prediction, "get_connection", lambda: conn)
    out = prediction.persist_prediction(
        501, result(model_version="2", model_alias="candidate-opt", predicted_wear_um=160), CLAIM)
    insert = [c.args for c in conn.cursor_obj.execute.call_args_list
              if "INSERT INTO predictions" in c.args[0]]
    assert len(insert) == 1
    sql, params = insert[0]
    assert "model_alias" not in sql
    assert params[0] == 501
    assert params[3:5] == (MODEL, "2")
    assert "candidate-opt" not in params
    assert out["model_version"] == "2"
    assert out["model_alias"] == "candidate-opt"  # echoed to client only
    assert conn.commits == 1


def test_persist_prediction_rejects_wrong_model_before_db_access(monkeypatch):
    connect = Mock(side_effect=AssertionError("DB must not be accessed"))
    monkeypatch.setattr(prediction, "get_connection", connect)
    with pytest.raises(ValueError, match="Unexpected model name"):
        prediction.persist_prediction(501, result(model_name="other", model_version="2"), CLAIM)
    connect.assert_not_called()


def test_manual_replay_rows_carry_version_per_replay(monkeypatch):
    image, sensor = "images/uploads/a/original.png", "sensors/uploads/a/sensor.csv"
    conns = []

    def connect():
        conn = MagicMock()
        conn.cursor.return_value.fetchone.return_value = {
            "source_type": "upload", "status": "completed",
            "image_path": image, "sensor_path": sensor}
        conn.cursor.return_value.lastrowid = 990 + len(conns)
        conns.append(conn)
        return conn

    monkeypatch.setattr(replay, "get_connection", connect)
    out1 = replay._save_replay(77, image, sensor, result(model_version="1"))
    out2 = replay._save_replay(77, image, sensor, result(model_version="2",
                                                         model_alias="candidate-opt"))
    assert (out1["model_version"], out2["model_version"]) == ("1", "2")
    saved = []
    for conn in conns:
        for call in conn.cursor.return_value.execute.call_args_list:
            if call.args[0].startswith("INSERT INTO predictions"):
                assert "model_alias" not in call.args[0]
                saved.append(call.args[1][3:5])
    assert saved == [(MODEL, "1"), (MODEL, "2")]


def test_manual_replay_rejects_bad_version_and_wrong_model_before_db_access(monkeypatch):
    connect = Mock(side_effect=AssertionError("DB must not be accessed"))
    monkeypatch.setattr(replay, "get_connection", connect)
    with pytest.raises(ValueError, match="Missing fixed MLflow Registry model version"):
        replay._save_replay(77, "i.png", "s.csv", result(model_version="candidate-opt"))
    with pytest.raises(ValueError, match="Unexpected model name"):
        replay._save_replay(77, "i.png", "s.csv", result(model_name="other", model_version="2"))
    connect.assert_not_called()


def test_monitoring_completion_stores_validated_name_and_version(monkeypatch):
    monkeypatch.setattr(queue, "_snapshot", lambda cursor: ({}, {}))
    monkeypatch.setattr(queue, "matching_run", lambda identity, row: True)
    executed = []

    class Cursor:
        rowcount = 1

        def execute(self, sql, params):
            executed.append((sql, params))

    monkeypatch.setattr(queue, "_transaction", lambda fn: fn(Cursor()))
    row = {"run_id": "run-v2", "set_number": 4}
    queue._finish(row, "completed", result=result(model_version="2", model_alias="candidate-opt"))
    sql, params = executed[0]
    assert "status = 'completed'" in sql
    assert params[2:4] == (MODEL, "2")
    assert params[-1] == "run-v2"


def test_monitoring_completion_with_bad_version_raises_inside_transaction(monkeypatch):
    monkeypatch.setattr(queue, "_snapshot", lambda cursor: ({}, {}))
    monkeypatch.setattr(queue, "matching_run", lambda identity, row: True)
    cursor = Mock(rowcount=1)
    monkeypatch.setattr(queue, "_transaction", lambda fn: fn(cursor))
    with pytest.raises(ValueError):
        queue._finish({"run_id": "r", "set_number": 4}, "completed",
                      result=result(model_version="candidate-opt"))
    cursor.execute.assert_not_called()
