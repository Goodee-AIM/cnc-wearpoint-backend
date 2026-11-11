"""DB에 저장된 공통 재생 상태를 조회하고 운영자가 제어합니다."""
import logging
import os
import secrets
from contextlib import contextmanager
from uuid import uuid4

import mysql.connector
from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.routers.images import list_images
from app.core.database import get_connection
from app.services.monitoring import build_schedule, elapsed_ms, state_response
from app.services.monitoring_alerts import emit_due_alerts


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["공통 모니터링"])
EMPTY_STATE = {
    "session_id": None, "status": "idle", "elapsed_ms": 0,
    "resumed_at": None, "revision": 0,
}


def require_control_token(x_monitoring_control_token: str = Header(default="")):
    expected = os.getenv("MONITORING_CONTROL_TOKEN", "")
    if not expected:
        raise HTTPException(503, "MONITORING_CONTROL_TOKEN을 먼저 설정하세요.")
    if not secrets.compare_digest(x_monitoring_control_token.encode(), expected.encode()):
        raise HTTPException(403, "공통 재생 제어 권한이 없습니다.")


@contextmanager
def monitoring_cursor():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        yield cursor
        connection.commit()
    except mysql.connector.Error as error:
        logger.exception("공통 모니터링 DB 요청 실패")
        if connection is not None:
            connection.rollback()
        detail = "공통 재생 DB 요청에 실패했습니다. 서버 로그를 확인하세요."
        if error.errno == 1146:
            migration = "20261111_monitoring.sql"
            if "monitoring_alert_events" in str(error):
                migration = "20261111_monitoring_alerts.sql"
            detail = f"sql/cnc/migrations/{migration}을 먼저 적용하세요."
        if error.errno == 1054 and "cycle_number" in str(error):
            detail = "sql/cnc/migrations/20261111_monitoring_alert_cycles.sql을 먼저 적용하세요."
        raise HTTPException(503, detail) from error
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def read_state(cursor, *, exclusive=False):
    if exclusive:
        # 중복 행에서도 배타 잠금을 먼저 얻어 제어 요청끼리의 잠금 승격을 피합니다.
        cursor.execute("""
            INSERT INTO monitoring_state (id) VALUES (1)
            ON DUPLICATE KEY UPDATE id = 1
        """)
    lock = "FOR UPDATE" if exclusive else "FOR SHARE"
    cursor.execute(f"SELECT * FROM monitoring_state WHERE id = 1 {lock}")
    return cursor.fetchone() or dict(EMPTY_STATE)


def read_clock(cursor):
    # 같은 DB를 사용하는 모든 worker가 동일한 UTC 시계로 계산합니다.
    cursor.execute("SELECT UTC_TIMESTAMP(6) AS now")
    return cursor.fetchone()["now"]


def read_items(cursor):
    cursor.execute("SELECT * FROM monitoring_items ORDER BY set_number, position")
    return cursor.fetchall()


@router.get("/state")
def get_state():
    with monitoring_cursor() as cursor:
        state = read_state(cursor)
        items = read_items(cursor) if state["session_id"] else []
        return state_response(state, items, read_clock(cursor))


@router.post("/start", dependencies=[Depends(require_control_token)])
def start():
    # CSV 준비 중에는 공통 상태 잠금을 유지하지 않습니다.
    with monitoring_cursor() as cursor:
        previous = read_state(cursor)
        if previous["status"] == "running":
            return state_response(previous, read_items(cursor), read_clock(cursor))
        measurements = []
        if previous["status"] == "idle":
            cursor.execute("""
                SELECT s.set_number, m.id AS measurement_id, m.image_name, m.sensor_name
                FROM measurements AS m
                JOIN tool_sets AS s ON s.set_id = m.set_id
                WHERE s.set_number BETWEEN 4 AND 11 AND m.image_name IS NOT NULL
                ORDER BY m.id
            """)
            measurements = cursor.fetchall()

    schedule = []
    if previous["status"] == "idle":
        images = {number: list_images(f"set{number}")["items"] for number in range(4, 12)}
        schedule = build_schedule(measurements, images)
        if not schedule:
            raise HTTPException(409, "DB 측정과 연결된 서버 이미지가 없습니다.")

    with monitoring_cursor() as cursor:
        state = read_state(cursor, exclusive=True)
        if state["status"] == "running":
            return state_response(state, read_items(cursor), read_clock(cursor))
        if state["revision"] != previous["revision"]:
            raise HTTPException(409, "준비 중 공통 재생 상태가 변경됐습니다. 다시 조회하세요.")
        if state["status"] == "idle":
            cursor.execute("DELETE FROM monitoring_items")
            cursor.executemany("""
                INSERT INTO monitoring_items
                    (set_number, position, measurement_id, image_name, sensor_name,
                     start_ms, duration_ms, playback_mode, message)
                VALUES (%(set_number)s, %(position)s, %(measurement_id)s,
                        %(image_name)s, %(sensor_name)s, %(start_ms)s,
                        %(duration_ms)s, %(playback_mode)s, %(message)s)
            """, schedule)
            state["session_id"] = str(uuid4())
        now = read_clock(cursor)
        cursor.execute("""
            UPDATE monitoring_state SET session_id = %s, status = 'running',
                resumed_at = %s, revision = revision + 1 WHERE id = 1
        """, (state["session_id"], now))
        state.update(status="running", resumed_at=now, revision=state["revision"] + 1)
        emit_due_alerts(cursor, state, now)
        return state_response(state, read_items(cursor), now)


@router.post("/pause", dependencies=[Depends(require_control_token)])
def pause():
    with monitoring_cursor() as cursor:
        state = read_state(cursor, exclusive=True)
        now = read_clock(cursor)
        items = read_items(cursor)
        if state["status"] == "running":
            emit_due_alerts(cursor, state, now)
            elapsed = elapsed_ms(state, now)
            cursor.execute("""
                UPDATE monitoring_state SET status = 'paused', elapsed_ms = %s,
                    resumed_at = NULL, revision = revision + 1 WHERE id = 1
            """, (elapsed,))
            state.update(status="paused", elapsed_ms=elapsed, resumed_at=None,
                         revision=state["revision"] + 1)
        return state_response(state, items, now)


@router.post("/reset", dependencies=[Depends(require_control_token)])
def reset():
    with monitoring_cursor() as cursor:
        state = read_state(cursor, exclusive=True)
        emit_due_alerts(cursor, state, read_clock(cursor))
        cursor.execute("DELETE FROM monitoring_items")
        cursor.execute("""
            UPDATE monitoring_state SET session_id = NULL, status = 'idle',
                elapsed_ms = 0, resumed_at = NULL, revision = revision + 1 WHERE id = 1
        """)
        state = {**EMPTY_STATE, "revision": state["revision"] + 1}
        return state_response(state, [], read_clock(cursor))
