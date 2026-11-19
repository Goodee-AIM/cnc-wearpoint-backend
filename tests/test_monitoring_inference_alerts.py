"""Offline regression tests; do not require a running MySQL or Serving."""
from datetime import datetime

from app.services.monitoring_inference_alerts import inference_alert_values, record_showing_alert

NOW = datetime(2026, 11, 19, 14, 0)


def gate(**kw):
    d = dict(session_id='s', playback_generation=2, cycle_number=3,
             set_number=4, position=5, measurement_id=10)
    d.update(kw)
    return d


def item(**kw):
    d = dict(set_number=4, position=5, measurement_id=10,
             image_name='a.png', sensor_name='a.csv')
    d.update(kw)
    return d


def run(wear=175, **kw):
    d = dict(gate(), run_id='run-123', status='completed',
             predicted_wear_um=wear, predicted_type='flank',
             wear_status='danger' if wear >= 200 else 'warning' if wear >= 150 else 'normal')
    d.update(kw)
    return d


def test_threshold_boundaries_and_model_source():
    assert inference_alert_values(gate(), item(), run(149.999), NOW) is None
    assert inference_alert_values(gate(), item(), run(150), NOW)[10] == 'warning'
    assert inference_alert_values(gate(), item(), run(199.999), NOW)[10] == 'warning'
    values = inference_alert_values(gate(), item(), run(200), NOW)
    assert values[10] == 'danger'
    assert values[6] == 'run-123'
    assert values[7:9] == ('a.png', 'a.csv')
    assert values[14:16] == (150, 200)
    assert values[9] == 'prediction'


def test_reject_mismatch_and_unavailable():
    for changed in [dict(session_id='wrong'), dict(playback_generation=1),
                    dict(cycle_number=2), dict(set_number=5), dict(position=6),
                    dict(measurement_id=11), dict(status='running'),
                    dict(wear_status='danger'), dict(predicted_wear_um=-1),
                    dict(predicted_wear_um=float('nan')), dict(run_id='')]:
        assert inference_alert_values(gate(), item(), run(**changed), NOW) is None
    assert inference_alert_values(gate(), item(measurement_id=11), run(), NOW) is None
    assert inference_alert_values(gate(), item(), None, NOW) is None


def test_sql_insert_is_idempotent_and_uses_the_exact_uuid():
    class Cursor:
        rowcount = 1
        def execute(self, sql, params):
            self.sql, self.params = sql, params
    cursor = Cursor()
    assert record_showing_alert(cursor, gate(), item(), run(175), NOW)
    assert 'ON DUPLICATE KEY UPDATE' in cursor.sql
    assert 'inference_run_id' in cursor.sql
    assert cursor.params[6] == 'run-123'
    cursor.rowcount = 0
    assert record_showing_alert(cursor, gate(), item(), run(175), NOW) is False
