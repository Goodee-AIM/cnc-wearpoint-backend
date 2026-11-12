"""현재 재생 세션의 알림 이력을 집계하고 발생 건별 확인을 기록합니다."""
import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Path, Query

from app.api.routers.monitoring import monitoring_cursor, read_clock, read_state


router = APIRouter(prefix="/api/monitoring/alerts", tags=["공통 알림 이력"])

# 기존 한국어 화면은 alerts의 naive 시각을 한국 시간으로 표시했습니다.
# 기존 DB에 UTC 시각이 저장되어 있다면 LEGACY_ALERTS_UTC_OFFSET_MINUTES=0을 사용합니다.
# UNION의 모든 문자열을 같은 charset/collation으로 명시합니다.
# 기존 테이블이나 연결 설정의 collation과 독립적으로 목록을 합칩니다.
FEED_SQL = """
    SELECT
        CONVERT(CONCAT('monitoring:', e.id) USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS id,
        COALESCE(e.prediction_id, available.id) AS prediction_id,
        CONVERT(e.level USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS level,
        CONVERT(e.message USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS message,
        e.created_at, e.detail_confirmed_at, e.set_number,
        CONVERT(e.image_name USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS image_name,
        CONVERT(e.sensor_name USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS sensor_name,
        COALESCE(e.predicted_wear_um, available.predicted_wear_um) AS predicted_wear_um,
        CONVERT(e.original_type USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS original_type,
        e.judged_wear_um,
        CONVERT(e.source USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS source,
        e.warning_threshold_um, e.danger_threshold_um,
        CONVERT(e.session_id USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS session_id,
        e.measurement_id, e.cycle_number
    FROM monitoring_alert_events AS e
    LEFT JOIN predictions AS available ON available.id = (
        SELECT latest.id FROM predictions AS latest
        WHERE e.prediction_id IS NULL AND latest.measurement_id = e.measurement_id
        ORDER BY latest.predicted_at DESC, latest.id DESC LIMIT 1
    )
    WHERE e.id <= %s AND e.session_id = %s
    UNION ALL
    SELECT
        CONVERT(CONCAT('legacy:', a.id) USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
        a.prediction_id,
        CONVERT(a.level USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
        CONVERT(a.message USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
        TIMESTAMPADD(MINUTE, %s, a.created_at),
        TIMESTAMPADD(MINUTE, %s, a.detail_confirmed_at),
        s.set_number,
        CONVERT(m.image_name USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
        CONVERT(m.sensor_name USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
        p.predicted_wear_um,
        CONVERT(l.original_type USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
        NULL,
        CONVERT('legacy' USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
        p.warning_threshold_um, p.danger_threshold_um,
        CONVERT(NULL USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
        m.id, NULL AS cycle_number
    FROM alerts AS a
    JOIN predictions AS p ON p.id = a.prediction_id
    JOIN measurements AS m ON m.id = p.measurement_id
    JOIN tool_sets AS s ON s.set_id = m.set_id
    LEFT JOIN wear_labels AS l ON l.measurement_id = m.id
    WHERE a.id <= %s
"""


def legacy_offset():
    try:
        offset = int(os.getenv("LEGACY_ALERTS_UTC_OFFSET_MINUTES", "540"))
        if not -840 <= offset <= 840:
            raise ValueError
        return offset
    except ValueError as error:
        raise HTTPException(503, "LEGACY_ALERTS_UTC_OFFSET_MINUTES 설정을 확인하세요.") from error


def utc_times(record):
    for field in ("created_at", "detail_confirmed_at"):
        value = record[field]
        if value is not None:
            if isinstance(value, str):
                value = datetime.fromisoformat(value)
            record[field] = value.replace(tzinfo=timezone.utc)
    return record


