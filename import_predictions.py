import csv
from decimal import Decimal
from pathlib import Path

from app.core.database import get_connection


BASE_DIR = Path(__file__).resolve().parent
MODEL_VERSION = "rf-csv-demo-v1"
WARNING = Decimal("50")
DANGER = Decimal("90")


def image_key(name):
    return Path(name.replace("\\", "/")).stem


def main():
    csv_path = BASE_DIR / "rf_test_predictions.csv"

    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"Set", "ImageName", "Predicted_Wear"}

        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                "CSV에 Set, ImageName, Predicted_Wear 열이 필요합니다."
            )

        rows = list(reader)

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    added = 0
    skipped = 0
    unmatched = []
    sensor_mismatches = []

    try:
        cursor.execute(
            """
            SELECT
                m.id,
                s.set_number,
                m.image_name,
                m.sensor_name
            FROM measurements AS m
            JOIN tool_sets AS s ON s.id = m.set_id
            WHERE s.set_number BETWEEN 4 AND 11
              AND m.image_name IS NOT NULL
            """
        )

        measurements = {}

        for item in cursor.fetchall():
            key = (
                item["set_number"],
                image_key(item["image_name"]),
            )

            if key in measurements:
                raise ValueError(f"DB 이미지 연결 중복: {key}")

            measurements[key] = item

        seen = set()

        for row in rows:
            set_number = int(Decimal(row["Set"].strip()))

            if not 4 <= set_number <= 11:
                continue

            name = row["ImageName"].strip()
            key = (set_number, image_key(name))

            if key in seen:
                raise ValueError(f"CSV 예측 행 중복: {key}")

            seen.add(key)

            predicted = Decimal(row["Predicted_Wear"].strip())

            if not predicted.is_finite() or predicted < 0:
                raise ValueError(f"잘못된 예측값: {name}")

            # DB의 소수점 자릿수와 동일하게 저장
            predicted = predicted.quantize(Decimal("0.00001"))

            measurement = measurements.get(key)

            if measurement is None:
                unmatched.append(f"Set{set_number}: {name}")
                continue

            # CSV와 DB의 센서 연결도 확인
            csv_sensor = (row.get("SensorName") or "").strip()
            db_sensor = measurement["sensor_name"]

            if csv_sensor and csv_sensor != db_sensor:
                sensor_mismatches.append(
                    f"Set{set_number}: {name}\n"
                    f"  CSV 센서: {csv_sensor}\n"
                    f"  DB 센서: {db_sensor}"
                )
                continue

            cursor.execute(
                """
                SELECT predicted_wear_um
                FROM predictions
                WHERE measurement_id = %s
                  AND model_version = %s
                """,
                (measurement["id"], MODEL_VERSION),
            )

            existing = cursor.fetchall()

            if existing:
                if any(
                    item["predicted_wear_um"] != predicted
                    for item in existing
                ):
                    raise ValueError(
                        f"기존 값과 다른 예측입니다: {name}. "
                        "변경된 CSV에는 새 MODEL_VERSION을 사용해주세요."
                    )

                skipped += 1
                continue

            if predicted >= DANGER:
                status = "danger"
            elif predicted >= WARNING:
                status = "warning"
            else:
                status = "normal"

            cursor.execute(
                """
                INSERT INTO predictions (
                    measurement_id,
                    predicted_wear_um,
                    predicted_type,
                    model_version,
                    warning_threshold_um,
                    danger_threshold_um,
                    status
                )
                VALUES (%s, %s, NULL, %s, %s, %s, %s)
                """,
                (
                    measurement["id"],
                    predicted,
                    MODEL_VERSION,
                    WARNING,
                    DANGER,
                    status,
                ),
            )
            added += 1

        connection.commit()

        print("임시 예측 결과 등록 완료")
        print(f"새로 등록: {added}건")
        print(f"이미 등록되어 건너뜀: {skipped}건")
        print(f"측정 연결 없음: {len(unmatched)}건")
        print(f"센서 연결 불일치: {len(sensor_mismatches)}건")

        for message in unmatched:
            print("[측정 연결 없음]", message)

        for message in sensor_mismatches:
            print("[센서 연결 불일치]", message)

    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()  