import sqlite3
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.routers import sets
from app.main import app


@pytest.fixture
def database(monkeypatch):
    cursor = Mock()
    connection = Mock()
    connection.cursor.return_value = cursor
    get_connection = Mock(return_value=connection)
    monkeypatch.setattr(sets, "get_connection", get_connection)
    return connection, cursor, get_connection


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_sets_returns_schema_identifiers(client, database):
    connection, cursor, _ = database
    cursor.fetchall.return_value = [
        {
            "set_id": 24,
            "set_number": 4,
            "set_name": "Set 4",
            "material": "Steel",
            "measurement_count": 2,
        }
    ]

    response = client.get("/api/sets")

    assert response.status_code == 200
    assert response.json()["items"] == cursor.fetchall.return_value
    assert "id" not in response.json()["items"][0]
    connection.cursor.assert_called_once_with(dictionary=True)
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_measurements_returns_original_labels_and_predictions(client, database):
    connection, cursor, _ = database
    cursor.fetchone.side_effect = [
        {"set_id": 24, "set_number": 4, "set_name": "Set 4"},
        {"total": 8},
    ]
    cursor.fetchall.return_value = [
        {
            "measurement_id": 101,
            "image_id": 7,
            "sensor_id": 8,
            "original_wear_um": Decimal("12.34567"),
            "original_type": "flank",
            "prediction_id": 301,
            "predicted_wear_um": Decimal("55.43210"),
            "model_version": "rf-csv-demo-v1",
            "prediction_status": "warning",
            "predicted_at": datetime(2026, 11, 6, 12, 0),
        },
        {
            "measurement_id": 102,
            "image_id": None,
            "sensor_id": 9,
            "original_wear_um": None,
            "original_type": None,
            "prediction_id": None,
            "predicted_wear_um": None,
            "model_version": None,
            "prediction_status": None,
            "predicted_at": None,
        },
    ]

    response = client.get("/api/sets/4/measurements?limit=2&offset=3")

    assert response.status_code == 200
    payload = response.json()
    assert {key: payload[key] for key in ("set_number", "total", "limit", "offset")} == {
        "set_number": 4,
        "total": 8,
        "limit": 2,
        "offset": 3,
    }
    original, unpredicted = payload["items"]
    assert original["image_id"] == 7
    assert original["sensor_id"] == 8
    assert original["original_wear_um"] == 12.34567
    assert original["original_type"] == "flank"
    assert original["predicted_wear_um"] == 55.4321
    assert original["model_version"] == "rf-csv-demo-v1"
    assert original["prediction_status"] == "warning"
    assert original["predicted_at"] == "2026-11-06T12:00:00"
    assert not {"source_image_id", "source_sensor_id", "actual_wear_um", "actual_type"} & original.keys()
    assert unpredicted["image_id"] is None
    assert unpredicted["sensor_id"] == 9
    assert all(
        unpredicted[key] is None
        for key in (
            "original_wear_um", "original_type", "prediction_id", "predicted_wear_um",
            "model_version", "prediction_status", "predicted_at",
        )
    )
    assert [call.args[1] for call in cursor.execute.call_args_list] == [
        (4,), (24,), (24, 2, 3),
    ]
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_measurements_returns_an_empty_page(client, database):
    connection, cursor, _ = database
    cursor.fetchone.side_effect = [
        {"set_id": 24, "set_number": 4, "set_name": "Set 4"},
        {"total": 0},
    ]
    cursor.fetchall.return_value = []

    response = client.get("/api/sets/4/measurements")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
    assert cursor.execute.call_args.args[1] == (24, 200, 0)
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_measurements_returns_404_for_an_unregistered_set(client, database):
    connection, cursor, _ = database
    cursor.fetchone.return_value = None

    response = client.get("/api/sets/4/measurements")

    assert response.status_code == 404
    assert response.json() == {"detail": "등록되지 않은 Set입니다."}
    assert cursor.execute.call_count == 1
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("url", [
    "/api/sets/3/measurements",
    "/api/sets/12/measurements",
    "/api/sets/4/measurements?limit=0",
    "/api/sets/4/measurements?limit=501",
    "/api/sets/4/measurements?offset=-1",
])
def test_invalid_measurement_request_does_not_open_database(client, database, url):
    _, _, get_connection = database

    response = client.get(url)

    assert response.status_code == 422
    get_connection.assert_not_called()


