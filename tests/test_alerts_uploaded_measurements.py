"""Regression: alerts from uploads (set_id=NULL) must stay visible."""

import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import alerts


def test_alerts_list_includes_upload_with_no_set(monkeypatch):
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE tool_sets (set_id INTEGER PRIMARY KEY, set_number INTEGER);
        CREATE TABLE measurements (
            id INTEGER PRIMARY KEY, set_id INTEGER,
            image_name TEXT, sensor_name TEXT
        );
        CREATE TABLE predictions (
            id INTEGER PRIMARY KEY, measurement_id INTEGER,
            predicted_wear_um REAL, predicted_type TEXT
        );
        CREATE TABLE alerts (
            id INTEGER PRIMARY KEY, prediction_id INTEGER,
            level TEXT, message TEXT, created_at TEXT,
            detail_confirmed_at TEXT
        );
        CREATE TABLE wear_labels (measurement_id INTEGER, original_type TEXT);
        INSERT INTO tool_sets VALUES (7,7);
        INSERT INTO measurements VALUES
            (319,7,'dataset.png','dataset.csv'),
            (1024,NULL,'upload.png','upload.csv');
        INSERT INTO predictions VALUES
            (901,319,201.0,'flank_wear'),
            (902,1024,205.0,'flank_wear');
        INSERT INTO alerts VALUES
            (91,901,'danger','Dataset warning','2026-11-18 10:00:00',NULL),
            (92,902,'danger','Uploaded warning','2026-11-18 11:00:00',NULL);
        """
    )

    class CursorAdapter:
        def __init__(self):
            self.cursor = db.cursor()

        def execute(self, query, params=()):
            self.cursor.execute(query.replace("%s", "?"), params)

        def fetchall(self):
            return [dict(row) for row in self.cursor.fetchall()]

        def close(self):
            self.cursor.close()

    class DBAdapter:
        def cursor(self, dictionary=False):
            assert dictionary
            return CursorAdapter()

        def commit(self):
            db.commit()

        def rollback(self):
            db.rollback()

        def close(self):
            pass

    monkeypatch.setattr(alerts, "get_connection", DBAdapter)
    app = FastAPI()
    app.include_router(alerts.router)
    try:
        with TestClient(app) as client:
            response = client.get("/api/alerts")
        assert response.status_code == 200
        items = response.json()["items"]
        assert [item["id"] for item in items] == [92, 91]
        assert items[0]["set_number"] is None
        assert items[0]["image_name"] == "upload.png"
        assert items[1]["set_number"] == 7
    finally:
        db.close()
