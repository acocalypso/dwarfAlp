from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Type

from google.protobuf import message as _message

from ..proto import ble_pb2

FRAME_HEADER = 0xAA
FRAME_END = 0x0D
PROTOCOL_ID = 0x01
PACKAGE_ID = 0x00
TOTAL_ID = 0x01
RESERVED1_ID = 0x00
RESERVED2_ID = 0x00

DWARF_CHARACTERISTIC_UUID = "00009999-0000-1000-8000-00805f9b34fb"
DWARF_SERVICE_UUIDS: Tuple[str, ...] = (
    "0000daf2-0000-1000-8000-00805f9b34fb",
    "0000daf3-0000-1000-8000-00805f9b34fb",
    "0000DAF5-0000-1000-8000-00805F9B34FB"
)
DEFAULT_BLE_PASSWORD = "DWARF_12345678"


class BlePacketError(RuntimeError):
    """Raised when a BLE packet is malformed or reports an error."""


def calculate_crc16(data: bytes) -> int:
    """Compute the Modbus CRC16 used by DWARF BLE frames."""
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            odd = crc & 0x0001
            crc >>= 1
            if odd:
                crc ^= 0xA001
    return crc & 0xFFFF


def _build_frame(cmd: int, payload: bytes) -> bytes:
    header = bytes(
        [
            FRAME_HEADER,
            PROTOCOL_ID,
            cmd & 0xFF,
            PACKAGE_ID,
            TOTAL_ID,
            RESERVED1_ID,
            RESERVED2_ID,
        ]
    )
    length_bytes = len(payload).to_bytes(2, byteorder="big")
    core = header + length_bytes + payload
    crc = calculate_crc16(core).to_bytes(2, byteorder="big")
    return core + crc + bytes([FRAME_END])


def build_req_getconfig(ble_password: str) -> bytes:
    message = ble_pb2.ReqGetconfig()
    message.cmd = 1
    message.ble_psd = ble_password
    return _build_frame(message.cmd, message.SerializeToString())


def build_req_sta(auto_start: int, ble_password: str, ssid: str, password: str) -> bytes:
    message = ble_pb2.ReqSta()
    message.cmd = 3
    message.auto_start = auto_start
    message.ble_psd = ble_password
    message.ssid = ssid
    message.psd = password
    return _build_frame(message.cmd, message.SerializeToString())


def build_req_reset() -> bytes:
    message = ble_pb2.ReqReset()
    message.cmd = 5
    return _build_frame(message.cmd, message.SerializeToString())


def build_req_getwifilist() -> bytes:
    message = ble_pb2.ReqGetwifilist()
    message.cmd = 6
    return _build_frame(message.cmd, message.SerializeToString())


_MESSAGE_TYPES: Dict[int, Type[_message.Message]] = {
    0: ble_pb2.ResReceiveDataError,
    1: ble_pb2.ResGetconfig,
    2: ble_pb2.ResAp,
    3: ble_pb2.ResSta,
    4: ble_pb2.ResSetblewifi,
    5: ble_pb2.ResReset,
    6: ble_pb2.ResWifilist,
    7: ble_pb2.ResGetsysteminfo,
    8: ble_pb2.ResCheckFile,
}


@dataclass(slots=True)
class ParsedPacket:
    cmd: int
    payload: _message.Message


def parse_notification(data: bytes) -> ParsedPacket:
    if len(data) < 12:
        raise BlePacketError("BLE packet too short")

    if data[0] != FRAME_HEADER or data[-1] != FRAME_END:
        raise BlePacketError("Invalid BLE frame markers")

    cmd = data[2]
    length = int.from_bytes(data[7:9], byteorder="big", signed=False)
    payload_start = 9
    payload_end = payload_start + length
    if payload_end + 3 > len(data):
        raise BlePacketError("BLE payload length mismatch")

    payload_bytes = data[payload_start:payload_end]
    crc_received = int.from_bytes(data[payload_end:payload_end + 2], byteorder="big")
    crc_expected = calculate_crc16(data[:payload_end])
    if crc_received != crc_expected:
        raise BlePacketError("BLE CRC mismatch")

    message_type = _MESSAGE_TYPES.get(cmd)
    if message_type is None:
        raise BlePacketError(f"Unknown BLE command {cmd}")

    message = message_type()
    message.ParseFromString(payload_bytes)
    return ParsedPacket(cmd=cmd, payload=message)


def describe_ble_error(code: int) -> str:
    try:
        return ble_pb2.DwarfBleErrorCode.Name(code)
    except ValueError:
        return str(code)