@router.get("")
def list_shared_alerts(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_max_id: int | None = Query(None, ge=0),
    legacy_max_id: int | None = Query(None, ge=0),
    session_id: str | None = Query(None),
):
    with monitoring_cursor() as cursor:
        # 상태 행을 읽는 동안 reset이 끼어들지 않게 하고, 모든 브라우저가 같은 세션을 집계합니다.
        current_session = read_state(cursor)["session_id"]
        if session_id is not None and session_id != current_session:
            raise HTTPException(409, "재생 세션이 초기화됐습니다. 첫 페이지부터 다시 조회하세요.")
        if event_max_id is None:
            cursor.execute("""
                SELECT COALESCE(MAX(id),0) AS event_max_id
                FROM monitoring_alert_events WHERE session_id = %s
            """, (current_session,))
            event_max_id = cursor.fetchone()["event_max_id"]
        # 기존 클라이언트의 페이지 인자는 유지하되, 세션 없는 legacy 이력은 현재 집계에서 제외합니다.
        legacy_max_id = 0
        parameters = (event_max_id, current_session, 0, 0, legacy_max_id)
        cursor.execute("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN detail_confirmed_at IS NULL THEN 1 ELSE 0 END),0) AS unread
            FROM monitoring_alert_events WHERE session_id = %s AND id <= %s
        """, (current_session, event_max_id))
        counts = {key: int(value) for key, value in cursor.fetchone().items()}
        cursor.execute(f"""
            SELECT * FROM ({FEED_SQL}) AS history
            ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s
        """, (*parameters, limit, offset))
        items = [utc_times(row) for row in cursor.fetchall()]
        for row in items:
            row["can_acknowledge"] = row["prediction_id"] is not None
        return {
            **counts, "event_max_id": event_max_id, "legacy_max_id": legacy_max_id,
            "session_id": current_session, "items": items,
        }


@router.patch("/{record_id}/acknowledge")
def acknowledge_shared_alert(record_id: str = Path()):
    match = re.fullmatch(r"(monitoring|legacy):([1-9][0-9]*)", record_id)
    if match is None:
        raise HTTPException(400, "올바르지 않은 알림 ID입니다.")
    kind, number = match.groups()
    # 테이블명은 위의 고정 허용 값으로만 선택합니다.
    table = "monitoring_alert_events" if kind == "monitoring" else "alerts"
    with monitoring_cursor() as cursor:
        fields = "id, prediction_id, measurement_id" if kind == "monitoring" else "id, prediction_id"
        cursor.execute(
            f"SELECT {fields} FROM {table} WHERE id = %s FOR UPDATE", (int(number),),
        )
        record = cursor.fetchone()
        if record is None:
            raise HTTPException(404, "알림이 없습니다.")
        if kind == "monitoring" and record["prediction_id"] is None:
            cursor.execute("""
                SELECT id, predicted_wear_um FROM predictions
                WHERE measurement_id = %s ORDER BY predicted_at DESC, id DESC LIMIT 1
            """, (record["measurement_id"],))
            prediction = cursor.fetchone()
            if prediction is not None:
                cursor.execute("""
                    UPDATE monitoring_alert_events SET prediction_id = %s, predicted_wear_um = %s
                    WHERE id = %s
                """, (prediction["id"], prediction["predicted_wear_um"], int(number)))
                record["prediction_id"] = prediction["id"]
        if record["prediction_id"] is None:
            raise HTTPException(422, "예측 결과가 있는 알림만 확인 시각을 저장할 수 있습니다.")
        now = read_clock(cursor)
        # 원래 alerts는 기존 API와 같은 DB 현지 시각으로 확인 시각을 기록합니다.
        if kind == "legacy":
            now += timedelta(minutes=legacy_offset())
        cursor.execute(f"""
            UPDATE {table} SET detail_confirmed_at = COALESCE(detail_confirmed_at, %s)
            WHERE id = %s
        """, (now, int(number)))
        cursor.execute(f"SELECT created_at, detail_confirmed_at FROM {table} WHERE id = %s", (int(number),))
        times = cursor.fetchone()
        if kind == "legacy":
            shift = timedelta(minutes=legacy_offset())
            for field, value in times.items():
                if value is not None:
                    if isinstance(value, str):
                        value = datetime.fromisoformat(value)
                    times[field] = value - shift
        return {"id": record_id, **utc_times(times)}
