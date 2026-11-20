"""Offline tests for ml/serving/service.py model selection.

No MLflow server, Registry, S3 or torch is touched: ``mlflow`` and
``mlflow.tracking`` are replaced by in-memory stubs via ``sys.modules`` before
service.py is imported from its file path. ml/serving is not modified.

What the current code actually does (and what these tests pin down):
- MODEL_NAME / MODEL_ALIAS come from env at import time
  (defaults ``cnc-wearpoint-multitask`` / ``candidate``).
- The alias is resolved ONCE in the FastAPI lifespan through
  ``MlflowClient().get_model_version_by_alias`` and the immutable
  ``models:/{name}/{version}`` URI is loaded with ``mlflow.pyfunc.load_model``.
- Moving the alias while the process is running has no effect until the
  lifespan runs again (process restart).
"""

import importlib.util
import io
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from PIL import Image

SERVICE_PATH = Path(__file__).resolve().parents[2] / "ml" / "serving" / "service.py"
MODULE_NAME = "cnc_wearpoint_serving_service_under_test"


class Registry:
    """Fake Registry state: alias -> version, mutable to simulate alias moves."""

    def __init__(self, aliases):
        self.aliases = dict(aliases)
        self.lookups = []

    def get_model_version_by_alias(self, name, alias):
        self.lookups.append((name, alias))
        if alias not in self.aliases:
            raise RuntimeError(f"RESOURCE_DOES_NOT_EXIST: {name}@{alias}")
        version = self.aliases[alias]
        return types.SimpleNamespace(name=name, version=version, run_id=f"run-v{version}")


def fake_pyfunc_model(epoch=10):
    model = Mock()
    model.predict.return_value = pd.DataFrame([{
        "epoch": epoch,
        "predicted_wear_um": 173.5,
        "flank_wear_probability": 0.91,
        "predicted_type": "flank_wear",
        "threshold": 0.5,
        "window_count": 174,
        "sampling_hz": 1642.0,
        "cut_start_index": 0,
        "cut_end_index_exclusive": 100,
    }])
    return model


@pytest.fixture
def serving(monkeypatch):
    """Import service.py with stubbed mlflow; returns load(...) -> (module, stubs)."""

    def load(model_name=None, model_alias=None, aliases=None,
             tracking_uri="http://registry.invalid/mlflow"):
        for key, value in (("MODEL_NAME", model_name), ("MODEL_ALIAS", model_alias),
                           ("MLFLOW_TRACKING_URI", tracking_uri)):
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)

        registry = Registry(aliases if aliases is not None else {"candidate": 1})
        loaded = {"uris": [], "models": []}

        def load_model(uri):
            loaded["uris"].append(uri)
            model = fake_pyfunc_model()
            loaded["models"].append(model)
            return model

        mlflow = types.ModuleType("mlflow")
        mlflow.set_tracking_uri = Mock()
        mlflow.pyfunc = types.ModuleType("mlflow.pyfunc")
        mlflow.pyfunc.load_model = Mock(side_effect=load_model)
        tracking = types.ModuleType("mlflow.tracking")
        tracking.MlflowClient = Mock(return_value=registry)
        mlflow.tracking = tracking
        monkeypatch.setitem(sys.modules, "mlflow", mlflow)
        monkeypatch.setitem(sys.modules, "mlflow.pyfunc", mlflow.pyfunc)
        monkeypatch.setitem(sys.modules, "mlflow.tracking", tracking)

        spec = importlib.util.spec_from_file_location(MODULE_NAME, SERVICE_PATH)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, MODULE_NAME, module)
        spec.loader.exec_module(module)
        return module, types.SimpleNamespace(mlflow=mlflow, registry=registry, loaded=loaded)

    return load


