"""Pure unit tests: never connect to RDS, Object Storage or Serving."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.routers import auto_prediction


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(auto_prediction.router)
    return TestClient(app, base_url="https://aimw.duckdns.org")


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("PREDICTION_API_ENABLED", "1")
    monkeypatch.setenv("PREDICTION_API_TOKEN", "a" * 64)
    monkeypatch.setenv("AUTO_PREDICTION_ENABLED", "1")
    monkeypatch.setenv("AUTO_PREDICTION_ORIGIN", "https://aimw.duckdns.org")


def post(client, origin="https://aimw.duckdns.org"):
    return client.post(
        "/api/measurements/auto-predict",
        headers={"Origin": origin},
        files={
            "image": ("sample.png", b"\x89PNG\r\n\x1a\n", "image/png"),
            "sensor_csv": ("sample.csv", b"1,2,3,4,5,2026-01-01T00:00:00\n", "text/csv"),
        },
    )


def test_disabled_is_fail_closed(client, monkeypatch):
    monkeypatch.delenv("AUTO_PREDICTION_ENABLED", raising=False)
    upload = AsyncMock(side_effect=AssertionError("storage must not run"))
    monkeypatch.setattr(auto_prediction, "create_measurement", upload)
    assert post(client).status_code == 503
    upload.assert_not_awaited()


def test_bad_origin_rejected_before_write(client, enabled, monkeypatch):
    upload = AsyncMock(side_effect=AssertionError("storage must not run"))
    monkeypatch.setattr(auto_prediction, "create_measurement", upload)
    assert post(client, origin="https://evil.example").status_code == 403
    upload.assert_not_awaited()


def test_missing_origin_configuration_is_503(client, enabled, monkeypatch):
    monkeypatch.delenv("AUTO_PREDICTION_ORIGIN")
    assert post(client).status_code == 503


def test_upload_predict_without_browser_token_or_login(client, enabled, monkeypatch):
    upload = AsyncMock(return_value={"measurement_id": 920})
    predict = Mock(return_value={
        "measurement_id": 920,
        "prediction_id": 84,
        "predicted_wear_um": 174.2,
        "predicted_type": "flank_wear",
        "status": "warning",
        "model_version": "1",
    })
    monkeypatch.setattr(auto_prediction, "create_measurement", upload)
    monkeypatch.setattr(auto_prediction, "execute_prediction", predict)

    response = post(client)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["measurement_id"] == 920
    assert result["measurement_status"] == "completed"
    assert result["prediction"]["model_version"] == "1"
    assert result["prediction"]["predicted_wear_um"] == 174.2
    upload.assert_awaited_once()
    predict.assert_called_once_with(920)


def test_failure_returns_committed_measurement_id(client, enabled, monkeypatch):
    monkeypatch.setattr(auto_prediction, "create_measurement", AsyncMock(return_value={"measurement_id": 921}))
    monkeypatch.setattr(
        auto_prediction, "execute_prediction", Mock(side_effect=HTTPException(502, "Prediction failed"))
    )
    response = post(client)
    assert response.status_code == 502
    assert response.json()["detail"]["measurement_id"] == 921


def test_busy_rejects_before_storage(client, enabled, monkeypatch):
    class BusySlot:
        def acquire(self, blocking=False):
            assert blocking is False
            return False

        def release(self):
            raise AssertionError("slot was never acquired")

    monkeypatch.setattr(auto_prediction, "_inference_slots", BusySlot())
    upload = AsyncMock()
    monkeypatch.setattr(auto_prediction, "create_measurement", upload)
    assert post(client).status_code == 429
    upload.assert_not_awaited()


def test_retry_requires_upload_scoped_cookie(client, enabled, monkeypatch):
    # Guessing a measurement ID or forging the origin never permits a retry.
    predict = Mock(side_effect=AssertionError("Serving and DB must not be touched"))
    monkeypatch.setattr(auto_prediction, "execute_prediction", predict)
    response = client.post("/api/measurements/921/retry", headers={"Origin": "https://aimw.duckdns.org"})
    assert response.status_code == 403
    predict.assert_not_called()


def test_failure_cookie_is_http_only_secure_and_internal_token_is_not_sent(client, enabled, monkeypatch):
    monkeypatch.setattr(auto_prediction, "create_measurement", AsyncMock(return_value={"measurement_id": 921}))
    monkeypatch.setattr(auto_prediction, "execute_prediction", Mock(side_effect=HTTPException(502, "Prediction failed")))
    response = post(client)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "INFERENCE_FAILED"
    assert response.json()["detail"]["measurement_id"] == 921
    cookie = response.headers["set-cookie"]
    assert "__Host-cnc_wp_retry_921=" in cookie
    assert "httponly" in cookie.lower()
    assert "secure" in cookie.lower()
    assert "samesite=strict" in cookie.lower()
    assert "path=/" in cookie.lower()
    assert "a" * 64 not in cookie
    assert response.headers["cache-control"] == "no-store"


def test_retry_reuses_existing_measurement_without_another_upload(client, enabled, monkeypatch):
    upload = AsyncMock(return_value={"measurement_id": 921})
    prediction = Mock(side_effect=[
        HTTPException(502, "Prediction failed"),
        {"measurement_id": 921, "prediction_id": 1001, "predicted_wear_um": 182.2, "status": "warning"},
    ])
    monkeypatch.setattr(auto_prediction, "create_measurement", upload)
    monkeypatch.setattr(auto_prediction, "execute_prediction", prediction)
    assert post(client).status_code == 502
    response = client.post("/api/measurements/921/retry", headers={"Origin": "https://aimw.duckdns.org"})
    assert response.status_code == 200, response.text
    assert response.json()["prediction"]["predicted_wear_um"] == 182.2
    assert "max-age=0" in response.headers["set-cookie"].lower()
    upload.assert_awaited_once()
    assert prediction.call_count == 2
    assert [c.args for c in prediction.call_args_list] == [(921,), (921,)]
    assert client.post("/api/measurements/921/retry", headers={"Origin": "https://aimw.duckdns.org"}).status_code == 403


def test_retry_token_is_bound_to_measurement_id(client, enabled, monkeypatch):
    monkeypatch.setattr(auto_prediction, "create_measurement", AsyncMock(return_value={"measurement_id": 921}))
    predict = Mock(side_effect=HTTPException(502, "Prediction failed"))
    monkeypatch.setattr(auto_prediction, "execute_prediction", predict)
    assert post(client).status_code == 502
    assert client.post("/api/measurements/922/retry", headers={"Origin": "https://aimw.duckdns.org"}).status_code == 403
    predict.assert_called_once_with(921)


def test_retry_tampered_cookie_rejected(client, enabled, monkeypatch):
    predict = Mock(side_effect=AssertionError("No prediction allowed"))
    monkeypatch.setattr(auto_prediction, "execute_prediction", predict)
    client.cookies.set("__Host-cnc_wp_retry_921", "v1:921:9999999999:" + "0" * 64, domain="aimw.duckdns.org", path="/")
    response = client.post("/api/measurements/921/retry", headers={"Origin": "https://aimw.duckdns.org"})
    assert response.status_code == 403
    predict.assert_not_called()


def test_retry_expiry_rejected(client, enabled, monkeypatch):
    # Sign with the real local test key but backdate expiry.
    import hashlib, hmac, time
    expiry = int(time.time()) - 10
    data = f"v1:921:{expiry}"
    sig = hmac.new(auto_prediction._retry_signing_key(), data.encode(), hashlib.sha256).hexdigest()
    client.cookies.set("__Host-cnc_wp_retry_921", data + ":" + sig, domain="aimw.duckdns.org", path="/")
    assert client.post("/api/measurements/921/retry", headers={"Origin": "https://aimw.duckdns.org"}).status_code == 403


def test_retry_busy_skips_prediction(client, enabled, monkeypatch):
    monkeypatch.setattr(auto_prediction, "create_measurement", AsyncMock(return_value={"measurement_id": 921}))
    predict = Mock(side_effect=HTTPException(502, "Prediction failed"))
    monkeypatch.setattr(auto_prediction, "execute_prediction", predict)
    assert post(client).status_code == 502

    class BusySlot:
        def acquire(self, blocking=False):
            return False
        def release(self):
            raise AssertionError("Not acquired")

    monkeypatch.setattr(auto_prediction, "_inference_slots", BusySlot())
    res = client.post("/api/measurements/921/retry", headers={"Origin": "https://aimw.duckdns.org"})
    assert res.status_code == 429
    assert res.headers["retry-after"] == "30"
    predict.assert_called_once()


def test_retry_failure_keeps_cookie_for_later_retry(client, enabled, monkeypatch):
    monkeypatch.setattr(auto_prediction, "create_measurement", AsyncMock(return_value={"measurement_id": 921}))
    predict = Mock(side_effect=HTTPException(502, "Prediction failed"))
    monkeypatch.setattr(auto_prediction, "execute_prediction", predict)
    assert post(client).status_code == 502
    assert client.post("/api/measurements/921/retry", headers={"Origin": "https://aimw.duckdns.org"}).status_code == 502
    assert client.post("/api/measurements/921/retry", headers={"Origin": "https://aimw.duckdns.org"}).status_code == 502
    assert predict.call_count == 3


def test_retry_completed_or_predicting_is_rejected(client, enabled, monkeypatch):
    monkeypatch.setattr(auto_prediction, "create_measurement", AsyncMock(return_value={"measurement_id": 921}))
    predict = Mock(side_effect=[HTTPException(502, "Prediction failed"), HTTPException(409, "Completed")])
    monkeypatch.setattr(auto_prediction, "execute_prediction", predict)
    assert post(client).status_code == 502
    resp = client.post("/api/measurements/921/retry", headers={"Origin": "https://aimw.duckdns.org"})
    assert resp.status_code == 409
    assert "재추론" in resp.json()["detail"]
    assert predict.call_count == 2


def test_retry_is_disabled_if_auto_feature_off(client, enabled, monkeypatch):
    monkeypatch.setattr(auto_prediction, "create_measurement", AsyncMock(return_value={"measurement_id": 921}))
    monkeypatch.setattr(auto_prediction, "execute_prediction", Mock(side_effect=HTTPException(502, "Prediction failed")))
    assert post(client).status_code == 502
    monkeypatch.setenv("AUTO_PREDICTION_ENABLED", "0")
    assert client.post("/api/measurements/921/retry", headers={"Origin": "https://aimw.duckdns.org"}).status_code == 503


def test_missing_private_key_blocks_before_storage(client, enabled, monkeypatch):
    monkeypatch.delenv("PREDICTION_API_TOKEN")
    upload = AsyncMock(side_effect=AssertionError("No writes without signing key"))
    monkeypatch.setattr(auto_prediction, "create_measurement", upload)
    assert post(client).status_code == 503
    upload.assert_not_awaited()


def test_input_rejected_returns_422_without_retry_cookie(client, enabled, monkeypatch):
    # Serving 400 = the files themselves are unusable; retrying cannot help.
    monkeypatch.setattr(auto_prediction, "create_measurement", AsyncMock(return_value={"measurement_id": 922}))
    rejected = HTTPException(422, {
        "code": "INPUT_REJECTED",
        "message": "모델이 입력 파일을 처리할 수 없습니다: 유효한 절삭 구간이 없습니다.",
        "measurement_id": 922,
    })
    monkeypatch.setattr(auto_prediction, "execute_prediction", Mock(side_effect=rejected))
    response = post(client)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "INPUT_REJECTED"
    assert detail["measurement_id"] == 922
    assert "유효한 절삭 구간이 없습니다." in detail["message"]
    assert "cnc_wp_retry" not in response.headers.get("set-cookie", "")
