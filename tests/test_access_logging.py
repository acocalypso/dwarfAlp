import logging

from fastapi.testclient import TestClient

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.server import build_app


def _build_client():
    app = build_app(Settings(force_simulation=True))
    return TestClient(app)


def test_access_log_skips_successful_requests(caplog):
    with _build_client() as client, caplog.at_level(logging.INFO):
        caplog.clear()
        response = client.get("/management/health")
        assert response.status_code == 200
        assert not any(record.name == "http.access" for record in caplog.records)


def test_access_log_records_non_200(caplog):
    with _build_client() as client, caplog.at_level(logging.INFO):
        caplog.clear()
        response = client.get("/api/v1/telescope/0/doesnotexist")
        assert response.status_code == 404
        access_logs = [record for record in caplog.records if record.name == "http.access"]
        assert access_logs
        assert access_logs[0].levelno >= logging.WARNING
        assert "http.request" in access_logs[0].getMessage()
