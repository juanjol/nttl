import numpy as np
import pytest

from nttl.hal import BayerPattern
from nttl.imaging.debayer import DebayerError, debayer, resolve_pattern


def mosaic(pattern: BayerPattern, r=1000, g=2000, b=3000, n=16) -> np.ndarray:
    layout = {
        BayerPattern.RGGB: [("R", 0, 0), ("G", 0, 1), ("G", 1, 0), ("B", 1, 1)],
        BayerPattern.BGGR: [("B", 0, 0), ("G", 0, 1), ("G", 1, 0), ("R", 1, 1)],
        BayerPattern.GRBG: [("G", 0, 0), ("R", 0, 1), ("B", 1, 0), ("G", 1, 1)],
        BayerPattern.GBRG: [("G", 0, 0), ("B", 0, 1), ("R", 1, 0), ("G", 1, 1)],
    }[pattern]
    values = {"R": r, "G": g, "B": b}
    out = np.zeros((n, n), dtype=np.uint16)
    for channel, dy, dx in layout:
        out[dy::2, dx::2] = values[channel]
    return out


@pytest.mark.parametrize("pattern", [p for p in BayerPattern if p is not BayerPattern.NONE])
def test_debayer_recovers_channel_order(pattern):
    rgb = debayer(mosaic(pattern), pattern)
    assert rgb.shape == (16, 16, 3)
    assert rgb.dtype == np.uint16
    means = rgb.reshape(-1, 3).mean(axis=0)
    assert means[0] == pytest.approx(1000, abs=200)
    assert means[1] == pytest.approx(2000, abs=200)
    assert means[2] == pytest.approx(3000, abs=200)


def test_debayer_rejects_missing_pattern():
    with pytest.raises(DebayerError):
        debayer(mosaic(BayerPattern.RGGB), BayerPattern.NONE)


def test_debayer_rejects_non_2d_input():
    with pytest.raises(DebayerError):
        debayer(np.zeros((4, 4, 3), dtype=np.uint16), BayerPattern.RGGB)


def test_resolve_pattern_auto_uses_sensor_pattern():
    assert resolve_pattern("auto", BayerPattern.GRBG) is BayerPattern.GRBG
    assert resolve_pattern("auto", BayerPattern.NONE) is BayerPattern.NONE


def test_resolve_pattern_forced_overrides_sensor():
    assert resolve_pattern(BayerPattern.BGGR, BayerPattern.RGGB) is BayerPattern.BGGR
    assert resolve_pattern("none", BayerPattern.RGGB) is BayerPattern.NONE


def test_resolve_pattern_rejects_unknown_value():
    with pytest.raises(DebayerError):
        resolve_pattern("XYZW", BayerPattern.RGGB)
