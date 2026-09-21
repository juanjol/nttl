from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from nttl.imaging.stats import FrameStats

_GAIN_DB_SCALE = 200.0


class Priority(StrEnum):
    EXPOSURE = "exposure"
    GAIN = "gain"


@dataclass(frozen=True, slots=True)
class ExposureSettings:
    exposure_s: float
    gain: float


class AutoExposureConfig(BaseModel):
    enabled: bool = True
    target_level: float = Field(default=0.22, gt=0.0, lt=1.0)
    tolerance: float = Field(default=0.03, ge=0.0, lt=0.5)
    min_exposure_s: float = Field(default=0.001, gt=0.0)
    max_exposure_s: float = Field(default=30.0, gt=0.0)
    min_gain: float = Field(default=0.0, ge=0.0)
    max_gain: float = Field(default=400.0, ge=0.0)
    priority: Priority = Priority.EXPOSURE
    max_change_factor: float = Field(default=1.6, gt=1.0, le=16.0)
    max_gain_step: float = Field(default=40.0, gt=0.0)
    damping: float = Field(default=0.7, gt=0.0, le=1.0)
    saturation_limit: float = Field(default=0.02, ge=0.0, le=1.0)
    saturation_reduction: float = Field(default=0.7, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _check_ranges(self) -> AutoExposureConfig:
        if self.min_exposure_s > self.max_exposure_s:
            raise ValueError("min_exposure_s must not exceed max_exposure_s")
        if self.min_gain > self.max_gain:
            raise ValueError("min_gain must not exceed max_gain")
        return self


def gain_to_factor(gain: float) -> float:
    return float(10.0 ** (gain / _GAIN_DB_SCALE))


def factor_to_gain_delta(factor: float) -> float:
    return _GAIN_DB_SCALE * math.log10(max(factor, 1e-9))


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _needed_factor(stats: FrameStats, config: AutoExposureConfig) -> float | None:
    level = max(stats.normalized_median, 1e-6)
    if stats.saturated_fraction > config.saturation_limit:
        return config.saturation_reduction
    if abs(level - config.target_level) <= config.tolerance:
        return None
    raw = config.target_level / level
    damped = raw**config.damping
    return _clamp(damped, 1.0 / config.max_change_factor, config.max_change_factor)


def next_settings(
    current: ExposureSettings, stats: FrameStats, config: AutoExposureConfig
) -> ExposureSettings:
    if not config.enabled:
        return current
    factor = _needed_factor(stats, config)
    if factor is None:
        return current

    exposure = _clamp(current.exposure_s, config.min_exposure_s, config.max_exposure_s)
    gain = _clamp(current.gain, config.min_gain, config.max_gain)
    increase = factor > 1.0
    exposure_first = (config.priority is Priority.EXPOSURE) == increase

    order = ("exposure", "gain") if exposure_first else ("gain", "exposure")
    remaining = factor
    for knob in order:
        if abs(remaining - 1.0) < 1e-6:
            break
        if knob == "exposure":
            wanted = exposure * remaining
            exposure = _clamp(wanted, config.min_exposure_s, config.max_exposure_s)
            remaining = wanted / exposure if exposure > 0 else 1.0
        else:
            delta = _clamp(
                factor_to_gain_delta(remaining), -config.max_gain_step, config.max_gain_step
            )
            previous = gain
            gain = _clamp(gain + delta, config.min_gain, config.max_gain)
            remaining /= gain_to_factor(gain - previous)

    return ExposureSettings(exposure_s=exposure, gain=gain)
