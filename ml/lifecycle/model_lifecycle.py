"""Minimal MLflow model lifecycle: evaluate -> promote (gated) -> rollback.

    python ml/lifecycle/model_lifecycle.py status
    python ml/lifecycle/model_lifecycle.py evaluate --version 2 --manifest eval/manifest.csv
    python ml/lifecycle/model_lifecycle.py promote  --version 2 --alias production [--dry-run]
    python ml/lifecycle/model_lifecycle.py rollback --alias production [--dry-run]
    python ml/lifecycle/model_lifecycle.py compare  --version 1 --other 2

`evaluate` logs overall + per-set metrics (set4.mae_um, ...) and every
prediction as eval/predictions.csv; `compare` diffs two versions row by row.

Run `evaluate` inside the Serving environment (needs torch + ml/serving code).
`status` / `promote` / `rollback` only talk to the Registry.

Serving resolves MODEL_ALIAS once at startup, so a promote/rollback takes
effect only after the Serving container is restarted (printed as a reminder).

Manifest CSV header: image_path,sensor_path,wear_um,type
[,crop_left,crop_top,crop_right,crop_bottom]  (see build_manifest.py)
Relative paths are resolved against the manifest's directory. When crop
columns are present they are used as-is (training crop per set); otherwise
Serving's own ROI rule is applied.

The model predicts only MODEL_TYPES. Label types outside that set (e.g.
"adhesion", "flank_wear+adhesion") need an explicit --type-map such as
"adhesion=other_wear,flank_wear+adhesion=other_wear"; without it type
accuracy is not computed (reported as unavailable) instead of being wrong.
"""
import argparse
import csv
import hashlib
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MODEL_NAME = "cnc-wearpoint-multitask"
SERVING_DIR = Path(__file__).resolve().parents[1] / "serving"

# Model version tags written by `evaluate`; `promote` gates on them.
TAG_MAE = "eval.mae_um"
TAG_RMSE = "eval.rmse_um"
TAG_TYPE_ACC = "eval.type_accuracy"
TAG_N = "eval.n"
TAG_DATASET = "eval.dataset_sha256"
TAG_RUN = "eval.run_id"
TAG_TYPE_MAP = "eval.type_map"

MODEL_TYPES = {"flank_wear", "other_wear"}
CROP_COLUMNS = ("crop_left", "crop_top", "crop_right", "crop_bottom")


class LifecycleError(Exception):
    """A gate refused the operation; nothing was changed in the Registry."""


def previous_tag(alias: str) -> str:
    # Registered-model tag holding the version the alias pointed to before.
    return f"lifecycle.{alias}.previous_version"


# ---------------------------------------------------------------- evaluate

def read_manifest(path: Path) -> list[dict]:
    base = path.resolve().parent
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = {"image_path", "sensor_path", "wear_um", "type"} - set(reader.fieldnames or [])
        if missing:
            raise LifecycleError(f"manifest is missing columns: {sorted(missing)}")
        for line, row in enumerate(reader, start=2):
            wear = float(row["wear_um"])
            if not math.isfinite(wear) or wear < 0:
                raise LifecycleError(f"manifest line {line}: invalid wear_um")
            item = {
                "image_path": str((base / row["image_path"]).resolve()),
                "sensor_path": str((base / row["sensor_path"]).resolve()),
                "wear_um": wear,
                "type": row["type"].strip(),
            }
            if all((row.get(c) or "").strip() for c in CROP_COLUMNS):
                item["crop"] = tuple(int(row[c]) for c in CROP_COLUMNS)
            if (row.get("set") or "").strip():
                item["set"] = int(float(row["set"]))
            rows.append(item)
    if not rows:
        raise LifecycleError("manifest has no rows")
    return rows


def manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_type_map(text: str | None) -> dict:
    mapping = {}
    for part in filter(None, (p.strip() for p in (text or "").split(","))):
        label, sep, target = part.partition("=")
        if not sep or target.strip() not in MODEL_TYPES:
            raise LifecycleError(f"invalid --type-map entry '{part}' (target must be one of {sorted(MODEL_TYPES)})")
        mapping[label.strip()] = target.strip()
    return mapping


def compute_metrics(labels: list[dict], predictions: list[dict], type_map: dict | None = None) -> dict:
    """MAE / RMSE in µm and wear-type accuracy over paired rows.

    type_accuracy is None when a label type cannot be expressed as a model class.
    """
    if len(labels) != len(predictions) or not labels:
        raise LifecycleError("labels and predictions must be non-empty and the same length")
    errors = [float(p["predicted_wear_um"]) - l["wear_um"] for l, p in zip(labels, predictions)]
    if not all(math.isfinite(e) for e in errors):
        raise LifecycleError("model returned a non-finite predicted_wear_um")
    n = len(errors)
    type_map = type_map or {}
    expected = [type_map.get(l["type"], l["type"]) for l in labels]
    unmapped = sorted({t for t in expected if t not in MODEL_TYPES})
    return {
        "mae_um": sum(abs(e) for e in errors) / n,
        "rmse_um": math.sqrt(sum(e * e for e in errors) / n),
        "type_accuracy": None if unmapped else sum(
            str(p["predicted_type"]) == t for t, p in zip(expected, predictions)) / n,
        "unmapped_types": unmapped,
        "n": n,
    }


def per_set_metrics(labels: list[dict], predictions: list[dict],
                    type_map: dict | None = None) -> dict:
    """compute_metrics per manifest `set` (rows without a set are grouped as None)."""
    groups = {}
    for label, prediction in zip(labels, predictions):
        groups.setdefault(label.get("set"), ([], []))
        groups[label.get("set")][0].append(label)
        groups[label.get("set")][1].append(prediction)
    return {key: compute_metrics(ls, ps, type_map)
            for key, (ls, ps) in sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))}


PREDICTION_COLUMNS = [
    "set", "image", "sensor", "wear_um", "type", "expected_type",
    "predicted_wear_um", "predicted_type", "flank_wear_probability", "abs_error_um",
]


def prediction_rows(labels: list[dict], predictions: list[dict],
                    type_map: dict | None = None) -> list[dict]:
    """One row per manifest entry; logged as eval/predictions.csv."""
    type_map = type_map or {}
    rows = []
    for label, prediction in zip(labels, predictions):
        wear = float(prediction["predicted_wear_um"])
        rows.append({
            "set": label.get("set", ""),
            "image": Path(label["image_path"]).name,
            "sensor": Path(label["sensor_path"]).name,
            "wear_um": label["wear_um"],
            "type": label["type"],
            "expected_type": type_map.get(label["type"], label["type"]),
            "predicted_wear_um": repr(wear),  # full float precision for exact comparison
            "predicted_type": str(prediction["predicted_type"]),
            "flank_wear_probability": repr(float(prediction.get("flank_wear_probability", "nan"))),
            "abs_error_um": abs(wear - label["wear_um"]),
        })
    return rows


def compare_predictions(rows_a: list[dict], rows_b: list[dict]) -> dict:
    """Row-level comparison of two eval/predictions.csv files (same manifest)."""
    key = lambda r: (str(r["image"]), str(r["sensor"]))  # noqa: E731
    a = {key(r): r for r in rows_a}
    b = {key(r): r for r in rows_b}
    common = sorted(set(a) & set(b))
    wear_diffs = [abs(float(a[k]["predicted_wear_um"]) - float(b[k]["predicted_wear_um"])) for k in common]
    prob_diffs = [abs(float(a[k]["flank_wear_probability"]) - float(b[k]["flank_wear_probability"]))
                  for k in common]
    type_mismatch = [k for k in common if a[k]["predicted_type"] != b[k]["predicted_type"]]
    return {
        "rows_a": len(a), "rows_b": len(b), "common": len(common),
        "only_a": len(set(a) - set(b)), "only_b": len(set(b) - set(a)),
        "identical_wear": sum(d == 0 for d in wear_diffs),
        "max_wear_diff_um": max(wear_diffs, default=0.0),
        "max_probability_diff": max(prob_diffs, default=0.0),
        "type_mismatches": len(type_mismatch),
        "type_mismatch_examples": type_mismatch[:5],
    }


