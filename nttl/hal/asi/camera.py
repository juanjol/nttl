from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Self

import numpy as np

from nttl.hal.asi._bindings import (
    AsiCameraInfo,
    AsiSdk,
    ControlType,
    ExposureStatus,
    ImageType,
)
from nttl.hal.errors import (
    CameraNotOpenError,
    ControlNotSupportedError,
    ExposureFailedError,
    InvalidRoiError,
)
from nttl.hal.types import (
    BayerPattern,
    CameraInfo,
    ControlName,
    ControlRange,
    Frame,
    FrameMetadata,
    Roi,
)

_BAYER = {
    0: BayerPattern.RGGB,
    1: BayerPattern.BGGR,
    2: BayerPattern.GRBG,
    3: BayerPattern.GBRG,
}

_CONTROL_MAP: dict[str, ControlType] = {
    ControlName.EXPOSURE: ControlType.EXPOSURE,
    ControlName.GAIN: ControlType.GAIN,
    ControlName.OFFSET: ControlType.OFFSET,
    ControlName.GAMMA: ControlType.GAMMA,
    ControlName.WB_RED: ControlType.WB_R,
    ControlName.WB_BLUE: ControlType.WB_B,
    ControlName.USB_BANDWIDTH: ControlType.BANDWIDTHOVERLOAD,
    ControlName.HIGH_SPEED: ControlType.HIGH_SPEED_MODE,
    ControlName.TARGET_TEMP: ControlType.TARGET_TEMP,
    ControlName.COOLER_ON: ControlType.COOLER_ON,
}

_PREFERRED_FORMATS = (ImageType.RAW16, ImageType.RAW8, ImageType.Y8)

_MICROSECONDS = 1_000_000.0
_POLL_INTERVAL_S = 0.01
_READ_TIMEOUT_MARGIN_S = 15.0


def _pick_image_type(info: AsiCameraInfo) -> int:
    """Prefer 16 bit raw frames, falling back to what the camera offers."""
    supported = set(info.supported_formats)
    for candidate in _PREFERRED_FORMATS:
        if candidate in supported:
            return int(candidate)
    return int(ImageType.RAW16)