def png_bytes(size=(600, 400)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def predict(client):
    return client.post(
        "/predictions",
        files={
            "image": ("tool.png", png_bytes(), "image/png"),
            "sensor_csv": ("sensor.csv", b"t,fy\n0,1\n", "text/csv"),
        },
    )


def test_defaults_are_production_name_and_candidate_alias(serving):
    service, _ = serving()
    assert service.MODEL_NAME == "cnc-wearpoint-multitask"
    assert service.MODEL_ALIAS == "candidate"


def test_alias_is_resolved_to_version_and_fixed_version_uri_is_loaded(serving):
    service, stubs = serving(aliases={"candidate": 1, "candidate-opt": 2})
    with TestClient(service.app) as client:
        health = client.get("/health").json()
    stubs.mlflow.set_tracking_uri.assert_called_once_with("http://registry.invalid/mlflow")
    assert stubs.registry.lookups == [("cnc-wearpoint-multitask", "candidate")]
    # The alias URI (models:/name@alias) is never loaded; only the resolved version.
    assert stubs.loaded["uris"] == ["models:/cnc-wearpoint-multitask/1"]
    assert health == {
        "status": "ok",
        "model_name": "cnc-wearpoint-multitask",
        "model_alias": "candidate",
        "model_version": "1",
        "model_run_id": "run-v1",
        "model_loaded": True,
    }


def test_test_alias_env_selects_other_version_without_touching_candidate(serving):
    service, stubs = serving(model_alias="candidate-opt",
                             aliases={"candidate": 1, "candidate-opt": 2})
    with TestClient(service.app) as client:
        health = client.get("/health").json()
    assert stubs.registry.lookups == [("cnc-wearpoint-multitask", "candidate-opt")]
    assert stubs.loaded["uris"] == ["models:/cnc-wearpoint-multitask/2"]
    assert health["model_alias"] == "candidate-opt"
    assert health["model_version"] == "2"


def test_model_name_env_is_used_for_lookup_and_uri(serving):
    service, stubs = serving(model_name="cnc-wearpoint-multitask-lifecycle-test",
                             model_alias="staging", aliases={"staging": 7})
    with TestClient(service.app) as client:
        body = client.get("/health").json()
    assert stubs.registry.lookups == [("cnc-wearpoint-multitask-lifecycle-test", "staging")]
    assert stubs.loaded["uris"] == ["models:/cnc-wearpoint-multitask-lifecycle-test/7"]
    assert body["model_name"] == "cnc-wearpoint-multitask-lifecycle-test"


def test_prediction_response_exposes_name_alias_resolved_version(serving):
    service, stubs = serving()
    with TestClient(service.app) as client:
        response = predict(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model_name"] == "cnc-wearpoint-multitask"
    assert body["model_alias"] == "candidate"
    assert body["model_version"] == "1"
    assert body["model_epoch"] == 10
    assert body["predicted_wear_um"] == 173.5
    assert body["predicted_type"] == "flank_wear"
    assert body["window_count"] == 174
    # Serving input contract: one-row DataFrame of paths + crop ints.
    frame = stubs.loaded["models"][0].predict.call_args.args[0]
    assert list(frame.columns) == ["image_path", "sensor_path", "crop_left", "crop_top",
                                   "crop_right", "crop_bottom"]
    assert len(frame) == 1
    crop = frame.iloc[0]
    assert (crop["crop_left"], crop["crop_top"], crop["crop_right"], crop["crop_bottom"]) == (0, 0, 600, 400)


def test_alias_move_after_load_does_not_change_served_version_until_restart(serving):
    service, stubs = serving(aliases={"candidate": 1})
    with TestClient(service.app) as client:
        assert client.get("/health").json()["model_version"] == "1"
        # Someone repoints the alias in the Registry while Serving is running.
        stubs.registry.aliases["candidate"] = 2
        health = client.get("/health").json()
        body = predict(client).json()
        assert health["model_version"] == "1"
        assert health["model_alias"] == "candidate"  # looks consistent, but alias is now 2
        assert body["model_version"] == "1"
        assert stubs.registry.lookups == [("cnc-wearpoint-multitask", "candidate")]
        assert stubs.loaded["uris"] == ["models:/cnc-wearpoint-multitask/1"]

    # Only a new lifespan (= process restart) picks up the moved alias.
    with TestClient(service.app) as client:
        assert client.get("/health").json()["model_version"] == "2"
    assert stubs.loaded["uris"] == ["models:/cnc-wearpoint-multitask/1",
                                    "models:/cnc-wearpoint-multitask/2"]


def test_shutdown_clears_loaded_model(serving):
    service, _ = serving()
    with TestClient(service.app):
        assert service.model is not None
    assert service.model is None
    assert service.model_version is None


def test_without_lifespan_health_reports_not_loaded_and_predictions_503(serving):
    service, stubs = serving()
    client = TestClient(service.app)  # no context manager -> lifespan not run
    health = client.get("/health").json()
    assert health["model_loaded"] is False
    assert health["model_version"] is None
    assert predict(client).status_code == 503
    stubs.mlflow.pyfunc.load_model.assert_not_called()


def test_missing_tracking_uri_fails_startup(serving):
    service, stubs = serving(tracking_uri=None)
    with pytest.raises(KeyError):
        with TestClient(service.app):
            pass
    assert stubs.registry.lookups == []
    stubs.mlflow.pyfunc.load_model.assert_not_called()


def test_missing_alias_fails_startup_hard_without_fallback(serving):
    service, stubs = serving(model_alias="candidate-opt", aliases={"candidate": 1})
    with pytest.raises(RuntimeError, match="RESOURCE_DOES_NOT_EXIST"):
        with TestClient(service.app):
            pass
    # No fallback to another alias or version.
    assert stubs.registry.lookups == [("cnc-wearpoint-multitask", "candidate-opt")]
    stubs.mlflow.pyfunc.load_model.assert_not_called()


def test_model_without_expected_output_columns_is_500_not_400(serving):
    """A model not following the V1 output contract (e.g. raw tensor output)
    raises KeyError, which is not mapped to 400 (input rejected)."""
    service, stubs = serving()
    with TestClient(service.app, raise_server_exceptions=False) as client:
        stubs.loaded["models"][0].predict.return_value = pd.DataFrame([{"output": 0.1}])
        response = predict(client)
    assert response.status_code == 500
