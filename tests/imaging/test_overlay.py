from datetime import UTC, datetime

import numpy as np

from nttl.hal import BayerPattern, FrameMetadata, Roi
from nttl.imaging.overlay import OverlayConfig, OverlayItem, Position, render_overlay, render_tokens


def metadata() -> FrameMetadata:
    return FrameMetadata(
        timestamp_utc=datetime(2026, 9, 21, 22, 30, 15, tzinfo=UTC),
        exposure_s=12.5,
        gain=220,
        offset=50,
        sensor_temp_c=-9.83,
        bayer_pattern=BayerPattern.RGGB,
        bin=1,
        roi=Roi(0, 0, 64, 64, 1),
        sequence=41,
        camera_name="ASI294MC Pro",
        bit_depth=16,
    )


def test_render_tokens_replaces_known_fields():
    text = render_tokens("{date_utc} {time_utc} {exp}s g{gain} {sensor_temp}C #{seq}", metadata())
    assert text == "2026-09-21 22:30:15 12.5s g220 -9.8C #41"


def test_render_tokens_uses_local_time_by_default():
    local = metadata().timestamp_utc.astimezone()
    assert render_tokens("{datetime}", metadata()) == local.strftime("%Y-%m-%d %H:%M:%S")


def test_render_tokens_supports_format_specs_and_custom_values():
    text = render_tokens("{sensor_temp:+.2f} {site}", metadata(), extra={"site": "Aralar"})
    assert text == "-9.83 Aralar"


def test_render_tokens_leaves_unknown_tokens_empty():
    assert render_tokens("[{nope}]", metadata()) == "[]"


def test_render_overlay_draws_on_a_copy():
    image = np.zeros((80, 240, 3), dtype=np.uint8)
    config = OverlayConfig(
        items=[OverlayItem(template="{date}", position=Position.TOP_LEFT, font_size=14)]
    )
    out = render_overlay(image, config, metadata())
    assert out.shape == image.shape
    assert image.max() == 0
    assert out.max() > 0


def test_render_overlay_disabled_returns_input_unchanged():
    image = np.zeros((40, 80, 3), dtype=np.uint8)
    out = render_overlay(image, OverlayConfig(enabled=False), metadata())
    assert np.array_equal(out, image)


def test_render_overlay_positions_are_independent():
    image = np.zeros((120, 320, 3), dtype=np.uint8)
    top = render_overlay(
        image,
        OverlayConfig(items=[OverlayItem(template="AAA", position=Position.TOP_LEFT)]),
        metadata(),
    )
    bottom = render_overlay(
        image,
        OverlayConfig(items=[OverlayItem(template="AAA", position=Position.BOTTOM_RIGHT)]),
        metadata(),
    )
    assert top[:60].max() > 0 and top[60:].max() == 0
    assert bottom[60:].max() > 0 and bottom[:60].max() == 0
