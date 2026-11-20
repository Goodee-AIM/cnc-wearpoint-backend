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
