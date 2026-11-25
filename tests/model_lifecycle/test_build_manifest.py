"""Offline tests for ml/lifecycle/build_manifest.py on a tiny fake dataset."""
import csv
import importlib.util
from pathlib import Path

import pytest
from PIL import Image

PATH = Path(__file__).resolve().parents[2] / "ml" / "lifecycle" / "build_manifest.py"
spec = importlib.util.spec_from_file_location("build_manifest_under_test", PATH)
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)

LABEL_HEADER = ["ImageName", "SensorName", "Set", "ImageID", "SensorID", "wear", "type",
                "ImageDateTime", "SensorDateTime", "ImageFile", "SensorFile"]


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / "storage"
    for kind in ("images", "sensordata"):
        (root / "Set16" / "Set16" / kind).mkdir(parents=True)
    Image.new("RGB", (2400, 2500)).save(root / "Set16/Set16/images/a.jpg")
    (root / "Set16/Set16/sensordata/a.csv").write_text("x\n", encoding="utf-8")
    Image.new("RGB", (2400, 2500)).save(root / "Set16/Set16/images/b.jpg")  # sensor file absent

    def row(img, sen, iid, wear, wtype):
        return [img, sen, "16", iid, iid, wear, wtype, "", "",
                f"MATWI/Set16/images/{img}", f"MATWI/Set16/sensordata/{sen}"]

    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(LABEL_HEADER)
        w.writerow(row("a.jpg", "a.csv", "0.0", "90.0", "flank_wear+adhesion"))
        w.writerow(row("b.jpg", "b.csv", "1.0", "120.0", "flank_wear"))   # missing sensor file
        w.writerow(row("", "c.csv", "2.0", "", ""))                       # missing labels
    sets = tmp_path / "sets.csv"
    sets.write_text(',Vc,crop\nSet 16,150,"1790, 2045, 2390, 2445"\n', encoding="utf-8")
    return tmp_path, root, labels, sets


def test_maps_paths_uses_set_crop_and_excludes_without_inventing(dataset):
    tmp, root, labels, sets = dataset
    manifest, excluded, problems, unreferenced = bm.build(labels, sets, root, [16], False)
    assert len(manifest) == 1
    row = manifest[0]
    assert row["image_path"] == root / "Set16/Set16/images/a.jpg"
    assert row["sensor_path"] == root / "Set16/Set16/sensordata/a.csv"
    assert (row["crop_left"], row["crop_top"], row["crop_right"], row["crop_bottom"]) == (1790, 2045, 2390, 2445)
    assert row["type"] == "flank_wear+adhesion"  # label kept verbatim
    reasons = sorted(e["reason"] for e in excluded)
    assert reasons == ["ImageName 없음, wear 없음, type 없음", "센서 파일 없음"]
    assert problems == []
    assert unreferenced == []


def test_crop_outside_image_is_reported(dataset):
    tmp, root, labels, sets = dataset
    sets.write_text(',crop\nSet 16,"1790, 2045, 9000, 9000"\n', encoding="utf-8")
    _, _, problems, _ = bm.build(labels, sets, root, [16], False)
    assert any("crop outside" in p for p in problems)


def test_output_inside_storage_is_refused(dataset):
    tmp, root, labels, sets = dataset
    with pytest.raises(SystemExit):
        bm.main(["--labels", str(labels), "--sets", str(sets), "--storage-root", str(root),
                 "--set", "16", "--out", str(root / "manifest.csv")])
    assert not (root / "manifest.csv").exists()


def test_written_manifest_is_readable_by_evaluate(dataset):
    tmp, root, labels, sets = dataset
    out = tmp / "eval" / "m.csv"
    assert bm.main(["--labels", str(labels), "--sets", str(sets), "--storage-root", str(root),
                    "--set", "16", "--out", str(out)]) == 0
    lc_spec = importlib.util.spec_from_file_location(
        "lc_for_manifest", PATH.parent / "model_lifecycle.py")
    lc = importlib.util.module_from_spec(lc_spec)
    lc_spec.loader.exec_module(lc)
    rows = lc.read_manifest(out)
    assert rows[0]["image_path"] == str((root / "Set16/Set16/images/a.jpg").resolve())
    assert rows[0]["crop"] == (1790, 2045, 2390, 2445)
