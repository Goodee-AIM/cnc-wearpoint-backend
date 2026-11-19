"""Offline unit tests; never connect to MySQL, Object Storage or Serving."""
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from app.services import monitoring_inference_queue as q


IDENTITY = ('session-a', 2, 3, 4, 7, 101)


def state(status='running', generation=2, cycle=3, session='session-a'):
    return {'status': status, 'session_id': session,
            'playback_generation': generation, 'cycle_number': cycle}


def item(status='running', measurement_id=101, position=7):
    return {'status': status, 'set_number': 4, 'position': position,
            'measurement_id': measurement_id, 'playback_mode': 'sensor',
            'image_name': 'one.png', 'sensor_name': 'one.csv'}


def run():
    return dict(zip(('session_id', 'playback_generation', 'cycle_number',
                     'set_number', 'position', 'measurement_id'), IDENTITY)) | {
        'run_id': 'fixed-uuid', 'image_name': 'one.png', 'sensor_name': 'one.csv'
    }


def test_identity_fences_other_images_sessions_cycles_and_restarts():
    assert q.occurrence_identity(state(), item()) == IDENTITY
    assert q.matching_run(IDENTITY, run())
    for field, changed in [('session_id', 'session-b'),
                           ('playback_generation', 3), ('cycle_number', 4),
                           ('set_number', 5), ('position', 8),
                           ('measurement_id', 102)]:
        other = run()
        other[field] = changed
        assert not q.matching_run(IDENTITY, other), field


def test_paused_same_occurrence_is_not_discarded():
    assert q.occurrence_identity(state('paused'), item('paused')) == IDENTITY
    assert q.occurrence_identity(state('idle'), item()) is None
    assert q.occurrence_identity(state(), item('completed')) is None
    assert q.occurrence_identity(state(), item() | {'sensor_name': None}) is None



def test_canonical_input_keys_and_filename_validation(monkeypatch):
    """DB의 실제 경로를 우선 사용하며 잘못된 경로를 거부한다."""

    paths = {
        "image_path": "images/set4/original/one.png",
        "sensor_path": "sensors/set4/one.csv",
        "set_number": 4,
    }

    class FakeCursor:
        def execute(self, sql, params):
            assert "measurements" in sql
            assert "image_path" in sql
            assert "sensor_path" in sql
            assert params == (101,)

        def fetchone(self):
            return paths.copy()

    monkeypatch.setattr(
        q,
        "_transaction",
        lambda fn: fn(FakeCursor()),
    )

    # 원본 이름이 JPG여도 DB의 PNG 경로를 사용한다.
    result = q._keys(run() | {"image_name": "one.jpg"})

    assert result == (
        "images/set4/original/one.png",
        "sensors/set4/one.csv",
    )

    # 잘못된 이미지 경로 차단
    for invalid_path in (
        "../steal.png",
        "images/set5/original/one.png",
        "images/set4/original/bad.webp",
        "images/set4/original/../../bad.png",
        "MATWI/Set4/images/one.jpg",
    ):
        paths["image_path"] = invalid_path

        with pytest.raises(ValueError):
            q._keys(run())

    paths["image_path"] = "images/set4/original/one.png"

    # 잘못된 센서 경로 차단
    for invalid_path in (
        "../steal.csv",
        "sensors/set5/one.csv",
        "sensors/set4/bad.png",
    ):
        paths["sensor_path"] = invalid_path

        with pytest.raises(ValueError):
            q._keys(run())

    paths["sensor_path"] = "sensors/set4/one.csv"

    # 측정 데이터가 다른 Set에 속한 경우
    paths["set_number"] = 5

    with pytest.raises(ValueError):
        q._keys(run())

    paths["set_number"] = 4

    # 허용되지 않은 Set 번호
    with pytest.raises(ValueError):
        q._keys(run() | {"set_number": 12})

    # 이미지 경로가 없는 경우
    paths["image_path"] = None

    with pytest.raises(ValueError):
        q._keys(run())