class AsiCamera:
    """ZWO ASI camera driven through the vendor SDK."""

    def __init__(
        self,
        sdk: AsiSdk,
        info: AsiCameraInfo,
        *,
        image_type: int | None = None,
    ) -> None:
        self._sdk = sdk
        self._native = info
        self._image_type = image_type if image_type is not None else _pick_image_type(info)
        self._open = False
        self._sequence = 0
        self._controls: dict[str, ControlRange] = {}
        self._roi = Roi(x=0, y=0, width=info.max_width, height=info.max_height, bin=1)
        self._info = CameraInfo(
            name=info.name,
            camera_id=str(info.camera_id),
            max_width=info.max_width,
            max_height=info.max_height,
            bit_depth=info.bit_depth if self._image_type == ImageType.RAW16 else 8,
            is_color=info.is_color,
            bayer_pattern=_BAYER.get(info.bayer_pattern, BayerPattern.RGGB)
            if info.is_color
            else BayerPattern.NONE,
            pixel_size_um=info.pixel_size_um,
            has_cooler=info.has_cooler,
            supported_bins=info.supported_bins,
            backend="asi",
        )

    # protocol

    @property
    def info(self) -> CameraInfo:
        return self._info

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        if self._open:
            return
        self._sdk.open(self._native.camera_id)
        self._open = True
        self._controls = self._read_controls()
        self.set_roi(self._roi)

    def close(self) -> None:
        if not self._open:
            return
        self._sdk.close(self._native.camera_id)
        self._open = False

    def controls(self) -> dict[str, ControlRange]:
        if not self._controls:
            self._controls = self._read_controls()
        return dict(self._controls)

    def get_control(self, name: str) -> float:
        control_type = self._control_type(name)
        value, _ = self._sdk.get_control(self._native.camera_id, control_type)
        if control_type is ControlType.EXPOSURE:
            return value / _MICROSECONDS
        return float(value)

    def set_control(self, name: str, value: float) -> None:
        control_type = self._control_type(name)
        control = self._controls.get(name)
        native = value * _MICROSECONDS if control_type is ControlType.EXPOSURE else value
        if control is not None:
            low = control.min_value * (_MICROSECONDS if control_type is ControlType.EXPOSURE else 1)
            high = control.max_value * (
                _MICROSECONDS if control_type is ControlType.EXPOSURE else 1
            )
            native = min(max(native, low), high)
        self._sdk.set_control(self._native.camera_id, control_type, round(native))

    def get_roi(self) -> Roi:
        return self._roi

    def set_roi(self, roi: Roi) -> None:
        if roi.bin not in self._info.supported_bins:
            raise InvalidRoiError(f"unsupported binning: {roi.bin}")
        if roi.width <= 0 or roi.height <= 0:
            raise InvalidRoiError("roi must have positive size")
        if roi.x < 0 or roi.y < 0:
            raise InvalidRoiError("roi origin must be positive")
        if roi.x + roi.width > self._info.max_width:
            raise InvalidRoiError("roi exceeds sensor width")
        if roi.y + roi.height > self._info.max_height:
            raise InvalidRoiError("roi exceeds sensor height")
        if roi.output_width % 8 or roi.output_height % 2:
            raise InvalidRoiError("ASI cameras need a width multiple of 8 and an even height")
        self._sdk.set_roi_format(
            self._native.camera_id,
            roi.output_width,
            roi.output_height,
            roi.bin,
            self._image_type,
        )
        self._sdk.set_start_position(self._native.camera_id, roi.x // roi.bin, roi.y // roi.bin)
        self._roi = roi

    def set_cooler(self, *, enabled: bool, target_c: float | None = None) -> None:
        if not self._info.has_cooler:
            raise ControlNotSupportedError("camera has no cooler")
        if target_c is not None:
            self._sdk.set_control(self._native.camera_id, ControlType.TARGET_TEMP, round(target_c))
        self._sdk.set_control(self._native.camera_id, ControlType.COOLER_ON, 1 if enabled else 0)

    def expose(self, exposure_s: float, *, dark: bool = False) -> Frame:
        if not self._open:
            raise CameraNotOpenError("camera is not open")
        self.set_control(ControlName.EXPOSURE, exposure_s)
        camera_id = self._native.camera_id
        self._sdk.start_exposure(camera_id, dark=dark)
        deadline = time.monotonic() + exposure_s + _READ_TIMEOUT_MARGIN_S
        while True:
            status = self._sdk.exposure_status(camera_id)
            if status is ExposureStatus.SUCCESS:
                break
            if status is ExposureStatus.FAILED:
                raise ExposureFailedError("the camera reported a failed exposure")
            if time.monotonic() > deadline:
                self._sdk.stop_exposure(camera_id)
                raise ExposureFailedError(f"exposure timed out after {exposure_s:g}s")
            time.sleep(_POLL_INTERVAL_S)

        height, width = self._roi.output_height, self._roi.output_width
        bytes_per_pixel = 1 if self._image_type in (ImageType.RAW8, ImageType.Y8) else 2
        raw = self._sdk.read_data(camera_id, width * height * bytes_per_pixel)
        dtype = np.uint8 if bytes_per_pixel == 1 else np.uint16
        data = np.frombuffer(raw, dtype=dtype).reshape(height, width).copy()

        metadata = FrameMetadata(
            timestamp_utc=datetime.now(UTC),
            exposure_s=exposure_s,
            gain=self.get_control(ControlName.GAIN),
            offset=self._safe_control(ControlName.OFFSET),
            sensor_temp_c=self.sensor_temperature(),
            bayer_pattern=self._info.bayer_pattern,
            bin=self._roi.bin,
            roi=self._roi,
            sequence=self._sequence,
            camera_name=self._info.name,
            bit_depth=self._info.bit_depth,
            is_dark=dark,
        )
        self._sequence += 1
        return Frame(data=data, metadata=metadata)

    def sensor_temperature(self) -> float:
        try:
            value, _ = self._sdk.get_control(self._native.camera_id, ControlType.TEMPERATURE)
        except Exception:
            return float("nan")
        return value / 10.0

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # internals

    def _control_type(self, name: str) -> ControlType:
        try:
            return _CONTROL_MAP[name]
        except KeyError:
            raise ControlNotSupportedError(f"unknown control: {name}") from None

    def _safe_control(self, name: str) -> float:
        try:
            return self.get_control(name)
        except Exception:
            return 0.0

    def _read_controls(self) -> dict[str, ControlRange]:
        reverse = {value: key for key, value in _CONTROL_MAP.items()}
        result: dict[str, ControlRange] = {}
        for caps in self._sdk.controls(self._native.camera_id):
            name = reverse.get(ControlType(caps.control_type))
            if name is None:
                continue
            scale = _MICROSECONDS if caps.control_type == ControlType.EXPOSURE else 1.0
            result[name] = ControlRange(
                name=name,
                min_value=caps.min_value / scale,
                max_value=caps.max_value / scale,
                default=caps.default / scale,
                unit="s" if scale != 1.0 else "",
                writable=caps.writable,
                auto_supported=caps.auto_supported,
            )
        return result


def open_asi_camera(
    camera_id: str | None = None, sdk: AsiSdk | None = None, **options: Any
) -> AsiCamera:
    from nttl.hal.errors import CameraNotFoundError

    driver = sdk or AsiSdk(options.pop("library_path", None))
    count = driver.camera_count()
    if count == 0:
        raise CameraNotFoundError("no ASI camera is connected")
    infos = [driver.camera_info(index) for index in range(count)]
    if camera_id is None:
        chosen = infos[0]
    else:
        matches = [
            info
            for info in infos
            if str(info.camera_id) == str(camera_id) or info.name == camera_id
        ]
        if not matches:
            available = ", ".join(f"{info.camera_id}:{info.name}" for info in infos)
            raise CameraNotFoundError(f"no ASI camera matching '{camera_id}' (found {available})")
        chosen = matches[0]
    camera = AsiCamera(driver, chosen, **options)
    camera.open()
    return camera


def list_asi_cameras(sdk: AsiSdk | None = None) -> list[CameraInfo]:
    driver = sdk or AsiSdk()
    return [
        AsiCamera(driver, driver.camera_info(index)).info for index in range(driver.camera_count())
    ]
