from __future__ import annotations

import asyncio
import json
import types
from pathlib import Path

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf import exposure
from dwarf_alpaca.dwarf.session import (
    CaptureConfigurationError,
    DwarfSession,
    FilterOption,
)
from dwarf_alpaca.proto import protocol_pb2
from dwarf_alpaca.proto.dwarf_messages import ComResponse
from dwarf_alpaca.proto.task_center_pb2 import ResGetDeviceStateInfo


@pytest.fixture()
def params_config() -> dict[str, object]:
    sample_path = Path(__file__).parent / "fixtures" / "params_config_sample.json"
    with sample_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_exposure_resolver_chooses_expected_index(params_config: dict[str, object]) -> None:
    resolver = exposure.ExposureResolver.from_config(params_config)
    assert resolver is not None
    assert resolver.choose_index(1.0) == 120
    assert any(abs(value - 1.0) < 1e-9 for value in resolver.available_durations())


def test_format_timezone_label_handles_offsets() -> None:
    session = DwarfSession(Settings())
    assert session._format_timezone_label(0.0) == "UTC"
    assert session._format_timezone_label(2.0) == "UTC+02:00"
    assert session._format_timezone_label(-3.5) == "UTC-03:30"
    assert session._format_timezone_label(5.75) == "UTC+05:45"


@pytest.mark.parametrize("model", ["dwarf2", "dwarf3", "dwarfmini"])
def test_all_models_use_v3_ws_profile(model: str) -> None:
    session = DwarfSession(Settings(dwarf_device_model=model))
    assert session._ws_client.minor_version == 20
    assert session._ws_client.device_id == 4


@pytest.mark.asyncio
async def test_mini_filter_labels_are_mapped_from_firmware_aliases() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session._params_config = {
        "data": {
            "cameras": [
                {
                    "name": "tele",
                    "supportParams": [
                        {
                            "id": 123,
                            "name": "Lens Mode",
                            "supportMode": [{"name": "gear", "index": 0}],
                            "gearMode": {
                                "values": [
                                    {"index": 0, "name": "DuoBand"},
                                    {"index": 1, "name": "Astro"},
                                    {"index": 2, "name": "VIS"},
                                ]
                            },
                        }
                    ],
                }
            ]
        }
    }
    session._filter_options = None

    labels = await session.get_filter_labels()
    assert labels == ["Astro", "Duo-Band"]


