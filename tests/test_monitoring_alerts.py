import asyncio
import importlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.routers import monitoring
from app.main import app
from app.services import monitoring_alerts
from test_monitoring import Connection, TOKEN, setup


@pytest.fixture
def populated(setup, monkeypatch):
    path, clock = setup
    monkeypatch.setenv("LEGACY_ALERTS_UTC_OFFSET_MINUTES", "540")
    monkeypatch.setattr(monitoring_alerts, "get_connection", lambda: Connection(path, clock))
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            INSERT INTO wear_labels VALUES
                (1,60,'flank_wear'),(2,100,'adhesion'),(3,120,'flank_wear');
            INSERT INTO predictions VALUES
                (501,2,20,50,90,'2026-11-11 00:00:00'),
                (701,3,95,50,90,'2026-11-11 00:00:00');
            INSERT INTO alerts VALUES
                (1,501,'danger','legacy (100.00 μm)','2026-11-11 10:00:00',NULL);
        """)
    return path, clock


def rows(path):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute("SELECT * FROM monitoring_alert_events ORDER BY id")]


def test_worker_generates_all_sets_without_browser_and_does_not_duplicate(populated):
    path, clock = populated
    started = monitoring.start()
    assert len(rows(path)) == 2
    clock[0] += timedelta(seconds=25)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: monitoring_alerts.process_due_alerts(), range(2)))
    events = rows(path)
    assert len(events) == 3
    assert {row["set_number"] for row in events} == {4, 11}
    assert {row["session_id"] for row in events} == {started["session_id"]}
    label_only = next(row for row in events if row["measurement_id"] == 1)
    assert label_only["prediction_id"] is None
    assert label_only["judged_wear_um"] == 60
    caught_up = next(row for row in events if row["measurement_id"] == 2)
    assert datetime.fromisoformat(caught_up["created_at"]) == clock[0] - timedelta(seconds=15)
    assert datetime.fromisoformat(caught_up["recorded_at"]) == clock[0]
    assert caught_up["level"] == "danger"  # label 100, prediction 20


def test_pause_flushes_before_stopping_and_reset_preserves_history(populated):
    path, clock = populated
    first = monitoring.start()
    clock[0] += timedelta(seconds=11)
    monitoring.pause()
    assert len(rows(path)) == 3
    clock[0] += timedelta(minutes=1)
    monitoring_alerts.process_due_alerts()
    assert len(rows(path)) == 3
    monitoring.reset()
    assert len(rows(path)) == 3
    second = monitoring.start()
    assert second["session_id"] != first["session_id"]
    monitoring_alerts.process_due_alerts()
    assert len(rows(path)) == 5


def test_reset_flushes_missed_events_and_reuses_schedule(populated):
    path, clock = populated
    monitoring.start()
    clock[0] += timedelta(seconds=11)
    monitoring.reset()
    assert len(rows(path)) == 3
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM monitoring_items").fetchone()[0] == 3


def test_prediction_added_later_is_recorded_for_reached_measurement(populated):
    path, _ = populated
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM predictions WHERE id = 701")
    monitoring.start()
    assert len(rows(path)) == 1
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO predictions VALUES (702,3,92,50,90,'2026-11-11 01:00:00')")
    monitoring_alerts.process_due_alerts()
    assert len(rows(path)) == 2
    assert any(row["prediction_id"] == 702 for row in rows(path))


def test_common_feed_has_current_session_events_and_same_counts(populated):
    monitoring.start()
    with TestClient(app) as a, TestClient(app) as b:
        first = a.get("/api/monitoring/alerts").json()
        second = b.get("/api/monitoring/alerts").json()
    assert first == second
    assert first["total"] == first["unread"] == 2
    assert len(first["items"]) == 2
    assert all(row["id"] != "legacy:1" for row in first["items"])
    label_only = next(row for row in first["items"] if row["prediction_id"] is None)
    assert label_only["source"] == "label"
    assert label_only["can_acknowledge"] is False
    assert all(row["session_id"] == first["session_id"] for row in first["items"])
    assert all(row["created_at"].endswith("+00:00") for row in first["items"])


def test_acknowledgment_is_shared_idempotent_and_keeps_occurrence_time(populated):
    _, clock = populated
    monitoring.start()
    with TestClient(app) as client:
        feed = client.get("/api/monitoring/alerts").json()
        event = next(row for row in feed["items"] if row["source"] == "prediction")
        created_at = event["created_at"]
        clock[0] += timedelta(seconds=3)
        first = client.patch(f"/api/monitoring/alerts/{event['id']}/acknowledge")
        assert first.status_code == 200
        clock[0] += timedelta(seconds=3)
        second = client.patch(f"/api/monitoring/alerts/{event['id']}/acknowledge")
        assert first.json() == second.json()
        assert first.json()["created_at"] == created_at
        assert first.json()["detail_confirmed_at"] != created_at
        shared = client.get("/api/monitoring/alerts").json()
        assert shared["total"] == 2 and shared["unread"] == 1
        label_only = next(row for row in feed["items"] if row["prediction_id"] is None)
        assert client.patch(f"/api/monitoring/alerts/{label_only['id']}/acknowledge").status_code == 422
        assert client.patch("/api/monitoring/alerts/bad-id/acknowledge").status_code == 400
        assert client.patch("/api/monitoring/alerts/monitoring:999/acknowledge").status_code == 404


def test_legacy_confirmation_updates_original_record_and_keeps_created_at(populated):
    path, clock = populated
    with TestClient(app) as client:
        first = client.patch("/api/monitoring/alerts/legacy:1/acknowledge").json()
        clock[0] += timedelta(seconds=5)
        second = client.patch("/api/monitoring/alerts/legacy:1/acknowledge").json()
    assert first == second
    assert first["created_at"].startswith("2026-11-11T01:00:00")
    with sqlite3.connect(path) as connection:
        created, confirmed = connection.execute("SELECT created_at, detail_confirmed_at FROM alerts WHERE id = 1").fetchone()
    assert created == "2026-11-11 10:00:00"
    assert confirmed.startswith("2026-11-11 10:30:00")


def test_pagination_caps_keep_new_insertions_from_shifting_pages(populated):
    _, clock = populated
    monitoring.start()
    with TestClient(app) as client:
        first = client.get("/api/monitoring/alerts?limit=1").json()
        clock[0] += timedelta(seconds=11)
        monitoring_alerts.process_due_alerts()
        caps = {"event_max_id": first["event_max_id"], "legacy_max_id": first["legacy_max_id"]}
        second = client.get("/api/monitoring/alerts", params={**caps, "limit": 500, "offset": 1}).json()
        assert first["total"] == second["total"] == 2
        assert len({row["id"] for row in first["items"] + second["items"]}) == 2
        assert client.get("/api/monitoring/alerts").json()["total"] == 3


def test_worker_lifespan_starts_without_browser_requests_and_stops(monkeypatch):
    main = importlib.import_module("app.main")
    monkeypatch.setenv("MONITORING_ALERT_WORKER_ENABLED", "1")
    started = threading.Event()
    stopped = threading.Event()

    async def run(stop):
        started.set()
        await stop.wait()
        stopped.set()

    monkeypatch.setattr(main, "run_alert_worker", run)
    with TestClient(app):
        assert started.wait(timeout=1)
    assert stopped.is_set()


def test_worker_recovers_after_transient_database_failure(monkeypatch):
    calls = []
    stop = asyncio.Event()

    def process():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporary DB failure")
        # worker의 대기를 테스트에서 즉시 해제합니다.

    async def wait_for(awaitable, timeout):
        awaitable.close()
        if len(calls) == 1:
            raise TimeoutError
        stop.set()

    monkeypatch.setattr(monitoring_alerts, "process_due_alerts", process)
    monkeypatch.setattr(monitoring_alerts.asyncio, "wait_for", wait_for)
    asyncio.run(monitoring_alerts.run_alert_worker(stop))
    assert len(calls) == 2


def test_label_event_becomes_confirmable_when_prediction_arrives_later(populated):
    path, _ = populated
    monitoring.start()
    with TestClient(app) as client:
        before = client.get("/api/monitoring/alerts").json()
        event = next(row for row in before["items"] if row["measurement_id"] == 1)
        assert not event["can_acknowledge"]
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO predictions VALUES (900,1,45,50,90,'2026-11-11 02:00:00')")
        after = client.get("/api/monitoring/alerts").json()
        changed = next(row for row in after["items"] if row["id"] == event["id"])
        assert after["total"] == before["total"]
        assert changed["can_acknowledge"]
        assert changed["prediction_id"] == 900
        assert changed["predicted_wear_um"] == 45
        acknowledged = client.patch(f"/api/monitoring/alerts/{event['id']}/acknowledge")
        assert acknowledged.status_code == 200
        assert acknowledged.json()["created_at"] == event["created_at"]
    stored = next(row for row in rows(path) if row["measurement_id"] == 1)
    assert stored["prediction_id"] == 900
    assert stored["detail_confirmed_at"] is not None


def test_cycles_keep_occurrences_and_confirmations_separate(populated):
    path, clock = populated
    started = monitoring.start()
    with TestClient(app) as client:
        first = next(row for row in client.get('/api/monitoring/alerts').json()['items']
                     if row['source'] == 'prediction')
        assert first['cycle_number'] == 1
        assert client.patch(f"/api/monitoring/alerts/{first['id']}/acknowledge").status_code == 200
        clock[0] += timedelta(seconds=30)
        state = client.get('/api/monitoring/state').json()
        assert state['session_id'] == started['session_id']
        assert state['cycle_number'] == 2
        assert state['cycle_elapsed_ms'] == 0
        assert all(row['position'] == row['elapsed_ms'] == 0 for row in state['sets'] if row['total'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: monitoring_alerts.process_due_alerts(), range(2)))
        events = [row for row in client.get('/api/monitoring/alerts').json()['items']
                  if row['source'] == 'prediction']
        assert len(events) == 2
        older = next(row for row in events if row['cycle_number'] == 1)
        newer = next(row for row in events if row['cycle_number'] == 2)
        assert older['id'] != newer['id']
        assert older['measurement_id'] == newer['measurement_id']
        assert older['detail_confirmed_at'] is not None
        assert newer['detail_confirmed_at'] is None
        assert datetime.fromisoformat(newer['created_at']) - datetime.fromisoformat(older['created_at']) == timedelta(seconds=30)
    assert len(rows(path)) == 5


def test_worker_catches_up_cycles_and_pause_keeps_absolute_clock(populated):
    path, clock = populated
    started = monitoring.start()
    clock[0] += timedelta(seconds=71)
    monitoring_alerts.process_due_alerts()
    assert len(rows(path)) == 9
    assert {row['cycle_number'] for row in rows(path)} == {1, 2, 3}
    paused = monitoring.pause()
    assert paused['elapsed_ms'] == 71000
    assert paused['cycle_number'] == 3
    clock[0] += timedelta(minutes=10)
    monitoring_alerts.process_due_alerts()
    assert len(rows(path)) == 9
    assert monitoring.get_state()['elapsed_ms'] == 71000
    resumed = monitoring.start()
    assert resumed['session_id'] == started['session_id']
    assert resumed['cycle_number'] == 3
    clock[0] += timedelta(seconds=19)
    monitoring_alerts.process_due_alerts()
    assert monitoring.get_state()['cycle_number'] == 4
    assert len(rows(path)) == 11
    latest = [row for row in rows(path) if row['cycle_number'] == 4]
    assert all(datetime.fromisoformat(row['created_at']) == clock[0] for row in latest)
    monitoring.reset()
    assert len(rows(path)) == 11
    new = monitoring.start()
    assert new['cycle_number'] == 1
    assert new['session_id'] != started['session_id']


def test_reset_restarts_cycle_and_counts_without_deleting_history_or_scanning_csv(populated, monkeypatch):
    path, clock = populated
    original = monitoring.start()
    with TestClient(app) as client:
        feed = client.get("/api/monitoring/alerts").json()
        event = next(row for row in feed["items"] if row["prediction_id"] is not None)
        assert client.patch(f"/api/monitoring/alerts/{event['id']}/acknowledge").status_code == 200
        clock[0] += timedelta(seconds=61)
        monitoring_alerts.process_due_alerts()
        before = rows(path)
        assert {row["cycle_number"] for row in before} == {1, 2, 3}
        monitoring.pause()

        def unexpected_scan(*args, **kwargs):
            pytest.fail("reset must reuse the prepared schedule")

        monkeypatch.setattr(monitoring, "build_schedule", unexpected_scan)
        reset = client.post("/api/monitoring/reset", headers=TOKEN).json()
        assert reset["status"] == "running"
        assert reset["cycle_number"] == 1
        assert reset["elapsed_ms"] == reset["cycle_elapsed_ms"] == 0
        assert reset["session_id"] != original["session_id"]
        assert reset["total_duration_ms"] == original["total_duration_ms"]
        assert rows(path) == before
        empty = client.get("/api/monitoring/alerts").json()
        assert empty["session_id"] == reset["session_id"]
        assert empty["total"] == empty["unread"] == 0
        assert empty["items"] == []
        assert monitoring.start()["session_id"] == reset["session_id"]

        # No browser request creates the next occurrences: the server worker does.
        monitoring_alerts.process_due_alerts()
        new = client.get("/api/monitoring/alerts").json()
        assert new["total"] == new["unread"] == 2
        assert all(row["detail_confirmed_at"] is None for row in new["items"])
        assert all(row["session_id"] == reset["session_id"] for row in new["items"])
        assert len(rows(path)) == len(before) + 2
        assert rows(path)[:len(before)] == before


def test_session_reset_between_pages_returns_conflict(populated):
    monitoring.start()
    with TestClient(app) as client:
        first = client.get("/api/monitoring/alerts?limit=1").json()
        monitoring.reset()
        response = client.get("/api/monitoring/alerts", params={
            "limit": 1, "offset": 1, "session_id": first["session_id"],
            "event_max_id": first["event_max_id"], "legacy_max_id": first["legacy_max_id"],
        })
        assert response.status_code == 409
        assert client.get("/api/monitoring/alerts").json()["total"] == 0


def test_reset_without_schedule_has_empty_counts_and_first_start_keeps_new_session(populated):
    with TestClient(app) as client:
        assert client.get("/api/monitoring/alerts").json()["total"] == 0
        reset = monitoring.reset()
        assert reset["status"] == "idle"
        assert reset["cycle_number"] == 1
        assert reset["session_id"]
        assert client.get("/api/monitoring/alerts").json()["total"] == 0
        assert monitoring.start()["session_id"] == reset["session_id"]
