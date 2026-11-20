"""Minimal MLflow model lifecycle: evaluate -> promote (gated) -> rollback.

    python ml/lifecycle/model_lifecycle.py status
    python ml/lifecycle/model_lifecycle.py evaluate --version 2 --manifest eval/manifest.csv
    python ml/lifecycle/model_lifecycle.py promote  --version 2 --alias production [--dry-run]
    python ml/lifecycle/model_lifecycle.py rollback --alias production [--dry-run]

Run `evaluate` inside the Serving environment (needs torch + ml/serving code).
`status` / `promote` / `rollback` only talk to the Registry.

Serving resolves MODEL_ALIAS once at startup, so a promote/rollback takes
effect only after the Serving container is restarted (printed as a reminder).

Manifest CSV header: image_path,sensor_path,wear_um,type
Relative paths are resolved against the manifest's directory.
"""
import argparse
import csv
import hashlib
import math
import os
import sys
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
            rows.append({
                "image_path": str((base / row["image_path"]).resolve()),
                "sensor_path": str((base / row["sensor_path"]).resolve()),
                "wear_um": wear,
                "type": row["type"].strip(),
            })
    if not rows:
        raise LifecycleError("manifest has no rows")
    return rows


def manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_metrics(labels: list[dict], predictions: list[dict]) -> dict:
    """MAE / RMSE in µm and wear-type accuracy over paired rows."""
    if len(labels) != len(predictions) or not labels:
        raise LifecycleError("labels and predictions must be non-empty and the same length")
    errors = [float(p["predicted_wear_um"]) - l["wear_um"] for l, p in zip(labels, predictions)]
    if not all(math.isfinite(e) for e in errors):
        raise LifecycleError("model returned a non-finite predicted_wear_um")
    n = len(errors)
    return {
        "mae_um": sum(abs(e) for e in errors) / n,
        "rmse_um": math.sqrt(sum(e * e for e in errors) / n),
        "type_accuracy": sum(
            str(p["predicted_type"]) == l["type"] for l, p in zip(labels, predictions)
        ) / n,
        "n": n,
    }


def evaluate(client, mlflow, name: str, version: str, manifest: Path) -> dict:
    sys.path.insert(0, str(SERVING_DIR))
    import pandas as pd
    from service import determine_crop  # same ROI rule as live Serving

    labels = read_manifest(manifest)
    model_input = pd.DataFrame([
        dict(image_path=r["image_path"], sensor_path=r["sensor_path"],
             **dict(zip(("crop_left", "crop_top", "crop_right", "crop_bottom"),
                        determine_crop(Path(r["image_path"])))))
        for r in labels
    ])
    model = mlflow.pyfunc.load_model(f"models:/{name}/{version}")
    predictions = model.predict(model_input).to_dict(orient="records")
    metrics = compute_metrics(labels, predictions)
    dataset = manifest_sha256(manifest)

    with mlflow.start_run(run_name=f"evaluate-{name}-v{version}") as run:
        mlflow.set_tags({"lifecycle_step": "evaluate", "model_name": name,
                         "model_version": str(version), "dataset_sha256": dataset})
        mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
        mlflow.log_artifact(str(manifest), artifact_path="eval")
        run_id = run.info.run_id

    for key, value in ((TAG_MAE, f"{metrics['mae_um']:.5f}"),
                       (TAG_RMSE, f"{metrics['rmse_um']:.5f}"),
                       (TAG_TYPE_ACC, f"{metrics['type_accuracy']:.5f}"),
                       (TAG_N, str(metrics["n"])),
                       (TAG_DATASET, dataset),
                       (TAG_RUN, run_id)):
        client.set_model_version_tag(name, str(version), key, value)
    return {**metrics, "dataset_sha256": dataset, "run_id": run_id}


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
    p = sub.add_parser("promote")
    p.add_argument("--version", required=True)
    p.add_argument("--alias", required=True)
    p.add_argument("--max-mae", type=float)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("rollback")
    p.add_argument("--alias", required=True)
    p.add_argument("--dry-run", action="store_true")
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
            result = evaluate(client, mlflow, name, args.version, args.manifest)
            print(f"v{args.version}: MAE={result['mae_um']:.3f} µm RMSE={result['rmse_um']:.3f} µm "
                  f"type_acc={result['type_accuracy']:.3f} n={result['n']} run_id={result['run_id']}")
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
