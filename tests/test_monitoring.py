import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.routers import monitoring
from app.main import app
from app.services.monitoring import build_schedule, sensor_duration


class Cursor:
    """API 트랜잭션 검증용. MySQL 잠금 자체는 별도 실기에서 확인합니다."""
    def __init__(self, connection, clock):
        self.cursor = connection.cursor()
        self.clock = clock
        self.now = False

    def execute(self, sql, parameters=()):
        self.now = "UTC_TIMESTAMP" in sql
        if self.now:
            return
        sql = sql.replace("ON DUPLICATE KEY UPDATE id = 1", "ON CONFLICT(id) DO UPDATE SET id = 1")
        sql = sql.replace("ON DUPLICATE KEY UPDATE id = monitoring_alert_events.id", "ON CONFLICT(session_id,cycle_number,set_number,position) DO NOTHING")
        for field in ("created_at", "detail_confirmed_at"):
            sql = sql.replace(f"TIMESTAMPADD(MINUTE, %s, a.{field})", f"datetime(a.{field}, %s || ' minutes')")
        # 실제 문자셋 충돌은 opt-in MySQL 테스트에서 검증합니다.
        sql = sql.replace(" USING utf8mb4) COLLATE utf8mb4_0900_ai_ci", ")")
        sql = sql.replace("CONVERT(", "mysql_text(")
        sql = sql.replace(" FOR SHARE", "").replace(" FOR UPDATE", "")
        parameters = tuple(
            value.isoformat(sep=" ") if isinstance(value, datetime)
            else float(value) if isinstance(value, Decimal) else value
            for value in parameters
        )
        self.cursor.execute(sql.replace("%s", "?"), parameters)

    def executemany(self, sql, parameters):
        for item in parameters:
            self.cursor.execute("""
                INSERT INTO monitoring_items VALUES
                (:set_number, :position, :measurement_id, :image_name, :sensor_name,
                 :start_ms, :duration_ms, :playback_mode, :message)
            """, item)

    def fetchone(self):
        if self.now:
            return {"now": self.clock[0]}
        row = self.cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        if result.get("resumed_at"):
            result["resumed_at"] = datetime.fromisoformat(result["resumed_at"])
        return result

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]

    def close(self):
        self.cursor.close()


