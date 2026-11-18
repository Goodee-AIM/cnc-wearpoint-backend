"""Offline security tests: no RDS, Object Storage, or Serving writes."""

import hashlib
import secrets
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.predictions import auth_router, router
from app.core import prediction_session as auth

ORIGIN = "https://aimw.duckdns.org"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PREDICTION_API_ENABLED", "1")
    monkeypatch.setenv("PREDICTION_API_TOKEN", "private-service-secret")
    monkeypatch.setenv("PREDICTION_SESSION_SECRET", "session-signing-secret-for-tests-min-32-chars")
    monkeypatch.setenv("PREDICTION_BROWSER_ORIGIN", ORIGIN)
    monkeypatch.setenv("PREDICTION_OPERATOR_USERNAME", "operator")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", b"correct-password", salt, 300000)
    monkeypatch.setenv("PREDICTION_OPERATOR_PASSWORD_HASH", f"pbkdf2_sha256$300000${salt.hex()}${digest.hex()}")
    monkeypatch.setattr("app.api.routers.predictions.execute_prediction", lambda measurement_id: {"measurement_id": measurement_id, "status": "completed"})
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(router)
    with TestClient(app, base_url=ORIGIN) as test_client:
        yield test_client


def login(client, headers=None, password="correct-password"):
    return client.post("/api/prediction-auth/login", json={"username": "operator", "password": password}, headers=headers or {"Origin": ORIGIN})


def test_no_login_cookie_denies_prediction(client):
    response = client.post("/api/measurements/42/predict", headers={"Origin": ORIGIN})
    assert response.status_code == 401


def test_login_and_prediction_without_private_token(client):
    response = login(client)
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert "private-service-secret" not in response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "secure" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert client.get("/api/prediction-auth/session").json()["authenticated"] is True
    result = client.post("/api/measurements/42/predict", headers={"Origin": ORIGIN})
    assert result.status_code == 200
    assert result.json()["measurement_id"] == 42
    assert login(client, password="wrong-password").status_code == 401


def test_cross_origin_login_and_prediction_rejected(client):
    assert login(client, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert login(client).status_code == 200
    assert client.post("/api/measurements/42/predict", headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.post("/api/measurements/42/predict").status_code == 403


def test_forged_cookie_rejected(client):
    client.cookies.set(auth.COOKIE_NAME, "fake.cookie")
    response = client.post("/api/measurements/42/predict", headers={"Origin": ORIGIN})
    assert response.status_code == 401


def test_expired_cookie_rejected(client, monkeypatch):
    assert login(client).status_code == 200
    monkeypatch.setattr(auth.time, "time", lambda: 9_999_999_999)
    assert client.post("/api/measurements/42/predict", headers={"Origin": ORIGIN}).status_code == 401


def test_logout_deletes_cookie(client):
    assert login(client).status_code == 200
    response = client.post("/api/prediction-auth/logout", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert client.get("/api/prediction-auth/session").json()["authenticated"] is False


def test_legacy_server_token_still_works(client):
    response = client.post("/api/measurements/42/predict", headers={"X-Prediction-Token": "private-service-secret"})
    assert response.status_code == 200
    assert client.post("/api/measurements/42/predict", headers={"X-Prediction-Token": "wrong"}).status_code == 401


def test_disabled_and_misconfigured_fail_closed(client, monkeypatch):
    monkeypatch.setenv("PREDICTION_API_ENABLED", "0")
    assert login(client).status_code == 503
    assert client.post("/api/measurements/42/predict", headers={"Origin": ORIGIN}).status_code == 503
    monkeypatch.setenv("PREDICTION_API_ENABLED", "1")
    monkeypatch.delenv("PREDICTION_SESSION_SECRET")
    assert login(client).status_code == 503
    # No cookie remains a 401; a presented cookie with invalid server config is 503.
    assert client.post("/api/measurements/42/predict", headers={"Origin": ORIGIN}).status_code == 401
    client.cookies.set(auth.COOKIE_NAME, "fake.cookie")
    assert client.post("/api/measurements/42/predict", headers={"Origin": ORIGIN}).status_code == 503
