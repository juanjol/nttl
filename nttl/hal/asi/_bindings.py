from __future__ import annotations

import ctypes
import os
import sys
from ctypes.util import find_library
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from nttl.hal.errors import CameraError, SdkNotAvailableError

ENV_VARS = ("NTTL_ASI_SDK", "ASI_SDK_LIB", "ZWO_ASI_LIB")

_LINUX_CANDIDATES = (
    "/usr/lib/libASICamera2.so",
    "/usr/local/lib/libASICamera2.so",
    "/usr/lib/x86_64-linux-gnu/libASICamera2.so",
    "/usr/lib/aarch64-linux-gnu/libASICamera2.so",
    "/opt/zwo/lib/libASICamera2.so",
)
_WINDOWS_CANDIDATES = (
    r"C:\Program Files\ASIStudio\ASICamera2.dll",
    r"C:\Program Files (x86)\ASIStudio\ASICamera2.dll",
    r"C:\Program Files\Common Files\ASCOM\Camera\ASICamera2.dll",
    r"C:\Windows\System32\ASICamera2.dll",
)


class ControlType(IntEnum):
    GAIN = 0
    EXPOSURE = 1
    GAMMA = 2
    WB_R = 3
    WB_B = 4
    OFFSET = 5
    BANDWIDTHOVERLOAD = 6
    OVERCLOCK = 7
    TEMPERATURE = 8
    FLIP = 9
    AUTO_MAX_GAIN = 10
    AUTO_MAX_EXP = 11
    AUTO_TARGET_BRIGHTNESS = 12
    HARDWARE_BIN = 13
    HIGH_SPEED_MODE = 14
    COOLER_POWER_PERC = 15
    TARGET_TEMP = 16
    COOLER_ON = 17
    MONO_BIN = 18
    FAN_ON = 19
    PATTERN_ADJUST = 20
    ANTI_DEW_HEATER = 21


class ImageType(IntEnum):
    RAW8 = 0
    RGB24 = 1
    RAW16 = 2
    Y8 = 3


class ExposureStatus(IntEnum):
    IDLE = 0
    WORKING = 1
    SUCCESS = 2
    FAILED = 3


ERRORS = {
    1: "invalid index",
    2: "invalid camera id",
    3: "invalid control type",
    4: "camera closed",
    5: "camera removed",
    6: "invalid path",
    7: "invalid file format",
    8: "invalid frame size",
    9: "invalid image type",
    10: "outside of the sensor",
    11: "timeout",
    12: "invalid sequence",
    13: "buffer too small",
    14: "video mode active",
    15: "exposure in progress",
    16: "general error",
    17: "mode not supported",
}


class AsiError(CameraError):
    def __init__(self, function: str, code: int) -> None:
        super().__init__(f"{function} failed: {ERRORS.get(code, f'error {code}')} ({code})")
        self.code = code


class _CameraInfoStruct(ctypes.Structure):
    _fields_ = [
        ("Name", ctypes.c_char * 64),
        ("CameraID", ctypes.c_int),
        ("MaxHeight", ctypes.c_long),
        ("MaxWidth", ctypes.c_long),
        ("IsColorCam", ctypes.c_int),
        ("BayerPattern", ctypes.c_int),
        ("SupportedBins", ctypes.c_int * 16),
        ("SupportedVideoFormat", ctypes.c_int * 8),
        ("PixelSize", ctypes.c_double),
        ("MechanicalShutter", ctypes.c_int),
        ("ST4Port", ctypes.c_int),
        ("IsCoolerCam", ctypes.c_int),
        ("IsUSB3Host", ctypes.c_int),
        ("IsUSB3Camera", ctypes.c_int),
        ("ElecPerADU", ctypes.c_float),
        ("BitDepth", ctypes.c_int),
        ("IsTriggerCam", ctypes.c_int),
        ("Unused", ctypes.c_char * 16),
    ]


class _ControlCapsStruct(ctypes.Structure):
    _fields_ = [
        ("Name", ctypes.c_char * 64),
        ("Description", ctypes.c_char * 128),
        ("MaxValue", ctypes.c_long),
        ("MinValue", ctypes.c_long),
        ("DefaultValue", ctypes.c_long),
        ("IsAutoSupported", ctypes.c_int),
        ("IsWritable", ctypes.c_int),
        ("ControlType", ctypes.c_int),
        ("Unused", ctypes.c_char * 32),
    ]


@dataclass(frozen=True, slots=True)
class AsiCameraInfo:
    name: str
    camera_id: int
    max_width: int
    max_height: int
    is_color: bool
    bayer_pattern: int
    supported_bins: tuple[int, ...]
    pixel_size_um: float
    has_cooler: bool
    bit_depth: int


@dataclass(frozen=True, slots=True)
class AsiControlCaps:
    name: str
    description: str
    min_value: int
    max_value: int
    default: int
    auto_supported: bool
    writable: bool
    control_type: int


def find_sdk(explicit: str | Path | None = None) -> Path | None:
    candidates: list[str] = []
    if explicit:
        candidates.append(str(explicit))
    candidates.extend(os.environ[name] for name in ENV_VARS if os.environ.get(name))
    located = find_library("ASICamera2")
    if located:
        candidates.append(located)
    candidates.extend(_WINDOWS_CANDIDATES if sys.platform.startswith("win") else _LINUX_CANDIDATES)
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return None


