from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_SAMPLE_LIMIT = 200_000


@dataclass(frozen=True, slots=True)
class FrameStats:
    median: float
    mean: float
    low_percentile: float
    high_percentile: float
    saturated_fraction: float
    max_value: float
    normalized_median: float
    normalized_high: float


def frame_stats(
    data: np.ndarray,
    *,
    low: float = 1.0,
    high: float = 99.5,
    saturation_threshold: float = 0.98,
) -> FrameStats:
    full_scale = float(np.iinfo(data.dtype).max) if data.dtype.kind == "u" else 1.0
    flat = data.reshape(-1)
    if flat.size > _SAMPLE_LIMIT:
        step = flat.size // _SAMPLE_LIMIT + 1
        sample = flat[::step]
    else:
        sample = flat
    sample = sample.astype(np.float32)
    median = float(np.median(sample))
    lo, hi = (float(v) for v in np.percentile(sample, (low, high)))
    saturated = float(np.count_nonzero(sample >= full_scale * saturation_threshold) / sample.size)
    return FrameStats(
        median=median,
        mean=float(sample.mean()),
        low_percentile=lo,
        high_percentile=hi,
        saturated_fraction=saturated,
        max_value=float(sample.max()),
        normalized_median=median / full_scale,
        normalized_high=hi / full_scale,
    )
