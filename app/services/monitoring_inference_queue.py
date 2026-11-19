"""Replay-scoped, opt-in inference queue for Set4..Set11.

Queueing/Serving is disabled unless MONITORING_INFERENCE_ENABLED=1.  A separate
per-Set playback gate is required before the new results can be displayed.
"""
import asyncio
import logging
import re
import uuid
from contextlib import contextmanager

from app.core.database import get_connection
from app.services.monitoring import state_response
from app.services.prediction_execution import request_serving_prediction, validate_model_result
from app.services.inference_capacity import inference_slots
from app.services.monitoring_playback_gate import (
    gate_enabled, read_gates, project_gated_state, advance_gates,
)

logger = logging.getLogger(__name__)


def occurrence_identity(state, item):
    """Immutable identity of an exact image/sensor visit within a replay."""
    # Paused items are still the same occurrence; don't discard a result
    # merely because the operator paused playback during inference.
    if not state or state.get('status') not in ('running', 'paused'):
        return None
    if item.get('status') not in ('running', 'paused'):
        return None
    if item.get('playback_mode') != 'sensor' or not item.get('sensor_name'):
        return None
    return (state['session_id'], state.get('playback_generation', 0),
            item.get('cycle_number', state['cycle_number']), item['set_number'], item['position'],
            item['measurement_id'])


def matching_run(identity, run):
    """Reject stale completions from other measurements, cycles or restarts."""
    if identity is None or not run:
        return False
    return identity == (run['session_id'], run['playback_generation'],
                        run['cycle_number'], run['set_number'], run['position'],
                        run['measurement_id'])


def _transaction(fn):
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            result = fn(cursor)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def _snapshot(cursor):
    cursor.execute('SELECT * FROM monitoring_state WHERE id = 1 FOR SHARE')
    state = cursor.fetchone()
    if not state or not state.get('session_id'):
        return None, {}
    cursor.execute('SELECT * FROM monitoring_items ORDER BY set_number, position')
    items = cursor.fetchall()
    cursor.execute('SELECT UTC_TIMESTAMP(6) AS now')
    now = cursor.fetchone()['now']
    result = state_response(state, items, now)
    if gate_enabled():
        result = project_gated_state(result, items, read_gates(cursor), now)
    return result, {i['set_number']: i for i in result['sets']}


def enqueue_current():
    """Enqueue current measurement for every Set, without duplicating an occurrence."""
    def operation(cursor):
        state, selected = _snapshot(cursor)
        if not state or state['status'] != 'running':
            return 0
        count = 0
        for item in selected.values():
            identity = occurrence_identity(state, item)
            if identity is None:
                continue
            cursor.execute('''
                INSERT INTO monitoring_inference_runs
                  (run_id, session_id, playback_generation, cycle_number,
                   set_number, position, measurement_id, image_name, sensor_name)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE id = id
            ''', (str(uuid.uuid4()), *identity, item['image_name'], item['sensor_name']))
            count += int(cursor.rowcount == 1)
        return count
    return _transaction(operation)


def _recover_interrupted_runs():
    """Fail closed on unknown-outcome Serving calls left `running` by a dead worker.

    Call ONLY while this worker holds `cnc_wp_monitoring_queue`'s MySQL advisory
    lock. When it is available, no *other healthy queue worker* should be
    executing that run. A dropped DB connection can still leave an orphaned
    Serving request in flight; do not automatically resend unknown outcomes.

    The transaction commits before the next queued run is claimed. Existing
    completed/failed/cancelled rows and pending queue items are untouched.
    """
    def operation(cursor):
        cursor.execute("""
            UPDATE monitoring_inference_runs
            SET status = 'failed', error_code = 'WORKER_INTERRUPTED',
                error_message = '추론 작업이 중단되어 결과를 확인할 수 없습니다.',
                finished_at = UTC_TIMESTAMP(6)
            WHERE status = 'running'
        """)
        return cursor.rowcount
    return _transaction(operation)