class Connection:
    def __init__(self, path, clock):
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.create_function("CONCAT", -1, lambda *values: "".join(str(value) for value in values))
        self.connection.create_function("mysql_text", 1, lambda value: None if value is None else str(value))
        self.connection.execute("BEGIN IMMEDIATE")
        self.clock = clock

    def cursor(self, dictionary):
        return Cursor(self.connection, self.clock)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    path = tmp_path / "monitoring.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE monitoring_state (
                id INTEGER PRIMARY KEY, session_id TEXT, status TEXT DEFAULT 'idle',
                elapsed_ms INTEGER DEFAULT 0, resumed_at TEXT, revision INTEGER DEFAULT 0
            );
            CREATE TABLE monitoring_items (
                set_number INTEGER, position INTEGER, measurement_id INTEGER,
                image_name TEXT, sensor_name TEXT, start_ms INTEGER, duration_ms INTEGER,
                playback_mode TEXT, message TEXT, PRIMARY KEY (set_number, position)
            );
            CREATE TABLE wear_labels (
                measurement_id INTEGER, original_wear_um REAL, original_type TEXT
            );
            CREATE TABLE predictions (
                id INTEGER PRIMARY KEY, measurement_id INTEGER, predicted_wear_um REAL,
                warning_threshold_um REAL DEFAULT 50, danger_threshold_um REAL DEFAULT 90,
                predicted_at TEXT
            );
            CREATE TABLE alerts (
                id INTEGER PRIMARY KEY, prediction_id INTEGER, level TEXT, message TEXT,
                created_at TEXT, detail_confirmed_at TEXT
            );
            CREATE TABLE monitoring_alert_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, cycle_number INTEGER DEFAULT 1, set_number INTEGER,
                position INTEGER, measurement_id INTEGER, prediction_id INTEGER,
                image_name TEXT, sensor_name TEXT, source TEXT, level TEXT,
                judged_wear_um REAL, predicted_wear_um REAL, original_type TEXT,
                warning_threshold_um REAL, danger_threshold_um REAL,
                message TEXT, created_at TEXT, recorded_at TEXT, detail_confirmed_at TEXT,
                UNIQUE (session_id,cycle_number,set_number,position)
            );
            CREATE TABLE tool_sets (set_id INTEGER, set_number INTEGER);
            CREATE TABLE measurements (
                id INTEGER, set_id INTEGER, image_name TEXT, sensor_name TEXT
            );
            INSERT INTO tool_sets VALUES (1, 4), (2, 11);
            INSERT INTO measurements VALUES
                (1, 1, 'one.jpg', 'one.csv'), (2, 1, 'two.jpg', NULL),
                (3, 2, 'three.jpg', 'three.csv');
        """)
    clock = [datetime(2026, 11, 11, 1, 30)]
    monkeypatch.setattr(monitoring, "get_connection", lambda: Connection(path, clock))
    monkeypatch.setenv("MONITORING_CONTROL_TOKEN", "test-operator-token")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path))
    for number, names in {4: ["one.png", "two.jpg"], 11: ["three.jpg"]}.items():
        folder = tmp_path / f"images/set{number}/original"
        folder.mkdir(parents=True)
        for name in names:
            (folder / name).write_bytes(b"test image")
        sensors = tmp_path / f"sensors/set{number}"
        sensors.mkdir(parents=True)
        duration = 10 if number == 4 else 30
        name = "one.csv" if number == 4 else "three.csv"
        (sensors / name).write_text(
            "1,2,3,4,5,2023-01-01 00:00:00.000000\n"
            f"1,2,3,4,5,2023-01-01 00:00:{duration:02d}.000000\n"
        )
    return path, clock


TOKEN = {"X-Monitoring-Control-Token": "test-operator-token"}


def test_late_join_pause_resume_reset_and_restart(setup):
    _, clock = setup
    with TestClient(app) as client:
        idle = client.get("/api/monitoring/state").json()
        assert idle["status"] == "idle"
        assert len(idle["sets"]) == 8
        first = client.post("/api/monitoring/start", headers=TOKEN).json()
        assert first["status"] == "running"
        assert first["sets"][0]["image_name"] == "one.png"
        assert first["sets"][0]["measurement_id"] == 1
        clock[0] += timedelta(seconds=11)
        second = client.get("/api/monitoring/state").json()
        assert second["sets"][0]["measurement_id"] == 2
        assert second["sets"][0]["elapsed_ms"] == 1000
        assert second["sets"][-1]["elapsed_ms"] == 11000
        paused = client.post("/api/monitoring/pause", headers=TOKEN).json()
        clock[0] += timedelta(minutes=1)
        assert client.get("/api/monitoring/state").json()["elapsed_ms"] == 11000
        resumed = client.post("/api/monitoring/start", headers=TOKEN).json()
        assert resumed["session_id"] == first["session_id"]
        assert resumed["elapsed_ms"] == paused["elapsed_ms"]
    # 다른 클라이언트와 새 DB 연결에서도 같은 저장 상태를 반환합니다.
    with TestClient(app) as client:
        clock[0] += timedelta(seconds=2)
        third = client.get("/api/monitoring/state").json()
        assert third["session_id"] == first["session_id"]
        assert third["sets"][0]["status"] == "completed"
        assert third["sets"][-1]["elapsed_ms"] == 13000
        clock[0] += timedelta(minutes=1)
        done = client.get("/api/monitoring/state").json()
        assert done["status"] == "running"
        assert done["elapsed_ms"] == 73000
        assert done["total_duration_ms"] == 30000
        assert done["cycle_number"] == 3
        assert done["cycle_elapsed_ms"] == 13000
        assert done["sets"][-1]["elapsed_ms"] == 13000
        cleared = client.post("/api/monitoring/reset", headers=TOKEN).json()
        assert cleared["status"] == "running"
        assert cleared["session_id"] != first["session_id"]
        assert cleared["cycle_number"] == 1
        assert cleared["elapsed_ms"] == 0
        assert cleared["sets"][0]["measurement_id"] == 1
        assert client.post("/api/monitoring/start", headers=TOKEN).json()["session_id"] != first["session_id"]


def test_duplicate_start_and_pause_are_idempotent(setup):
    with TestClient(app) as client:
        first = client.post("/api/monitoring/start", headers=TOKEN).json()
        second = client.post("/api/monitoring/start", headers=TOKEN).json()
        assert second == first
        first_pause = client.post("/api/monitoring/pause", headers=TOKEN).json()
        second_pause = client.post("/api/monitoring/pause", headers=TOKEN).json()
        assert second_pause == first_pause


def test_controls_require_operator_token(setup, monkeypatch):
    with TestClient(app) as client:
        assert client.get("/api/monitoring/state").status_code == 200
        for action in ("start", "pause", "reset"):
            assert client.post(f"/api/monitoring/{action}").status_code == 403
        monkeypatch.delenv("MONITORING_CONTROL_TOKEN")
        assert client.post("/api/monitoring/start").status_code == 503


def test_no_data_does_not_create_partial_session(setup):
    path, _ = setup
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM measurements")
    with TestClient(app) as client:
        assert client.post("/api/monitoring/start", headers=TOKEN).status_code == 409
        assert client.get("/api/monitoring/state").json()["status"] == "idle"


def test_simultaneous_start_uses_one_session(setup):
    def start_client(_):
        with TestClient(app) as client:
            response = client.post("/api/monitoring/start", headers=TOKEN)
            assert response.status_code == 200
            return response.json()["session_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        sessions = list(pool.map(start_client, range(2)))
    assert len(set(sessions)) == 1


@pytest.mark.parametrize("contents", [
    "1,2,3,4,5,2023-01-01 00:00:01\n1,2,3,4,5,2023-01-01 00:00:00\n",
    "1,2,nan,4,5,2023-01-01 00:00:00\n",
    "1,2,3,4,5,invalid\n", "1,2,3,4,5\n", "", ",2,3,4,5,2023-01-01 00:00:00\n",
])
def test_invalid_sensor_falls_back_to_two_seconds(tmp_path, monkeypatch, contents):
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path))
    path = tmp_path / "sensors/set4/broken.csv"
    path.parent.mkdir(parents=True)
    path.write_text(contents)
    schedule = build_schedule([
        {"set_number": 4, "measurement_id": 1, "image_name": "one.jpg", "sensor_name": "broken.csv"},
    ], {4: [{"name": "one.png"}]})
    assert schedule[0]["duration_ms"] == 2000
    assert schedule[0]["playback_mode"] == "image_only"


def test_sensor_duration_matches_frontend_millisecond_precision(tmp_path):
    path = tmp_path / "sensor.csv"
    path.write_text(
        "\ufeff1,2,3,4,5,2023-01-01 23:59:59.999900000\n"
        "1,2,3,4,5,2023-01-02 00:00:00.020100000\n",
        encoding="utf-8",
    )
    assert sensor_duration(path) == 21


def test_reset_during_preparation_is_not_overwritten(setup, monkeypatch):
    original = monitoring.build_schedule

    def reset_while_preparing(*args):
        monitoring.reset()
        return original(*args)

    monkeypatch.setattr(monitoring, "build_schedule", reset_while_preparing)
    with TestClient(app) as client:
        response = client.post("/api/monitoring/start", headers=TOKEN)
        assert response.status_code == 409
        state = client.get("/api/monitoring/state").json()
        assert state["status"] == "idle"
        assert state["revision"] == 1


def test_failed_schedule_insert_rolls_back_session(setup, monkeypatch):
    import mysql.connector

    def fail_insert(*args):
        raise mysql.connector.Error("test insert failure", errno=1213)

    monkeypatch.setattr(Cursor, "executemany", fail_insert)
    with TestClient(app) as client:
        assert client.post("/api/monitoring/start", headers=TOKEN).status_code == 503
        state = client.get("/api/monitoring/state").json()
        assert state["status"] == "idle"
        assert state["session_id"] is None


def test_missing_migration_returns_actionable_error(monkeypatch):
    import mysql.connector

    def missing_schema():
        raise mysql.connector.Error("missing table", errno=1146)

    monkeypatch.setattr(monitoring, "get_connection", missing_schema)
    with TestClient(app) as client:
        response = client.get("/api/monitoring/state")
        assert response.status_code == 503
        assert "20261111_monitoring.sql" in response.json()["detail"]
