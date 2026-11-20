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
