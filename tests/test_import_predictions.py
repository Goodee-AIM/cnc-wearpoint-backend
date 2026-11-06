import csv
import re
from decimal import Decimal
from unittest.mock import Mock

import pytest

import import_predictions


@pytest.fixture
def import_database(monkeypatch, tmp_path):
    """Keep import side effects in memory while honoring bound model identities."""
    measurements = []
    predictions = []
    cursor = Mock()
    connection = Mock()
    connection.cursor.return_value = cursor
    result = []

    def execute(query, params=()):
        nonlocal result
        if "FROM measurements" in query:
            result = measurements
        elif "FROM predictions" in query:
            columns = re.findall(r"\b(\w+)\s*=\s*%s", query)
            criteria = dict(zip(columns, params, strict=True))
            result = [
                row.copy()
                for row in predictions
                if all(row[column] == value for column, value in criteria.items())
            ]
        elif "INSERT INTO predictions" in query:
            match = re.search(
                r"INSERT INTO predictions\s*\((.*?)\)\s*VALUES\s*\((.*?)\)",
                query,
                re.DOTALL,
            )
            columns = [column.strip() for column in match.group(1).split(",")]
            bound_values = iter(params)
            values = [
                next(bound_values) if token.strip() == "%s" else None
                for token in match.group(2).split(",")
            ]
            predictions.append(dict(zip(columns, values, strict=True)))
        else:
            raise AssertionError("Unexpected database operation")

    cursor.execute.side_effect = execute
    cursor.fetchall.side_effect = lambda: [row.copy() for row in result]
    monkeypatch.setattr(import_predictions, "BASE_DIR", tmp_path)
    monkeypatch.setattr(import_predictions, "get_connection", Mock(return_value=connection))

    def write_csv(rows):
        with (tmp_path / "rf_test_predictions.csv").open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["Set", "ImageName", "SensorName", "Predicted_Wear"])
            writer.writeheader()
            writer.writerows(rows)

    return connection, cursor, measurements, predictions, write_csv


def test_import_stores_model_identity_and_threshold_boundary_statuses(import_database):
    connection, cursor, measurements, predictions, write_csv = import_database
    values = ["49.99999", "50", "89.99999", "90"]
    measurements.extend(
        {"id": index, "set_number": 4, "image_name": f"image{index}.png", "sensor_name": None}
        for index in range(1, 5)
    )
    write_csv([
        {"Set": 4, "ImageName": f"image{index}.png", "Predicted_Wear": wear}
        for index, wear in enumerate(values, 1)
    ])

    import_predictions.main()

    assert [prediction["status"] for prediction in predictions] == [
        "normal", "warning", "warning", "danger",
    ]
    assert [prediction["predicted_wear_um"] for prediction in predictions] == [
        Decimal(value) for value in values
    ]
    for prediction in predictions:
        assert prediction["model_name"] == "rf-csv-demo"
        assert prediction["model_version"] == "rf-csv-demo-v1"
        assert prediction["predicted_type"] is None
        assert prediction["warning_threshold_um"] == Decimal("50")
        assert prediction["danger_threshold_um"] == Decimal("90")
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("other_model,other_version", [
    ("another-model", "rf-csv-demo-v1"),
    ("rf-csv-demo", "older-version"),
])
def test_import_rerun_skips_only_the_same_model_and_version(
    import_database, capsys, other_model, other_version,
):
    connection, _, measurements, predictions, write_csv = import_database
    measurements.append({"id": 101, "set_number": 4, "image_name": "sample.png", "sensor_name": None})
    predictions.append({
        "measurement_id": 101,
        "model_name": other_model,
        "model_version": other_version,
        "predicted_wear_um": Decimal("5"),
    })
    write_csv([{"Set": 4, "ImageName": "sample.png", "Predicted_Wear": "55"}])

    import_predictions.main()

    assert len(predictions) == 2
    assert predictions[-1]["model_name"] == "rf-csv-demo"
    assert predictions[-1]["predicted_wear_um"] == Decimal("55")
    capsys.readouterr()

    import_predictions.main()

    assert len(predictions) == 2
    assert "새로 등록: 0건" in capsys.readouterr().out
    assert connection.commit.call_count == 2
    connection.rollback.assert_not_called()


def test_changed_prediction_for_same_model_rolls_back(import_database):
    connection, cursor, measurements, predictions, write_csv = import_database
    measurements.append({"id": 101, "set_number": 4, "image_name": "sample.png", "sensor_name": None})
    predictions.append({
        "measurement_id": 101,
        "model_name": "rf-csv-demo",
        "model_version": "rf-csv-demo-v1",
        "predicted_wear_um": Decimal("5"),
    })
    write_csv([{"Set": 4, "ImageName": "sample.png", "Predicted_Wear": "55"}])

    with pytest.raises(ValueError, match="기존 값과 다른 예측"):
        import_predictions.main()

    assert len(predictions) == 1
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("wear", ["-1", "NaN", "Infinity"])
def test_invalid_wear_rolls_back(import_database, wear):
    connection, cursor, measurements, predictions, write_csv = import_database
    measurements.append({"id": 101, "set_number": 4, "image_name": "sample.png", "sensor_name": None})
    write_csv([{"Set": 4, "ImageName": "sample.png", "Predicted_Wear": wear}])

    with pytest.raises(ValueError, match="잘못된 예측값"):
        import_predictions.main()

    assert predictions == []
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_database_failure_rolls_back_and_closes_resources(import_database):
    connection, cursor, _, _, write_csv = import_database
    write_csv([])
    cursor.execute.side_effect = RuntimeError("database query failed")

    with pytest.raises(RuntimeError, match="database query failed"):
        import_predictions.main()

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
