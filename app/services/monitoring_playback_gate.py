"""Server-authoritative, opt-in independent replay clock for each Set.

A Set's sensor/image playback never waits for the inference queue. At the end
of playback it waits for the exact inference result, shows it for 3 seconds,
then advances to the next measurement. This feature is OFF by default.
"""
import os
from datetime import timedelta
from app.services.monitoring_inference_alerts import record_showing_alert
from app.services.playback_speed import PLAYBACK_RATE, scaled_elapsed_ms

RESULT_HOLD_MS = 3000


def gate_enabled():
    return os.getenv('MONITORING_INFERENCE_ENABLED', '0') == '1'


def elapsed_ms(gate, now, is_running=True):
    # Sensor progress is in source milliseconds; result hold uses real time.
    rate = PLAYBACK_RATE if gate['phase'] == 'playing' else 1
    return scaled_elapsed_ms(
        gate['phase_elapsed_ms'],
        gate.get('phase_started_at') if is_running else None,
        now, rate=rate,
    )


def initialize_gates(cursor, state, items, now):
    """Reset only the new gate table under monitoring_state FOR UPDATE."""
    cursor.execute('DELETE FROM monitoring_playback_gates')
    first = {}
    for item in items:
        first.setdefault(int(item['set_number']), item)
    for set_number, item in sorted(first.items()):
        cursor.execute('''
          INSERT INTO monitoring_playback_gates
            (set_number, session_id, playback_generation, cycle_number,
             position, measurement_id, phase, phase_elapsed_ms, phase_started_at)
          VALUES (%s,%s,%s,1,%s,%s,'playing',0,%s)
        ''', (set_number, state['session_id'], state.get('playback_generation', 0),
              item['position'], item['measurement_id'], now))


def pause_gates(cursor, now):
    cursor.execute('SELECT * FROM monitoring_playback_gates FOR UPDATE')
    for row in cursor.fetchall():
        cursor.execute('''
          UPDATE monitoring_playback_gates
          SET phase_elapsed_ms = %s, phase_started_at = NULL
          WHERE set_number = %s
        ''', (elapsed_ms(row, now), row['set_number']))


def resume_gates(cursor, now):
    cursor.execute('''
      UPDATE monitoring_playback_gates SET phase_started_at = %s
      WHERE phase_started_at IS NULL AND phase IN ('playing','showing')
    ''', (now,))


def read_gates(cursor):
    cursor.execute('SELECT * FROM monitoring_playback_gates')
    return {int(g['set_number']): g for g in cursor.fetchall()}


def project_gated_state(base, items, gates, now):
    """Override only Set cursors; preserve existing response envelope and alerts API."""
    by_key = {(int(i['set_number']), int(i['position'])): i for i in items}
    mapped = []
    for item in base['sets']:
        gate = gates.get(int(item['set_number']))
        scheduled = by_key.get((int(item['set_number']), int(gate['position']))) if gate else None
        if (not scheduled or not base['session_id'] or
            gate['session_id'] != base['session_id'] or
            int(gate['playback_generation']) != int(base.get('playback_generation', 0)) or
            int(scheduled['measurement_id']) != int(gate['measurement_id'])):
            # Fail closed. Never return a stale image with a fresh prediction.
            mapped.append({**item, 'status': 'empty', 'playback_phase': 'unavailable',
                           'image_url': None, 'sensor_url': None})
            continue
        phase = gate['phase']
        duration = int(scheduled['duration_ms'])
        elapsed = elapsed_ms(gate, now, base['status'] == 'running') if phase != 'waiting' else duration
        elapsed = min(duration, elapsed) if phase == 'playing' else duration
        from urllib.parse import quote
        sensor_url = (f"/api/sensors/set{scheduled['set_number']}/"
                      f"{quote(scheduled['sensor_name'], safe='')}") if scheduled['playback_mode'] == 'sensor' else None
        status = 'paused' if base['status'] == 'paused' else 'running'
        mapped.append({**scheduled,
                       'total': item.get('total', 0), 'elapsed_ms': elapsed,
                       'status': status,
                       'image_url': f"/api/images/set{scheduled['set_number']}/{quote(scheduled['image_name'], safe='')}",
                       'sensor_url': sensor_url,
                       'playback_phase': phase,
                       'playback_rate': PLAYBACK_RATE,
                       'result_visible': phase == 'showing',
                       'cycle_number': int(gate['cycle_number']),
                       'playback_generation': int(gate['playback_generation']),
                       'phase_elapsed_ms': min(RESULT_HOLD_MS, elapsed_ms(gate, now, base['status'] == 'running')) if phase == 'showing' else 0})
    return {**base, 'sets': mapped, 'gated_playback': True, 'playback_rate': PLAYBACK_RATE}


