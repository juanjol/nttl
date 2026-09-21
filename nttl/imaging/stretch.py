from __future__ import annotations

from enum import StrEnum

import numpy as np
from pydantic import BaseModel, Field


class StretchMode(StrEnum):
    NONE = "none"
    LINEAR = "linear"
    AUTO = "auto"


class StretchConfig(BaseModel):
    mode: StretchMode = StretchMode.AUTO
    target_background: float = Field(default=0.25, ge=0.01, le=0.9)
    shadow_clip: float = Field(default=-2.8, le=0.0)
    low_percentile: float = Field(default=0.5, ge=0.0, le=49.0)
    high_percentile: float = Field(default=99.8, ge=51.0, le=100.0)
    gamma: float = Field(default=1.0, gt=0.0, le=5.0)


def _mtf(midtone: float, x: np.ndarray) -> np.ndarray:
    if midtone <= 0.0:
        return np.ones_like(x)
    if midtone >= 1.0:
        return np.zeros_like(x)
    result = ((midtone - 1.0) * x) / (((2.0 * midtone - 1.0) * x) - midtone)
    return np.asarray(result, dtype=np.float32)


def _auto_transform(norm: np.ndarray) -> tuple[float, float]:
    sample = norm.reshape(-1)
    if sample.size > 200_000:
        sample = sample[:: sample.size // 200_000 + 1]
    median = float(np.median(sample))
    mad = float(np.median(np.abs(sample - median))) * 1.4826
    return median, mad


def apply_stretch(
    data: np.ndarray, config: StretchConfig | None = None, *, bit_depth: int = 8
) -> np.ndarray:
    config = config or StretchConfig()
    out_max = 255 if bit_depth == 8 else 65535
    out_dtype = np.uint8 if bit_depth == 8 else np.uint16
    full_scale = float(np.iinfo(data.dtype).max) if data.dtype.kind == "u" else 1.0
    norm = data.astype(np.float32) / full_scale

    if config.mode is StretchMode.NONE:
        stretched = norm
    elif config.mode is StretchMode.LINEAR:
        lo, hi = (
            float(v) for v in np.percentile(norm, (config.low_percentile, config.high_percentile))
        )
        stretched = np.clip((norm - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    else:
        median, mad = _auto_transform(norm)
        shadows = float(np.clip(median + config.shadow_clip * mad, 0.0, 1.0))
        centered = float(np.clip(median - shadows, 1e-6, 1.0))
        midtone = float(_mtf(config.target_background, np.array([centered]))[0])
        clipped = np.clip((norm - shadows) / max(1.0 - shadows, 1e-6), 0.0, 1.0)
        stretched = _mtf(midtone, clipped)

    if config.gamma != 1.0:
        stretched = np.power(np.clip(stretched, 0.0, 1.0), 1.0 / config.gamma)

    if config.mode is StretchMode.NONE and bit_depth == 8 and data.dtype == np.uint16:
        return np.asarray(data >> 8, dtype=out_dtype)
    scaled = np.clip(stretched * out_max + 0.5, 0, out_max)
    return np.asarray(scaled, dtype=out_dtype)