@pytest.mark.asyncio
async def test_ensure_default_filter_uses_dwarf3_v3_capture_index(
    params_config: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarf3"))
    session.simulation = False
    session._params_config = params_config
    session.camera_state.filter_name = ""
    calls: list[tuple[int, int]] = []

    async def noop(*_args, **_kwargs):
        return None

    async def fake_send_and_check(_module_id, command_id, request, **_kwargs):
        calls.append((command_id, int(request.value)))

    monkeypatch.setattr(session, "_ensure_ws", noop)
    monkeypatch.setattr(session, "_send_and_check", fake_send_and_check)

    await session._ensure_default_filter("VIS")

    assert session.camera_state.filter_name == "VIS Filter"
    assert session.camera_state.filter_index == 0
    assert calls == [(16703, 0)]


@pytest.mark.asyncio
async def test_mini_filter_options_use_astro_start_ir_index() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._params_config = {"data": {"version": "1.0.0"}}
    session._filter_options = None

    options = await session._get_filter_options()

    assert [opt.label for opt in options] == ["Astro", "Duo-Band"]
    assert [opt.index for opt in options] == [1, 2]
    assert all(opt.controllable for opt in options)
    assert all(
        opt.parameter and opt.parameter.get("__control") == "astro_capture_ir_index"
        for opt in options
    )


@pytest.mark.asyncio
async def test_dwarf3_filter_options_use_model_specific_v3_indices() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarf3"))

    options = await session._get_filter_options()

    assert [entry.label for entry in options] == [
        "VIS Filter",
        "Astro Filter",
        "Duo-Band Filter",
    ]
    assert [entry.index for entry in options] == [0, 1, 2]
    assert all(entry.controllable for entry in options)
    assert all(entry.parameter["__control"] == "v3_camera_param" for entry in options)


@pytest.mark.asyncio
async def test_dwarf3_filter_selection_uses_v3_adjust_command() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarf3"))
    session.simulation = False
    calls: list[tuple[int, int, int]] = []

    async def fake_ensure_ws(self) -> None:  # type: ignore[override]
        return None

    async def fake_send_and_check(self, module_id, command_id, request, **_kwargs):  # type: ignore[override]
        calls.append((command_id, int(request.param_id), int(request.value)))

    session._ensure_ws = types.MethodType(fake_ensure_ws, session)
    session._send_and_check = types.MethodType(fake_send_and_check, session)

    options = await session._get_filter_options()
    await session._apply_filter_option(1, options[1])

    assert calls == [(16703, 0x20100000000000D, 1)]
    assert session.camera_state.filter_name == "Astro Filter"
    assert session.camera_state.applied_filter_name == "Astro Filter"


@pytest.mark.asyncio
async def test_apply_filter_option_remembers_mini_ir_index_for_next_capture() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False

    filter_option = FilterOption(
        parameter={"__control": "astro_capture_ir_index"},
        mode_index=0,
        index=2,
        label="Duo-Band",
        continue_value=None,
        controllable=True,
    )

    await session._apply_filter_option(1, filter_option)

    assert session.camera_state.filter_name == "Duo-Band"
    assert session.camera_state.filter_index == 1
    assert session.camera_state.applied_filter_name is None


@pytest.mark.asyncio
async def test_mini_filter_options_do_not_advertise_dark_as_normal_position() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._params_config = {"data": {"version": "1.0.0"}}
    session._filter_options = None

    options = await session._get_filter_options()

    assert [opt.label for opt in options] == ["Astro", "Duo-Band"]
    assert all(opt.controllable for opt in options)
    assert "Dark" not in [opt.label for opt in options]


@pytest.mark.asyncio
async def test_set_v3_camera_param_mini_uses_adjust_only_on_timeouts() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    calls: list[tuple[int, int]] = []

    async def fake_ensure_ws(self) -> None:  # type: ignore[override]
        return None

    async def fake_send_and_check(self, module_id, command_id, request, **_kwargs):  # type: ignore[override]
        calls.append((command_id, int(getattr(request, "param_id", 0))))
        if command_id == 16703:
            raise asyncio.TimeoutError()
        return None

    session._ensure_ws = types.MethodType(fake_ensure_ws, session)
    session._send_and_check = types.MethodType(fake_send_and_check, session)

    with pytest.raises(CaptureConfigurationError, match="not confirmed"):
        await session._set_v3_camera_param(param_id=13, value=2, flag=0)

    # Mini path uses fast adjust-only retries but does not claim an unconfirmed write.
    command_ids = [cmd for cmd, _ in calls]
    assert set(command_ids) == {16703}
    assert len(command_ids) >= 1
    assert session._ws_v3_filter_param_id is not None


@pytest.mark.asyncio
async def test_set_v3_camera_param_mini_prefers_adjust_with_packed_id() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    calls: list[tuple[int, int]] = []

    async def fake_ensure_ws(self) -> None:  # type: ignore[override]
        return None

    async def fake_send_and_check(self, module_id, command_id, request, **_kwargs):  # type: ignore[override]
        calls.append((command_id, int(getattr(request, "param_id", 0))))
        return None

    session._ensure_ws = types.MethodType(fake_ensure_ws, session)
    session._send_and_check = types.MethodType(fake_send_and_check, session)

    await session._set_v3_camera_param(param_id=0x20100000000000D, value=1, flag=0)

    assert calls == [(16703, 0x20100000000000D)]


@pytest.mark.asyncio
async def test_set_v3_camera_param_mini_sticky_param_id_avoids_fanout() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._ws_v3_filter_param_id = 13
    calls: list[tuple[int, int]] = []

    async def fake_ensure_ws(self) -> None:  # type: ignore[override]
        return None

    async def fake_send_and_check(self, module_id, command_id, request, **_kwargs):  # type: ignore[override]
        calls.append((command_id, int(getattr(request, "param_id", 0))))
        raise asyncio.TimeoutError()

    session._ensure_ws = types.MethodType(fake_ensure_ws, session)
    session._send_and_check = types.MethodType(fake_send_and_check, session)

    with pytest.raises(CaptureConfigurationError, match="not confirmed"):
        await session._set_v3_camera_param(param_id=0x20100000000000D, value=2, flag=0)

    assert calls == [(16703, 13)]


def test_mini_filter_param_id_detection_accepts_index_13() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))

    assert session._is_likely_filter_param_id(13)

    # Packed v3 format: shootingMode/category/cameraId/paramIndex
    packed = (2 << 24) | (4 << 16) | (0 << 8) | 13
    assert session._is_likely_filter_param_id(packed)


