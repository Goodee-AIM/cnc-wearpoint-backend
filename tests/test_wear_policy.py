"""신규 기준 경계값, 유형별 조치 및 기존 기록 보존 검증."""
import sqlite3
from contextlib import contextmanager
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.routers import alerts, monitoring
from app.core.wear_policy import wear_level, alert_title
from app.services import monitoring_alerts
from test_monitoring import setup
from test_monitoring_alerts import populated, rows


@pytest.mark.parametrize('wear,expected', [
    (None, None), ('NaN', None), ('Infinity', None), (-1, None),
    (0, 'normal'), ('149.999', 'normal'), (150, 'warning'),
    ('199.999', 'warning'), (200, 'danger'), (201, 'danger'),
])
def test_policy_boundaries(wear, expected):
    assert wear_level(wear) == expected


@pytest.mark.parametrize('kind,warning,danger', [
    ('flank', '감속 필요', '공구 교체 필요'),
    ('flank_wear', '감속 필요', '공구 교체 필요'),
    ('adhesion', '공구 점검 필요', '공구 점검 필요'),
    ('adhesion + flank', '공구 점검 필요', '공구 점검 필요'),
    ('flank_wear+adhesion', '공구 점검 필요', '공구 점검 필요'),
    (None, '마모 상태 확인', '마모 상태 확인'),
    ('unsupported', '마모 상태 확인', '마모 상태 확인'),
])
def test_type_advice(kind, warning, danger):
    assert alert_title('warning', kind) == f'경고 · {warning}'
    assert alert_title('danger', kind) == f'위험 · {danger}'


@pytest.mark.parametrize('wear,level', [(149.999, None), (150, 'warning'), (199.999, 'warning'), (200, 'danger')])
def test_worker_uses_new_policy_for_both_sources(populated, wear, level):
    path, _ = populated
    with sqlite3.connect(path) as connection:
        connection.execute('UPDATE wear_labels SET original_wear_um=? WHERE measurement_id=1', (wear,))
        connection.execute("UPDATE predictions SET predicted_wear_um=?, predicted_type='adhesion+flank' WHERE id=701", (wear,))
    monitoring.start()
    events = rows(path)
    assert len(events) == (2 if level else 0)
    for event in events:
        assert event['level'] == level
        assert event['warning_threshold_um'] == 150
        assert event['danger_threshold_um'] == 200
        if event['source'] == 'prediction':
            assert event['original_type'] == 'adhesion+flank'
            assert '공구 점검 필요' in event['message']
        else:
            assert ('공구 교체 필요' if level == 'danger' else '감속 필요') in event['message']
    with sqlite3.connect(path) as connection:
        # 모델 저장 메타데이터와 과거 알림을 소급 변경하지 않습니다.
        assert connection.execute('SELECT warning_threshold_um,danger_threshold_um FROM predictions WHERE id=701').fetchone() == (50, 90)
        assert connection.execute('SELECT level,message FROM alerts WHERE id=1').fetchone() == ('danger', 'legacy (100.00 μm)')


def test_worker_preserves_existing_event_and_acknowledgment(populated):
    path, _ = populated
    monitoring.start()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE monitoring_alert_events SET level='warning',judged_wear_um=60,warning_threshold_um=50,danger_threshold_um=90,message='old policy',detail_confirmed_at='2026-11-11 00:00:00'")
    before = rows(path)
    monitoring_alerts.process_due_alerts()
    assert rows(path) == before


def test_empty_schedule_does_not_raise(populated):
    path, clock = populated
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM monitoring_items')
    wrapped = monitoring_alerts.get_connection()
    cursor = wrapped.cursor(dictionary=True)
    try:
        monitoring_alerts.emit_due_alerts(cursor, {'status': 'running', 'session_id': 'empty', 'elapsed_ms': 0, 'resumed_at': clock[0]}, clock[0])
    finally:
        cursor.close()
        wrapped.close()
    assert rows(path) == []


@pytest.mark.parametrize('source,wear,allowed', [('prediction', 149, False), ('prediction', 150, True), ('prediction', 200, True), ('label', 149, False), ('label', 150, True), ('label', 200, True)])
def test_legacy_create_uses_current_policy(monkeypatch, source, wear, allowed):
    class Cursor:
        def __init__(self):
            self.calls = []
        def execute(self, sql, params):
            self.calls.append((sql, params))
        def fetchone(self):
            if len(self.calls) == 1:
                return dict(predicted_wear_um=Decimal(wear), predicted_type='adhesion', original_wear_um=Decimal(wear), original_type='flank', set_number=4)
            return {'id': 1}
    cursor = Cursor()
    @contextmanager
    def database():
        yield cursor
    monkeypatch.setattr(alerts, 'alert_cursor', database)
    payload = alerts.AlertCreate(prediction_id=1, source=source)
    if not allowed:
        with pytest.raises(HTTPException) as error:
            alerts.create_alert(payload)
        assert error.value.status_code == 422
        assert len(cursor.calls) == 1
    else:
        assert alerts.create_alert(payload) == {'id': 1}
        _, (_, level, message) = cursor.calls[1]
        assert level == ('danger' if wear >= 200 else 'warning')
        assert ('공구 점검 필요' if source == 'prediction' else '공구 교체 필요' if wear >= 200 else '감속 필요') in message
