from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import numpy as np


class BayerPattern(StrEnum):
    NONE = "none"
    RGGB = "RGGB"
    BGGR = "BGGR"
    GRBG = "GRBG"
    GBRG = "GBRG"


class ControlName(StrEnum):
    EXPOSURE = "exposure"
    GAIN = "gain"
    OFFSET = "offset"
    GAMMA = "gamma"
    WB_RED = "wb_red"
    WB_BLUE = "wb_blue"
    USB_BANDWIDTH = "usb_bandwidth"
    HIGH_SPEED = "high_speed"
    TARGET_TEMP = "target_temp"
    COOLER_ON = "cooler_on"


@dataclass(frozen=True, slots=True)
class ControlRange:
    name: str
    min_value: float
    max_value: float
    default: float
    unit: str = ""
    writable: bool = True
    auto_supported: bool = False

    def clamp(self, value: float) -> float:
        return min(max(float(value), self.min_value), self.max_value)


@dataclass(frozen=True, slots=True)
class CameraInfo:
    name: str
    camera_id: str
    max_width: int
    max_height: int
    bit_depth: int
    is_color: bool
    bayer_pattern: BayerPattern
    pixel_size_um: float
    has_cooler: bool
    supported_bins: tuple[int, ...]
    backend: str


@dataclass(frozen=True, slots=True)
class Roi:
    x: int
    y: int
    width: int
    height: int
    bin: int = 1

    @property
    def output_width(self) -> int:
        return self.width // self.bin

    @property
    def output_height(self) -> int:
        return self.height // self.bin


@dataclass(frozen=True, slots=True)
class FrameMetadata:
    timestamp_utc: datetime
    exposure_s: float
    gain: float
    offset: float
    sensor_temp_c: float
    bayer_pattern: BayerPattern
    bin: int
    roi: Roi
    sequence: int
    camera_name: str
    bit_depth: int
    is_dark: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Frame:
    data: np.ndarray
    metadata: FrameMetadata
