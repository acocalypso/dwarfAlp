# DWARFLAB APK 3.4.1 WebSocket code registry

Generated from the decompiled `WsCmd` and `WsRespCode` registries. Registration in the app does not prove model/firmware support.

## Commands (356)

| ID | Name | Direction | Request wrappers |
|---:|---|---|---|
| 10000 | `CMD_CAMERA_TELE_OPEN_CAMERA` | request | WsOpenCameraReq |
| 10001 | `CMD_CAMERA_TELE_CLOSE_CAMERA` | request | WsCloseCameraReq |
| 10002 | `CMD_CAMERA_TELE_PHOTOGRAPH` | request | WsPhotoReq |
| 10003 | `CMD_CAMERA_TELE_BURST` | request | WsStartBurstReq |
| 10004 | `CMD_CAMERA_TELE_STOP_BURST` | request | WsStopBurstReq |
| 10005 | `CMD_CAMERA_TELE_START_RECORD` | request | WsStartRecordReq |
| 10006 | `CMD_CAMERA_TELE_STOP_RECORD` | request | WsStopRecordReq |
| 10007 | `CMD_CAMERA_TELE_SET_EXP_MODE` | request | WsSetExpModeReq |
| 10008 | `CMD_CAMERA_TELE_GET_EXP_MODE` | request | — |
| 10009 | `CMD_CAMERA_TELE_SET_EXP` | request | WsSetExpReq |
| 10010 | `CMD_CAMERA_TELE_GET_EXP` | request | — |
| 10011 | `CMD_CAMERA_TELE_SET_GAIN_MODE` | request | WsSetGainModeReq |
| 10012 | `CMD_CAMERA_TELE_GET_GAIN_MODE` | request | — |
| 10013 | `CMD_CAMERA_TELE_SET_GAIN` | request | WsSetGainReq |
| 10014 | `CMD_CAMERA_TELE_GET_GAIN` | request | — |
| 10015 | `CMD_CAMERA_TELE_SET_BRIGHTNESS` | request | WsSetCamParamReq |
| 10016 | `CMD_CAMERA_TELE_GET_BRIGHTNESS` | request | — |
| 10017 | `CMD_CAMERA_TELE_SET_CONTRAST` | request | WsSetCamParamReq |
| 10018 | `CMD_CAMERA_TELE_GET_CONTRAST` | request | — |
| 10019 | `CMD_CAMERA_TELE_SET_SATURATION` | request | WsSetCamParamReq |
| 10020 | `CMD_CAMERA_TELE_GET_SATURATION` | request | — |
| 10021 | `CMD_CAMERA_TELE_SET_HUE` | request | WsSetCamParamReq |
| 10022 | `CMD_CAMERA_TELE_GET_HUE` | request | — |
| 10023 | `CMD_CAMERA_TELE_SET_SHARPNESS` | request | WsSetCamParamReq |
| 10024 | `CMD_CAMERA_TELE_GET_SHARPNESS` | request | — |
| 10025 | `CMD_CAMERA_TELE_SET_WB_MODE` | request | WsSetWBModeReq |
| 10026 | `CMD_CAMERA_TELE_GET_WB_MODE` | request | — |
| 10027 | `CMD_CAMERA_TELE_SET_WB_SCENE` | request | WsSetWBSceneReq |
| 10028 | `CMD_CAMERA_TELE_GET_WB_SCENE` | request | — |
| 10029 | `CMD_CAMERA_TELE_SET_WB_CT` | request | WsSetWBCTReq |
| 10030 | `CMD_CAMERA_TELE_GET_WB_CT` | request | — |
| 10031 | `CMD_CAMERA_TELE_SET_IRCUT` | request | WsSetIrCutReq |
| 10032 | `CMD_CAMERA_TELE_GET_IRCUT` | request | — |
| 10033 | `CMD_CAMERA_TELE_START_TIMELAPSE_PHOTO` | request | WsStartTLRecordReq |
| 10034 | `CMD_CAMERA_TELE_STOP_TIMELAPSE_PHOTO` | request | WsStopTLRecordReq |
| 10035 | `CMD_CAMERA_TELE_SET_ALL_PARAMS` | request | — |
| 10036 | `CMD_CAMERA_TELE_GET_ALL_PARAMS` | request | WsGetAllParamsReq |
| 10037 | `CMD_CAMERA_TELE_SET_FEATURE_PARAM` | request | WsSetFeatureReq |
| 10038 | `CMD_CAMERA_TELE_GET_ALL_FEATURE_PARAMS` | request | WsGetAllFeatureParamsReq |
| 10039 | `CMD_CAMERA_TELE_GET_SYSTEM_WORKING_STATE` | request | WsGetSystemWorkingStateReq |
| 10040 | `CMD_CAMERA_TELE_SET_JPG_QUALITY` | request | WsSetCamParamReq |
| 10041 | `CMD_CAMERA_TELE_PHOTO_RAW` | request | — |
| 10042 | `CMD_CAMERA_TELE_SET_RTSP_BITRATE_TYPE` | request | WsSetRtspBitrateReq |
| 10043 | `CMD_CAMERA_TELE_DISABLE_ALL_ISP_PROCESSING` | request | — |
| 10044 | `CMD_CAMERA_TELE_ENABLE_ALL_ISP_PROCESSING` | request | — |
| 10045 | `CMD_CAMERA_TELE_SET_ISP_MODULE_STATE` | request | — |
| 10046 | `CMD_CAMERA_TELE_GET_ISP_MODULE_STATE` | request | — |
| 10047 | `CMD_CAMERA_TELE_SWITCH_RESOLUTION` | request | WsSwitchResolutionReq |
| 10048 | `CMD_CAMERA_TELE_SWITCH_FRAMERATE` | request | WsSwitchFrameRateReq |
| 10049 | `CMD_CAMERA_TELE_SWITCH_CROP_RATIO` | request | WsSwitchCropRatio |
| 10050 | `CMD_CAMERA_TELE_SET_PREVIEW_QUALITY` | request | WsSetPreviewQualityReq |
| 10051 | `CMD_CAMERA_TELE_SET_ND_FILTER` | request | WsSetNdFilterReq |
| 11000 | `CMD_ASTRO_START_CALIBRATION` | request | WsStartCalibrationReq |
| 11001 | `CMD_ASTRO_STOP_CALIBRATION` | request | WsStopCalibrationReq |
| 11002 | `CMD_ASTRO_START_GOTO_DSO` | request | WsStartGoToDSOReq |
| 11003 | `CMD_ASTRO_START_GOTO_SOLAR_SYSTEM` | request | WsStartGoToSolarSystemReq; GotoSolarSystem (AstroProto.ResGotoSolarSystem) |
| 11004 | `CMD_ASTRO_STOP_GOTO` | request | WsReqStopGoTo, WsStopGoToReq |
| 11005 | `CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING` | request | WsStartCaptureRawLiveStackingReq |
| 11006 | `CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING` | request | WsStopCaptureRawLiveStackingReq |
| 11007 | `CMD_ASTRO_START_CAPTURE_RAW_DARK` | request | WsStartCaptureDarkFrameReq |
| 11008 | `CMD_ASTRO_STOP_CAPTURE_RAW_DARK` | request | WsStopCaptureDarkFrameReq |
| 11009 | `CMD_ASTRO_CHECK_GOT_DARK` | request | WsCheckDarkFrameReq |
| 11010 | `CMD_ASTRO_GO_LIVE` | request | WsGoLiveReq |
| 11011 | `CMD_ASTRO_START_TRACK_SPECIAL_TARGET` | request | WsSunOrMoonStartTrackReq |
| 11012 | `CMD_ASTRO_STOP_TRACK_SPECIAL_TARGET` | request | WsSunOrMoonStopTrackReq |
| 11013 | `CMD_ASTRO_START_ONE_CLICK_GOTO_DSO` | request | WsOneClickGotoDsoReq; OneClickGotoDso (AstroProto.ResOneClickGoto) |
| 11014 | `CMD_ASTRO_START_ONE_CLICK_GOTO_SOLAR_SYSTEM` | request | WsOneClickGotoSolarReq; OneClickGotoSolarSystem (AstroProto.ResOneClickGotoSolarSystem) |
| 11015 | `CMD_ASTRO_STOP_ONE_CLICK_GOTO` | request | WsStopAstroTrackingReq, WsStopOneClickGotoReq |
| 11016 | `CMD_ASTRO_START_WIDE_CAPTURE_LIVE_STACKING` | request | WsStartCaptureWideRawLiveStackingReq |
| 11017 | `CMD_ASTRO_STOP_WIDE_CAPTURE_LIVE_STACKING` | request | WsStopCaptureRawLiveStackingReq |
| 11018 | `CMD_ASTRO_START_EQ_SOLVING` | request | WsStartEQSolving |
| 11019 | `CMD_ASTRO_STOP_EQ_SOLVING` | request | WsStopEQSolving |
| 11020 | `CMD_ASTRO_WIDE_GO_LIVE` | request | WsGoLiveReq |
| 11021 | `CMD_ASTRO_START_CAPTURE_RAW_DARK_WITH_PARAM` | request | WsStartCaptureDarkFrameWithParamReq |
| 11022 | `CMD_ASTRO_STOP_CAPTURE_RAW_DARK_WITH_PARAM` | request | WsStopCaptureDarkFrameWithParamReq |
| 11023 | `CMD_ASTRO_GET_DARK_FRAME_LIST` | request | WsGetDarkFrameListReq |
| 11024 | `CMD_ASTRO_DEL_DARK_FRAME_LIST` | request | WsDelDarkFrameListReq |
| 11025 | `CMD_ASTRO_START_CAPTURE_WIDE_RAW_DARK_WITH_PARAM` | request | WsStartCaptureDarkFrameWithParamReq |
| 11026 | `CMD_ASTRO_STOP_CAPTURE_WIDE_RAW_DARK_WITH_PARAM` | request | WsStopCaptureDarkFrameWithParamReq |
| 11027 | `CMD_ASTRO_GET_WIDE_DARK_FRAME_LIST` | request | WsGetDarkFrameListReq |
| 11028 | `CMD_ASTRO_DEL_WIDE_DARK_FRAME_LIST` | request | WsDelDarkFrameListReq |
| 11029 | `CMD_ASTRO_START_AI_ENHANCE` | request | WsStartAIEnhanceReq |
| 11030 | `CMD_ASTRO_STOP_AI_ENHANCE` | request | WsStopAIEnhanceReq |
| 11031 | `CMD_ASTRO_START_TELE_MOSAIC` | request | WsStartMosaicReq |
| 11032 | `CMD_ASTRO_CHECK_IF_RESTACKABLE` | request | WsCheckMegaStackableReq |
| 11033 | `CMD_ASTRO_START_MAKE_FITS_THUMB` | request | WsStartMakeFitsThumbTaskReq |
| 11034 | `CMD_ASTRO_STOP_MAKE_FITS_THUMB` | request | WsStopMakeFitsThumbTaskReq |
| 11035 | `CMD_ASTRO_START_RESTACKED` | request | WsStartMegaStackTaskReq |
| 11036 | `CMD_ASTRO_STOP_RESTACKED` | request | WsStopMegaStackingTaskReq |
| 11037 | `CMD_ASTRO_FAST_STOP_CAPTURE_RAW_LIVE_STACKING` | request | WsFastStopCaptureRawLiveStackingReq |
| 11038 | `CMD_ASTRO_FAST_STOP_WIDE_CAPTURE_LIVE_STACKING` | request | WsFastStopCaptureRawLiveStackingReq |
| 11039 | `CMD_ASTRO_GET_ASTRO_SHOOTING_TIME` | request | WsGetAstroShootingTimeReq; RespGetShootingTime (AstroProto.ResGetAstroShootingTime) |
| 11040 | `CMD_ASTRO_GET_QUICK_SET_LIST` | request | WsGetQuickSetReq; RespGetQuickSetList (AstroProto.ResGetQuikSetList) |
| 11041 | `CMD_ASTRO_SET_QUICK_SET` | request | WsSetQuickSetReq; RespSetQuickSet (AstroProto.ResSetQuickSet) |
| 11042 | `CMD_ASTRO_START_ONE_CLICK_SHOOTING` | request | WsStartOneClickShooting |
| 11043 | `CMD_ASTRO_GET_CALI_FRAME_LIST` | request | WsMessageGetCaliFrameListReq |
| 11044 | `CMD_ASTRO_DEL_CALI_FRAME_LIST` | request | WsDelCaliFrameListReq |
| 11045 | `CMD_ASTRO_START_CAPTURE_CALI_FRAME` | request | WsStartCaptureCaliFrameReq |
| 11046 | `CMD_ASTRO_STOP_CAPTURE_CALI_FRAME` | request | WsStopCaptureCaliFrameReq |
| 11047 | `CMD_ASTRO_START_SKY_TARGET_FINDER` | request | WsReqStartSkyTargetFinder; StartSkyFinder (AstroProto.ResStartSkyTargetFinder) |
| 11048 | `CMD_ASTRO_STOP_SKY_TARGET_FINDER` | request | WsReqStopSkyTargetFinder |
| 11049 | `CMD_ASTRO_GET_GYRO_ATTITUDE` | request | — |
| 11050 | `CMD_ASTRO_CONTINUE_SHOOTING` | request | WsContinueShootingReq |
| 12001 | `CMD_CAMERA_WIDE_CLOSE_CAMERA` | request | WsCloseCameraReq |
| 12002 | `CMD_CAMERA_WIDE_SET_EXP_MODE` | request | WsSetExpModeReq |
| 12003 | `CMD_CAMERA_WIDE_GET_EXP_MODE` | request | — |
| 12004 | `CMD_CAMERA_WIDE_SET_EXP` | request | WsSetExpReq |
| 12008 | `CMD_CAMERA_WIDE_SET_BRIGHTNESS` | request | WsSetCamParamReq |
| 12009 | `CMD_CAMERA_WIDE_GET_BRIGHTNESS` | request | — |
| 12010 | `CMD_CAMERA_WIDE_SET_CONTRAST` | request | WsSetCamParamReq |
| 12011 | `CMD_CAMERA_WIDE_GET_CONTRAST` | request | — |
| 12012 | `CMD_CAMERA_WIDE_SET_SATURATION` | request | WsSetCamParamReq |
| 12014 | `CMD_CAMERA_WIDE_SET_HUE` | request | WsSetCamParamReq |
| 12015 | `CMD_CAMERA_WIDE_GET_HUE` | request | — |
| 12016 | `CMD_CAMERA_WIDE_SET_SHARPNESS` | request | WsSetCamParamReq |
| 12018 | `CMD_CAMERA_WIDE_SET_WB_MODE` | request | WsSetWBModeReq |
| 12020 | `CMD_CAMERA_WIDE_SET_WB_CT` | request | WsSetWBCTReq |
| 12021 | `CMD_CAMERA_WIDE_GET_WB_CT` | request | — |
| 12022 | `CMD_CAMERA_WIDE_PHOTOGRAPH` | request | WsPhotoReq |
| 12024 | `CMD_CAMERA_WIDE_STOP_BURST` | request | WsStopBurstReq |
| 12025 | `CMD_CAMERA_WIDE_START_TIMELAPSE_PHOTO` | request | WsStartTLRecordReq |
| 12029 | `CMD_CAMERA_WIDE_PHOTO_RAW` | request | — |
| 12030 | `CMD_CAMERA_WIDE_START_RECORD` | request | WsStartRecordReq |
| 12036 | `CMD_CAMERA_WIDE_SET_PREVIEW_QUALITY` | request | WsSetPreviewQualityReq |
| 13001 | `CMD_SYSTEM_SET_TIME_ZONE` | request | WsSetTimezoneReq |
| 13002 | `CMD_SYSTEM_SET_MTP_MODE` | request | WsSetMTPModeReq |
| 13003 | `CMD_SYSTEM_SET_CPU_MODE` | request | WsSetCPUModeReq |
| 13004 | `CMD_SYSTEM_SET_MASTER` | request | WsSetMasterLockModeReq |
| 13006 | `CMD_SYSTEM_DEVICE_ACTIVATE_WRITE_FILE` | request | — |
| 13007 | `CMD_SYSTEM_DEVICE_ACTIVATE_NOTIFY_ACTIVATE_SUCCESSFULL` | request | — |
| 13008 | `CMD_SYSTEM_FACTORY_TEST_UN_ACTIVATE` | request | — |
| 13010 | `CMD_SYSTEM_SET_LOCATION` | request | WsReqSetLocation |
| 13500 | `CMD_RGB_POWER_OPEN_RGB` | request | WsOpenRgbReq |
| 13501 | `CMD_RGB_POWER_CLOSE_RGB` | request | WsCloseRgbReq |
| 13502 | `CMD_RGB_POWER_POWER_DOWN` | request | WsShutdownReq |
| 13503 | `CMD_RGB_POWER_POWERIND_ON` | request | WsOpenPowerIndicatorReq |
| 13504 | `CMD_RGB_POWER_POWERIND_OFF` | request | WsClosePowerIndicatorReq |
| 14000 | `CMD_STEP_MOTOR_RUN` | request | — |
| 14002 | `CMD_STEP_MOTOR_STOP` | request | — |
| 14006 | `CMD_STEP_MOTOR_SERVICE_JOYSTICK` | request | WsMotorServiceJoystickReq |
| 14007 | `CMD_STEP_MOTOR_SERVICE_JOYSTICK_FIXED_ANGLE` | request | WsMotorServiceJoystickFixedAngleReq |
| 14008 | `CMD_STEP_MOTOR_SERVICE_JOYSTICK_STOP` | request | WsMotorServiceJoystickStopReq |
| 14009 | `CMD_STEP_MOTOR_SERVICE_DUAL_CAMERA_LINKAGE` | request | WsDualCameraLinkageReq |
| 14010 | `CMD_STEP_MOTOR_RUN_IN_PULSE` | request | — |
| 14011 | `CMD_STEP_MOTOR_GET_POSITION` | request | — |
| 14012 | `CMD_STEP_MOTOR_START_ATTITUDE_NOTIFY` | request | — |
| 14013 | `CMD_STEP_MOTOR_STOP_ATTITUDE_NOTIFY` | request | — |
| 14014 | `CMD_STEP_MOTOR_LEVEL_CALIBRATION_MOVE` | request | WsLevelCalibrationMoveReq |
| 14015 | `CMD_STEP_MOTOR_SAVE_LEVEL_CALIBRATION_OFFSET` | request | WsLevelCalibrationSaveReq |
| 14016 | `CMD_STEP_MOTOR_RESET_LEVEL_CALIBRATION_DEFAULT` | request | WsLevelCalibrationResetReq |
| 14800 | `CMD_TRACK_START_TRACK` | request | WsStartTargetTrackReq |
| 14801 | `CMD_TRACK_STOP_TRACK` | request | WsStopTargetTrackReq |
| 14802 | `CMD_SENTRY_MODE_START` | request | WsStartSentryModeReq |
| 14804 | `CMD_MOT_START` | request | — |
| 14805 | `CMD_MOT_TRACK_ONE` | request | WsStartMOTTrackOneReq |
| 14806 | `CMD_UFOTRACK_MODE_START` | request | — |
| 14807 | `CMD_UFOTRACK_MODE_STOP` | request | — |
| 14808 | `CMD_MOT_WIDE_TRACK_ONE` | request | WsStartMOTTrackOneReq |
| 14809 | `CMD_SWITCH_MAIN_PREVIEW` | request | — |
| 14810 | `CMD_UFO_HAND_AOTO_MODE` | request | WsUFOAutoManualModeReq |
| 14812 | `CMD_TRACK_START_CLICK` | request | WsStartTargetTrackClickReq |
| 15000 | `CMD_FOCUS_AUTO_FOCUS` | request | WsNormalAutoFocusReq |
| 15001 | `CMD_FOCUS_MANUAL_SINGLE_STEP_FOCUS` | request | WsManualSingleStepFocusReq |
| 15002 | `CMD_FOCUS_START_MANUAL_CONTINU_FOCUS` | request | WsManualContinuousFocusReq |
| 15003 | `CMD_FOCUS_STOP_MANUAL_CONTINU_FOCUS` | request | WsStopManualContinuousFocusReq |
| 15004 | `CMD_FOCUS_START_ASTRO_AUTO_FOCUS` | request | WsAstroAutoFocusReq |
| 15005 | `CMD_FOCUS_STOP_ASTRO_AUTO_FOCUS` | request | WsStopAstroAutoFocusReq |
| 15015 | `CMD_WIDE_FOCUS_MANUAL_SINGLE_STEP_FOCUS` | request | WsManualSingleStepFocusReq |
| 15016 | `CMD_WIDE_FOCUS_START_MANUAL_CONTINU_FOCUS` | request | WsManualContinuousFocusReq |
| 15018 | `CMD_WIDE_FOCUS_START_ASTRO_AUTO_FOCUS` | request | WsAstroAutoFocusReq |
| 15019 | `CMD_WIDE_FOCUS_STOP_ASTRO_AUTO_FOCUS` | request | WsStopAstroAutoFocusReq |
| 15020 | `CMD_WIDE_FOCUS_AUTO_INFINITY_FOCUS` | request | — |
| 15027 | `CMD_GUIDE_FOCUS_SET_USER_INFINITY_POS` | request | WsSetUserInfinityPosReq |
| 15028 | `CMD_GUIDE_FOCUS_GET_USER_INFINITY_POS` | request | WsGetUserInfinityPosReq |
| 15029 | `CMD_GUIDE_FOCUS_MANUAL_SINGLE_STEP_FOCUS` | request | WsManualSingleStepFocusReq |
| 15030 | `CMD_GUIDE_FOCUS_START_MANUAL_CONTINU_FOCUS` | request | WsManualContinuousFocusReq |
| 15031 | `CMD_GUIDE_FOCUS_STOP_MANUAL_CONTINU_FOCUS` | request | WsStopManualContinuousFocusReq |
| 15501 | `CMD_PANORAMA_STOP` | request | WsStopPanoramaReq |
| 15505 | `CMD_PANORAMA_GET_CURRENT_UPLOAD_STATE` | request | WsGetPanoramaCurrentUploadStateReq |
| 15506 | `CMD_PANORAMA_GET_UPLOAD_PREDICT` | request | WsGetUploadPredictReq |
| 15507 | `CMD_PANORAMA_START_COMPRESS` | request | WsReqPanoramaStartCompress; PanoramaStartCompress (BaseProto.ComResponse) |
| 15508 | `CMD_PANORAMA_STOP_COMPRESS` | request | WsReqPanoramaStopCompress; PanoramaStopCompress (BaseProto.ComResponse) |
| 15509 | `CMD_PANORAMA_START_FRAMING` | request | — |
| 15510 | `CMD_PANORAMA_STOP_FRAMING` | request | — |
| 15511 | `CMD_PANORAMA_RESET_FRAMING` | request | — |
| 15512 | `CMD_PANORAMA_UPDATE_FRAMING_RECT` | request | ReqPanoramaUpdateFraming |
| 15513 | `CMD_PANORAMA_STOP_FRAMEING_AND_START_GRID` | request | — |
| 15011 | `CMD_FOCUS_GET_USER_INFINITY_POS` | request | WsGetUserInfinityPosReq |
| 15012 | `CMD_FOCUS_SET_USER_INFINITY_POS` | request | WsSetUserInfinityPosReq |
| 15200 | `CMD_NOTIFY_TELE_WIDE_PICTURE_MATCHING` | notification | NotifyPictureMatching (NotifyProto.PictureMatching) |
| 15201 | `CMD_NOTIFY_ELE` | notification | NotifyEle (NotifyProto.BatteryInfo) |
| 15202 | `CMD_NOTIFY_CHARGE` | notification | NotifyCharge (NotifyProto.ChargingState) |
| 15203 | `CMD_NOTIFY_SDCARD_INFO` | notification | NotifyStorageInfo (NotifyProto.StorageInfo) |
| 15204 | `CMD_NOTIFY_TELE_RECORD_TIME` | notification | — |
| 15205 | `CMD_NOTIFY_TELE_TIMELAPSE_OUT_TIME` | notification | — |
| 15206 | `CMD_NOTIFY_STATE_CAPTURE_RAW_DARK` | notification | — |
| 15207 | `CMD_NOTIFY_PROGRASS_CAPTURE_RAW_DARK` | notification | — |
| 15208 | `CMD_NOTIFY_STATE_CAPTURE_RAW_LIVE_STACKING` | notification | NotifyCaptureRawLivingState (NotifyProto.CaptureRawState) |
| 15209 | `CMD_NOTIFY_PROGRASS_CAPTURE_RAW_LIVE_STACKING` | notification | NotifyProgressCaptureRaw (NotifyProto.ProgressCaptureRawLiveStacking) |
| 15210 | `CMD_NOTIFY_STATE_ASTRO_CALIBRATION` | notification | NotifyAstroCalibration (NotifyProto.AstroCalibrationState) |
| 15211 | `CMD_NOTIFY_STATE_ASTRO_GOTO` | notification | NotifyAstroGoto (NotifyProto.AstroGotoState) |
| 15212 | `CMD_NOTIFY_STATE_ASTRO_TRACKING` | notification | NotifyAstroTracking (NotifyProto.AstroTrackingState) |
| 15213 | `CMD_NOTIFY_TELE_SET_PARAM` | notification | — |
| 15214 | `CMD_NOTIFY_WIDE_SET_PARAM` | notification | — |
| 15215 | `CMD_NOTIFY_TELE_FUNCTION_STATE` | notification | — |
| 15216 | `CMD_NOTIFY_WIDE_FUNCTION_STATE` | notification | — |
| 15217 | `CMD_NOTIFY_SET_FEATURE_PARAM` | notification | — |
| 15218 | `CMD_NOTIFY_TELE_BURST_PROGRESS` | notification | — |
| 15219 | `CMD_NOTIFY_PANORAMA_PROGRESS` | notification | NotifyPanoramaProgress (NotifyProto.PanoramaProgress) |
| 15220 | `CMD_NOTIFY_WIDE_BURST_PROGRESS` | notification | — |
| 15222 | `CMD_NOTIFY_POWER_IND_STATE` | notification | NotifyPowerIndState (NotifyProto.PowerIndState) |
| 15223 | `CMD_NOTIFY_WS_HOST_SLAVE_MODE` | notification | NotifyHostSlaveMode (NotifyProto.HostSlaveMode) |
| 15224 | `CMD_NOTIFY_MTP_STATE` | notification | NotifyMTPState (NotifyProto.MTPState) |
| 15226 | `CMD_NOTIFY_WIDE_TIMELAPSE_OUT_TIME` | notification | — |
| 15227 | `CMD_NOTIFY_CPU_MODE` | notification | NotifyCPUMode (NotifyProto.CPUMode) |
| 15228 | `CMD_NOTIFY_STATE_ASTRO_TRACKING_SPECIAL` | notification | NotifyAstroTrackingSpecial (NotifyProto.AstroTrackingSpecialState) |
| 15229 | `CMD_NOTIFY_POWER_OFF` | notification | — |
| 15230 | `CMD_NOTIFY_ALBUM_UPDATE` | notification | — |
| 15232 | `CMD_NOTIFY_SENTRY_MODE_TRACK_RESULT` | notification | — |
| 15233 | `CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO` | notification | NotifyOneClickGotoState (NotifyProto.OneClickGotoState) |
| 15234 | `CMD_NOTIFY_STREAM_TYPE` | notification | NotifyStreamType (NotifyProto.StreamType) |
| 15235 | `CMD_NOTIFY_WIDE_RECORD_TIME` | notification | — |
| 15236 | `CMD_NOTIFY_STATE_WIDE_CAPTURE_RAW_LIVE_STACKING` | notification | — |
| 15237 | `CMD_NOTIFY_PROGRASS_WIDE_CAPTURE_RAW_LIVE_STACKING` | notification | — |
| 15238 | `CMD_NOTIFY_MULTI_TRACK_RESULT` | notification | — |
| 15239 | `CMD_NOTIFY_EQ_SOLVING_STATE` | notification | NotifyEqSolvingState (NotifyProto.EqSolvingState) |
| 15244 | `CMD_NOTIFY_PANORAMA_UPLOAD_COMPRESS_PROGRESS` | notification | — |
| 15245 | `CMD_NOTIFY_PANORAMA_UPLOAD_COMPLETE` | notification | — |
| 15247 | `CMD_NOTIFY_STATE_CAPTURE_WIDE_RAW_DARK` | notification | — |
| 15248 | `CMD_NOTIFY_SHOOTING_SCHEDULE_RESULT_AND_STATE` | notification | — |
| 15249 | `CMD_NOTIFY_SHOOTING_TASK_STATE` | notification | — |
| 15250 | `CMD_NOTIFY_SKY_SEACHER_STATE` | notification | NotifySkySeacherState (NotifyProto.SkySeacherState) |
| 15252 | `CMD_NOTIFY_WIDE_TRACK_RESULT` | notification | — |
| 15253 | `CMD_NOTIFY_STATE_AI_ENHANCE` | notification | — |
| 15254 | `CMD_NOTIFY_PROGRESS_AI_ENHANCE` | notification | — |
| 15255 | `CMD_NOTIFY_WAIT_SHOOTING_PROGRESS` | notification | — |
| 15256 | `CMD_NOTIFY_CALIBRATION_RESULT` | notification | NotifyCalibrationResult (NotifyProto.CalibrationResult) |
| 15257 | `CMD_NOTIFY_FOCUS_POSITION` | notification | NotifyFocusPosition (NotifyProto.FocusPosition) |
| 15258 | `CMD_NOTIFY_UFO_AUTO_HAND_MODE` | notification | NotifySentryAutoHandMode (NotifyProto.SentryAutoHand) |
| 15259 | `CMD_NOTIFY_CURRENT_PANORAMA_UPLOAD_STATE` | notification | — |
| 15260 | `CMD_NOTIFY_LOW_TEMP_PROTECTION_MODE` | notification | — |
| 15261 | `CMD_NOTIFY_EXCLUSIVE_SYSTEM_IO_TASK_STATE` | notification | NotifyTaskState (TaskCenterProto.ResNotifyTaskState) |
| 15262 | `CMD_NOTIFY_BODY_STATUS` | notification | NotifyBodyState (NotifyProto.BodyStatus) |
| 15263 | `CMD_NOTIFY_PROGRESS_CAPTURE_MOSAIC` | notification | NotifyProgressCaptureMosaic (NotifyProto.ProgressCaptureMosaic) |
| 15264 | `CMD_NOTIFY_GENERAL_INT_PARAM` | notification | WsUpdateGeneralIntParamReq |
| 15265 | `CMD_NOTIFY_GENERAL_FLOAT_PARAM` | notification | — |
| 15266 | `CMD_NOTIFY_GENERAL_BOOL_PARAM` | notification | WsSetBooleanParamWsMessageReq |
| 15267 | `CMD_NOTIFY_SWITCH_SHOOTING_MODE` | notification | — |
| 15268 | `CMD_NOTIFY_TELE_SWITCH_CROP_RATIO` | notification | — |
| 15269 | `CMD_NOTIFY_TELE_SHOOTING_TECH_STATE` | notification | — |
| 15270 | `CMD_NOTIFY_WB` | notification | — |
| 15271 | `CMD_NOTIFY_WIDE_SHOOTING_TECH_STATE` | notification | — |
| 15272 | `CMD_NOTIFY_RESOLUTION_PARAM` | notification | — |
| 15273 | `CMD_NOTIFY_PHOTO_STATE` | notification | NotifyPhotoState (NotifyProto.PhotoState) |
| 15274 | `CMD_NOTIFY_BURST_STATE` | notification | NotifyBurstState (NotifyProto.BurstState) |
| 15275 | `CMD_NOTIFY_RECORD_STATE` | notification | NotifyRecordState (NotifyProto.RecordState) |
| 15276 | `CMD_NOTIFY_TIMELAPSE_STATE` | notification | NotifyTimeLapseState (NotifyProto.TimeLapseState) |
| 15277 | `CMD_NOTIFY_PANORAMA_STATE` | notification | NotifyPanoramaState (NotifyProto.PanoramaState) |
| 15278 | `CMD_NOTIFY_ASTRO_AUTO_FOCUS_STATE` | notification | NotifyAstroAutoFocusState (NotifyProto.AstroAutoFocusState) |
| 15279 | `CMD_NOTIFY_NORMAL_AUTO_FOCUS_STATE` | notification | NotifyNormalAutoFocusState (NotifyProto.NormalAutoFocusState) |
| 15280 | `CMD_NOTIFY_ASTRO_AUTO_FOCUS_FAST_STATE` | notification | NotifyAstroAutoFocusFastState (NotifyProto.AstroAutoFocusFastState) |
| 15281 | `CMD_NOTIFY_AREA_AUTO_FOCUS_STATE` | notification | NotifyAreaAutoFocusState (NotifyProto.AreaAutoFocusState) |
| 15282 | `CMD_NOTIFY_DUAL_CAMERA_LINKAGE_STATE` | notification | NotifyDualCameraLinkageState (NotifyProto.DualCameraLinkageState) |
| 15283 | `CMD_NOTIFY_RESOLUTION_FPS_STATE` | notification | — |
| 15284 | `CMD_NOTIFY_NORMAL_TRACK_STATE` | notification | NotifyNormalTrackState (NotifyProto.NormalTrackState) |
| 15285 | `CMD_NOTIFY_BURST_PROGRESS` | notification | NotifyBurstProgress (NotifyProto.BurstProgress) |
| 15286 | `CMD_NOTIFY_RECORD_TIME` | notification | NotifyRecordTime (NotifyProto.RecordTime) |
| 15287 | `CMD_NOTIFY_TIMELAPSE_OUT_TIME` | notification | NotifyTimeLapseOutTime (NotifyProto.TimeLapseOutTime) |
| 15288 | `CMD_NOTIFY_LONG_EXP_PROGRESS` | notification | NotifyLongExpPhotoProgress (NotifyProto.LongExpPhotoProgress) |
| 15289 | `CMD_NOTIFY_SENTRY_MOTOR_STATE` | notification | NotifySentryMotorState (NotifyProto.SentryState) |
| 15290 | `CMD_NOTIFY_STATE_CAPTURE_CALI_FRAME` | notification | NotifyCaptureCaliFrameState (NotifyProto.CaptureCaliFrameState) |
| 15291 | `CMD_NOTIFY_PROGRESS_CAPTURE_CALI_FRAME` | notification | NotifyCaptureCaliFrameProgress (NotifyProto.CaptureCaliFrameProgress) |
| 15292 | `CMD_NOTIFY_CMOS_TEMPERATURE` | notification | NotifyCmosTemperature (NotifyProto.CmosTemperature) |
| 15293 | `CMD_NOTIFY_PANORAMA_COMPRESS_PROGRESS` | notification | PanoramaCompressProgress (NotifyProto.PanoramaCompressionProgress) |
| 15294 | `CMD_NOTIFY_PANORAMA_COMPRESS_COMPLETE` | notification | PanoramaCompressComplete (NotifyProto.PanoramaCompressionComplete) |
| 15296 | `CMD_NOTIFY_SKY_TARGET_FINDER_STATE` | notification | NotifySkyTargetFinderState (NotifyProto.SkyTargetFinderState) |
| 15295 | `CMD_NOTIFY_DEVICE_ATTITUDE` | notification | NotifyDeviceAttitude (NotifyProto.DeviceAttitude) |
| 15300 | `CMD_NOTIFY_WIDE_FOCUS_POSITION` | notification | NotifyWideFocusPosition (NotifyProto.FocusPosition) |
| 15301 | `CMD_NOTIFY_LENS_DEFOG_STATE` | notification | NotifyLensDefogState (NotifyProto.LensDefog) |
| 15302 | `CMD_NOTIFY_AUTO_COOLING_STATE` | notification | NotifyAutoCoolingState (NotifyProto.AutoCooling) |
| 15303 | `CMD_NOTIFY_AUTO_SHUTDOWN_STATE` | notification | NotifyAutoShutdownState (NotifyProto.AutoShutdown) |
| 15304 | `CMD_NOTIFY_ROLL_LEVEL_CALIBRATION_ANGLE` | notification | NotifyRollLevelCalibrationAngle (NotifyProto.RollLevelCalibrationAngle) |
| 15305 | `CMD_NOTIFY_GUIDE_FOCUS_POSITION` | notification | NotifyGuideFocusPosition (NotifyProto.FocusPosition) |
| 15700 | `CMD_ITIPS_GET` | request | WsITipsGetReq |
| 16100 | `CMD_SYNC_SHOOTING_SCHEDULE` | request | WsSyncShootingScheduleReq |
| 16101 | `CMD_CANCEL_SHOOTING_SCHEDULE` | request | WsCancelShootingScheduleReq |
| 16102 | `CMD_GET_ALL_SHOOTING_SCHEDULE` | request | WsGetAllShootingScheduleReq |
| 16103 | `CMD_GET_SHOOTING_SCHEDULE_BY_ID` | request | WsGetShootingScheduleReq |
| 16105 | `CMD_REPLACE_SHOOTING_SCHEDULE` | request | WsReplaceShootingScheduleReq |
| 16106 | `CMD_UNLOCK_SHOOTING_SCHEDULE` | request | WsUnlockShootingScheduleReq |
| 16107 | `CMD_LOCK_SHOOTING_SCHEDULE` | request | WsLockShootingScheduleReq |
| 16108 | `CMD_DELETE_SHOOTING_SCHEDULE` | request | WsDeleteShootingScheduleReq |
| 16400 | `CMD_GLOBAL_TASK_MANAGER_START_TASK` | request | — |
| 16401 | `CMD_GLOBAL_TASK_MANAGER_STOP_TASK` | request | — |
| 16402 | `CMD_GLOBAL_TASK_MANAGER_SWITCH_SHOOTING_MODE` | request | WsReqSwitchShootingMode, WsSwitchShootingMode; SwitchShootingMode (TaskCenterProto.ResSwitchShootingMode) |
| 16403 | `CMD_GLOBAL_TASK_MANAGER_SWITCH_SHOOTING_TECH` | request | WsReqSwitchShootingTech, WsSwitchShootingTech |
| 16404 | `CMD_GLOBAL_TASK_MANAGER_ENTER_CAMERA` | request | WsEnterCamReq; EnterCamera (TaskCenterProto.ResEnterCamera) |
| 16405 | `CMD_GLOBAL_TASK_GET_DEVICE_STATE_INFO` | request | WsGetDeviceStateInfo; GetDeviceStateInfo (TaskCenterProto.ResGetDeviceStateInfo) |
| 16406 | `CMD_GLOBAL_VOICE_ASSISTANT_TASK` | request | — |
| 16800 | `CMD_VOICE_ASSISTANT_TASK` | request | WsVoiceAssistantReq |
| 16700 | `CMD_PARAM_SET_EXPOSURE` | request | WsSetExposureParamReq |
| 16701 | `CMD_PARAM_SET_GAIN` | request | WsSetGainParamReq |
| 16702 | `CMD_PARAM_SET_WB` | request | WsSetWBParamReq |
| 16703 | `CMD_PARAM_SET_GENERAL_INT_PARAM` | request | WsSetEnumParamReq, WsSetGeneralIntParamReq, WsUpdateGeneralIntParamReq |
| 16704 | `CMD_PARAM_SET_GENERAL_FLOAT_PARAM` | request | — |
| 16705 | `CMD_PARAM_SET_GENERAL_BOOL_PARAM` | request | WsSetBooleanParamWsMessageReq, WsSetGeneralBooleanParamReq |
| 16706 | `CMD_PARAM_SET_AUTO_PARAMS` | request | WsSetAutoSetParamsReq |
| 16900 | `CMD_CAMERA_GUIDE_SET_EXP` | request | WsSetExpReq |
| 16901 | `CMD_CAMERA_GUIDE_GET_EXP` | request | — |
| 16902 | `CMD_CAMERA_GUIDE_SET_GAIN` | request | WsSetGainReq |
| 16903 | `CMD_CAMERA_GUIDE_GET_GAIN` | request | — |
| 17000 | `CMD_DEVICE_LENS_DEFOG` | request | WsSetLensDefogReq |
| 17001 | `CMD_DEVICE_AUTO_COOLING` | request | WsSetAutoCoolingReq |
| 17002 | `CMD_DEVICE_AUTO_SHUTDOWN` | request | WsSetAutoShutdownReq |
| 12023 | `CMD_CAMERA_WIDE_BURST` | request | WsStartBurstReq |
| 12027 | `CMD_CAMERA_WIDE_GET_ALL_PARAMS` | request | WsGetAllParamsReq |
| 12005 | `CMD_CAMERA_WIDE_GET_EXP` | request | — |
| 12007 | `CMD_CAMERA_WIDE_GET_GAIN` | request | — |
| 12013 | `CMD_CAMERA_WIDE_GET_SATURATION` | request | — |
| 12017 | `CMD_CAMERA_WIDE_GET_SHARPNESS` | request | — |
| 12019 | `CMD_CAMERA_WIDE_GET_WB_MODE` | request | — |
| 12000 | `CMD_CAMERA_WIDE_OPEN_CAMERA` | request | WsOpenCameraReq |
| 12028 | `CMD_CAMERA_WIDE_SET_ALL_PARAMS` | request | — |
| 12006 | `CMD_CAMERA_WIDE_SET_GAIN` | request | WsSetGainReq |
| 12038 | `CMD_CAMERA_WIDE_SET_ND_FILTER` | request | WsSetNdFilterReq |
| 12032 | `CMD_CAMERA_WIDE_SET_RTSP_BITRATE_TYPE` | request | WsSetRtspBitrateReq |
| 12035 | `CMD_CAMERA_WIDE_SET_WB_SCENE` | request | WsSetWBSceneReq |
| 12031 | `CMD_CAMERA_WIDE_STOP_RECORD` | request | WsStopRecordReq |
| 12026 | `CMD_CAMERA_WIDE_STOP_TIMELAPSE_PHOTO` | request | WsStopTLRecordReq |
| 15006 | `CMD_FOCUS_AUTO_INFINITY_FOCUS` | request | — |
| 15033 | `CMD_GUIDE_FOCUS_AUTO_INFINITY_FOCUS` | request | — |
| 15032 | `CMD_GUIDE_FOCUS_START_ASTRO_AUTO_FOCUS` | request | WsAstroAutoFocusReq |
| 15034 | `CMD_GUIDE_FOCUS_STOP_ASTRO_AUTO_FOCUS` | request | WsStopAstroAutoFocusReq |
| 15245 | `CMD_NOTIFY_PANORAMA_UPLOAD_UPLOAD_PROGRESS` | notification | — |
| 15297 | `CMD_NOTIFY_PANO_FRAMING_RECT_UPDATE` | notification | NotifyPanoFramingRectUpdate (NotifyProto.PanoFramingRectUpdateNotify) |
| 15299 | `CMD_NOTIFY_PANO_FRAMING_STATE` | notification | NotifyPanoFramingState (NotifyProto.PanoFramingStateNotify) |
| 15298 | `CMD_NOTIFY_PANO_FRAMING_THUMBNAIL_UPDATE` | notification | NotifyPanoFramingThumbnailUpdate (NotifyProto.PanoFramingThumbnailUpdateNotify) |
| 15221 | `CMD_NOTIFY_RGB_STATE` | notification | NotifyRgbState (NotifyProto.ChargingState) |
| 15231 | `CMD_NOTIFY_SENTRY_MODE_STATE` | notification | NotifySentryState (NotifyProto.SentryState) |
| 15241 | `CMD_NOTIFY_TELE_LONG_EXP_PROGRESS` | notification | — |
| 15243 | `CMD_NOTIFY_TEMPERATURE` | notification | NotifyTemperature (NotifyProto.Temperature) |
| 15225 | `CMD_NOTIFY_TRACK_RESULT` | notification | — |
| 15240 | `CMD_NOTIFY_UFO_MODE_STATE` | notification | — |
| 15242 | `CMD_NOTIFY_WIDE_LONG_EXP_PROGRESS` | notification | — |
| 15251 | `CMD_NOTIFY_WIDE_MULTI_TRACK_RESULT` | notification | — |
| 15500 | `CMD_PANORAMA_START_GRID` | request | WsStartPanoramaGridReq |
| 15503 | `CMD_PANORAMA_START_STITCH_UPLOAD` | request | WsStartPanoramaStitchUploadReq |
| 15504 | `CMD_PANORAMA_STOP_STITCH_UPLOAD` | request | WsStopPanoramaStitchUploadReq |
| 13505 | `CMD_RGB_POWER_REBOOT` | request | WsRestartReq |
| 14803 | `CMD_SENTRY_MODE_STOP` | request | WsStopSentryModeReq |
| 14811 | `CMD_SENTRY_SCENE_SELECT` | request | — |
| 13005 | `CMD_SYSTEM_GET_DEVICE_ACTIVATE_INFO` | request | — |
| 13009 | `CMD_SYSTEM_SET_LOW_TEMP_PROTECTION_MODE` | request | — |
| 13000 | `CMD_SYSTEM_SET_TIME` | request | WsSetTimeReq |
| 15014 | `CMD_WIDE_FOCUS_AUTO_FOCUS` | request | WsNormalAutoFocusReq |
| 15017 | `CMD_WIDE_FOCUS_STOP_MANUAL_CONTINU_FOCUS` | request | WsStopManualContinuousFocusReq |

