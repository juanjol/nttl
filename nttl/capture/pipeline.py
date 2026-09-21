from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from nttl.config.models import OutputConfig
from nttl.hal import BayerPattern, Frame, FrameMetadata
from nttl.imaging.calibrate import subtract_dark
from nttl.imaging.debayer import debayer, resolve_pattern
from nttl.imaging.overlay import render_overlay
from nttl.imaging.stats import FrameStats, frame_stats
from nttl.imaging.stretch import apply_stretch
from nttl.imaging.writers import ImageFormat, write_fits, write_image


@dataclass(frozen=True, slots=True)
class RenderedFrame:
    raw: np.ndarray
    image16: np.ndarray
    image8: np.ndarray
    stats: FrameStats
    dark_applied: bool


def render_frame(
    frame: Frame,
    config: OutputConfig,
    *,
    dark: np.ndarray | None = None,
    extra: dict[str, object] | None = None,
) -> RenderedFrame:
    raw = frame.data
    dark_applied = False
    if dark is not None:
        raw = subtract_dark(raw, dark)
        dark_applied = True

    stats = frame_stats(raw)
    pattern = resolve_pattern(config.debayer, frame.metadata.bayer_pattern)
    linear = debayer(raw, pattern) if pattern is not BayerPattern.NONE else raw

    image16 = apply_stretch(linear, config.stretch, bit_depth=16)
    image8 = apply_stretch(linear, config.stretch, bit_depth=8)
    if config.overlay.enabled and config.overlay.items:
        image16 = render_overlay(image16, config.overlay, frame.metadata, extra)
        image8 = render_overlay(image8, config.overlay, frame.metadata, extra)
    return RenderedFrame(
        raw=raw, image16=image16, image8=image8, stats=stats, dark_applied=dark_applied
    )


def write_outputs(
    stem: Path | str,
    rendered: RenderedFrame,
    metadata: FrameMetadata,
    config: OutputConfig,
) -> dict[ImageFormat, Path]:
    stem = Path(stem)
    fmt = config.format
    if fmt is ImageFormat.FITS:
        path = write_fits(stem, rendered.raw, metadata)
    elif fmt is ImageFormat.JPEG:
        path = write_image(stem, rendered.image8, fmt, quality=config.jpeg_quality)
    else:
        path = write_image(stem, rendered.image16, fmt, compression=config.png_compression)
    return {fmt: path}
