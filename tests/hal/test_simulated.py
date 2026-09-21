import numpy as np
import pytest

from nttl.hal import BayerPattern, ControlName
from nttl.hal.simulated import SimulatedCamera


def test_same_seed_produces_identical_frames():
    a = SimulatedCamera(seed=42, width=128, height=128, star_count=20)
    b = SimulatedCamera(seed=42, width=128, height=128, star_count=20)
    a.open()
    b.open()
    assert np.array_equal(a.expose(0.3).data, b.expose(0.3).data)


def test_color_variant_declares_bayer_pattern():
    cam = SimulatedCamera(seed=1, is_color=True, bayer_pattern=BayerPattern.GRBG)
    cam.open()
    assert cam.info.is_color
    assert cam.info.bayer_pattern is BayerPattern.GRBG


def test_mono_variant_has_no_bayer_pattern():
    cam = SimulatedCamera(seed=1, is_color=False)
    cam.open()
    assert cam.info.bayer_pattern is BayerPattern.NONE


def test_dark_frames_have_bias_and_hot_pixels():
    cam = SimulatedCamera(seed=3, width=128, height=128)
    cam.open()
    cam.set_control(ControlName.GAIN, 0)
    dark = cam.expose(2.0, dark=True).data
    assert dark.mean() > 0
    assert dark.max() > dark.mean() * 4


def test_cooler_drives_sensor_temperature_down():
    cam = SimulatedCamera(
        seed=5, width=64, height=64, has_cooler=True, ambient_temp_c=20.0, star_count=10
    )
    cam.open()
    start = cam.expose(0.01).metadata.sensor_temp_c
    cam.set_cooler(enabled=True, target_c=-10.0)
    for _ in range(200):
        cam.expose(0.01)
    assert cam.expose(0.01).metadata.sensor_temp_c < start - 5


def test_saturation_is_clipped_to_bit_depth():
    cam = SimulatedCamera(seed=9, width=64, height=64)
    cam.open()
    cam.set_control(ControlName.GAIN, cam.controls()[ControlName.GAIN].max_value)
    frame = cam.expose(60.0)
    assert frame.data.max() <= 65535


def test_context_manager_opens_and_closes():
    with SimulatedCamera(seed=11) as cam:
        assert cam.expose(0.01).data.size > 0
    assert not cam.is_open


def test_invalid_roi_is_rejected():
    cam = SimulatedCamera(seed=13, width=64, height=64)
    cam.open()
    from nttl.hal import Roi
    from nttl.hal.errors import InvalidRoiError

    with pytest.raises(InvalidRoiError):
        cam.set_roi(Roi(x=0, y=0, width=128, height=64, bin=1))
    with pytest.raises(InvalidRoiError):
        cam.set_roi(Roi(x=0, y=0, width=64, height=64, bin=3))