def evaluate(client, mlflow, name: str, version: str, manifest: Path,
             type_map: dict | None = None) -> dict:
    sys.path.insert(0, str(SERVING_DIR))
    import pandas as pd
    from service import determine_crop  # same ROI rule as live Serving

    labels = read_manifest(manifest)
    model_input = pd.DataFrame([
        dict(image_path=r["image_path"], sensor_path=r["sensor_path"],
             **dict(zip(CROP_COLUMNS, r.get("crop") or determine_crop(Path(r["image_path"])))))
        for r in labels
    ])
    model = mlflow.pyfunc.load_model(f"models:/{name}/{version}")
    predictions = model.predict(model_input).to_dict(orient="records")
    metrics = compute_metrics(labels, predictions, type_map)
    by_set = per_set_metrics(labels, predictions, type_map)
    rows = prediction_rows(labels, predictions, type_map)
    dataset = manifest_sha256(manifest)
    map_text = ",".join(f"{k}={v}" for k, v in sorted((type_map or {}).items())) or "none"

    with mlflow.start_run(run_name=f"evaluate-{name}-v{version}") as run:
        mlflow.set_tags({"lifecycle_step": "evaluate", "model_name": name,
                         "model_version": str(version), "dataset_sha256": dataset})
        mlflow.set_tag("type_map", map_text)
        mlflow.log_metrics({k: float(metrics[k]) for k in ("mae_um", "rmse_um", "n")})
        if metrics["type_accuracy"] is not None:
            mlflow.log_metric("type_accuracy", metrics["type_accuracy"])
        for set_no, m in by_set.items():
            if set_no is None:
                continue
            prefix = f"set{set_no}."
            mlflow.log_metrics({prefix + k: float(m[k]) for k in ("mae_um", "rmse_um", "n")})
            if m["type_accuracy"] is not None:
                mlflow.log_metric(prefix + "type_accuracy", m["type_accuracy"])
        mlflow.log_artifact(str(manifest), artifact_path="eval")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "predictions.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=PREDICTION_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            mlflow.log_artifact(str(path), artifact_path="eval")
        run_id = run.info.run_id

    for key, value in ((TAG_MAE, f"{metrics['mae_um']:.5f}"),
                       (TAG_RMSE, f"{metrics['rmse_um']:.5f}"),
                       (TAG_TYPE_ACC, "n/a" if metrics["type_accuracy"] is None
                        else f"{metrics['type_accuracy']:.5f}"),
                       (TAG_TYPE_MAP, map_text),
                       (TAG_N, str(metrics["n"])),
                       (TAG_DATASET, dataset),
                       (TAG_RUN, run_id)):
        client.set_model_version_tag(name, str(version), key, value)
    return {**metrics, "per_set": by_set, "dataset_sha256": dataset, "run_id": run_id}


def load_eval_predictions(client, mlflow, name: str, version: str) -> tuple[list[dict], dict]:
    tags = eval_tags(client, name, version)
    if TAG_RUN not in tags:
        raise LifecycleError(f"v{version} has no evaluation run; run `evaluate` first")
    try:
        path = mlflow.artifacts.download_artifacts(
            run_id=tags[TAG_RUN], artifact_path="eval/predictions.csv")
    except Exception as exc:
        raise LifecycleError(
            f"v{version} evaluation run {tags[TAG_RUN]} has no eval/predictions.csv "
            f"(evaluated before per-row logging); re-run `evaluate`") from exc
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f)), tags


# ------------------------------------------------------- promote / rollback

