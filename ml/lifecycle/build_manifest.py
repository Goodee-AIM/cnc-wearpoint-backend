"""Build an evaluation manifest for model_lifecycle.py from MATWI labels.

Read-only with respect to the dataset: source images/CSVs are never moved,
renamed, modified or created. Rows with missing labels or files are EXCLUDED
(and reported), never filled in.

    python ml/lifecycle/build_manifest.py \
        --labels  ../matwi-research/data/raw/labels.csv \
        --sets    ../matwi-research/data/raw/sets.csv \
        --storage-root storage --set 4 9 11 16 \
        --out ml/lifecycle/eval/test_sets_manifest.csv [--check-sensors]

Path mapping rule (verified 2026-11-21 against ./storage):
    labels.ImageFile  MATWI/Set{N}/images/{ImageName}
      -> {storage-root}/Set{N}/Set{N}/images/{ImageName}
    labels.SensorFile MATWI/Set{N}/sensordata/{SensorName}
      -> {storage-root}/Set{N}/Set{N}/sensordata/{SensorName}

The per-set crop comes from sets.csv (the crop used in training). It is written
to the manifest because Serving's fixed ROI does not match every set (e.g. Set16).
"""
import argparse
import collections
import csv
import os
import sys
from pathlib import Path

MANIFEST_COLUMNS = [
    "set", "image_id", "sensor_id", "image_path", "sensor_path", "wear_um", "type",
    "crop_left", "crop_top", "crop_right", "crop_bottom",
]


def _set_number(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def read_crops(sets_csv: Path) -> dict[int, tuple[int, int, int, int]]:
    crops = {}
    with sets_csv.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("") or row.get(next(iter(row))) or "").strip()  # "Set 4"
            if not name.lower().startswith("set"):
                continue
            number = _set_number(name[3:].strip())
            parts = [p.strip() for p in (row.get("crop") or "").split(",")]
            if number is not None and len(parts) == 4 and all(p.lstrip("-").isdigit() for p in parts):
                crops[number] = tuple(int(p) for p in parts)
    return crops


def storage_path(root: Path, set_no: int, kind: str, file_name: str) -> Path:
    return root / f"Set{set_no}" / f"Set{set_no}" / kind / file_name


def _serving_sensor_reader():
    """Serving's own read_and_cut_sensor (ml/serving/preprocessing.py).

    Using the real function keeps this check identical to live Serving,
    including nanosecond timestamps and cutting-segment detection. The module
    imports torch/torchvision at top level but read_and_cut_sensor only needs
    numpy/pandas/scipy, so empty stand-ins are used when torch is absent.
    """
    import importlib
    import types

    serving_dir = str(Path(__file__).resolve().parents[1] / "serving")
    if serving_dir not in sys.path:
        sys.path.insert(0, serving_dir)
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401
    except ImportError:
        sys.modules.setdefault("torch", types.ModuleType("torch"))
        vision = sys.modules.setdefault("torchvision", types.ModuleType("torchvision"))
        vision.transforms = types.ModuleType("torchvision.transforms")
    return importlib.import_module("preprocessing").read_and_cut_sensor


def sensor_problem(path: Path, reader) -> str | None:
    """None if Serving would accept the CSV, else Serving's own error."""
    try:
        reader(str(path))
    except ValueError as exc:
        return str(exc)
    return None


