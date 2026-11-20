from datetime import datetime, timedelta
from unittest.mock import patch

from app.services.playback_speed import PLAYBACK_RATE, scaled_elapsed_ms
from app.services import monitoring
from app.services import monitoring_playback_gate as gates

NOW = datetime(2026, 11, 20, 0, 0, 20)


def gate(phase="playing", elapsed=0, ago=20):
    return dict(set_number=4, session_id="session", playback_generation=1,
                cycle_number=1, position=0, measurement_id=10, phase=phase,
                phase_elapsed_ms=elapsed, phase_started_at=NOW - timedelta(seconds=ago))


def schedule():
    return [dict(set_number=4, position=0, measurement_id=10, duration_ms=40000,
                 playback_mode="sensor", sensor_name="sample.csv", image_name="sample.png"),
            dict(set_number=4, position=1, measurement_id=11, duration_ms=40000,
                 playback_mode="sensor", sensor_name="next.csv", image_name="next.png")]


def test_replay_rate_is_two():
    assert PLAYBACK_RATE == 2
    assert scaled_elapsed_ms(0, NOW - timedelta(seconds=20), NOW) == 40000


def test_pause_resume_does_not_rescale_accumulated_source_time():
    paused = gate(elapsed=12000)
    paused["phase_started_at"] = None
    assert gates.elapsed_ms(paused, NOW) == 12000
    resumed = {**paused, "phase_started_at": NOW - timedelta(seconds=1)}
    assert gates.elapsed_ms(resumed, NOW) == 14000
    assert gates.elapsed_ms(resumed, NOW, is_running=False) == 12000


def test_showing_hold_is_three_real_seconds():
    assert gates.RESULT_HOLD_MS == 3000
    assert gates.elapsed_ms(gate("showing", ago=2), NOW) == 2000
    assert gates.elapsed_ms(gate("showing", ago=3), NOW) == 3000


def test_negative_clock_delta_is_clamped():
    assert scaled_elapsed_ms(500, NOW + timedelta(seconds=5), NOW) == 500


def test_legacy_clock_also_runs_two_times_and_pauses():
    state = dict(status="running", elapsed_ms=1000, resumed_at=NOW - timedelta(seconds=5))
    assert monitoring.elapsed_ms(state, NOW) == 11000
    assert monitoring.elapsed_ms({**state, "status": "paused"}, NOW) == 1000


def test_projection_advertises_rate_and_keeps_original_duration():
    base = dict(session_id="session", playback_generation=1, status="running",
                sets=[dict(set_number=4, total=2)])
    projected = gates.project_gated_state(base, schedule(), {4: gate(ago=10)}, NOW)
    item = projected["sets"][0]
    assert projected["playback_rate"] == 2
    assert item["playback_rate"] == 2
    assert item["elapsed_ms"] == 20000
    assert item["duration_ms"] == 40000
    assert not item["result_visible"]


class Cursor:
    def __init__(self, current, run_status="completed"):
        self.current, self.run_status = current, run_status
        self.rowcount = 1
        self.query = ""
        self.transitions = []

    def execute(self, sql, params=None):
        self.query = " ".join(sql.split())
        if "SET phase=%s" in self.query:
            self.transitions.append(params)

    def fetchone(self):
        if "monitoring_state" in self.query:
            return dict(session_id="session", playback_generation=1, status="running")
        if "UTC_TIMESTAMP" in self.query:
            return dict(now=NOW)
        if "monitoring_inference_runs" in self.query:
            return dict(status=self.run_status) if self.run_status else None
        raise AssertionError(self.query)

    def fetchall(self):
        if "monitoring_items" in self.query:
            return schedule()
        if "monitoring_playback_gates" in self.query:
            return [self.current]
        raise AssertionError(self.query)


def test_twenty_real_seconds_finishes_forty_second_sensor():
    cursor = Cursor(gate(ago=20))
    with patch.object(gates, 'record_showing_alert'):
        assert gates.advance_gates(cursor) == 1
    assert cursor.transitions[0][0] == "showing"


def test_unfinished_inference_still_waits_after_faster_playback():
    cursor = Cursor(gate(ago=20), run_status="running")
    assert gates.advance_gates(cursor) == 1
    assert cursor.transitions[0][0] == "waiting"


def test_result_does_not_advance_after_only_two_real_seconds():
    cursor = Cursor(gate("showing", ago=2))
    assert gates.advance_gates(cursor) == 0
    assert cursor.transitions == []


def test_result_advances_after_three_real_seconds():
    cursor = Cursor(gate("showing", ago=3))
    assert gates.advance_gates(cursor) == 1
    transition = cursor.transitions[0]
    assert transition[0] == "playing"
    assert transition[3:5] == (1, 11)
