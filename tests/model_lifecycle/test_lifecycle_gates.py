"""Offline tests for ml/lifecycle/model_lifecycle.py promotion/rollback gates.

A fake in-memory Registry stands in for MlflowClient; no MLflow server, torch
or network is touched.
"""
import importlib.util
import types
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "ml" / "lifecycle" / "model_lifecycle.py"
spec = importlib.util.spec_from_file_location("model_lifecycle_under_test", PATH)
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)

NAME = "cnc-wearpoint-multitask"
DATASET = "a" * 64


def evaluated(mae, dataset=DATASET):
    return {lc.TAG_MAE: str(mae), lc.TAG_DATASET: dataset}


class FakeClient:
    def __init__(self, versions, aliases=None, model_tags=None):
        self.versions = {str(k): dict(v) for k, v in versions.items()}
        self.aliases = {k: str(v) for k, v in (aliases or {}).items()}
        self.model_tags = dict(model_tags or {})

    def get_model_version(self, name, version):
        return types.SimpleNamespace(version=version, tags=self.versions[str(version)])

    def get_model_version_by_alias(self, name, alias):
        if alias not in self.aliases:
            raise RuntimeError(f"RESOURCE_DOES_NOT_EXIST: alias {alias}")
        return types.SimpleNamespace(version=self.aliases[alias])

    def get_registered_model(self, name):
        return types.SimpleNamespace(tags=self.model_tags, aliases=self.aliases)

    def set_registered_model_alias(self, name, alias, version):
        self.aliases[alias] = str(version)

    def set_registered_model_tag(self, name, key, value):
        self.model_tags[key] = str(value)

    def set_model_version_tag(self, name, version, key, value):
        self.versions[str(version)][key] = value


def test_unevaluated_version_cannot_be_promoted():
    client = FakeClient({1: evaluated(20.0), 2: {}}, aliases={"production": 1})
    with pytest.raises(lc.LifecycleError, match="no evaluation"):
        lc.plan_promotion(client, NAME, "2", "production")


def test_worse_mae_is_refused_unless_forced():
    client = FakeClient({1: evaluated(20.0), 2: evaluated(25.0)}, aliases={"production": 1})
    with pytest.raises(lc.LifecycleError, match="worse than current"):
        lc.plan_promotion(client, NAME, "2", "production")
    assert lc.plan_promotion(client, NAME, "2", "production", force=True)["action"] == "promote"


def test_different_dataset_is_not_comparable():
    client = FakeClient({1: evaluated(20.0, dataset="b" * 64), 2: evaluated(10.0)},
                        aliases={"production": 1})
    with pytest.raises(lc.LifecycleError, match="same dataset"):
        lc.plan_promotion(client, NAME, "2", "production")


def test_max_mae_is_an_absolute_gate():
    client = FakeClient({2: evaluated(40.0)})
    with pytest.raises(lc.LifecycleError, match="exceeds --max-mae"):
        lc.plan_promotion(client, NAME, "2", "production", max_mae=30.0)


def test_first_promotion_without_current_alias():
    client = FakeClient({2: evaluated(15.0)})
    plan = lc.plan_promotion(client, NAME, "2", "production")
    assert plan == {"action": "promote", "current": None, "target": "2",
                    "reason": "no current version"}


def test_same_version_is_noop():
    client = FakeClient({1: evaluated(20.0)}, aliases={"production": 1})
    assert lc.plan_promotion(client, NAME, "1", "production")["action"] == "noop"


def test_promote_then_rollback_restores_previous_and_is_repeatable():
    client = FakeClient({1: evaluated(20.0), 2: evaluated(18.0)}, aliases={"production": 1})
    plan = lc.plan_promotion(client, NAME, "2", "production")
    lc.apply_alias_move(client, NAME, "production", plan["current"], plan["target"])
    assert client.aliases["production"] == "2"
    assert client.model_tags[lc.previous_tag("production")] == "1"

    back = lc.plan_rollback(client, NAME, "production")
    assert (back["current"], back["target"]) == ("2", "1")
    lc.apply_alias_move(client, NAME, "production", back["current"], back["target"])
    assert client.aliases["production"] == "1"
    # Rolling back again returns to v2 (previous is swapped on each move).
    assert lc.plan_rollback(client, NAME, "production")["target"] == "2"


def test_rollback_without_history_is_refused():
    client = FakeClient({1: evaluated(20.0)}, aliases={"production": 1})
    with pytest.raises(lc.LifecycleError, match="no recorded previous"):
        lc.plan_rollback(client, NAME, "production")


def test_promotion_gate_only_touches_given_alias():
    client = FakeClient({1: evaluated(20.0), 2: evaluated(18.0)},
                        aliases={"production": 1, "candidate": 1, "candidate-opt": 2})
    plan = lc.plan_promotion(client, NAME, "2", "production")
    lc.apply_alias_move(client, NAME, "production", plan["current"], plan["target"])
    assert client.aliases == {"production": "2", "candidate": "1", "candidate-opt": "2"}


