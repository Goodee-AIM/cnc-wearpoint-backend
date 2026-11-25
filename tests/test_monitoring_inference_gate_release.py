"""No external MySQL, Object Storage, or Serving: advisory lock release tests."""

import pytest

from app.services import monitoring_inference_queue as queue


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.pending = False
        self.sql = ""
        self.fetchone_count = 0
        self.closed = False

    def execute(self, sql, params):
        assert params == ("cnc_wp_monitoring_queue",)
        assert "GET_LOCK" in sql or "RELEASE_LOCK" in sql
        assert not self.pending, "Unread result found before executing a new SELECT"
        self.sql = sql
        self.pending = True

    def fetchone(self):
        assert self.pending, "No unread SELECT result"
        self.pending = False
        self.fetchone_count += 1
        if "GET_LOCK" in self.sql:
            return {"acquired": self.connection.acquire_result}
        return {"released": 1}

    def close(self):
        # Simulate mysql.connector's non-buffered cursor contract.
        if self.pending:
            raise RuntimeError("Unread result found")
        self.closed = True


class Connection:
    def __init__(self, acquire_result):
        self.acquire_result = acquire_result
        self.cursors = []
        self.closed = False

    def cursor(self, *, dictionary):
        assert dictionary is True
        cursor = Cursor(self)
        self.cursors.append(cursor)
        return cursor

    def close(self):
        self.closed = True


@pytest.mark.parametrize("acquire_result", [0, 1])
def test_gate_consumes_each_select_result(monkeypatch, acquire_result):
    connection = Connection(acquire_result)
    monkeypatch.setattr(queue, "get_connection", lambda: connection)
    with queue._serving_gate() as acquired:
        assert acquired is bool(acquire_result)
    assert connection.closed
    assert len(connection.cursors) == (2 if acquire_result else 1)
    assert all(cursor.closed for cursor in connection.cursors)
    assert all(cursor.fetchone_count == 1 for cursor in connection.cursors)
    if acquire_result:
        assert "RELEASE_LOCK" in connection.cursors[-1].sql


def test_gate_releases_lock_even_if_work_raises(monkeypatch):
    connection = Connection(1)
    monkeypatch.setattr(queue, "get_connection", lambda: connection)
    with pytest.raises(ValueError, match="simulated worker error"):
        with queue._serving_gate() as acquired:
            assert acquired is True
            raise ValueError("simulated worker error")
    assert connection.closed
    assert len(connection.cursors) == 2
    assert all(cursor.closed for cursor in connection.cursors)
    assert connection.cursors[-1].fetchone_count == 1
