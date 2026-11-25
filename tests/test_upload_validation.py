"""Upload validation must reject what Serving would reject (no DB/Storage)."""

import io
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from PIL import Image

from app.api.routers.measurements import (
    MIN_SENSOR_ROWS,
    validate_image_dimensions,
    validate_sensor_csv,
)

START = datetime(2026, 1, 1, 0, 0, 0)
STEP = timedelta(microseconds=609)


def csv_bytes(timestamps):
    return "".join(
        f"0.0,0.1,0.2,0.3,0.4,{ts.isoformat(sep=' ')}\n" for ts in timestamps
    ).encode()


def regular(n):
    return [START + STEP * i for i in range(n)]


def png(width, height, fmt="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height)).save(buffer, format=fmt)
    return buffer.getvalue()


def test_valid_sensor_csv_at_minimum_rows():
    rows, started, ended = validate_sensor_csv(csv_bytes(regular(MIN_SENSOR_ROWS)))
    assert rows == MIN_SENSOR_ROWS
    assert started == START
    assert ended == START + STEP * (MIN_SENSOR_ROWS - 1)


def test_too_few_rows_rejected():
    with pytest.raises(HTTPException) as error:
        validate_sensor_csv(csv_bytes(regular(MIN_SENSOR_ROWS - 1)))
    assert error.value.status_code == 422


def test_duplicate_timestamp_rejected():
    timestamps = regular(MIN_SENSOR_ROWS)
    timestamps[100] = timestamps[99]
    with pytest.raises(HTTPException) as error:
        validate_sensor_csv(csv_bytes(timestamps))
    assert error.value.status_code == 422


def test_backwards_timestamp_rejected():
    timestamps = regular(MIN_SENSOR_ROWS)
    timestamps[100], timestamps[101] = timestamps[101], timestamps[100]
    with pytest.raises(HTTPException) as error:
        validate_sensor_csv(csv_bytes(timestamps))
    assert error.value.status_code == 422


def test_irregular_interval_rejected():
    timestamps = regular(MIN_SENSOR_ROWS)
    timestamps[200:] = [ts + timedelta(microseconds=1) for ts in timestamps[200:]]
    with pytest.raises(HTTPException) as error:
        validate_sensor_csv(csv_bytes(timestamps))
    assert error.value.status_code == 422


@pytest.mark.parametrize("size", [(600, 400), (1750, 1070), (1920, 1080)])
def test_supported_image_sizes(size):
    assert validate_image_dimensions(png(*size)) == size


def test_jpeg_is_supported():
    assert validate_image_dimensions(png(600, 400, fmt="JPEG")) == (600, 400)


@pytest.mark.parametrize("size", [(800, 600), (1749, 1080), (1920, 1069), (400, 600)])
def test_unsupported_image_sizes_rejected(size):
    with pytest.raises(HTTPException) as error:
        validate_image_dimensions(png(*size))
    assert error.value.status_code == 422


def test_truncated_image_rejected():
    data = png(600, 400)
    with pytest.raises(HTTPException) as error:
        validate_image_dimensions(data[: len(data) // 2])
    assert error.value.status_code == 422


# --- nanosecond timestamps (regression for v0.1.12 rejecting MATWI originals)

from datetime import timezone
from pathlib import Path
import importlib
import sys
import types

REPO = Path(__file__).resolve().parents[1]
NS_START = 1_676_544_756_908_050_000  # 2023-02-16 10:52:36.908050000 (ns since epoch)
NS_STEP = 616_312                      # 616.312 µs, as in Set4 originals


def ns_text(ns):
    seconds, fraction = divmod(ns, 1_000_000_000)
    base = datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return f"{base}.{fraction:09d}"


def ns_csv(stamps_ns):
    return "".join(f"0.0,0.1,0.2,0.3,0.4,{ns_text(ns)}\n" for ns in stamps_ns).encode()


def ns_regular(n):
    return [NS_START + NS_STEP * i for i in range(n)]


def rejected(data):
    with pytest.raises(HTTPException) as error:
        validate_sensor_csv(data)
    assert error.value.status_code == 422
    return error.value.detail


def test_nanosecond_regular_interval_accepted():
    # Truncated to µs these intervals alternate 616/617 µs; at ns they are equal.
    stamps = ns_regular(MIN_SENSOR_ROWS)
    truncated = {(b // 1000) - (a // 1000) for a, b in zip(stamps, stamps[1:])}
    assert truncated == {616, 617}
    rows, started, _ = validate_sensor_csv(ns_csv(stamps))
    assert rows == MIN_SENSOR_ROWS
    # Returned start time keeps the existing µs-precision datetime.
    assert started == datetime(2023, 2, 16, 10, 52, 36, 908050)


def test_nanosecond_duplicate_rejected():
    stamps = ns_regular(MIN_SENSOR_ROWS)
    stamps[300] = stamps[299]
    assert "중복" in rejected(ns_csv(stamps))


def test_nanosecond_backwards_rejected():
    stamps = ns_regular(MIN_SENSOR_ROWS)
    stamps[300], stamps[301] = stamps[301], stamps[300]
    assert "시간순" in rejected(ns_csv(stamps))


@pytest.mark.parametrize("shift_ns", [2, 1_000, 616_312])  # 2 ns jitter .. one missing sample
def test_nanosecond_irregular_interval_rejected(shift_ns):
    stamps = ns_regular(MIN_SENSOR_ROWS)
    stamps[400:] = [ns + shift_ns for ns in stamps[400:]]
    detail = rejected(ns_csv(stamps))
    assert "간격이 일정하지 않습니다" in detail and "401번째 행" in detail


def test_invalid_timestamp_value_rejected():
    lines = ns_csv(ns_regular(MIN_SENSOR_ROWS)).decode().splitlines(keepends=True)
    lines[10] = "0.0,0.1,0.2,0.3,0.4,2023-02-30 10:52:36.908050000\n"
    rejected("".join(lines).encode())


def test_mixed_timezone_rejected():
    lines = csv_bytes(regular(MIN_SENSOR_ROWS)).decode().splitlines(keepends=True)
    lines[10] = lines[10].rstrip("\n") + "+09:00\n"
    assert "시간대" in rejected("".join(lines).encode())


def _matwi_files(set_no, limit=3):
    folder = REPO / "storage" / f"Set{set_no}" / f"Set{set_no}" / "sensordata"
    return sorted(folder.glob("*.csv"))[:limit] if folder.is_dir() else []


@pytest.mark.parametrize("set_no", [4, 9, 11])
def test_matwi_original_sensor_csv_accepted(set_no):
    files = _matwi_files(set_no)
    if not files:
        pytest.skip(f"local MATWI Set{set_no} originals not present under storage/")
    for path in files:
        rows, _, _ = validate_sensor_csv(path.read_bytes())
        assert rows >= MIN_SENSOR_ROWS, path.name


def _serving_timestamp_verdict(data: bytes, tmp_path, monkeypatch) -> bool:
    """True if Serving's own read_and_cut_sensor accepts the timestamps.

    Serving later fails on cutting-segment detection for synthetic signals;
    only its timestamp errors decide the verdict here.
    """
    # Stand-ins are scoped to this test (monkeypatch restores sys.modules/sys.path).
    monkeypatch.syspath_prepend(str(REPO / "ml" / "serving"))
    monkeypatch.delitem(sys.modules, "preprocessing", raising=False)
    try:
        import torch  # noqa: F401
    except ImportError:
        vision = types.ModuleType("torchvision")
        vision.transforms = types.ModuleType("torchvision.transforms")
        monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
        monkeypatch.setitem(sys.modules, "torchvision", vision)
    read_and_cut_sensor = importlib.import_module("preprocessing").read_and_cut_sensor
    monkeypatch.delitem(sys.modules, "preprocessing")
    path = tmp_path / "s.csv"
    path.write_bytes(data)
    try:
        read_and_cut_sensor(str(path))
    except ValueError as exc:
        return "timestamp" not in str(exc)
    return True


@pytest.mark.parametrize("case", ["regular", "dup", "back", "shift1", "shift2", "shift1us", "gap"])
def test_interval_verdict_matches_serving(case, tmp_path, monkeypatch):
    stamps = ns_regular(MIN_SENSOR_ROWS)
    if case == "dup":
        stamps[300] = stamps[299]
    elif case == "back":
        stamps[300], stamps[301] = stamps[301], stamps[300]
    elif case.startswith("shift") or case == "gap":
        shift = {"shift1": 1, "shift2": 2, "shift1us": 1_000, "gap": NS_STEP}[case]
        stamps[400:] = [ns + shift for ns in stamps[400:]]
    data = ns_csv(stamps)
    try:
        validate_sensor_csv(data)
        backend_ok = True
    except HTTPException:
        backend_ok = False
    assert backend_ok == _serving_timestamp_verdict(data, tmp_path, monkeypatch)