## Response and error codes (123)

| Code | Name |
|---:|---|
| 0 | `WS_OK` |
| -1 | `WS_PARSE_PROTOBUF_ERROR` |
| -2 | `WS_SDCARD_NOT_EXIST` |
| -3 | `WS_INVAID_PARAM` |
| -4 | `WS_SDCARD_WRITE_ERROR` |
| -5 | `WS_DEVICE_NOT_ACTIVATED` |
| -6 | `WS_SDCARD_FULL_ERROR` |
| -10500 | `CODE_CAMERA_TELE_OPENED` |
| -10501 | `CODE_CAMERA_TELE_CLOSED` |
| -10502 | `CODE_CAMERA_TELE_ISP_SET_FAILED` |
| -10503 | `CODE_CAMERA_TELE_OPEN_FAILED` |
| -10504 | `CODE_CAMERA_TELE_START_RECORD_FAILED` |
| -10505 | `CODE_CAMERA_TELE_STOP_RECORD_FAILED` |
| -10506 | `CODE_CAMERA_TELE_CAPTURE_RAW_FAILED` |
| -10507 | `CODE_CAMERA_TELE_WORKING_BUSY` |
| -10508 | `CODE_CAMERA_TELE_GET_IMAGE_FAILED` |
| -10509 | `CODE_CAMERA_TELE_RUNNING_PHOTO` |
| -10510 | `CODE_CAMERA_TELE_RUNNING_RECORD` |
| -10511 | `CODE_CAMERA_TELE_RUNNING_PANORAMA` |
| -10512 | `CODE_CAMERA_TELE_RUNNING_TIMELAPSE` |
| -10513 | `CODE_CAMERA_TELE_RUNNING_CAPTURE_DARK` |
| -10514 | `CODE_CAMERA_TELE_RUNNING_CAPTURE_LIVE_STACKING` |
| -10515 | `CODE_CAMERA_TELE_EXP_TOO_LONG` |
| -10516 | `CODE_CAMERA_TELE_SWITCH_WORK_MODE_FAILED` |
| -10517 | `CODE_CAMERA_TELE_RUNNING_TRACK` |
| -10518 | `CODE_CAMERA_TELE_RECORD_FILE_ERROR` |
| -11500 | `CODE_ASTRO_PLATE_SOLVING_FAILED` |
| -11501 | `CODE_ASTRO_FUNCTION_BUSY` |
| -11502 | `CODE_ASTRO_DARK_GAIN_OUT_OF_RANGE` |
| -11503 | `CODE_ASTRO_DARK_NOT_FOUND` |
| -11504 | `CODE_ASTRO_CALIBRATION_FAILED` |
| -11505 | `CODE_ASTRO_GOTO_FAILED` |
| -11506 | `CODE_ASTRO_DARK_RUNNING` |
| -11507 | `CODE_ASTRO_CALIBRATION_RUNNING` |
| -11508 | `CODE_ASTRO_GOTO_RUNNING` |
| -11509 | `CODE_ASTRO_LIVE_STACKING_RUNNING` |
| -11510 | `CODE_ASTRO_RESET_PITCH_MOTOR_FAILED` |
| -11511 | `CODE_ASTRO_NEED_CALIBRATION` |
| -11512 | `CODE_ASTRO_GOTO_READ_MOTOR_POSITION_AND_PLATE_SOLVING_FAILED` |
| -11513 | `CODE_ASTRO_NEED_GOTO` |
| -11514 | `CODE_ASTRO_NEED_ADJUST_SHOOT_PARAM` |
| -11515 | `CODE_ASTRO_CALIBRATION_PLATE_SOLVING_FAILED_TOO_MUCH` |
| -11516 | `CODE_ASTRO_EQ_SOLVING_FAILED` |
| -11517 | `CODE_ASTRO_SKY_SEARCH_FAILED` |
| -11518 | `CODE_ASTRO_NEED_GOTO_DSO` |
| -11519 | `CODE_ASTRO_RESTACK_CAMERA_MISMATCH` |
| -11520 | `CODE_ASTRO_RESTACK_BINNING_MISMATCH` |
| -11521 | `CODE_ASTRO_RESTACK_FILTER_MISMATCH` |
| -11522 | `CODE_ASTRO_RESTACK_TARGET_MISMATCH` |
| -11523 | `CODE_ASTRO_RESTACK_DARKFRAME_MISMATCH` |
| -11524 | `CODE_ASTRO_RESTACK_FAILED` |
| -11525 | `CODE_ASTRO_RESTACK_INVALID_DATA` |
| -11526 | `CODE_ASTRO_OVEREXPOSURE_WARNING` |
| -11527 | `CODE_ASTRO_EXP_TOO_LONG` |
| -11528 | `CODE_ASTRO_NEED_EQ` |
| -11529 | `CODE_ASTRO_STAR_TOO_FEW` |
| -11530 | `CODE_ASTRO_DARK_TEMP_MISMATCH` |
| -11531 | `CODE_ASTRO_SUN_MOON_NOT_FOUND` |
| -11532 | `CODE_ASTRO_GUIDING_FAILED_LOWER_EXPOSURE` |
| -11533 | `CODE_ASTRO_GUIDING_FAILED_TARGET_BLOCKED` |
| -12500 | `CODE_CAMERA_WIDE_OPENED` |
| -12501 | `CODE_CAMERA_WIDE_CLOSED` |
| -12502 | `CODE_CAMERA_WIDE_CANNOT_FOUND` |
| -12503 | `CODE_CAMERA_WIDE_OPEN_FAILED` |
| -12504 | `CODE_CAMERA_WIDE_CLOSE_FAILED` |
| -12505 | `CODE_CAMERA_WIDE_SET_ISP_FAILED` |
| -12506 | `CODE_CAMERA_WIDE_PHOTOGRAPHING` |
| -12507 | `CODE_CAMERA_WIDE_TIMELAPSE_RECORDING` |
| -12508 | `CODE_CAMERA_WIDE_EXP_TOO_LONG` |
| -12509 | `CODE_CAMERA_WIDE_RECORD_FILE_ERROR` |
| -13300 | `CODE_SYSTEM_SET_TIME_FAILED` |
| -13301 | `CODE_SYSTEM_SET_TIMEZONE_FAILED` |
| -13800 | `CODE_RGB_POWER_UART_INIT_FAILED` |
| -13801 | `CODE_RGB_POWER_UART_SEND_FAILED` |
| -14500 | `CODE_STEP_MOTOR_IS_RUNNING` |
| -14501 | `CODE_STEP_MOTOR_IS_STOPPED` |
| -14502 | `CODE_STEP_MOTOR_PARALLEL_IN` |
| -14503 | `CODE_STEP_MOTOR_PARALLEL_END` |
| -14504 | `CODE_STEP_MOTOR_INVALID_PARAMETER_ID` |
| -14505 | `CODE_STEP_MOTOR_INVALID_PARAMETER_ANGLE` |
| -14506 | `CODE_STEP_MOTOR_INVALID_PARAMETER_SPEED` |
| -14507 | `CODE_STEP_MOTOR_INVALID_PARAMETER_SPEED_RAMPING` |
| -14508 | `CODE_STEP_MOTOR_INVALID_PARAMETER_RESOLUTION` |
| -14509 | `CODE_STEP_MOTOR_INVALID_PARAMETER_POSITION` |
| -14510 | `CODE_STEP_MOTOR_OVERTIME_GET_LIMIT_RETURN` |
| -14511 | `CODE_STEP_MOTOR_OVERTIME_GET_RESET_RETURN` |
| -14512 | `CODE_STEP_MOTOR_OVERTIME_GET_ABSOLUTE_POSITION_RETURN` |
| -14513 | `CODE_STEP_MOTOR_OVERTIME_GET_RELATIVE_POSITION_RETURN` |
| -14514 | `CODE_STEP_MOTOR_OVERTIME_WAIT_TO_STOP` |
| -14515 | `CODE_STEP_MOTOR_OVERTIME_WAIT_TO_RUN` |
| -14516 | `CODE_STEP_MOTOR_LIMIT_SPEED_TO_MAX` |
| -14517 | `CODE_STEP_MOTOR_LIMIT_SPEED_TO_MIN` |
| -14518 | `CODE_STEP_MOTOR_LIMIT_POSITION_WARNING` |
| -14519 | `CODE_STEP_MOTOR_LIMIT_POSITION_HIT` |
| -14520 | `CODE_STEP_MOTOR_NEED_RESET` |
| -14521 | `CODE_STEP_MOTOR_OVERTIME_GET_PE_SWITCH_RETURN` |
| -14522 | `CODE_STEP_MOTOR_OVERTIME_TO_RESET` |
| -14523 | `CODE_STEP_MOTOR_ROLL_LIMIT_ANGLE_WARNING` |
| -14900 | `CODE_TRACK_TRACKER_INITING` |
| -14901 | `CODE_TRACK_TRACKER_FAILED` |
| -14902 | `CODE_TRACK_SENTRY_MODE_INITING` |
| -14903 | `CODE_TRACK_SENTRY_MODE_FAILED` |
| -14904 | `CODE_UFOTRACK_MODE_INITING` |
| -14906 | `CODE_UFO_DAY_AUTO_MODE` |
| -15100 | `CODE_FOCUS_ASTRO_AUTO_FOCUS_SLOW_ERROR` |
| -15101 | `CODE_FOCUS_ASTRO_AUTO_FOCUS_FAST_ERROR` |
| -15106 | `CODE_FOCUS_EXP_TOO_LONG` |
| -15601 | `CODE_PANORAMA_MOTOR_RESET_FAILED` |
| -15602 | `CODE_PANORAMA_UPLOAD_USER_STOP` |
| -15603 | `CODE_PANORAMA_UPLOAD_FILE_CHECK_FAILED` |
| -15604 | `CODE_PANORAMA_UPLOAD_COMPRESS_FAILED` |
| -15605 | `CODE_PANORAMA_UPLOAD_UPLOAD_FAILED` |
| -15607 | `CODE_PANORAMA_UPLOAD_IS_RUNNING` |
| -15608 | `CODE_PANORAMA_UPLOAD_CAMERA_BUSY` |
| -15609 | `CODE_PANORAMA_UPLOAD_NOT_IN_STA` |
| -15615 | `CODE_PANORAMA_COMPOSE_IS_RUNNING` |
| -16300 | `CODE_SHOOTING_SCHEDULE_DEVICE_ID_NOT_MATCH` |
| -16301 | `CODE_SHOOTING_SCHEDULE_INVALID_SHOOTING_DURATION` |
| -16302 | `CODE_SHOOTING_SCHEDULE_TIME_CONFLICT` |
| -16305 | `CODE_SHOOTING_SCHEDULE_DATABASE_OPERATION_FAILED` |
| -16306 | `CODE_SHOOTING_SCHEDULE_PASSWORD_ERROR` |
| -16310 | `CODE_SHOOTING_SCHEDULE_INTERRUPTED` |
| -16311 | `CODE_SHOOTING_SCHEDULE_NOT_SYNCED` |