class AsiSdk:
    """Thin pythonic wrapper over libASICamera2."""

    def __init__(self, library_path: Path | str | None = None) -> None:
        path = find_sdk(library_path)
        if path is None:
            raise SdkNotAvailableError(
                "the ZWO ASI SDK was not found. Install the vendor driver package or set "
                f"one of {', '.join(ENV_VARS)} to the full path of the library"
            )
        self.path = path
        try:
            self._lib = ctypes.CDLL(str(path))
        except OSError as exc:
            raise SdkNotAvailableError(f"could not load {path}: {exc}") from exc
        self._declare()

    def _declare(self) -> None:
        lib = self._lib
        lib.ASIGetNumOfConnectedCameras.restype = ctypes.c_int
        lib.ASIGetCameraProperty.argtypes = [ctypes.POINTER(_CameraInfoStruct), ctypes.c_int]
        lib.ASIGetControlCaps.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_ControlCapsStruct),
        ]
        lib.ASIGetControlValue.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_long),
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.ASISetControlValue.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_long,
            ctypes.c_int,
        ]
        lib.ASIGetDataAfterExp.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_long]

    def _check(self, name: str, code: int) -> None:
        if code != 0:
            raise AsiError(name, code)

    # discovery

    def camera_count(self) -> int:
        return int(self._lib.ASIGetNumOfConnectedCameras())

    def camera_info(self, index: int) -> AsiCameraInfo:
        struct = _CameraInfoStruct()
        self._check("ASIGetCameraProperty", self._lib.ASIGetCameraProperty(struct, index))
        bins = tuple(value for value in struct.SupportedBins if value > 0)
        return AsiCameraInfo(
            name=struct.Name.decode(errors="replace").strip(),
            camera_id=int(struct.CameraID),
            max_width=int(struct.MaxWidth),
            max_height=int(struct.MaxHeight),
            is_color=bool(struct.IsColorCam),
            bayer_pattern=int(struct.BayerPattern),
            supported_bins=bins or (1,),
            pixel_size_um=float(struct.PixelSize),
            has_cooler=bool(struct.IsCoolerCam),
            bit_depth=int(struct.BitDepth) or 16,
        )

    # lifecycle

    def open(self, camera_id: int) -> None:
        self._check("ASIOpenCamera", self._lib.ASIOpenCamera(camera_id))
        self._check("ASIInitCamera", self._lib.ASIInitCamera(camera_id))

    def close(self, camera_id: int) -> None:
        self._check("ASICloseCamera", self._lib.ASICloseCamera(camera_id))

    # controls

    def controls(self, camera_id: int) -> list[AsiControlCaps]:
        count = ctypes.c_int()
        self._check(
            "ASIGetNumOfControls", self._lib.ASIGetNumOfControls(camera_id, ctypes.byref(count))
        )
        caps = []
        for index in range(count.value):
            struct = _ControlCapsStruct()
            self._check("ASIGetControlCaps", self._lib.ASIGetControlCaps(camera_id, index, struct))
            caps.append(
                AsiControlCaps(
                    name=struct.Name.decode(errors="replace").strip(),
                    description=struct.Description.decode(errors="replace").strip(),
                    min_value=int(struct.MinValue),
                    max_value=int(struct.MaxValue),
                    default=int(struct.DefaultValue),
                    auto_supported=bool(struct.IsAutoSupported),
                    writable=bool(struct.IsWritable),
                    control_type=int(struct.ControlType),
                )
            )
        return caps

    def get_control(self, camera_id: int, control_type: int) -> tuple[int, bool]:
        value = ctypes.c_long()
        auto = ctypes.c_int()
        self._check(
            "ASIGetControlValue",
            self._lib.ASIGetControlValue(
                camera_id, control_type, ctypes.byref(value), ctypes.byref(auto)
            ),
        )
        return int(value.value), bool(auto.value)

    def set_control(
        self, camera_id: int, control_type: int, value: int, *, auto: bool = False
    ) -> None:
        self._check(
            "ASISetControlValue",
            self._lib.ASISetControlValue(camera_id, control_type, int(value), 1 if auto else 0),
        )

    # frame geometry

    def set_roi_format(
        self, camera_id: int, width: int, height: int, binning: int, image_type: int
    ) -> None:
        self._check(
            "ASISetROIFormat",
            self._lib.ASISetROIFormat(camera_id, width, height, binning, image_type),
        )

    def set_start_position(self, camera_id: int, x: int, y: int) -> None:
        self._check("ASISetStartPos", self._lib.ASISetStartPos(camera_id, x, y))

    # exposure

    def start_exposure(self, camera_id: int, *, dark: bool = False) -> None:
        self._check("ASIStartExposure", self._lib.ASIStartExposure(camera_id, 1 if dark else 0))

    def stop_exposure(self, camera_id: int) -> None:
        self._check("ASIStopExposure", self._lib.ASIStopExposure(camera_id))

    def exposure_status(self, camera_id: int) -> ExposureStatus:
        status = ctypes.c_int()
        self._check("ASIGetExpStatus", self._lib.ASIGetExpStatus(camera_id, ctypes.byref(status)))
        return ExposureStatus(status.value)

    def read_data(self, camera_id: int, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        self._check("ASIGetDataAfterExp", self._lib.ASIGetDataAfterExp(camera_id, buffer, size))
        return buffer.raw[:size]