def test_queue_worker_never_calls_serving_when_run_is_stale(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(q, 'inference_slots', fake)
    fake.acquire.return_value = True
    @contextmanager
    def gate():
        yield True
    monkeypatch.setattr(q, '_serving_gate', gate)
    monkeypatch.setattr(q, '_recover_interrupted_runs', lambda: 0)
    monkeypatch.setattr(q, '_claim_next', lambda: run())
    monkeypatch.setattr(q, '_is_current', lambda row: False)
    serving = Mock()
    finish = Mock()
    monkeypatch.setattr(q, 'request_serving_prediction', serving)
    monkeypatch.setattr(q, '_finish', finish)
    assert q.process_one() is True
    serving.assert_not_called()
    finish.assert_called_once_with(run(), 'cancelled', error_code='STALE_OCCURRENCE')
    fake.release.assert_called_once()



def test_queue_processes_one_current_run_and_passes_result(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(q, "inference_slots", fake)
    fake.acquire.return_value = True

    @contextmanager
    def gate():
        yield True

    monkeypatch.setattr(q, "_serving_gate", gate)
    monkeypatch.setattr(q, "_recover_interrupted_runs", lambda: 0)
    monkeypatch.setattr(q, "_claim_next", lambda: run())
    monkeypatch.setattr(q, "_is_current", lambda row: True)

    # DB 경로 조회는 별도 테스트에서 검증하므로 여기서는 Mock 사용
    image_key = "images/set4/original/one.png"
    sensor_key = "sensors/set4/one.csv"

    monkeypatch.setattr(
        q,
        "_keys",
        lambda row: (image_key, sensor_key),
    )

    prediction = {"predicted_wear_um": 123}

    serving = Mock(return_value=prediction)

    monkeypatch.setattr(
        q,
        "request_serving_prediction",
        serving,
    )

    finish = Mock()
    monkeypatch.setattr(q, "_finish", finish)

    assert q.process_one() is True

    # AI Serving에 정확한 파일 경로 전달
    serving.assert_called_once_with(
        image_key,
        sensor_key,
    )

    # 추론 성공 결과가 완료 처리 함수로 전달
    finish.assert_called_once_with(
        run(),
        "completed",
        result=prediction,
    )

    fake.release.assert_called_once()



def test_busy_slot_never_claims_queue(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(q, 'inference_slots', fake)
    fake.acquire.return_value = False
    claim = Mock()
    monkeypatch.setattr(q, '_claim_next', claim)
    assert q.process_one() is False
    claim.assert_not_called()
    fake.release.assert_not_called()


def test_cross_worker_gate_is_respected(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(q, 'inference_slots', fake)
    fake.acquire.return_value = True
    @contextmanager
    def gate():
        yield False
    monkeypatch.setattr(q, '_serving_gate', gate)
    claim = Mock()
    monkeypatch.setattr(q, '_claim_next', claim)
    assert q.process_one() is False
    claim.assert_not_called()
    fake.release.assert_called_once()


def test_snapshot_fencing_applies_inside_completion_transaction(monkeypatch):
    row = run()
    monkeypatch.setattr(q, '_snapshot', lambda cursor: (state(generation=99), {4: item()}))
    validate = Mock()
    monkeypatch.setattr(q, 'validate_model_result', validate)
    executed = []
    class Cursor:
        rowcount = 1
        def execute(self, sql, params):
            executed.append((sql, params))
    monkeypatch.setattr(q, '_transaction', lambda fn: fn(Cursor()))
    q._finish(row, 'completed', result={'predicted_wear_um': 1})
    assert 'status = %s' in executed[0][0]
    assert executed[0][1][0] == 'cancelled'
    assert executed[0][1][1] == 'STALE_OCCURRENCE'
    validate.assert_not_called()


def test_successful_result_written_only_for_current_identity(monkeypatch):
    row = run()
    monkeypatch.setattr(q, '_snapshot', lambda cursor: (state(), {4: item()}))
    monkeypatch.setattr(q, 'validate_model_result', lambda _: (123, 'flank_wear', 'model', '1', 'normal'))
    executed = []
    class Cursor:
        rowcount = 1
        def execute(self, sql, params):
            executed.append((sql, params))
    monkeypatch.setattr(q, '_transaction', lambda fn: fn(Cursor()))
    q._finish(row, 'completed', result={'anything': True})
    assert "status = 'completed'" in executed[0][0]
    assert executed[0][1][-1] == 'fixed-uuid'


def test_read_endpoint_is_disabled_by_default(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.delenv('MONITORING_INFERENCE_ENABLED', raising=False)
    with TestClient(app) as client:
        assert client.get('/api/monitoring/inference/current').status_code == 503


def test_read_endpoint_uses_fenced_results_only_when_enabled(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.routers import monitoring_inference
    monkeypatch.setenv('MONITORING_INFERENCE_ENABLED', '1')
    monkeypatch.setattr(monitoring_inference, 'current_runs', lambda: {'enabled': True, 'runs': []})
    # Do not start the worker in this test: app lifespan uses the same flag.
    client = TestClient(app)
    response = client.get('/api/monitoring/inference/current')
    assert response.status_code == 200
    assert response.json() == {'enabled': True, 'runs': []}
