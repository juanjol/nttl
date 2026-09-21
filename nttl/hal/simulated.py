from __future__ import annotations

from datetime import UTC, datetime
from typing import Self

import numpy as np

from nttl.hal.errors import CameraNotOpenError, ControlNotSupportedError, InvalidRoiError
from nttl.hal.types import (
    BayerPattern,
    CameraInfo,
    ControlName,
    ControlRange,
    Frame,
    FrameMetadata,
    Roi,
)

_COOLER_STEP = 0.05
_DARK_CURRENT_AT_20C = 12.0
_ELECTRONS_PER_ADU = 1.6
_READ_NOISE_E = 3.2


class SimulatedCamera:
    """Synthetic camera used for development, tests and demos."""

    def __init__(
        self,
        *,
        seed: int = 0,
        width: int = 1024,
        height: int = 768,
        is_color: bool = True,
        bayer_pattern: BayerPattern = BayerPattern.RGGB,
        has_cooler: bool = False,
        ambient_temp_c: float = 12.0,
        star_count: int = 400,
        name: str = "NTTL Simulated Camera",
    ) -> None:
        self._info = CameraInfo(
            name=name,
            camera_id="simulated-0",
            max_width=width,
            max_height=height,
            bit_depth=16,
            is_color=is_color,
            bayer_pattern=bayer_pattern if is_color else BayerPattern.NONE,
            pixel_size_um=3.76,
            has_cooler=has_cooler,
            supported_bins=(1, 2, 4),
            backend="simulated",
        )
        self._seed = seed
        self._rng = np.random.default_rng(seed)
        self._controls = self._build_controls()
        self._values = {name: c.default for name, c in self._controls.items()}
        self._roi = Roi(x=0, y=0, width=width, height=height, bin=1)
        self._open = False
        self._sequence = 0
        self._ambient = ambient_temp_c
        self._sensor_temp = ambient_temp_c
        self._cooler_on = False
        self._cooler_target = ambient_temp_c
        self._star_count = star_count
        self._scene = self._build_scene()
        self._hot_pixels = self._build_hot_pixels()

    # construction helpers

    def _build_controls(self) -> dict[str, ControlRange]:
        controls = [
            ControlRange(ControlName.EXPOSURE, 0.000032, 3600.0, 1.0, "s"),
            ControlRange(ControlName.GAIN, 0.0, 500.0, 120.0, "0.1dB", auto_supported=True),
            ControlRange(ControlName.OFFSET, 0.0, 600.0, 50.0, "ADU"),
            ControlRange(ControlName.GAMMA, 1.0, 100.0, 50.0),
            ControlRange(ControlName.WB_RED, 1.0, 99.0, 52.0),
            ControlRange(ControlName.WB_BLUE, 1.0, 99.0, 95.0),
        ]
        if self._info.has_cooler:
            controls += [
                ControlRange(ControlName.TARGET_TEMP, -40.0, 30.0, 0.0, "C"),
                ControlRange(ControlName.COOLER_ON, 0.0, 1.0, 0.0),
            ]
        return {c.name: c for c in controls}

    def _build_scene(self) -> np.ndarray:
        rng = np.random.default_rng(self._seed + 1)
        h, w = self._info.max_height, self._info.max_width
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        gradient = 18.0 + 10.0 * (1.0 - yy / h) + 4.0 * (xx / w)
        scene = gradient
        sigma = 1.6
        for _ in range(self._star_count):
            cx = rng.uniform(0, w)
            cy = rng.uniform(0, h)
            flux = rng.pareto(1.6) * 900.0 + 60.0
            x0, x1 = max(0, int(cx - 6)), min(w, int(cx + 7))
            y0, y1 = max(0, int(cy - 6)), min(h, int(cy + 7))
            if x1 <= x0 or y1 <= y0:
                continue
            patch_y = yy[y0:y1, x0:x1] - cy
            patch_x = xx[y0:y1, x0:x1] - cx
            scene[y0:y1, x0:x1] += flux * np.exp(-(patch_x**2 + patch_y**2) / (2.0 * sigma**2))
        return np.asarray(scene, dtype=np.float32)

    def _build_hot_pixels(self) -> np.ndarray:
        rng = np.random.default_rng(self._seed + 2)
        h, w = self._info.max_height, self._info.max_width
        hot = np.zeros((h, w), dtype=np.float32)
        count = max(8, (h * w) // 20000)
        ys = rng.integers(0, h, count)
        xs = rng.integers(0, w, count)
        hot[ys, xs] = rng.uniform(300.0, 3000.0, count)
        return hot

    def _bayer_response(self) -> np.ndarray:
        h, w = self._info.max_height, self._info.max_width
        if not self._info.is_color:
            return np.ones((h, w), dtype=np.float32)
        red = self._values[ControlName.WB_RED] / 52.0
        blue = self._values[ControlName.WB_BLUE] / 95.0
        layout = {
            BayerPattern.RGGB: ((red, 1.0), (1.0, blue)),
            BayerPattern.BGGR: ((blue, 1.0), (1.0, red)),
            BayerPattern.GRBG: ((1.0, red), (blue, 1.0)),
            BayerPattern.GBRG: ((1.0, blue), (red, 1.0)),
        }[self._info.bayer_pattern]
        response = np.empty((h, w), dtype=np.float32)
        response[0::2, 0::2] = layout[0][0]
        response[0::2, 1::2] = layout[0][1]
        response[1::2, 0::2] = layout[1][0]
        response[1::2, 1::2] = layout[1][1]
        return response

    # protocol

    @property
    def info(self) -> CameraInfo:
        return self._info

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def controls(self) -> dict[str, ControlRange]:
        return dict(self._controls)

    def get_control(self, name: str) -> float:
        self._require_control(name)
        return self._values[name]

    def set_control(self, name: str, value: float) -> None:
        control = self._require_control(name)
        self._values[name] = control.clamp(value)
        if name == ControlName.COOLER_ON:
            self._cooler_on = self._values[name] >= 0.5
        elif name == ControlName.TARGET_TEMP:
            self._cooler_target = self._values[name]

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
        self._roi = roi

    def set_cooler(self, *, enabled: bool, target_c: float | None = None) -> None:
        if not self._info.has_cooler:
            raise ControlNotSupportedError("camera has no cooler")
        self._cooler_on = enabled
        self.set_control(ControlName.COOLER_ON, 1.0 if enabled else 0.0)
        if target_c is not None:
            self.set_control(ControlName.TARGET_TEMP, target_c)

    def expose(self, exposure_s: float, *, dark: bool = False) -> Frame:
        if not self._open:
            raise CameraNotOpenError("camera is not open")
        exposure_s = self._controls[ControlName.EXPOSURE].clamp(exposure_s)
        self._step_temperature()
        roi = self._roi
        window = np.s_[roi.y : roi.y + roi.height, roi.x : roi.x + roi.width]
        gain_factor = 10.0 ** (self._values[ControlName.GAIN] / 200.0)
        dark_current = _DARK_CURRENT_AT_20C * 2.0 ** ((self._sensor_temp - 20.0) / 6.0)

        electrons = np.full((roi.height, roi.width), dark_current * exposure_s, dtype=np.float32)
        electrons += self._hot_pixels[window] * exposure_s
        if not dark:
            electrons += self._scene[window] * self._bayer_response()[window] * exposure_s

        signal = self._rng.poisson(np.clip(electrons, 0.0, 1e9)).astype(np.float32)
        signal += self._rng.normal(0.0, _READ_NOISE_E, signal.shape).astype(np.float32)
        adu = signal * gain_factor / _ELECTRONS_PER_ADU + self._values[ControlName.OFFSET]

        if roi.bin > 1:
            b = roi.bin
            oh, ow = roi.output_height, roi.output_width
            adu = adu[: oh * b, : ow * b].reshape(oh, b, ow, b).sum(axis=(1, 3))

        data = np.clip(adu, 0, 65535).astype(np.uint16)
        metadata = FrameMetadata(
            timestamp_utc=datetime.now(UTC),
            exposure_s=exposure_s,
            gain=self._values[ControlName.GAIN],
            offset=self._values[ControlName.OFFSET],
            sensor_temp_c=round(self._sensor_temp, 2),
            bayer_pattern=self._info.bayer_pattern,
            bin=roi.bin,
            roi=roi,
            sequence=self._sequence,
            camera_name=self._info.name,
            bit_depth=self._info.bit_depth,
            is_dark=dark,
        )
        self._sequence += 1
        return Frame(data=data, metadata=metadata)

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # internals

    def _require_control(self, name: str) -> ControlRange:
        try:
            return self._controls[name]
        except KeyError:
            raise ControlNotSupportedError(f"unknown control: {name}") from None

    def _step_temperature(self) -> None:
        target = self._cooler_target if self._cooler_on else self._ambient
        self._sensor_temp += (target - self._sensor_temp) * _COOLER_STEP
