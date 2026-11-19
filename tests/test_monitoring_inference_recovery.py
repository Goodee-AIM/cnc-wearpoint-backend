"""No database or Serving calls; mocked recovery and queue scheduling."""
from contextlib import contextmanager
from unittest.mock import Mock

from app.services import monitoring_inference_queue as q


def test_recovery_marks_only_abandoned_running_jobs_as_failed(monkeypatch):
    executed = []
    class Cursor:
        rowcount = 2
        def execute(self, sql, args=None):
            executed.append((sql, args))
    monkeypatch.setattr(q, '_transaction', lambda fn: fn(Cursor()))
    assert q._recover_interrupted_runs() == 2
    assert len(executed) == 1
    sql, args = executed[0]
    assert args is None
    assert "WHERE status = 'running'" in sql
    assert "SET status = 'failed'" in sql
    assert "WORKER_INTERRUPTED" in sql
    assert 'UTC_TIMESTAMP(6)' in sql
    assert 'DELETE' not in sql.upper()
    assert "status = 'queued'" not in sql


def test_recovery_runs_inside_cross_worker_lock_before_claim(monkeypatch):
    order = []
    slots = Mock()
    slots.acquire.return_value = True
    monkeypatch.setattr(q, 'inference_slots', slots)
    @contextmanager
    def acquired_lock():
        order.append('lock')
        yield True
        order.append('unlock')
    monkeypatch.setattr(q, '_serving_gate', acquired_lock)
    monkeypatch.setattr(q, '_recover_interrupted_runs', lambda: order.append('recover') or 1)
    monkeypatch.setattr(q, '_claim_next', lambda: order.append('claim') or None)
    assert q.process_one() is False
    assert order == ['lock', 'recover', 'claim', 'unlock']
    slots.release.assert_called_once()


def test_no_recovery_when_global_lock_is_unavailable(monkeypatch):
    slots = Mock()
    slots.acquire.return_value = True
    monkeypatch.setattr(q, 'inference_slots', slots)
    @contextmanager
    def unavailable():
        yield False
    monkeypatch.setattr(q, '_serving_gate', unavailable)
    recover = Mock()
    claim = Mock()
    monkeypatch.setattr(q, '_recover_interrupted_runs', recover)
    monkeypatch.setattr(q, '_claim_next', claim)
    assert q.process_one() is False
    recover.assert_not_called()
    claim.assert_not_called()
    slots.release.assert_called_once()


def test_no_recovery_when_process_slot_is_busy(monkeypatch):
    slots = Mock()
    slots.acquire.return_value = False
    monkeypatch.setattr(q, 'inference_slots', slots)
    recover = Mock()
    monkeypatch.setattr(q, '_recover_interrupted_runs', recover)
    assert q.process_one() is False
    recover.assert_not_called()
    slots.release.assert_not_called()


def test_recovery_error_does_not_claim_or_serve(monkeypatch):
    slots = Mock()
    slots.acquire.return_value = True
    monkeypatch.setattr(q, 'inference_slots', slots)
    @contextmanager
    def acquired():
        yield True
    monkeypatch.setattr(q, '_serving_gate', acquired)
    def broken():
        raise RuntimeError('DB unavailable')
    monkeypatch.setattr(q, '_recover_interrupted_runs', broken)
    claim = Mock()
    serving = Mock()
    monkeypatch.setattr(q, '_claim_next', claim)
    monkeypatch.setattr(q, 'request_serving_prediction', serving)
    import pytest
    with pytest.raises(RuntimeError, match='DB unavailable'):
        q.process_one()
    claim.assert_not_called()
    serving.assert_not_called()
    slots.release.assert_called_once()


def test_recovery_does_not_change_completed_rows_or_enqueue_duplicates():
    import inspect
    code = inspect.getsource(q._recover_interrupted_runs)
    assert "UPDATE monitoring_inference_runs" in code
    assert "WHERE status = 'running'" in code
    assert 'INSERT INTO' not in code
    assert 'DELETE FROM' not in code