def _claim_next():
    def operation(cursor):
        # SKIP LOCKED fences parallel claimers on multi-worker deployments.
        cursor.execute('''
            SELECT * FROM monitoring_inference_runs
            WHERE status = 'queued'
            ORDER BY queued_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
        ''')
        row = cursor.fetchone()
        if row is None:
            return None
        cursor.execute('''
            UPDATE monitoring_inference_runs
            SET status = 'running', attempt_count = attempt_count + 1,
                started_at = NOW(6)
            WHERE id = %s AND status = 'queued'
        ''', (row['id'],))
        if cursor.rowcount != 1:
            raise RuntimeError('Queue claim was lost')
        return row
    return _transaction(operation)


def _is_current(row):
    def operation(cursor):
        state, selected = _snapshot(cursor)
        if not state:
            return False
        return matching_run(occurrence_identity(state, selected.get(row['set_number'], {})), row)
    return _transaction(operation)


def _finish(row, status, result=None, error_code=None):
    def operation(cursor):
        # Fence result persistence behind the monitoring_state shared lock.
        # Restart/reset takes an exclusive lock on the same row.
        state, selected = _snapshot(cursor)
        same_occurrence = (state is not None and matching_run(
            occurrence_identity(state, selected.get(row['set_number'], {})), row))
        final_status = status if same_occurrence else 'cancelled'
        if final_status == 'completed':
            wear, wear_type, model, version, level = validate_model_result(result)
            cursor.execute('''
                UPDATE monitoring_inference_runs SET status = 'completed',
                    predicted_wear_um = %s, predicted_type = %s,
                    model_name = %s, model_version = %s, wear_status = %s,
                    finished_at = NOW(6) WHERE run_id = %s AND status = 'running'
            ''', (wear, wear_type, model, version, level, row['run_id']))
        else:
            cursor.execute('''
                UPDATE monitoring_inference_runs SET status = %s,
                    error_code = %s, finished_at = NOW(6)
                WHERE run_id = %s AND status = 'running'
            ''', (final_status, (error_code if same_occurrence else 'STALE_OCCURRENCE'), row['run_id']))
        if cursor.rowcount != 1:
            raise RuntimeError('Running inference row changed before completion')
    _transaction(operation)



def _keys(row):
    """
    measurements 테이블에 저장된 실제 파일 경로를 사용한다.

    image_name은 원본 파일명으로 보존하고,
    image_path / sensor_path를 Object Storage Key로 사용한다.
    """

    set_number = int(row["set_number"])
    measurement_id = int(row["measurement_id"])

    if not 4 <= set_number <= 11:
        raise ValueError("Invalid Set number")

    def read_paths(cursor):
        cursor.execute(
            """
            SELECT
                m.image_path,
                m.sensor_path,
                t.set_number
            FROM measurements AS m
            LEFT JOIN tool_sets AS t
                ON m.set_id = t.set_id
            WHERE m.id = %s
            """,
            (measurement_id,),
        )
        return cursor.fetchone()

    # 조회만 수행. 기존 _transaction을 재사용한다.
    measurement = _transaction(read_paths)

    if measurement is None:
        raise ValueError("Measurement not found")

    if measurement["set_number"] != set_number:
        raise ValueError("Measurement Set mismatch")

    image_key = measurement["image_path"]
    sensor_key = measurement["sensor_path"]

    if not isinstance(image_key, str) or not image_key:
        raise ValueError("Missing image path")

    if not isinstance(sensor_key, str) or not sensor_key:
        raise ValueError("Missing sensor path")

    # 다른 Set 또는 예상치 못한 경로 접근 차단
    image_pattern = (
        rf"images/set{set_number}/original/"
        rf"[A-Za-z0-9_.-]+\.(?:png|jpe?g)"
    )

    sensor_pattern = (
        rf"sensors/set{set_number}/"
        rf"[A-Za-z0-9_.-]+\.csv"
    )

    if not re.fullmatch(image_pattern, image_key, re.I):
        raise ValueError(
            "Invalid or legacy image path"
        )

    if not re.fullmatch(sensor_pattern, sensor_key, re.I):
        raise ValueError(
            "Invalid or legacy sensor path"
        )

    return image_key, sensor_key