@pytest.mark.asyncio
async def test_mini_filter_options_ignore_unverified_http_aliases() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._params_config = {
        "data": {
            "cameras": [
                {
                    "name": "tele",
                    "supportParams": [
                        {
                            "id": 0x0204000D,
                            "name": "Lens Mode",
                            "supportMode": [{"name": "gear", "index": 0}],
                            "gearMode": {
                                # Intentionally shuffled order and non-sequential indices.
                                "values": [
                                    {"index": 2, "name": "VIS"},
                                    {"index": 0, "name": "DuoBand"},
                                    {"index": 1, "name": "Astro"},
                                ]
                            },
                        }
                    ],
                }
            ]
        }
    }
    session._filter_options = None

    options = await session._get_filter_options()

    assert [entry.label for entry in options] == ["Astro", "Duo-Band"]
    assert [entry.index for entry in options] == [1, 2]


@pytest.mark.asyncio
async def test_bootstrap_v3_state_queries_config_without_switching_mode() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._ws_client._conn = types.SimpleNamespace(closed=False, close_code=None)

    calls: list[tuple[int, int]] = []

    async def fake_send_request(self, module_id, command_id, request, response_cls, **_kwargs):  # type: ignore[override]
        calls.append((module_id, command_id))
        if command_id == 16405:
            response = ResGetDeviceStateInfo()
            response.code = protocol_pb2.OK
            response.shooting_mode = 8
            response.tele_camera_state_info.resolution_width = 1920
            response.tele_camera_state_info.resolution_height = 1080
            response.tele_camera_state_info.h_fov = 2.14
            response.tele_camera_state_info.v_fov = 1.2
            response.tele_camera_state_info.cmos_temperature.temperature = 18
            response.tele_camera_state_info.cmos_temperature.camera_type = 0
            response.tele_camera_state_info.exclusive_state.capture_raw_state.state = 3
            response.tele_camera_state_info.exclusive_state.capture_raw_state.camera_type = 0
            response.device_state_info.calibration_result.azi = 181.25
            response.device_state_info.calibration_result.alt = 47.5
            return response
        raise AssertionError(f"unexpected command {command_id}")

    session._send_request = types.MethodType(fake_send_request, session)

    await session._bootstrap_v3_state()

    assert calls == [(14, 16405)]
    assert session._v3_device_state_mode == 8
    assert session._v3_device_config_bytes is not None
    assert session._v3_device_config_bytes > 3
    assert session._astro_capture_operation_state == 3
    assert session.camera_state.reported_preview_width == 1920
    assert session.camera_state.reported_preview_height == 1080
    assert session.camera_state.reported_fv_width == pytest.approx(2.14)
    assert session.camera_state.reported_fv_height == pytest.approx(1.2)
    assert session.camera_state.temperature_c == pytest.approx(18.0)
    assert session._calibration_azimuth == pytest.approx(181.25)
    assert session._calibration_altitude == pytest.approx(47.5)


@pytest.mark.asyncio
async def test_ensure_master_lock_triggers_v3_bootstrap() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._ws_client._conn = types.SimpleNamespace(closed=False, close_code=None)

    called = {"bootstrap": False}

    async def fake_ws_send_request(self, module_id, command_id, request, response_cls, **_kwargs):  # type: ignore[override]
        assert module_id == protocol_pb2.ModuleId.MODULE_SYSTEM
        assert command_id == protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_MASTER
        response = ComResponse()
        response.code = protocol_pb2.OK
        return response

    async def fake_bootstrap(self) -> None:  # type: ignore[override]
        called["bootstrap"] = True

    session._ws_client.send_request = types.MethodType(fake_ws_send_request, session._ws_client)
    session._bootstrap_v3_state = types.MethodType(fake_bootstrap, session)

    await session._ensure_master_lock()

    assert session._master_lock_acquired is True
    assert called["bootstrap"] is True
