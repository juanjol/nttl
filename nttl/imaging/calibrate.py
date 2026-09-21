from __future__ import annotations

import numpy as np


class CalibrationError(Exception):
    pass


def subtract_dark(light: np.ndarray, dark: np.ndarray, *, scale: float = 1.0) -> np.ndarray:
    if light.shape != dark.shape:
        raise CalibrationError(f"shape mismatch: light {light.shape} vs dark {dark.shape}")
    result = light.astype(np.float32) - dark.astype(np.float32) * scale
    return np.clip(result, 0, np.iinfo(light.dtype).max).astype(light.dtype)
