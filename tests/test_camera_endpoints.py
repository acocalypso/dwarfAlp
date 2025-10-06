import pytest
from fastapi.testclient import TestClient

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.server import build_app


client = TestClient(build_app(Settings(force_simulation=True)))


def _value(response):
    payload = response.json()
    return payload.get("Value")


def _connect_camera():
    resp = client.put("/api/v1/camera/0/connected", json={"Connected": True})
    assert resp.status_code == 200


def test_camera_capture_and_metadata():
    _connect_camera()

    resp = client.get("/api/v1/camera/0/canabortexposure")
    assert resp.status_code == 200 and _value(resp) is True

    resp = client.put(
        "/api/v1/camera/0/startexposure",
        params={"Duration": 0.05, "Light": True},
    )
    assert resp.status_code == 200

    resp = client.get("/api/v1/camera/0/imageready")
    assert resp.status_code == 200 and _value(resp) is True

    resp = client.get("/api/v1/camera/0/camerastate")
    assert resp.status_code == 200 and _value(resp) == 4

    resp = client.get("/api/v1/camera/0/lastexposureduration")
    assert resp.status_code == 200 and _value(resp) > 0

    resp = client.get("/api/v1/camera/0/lastexposurestarttime")
    assert resp.status_code == 200 and _value(resp)

    resp = client.get("/api/v1/camera/0/imagetimestamp")
    assert resp.status_code == 200 and _value(resp)

    resp = client.get("/api/v1/camera/0/cameraxsize")
    assert resp.status_code == 200 and _value(resp) >= 1

    resp = client.get("/api/v1/camera/0/pixelsizex")
    assert resp.status_code == 200 and _value(resp) > 0

    resp = client.get("/api/v1/camera/0/imagebytes")
    assert resp.status_code == 200
    image_payload = _value(resp)
    assert "ImageBytes" in image_payload
    assert image_payload["Dim1"] >= 1 and image_payload["Dim2"] >= 1
    assert image_payload["ImageElementType"] == 2
    assert image_payload["ImageElementTypeName"] == "Int32"
    assert image_payload["TransmissionElementType"] == 2
    assert image_payload["TransmissionElementTypeName"] == "Int32"

    resp = client.get("/api/v1/camera/0/imagearray")
    assert resp.status_code == 200
    array_response = resp.json()
    array_payload = array_response["Value"]
    assert isinstance(array_payload, list) and len(array_payload) > 0
    assert array_response["Type"] == 2
    assert array_response["TypeName"] == "Int32"
    assert array_response["Rank"] == 2
    assert isinstance(array_response["Dimensions"], list)
    assert array_response["Dimensions"][0] == len(array_payload)
    assert array_response["Dimensions"][1] == len(array_payload[0])

    resp = client.get("/api/v1/camera/0/imagearrayvariant")
    assert resp.status_code == 200
    variant_response = resp.json()
    variant_payload = variant_response["Value"]
    assert isinstance(variant_payload, list) and len(variant_payload) > 0
    assert variant_response["Type"] == 2
    assert variant_response["TypeName"] == "Int32"
    assert variant_response["Rank"] == 2
    assert isinstance(variant_response["Dimensions"], list)


def test_camera_static_metadata_properties():
    _connect_camera()

    resp = client.get("/api/v1/camera/0/driverinfo")
    assert resp.status_code == 200 and "DWARF" in _value(resp)

    resp = client.get("/api/v1/camera/0/sensortype")
    assert resp.status_code == 200 and _value(resp) == 2

    resp = client.get("/api/v1/camera/0/sensorname")
    assert resp.status_code == 200 and "IMX678" in _value(resp)

    resp = client.get("/api/v1/camera/0/electronsperadu")
    assert resp.status_code == 200
    assert _value(resp) == pytest.approx(2.75, rel=1e-3)

    resp = client.get("/api/v1/camera/0/fullwellcapacity")
    assert resp.status_code == 200 and _value(resp) > 0

    resp = client.get("/api/v1/camera/0/maxadu")
    assert resp.status_code == 200 and _value(resp) == 4095

    resp = client.get("/api/v1/camera/0/bayeroffsetx")
    assert resp.status_code == 200 and _value(resp) == 0

    resp = client.get("/api/v1/camera/0/bayeroffsety")
    assert resp.status_code == 200 and _value(resp) == 0

    resp = client.get("/api/v1/camera/0/supportedactions")
    assert resp.status_code == 200 and _value(resp) == []