@pytest.mark.parametrize("url", ["/api/sets", "/api/sets/4/measurements"])
def test_query_failure_closes_database_resources(client, database, url):
    connection, cursor, _ = database
    cursor.execute.side_effect = RuntimeError("database query failed")

    with pytest.raises(RuntimeError, match="database query failed"):
        client.get(url)

    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_actual_queries_select_latest_predictions_and_page_by_internal_set_id(client, monkeypatch):
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row

    class DictCursor:
        def __init__(self):
            self.cursor = connection.cursor()

        def execute(self, query, params=()):
            self.cursor.execute(query.replace("%s", "?"), params)

        def fetchone(self):
            row = self.cursor.fetchone()
            return dict(row) if row is not None else None

        def fetchall(self):
            return [dict(row) for row in self.cursor.fetchall()]

        def close(self):
            self.cursor.close()

    class ConnectionAdapter:
        def cursor(self, dictionary=False):
            assert dictionary
            return DictCursor()

        def close(self):
            pass  # Keep the in-memory fixture alive between API requests.

    monkeypatch.setattr(sets, "get_connection", ConnectionAdapter)
    try:
        connection.executescript("""
            CREATE TABLE tool_sets (
                set_id INTEGER PRIMARY KEY, set_number INTEGER, set_name TEXT, material TEXT
            );
            CREATE TABLE measurements (
                id INTEGER PRIMARY KEY, set_id INTEGER, measurement_key TEXT,
                image_name TEXT, image_path TEXT, sensor_name TEXT, sensor_path TEXT,
                image_id INTEGER, sensor_id INTEGER, image_captured_at TEXT,
                sensor_started_at TEXT, sensor_ended_at TEXT, status TEXT
            );
            CREATE TABLE wear_labels (
                measurement_id INTEGER, original_wear_um REAL, original_type TEXT
            );
            CREATE TABLE predictions (
                id INTEGER PRIMARY KEY, measurement_id INTEGER, predicted_wear_um REAL,
                predicted_type TEXT, model_version TEXT, status TEXT, predicted_at TEXT
            );
            INSERT INTO tool_sets VALUES
                (24, 4, 'Set 4', 'Steel'), (4, 5, 'Set 5', 'Steel'), (30, 3, 'Set 3', 'Steel');
            INSERT INTO measurements (id, set_id, measurement_key, image_id, sensor_id, status)
            VALUES (101, 24, 'sensor-only', NULL, 2, 'ready'),
                   (102, 24, 'image-only', 1, NULL, 'completed'),
                   (201, 4, 'other-set', 0, 0, 'completed');
            INSERT INTO wear_labels VALUES (102, 12.34567, 'flank');
            INSERT INTO predictions VALUES
                (999, 102, 80, 'older', 'old', 'warning', '2026-11-05 12:00:00'),
                (300, 102, 50, 'flank', 'v2', 'warning', '2026-11-06 12:00:00'),
                (301, 102, 55, 'flank', 'v3', 'warning', '2026-11-06 12:00:00');
        """)

        set_response = client.get("/api/sets")
        assert set_response.status_code == 200
        assert [(row["set_id"], row["measurement_count"]) for row in set_response.json()["items"]] == [
            (24, 2), (4, 1),
        ]

        first_response = client.get("/api/sets/4/measurements?limit=1&offset=0")
        second_response = client.get("/api/sets/4/measurements?limit=1&offset=1")
        empty_response = client.get("/api/sets/4/measurements?limit=1&offset=2")
        assert [response.status_code for response in (first_response, second_response, empty_response)] == [200] * 3
        first, second, empty = [response.json() for response in (first_response, second_response, empty_response)]
        assert [page["total"] for page in (first, second, empty)] == [2, 2, 2]
        assert [first["items"][0]["measurement_id"], second["items"][0]["measurement_id"]] == [102, 101]
        assert empty["items"] == []
        predicted = first["items"][0]
        assert predicted["original_wear_um"] == 12.34567
        assert predicted["original_type"] == "flank"
        assert predicted["prediction_id"] == 301
        assert predicted["predicted_wear_um"] == 55.0
        assert predicted["model_version"] == "v3"
        assert predicted["prediction_status"] == "warning"
        assert predicted["predicted_at"] == "2026-11-06 12:00:00"
        unpredicted = second["items"][0]
        assert unpredicted["image_id"] is None and unpredicted["sensor_id"] == 2
        assert all(unpredicted[key] is None for key in (
            "original_wear_um", "original_type", "prediction_id", "predicted_wear_um",
            "model_version", "prediction_status", "predicted_at",
        ))
    finally:
        connection.close()