## HTTP operations (50)

Device-local and DWARFLAB cloud interfaces are separated by scope. Cloud registration is documentation only and is not part of local telescope control.

| Scope | Method | Path | Operation | Body model |
|---|---|---|---|---|
| device | `POST` | `album/astro/fitsList` | `astroFits` | AstroFitsRequest |
| device | `DELETE` | `album/astro/deleteFits` | `deleteFits` | DeleteFitsRequest |
| device | `POST` | `album/delete` | `deleteMedias` | RequestBody |
| device | `POST` | `deviceActivateStatusNotify` | `deviceActivateStatusNotify` | RequestBody |
| device | `POST` | `deviceActivateWriteFile` | `deviceActivateWriteFile` | RequestBody |
| device | `POST` | `deviceInfo` | `deviceInfo` | — |
| device | `GET` | `<dynamic-url>` | `downloadFile` | — |
| device | `GET` | `downloadLog` | `downloadLogFile` | — |
| device | `GET` | `getDefaultParamsConfig` | `getDefaultParamsConfig` | — |
| device | `GET` | `getDefaultParamsConfig` | `getDefaultParamsConfigRx` | — |
| device | `POST` | `getDeviceActivateInfo` | `getDeviceActivateInfo` | RequestBody |
| device | `GET` | `logInfo` | `getLogInfo` | — |
| device | `POST` | `album/getMediaInfoByFilePath` | `getMediaInfoByFilePath` | StackingReq |
| device | `POST` | `album/list/mediaInfos` | `getMediaInfos` | RequestBody |
| device | `POST` | `shootingMode/getParamAndSetting` | `getParamAndSetting` | GetParamAndSettingRequest |
| device | `POST` | `getResetState` | `getResetState` | — |
| device | `GET` | `shootingMode/getSupportedShootingModes` | `getShootingMode` | — |
| device | `POST` | `album/list/mediaCounts` | `mediaCounts` | — |
| device | `POST` | `album/list/mediaInfos` | `mediaInfos` | MediaInfoRequest |
| device | `POST` | `resetDeviceInfo` | `resetDeviceInfo` | — |
| device | `POST` | `setDeviceNameAndPsd` | `setDeviceNameAndPsd` | RequestBody |
| device | `GET` | `update` | `updateFirmware` | — |
| device | `POST` | `uploadFirmware` | `uploadFirmware` | — |
| device | `POST` | `uploadFirmwareDiff` | `uploadFirmwareDiff` | — |
| cloud | `POST` | `/api-front/v1/user/userinfo` | `a` | — |
| cloud | `POST` | `/api-front/v1/user/deactivate` | `b` | — |
| cloud | `GET` | `/api-front/v1/system/server-info` | `c` | — |
| cloud | `POST` | `/api-front/v1/user/avatar` | `d` | — |
| cloud | `GET` | `/api-front/v1/sn/status` | `e` | — |
| cloud | `GET` | `/api-front/v1/version/app/up-version` | `f` | — |
| cloud | `GET` | `/api-front/v1/sn/status` | `g` | — |
| cloud | `GET` | `/api-front/v1/user/userinfo` | `h` | — |
| cloud | `POST` | `/api-front/v1/stitch-process/export` | `i` | — |
| cloud | `POST` | `/api-front/v1/auth/refresh-token` | `j` | — |
| cloud | `POST` | `/api-front/v1/user/subscribe-email` | `k` | — |
| cloud | `POST` | `/api-front/v1/user/userinfo` | `l` | — |
| cloud | `GET` | `<dynamic-url>` | `m` | — |
| cloud | `GET` | `/api-front/v1/gpt/watermark-text` | `n` | — |
| cloud | `POST` | `/api-front/v1/sn/activate/code` | `o` | ServerRequest |
| cloud | `POST` | `/api-front/v1/stitch-process/adjust-color-params` | `p` | — |
| cloud | `POST` | `/api-front/v1/auth/password` | `q` | — |
| cloud | `POST` | `/api-front/v1/auth/register` | `r` | — |
| cloud | `POST` | `/api-front/v1/sn/activate/notify` | `s` | ServerRequest |
| cloud | `GET` | `/api-front/v1/version/star/up-version` | `t` | — |
| cloud | `GET` | `/api-front/v1/stitch-process/detail/{processId}` | `u` | — |
| cloud | `GET` | `/api-front/v1/version/app/up-version` | `v` | — |
| cloud | `POST` | `/api-front/v1/user/bind-identifier` | `w` | — |
| cloud | `GET` | `/api-front/v1/version/firmware/up-version-ex` | `x` | — |
| cloud-log-analysis | `GET` | `v1/ai/analysis/tasks` | `a` | — |
| cloud-log-analysis | `GET` | `v1/ai/analysis/tasks/{taskId}` | `b` | — |

## BLE provisioning commands (8)

| ID | Request | Response |
|---:|---|---|
| 1 | `ReqGetconfig` | `ResGetconfig` |
| 2 | `ReqAp` | `ResAp` |
| 3 | `ReqSta` | `ResSta` |
| 4 | `ReqSetblewifi` | `ResSetblewifi` |
| 5 | `ReqReset` | `ResReset` |
| 6 | `ReqGetwifilist` | `ResWifilist` |
| 7 | `ReqGetsysteminfo` | `ResGetsysteminfo` |
| 8 | `ReqCheckFile` | `ResCheckFile` |

## Registered BLE UUIDs (8)

- `0000180A-0000-1000-8000-00805F9B34FB`
- `0000DAF2-0000-1000-8000-00805F9B34FB`
- `0000DAF3-0000-1000-8000-00805F9B34FB`
- `0000DAF4-0000-1000-8000-00805F9B34FB`
- `0000DAF5-0000-1000-8000-00805F9B34FB`
- `0000DAF6-0000-1000-8000-00805F9B34FB`
- `000DAF07-0000-1000-8000-00805F9B34FB`
- `00009999-0000-1000-8000-00805F9B34FB`