def alias_version(client, name: str, alias: str) -> str | None:
    try:
        return str(client.get_model_version_by_alias(name, alias).version)
    except Exception as exc:  # MlflowException RESOURCE_DOES_NOT_EXIST
        if "RESOURCE_DOES_NOT_EXIST" in str(exc) or "not found" in str(exc).lower():
            return None
        raise


def eval_tags(client, name: str, version: str) -> dict:
    return dict(client.get_model_version(name, str(version)).tags or {})


def plan_promotion(client, name: str, version: str, alias: str,
                   max_mae: float | None = None, force: bool = False) -> dict:
    """Decide whether `alias` may move to `version`. Read-only."""
    version = str(version)
    target = eval_tags(client, name, version)
    if TAG_MAE not in target or TAG_DATASET not in target:
        raise LifecycleError(f"v{version} has no evaluation; run `evaluate` first")
    target_mae = float(target[TAG_MAE])
    if max_mae is not None and target_mae > max_mae:
        raise LifecycleError(f"v{version} MAE {target_mae:.3f} µm exceeds --max-mae {max_mae}")

    current = alias_version(client, name, alias)
    if current == version:
        return {"action": "noop", "current": current, "target": version}

    reason = "no current version"
    if current is not None:
        cur = eval_tags(client, name, current)
        if TAG_MAE not in cur or cur.get(TAG_DATASET) != target[TAG_DATASET]:
            if not force:
                raise LifecycleError(
                    f"current v{current} was not evaluated on the same dataset; "
                    f"evaluate it with the same manifest or pass --force")
            reason = "forced (not comparable)"
        else:
            cur_mae = float(cur[TAG_MAE])
            if target_mae > cur_mae and not force:
                raise LifecycleError(
                    f"v{version} MAE {target_mae:.3f} µm is worse than current "
                    f"v{current} {cur_mae:.3f} µm; pass --force to override")
            reason = f"MAE {cur_mae:.3f} -> {target_mae:.3f} µm"
    return {"action": "promote", "current": current, "target": version, "reason": reason}


def apply_alias_move(client, name: str, alias: str, current: str | None, target: str):
    if current is not None:
        client.set_registered_model_tag(name, previous_tag(alias), current)
    client.set_registered_model_alias(name, alias, target)


def plan_rollback(client, name: str, alias: str) -> dict:
    current = alias_version(client, name, alias)
    previous = (client.get_registered_model(name).tags or {}).get(previous_tag(alias))
    if not previous:
        raise LifecycleError(f"no recorded previous version for alias '{alias}'")
    if previous == current:
        raise LifecycleError(f"alias '{alias}' already points to v{previous}")
    return {"action": "rollback", "current": current, "target": previous}


# --------------------------------------------------------------------- CLI

