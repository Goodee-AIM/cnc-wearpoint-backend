"""Pure projection/advance tests, no SQL backend or Serving required."""
from datetime import datetime, timedelta
from unittest.mock import Mock
from app.services import monitoring_playback_gate as gate

NOW = datetime(2026, 11, 19, 12, 0, 0)


def row(**changes):
    value = {'set_number': 4, 'session_id': 'session', 'playback_generation': 2,
             'cycle_number': 3, 'position': 5, 'measurement_id': 10,
             'phase': 'playing', 'phase_elapsed_ms': 0,
             'phase_started_at': NOW - timedelta(seconds=5)}
    value.update(changes)
    return value


def item(**changes):
    value = {'set_number': 4, 'position': 5, 'measurement_id': 10,
             'image_name': 'a.png', 'sensor_name': 'a.csv',
             'playback_mode': 'sensor', 'duration_ms': 1000}
    value.update(changes)
    return value


def test_elapsed_does_not_increase_when_paused():
    assert gate.elapsed_ms(row(phase_elapsed_ms=100), NOW) == 5100
    assert gate.elapsed_ms(row(phase_elapsed_ms=100), NOW, False) == 100
    assert gate.elapsed_ms(row(phase_elapsed_ms=100, phase_started_at=None), NOW) == 100


def test_projection_uses_same_measurement_and_cycle_and_does_not_fabricate_result():
    baseline = {'status': 'running', 'session_id': 'session', 'playback_generation': 2,
                'sets': [{'set_number': 4, 'status': 'running', 'total': 12}]}
    projected = gate.project_gated_state(baseline, [item()], {4: row()}, NOW)
    output = projected['sets'][0]
    assert output['measurement_id'] == 10
    assert output['image_url'] == '/api/images/set4/a.png'
    assert output['cycle_number'] == 3
    assert output['playback_phase'] == 'playing'
    assert output['result_visible'] is False
    assert output['elapsed_ms'] == 1000
    assert gate.project_gated_state(baseline, [item()], {4: row(measurement_id=999)}, NOW)['sets'][0]['status'] == 'empty'
    assert gate.project_gated_state(baseline, [item()], {4: row(playback_generation=1)}, NOW)['sets'][0]['status'] == 'empty'


def test_waiting_and_showing_stay_on_same_image():
    baseline = {'status': 'running', 'session_id': 'session', 'playback_generation': 2,
                'sets': [{'set_number': 4, 'status': 'running', 'total': 12}]}
    for phase, visible in [('waiting', False), ('showing', True)]:
        shown = gate.project_gated_state(baseline, [item()], {4: row(phase=phase)}, NOW)['sets'][0]
        assert shown['image_name'] == 'a.png'
        assert shown['elapsed_ms'] == 1000
        assert shown['result_visible'] == visible


class Cursor:
    def __init__(self, rows, state=None, result=None):
        self.state = state or {'status': 'running', 'session_id': 'session', 'playback_generation': 2}
        self.rows = rows
        self.result = result
        self.last = None
        self.updates = []
        self.rowcount = 1
        self.now = NOW
    def execute(self, sql, params=()):
        self.last = sql
        if 'UPDATE monitoring_playback_gates SET' in sql:
            self.updates.append((sql, params))
    def fetchone(self):
        if 'monitoring_state' in self.last:
            return self.state
        if 'UTC_TIMESTAMP' in self.last:
            return {'now': self.now}
        if 'monitoring_inference_runs' in self.last:
            return self.result
        raise AssertionError(self.last)
    def fetchall(self):
        if 'monitoring_items' in self.last:
            return [item(), item(position=6, measurement_id=11, image_name='b.png', sensor_name='b.csv')]
        if 'monitoring_playback_gates' in self.last:
            return self.rows
        raise AssertionError(self.last)


def test_playback_finishes_but_waits_for_its_own_inference_result():
    c = Cursor([row()])
    assert gate.advance_gates(c) == 1
    assert c.updates[0][1][0] == 'waiting'
    assert c.updates[0][1][3:6] == (5, 10, 3)


def test_completion_shows_for_three_seconds_then_next_measurement():
    c = Cursor([row()], result={'status': 'completed'})
    assert gate.advance_gates(c) == 1
    assert c.updates[0][1][0] == 'showing'
    c = Cursor([row(phase='showing', phase_started_at=NOW - timedelta(milliseconds=2999))])
    assert gate.advance_gates(c) == 0
    c.now += timedelta(milliseconds=1)
    assert gate.advance_gates(c) == 1
    assert c.updates[0][1][0] == 'playing'
    assert c.updates[0][1][3:6] == (6, 11, 3)


def test_last_measurement_wraps_to_new_cycle():
    c = Cursor([row(phase='showing', position=6, measurement_id=11,
                    phase_started_at=NOW - timedelta(seconds=4))])
    assert gate.advance_gates(c) == 1
    assert c.updates[0][1][3:6] == (5, 10, 4)


def test_failure_does_not_deadlock_its_set():
    c = Cursor([row(phase='waiting', phase_started_at=None)], result={'status': 'failed'})
    assert gate.advance_gates(c) == 1
    assert c.updates[0][1][0] == 'showing'


def test_paused_global_state_does_not_advance_any_set():
    c = Cursor([row()], state={'status': 'paused', 'session_id': 'session', 'playback_generation': 2})
    assert gate.advance_gates(c) == 0
    assert c.updates == []
