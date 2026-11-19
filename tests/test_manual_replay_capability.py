"""Set test replay requires its own unforgeable, measurement-specific cookie."""
from types import SimpleNamespace
from starlette.responses import JSONResponse
from app.api.routers import auto_prediction as api


def _issued_replay_cookie(measurement_id):
    response = JSONResponse({"ok": True})
    api._allow_replay(response, measurement_id)
    raw = response.headers["set-cookie"]
    name, value = raw.split(";", 1)[0].split("=", 1)
    return name, value, raw


def test_replay_cookie_is_httponly_secure_and_bound_to_measurement(monkeypatch):
    monkeypatch.setenv("PREDICTION_API_TOKEN", "a" * 64)
    name, value, raw = _issued_replay_cookie(920)
    assert name == "__Host-cnc_wp_replay_920"
    assert all(flag in raw.lower() for flag in ("httponly", "secure", "samesite=strict", "path=/"))
    assert api._has_replay_capability(SimpleNamespace(cookies={name: value}), 920)
    assert not api._has_replay_capability(SimpleNamespace(cookies={name: value}), 921)
    assert not api._has_replay_capability(SimpleNamespace(cookies={name: "bad"}), 920)


def test_retry_cookie_does_not_grant_successful_replay(monkeypatch):
    monkeypatch.setenv("PREDICTION_API_TOKEN", "a" * 64)
    name = api._replay_cookie_name(920)
    failed_upload_cookie = api._retry_capability(920)
    assert not api._has_replay_capability(
        SimpleNamespace(cookies={name: failed_upload_cookie}), 920
    )