def _transition(cursor, gate, phase, now, elapsed=0, *, position=None,
                measurement_id=None, cycle_number=None):
    cursor.execute('''
      UPDATE monitoring_playback_gates SET phase=%s, phase_elapsed_ms=%s,
      phase_started_at=%s, position=%s, measurement_id=%s, cycle_number=%s
      WHERE set_number=%s AND session_id=%s AND playback_generation=%s
    ''', (phase, elapsed, now if phase in ('playing','showing') else None,
          gate['position'] if position is None else position,
          gate['measurement_id'] if measurement_id is None else measurement_id,
          gate['cycle_number'] if cycle_number is None else cycle_number,
          gate['set_number'], gate['session_id'], gate['playback_generation']))
    if cursor.rowcount != 1:
        raise RuntimeError('Set playback gate changed during transition')


def advance_gates(cursor):
    """One transaction, state row locked: never advance before 3s result hold.

    Completion is checked using the full occurrence tuple. A failed inference
    shows an unavailable result for 3s rather than blocking the whole Set.
    """
    cursor.execute('SELECT * FROM monitoring_state WHERE id=1 FOR UPDATE')
    state = cursor.fetchone()
    if not state or state['status'] != 'running' or not state['session_id']:
        return 0
    cursor.execute('SELECT UTC_TIMESTAMP(6) AS now')
    now = cursor.fetchone()['now']
    cursor.execute('SELECT * FROM monitoring_items ORDER BY set_number, position')
    schedule = cursor.fetchall()
    by_set = {}
    for item in schedule:
        by_set.setdefault(int(item['set_number']), []).append(item)
    cursor.execute('SELECT * FROM monitoring_playback_gates FOR UPDATE')
    gates = cursor.fetchall()
    changed = 0
    for gate in gates:
        set_number = int(gate['set_number'])
        if (gate['session_id'] != state['session_id'] or
            int(gate['playback_generation']) != int(state.get('playback_generation', 0))):
            continue
        queue = by_set.get(set_number, [])
        item = next((i for i in queue if int(i['position']) == int(gate['position'])
                     and int(i['measurement_id']) == int(gate['measurement_id'])), None)
        if not item:
            continue
        phase = gate['phase']
        run = None
        if item['playback_mode'] == 'sensor' and item['sensor_name']:
            cursor.execute('''
              SELECT run_id, session_id, playback_generation, cycle_number,
                     set_number, position, measurement_id, status,
                     predicted_wear_um, predicted_type, wear_status
              FROM monitoring_inference_runs
              WHERE session_id=%s AND playback_generation=%s AND cycle_number=%s
                AND set_number=%s AND position=%s AND measurement_id=%s
            ''', (gate['session_id'], gate['playback_generation'], gate['cycle_number'],
                  set_number, gate['position'], gate['measurement_id']))
            run = cursor.fetchone()
        ready = (run is not None and run['status'] in ('completed','failed','cancelled'))
        # An image-only item cannot be inferred with the required image+sensor pair.
        ready = ready or item['playback_mode'] != 'sensor' or not item['sensor_name']
        if phase == 'playing' and elapsed_ms(gate, now) >= item['duration_ms']:
            if ready and run is not None:
                record_showing_alert(cursor, gate, item, run, now)
            _transition(cursor, gate, 'showing' if ready else 'waiting', now)
            changed += 1
        elif phase == 'waiting' and ready:
            if run is not None:
                record_showing_alert(cursor, gate, item, run, now)
            _transition(cursor, gate, 'showing', now)
            changed += 1
        elif phase == 'showing' and elapsed_ms(gate, now) >= RESULT_HOLD_MS:
            next_index = next((idx for idx, row in enumerate(queue)
                               if int(row['position']) == int(gate['position'])), -1) + 1
            if next_index >= len(queue):
                next_index = 0
                next_cycle = int(gate['cycle_number']) + 1
            else:
                next_cycle = int(gate['cycle_number'])
            next_item = queue[next_index]
            _transition(cursor, gate, 'playing', now,
                        position=next_item['position'], measurement_id=next_item['measurement_id'],
                        cycle_number=next_cycle)
            changed += 1
    return changed
