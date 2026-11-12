from fastapi import APIRouter, HTTPException, Path, Query

from app.core.database import get_connection


router = APIRouter(prefix="/api/sets", tags=["Set 조회"])

#Set4~11 목록 조회
@router.get("")
def get_sets():
    """사용 대상인 Set4~11과 Set별 측정 수를 조회합니다."""
    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                """
                SELECT
                    s.set_id,
                    s.set_number,
                    s.set_name,
                    s.material,
                    COUNT(m.id) AS measurement_count
                FROM tool_sets AS s
                LEFT JOIN measurements AS m ON m.set_id = s.set_id
                WHERE s.set_number BETWEEN 4 AND 11
                GROUP BY
                    s.set_id, s.set_number, s.set_name, s.material
                ORDER BY s.set_number
                """
            )

            return {"items": cursor.fetchall()}
        finally:
            cursor.close()
    finally:
        connection.close()


#Set의 측정 정보·정답 라벨·최신 예측 조회
@router.get("/{set_number}/measurements")
def get_measurements(
    set_number: int = Path(..., ge=4, le=11),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """선택한 Set의 측정과 정답·최신 예측 결과를 조회합니다."""
    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                """
                SELECT set_id, set_number, set_name
                FROM tool_sets
                WHERE set_number = %s
                """,
                (set_number,),
            )
            selected_set = cursor.fetchone()

            if selected_set is None:
                raise HTTPException(
                    status_code=404,
                    detail="등록되지 않은 Set입니다.",
                )

            set_id = selected_set["set_id"]

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM measurements
                WHERE set_id = %s
                """,
                (set_id,),
            )
            total = cursor.fetchone()["total"]

            cursor.execute(
                """
                SELECT
                    m.id AS measurement_id,
                    m.measurement_key,
                    m.image_name,
                    m.image_path,
                    m.sensor_name,
                    m.sensor_path,
                    m.image_id,
                    m.sensor_id,
                    m.image_captured_at,
                    m.sensor_started_at,
                    m.sensor_ended_at,
                    m.status AS measurement_status,

                    l.original_wear_um,
                    l.original_type,

                    p.id AS prediction_id,
                    p.predicted_wear_um,
                    p.predicted_type,
                    p.model_version,
                    p.status AS prediction_status,
                    p.predicted_at

                FROM measurements AS m

                LEFT JOIN wear_labels AS l
                    ON l.measurement_id = m.id

                LEFT JOIN predictions AS p
                    ON p.id = (
                        SELECT latest.id
                        FROM predictions AS latest
                        WHERE latest.measurement_id = m.id
                        ORDER BY latest.predicted_at DESC, latest.id DESC
                        LIMIT 1
                    )

                WHERE m.set_id = %s

                ORDER BY
                    COALESCE(m.image_id, m.sensor_id),
                    m.id

                LIMIT %s OFFSET %s
                """,
                (set_id, limit, offset),
            )

            items = cursor.fetchall()

            # 예측 마모량과 정답 마모량을 서로 구분하여 반환합니다.
            for item in items:
                for field in ("original_wear_um", "predicted_wear_um"):
                    if item[field] is not None:
                        item[field] = float(item[field])

            return {
                "set_number": selected_set["set_number"],
                "set_name": selected_set["set_name"],
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": items,
            }
        finally:
            cursor.close()
    finally:
        connection.close()
