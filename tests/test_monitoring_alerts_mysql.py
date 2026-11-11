"""실제 MySQL에서만 검증할 수 있는 collation 회귀 테스트.

CNC_TEST_MYSQL_COLLATIONS=1일 때 실행합니다. 설정된 DB에서 SELECT CTE만 실행하며
테이블 생성·변경이나 데이터 삽입은 수행하지 않습니다.
"""
import os

import mysql.connector
import pytest

from app.api.routers.monitoring_alerts import FEED_SQL
from app.core.database import get_connection


pytestmark = pytest.mark.skipif(
    os.getenv("CNC_TEST_MYSQL_COLLATIONS") != "1",
    reason="실제 MySQL 연결이 필요한 opt-in 테스트",
)

# CTE가 같은 이름의 실제 테이블을 가립니다. 문자셋이 섞인 가상 행만 조회합니다.
FIXTURE_SQL = """
WITH monitoring_alert_events AS (
    SELECT 1 AS id, NULL AS prediction_id,
           _utf8mb4'warning' COLLATE utf8mb4_0900_ai_ci AS level,
           _utf8mb4'신규 알림' COLLATE utf8mb4_0900_ai_ci AS message,
           CAST('2026-11-11 01:00:00' AS DATETIME) AS created_at,
           CAST(NULL AS DATETIME) AS detail_confirmed_at, 4 AS set_number,
           _utf8mb4'공구.png' COLLATE utf8mb4_0900_ai_ci AS image_name,
           CAST(NULL AS CHAR CHARACTER SET utf8mb4) AS sensor_name,
           NULL AS predicted_wear_um,
           _utf8mb4'flank_wear' COLLATE utf8mb4_0900_ai_ci AS original_type,
           60 AS judged_wear_um,
           _utf8mb4'label' COLLATE utf8mb4_0900_ai_ci AS source,
           50 AS warning_threshold_um, 90 AS danger_threshold_um,
           _utf8mb4'session' COLLATE utf8mb4_0900_ai_ci AS session_id,
           1 AS measurement_id, 1 AS cycle_number
), alerts AS (
    SELECT 1 AS id, 1 AS prediction_id,
           _utf8mb4'warning' COLLATE utf8mb4_general_ci AS level,
           _utf8mb4'기존 알림' COLLATE utf8mb4_general_ci AS message,
           CAST('2026-11-11 10:00:00' AS DATETIME) AS created_at,
           CAST(NULL AS DATETIME) AS detail_confirmed_at
), predictions AS (
    SELECT 1 AS id, 1 AS measurement_id, 65 AS predicted_wear_um,
           50 AS warning_threshold_um, 90 AS danger_threshold_um,
           CAST('2026-11-10 01:00:00' AS DATETIME) AS predicted_at
), measurements AS (
    SELECT 1 AS id, 1 AS set_id,
           _utf8mb4'기존.jpg' COLLATE utf8mb4_unicode_ci AS image_name,
           _utf8mb4'sensor.csv' COLLATE utf8mb4_general_ci AS sensor_name
), tool_sets AS (
    SELECT 1 AS set_id, 4 AS set_number
), wear_labels AS (
    SELECT 1 AS measurement_id,
           _utf8mb4'adhesion' COLLATE utf8mb4_unicode_ci AS original_type
)
"""


def test_feed_unifies_collations_on_mysql():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        with pytest.raises(mysql.connector.Error) as captured:
            cursor.execute(FIXTURE_SQL + """
                SELECT message FROM monitoring_alert_events
                UNION ALL SELECT message FROM alerts
            """)
            cursor.fetchall()
        assert captured.value.errno == 1271

        cursor.execute(FIXTURE_SQL + f"SELECT * FROM ({FEED_SQL}) AS history", (1, -540, -540, 1))
        rows = {row["id"]: row for row in cursor.fetchall()}
        assert set(rows) == {"monitoring:1", "legacy:1"}
        assert rows["monitoring:1"]["message"] == "신규 알림"
        assert rows["monitoring:1"]["sensor_name"] is None
        assert rows["legacy:1"]["image_name"] == "기존.jpg"

        cursor.execute(FIXTURE_SQL + f"""
            SELECT COUNT(*) AS total, COUNT(DISTINCT COLLATION(message)) AS collations
            FROM ({FEED_SQL}) AS history
        """, (1, -540, -540, 1))
        assert cursor.fetchone() == {"total": 2, "collations": 1}
    finally:
        cursor.close()
        connection.close()
