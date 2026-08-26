#!/usr/bin/env python3
"""Perform daylight-safe BLE and protocol checks against a DWARF.

By default the probe is read-only. An exposure is performed only when the
operator supplies ``--exposure-seconds``. It never moves motors, focuses,
calibrates, or performs a GoTo.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
from typing import Any

from bleak import BleakClient

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.device_profile import get_device_profile
from dwarf_alpaca.dwarf.ble_packets import (
    DEFAULT_BLE_PASSWORD,
    DWARF_CHARACTERISTIC_UUID,
    build_req_getconfig,
    parse_notification,
)
from dwarf_alpaca.dwarf.ble_provisioner import DwarfBleProvisioner
from dwarf_alpaca.dwarf.session import CapturePhase, DwarfSession
from dwarf_alpaca.dwarf.ws_client import DwarfWsClient
from dwarf_alpaca.proto import protocol_pb2
from dwarf_alpaca.proto.task_center_pb2 import ReqGetDeviceStateInfo, ResGetDeviceStateInfo


async def _read_ble_config(model: str, address: str | None) -> dict[str, Any]:
    devices = await DwarfBleProvisioner.discover_devices(timeout=10.0)
    if address:
        device = next((item for item in devices if item.address.lower() == address.lower()), None)
    else:
        model_token = "mini" if model == "dwarfmini" else model.removeprefix("dwarf")
        device = next(
            (
                item
                for item in devices
                if item.name and model_token in item.name.lower().replace(" ", "")
            ),
            None,
        )
    if device is None:
        raise RuntimeError(f"No BLE device found for {model}")

    queue: asyncio.Queue[Any] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def notification_handler(_: Any, data: bytearray) -> None:
        try:
            packet = parse_notification(bytes(data))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        else:
            loop.call_soon_threadsafe(queue.put_nowait, packet)

    async with BleakClient(device) as client:
        await client.start_notify(DWARF_CHARACTERISTIC_UUID, notification_handler)
        try:
            await client.write_gatt_char(
                DWARF_CHARACTERISTIC_UUID,
                build_req_getconfig(DEFAULT_BLE_PASSWORD),
                response=True,
            )
            packet = await asyncio.wait_for(queue.get(), timeout=15.0)
            if isinstance(packet, Exception):
                raise packet
            if packet.cmd != 1:
                raise RuntimeError(f"Unexpected BLE response command {packet.cmd}")
            payload = packet.payload
            return {
                "name": device.name,
                "address": device.address,
                "state": int(payload.state),
                "wifi_mode": int(payload.wifi_mode),
                "ip": str(payload.ip),
                "code": int(payload.code),
            }
        finally:
            with contextlib.suppress(Exception):
                await client.stop_notify(DWARF_CHARACTERISTIC_UUID)


def _state_summary(response: ResGetDeviceStateInfo) -> dict[str, Any]:
    tele = response.tele_camera_state_info
    focus = response.focus_motor_state_info
    motion = response.motion_motor_state_info
    return {
        "code": int(response.code),
        "shooting_mode": int(response.shooting_mode),
        "tele_resolution": [int(tele.resolution_width), int(tele.resolution_height)],
        "tele_stream_type": {
            "stream_type": int(tele.stream_type.stream_type),
            "camera_id": int(tele.stream_type.cam_id),
        },
        "tele_camera_state": tele.exclusive_state.WhichOneof("current_state"),
        "focus_state": focus.exclusive_state.WhichOneof("current_state"),
        "motion_state": motion.exclusive_state.WhichOneof("current_state"),
        "has_focus_position": focus.HasField("focus_position"),
        "has_cmos_temperature": tele.HasField("cmos_temperature"),
    }


async def _read_device_state(ip: str, model: str) -> dict[str, Any]:
    profile = get_device_profile(model)
    client = DwarfWsClient(
        ip,
        major_version=profile.protocol.ws_major_version,
        minor_version=profile.protocol.ws_minor_version,
        device_id=profile.protocol.ws_device_id,
        client_id=profile.ws_client_id,
    )
    try:
        await client.connect()
        response = await client.send_request(
            protocol_pb2.ModuleId.MODULE_DEVICE_CONFIG,
            protocol_pb2.DwarfCMD.CMD_GLOBAL_TASK_GET_DEVICE_STATE_INFO,
            ReqGetDeviceStateInfo(),
            ResGetDeviceStateInfo,
            timeout=10.0,
        )
        if not isinstance(response, ResGetDeviceStateInfo):
            raise RuntimeError(f"Unexpected response {type(response).__name__}")
        return _state_summary(response)
    finally:
        await client.close()


async def _take_exposure(
    ip: str,
    model: str,
    duration: float,
    gain: int,
    filter_name: str,
) -> dict[str, Any]:
    profile = get_device_profile(model)
    settings = Settings(
        dwarf_ap_ip=ip,
        dwarf_device_model=model,
        dwarf_ws_client_id=profile.ws_client_id,
        network_mode="sta",
        calibrate_after_server_start=False,
        auto_calibrate_on_slew=False,
        allow_continue_without_darks=True,
        dwarf_mini_capture_mode="astro",
    )
    session = DwarfSession(settings)
    state = session.camera_state
    try:
        await session.camera_connect()
        state.requested_gain = gain
        state.filter_name = filter_name
        try:
            state.filter_index = profile.filters.labels.index(filter_name)
        except ValueError:
            pass
        state.requested_bin = (1, 1)
        state.requested_frame_count = 1
        await session.camera_start_exposure(
            duration,
            True,
            continue_without_darks=True,
        )
        if state.capture_task is not None:
            await asyncio.wait_for(asyncio.shield(state.capture_task), timeout=180.0)
        image = state.image
        return {
            "phase": state.capture_phase.value,
            "last_error": state.last_error,
            "applied_duration": state.applied_duration,
            "applied_gain": state.applied_gain_value,
            "applied_filter": state.applied_filter_name,
            "applied_frames": state.applied_frame_count,
            "progress_current": state.progress_current_count,
            "progress_total": state.progress_total_count,
            "retrieved_file_path": state.retrieved_file_path,
            "source_format": state.source_format,
            "source_bit_depth": state.source_bit_depth,
            "image_shape": list(image.shape) if image is not None else None,
            "image_dtype": str(image.dtype) if image is not None else None,
            "image_min": int(image.min()) if image is not None else None,
            "image_max": int(image.max()) if image is not None else None,
        }
    finally:
        if state.capture_phase in {
            CapturePhase.CONFIGURING,
            CapturePhase.WAITING_FOR_DARK,
            CapturePhase.STARTING,
            CapturePhase.EXPOSING,
            CapturePhase.PROCESSING,
            CapturePhase.TRANSFERRING,
        }:
            with contextlib.suppress(Exception):
                await session.camera_abort_exposure()
        with contextlib.suppress(Exception):
            await session.camera_disconnect()
        await session.shutdown()


async def _run(args: argparse.Namespace) -> int:
    result: dict[str, Any] = {
        "model": args.model,
        "safety": "single-exposure" if args.exposure_seconds else "read-only",
    }
    ble = await _read_ble_config(args.model, args.address)
    result["ble"] = ble
    ip = args.ip or ble["ip"]
    if not ip or ip == "192.168.88.1":
        result["websocket"] = {"skipped": "No STA address reported"}
    else:
        result["websocket"] = await _read_device_state(ip, args.model)
        if args.exposure_seconds:
            result["exposure"] = await _take_exposure(
                ip,
                args.model,
                args.exposure_seconds,
                args.gain,
                args.filter,
            )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("dwarf2", "dwarf3", "dwarfmini"), required=True)
    parser.add_argument("--address", help="Optional BLE address")
    parser.add_argument("--ip", help="Override the BLE-reported STA address")
    parser.add_argument("--exposure-seconds", type=float)
    parser.add_argument("--gain", type=int, default=60)
    parser.add_argument("--filter", default="Astro")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
