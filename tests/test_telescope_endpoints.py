from datetime import datetime, timedelta, timezone
import time

from fastapi.testclient import TestClient

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.server import build_app

client = TestClient(build_app(Settings(force_simulation=True)))


def _value(response):
    payload = response.json()
    return payload.get("Value")


def _parse_iso8601(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def test_telescope_status_endpoints_available():
    endpoints = [
        "altitude",
        "athome",
        "atpark",
        "azimuth",
        "utcdate",
        "declinationrate",
        "guideratedeclination",
        "guideraterightascension",
        "ispulseguiding",
        "rightascensionrate",
        "sideofpier",
        "siderealtime",
        "targetdeclination",
        "targetrightascension",
        "tracking",
        "trackingrate",
        "alignmentmode",
        "aperturearea",
        "aperturediameter",
        "driverinfo",
        "doesrefraction",
        "equatorialsystem",
        "focallength",
        "siteelevation",
        "slewsettletime",
        "supportedactions",
        "trackingrates",
    ]
    for endpoint in endpoints:
        resp = client.get(f"/api/v1/telescope/0/{endpoint}")
        assert resp.status_code == 200, endpoint
        body = resp.json()
        assert body["ErrorNumber"] == 0
        assert "Value" in body


def test_axis_rates_endpoint_returns_ranges():
    resp = client.get("/api/v1/telescope/0/axisrates/0")
    assert resp.status_code == 200
    rates = _value(resp)
    assert isinstance(rates, list)
    assert rates[0]["Minimum"] == -4.0
    assert rates[0]["Maximum"] == 4.0

    resp = client.get("/api/v1/telescope/0/axisrates/2")
    assert resp.status_code == 200
    rates = _value(resp)
    assert rates[0]["Minimum"] == 0.0
    assert rates[0]["Maximum"] == 0.0

    resp = client.get("/api/v1/telescope/0/axisrates", params={"Axis": 1})
    assert resp.status_code == 200
    rates = _value(resp)
    assert rates[0]["Minimum"] == -4.0
    assert rates[0]["Maximum"] == 4.0


def test_site_parameters_accept_locale_decimal():
    resp = client.put(
        "/api/v1/telescope/0/sitelatitude",
        json={"Latitude": "49,457185"},
    )
    assert resp.status_code == 200
    resp = client.get("/api/v1/telescope/0/sitelatitude")
    assert abs(_value(resp) - 49.457185) < 1e-6

    resp = client.put(
        "/api/v1/telescope/0/sitelongitude",
        json={"Longitude": "10,997732"},
    )
    assert resp.status_code == 200
    resp = client.get("/api/v1/telescope/0/sitelongitude")
    assert abs(_value(resp) - 10.997732) < 1e-6

    resp = client.put(
        "/api/v1/telescope/0/siteelevation",
        json={"Elevation": "351.4"},
    )
    assert resp.status_code == 200
    resp = client.get("/api/v1/telescope/0/siteelevation")
    assert abs(_value(resp) - 351.4) < 1e-6


def test_tracking_rates_list_contains_sidereal():
    resp = client.get("/api/v1/telescope/0/trackingrates")
    assert resp.status_code == 200
    assert _value(resp) == [0]


def test_utcdate_matches_system_clock_within_tolerance():
    resp = client.get("/api/v1/telescope/0/utcdate")
    assert resp.status_code == 200
    reported = _parse_iso8601(_value(resp))
    now = datetime.now(timezone.utc)
    assert abs((reported - now).total_seconds()) < 5


def test_setting_utcdate_with_local_time_keeps_running_clock():
    local_tz = datetime.now().astimezone().tzinfo or timezone.utc
    target_local = datetime.now(local_tz) + timedelta(minutes=5)
    naive_iso = target_local.replace(tzinfo=None).isoformat()

    resp = client.put("/api/v1/telescope/0/utcdate", json={"UTCDate": naive_iso})
    assert resp.status_code == 200

    resp = client.get("/api/v1/telescope/0/utcdate")
    assert resp.status_code == 200
    first_value = _parse_iso8601(_value(resp))
    expected = target_local.astimezone(timezone.utc)
    assert abs((first_value - expected).total_seconds()) < 5

    time.sleep(0.1)
    resp = client.get("/api/v1/telescope/0/utcdate")
    assert resp.status_code == 200
    second_value = _parse_iso8601(_value(resp))
    assert (second_value - first_value).total_seconds() >= 0

    reset_target = datetime.now(timezone.utc)
    reset_resp = client.put("/api/v1/telescope/0/utcdate", json={"UTCDate": reset_target.isoformat()})
    assert reset_resp.status_code == 200