RESTART_HINT = ("Serving resolves the alias only at startup: restart the Serving "
                "container (MODEL_ALIAS={alias}) and check /health shows model_version {version}.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    p = sub.add_parser("evaluate")
    p.add_argument("--version", required=True)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--type-map", help='e.g. "adhesion=other_wear,flank_wear+adhesion=other_wear"')
    p = sub.add_parser("promote")
    p.add_argument("--version", required=True)
    p.add_argument("--alias", required=True)
    p.add_argument("--max-mae", type=float)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("rollback")
    p.add_argument("--alias", required=True)
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("compare", help="Row-level diff of two versions' evaluation predictions (read-only)")
    p.add_argument("--version", required=True)
    p.add_argument("--other", required=True)
    args = parser.parse_args(argv)

    if not args.tracking_uri:
        parser.error("set --tracking-uri or MLFLOW_TRACKING_URI explicitly")

    import mlflow
    from mlflow import MlflowClient
    mlflow.set_tracking_uri(args.tracking_uri)
    client = MlflowClient()
    name = args.model_name

    try:
        if args.command == "status":
            model = client.get_registered_model(name)
            print(f"{name} @ {args.tracking_uri}")
            for alias, version in sorted((model.aliases or {}).items()):
                print(f"  alias {alias} -> v{version}")
            for key, value in sorted((model.tags or {}).items()):
                if key.startswith("lifecycle."):
                    print(f"  tag {key} = {value}")
            for mv in sorted(client.search_model_versions(f"name='{name}'"),
                             key=lambda m: int(m.version)):
                tags = mv.tags or {}
                print(f"  v{mv.version}: MAE={tags.get(TAG_MAE, '-')} "
                      f"type_acc={tags.get(TAG_TYPE_ACC, '-')} n={tags.get(TAG_N, '-')} "
                      f"dataset={tags.get(TAG_DATASET, '-')[:12]}")
        elif args.command == "evaluate":
            result = evaluate(client, mlflow, name, args.version, args.manifest,
                              parse_type_map(args.type_map))
            acc = result["type_accuracy"]
            print(f"v{args.version}: MAE={result['mae_um']:.3f} µm RMSE={result['rmse_um']:.3f} µm "
                  f"type_acc={'n/a' if acc is None else f'{acc:.3f}'} n={result['n']} "
                  f"run_id={result['run_id']}")
            for set_no, m in result["per_set"].items():
                set_acc = m["type_accuracy"]
                print(f"  set {set_no if set_no is not None else '-'}: n={m['n']} "
                      f"MAE={m['mae_um']:.3f} µm RMSE={m['rmse_um']:.3f} µm "
                      f"type_acc={'n/a' if set_acc is None else f'{set_acc:.3f}'}")
            if result["unmapped_types"]:
                print(f"type accuracy unavailable: label types {result['unmapped_types']} "
                      f"need --type-map to a model class {sorted(MODEL_TYPES)}")
        elif args.command == "compare":
            rows_a, tags_a = load_eval_predictions(client, mlflow, name, args.version)
            rows_b, tags_b = load_eval_predictions(client, mlflow, name, args.other)
            if tags_a.get(TAG_DATASET) != tags_b.get(TAG_DATASET):
                raise LifecycleError("the two versions were evaluated on different manifests")
            c = compare_predictions(rows_a, rows_b)
            print(f"v{args.version} vs v{args.other} (dataset {tags_a[TAG_DATASET][:12]}): "
                  f"rows {c['rows_a']}/{c['rows_b']}, common {c['common']}, "
                  f"only_a {c['only_a']}, only_b {c['only_b']}")
            print(f"  identical predicted_wear_um: {c['identical_wear']}/{c['common']} "
                  f"(max diff {c['max_wear_diff_um']:.3g} µm)")
            print(f"  max flank_wear_probability diff: {c['max_probability_diff']:.3g}")
            print(f"  predicted_type mismatches: {c['type_mismatches']} {c['type_mismatch_examples']}")
        elif args.command == "promote":
            plan = plan_promotion(client, name, args.version, args.alias, args.max_mae, args.force)
            if plan["action"] == "noop":
                print(f"alias '{args.alias}' already points to v{plan['target']}")
                return 0
            print(f"promote '{args.alias}': v{plan['current']} -> v{plan['target']} ({plan['reason']})")
            if args.dry_run:
                print("dry-run: Registry not changed")
                return 0
            apply_alias_move(client, name, args.alias, plan["current"], plan["target"])
            client.set_model_version_tag(name, plan["target"], f"lifecycle.{args.alias}.promoted_at",
                                         datetime.now(timezone.utc).isoformat(timespec="seconds"))
            print(RESTART_HINT.format(alias=args.alias, version=plan["target"]))
        elif args.command == "rollback":
            plan = plan_rollback(client, name, args.alias)
            print(f"rollback '{args.alias}': v{plan['current']} -> v{plan['target']}")
            if args.dry_run:
                print("dry-run: Registry not changed")
                return 0
            apply_alias_move(client, name, args.alias, plan["current"], plan["target"])
            print(RESTART_HINT.format(alias=args.alias, version=plan["target"]))
    except LifecycleError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