@contextmanager
def _serving_gate():
    """Cross-process, MySQL-backed queue slot; no DB row lock during Serving I/O."""
    connection = get_connection()
    acquired = False
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT GET_LOCK(%s, 0) AS acquired", ("cnc_wp_monitoring_queue",))
            acquired = cursor.fetchone()["acquired"] == 1
        finally:
            cursor.close()
        yield acquired
    finally:
        if acquired:
            try:
                cursor = connection.cursor(dictionary=True)
                try:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", ("cnc_wp_monitoring_queue",))
                finally:
                    cursor.close()
            except Exception:
                logger.exception("Unable to release replay inference lock")
        connection.close()


def process_one():
    """Claim one queued run; keep DB transactions short across Serving I/O."""
    if not inference_slots.acquire(blocking=False):
        return False
    try:
        with _serving_gate() as allowed:
            if not allowed:
                return False
            # Recover under the same cross-process Serving gate. A previous
            # worker might have died after claiming a row, leaving it running
            # forever. Unknown outcomes become terminal failures; the Set gate
            # can then proceed without displaying an unverified prediction.
            _recover_interrupted_runs()
            row = _claim_next()
            if row is None:
                return False
            if not _is_current(row):
                _finish(row, 'cancelled', error_code='STALE_OCCURRENCE')
                return True
            try:
                image_key, sensor_key = _keys(row)
                prediction = request_serving_prediction(image_key, sensor_key)
                # _finish rechecks identity under the monitoring state lock.
                _finish(row, 'completed', result=prediction)
            except Exception:
                logger.exception('Replay inference failed (run_id=%s)', row['run_id'])
                _finish(row, 'failed', error_code='INFERENCE_FAILED')
            return True
    finally:
        inference_slots.release()


def current_runs():
    """Show only a run for the current session/generation/cycle/measurement."""
    def operation(cursor):
        state, items = _snapshot(cursor)
        if state is None:
            return {'enabled': True, 'runs': []}
        active = {set_number: occurrence_identity(state, item)
                  for set_number, item in items.items()}
        active_cycles = sorted({identity[2] for identity in active.values() if identity})
        if not active_cycles:
            return {'enabled': True, 'runs': []}
        placeholders = ','.join(['%s'] * len(active_cycles))
        cursor.execute(f'''
            SELECT run_id, session_id, playback_generation, cycle_number,
                   set_number, position, measurement_id, status,
                   predicted_wear_um, predicted_type, wear_status,
                   model_name, model_version
            FROM monitoring_inference_runs WHERE session_id = %s
              AND playback_generation = %s AND cycle_number IN ({placeholders})
        ''', (state['session_id'], state['playback_generation'], *active_cycles))
        runs = []
        for row in cursor.fetchall():
            if not matching_run(active.get(row['set_number']), row):
                continue
            runs.append({
                'run_id': row['run_id'], 'session_id': row['session_id'],
                'playback_generation': row['playback_generation'],
                'cycle_number': row['cycle_number'], 'set_number': row['set_number'],
                'position': row['position'], 'measurement_id': row['measurement_id'],
                'status': row['status'],
                'predicted_wear_um': float(row['predicted_wear_um']) if row['status'] == 'completed' else None,
                'predicted_type': row['predicted_type'] if row['status'] == 'completed' else None,
                'wear_status': row['wear_status'] if row['status'] == 'completed' else None,
                'model_name': row['model_name'] if row['status'] == 'completed' else None,
                'model_version': row['model_version'] if row['status'] == 'completed' else None,
            })
        return {'enabled': True, 'runs': runs}
    return _transaction(operation)


async def run_inference_worker(stop):
    """One opt-in worker per application process; no implicit DB or Serving writes."""
    while not stop.is_set():
        try:
            await asyncio.to_thread(_transaction, advance_gates)
            await asyncio.to_thread(enqueue_current)
            await asyncio.to_thread(process_one)
        except Exception:
            logger.exception('Replay inference worker failure')
        try:
            await asyncio.wait_for(stop.wait(), timeout=1)
        except TimeoutError:
            pass
