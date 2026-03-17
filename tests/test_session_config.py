from __future__ import annotations

import asyncio
import json
import types
from pathlib import Path

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf import exposure
from dwarf_alpaca.dwarf.session import DwarfSession, FilterOption
from dwarf_alpaca.proto import protocol_pb2
from dwarf_alpaca.proto.dwarf_messages import ComResponse, V3ResGetDeviceConfig, V3ResModeQuery


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


def test_dwarf_mini_uses_v3_ws_profile() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    assert session._ws_client.minor_version == 20
    assert session._ws_client.device_id == 4


def test_non_mini_uses_v2_ws_profile() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarf3"))
    assert session._ws_client.minor_version == 2
    assert session._ws_client.device_id == 1

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
    assert labels == ["Duo-Band", "Dark", "No Filter"]


@pytest.mark.asyncio
async def test_ensure_default_filter_prefers_support_params(params_config: dict[str, object]) -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarf3"))
    session.simulation = False
    session._params_config = params_config
    session.camera_state.filter_name = ""

    taken: dict[str, object] = {}

    async def fake_set_ir_cut(self, *, value: int) -> None:  # type: ignore[override]
        taken["ircut_value"] = value

    async def fake_set_feature_param(self, *args, **kwargs) -> None:  # type: ignore[override]
        raise AssertionError("_set_feature_param should not be called for IR Cut filters")

    async def fake_ensure_ws(self) -> None:  # type: ignore[override]
        return None

    session._set_ir_cut = types.MethodType(fake_set_ir_cut, session)
    session._set_feature_param = types.MethodType(fake_set_feature_param, session)
    session._ensure_ws = types.MethodType(fake_ensure_ws, session)

    await session._ensure_default_filter("VIS")

    assert taken["ircut_value"] == 0
    assert session.camera_state.filter_name == "VIS Filter"


@pytest.mark.asyncio
async def test_mini_filter_options_use_ws_v3_param_when_http_lacks_filter_data() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._params_config = {"data": {"version": "1.0.0"}}
    session._ws_v3_filter_param_id = 8
    session._ws_v3_filter_param_flag = 0
    session._filter_options = None

    async def fake_ensure_ws_feature_params(self) -> None:  # type: ignore[override]
        return None

    session._ensure_ws_feature_params = types.MethodType(fake_ensure_ws_feature_params, session)

    options = await session._get_filter_options()

    assert [opt.label for opt in options] == ["Duo-Band", "Dark", "No Filter"]
    assert all(opt.controllable for opt in options)
    assert all(opt.parameter and opt.parameter.get("__control") == "v3_camera_param" for opt in options)


@pytest.mark.asyncio
async def test_apply_filter_option_uses_v3_camera_param_control_for_mini() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False

    captured: dict[str, int] = {}

    async def fake_set_v3_camera_param(self, *, param_id: int, value: int, flag: int = 0) -> None:  # type: ignore[override]
        captured["param_id"] = param_id
        captured["value"] = value
        captured["flag"] = flag

    session._set_v3_camera_param = types.MethodType(fake_set_v3_camera_param, session)

    filter_option = FilterOption(
        parameter={"__control": "v3_camera_param", "__v3_param_id": 8, "flag": 1},
        mode_index=1,
        index=2,
        label="No Filter",
        continue_value=None,
        controllable=True,
    )

    await session._apply_filter_option(2, filter_option)

    assert captured == {"param_id": 8, "value": 2, "flag": 1}
    assert session.camera_state.filter_name == "No Filter"
    assert session.camera_state.filter_index == 2


@pytest.mark.asyncio
async def test_mini_filter_options_use_default_param_when_discovery_missing() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._params_config = {"data": {"version": "1.0.0"}}
    session._ws_v3_filter_param_id = None
    session._ws_v3_filter_param_flag = 0
    session._filter_options = None

    async def fake_ensure_ws_feature_params(self) -> None:  # type: ignore[override]
        self._ws_feature_params = []

    session._ensure_ws_feature_params = types.MethodType(fake_ensure_ws_feature_params, session)

    options = await session._get_filter_options()

    assert [opt.label for opt in options] == ["Duo-Band", "Dark", "No Filter"]
    assert all(opt.controllable for opt in options)
    assert all(opt.parameter and opt.parameter.get("__v3_param_id") == 0x20100000000000D for opt in options)


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

    await session._set_v3_camera_param(param_id=13, value=2, flag=0)

    # Mini path uses fast adjust-only retries and keeps state coherent even when unconfirmed.
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

    await session._set_v3_camera_param(param_id=0x20100000000000D, value=2, flag=0)

    assert calls == [(16703, 13)]


def test_mini_filter_param_id_detection_accepts_index_13() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))

    assert session._is_likely_filter_param_id(13)

    # Packed v3 format: shootingMode/category/cameraId/paramIndex
    packed = (2 << 24) | (4 << 16) | (0 << 8) | 13
    assert session._is_likely_filter_param_id(packed)


@pytest.mark.asyncio
async def test_mini_filter_options_are_canonicalized_to_three_positions() -> None:
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

    assert [entry.label for entry in options] == ["Duo-Band", "Dark", "No Filter"]
    # Keep device values intact while exposing canonical Alpaca positions.
    assert [entry.index for entry in options] == [0, 1, 2]


@pytest.mark.asyncio
async def test_bootstrap_mini_v3_state_queries_mode_and_config() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._ws_client._conn = types.SimpleNamespace(closed=False, close_code=None)

    calls: list[tuple[int, int]] = []

    async def fake_send_request(self, module_id, command_id, request, response_cls, **_kwargs):  # type: ignore[override]
        calls.append((module_id, command_id))
        if command_id == 16402:
            response = V3ResModeQuery()
            response.code = protocol_pb2.OK
            response.mode = 8
            return response
        if command_id == 16405:
            response = V3ResGetDeviceConfig()
            response.code = protocol_pb2.OK
            response.config_data = b"abc"
            return response
        raise AssertionError(f"unexpected command {command_id}")

    session._send_request = types.MethodType(fake_send_request, session)

    await session._bootstrap_mini_v3_state()

    assert calls == [(14, 16402), (14, 16405)]
    assert session._v3_device_state_mode == 8
    assert session._v3_device_config_bytes == 3


@pytest.mark.asyncio
async def test_ensure_master_lock_triggers_mini_v3_bootstrap() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._ws_client._conn = types.SimpleNamespace(closed=False, close_code=None)

    called = {"bootstrap": False}

    async def fake_ws_send_request(self, module_id, command_id, request, response_cls, **_kwargs):  # type: ignore[override]
        assert module_id == protocol_pb2.ModuleId.MODULE_SYSTEM
        assert command_id == protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_MASTERLOCK
        response = ComResponse()
        response.code = protocol_pb2.OK
        return response

    async def fake_bootstrap(self) -> None:  # type: ignore[override]
        called["bootstrap"] = True

    session._ws_client.send_request = types.MethodType(fake_ws_send_request, session._ws_client)
    session._bootstrap_mini_v3_state = types.MethodType(fake_bootstrap, session)

    await session._ensure_master_lock()

    assert session._master_lock_acquired is True
    assert called["bootstrap"] is True
