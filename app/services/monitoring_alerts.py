"""브라우저 접속과 독립적으로 공통 재생의 경고·위험을 기록합니다."""
import asyncio
import logging
from datetime import timedelta
from decimal import Decimal

from app.core.database import get_connection
from app.services.monitoring import elapsed_ms


logger = logging.getLogger(__name__)


def emit_due_alerts(cursor, state, now):
    """호출자는 공통 상태 행의 배타 잠금을 보유한 트랜잭션 안에서 실행합니다."""
    if state["status"] != "running" or not state["session_id"]:
        return
    elapsed = elapsed_ms(state, now)
    cursor.execute("SELECT MAX(start_ms + duration_ms) AS total_ms FROM monitoring_items")
    total_ms = cursor.fetchone()["total_ms"] or 0
    if not total_ms:
        return
    # 현재 세션의 기록만 조회해 누락 회차를 복구합니다. 확인 상태는 덮어쓰지 않습니다.
    cursor.execute("""
        SELECT cycle_number, set_number, position FROM monitoring_alert_events
        WHERE session_id = %s
    """, (state["session_id"],))
    recorded = {(row["cycle_number"], row["set_number"], row["position"])
                for row in cursor.fetchall()}
    cursor.execute("""
        SELECT i.*, l.original_wear_um, l.original_type,
               p.id AS prediction_id, p.predicted_wear_um,
               p.warning_threshold_um, p.danger_threshold_um
        FROM monitoring_items AS i
        LEFT JOIN wear_labels AS l ON l.measurement_id = i.measurement_id
        LEFT JOIN predictions AS p ON p.id = (
            SELECT latest.id FROM predictions AS latest
            WHERE latest.measurement_id = i.measurement_id
            ORDER BY latest.predicted_at DESC, latest.id DESC LIMIT 1
        )
        WHERE (
              (i.set_number BETWEEN 4 AND 9 AND l.original_wear_um >= 50)
              OR (i.set_number IN (10,11) AND p.predicted_wear_um >= p.warning_threshold_um)
          )
        ORDER BY i.start_ms, i.set_number, i.position
    """)
    candidates = cursor.fetchall()
    for cycle_index in range(elapsed // total_ms + 1):
        for row in candidates:
            occurrence_ms = cycle_index * total_ms + row["start_ms"]
            cycle_number = cycle_index + 1
            if occurrence_ms > elapsed or (cycle_number, row["set_number"], row["position"]) in recorded:
                continue
            source = "label" if row["set_number"] < 10 else "prediction"
            wear = row["original_wear_um"] if source == "label" else row["predicted_wear_um"]
            warning = Decimal(50) if source == "label" else row["warning_threshold_um"]
            danger = Decimal(90) if source == "label" else row["danger_threshold_um"]
            level = "danger" if wear >= danger else "warning"
            title = "위험 · 공구 교체 필요" if level == "danger" else "경고 · 마모 상태 확인"
            # 재개 이전에 새로 추가된 결과는 현재 감지 시각으로 기록합니다.
            occurred_at = now
            if occurrence_ms >= state["elapsed_ms"]:
                occurred_at -= timedelta(milliseconds=elapsed - occurrence_ms)
            cursor.execute("""
                INSERT INTO monitoring_alert_events
                    (session_id, cycle_number, set_number, position, measurement_id, prediction_id,
                     image_name, sensor_name, source, level, judged_wear_um,
                     predicted_wear_um, original_type, warning_threshold_um,
                     danger_threshold_um, message, created_at, recorded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE id = monitoring_alert_events.id
            """, (
                state["session_id"], cycle_number, row["set_number"], row["position"], row["measurement_id"],
                row["prediction_id"], row["image_name"], row["sensor_name"], source, level,
                wear, row["predicted_wear_um"], row["original_type"], warning, danger,
                f"{title} ({wear:.2f} μm)", occurred_at, now,
            ))


def process_due_alerts():
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM monitoring_state WHERE id = 1 FOR UPDATE")
        state = cursor.fetchone()
        if state and state["status"] == "running":
            cursor.execute("SELECT UTC_TIMESTAMP(6) AS now")
            emit_due_alerts(cursor, state, cursor.fetchone()["now"])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


async def run_alert_worker(stop):
    failed = False
    while not stop.is_set():
        try:
            await asyncio.to_thread(process_due_alerts)
        except Exception:
            if not failed:
                logger.exception("공통 알림 기록 실패. DB 연결과 monitoring_alerts migration을 확인하세요.")
            failed = True
        else:
            failed = False
        try:
            await asyncio.wait_for(stop.wait(), timeout=5 if failed else 1)
        except TimeoutError:
            pass
