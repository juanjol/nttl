from __future__ import annotations

from enum import StrEnum
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from nttl.hal import FrameMetadata


class Position(StrEnum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


class OverlayItem(BaseModel):
    template: str
    position: Position = Position.BOTTOM_LEFT
    font_size: int = Field(default=16, ge=6, le=200)
    color: str = "#ffffff"
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    background: str | None = None
    background_opacity: float = Field(default=0.45, ge=0.0, le=1.0)


def _preset_items() -> dict[str, list[OverlayItem]]:
    """Ready made overlays, so a fresh install already stamps its frames."""
    return {
        "none": [],
        "timestamp": [
            OverlayItem(
                template="{datetime}",
                position=Position.BOTTOM_LEFT,
                font_size=22,
                background="#000000",
            )
        ],
        "standard": [
            OverlayItem(
                template="{datetime}",
                position=Position.BOTTOM_LEFT,
                font_size=22,
                background="#000000",
            ),
            OverlayItem(
                template="{exp}s  gain {gain}",
                position=Position.BOTTOM_RIGHT,
                font_size=18,
                background="#000000",
            ),
        ],
        "detailed": [
            OverlayItem(
                template="{camera}",
                position=Position.TOP_LEFT,
                font_size=18,
                background="#000000",
            ),
            OverlayItem(
                template="frame {seq}",
                position=Position.TOP_RIGHT,
                font_size=18,
                background="#000000",
            ),
            OverlayItem(
                template="{datetime}",
                position=Position.BOTTOM_LEFT,
                font_size=22,
                background="#000000",
            ),
            OverlayItem(
                template="{exp}s  gain {gain}  {sensor_temp:+.1f}C",
                position=Position.BOTTOM_RIGHT,
                font_size=18,
                background="#000000",
            ),
        ],
    }


DEFAULT_PRESET = "standard"


def preset_items(name: str) -> list[OverlayItem]:
    return _preset_items().get(name, [])


def preset_names() -> list[str]:
    return list(_preset_items())


class OverlayConfig(BaseModel):
    enabled: bool = True
    margin: int = Field(default=12, ge=0, le=200)
    line_spacing: int = Field(default=4, ge=0, le=100)
    font_path: str | None = None
    scale_to_frame: bool = True
    reference_height: int = Field(default=1080, ge=120, le=20000)
    items: list[OverlayItem] = Field(default_factory=lambda: preset_items(DEFAULT_PRESET))

    def scale_for(self, height: int) -> float:
        """Keep the text the same relative size on any sensor."""
        if not self.scale_to_frame or height <= 0:
            return 1.0
        return max(height / self.reference_height, 0.25)


class _SafeTokens(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return ""


def _tokens(metadata: FrameMetadata, extra: dict[str, Any] | None) -> _SafeTokens:
    local = metadata.timestamp_utc.astimezone()
    tokens = _SafeTokens(
        date=local.strftime("%Y-%m-%d"),
        time=local.strftime("%H:%M:%S"),
        datetime=local.strftime("%Y-%m-%d %H:%M:%S"),
        date_utc=metadata.timestamp_utc.strftime("%Y-%m-%d"),
        time_utc=metadata.timestamp_utc.strftime("%H:%M:%S"),
        exp=_trim(metadata.exposure_s),
        gain=_trim(metadata.gain),
        offset=_trim(metadata.offset),
        sensor_temp=_Temp(metadata.sensor_temp_c),
        seq=metadata.sequence,
        camera=metadata.camera_name,
        bin=metadata.bin,
        bayer=str(metadata.bayer_pattern),
    )
    tokens.update(metadata.extra)
    if extra:
        tokens.update(extra)
    return tokens


class _Temp(float):
    def __format__(self, spec: str) -> str:
        return format(float(self), spec or ".1f")


def _trim(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def render_tokens(
    template: str, metadata: FrameMetadata, extra: dict[str, Any] | None = None
) -> str:
    tokens = _tokens(metadata, extra)
    try:
        return template.format_map(tokens)
    except (ValueError, TypeError):
        return template


def _font(config: OverlayConfig, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    if config.font_path:
        try:
            return ImageFont.truetype(config.font_path, size)
        except OSError:
            pass
    for candidate in ("DejaVuSans.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _rgba(color: str, opacity: float) -> tuple[int, int, int, int]:
    from PIL import ImageColor

    r, g, b = ImageColor.getrgb(color)[:3]
    return r, g, b, round(255 * opacity)


def render_overlay(
    image: np.ndarray,
    config: OverlayConfig,
    metadata: FrameMetadata,
    extra: dict[str, Any] | None = None,
) -> np.ndarray:
    if not config.enabled or not config.items:
        return image
    rgb = np.dstack([image] * 3) if image.ndim == 2 else image
    if rgb.dtype != np.uint8:
        rgb = (rgb.astype(np.float32) / 257.0).astype(np.uint8)
    canvas = Image.fromarray(rgb).convert("RGBA")
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    width, height = canvas.size
    scale = config.scale_for(height)
    margin = max(0, round(config.margin * scale))
    line_spacing = max(0, round(config.line_spacing * scale))
    cursors = {position: 0 for position in Position}

    for item in config.items:
        text = render_tokens(item.template, metadata, extra)
        if not text:
            continue
        font_size = max(6, round(item.font_size * scale))
        font = _font(config, font_size)
        box = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = int(box[2] - box[0]), int(box[3] - box[1])
        offset = cursors[item.position]
        if item.position in (Position.TOP_LEFT, Position.BOTTOM_LEFT):
            x = margin
        else:
            x = int(width - margin - text_w)
        if item.position in (Position.TOP_LEFT, Position.TOP_RIGHT):
            y = margin + offset
        else:
            y = int(height - margin - text_h - offset)
        cursors[item.position] = offset + text_h + line_spacing
        if item.background:
            pad = max(2, font_size // 5)
            draw.rectangle(
                (x - pad, y - pad, x + text_w + pad, y + text_h + pad),
                fill=_rgba(item.background, item.background_opacity),
            )
        draw.text(
            (x - int(box[0]), y - int(box[1])),
            text,
            font=font,
            fill=_rgba(item.color, item.opacity),
        )

    merged = Image.alpha_composite(canvas, layer)
    # A mono frame has to stay mono, the overlay only paints over it.
    out = np.asarray(merged.convert("L" if image.ndim == 2 else "RGB"))
    if image.dtype == np.uint16:
        return (out.astype(np.uint16) * 257).astype(np.uint16)
    return out
