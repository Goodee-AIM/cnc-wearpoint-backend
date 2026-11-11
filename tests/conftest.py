import pytest


@pytest.fixture(autouse=True)
def disable_background_worker_in_tests(monkeypatch):
    # API 단위 테스트가 실행 환경의 실제 DB에 접근하지 않도록 합니다.
    monkeypatch.setenv("MONITORING_ALERT_WORKER_ENABLED", "0")