def test_compute_metrics():
    labels = [{"wear_um": 100.0, "type": "flank_wear"}, {"wear_um": 50.0, "type": "adhesion"}]
    preds = [{"predicted_wear_um": 110.0, "predicted_type": "flank_wear"},
             {"predicted_wear_um": 44.0, "predicted_type": "other_wear"}]
    m = lc.compute_metrics(labels, preds)
    assert m["mae_um"] == pytest.approx(8.0)
    assert m["rmse_um"] == pytest.approx(((100 + 36) / 2) ** 0.5)
    # "adhesion" is not a model class: accuracy must not be silently computed.
    assert m["type_accuracy"] is None
    assert m["unmapped_types"] == ["adhesion"]
    assert m["n"] == 2

    mapped = lc.compute_metrics(labels, preds, {"adhesion": "other_wear"})
    assert mapped["type_accuracy"] == pytest.approx(1.0)
    assert mapped["unmapped_types"] == []


def test_parse_type_map_rejects_unknown_target():
    assert lc.parse_type_map("adhesion=other_wear, flank_wear+adhesion=flank_wear") == {
        "adhesion": "other_wear", "flank_wear+adhesion": "flank_wear"}
    with pytest.raises(lc.LifecycleError, match="invalid --type-map"):
        lc.parse_type_map("adhesion=sticky")


def test_read_manifest_keeps_per_set_crop(tmp_path):
    (tmp_path / "m.csv").write_text(
        "image_path,sensor_path,wear_um,type,crop_left,crop_top,crop_right,crop_bottom\n"
        "a.jpg,a.csv,90,flank_wear,1790,2045,2390,2445\n", encoding="utf-8")
    assert lc.read_manifest(tmp_path / "m.csv")[0]["crop"] == (1790, 2045, 2390, 2445)


def test_read_manifest_resolves_relative_paths(tmp_path):
    (tmp_path / "m.csv").write_text(
        "image_path,sensor_path,wear_um,type\nimg/a.png,csv/a.csv,105,flank_wear\n",
        encoding="utf-8")
    rows = lc.read_manifest(tmp_path / "m.csv")
    assert rows[0]["image_path"] == str((tmp_path / "img/a.png").resolve())
    assert rows[0]["wear_um"] == 105.0


def test_read_manifest_rejects_missing_columns(tmp_path):
    (tmp_path / "m.csv").write_text("image_path,wear_um\na.png,1\n", encoding="utf-8")
    with pytest.raises(lc.LifecycleError, match="missing columns"):
        lc.read_manifest(tmp_path / "m.csv")


# --- per-set metrics, per-row predictions and version comparison

def _labels_preds():
    labels = [
        {"set": 4, "image_path": "/d/a.jpg", "sensor_path": "/d/a.csv", "wear_um": 100.0, "type": "flank_wear"},
        {"set": 4, "image_path": "/d/b.jpg", "sensor_path": "/d/b.csv", "wear_um": 50.0, "type": "adhesion"},
        {"set": 16, "image_path": "/d/c.jpg", "sensor_path": "/d/c.csv", "wear_um": 200.0,
         "type": "flank_wear+adhesion"},
    ]
    preds = [
        {"predicted_wear_um": 110.0, "predicted_type": "flank_wear", "flank_wear_probability": 0.9},
        {"predicted_wear_um": 44.0, "predicted_type": "other_wear", "flank_wear_probability": 0.2},
        {"predicted_wear_um": 150.0, "predicted_type": "flank_wear", "flank_wear_probability": 0.7},
    ]
    return labels, preds


TYPE_MAP = {"adhesion": "other_wear", "flank_wear+adhesion": "other_wear"}


def test_per_set_metrics_split_by_manifest_set():
    labels, preds = _labels_preds()
    by_set = lc.per_set_metrics(labels, preds, TYPE_MAP)
    assert list(by_set) == [4, 16]
    assert by_set[4]["n"] == 2 and by_set[4]["mae_um"] == pytest.approx(8.0)
    assert by_set[4]["type_accuracy"] == pytest.approx(1.0)
    assert by_set[16]["mae_um"] == pytest.approx(50.0)
    assert by_set[16]["type_accuracy"] == pytest.approx(0.0)


def test_prediction_rows_keep_full_precision_and_expected_type():
    labels, preds = _labels_preds()
    preds[0]["predicted_wear_um"] = 110.12345678901234
    rows = lc.prediction_rows(labels, preds, TYPE_MAP)
    assert rows[0]["image"] == "a.jpg" and rows[0]["set"] == 4
    assert float(rows[0]["predicted_wear_um"]) == 110.12345678901234
    assert rows[2]["expected_type"] == "other_wear"
    assert rows[2]["abs_error_um"] == pytest.approx(50.0)


