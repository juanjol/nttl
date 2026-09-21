"""In process stand in for libASICamera2, backed by the simulated camera."""

from __future__ import annotations

from nttl.hal.asi._bindings import (
    AsiCameraInfo,
    AsiControlCaps,
    AsiError,
    ControlType,
    ExposureStatus,
    ImageType,
)
from nttl.hal.simulated import SimulatedCamera
from nttl.hal.types import BayerPattern, ControlName, Roi

_CAPS = [
    AsiControlCaps(
        "Exposure", "us", 32, 3_600_000_000, 1_000_000, True, True, ControlType.EXPOSURE
    ),
    AsiControlCaps("Gain", "", 0, 500, 120, True, True, ControlType.GAIN),
    AsiControlCaps("Offset", "", 0, 600, 50, False, True, ControlType.OFFSET),
    AsiControlCaps("Gamma", "", 1, 100, 50, False, True, ControlType.GAMMA),
    AsiControlCaps("WB_R", "", 1, 99, 52, True, True, ControlType.WB_R),
    AsiControlCaps("WB_B", "", 1, 99, 95, True, True, ControlType.WB_B),
    AsiControlCaps("Temperature", "0.1C", -500, 1000, 0, False, False, ControlType.TEMPERATURE),
    AsiControlCaps("TargetTemp", "C", -40, 30, 0, False, True, ControlType.TARGET_TEMP),
    AsiControlCaps("CoolerOn", "", 0, 1, 0, False, True, ControlType.COOLER_ON),
]

_BAYER_CODES = {
    BayerPattern.RGGB: 0,
    BayerPattern.BGGR: 1,
    BayerPattern.GRBG: 2,
    BayerPattern.GBRG: 3,
}


class FakeAsiSdk:
    def __init__(
        self,
        *,
        width: int = 64,
        height: int = 64,
        is_color: bool = True,
        has_cooler: bool = True,
        cameras: int = 1,
        fail_exposure: bool = False,
        formats: tuple[int, ...] = (ImageType.RAW8, ImageType.RAW16),
    ) -> None:
        self._formats = formats
        self._sim = SimulatedCamera(
            seed=17,
            width=width,
            height=height,
            is_color=is_color,
            has_cooler=has_cooler,
            star_count=20,
        )
        self._sim.open()
        self._cameras = cameras
        self._opened: set[int] = set()
        self._exposure_us = 1_000_000
        self._pending: bytes | None = None
        self._status = ExposureStatus.IDLE
        self._fail_exposure = fail_exposure
        self._start_x = 0
        self._start_y = 0
        self._bin = 1
        self._image_type = ImageType.RAW16
        self._width = width
        self._height = height
        self.calls: list[str] = []

    # discovery

    def camera_count(self) -> int:
        return self._cameras

    def camera_info(self, index: int) -> AsiCameraInfo:
        if index >= self._cameras:
            raise AsiError("ASIGetCameraProperty", 1)
        info = self._sim.info
        return AsiCameraInfo(
            name=f"ASI{294 + index}MC Pro",
            camera_id=index,
            max_width=info.max_width,
            max_height=info.max_height,
            is_color=info.is_color,
            bayer_pattern=_BAYER_CODES.get(info.bayer_pattern, 0),
            supported_bins=info.supported_bins,
            supported_formats=self._formats,
            pixel_size_um=info.pixel_size_um,
            has_cooler=info.has_cooler,
            bit_depth=info.bit_depth,
        )

    # lifecycle

    def open(self, camera_id: int) -> None:
        self.calls.append("open")
        self._opened.add(camera_id)

    def close(self, camera_id: int) -> None:
        self.calls.append("close")
        self._opened.discard(camera_id)

    # controls

    def controls(self, camera_id: int) -> list[AsiControlCaps]:
        return list(_CAPS)

    def get_control(self, camera_id: int, control_type: int) -> tuple[int, bool]:
        if control_type == ControlType.EXPOSURE:
            return self._exposure_us, False
        if control_type == ControlType.TEMPERATURE:
            return round(self._sim.expose(0.001).metadata.sensor_temp_c * 10), False
        if control_type == ControlType.GAIN:
            return round(self._sim.get_control(ControlName.GAIN)), False
        if control_type == ControlType.OFFSET:
            return round(self._sim.get_control(ControlName.OFFSET)), False
        if control_type == ControlType.GAMMA:
            return round(self._sim.get_control(ControlName.GAMMA)), False
        if control_type == ControlType.WB_R:
            return round(self._sim.get_control(ControlName.WB_RED)), False
        if control_type == ControlType.WB_B:
            return round(self._sim.get_control(ControlName.WB_BLUE)), False
        if control_type in (ControlType.TARGET_TEMP, ControlType.COOLER_ON):
            return 0, False
        raise AsiError("ASIGetControlValue", 3)

    def set_control(
        self, camera_id: int, control_type: int, value: int, *, auto: bool = False
    ) -> None:
        if control_type == ControlType.EXPOSURE:
            self._exposure_us = int(value)
        elif control_type == ControlType.GAIN:
            self._sim.set_control(ControlName.GAIN, value)
        elif control_type == ControlType.OFFSET:
            self._sim.set_control(ControlName.OFFSET, value)
        elif control_type == ControlType.GAMMA:
            self._sim.set_control(ControlName.GAMMA, value)
        elif control_type == ControlType.WB_R:
            self._sim.set_control(ControlName.WB_RED, value)
        elif control_type == ControlType.WB_B:
            self._sim.set_control(ControlName.WB_BLUE, value)
        elif control_type == ControlType.COOLER_ON:
            self._sim.set_cooler(enabled=bool(value))
        elif control_type == ControlType.TARGET_TEMP:
            self._sim.set_cooler(enabled=True, target_c=float(value))
        else:
            raise AsiError("ASISetControlValue", 3)

    # geometry

    def set_roi_format(
        self, camera_id: int, width: int, height: int, binning: int, image_type: int
    ) -> None:
        self.calls.append(f"roi:{width}x{height}/{binning}")
        self._width, self._height, self._bin = width, height, binning
        self._image_type = image_type
        self._apply_roi()

    def set_start_position(self, camera_id: int, x: int, y: int) -> None:
        self._start_x, self._start_y = x, y
        self._apply_roi()

    def _apply_roi(self) -> None:
        self._sim.set_roi(
            Roi(
                x=self._start_x * self._bin,
                y=self._start_y * self._bin,
                width=self._width * self._bin,
                height=self._height * self._bin,
                bin=self._bin,
            )
        )

    # exposure

    def start_exposure(self, camera_id: int, *, dark: bool = False) -> None:
        if camera_id not in self._opened:
            raise AsiError("ASIStartExposure", 4)
        if self._fail_exposure:
            self._status = ExposureStatus.FAILED
            return
        frame = self._sim.expose(self._exposure_us / 1_000_000, dark=dark)
        data = frame.data
        if self._image_type in (ImageType.RAW8, ImageType.Y8):
            data = (data >> 8).astype("uint8")
        self._pending = data.tobytes()
        self._status = ExposureStatus.SUCCESS

    def stop_exposure(self, camera_id: int) -> None:
        self._status = ExposureStatus.IDLE

    def exposure_status(self, camera_id: int) -> ExposureStatus:
        return self._status

    def read_data(self, camera_id: int, size: int) -> bytes:
        if self._pending is None:
            raise AsiError("ASIGetDataAfterExp", 12)
        if len(self._pending) < size:
            raise AsiError("ASIGetDataAfterExp", 13)
        return self._pending[:size]
