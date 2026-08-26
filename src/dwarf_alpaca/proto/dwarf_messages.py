"""Compatibility exports backed exclusively by generated canonical protobufs.

New code should import the owning ``*_pb2`` module directly. Historical V3
names remain aliases so downstream imports do not break, but they now serialize
the descriptor-verified firmware message rather than a second hand-built schema.
"""

# Re-exporting imported generated classes is the purpose of this compatibility module.
# ruff: noqa: F401

from __future__ import annotations

from typing import Callable, Type

from google.protobuf.message import Message

from .astro_pb2 import (
    ReqCaptureDarkFrame,
    ReqCaptureDarkFrameWithParam,
    ReqCaptureRawLiveStacking,
    ReqCheckDarkFrame,
    ReqGoLive,
    ReqGotoDSO,
    ReqGotoSolarSystem,
    ReqStopCaptureDarkFrame,
    ReqStopCaptureDarkFrameWithParam,
    ReqStopCaptureRawLiveStacking,
    ReqStopGoto,
    ReqStopTrackSpecialTarget,
    ReqTrackSpecialTarget,
    ResCheckDarkFrame,
)
from .base_pb2 import CommonParam, ComResponse, WsPacket
from .camera_pb2 import (
    ReqCloseCamera,
    ReqGetAllFeatureParams,
    ReqGetSystemWorkingState,
    ReqOpenCamera,
    ReqPhoto,
    ReqPhotoRaw,
    ReqSetExp,
    ReqSetExpMode,
    ReqSetFeatureParams,
    ReqSetGain,
    ReqSetGainMode,
    ReqSetIrCut,
    ReqSetPreviewQuality,
    ResGetAllFeatureParams,
)
from .focus_pb2 import (
    ReqGetUserInfinityPos,
    ReqManualContinuFocus,
    ReqManualSingleStepFocus,
    ReqStopManualContinuFocus,
    ResUserInfinityPos,
)
from .motor_control_pb2 import (
    ReqMotorRun,
    ReqMotorRunTo,
    ReqMotorServiceJoystick,
    ReqMotorServiceJoystickStop,
    ReqMotorStop,
    ResMotor,
)
from .notify_pb2 import (
    AstroGotoState,
    AstroTrackingState,
    CmosTemperature,
    FocusPosition,
    GeneralIntParam,
    HostSlaveMode,
    Param,
    SkyTargetFinderState,
    SwitchShootingMode,
    Temperature,
)
from .param_pb2 import ReqSetExposure, ReqSetGeneralIntParam
from .protocol_pb2 import MessageTypeId
from .system_pb2 import ReqsetMasterLock, ReqSetTime, ReqSetTimezone
from .task_center_pb2 import (
    ReqEnterCamera,
    ReqGetDeviceStateInfo,
    ReqSwitchShootingMode,
    ReqSwitchShootingTech,
    ResEnterCamera,
    ResGetDeviceStateInfo,
    ResNotifyTaskState,
    ResSwitchShootingMode,
    ResSwitchShootingTech,
)
from .v3_notify_pb2 import V3ResNotifyExposureProgress

TYPE_REQUEST = 0
TYPE_REQUEST_RESPONSE = 1
TYPE_NOTIFICATION = 2
TYPE_NOTIFICATION_RESPONSE = 3

# Stable legacy notification names.
ResNotifyParam = Param
ResNotifyFocus = FocusPosition
ResNotifyTemperature = Temperature
ResNotifyStateAstroGoto = AstroGotoState
ResNotifyStateAstroTracking = AstroTrackingState
ResNotifyHostSlaveMode = HostSlaveMode

# Stable legacy astronomy wrapper names.
ReqAstroStartCaptureRawLiveStacking = ReqCaptureRawLiveStacking
ReqAstroStopCaptureRawLiveStacking = ReqStopCaptureRawLiveStacking

# Deprecated provisional V3 names mapped to descriptor-exact classes.
V3ReqOpenTeleCamera = ReqSetPreviewQuality
V3ReqOpenWideCamera = ReqSetPreviewQuality
V3ReqSetCameraParam = ReqSetExposure
V3ReqSetExposureGain = ReqSetExposure
V3ReqAdjustParam = ReqSetGeneralIntParam
V3ReqModeQuery = ReqSwitchShootingMode
V3ResModeQuery = ResSwitchShootingMode
V3ReqShootingModeSwitch = ReqSwitchShootingTech
V3ResShootingModeSwitch = ResSwitchShootingTech
V3ReqModeSwitch = ReqEnterCamera
V3ResModeSwitch = ResEnterCamera
V3ReqGetDeviceConfig = ReqGetDeviceStateInfo
V3ResGetDeviceConfig = ResGetDeviceStateInfo
V3ResNotifyCameraParamState = GeneralIntParam
V3ResNotifyDeviceState = ResNotifyTaskState
V3ResNotifyModeChange = SwitchShootingMode
V3ResNotifyTemperature2 = CmosTemperature
V3ResNotifyObservationState = SkyTargetFinderState
V3ReqFocusInit = ReqGetUserInfinityPos
V3ResFocusInit = ResUserInfinityPos


def build_message(message_cls: Type[Message], initializer: Callable[[Message], None]) -> Message:
    message = message_cls()
    initializer(message)
    return message