def build(labels_csv: Path, sets_csv: Path, root: Path, sets: list[int], check_sensors: bool):
    from PIL import Image

    crops = read_crops(sets_csv)
    reader = _serving_sensor_reader() if check_sensors else None
    manifest, excluded, problems = [], [], []
    with labels_csv.open(newline="", encoding="utf-8-sig") as f:
        labels = [r for r in csv.DictReader(f) if _set_number(r.get("Set")) in sets]

    for row in labels:
        set_no = _set_number(row["Set"])
        image, sensor = row["ImageName"].strip(), row["SensorName"].strip()
        wear, wear_type = row["wear"].strip(), row["type"].strip()
        base = {"set": set_no, "image_id": row["ImageID"], "image": image, "sensor": sensor}
        reasons = [msg for ok, msg in ((image, "ImageName 없음"), (sensor, "SensorName 없음"),
                                       (wear, "wear 없음"), (wear_type, "type 없음")) if not ok]
        if reasons:
            excluded.append({**base, "reason": ", ".join(reasons)})
            continue
        if set_no not in crops:
            excluded.append({**base, "reason": "sets.csv에 crop 없음"})
            continue
        image_path = storage_path(root, set_no, "images", image)
        sensor_path = storage_path(root, set_no, "sensordata", sensor)
        missing = [msg for p, msg in ((image_path, "이미지 파일 없음"), (sensor_path, "센서 파일 없음"))
                   if not p.is_file()]
        if missing:
            excluded.append({**base, "reason": ", ".join(missing)})
            continue
        manifest.append({
            "set": set_no,
            "image_id": int(float(row["ImageID"])),
            "sensor_id": int(float(row["SensorID"])),
            "image_path": image_path,
            "sensor_path": sensor_path,
            "wear_um": float(wear),
            "type": wear_type,
            **dict(zip(("crop_left", "crop_top", "crop_right", "crop_bottom"), crops[set_no])),
        })

    manifest.sort(key=lambda r: (r["set"], r["image_id"]))

    # ---- validation (report only; never fixes data)
    for key in ("image_path", "sensor_path"):
        for path, n in collections.Counter(r[key] for r in manifest).items():
            if n > 1:
                problems.append(f"duplicate {key}: {path} x{n}")
    for r in manifest:
        if r["wear_um"] < 0:
            problems.append(f"negative wear: {r['image_path']}")
        with Image.open(r["image_path"]) as im:
            width, height = im.size
        if r["crop_right"] > width or r["crop_bottom"] > height:
            problems.append(f"crop outside {width}x{height}: {r['image_path']}")
        if check_sensors:
            issue = sensor_problem(r["sensor_path"], reader)
            if issue:
                problems.append(f"sensor rejected by Serving rules ({issue}): {r['sensor_path']}")

    # Files present in storage but not referenced by labels (informational).
    unreferenced = []
    for set_no in sets:
        referenced = {(r["ImageName"].strip(), r["SensorName"].strip())
                      for r in labels if _set_number(r["Set"]) == set_no}
        ref_images = {i for i, _ in referenced}
        ref_sensors = {s for _, s in referenced}
        for kind, names in (("images", ref_images), ("sensordata", ref_sensors)):
            folder = root / f"Set{set_no}" / f"Set{set_no}" / kind
            if folder.is_dir():
                unreferenced += [str(folder / n) for n in sorted(os.listdir(folder)) if n not in names]
            else:
                problems.append(f"missing folder: {folder}")
    return manifest, excluded, problems, unreferenced


def write_outputs(out: Path, manifest, excluded):
    out.parent.mkdir(parents=True, exist_ok=True)
    base = out.resolve().parent
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for r in manifest:
            writer.writerow({**r,
                             "image_path": Path(os.path.relpath(r["image_path"], base)).as_posix(),
                             "sensor_path": Path(os.path.relpath(r["sensor_path"], base)).as_posix()})
    report = out.with_name(out.stem + "_excluded.csv")
    with report.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["set", "image_id", "image", "sensor", "reason"])
        writer.writeheader()
        writer.writerows(excluded)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--sets", required=True, type=Path)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--set", required=True, type=int, nargs="+", dest="set_numbers")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--check-sensors", action="store_true",
                        help="Also apply Serving's sensor CSV rules (slower).")
    args = parser.parse_args(argv)

    root = args.storage_root.resolve()
    if args.out.resolve().is_relative_to(root):
        parser.error("--out must be outside --storage-root (dataset stays read-only)")

    manifest, excluded, problems, unreferenced = build(
        args.labels, args.sets, root, args.set_numbers, args.check_sensors)
    report = write_outputs(args.out, manifest, excluded)

    print(f"manifest: {args.out} ({len(manifest)} rows)")
    print(f"excluded: {report} ({len(excluded)} rows)")
    for set_no in args.set_numbers:
        rows = [r for r in manifest if r["set"] == set_no]
        types = dict(collections.Counter(r["type"] for r in rows))
        crop = rows[0] and (rows[0]["crop_left"], rows[0]["crop_top"],
                            rows[0]["crop_right"], rows[0]["crop_bottom"]) if rows else None
        print(f"  Set{set_no}: {len(rows)} rows, excluded "
              f"{sum(e['set'] == set_no for e in excluded)}, crop={crop}, types={types}")
    print(f"storage files not referenced by labels: {len(unreferenced)}")
    for path in unreferenced[:20]:
        print(f"  {path}")
    if problems:
        print(f"VALIDATION FAILED ({len(problems)}):", file=sys.stderr)
        for p in problems[:50]:
            print(f"  {p}", file=sys.stderr)
        return 1
    print("validation: OK (files exist, no duplicates, crop within image bounds"
          + (", sensors pass Serving rules" if args.check_sensors else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
