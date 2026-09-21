import numpy as np
import pytest

from nttl.imaging.stretch import StretchConfig, StretchMode, apply_stretch


def sky_frame() -> np.ndarray:
    rng = np.random.default_rng(0)
    data = rng.normal(800, 40, (64, 64))
    data[10, 10] = 40000
    return np.clip(data, 0, 65535).astype(np.uint16)


def test_linear_stretch_maps_to_full_range():
    out = apply_stretch(sky_frame(), StretchConfig(mode=StretchMode.LINEAR))
    assert out.dtype == np.uint8
    assert out.min() == 0
    assert out.max() == 255


def test_auto_stretch_lifts_background_to_target():
    cfg = StretchConfig(mode=StretchMode.AUTO, target_background=0.25)
    out = apply_stretch(sky_frame(), cfg)
    assert np.median(out) / 255 == pytest.approx(0.25, abs=0.08)


def test_none_mode_only_rescales_bit_depth():
    data = np.array([[0, 32768, 65535]], dtype=np.uint16)
    out = apply_stretch(data, StretchConfig(mode=StretchMode.NONE))
    assert out.tolist() == [[0, 128, 255]]


def test_stretch_can_output_16_bit():
    out = apply_stretch(sky_frame(), StretchConfig(mode=StretchMode.AUTO), bit_depth=16)
    assert out.dtype == np.uint16
    assert out.max() > 255


def test_rgb_input_is_stretched_jointly():
    rgb = np.dstack([sky_frame()] * 3)
    out = apply_stretch(rgb, StretchConfig(mode=StretchMode.AUTO))
    assert out.shape == rgb.shape
    assert np.array_equal(out[..., 0], out[..., 2])
