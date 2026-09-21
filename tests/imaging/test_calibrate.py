import numpy as np
import pytest

from nttl.imaging.calibrate import CalibrationError, subtract_dark


def test_subtract_dark_removes_bias_and_hot_pixels():
    light = np.full((8, 8), 1200, dtype=np.uint16)
    light[3, 3] = 30000
    dark = np.full((8, 8), 200, dtype=np.uint16)
    dark[3, 3] = 29000
    out = subtract_dark(light, dark)
    assert out.dtype == np.uint16
    assert out[0, 0] == 1000
    assert out[3, 3] == 1000


def test_subtract_dark_clips_at_zero():
    light = np.full((4, 4), 100, dtype=np.uint16)
    dark = np.full((4, 4), 500, dtype=np.uint16)
    assert subtract_dark(light, dark).max() == 0


def test_subtract_dark_scaling():
    light = np.full((4, 4), 1000, dtype=np.uint16)
    dark = np.full((4, 4), 200, dtype=np.uint16)
    assert subtract_dark(light, dark, scale=0.5)[0, 0] == 900


def test_shape_mismatch_raises():
    with pytest.raises(CalibrationError):
        subtract_dark(np.zeros((4, 4), np.uint16), np.zeros((8, 8), np.uint16))
