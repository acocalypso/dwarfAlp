from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Type

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message


@dataclass(frozen=True)
class MessageSpec:
    name: str
    fields: tuple[tuple[str, int, int, int] | tuple[str, int, int, int, str], ...]


def _build_file_descriptor() -> descriptor_pool.DescriptorPool:
    pool = descriptor_pool.DescriptorPool()
    file_descriptor = descriptor_pb2.FileDescriptorProto()
    file_descriptor.name = "dwarf_messages.proto"
    file_descriptor.package = "dwarf"

    enums = {
        "MessageTypeId": (
            ("TYPE_REQUEST", 0),
            ("TYPE_REQUEST_RESPONSE", 1),
            ("TYPE_NOTIFICATION", 2),
            ("TYPE_NOTIFICATION_RESPONSE", 3),
        ),
    }

    for enum_name, values in enums.items():
        enum_desc = file_descriptor.enum_type.add()
        enum_desc.name = enum_name
        for value_name, number in values:
            value = enum_desc.value.add()
            value.name = value_name
            value.number = number

    messages = (
        MessageSpec(
            name="WsPacket",
            fields=(
                ("major_version", 1, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("minor_version", 2, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("device_id", 3, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("module_id", 4, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("cmd", 5, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("type", 6, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("data", 7, descriptor_pb2.FieldDescriptorProto.TYPE_BYTES, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("client_id", 8, descriptor_pb2.FieldDescriptorProto.TYPE_STRING, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ComResponse",
            fields=(("code", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),),
        ),
        MessageSpec(
            name="CommonParam",
            fields=(
                ("hasAuto", 1, descriptor_pb2.FieldDescriptorProto.TYPE_BOOL, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("auto_mode", 2, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("id", 3, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("mode_index", 4, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("index", 5, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("continue_value", 6, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqMotorRun",
            fields=(
                ("id", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("speed", 2, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("direction", 3, descriptor_pb2.FieldDescriptorProto.TYPE_BOOL, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("speed_ramping", 4, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("resolution_level", 5, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqMotorRunTo",
            fields=(
                ("id", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("end_position", 2, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("speed", 3, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("speed_ramping", 4, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("resolution_level", 5, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqMotorStop",
            fields=(("id", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),),
        ),
        MessageSpec(
            name="ReqMotorServiceJoystick",
            fields=(
                ("vector_angle", 1, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("vector_length", 2, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("speed", 3, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqMotorServiceJoystickStop",
            fields=(),
        ),
        MessageSpec(
            name="ResMotor",
            fields=(
                ("id", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("code", 2, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqOpenCamera",
            fields=(
                ("binning", 1, descriptor_pb2.FieldDescriptorProto.TYPE_BOOL, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("rtsp_encode_type", 2, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
            MessageSpec(
                name="ReqGetSystemWorkingState",
                fields=(),
            ),
            MessageSpec(
                name="ReqSetFeatureParams",
                fields=(
                    (
                        "param",
                        1,
                        descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
                        descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
                        ".dwarf.CommonParam",
                    ),
                ),
            ),
            MessageSpec(
                name="ReqSetIrCut",
                fields=(
                    (
                        "value",
                        1,
                        descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
                        descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
                    ),
                ),
            ),
        MessageSpec(
            name="ReqCloseCamera",
            fields=(),
        ),
        MessageSpec(
            name="ResNotifyParam",
            fields=(
                (
                    "param",
                    1,
                    descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
                    descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
                    ".dwarf.CommonParam",
                ),
            ),
        ),
        MessageSpec(
            name="ResNotifyFocus",
            fields=(
                (
                    "focus",
                    1,
                    descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
                    descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
                ),
            ),
        ),
        MessageSpec(
            name="ResNotifyTemperature",
            fields=(
                (
                    "code",
                    1,
                    descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
                    descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
                ),
                (
                    "temperature",
                    2,
                    descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
                    descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
                ),
            ),
        ),
        MessageSpec(
            name="ReqPhoto",
            fields=(
                ("x", 1, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("y", 2, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("ratio", 3, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqPhotoRaw",
            fields=(),
        ),
        MessageSpec(
            name="ReqSetExpMode",
            fields=(
                ("mode", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqSetExp",
            fields=(
                ("index", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqSetGainMode",
            fields=(
                ("mode", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqSetGain",
            fields=(
                ("index", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqGotoDSO",
            fields=(
                ("ra", 1, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("dec", 2, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("target_name", 3, descriptor_pb2.FieldDescriptorProto.TYPE_STRING, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqGotoSolarSystem",
            fields=(
                ("index", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("lon", 2, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("lat", 3, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("target_name", 4, descriptor_pb2.FieldDescriptorProto.TYPE_STRING, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqStopGoto",
            fields=(),
        ),
        MessageSpec(
            name="ReqManualSingleStepFocus",
            fields=(("direction", 1, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),),
        ),
        MessageSpec(
            name="ReqManualContinuFocus",
            fields=(("direction", 1, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),),
        ),
        MessageSpec(
            name="ReqStopManualContinuFocus",
            fields=(),
        ),
        MessageSpec(
            name="ReqSetTime",
            fields=(
                (
                    "timestamp",
                    1,
                    descriptor_pb2.FieldDescriptorProto.TYPE_UINT64,
                    descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
                ),
                (
                    "timezone_offset",
                    2,
                    descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE,
                    descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
                ),
            ),
        ),
        MessageSpec(
            name="ReqSetTimezone",
            fields=(
                (
                    "timezone",
                    1,
                    descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
                    descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
                ),
            ),
        ),
        MessageSpec(
            name="ReqsetMasterLock",
            fields=(
                ("lock", 1, descriptor_pb2.FieldDescriptorProto.TYPE_BOOL, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ResNotifyHostSlaveMode",
            fields=(
                ("mode", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("lock", 2, descriptor_pb2.FieldDescriptorProto.TYPE_BOOL, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqTrackSpecialTarget",
            fields=(
                ("index", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("lon", 2, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("lat", 3, descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqStopTrackSpecialTarget",
            fields=(),
        ),
        MessageSpec(
            name="ReqCheckDarkFrame",
            fields=(),
        ),
        MessageSpec(
            name="ResCheckDarkFrame",
            fields=(
                ("progress", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("code", 2, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqCaptureDarkFrame",
            fields=(("reshoot", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),),
        ),
        MessageSpec(
            name="ReqStopCaptureDarkFrame",
            fields=(),
        ),
        MessageSpec(
            name="ReqCaptureDarkFrameWithParam",
            fields=(
                ("exp_index", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("gain_index", 2, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("bin_index", 3, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
                ("cap_size", 4, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
            ),
        ),
        MessageSpec(
            name="ReqStopCaptureDarkFrameWithParam",
            fields=(),
        ),
        MessageSpec(
            name="ReqAstroStartCaptureRawLiveStacking",
            fields=(),
        ),
        MessageSpec(
            name="ReqAstroStopCaptureRawLiveStacking",
            fields=(),
        ),
        MessageSpec(
            name="ReqGoLive",
            fields=(),
        ),
    )

    for spec in messages:
        msg_descriptor = file_descriptor.message_type.add()
        msg_descriptor.name = spec.name
        for field_spec in spec.fields:
            if len(field_spec) == 4:
                field_name, number, field_type, label = field_spec
                type_name: str | None = None
            else:
                field_name, number, field_type, label, type_name = field_spec
            field = msg_descriptor.field.add()
            field.name = field_name
            field.number = number
            field.type = field_type
            field.label = label
            if type_name:
                field.type_name = type_name

    pool.Add(file_descriptor)
    return pool


_POOL = _build_file_descriptor()
_FACTORY = message_factory.MessageFactory(_POOL)


def _prototype(name: str) -> Type[Message]:
    descriptor = _POOL.FindMessageTypeByName(f"dwarf.{name}")
    return _FACTORY.GetPrototype(descriptor)


WsPacket = _prototype("WsPacket")
ComResponse = _prototype("ComResponse")
CommonParam = _prototype("CommonParam")
ReqMotorRun = _prototype("ReqMotorRun")
ReqMotorRunTo = _prototype("ReqMotorRunTo")
ReqMotorStop = _prototype("ReqMotorStop")
ReqMotorServiceJoystick = _prototype("ReqMotorServiceJoystick")
ReqMotorServiceJoystickStop = _prototype("ReqMotorServiceJoystickStop")
ResMotor = _prototype("ResMotor")
ReqOpenCamera = _prototype("ReqOpenCamera")
ReqGetSystemWorkingState = _prototype("ReqGetSystemWorkingState")
ReqSetFeatureParams = _prototype("ReqSetFeatureParams")
ReqSetIrCut = _prototype("ReqSetIrCut")
ReqCloseCamera = _prototype("ReqCloseCamera")
ResNotifyParam = _prototype("ResNotifyParam")
ResNotifyFocus = _prototype("ResNotifyFocus")
ResNotifyTemperature = _prototype("ResNotifyTemperature")
ReqPhoto = _prototype("ReqPhoto")
ReqPhotoRaw = _prototype("ReqPhotoRaw")
ReqSetExpMode = _prototype("ReqSetExpMode")
ReqSetExp = _prototype("ReqSetExp")
ReqSetGainMode = _prototype("ReqSetGainMode")
ReqSetGain = _prototype("ReqSetGain")
ReqGotoDSO = _prototype("ReqGotoDSO")
ReqGotoSolarSystem = _prototype("ReqGotoSolarSystem")
ReqStopGoto = _prototype("ReqStopGoto")
ReqManualSingleStepFocus = _prototype("ReqManualSingleStepFocus")
ReqManualContinuFocus = _prototype("ReqManualContinuFocus")
ReqStopManualContinuFocus = _prototype("ReqStopManualContinuFocus")
ReqSetTime = _prototype("ReqSetTime")
ReqSetTimezone = _prototype("ReqSetTimezone")
ReqsetMasterLock = _prototype("ReqsetMasterLock")
ResNotifyHostSlaveMode = _prototype("ResNotifyHostSlaveMode")
ReqTrackSpecialTarget = _prototype("ReqTrackSpecialTarget")
ReqStopTrackSpecialTarget = _prototype("ReqStopTrackSpecialTarget")
ReqCheckDarkFrame = _prototype("ReqCheckDarkFrame")
ResCheckDarkFrame = _prototype("ResCheckDarkFrame")
ReqCaptureDarkFrame = _prototype("ReqCaptureDarkFrame")
ReqStopCaptureDarkFrame = _prototype("ReqStopCaptureDarkFrame")
ReqCaptureDarkFrameWithParam = _prototype("ReqCaptureDarkFrameWithParam")
ReqStopCaptureDarkFrameWithParam = _prototype("ReqStopCaptureDarkFrameWithParam")
ReqAstroStartCaptureRawLiveStacking = _prototype("ReqAstroStartCaptureRawLiveStacking")
ReqAstroStopCaptureRawLiveStacking = _prototype("ReqAstroStopCaptureRawLiveStacking")
ReqGoLive = _prototype("ReqGoLive")

MessageTypeId = _POOL.FindEnumTypeByName("dwarf.MessageTypeId")

TYPE_REQUEST = MessageTypeId.values_by_name["TYPE_REQUEST"].number
TYPE_REQUEST_RESPONSE = MessageTypeId.values_by_name["TYPE_REQUEST_RESPONSE"].number
TYPE_NOTIFICATION = MessageTypeId.values_by_name["TYPE_NOTIFICATION"].number
TYPE_NOTIFICATION_RESPONSE = MessageTypeId.values_by_name["TYPE_NOTIFICATION_RESPONSE"].number


def build_message(message_cls: Type[Message], initializer: Callable[[Message], None]) -> Message:
    message = message_cls()
    initializer(message)
    return message