def test_camera_gain_and_offset_controls():
    _connect_camera()

    resp = client.get("/api/v1/camera/0/gainmin")
    assert resp.status_code == 200
    gain_min = _value(resp)
    assert isinstance(gain_min, int)

    resp = client.get("/api/v1/camera/0/gainmax")
    assert resp.status_code == 200
    gain_max = _value(resp)
    assert isinstance(gain_max, int)
    assert gain_max == 200
    assert gain_max >= gain_min

    resp = client.get("/api/v1/camera/0/gains")
    assert resp.status_code == 200
    gains_list = _value(resp)
    assert isinstance(gains_list, list) and all(isinstance(v, int) for v in gains_list)
    assert gains_list[-1] == 200

    resp = client.get("/api/v1/camera/0/gain")
    assert resp.status_code == 200
    initial_gain = _value(resp)
    assert isinstance(initial_gain, int)

    new_gain = min(gain_min + 10, gain_max)
    resp = client.put("/api/v1/camera/0/gain", json={"Gain": new_gain})
    assert resp.status_code == 200

    resp = client.get("/api/v1/camera/0/gain")
    assert resp.status_code == 200 and _value(resp) == new_gain

    resp = client.get("/api/v1/camera/0/offset")
    assert resp.status_code == 200
    initial_offset = _value(resp)
    assert isinstance(initial_offset, int)

    resp = client.put("/api/v1/camera/0/offset", json={"Offset": 128})
    assert resp.status_code == 200

    resp = client.get("/api/v1/camera/0/offset")
    assert resp.status_code == 200 and _value(resp) == 128

    resp = client.get("/api/v1/camera/0/offsetmin")
    assert resp.status_code == 200
    offset_min = _value(resp)
    assert isinstance(offset_min, int)

    resp = client.get("/api/v1/camera/0/offsetmax")
    assert resp.status_code == 200
    offset_max = _value(resp)
    assert isinstance(offset_max, int)
    assert offset_max >= offset_min

    resp = client.put("/api/v1/camera/0/gain", json={"Gain": gain_max + 1})
    assert resp.status_code == 400

    resp = client.put("/api/v1/camera/0/offset", json={"Offset": -1})
    assert resp.status_code == 400


def test_camera_subframe_and_cooling_controls():
    _connect_camera()

    resp = client.put("/api/v1/camera/0/startx", params={"StartX": 10})
    assert resp.status_code == 200

    resp = client.put("/api/v1/camera/0/starty", params={"StartY": 5})
    assert resp.status_code == 200

    resp = client.put("/api/v1/camera/0/numx", params={"NumX": 100})
    assert resp.status_code == 200

    resp = client.put("/api/v1/camera/0/numy", params={"NumY": 80})
    assert resp.status_code == 200

    resp = client.put("/api/v1/camera/0/binx", params={"BinX": 1})
    assert resp.status_code == 200

    resp = client.put("/api/v1/camera/0/cooleron", params={"CoolerOn": False})
    assert resp.status_code == 200

    resp = client.get("/api/v1/camera/0/coolerpower")
    assert resp.status_code == 200 and _value(resp) == 0.0

    resp = client.get("/api/v1/camera/0/ccdtemperature")
    assert resp.status_code == 200


def test_camera_mutators_accept_json_payloads():
    _connect_camera()

    resp = client.put("/api/v1/camera/0/startx", json={"StartX": 12})
    assert resp.status_code == 200

    resp = client.put("/api/v1/camera/0/starty", json={"StartY": 8})
    assert resp.status_code == 200

    resp = client.put("/api/v1/camera/0/numx", json={"NumX": 64})
    assert resp.status_code == 200

    resp = client.put("/api/v1/camera/0/numy", json={"NumY": 48})
    assert resp.status_code == 200

    resp = client.put("/api/v1/camera/0/binx", json={"BinX": 1})
    assert resp.status_code == 200

    resp = client.put("/api/v1/camera/0/biny", json={"BinY": 1})
    assert resp.status_code == 200

    resp = client.put(
        "/api/v1/camera/0/startexposure",
        json={"Duration": 0.05, "Light": True},
    )
    assert resp.status_code == 200