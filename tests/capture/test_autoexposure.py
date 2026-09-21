import numpy as np
import pytest

from nttl.capture.autoexposure import (
    AutoExposureConfig,
    ExposureSettings,
    Priority,
    gain_to_factor,
    next_settings,
)
from nttl.imaging.stats import FrameStats


def stats(level: float, *, saturated: float = 0.0, high: float | None = None) -> FrameStats:
    return FrameStats(
        median=level * 65535,
        mean=level * 65535,
        low_percentile=0.0,
        high_percentile=(high if high is not None else min(1.0, level * 2)) * 65535,
        saturated_fraction=saturated,
        max_value=65535,
        normalized_median=level,
        normalized_high=high if high is not None else min(1.0, level * 2),
    )


def config(**kwargs) -> AutoExposureConfig:
    defaults = dict(
        target_level=0.2,
        tolerance=0.02,
        min_exposure_s=0.001,
        max_exposure_s=30.0,
        min_gain=0.0,
        max_gain=400.0,
        max_change_factor=2.0,
        max_gain_step=50.0,
        damping=1.0,
    )
    defaults.update(kwargs)
    return AutoExposureConfig(**defaults)


def test_inside_deadband_keeps_settings():
    current = ExposureSettings(exposure_s=5.0, gain=100.0)
    assert next_settings(current, stats(0.21), config()) == current


def test_dark_frame_increases_exposure_first():
    out = next_settings(ExposureSettings(1.0, 100.0), stats(0.1), config())
    assert out.exposure_s > 1.0
    assert out.gain == 100.0


def test_bright_frame_reduces_gain_first():
    out = next_settings(ExposureSettings(1.0, 200.0), stats(0.3), config())
    assert out.gain < 200.0
    assert out.exposure_s == pytest.approx(1.0)


def test_gain_takes_over_when_exposure_hits_ceiling():
    cfg = config(max_exposure_s=10.0)
    out = next_settings(ExposureSettings(10.0, 100.0), stats(0.05), cfg)
    assert out.exposure_s == pytest.approx(10.0)
    assert out.gain > 100.0


def test_exposure_reduced_when_gain_hits_floor():
    cfg = config(min_gain=100.0)
    out = next_settings(ExposureSettings(4.0, 100.0), stats(0.6), cfg)
    assert out.gain == pytest.approx(100.0)
    assert out.exposure_s < 4.0


def test_gain_priority_moves_gain_first():
    cfg = config(priority=Priority.GAIN)
    out = next_settings(ExposureSettings(1.0, 100.0), stats(0.16), cfg)
    assert out.gain > 100.0
    assert out.exposure_s == pytest.approx(1.0)


def test_gain_step_overflow_spills_into_exposure():
    cfg = config(priority=Priority.GAIN, max_gain_step=10.0)
    out = next_settings(ExposureSettings(1.0, 100.0), stats(0.1), cfg)
    assert out.gain == pytest.approx(110.0)
    assert out.exposure_s > 1.0


def test_ramp_limit_caps_single_step_change():
    cfg = config(max_change_factor=1.5)
    out = next_settings(ExposureSettings(1.0, 0.0), stats(0.001), cfg)
    assert out.exposure_s <= 1.5 + 1e-6


def test_saturation_forces_reduction_even_inside_deadband():
    cfg = config(saturation_limit=0.01)
    out = next_settings(ExposureSettings(4.0, 200.0), stats(0.2, saturated=0.05), cfg)
    assert out.gain < 200.0 or out.exposure_s < 4.0


def test_bounds_are_never_exceeded():
    cfg = config(min_exposure_s=0.5, max_exposure_s=8.0, min_gain=50.0, max_gain=150.0)
    settings = ExposureSettings(8.0, 150.0)
    for level in (0.001, 0.9, 0.5, 0.001):
        settings = next_settings(settings, stats(level), cfg)
        assert cfg.min_exposure_s <= settings.exposure_s <= cfg.max_exposure_s
        assert cfg.min_gain <= settings.gain <= cfg.max_gain


def test_converges_on_a_linear_sensor_model():
    cfg = config(damping=0.8)
    settings = ExposureSettings(0.01, 0.0)
    sky = 0.004
    for _ in range(40):
        level = min(1.0, sky * settings.exposure_s * gain_to_factor(settings.gain))
        settings = next_settings(settings, stats(level), cfg)
    level = min(1.0, sky * settings.exposure_s * gain_to_factor(settings.gain))
    assert level == pytest.approx(cfg.target_level, abs=cfg.tolerance)


def test_tracks_falling_light_without_oscillating():
    cfg = config(damping=0.7, max_change_factor=1.6)
    settings = ExposureSettings(0.05, 0.0)
    levels = []
    for step in range(120):
        sky = 0.5 * np.exp(-step / 12.0) + 0.0008
        level = min(1.0, sky * settings.exposure_s * gain_to_factor(settings.gain))
        levels.append(level)
        settings = next_settings(settings, stats(level), cfg)
    tail = np.array(levels[-20:])
    assert np.all(np.abs(tail - cfg.target_level) < 0.05)
    assert tail.std() < 0.02


def test_disabled_controller_is_a_no_op():
    cfg = config(enabled=False)
    current = ExposureSettings(2.0, 30.0)
    assert next_settings(current, stats(0.9), cfg) == current
