import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.sensors import router
from app.services.cutting_segment import describe_cutting_segment

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def post(data, name="sensor.csv"):
    return client.post("/api/sensors/cutting-segment", files={
        "sensor_csv": (name, data, "text/csv"),
    })


def test_manual_matches_existing_python_algorithm():
    rng = np.random.default_rng(10)
    count = 2000
    fx, fy = rng.normal(0, .01, (2, count))
    fx[500:1500] += 5 * np.sin(np.arange(1000) * .3)
    fy[500:1500] += 3 * np.cos(np.arange(1000) * .3)
    timestamps = pd.date_range("2026-01-01", periods=count, freq="1ms")
    data = pd.DataFrame({0: np.zeros(count), 1: np.zeros(count), 2: fx,
                         3: fy, 4: np.zeros(count), 5: timestamps}).to_csv(
                             index=False, header=False).encode()
    response = post(data)
    assert response.status_code == 200
    assert response.json() == describe_cutting_segment(data)
    assert .4 < response.json()["start_seconds"] < .6
    assert 1.4 < response.json()["end_seconds"] < 1.6
    assert response.json()["window_ms"] == 50
    assert response.json()["min_duration_ms"] == 100


def test_empty_csv_rejected():
    assert post(b"").status_code == 422


def test_wrong_extension_rejected():
    assert post(b"invalid", "sensor.txt").status_code == 422


def test_invalid_columns_rejected():
    assert post(b"1,2,3\n").status_code == 422


def test_invalid_timestamp_rejected():
    assert post(b"1,2,3,4,5,invalid\n").status_code == 422


def test_missing_file_rejected():
    assert client.post("/api/sensors/cutting-segment").status_code == 422


def test_oversized_file_rejected():
    assert post(b"0" * (20 * 1024 * 1024 + 1)).status_code == 413
