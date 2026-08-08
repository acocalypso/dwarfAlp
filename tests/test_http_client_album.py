import pytest

from dwarf_alpaca.dwarf.http_client import DwarfHttpClient


@pytest.mark.asyncio
async def test_list_astro_fits_parses_app_response(monkeypatch):
    client = DwarfHttpClient("192.0.2.1")
    captured = {}

    async def fake_post(self, path, payload, params=None):
        captured.update(path=path, payload=payload)
        return {
            "code": 0,
            "data": {
                "totalCount": 1,
                "fitsInfo": [
                    {"url": "/preview", "isFailed": False, "filePath": "/frame.fit"}
                ],
            },
        }

    monkeypatch.setattr(DwarfHttpClient, "post_json", fake_post)

    result = await client.list_astro_fits("/Astronomy/M11")

    assert captured == {
        "path": "/album/astro/fitsList",
        "payload": {"srcDir": "/Astronomy/M11"},
    }
    assert result == [
        {"url": "/preview", "isFailed": False, "filePath": "/frame.fit"}
    ]
