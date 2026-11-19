"""Persist a warning only when the exact inference occurrence starts showing.

Called inside the same transaction and monitoring_state/gate locks as a
playing/waiting -> showing transition. Never substitutes ground-truth labels
or the latest prediction for a different visit of the same measurement.
"""
from decimal import Decimal, InvalidOperation

from app.core.wear_policy import WARNING_UM, DANGER_UM, wear_level, alert_title


IDENTITY_COLUMNS = (
    'session_id', 'playback_generation', 'cycle_number', 'set_number',
    'position', 'measurement_id',
)


def inference_alert_values(gate, item, run, now):
    """Return a stable INSERT tuple or None if no valid warning exists."""
    if not run or run.get('status') != 'completed':
        return None
    if any(gate.get(key) != run.get(key) for key in IDENTITY_COLUMNS):
        return None
    if any(gate.get(key) != item.get(key) for key in ('set_number', 'position', 'measurement_id')):
        return None
    if not isinstance(run.get('run_id'), str) or not run['run_id'].strip():
        return None
    if not run.get('predicted_type') or not isinstance(run['predicted_type'], str):
        return None
    try:
        wear = Decimal(str(run['predicted_wear_um']))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return None
    if not wear.is_finite() or wear < 0:
        return None
    level = wear_level(wear)
    if level not in ('warning', 'danger') or level != run.get('wear_status'):
        return None
    # Use exact inference result and currently displayed image/sensor snapshot.
    title = alert_title(level, run['predicted_type'])
    return (
        gate['session_id'], gate['playback_generation'], gate['cycle_number'],
        gate['set_number'], gate['position'], gate['measurement_id'], run['run_id'],
        item['image_name'], item['sensor_name'], 'prediction', level,
        wear, wear, run['predicted_type'], WARNING_UM, DANGER_UM,
        f'{title} ({wear:.2f} μm)', now, now,
    )


def record_showing_alert(cursor, gate, item, run, now):
    """Idempotent insert; caller owns DB transaction and replay gate locks."""
    values = inference_alert_values(gate, item, run, now)
    if values is None:
        return False
    cursor.execute('''
        INSERT INTO monitoring_alert_events
            (session_id, playback_generation, cycle_number, set_number,
             position, measurement_id, inference_run_id, image_name, sensor_name,
             source, level, judged_wear_um, predicted_wear_um, original_type,
             warning_threshold_um, danger_threshold_um, message, created_at, recorded_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE id = monitoring_alert_events.id
    ''', values)
    return cursor.rowcount == 1