def test_compare_predictions_detects_identical_and_different_rows():
    labels, preds = _labels_preds()
    a = lc.prediction_rows(labels, preds, TYPE_MAP)
    same = lc.compare_predictions(a, [dict(r) for r in a])
    assert same["identical_wear"] == 3 and same["max_wear_diff_um"] == 0
    assert same["type_mismatches"] == 0 and same["only_a"] == same["only_b"] == 0

    b = [dict(r) for r in a[:2]]
    b[1]["predicted_wear_um"] = repr(44.5)
    b[1]["predicted_type"] = "flank_wear"
    diff = lc.compare_predictions(a, b)
    assert diff["common"] == 2 and diff["only_a"] == 1
    assert diff["identical_wear"] == 1
    assert diff["max_wear_diff_um"] == pytest.approx(0.5)
    assert diff["type_mismatches"] == 1


def test_read_manifest_keeps_set_column(tmp_path):
    (tmp_path / "m.csv").write_text(
        "set,image_path,sensor_path,wear_um,type\n16,a.jpg,a.csv,90,flank_wear\n", encoding="utf-8")
    assert lc.read_manifest(tmp_path / "m.csv")[0]["set"] == 16


def test_compare_refuses_versions_without_prediction_artifact():
    client = FakeClient({1: {lc.TAG_RUN: "run-1", **evaluated(20.0)}})

    class NoArtifacts:
        class artifacts:
            @staticmethod
            def download_artifacts(run_id, artifact_path):
                raise OSError("not found")

    with pytest.raises(lc.LifecycleError, match="re-run `evaluate`"):
        lc.load_eval_predictions(client, NoArtifacts, NAME, "1")


def test_evaluate_end_to_end_with_fake_mlflow(tmp_path, monkeypatch):
    """evaluate() writes per-set metrics, predictions.csv and version tags."""
    import contextlib
    import sys
    import pandas as pd

    # service.py imports mlflow at module level; give it inert stand-ins.
    fake_mlflow = types.ModuleType("mlflow")
    fake_tracking = types.ModuleType("mlflow.tracking")
    fake_tracking.MlflowClient = object
    fake_mlflow.tracking = fake_tracking
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    monkeypatch.setitem(sys.modules, "mlflow.tracking", fake_tracking)
    monkeypatch.delitem(sys.modules, "service", raising=False)

    (tmp_path / "m.csv").write_text(
        "set,image_path,sensor_path,wear_um,type,crop_left,crop_top,crop_right,crop_bottom\n"
        "4,a.jpg,a.csv,100,flank_wear,1150,670,1750,1070\n"
        "16,b.jpg,b.csv,200,flank_wear+adhesion,1790,2045,2390,2445\n", encoding="utf-8")

    seen = {"metrics": {}, "artifacts": {}, "inputs": None}

    class Model:
        def predict(self, df):
            seen["inputs"] = df
            return pd.DataFrame([
                {"predicted_wear_um": 90.0, "predicted_type": "flank_wear", "flank_wear_probability": 0.8},
                {"predicted_wear_um": 260.0, "predicted_type": "other_wear", "flank_wear_probability": 0.1},
            ])

    class FakeMlflow:
        class pyfunc:
            @staticmethod
            def load_model(uri):
                assert uri == "models:/cnc-wearpoint-multitask/2"
                return Model()

        @staticmethod
        @contextlib.contextmanager
        def start_run(run_name):
            yield types.SimpleNamespace(info=types.SimpleNamespace(run_id="run-eval"))

        set_tags = set_tag = staticmethod(lambda *a, **k: None)

        @staticmethod
        def log_metrics(m):
            seen["metrics"].update(m)

        @staticmethod
        def log_metric(k, v):
            seen["metrics"][k] = v

        @staticmethod
        def log_artifact(path, artifact_path):
            seen["artifacts"][Path(path).name] = Path(path).read_text(encoding="utf-8")

    client = FakeClient({2: {}})
    result = lc.evaluate(client, FakeMlflow, NAME, "2", tmp_path / "m.csv", TYPE_MAP)

    assert list(seen["inputs"]["crop_left"]) == [1150, 1790]  # manifest crop, not Serving ROI
    assert result["mae_um"] == pytest.approx(35.0) and result["type_accuracy"] == pytest.approx(1.0)
    assert seen["metrics"]["set4.mae_um"] == pytest.approx(10.0)
    assert seen["metrics"]["set16.mae_um"] == pytest.approx(60.0)
    assert seen["metrics"]["set16.type_accuracy"] == pytest.approx(1.0)
    assert "predictions.csv" in seen["artifacts"] and "m.csv" in seen["artifacts"]
    assert seen["artifacts"]["predictions.csv"].splitlines()[0].split(",") == lc.PREDICTION_COLUMNS
    assert client.versions["2"][lc.TAG_RUN] == "run-eval"
    assert client.versions["2"][lc.TAG_MAE] == "35.00000"
