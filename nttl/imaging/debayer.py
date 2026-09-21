from __future__ import annotations

import cv2
import numpy as np

from nttl.hal import BayerPattern

AUTO = "auto"

_CV_CODES = {
    BayerPattern.RGGB: cv2.COLOR_BayerRGGB2RGB,
    BayerPattern.BGGR: cv2.COLOR_BayerBGGR2RGB,
    BayerPattern.GRBG: cv2.COLOR_BayerGRBG2RGB,
    BayerPattern.GBRG: cv2.COLOR_BayerGBRG2RGB,
}


class DebayerError(Exception):
    pass


def resolve_pattern(configured: str | BayerPattern, sensor: BayerPattern) -> BayerPattern:
    value = str(configured)
    if value.lower() == AUTO:
        return sensor
    try:
        return BayerPattern(value if value != "none" else BayerPattern.NONE)
    except ValueError:
        raise DebayerError(f"unknown bayer pattern: {configured}") from None


def debayer(data: np.ndarray, pattern: BayerPattern) -> np.ndarray:
    if pattern is BayerPattern.NONE:
        raise DebayerError("cannot debayer a frame without a bayer pattern")
    if data.ndim != 2:
        raise DebayerError("debayer expects a single channel frame")
    return np.asarray(cv2.cvtColor(data, _CV_CODES[pattern]))
