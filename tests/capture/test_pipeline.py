import numpy as np
import pytest

from nttl.capture.pipeline import render_frame, write_outputs
from nttl.config.models import OutputConfig
from nttl.hal import BayerPattern
from nttl.hal.simulated import SimulatedCamera
from nttl.imaging import ImageFormat
from nttl.imaging.overlay import OverlayConfig, OverlayItem, Position


def camera(**kwargs) -> SimulatedCamera:
    cam = SimulatedCamera(seed=2, width=64, height=64, star_count=20, **kwargs)
    cam.open()
    return cam


def test_color_frame_is_debayered_for_display():
    frame = camera(is_color=True, bayer_pattern=BayerPattern.RGGB).expose(1.0)
    rendered = render_frame(frame, OutputConfig())
    assert rendered.raw.ndim == 2
    assert rendered.image16.shape == (64, 64, 3)
    assert rendered.image8.shape == (64, 64, 3)
    assert rendered.image8.dtype == np.uint8


def test_mono_frame_stays_single_channel():
    frame = camera(is_color=False).expose(1.0)
    rendered = render_frame(frame, OutputConfig())
    assert rendered.image16.ndim == 2
    assert rendered.image8.ndim == 2


def test_debayer_can_be_forced_off():
    frame = camera(is_color=True).expose(1.0)
    rendered = render_frame(frame, OutputConfig(debayer="none"))
    assert rendered.image16.ndim == 2


def test_dark_subtraction_is_applied_to_raw_and_display():
    cam = camera(is_color=False)
    dark = cam.expose(1.0, dark=True).data
    frame = cam.expose(1.0)
    plain = render_frame(frame, OutputConfig())
    calibrated = render_frame(frame, OutputConfig(), dark=dark)
    assert calibrated.raw.mean() < plain.raw.mean()
    assert calibrated.dark_applied is True
    assert plain.dark_applied is False


def test_overlay_is_rendered_on_outputs():
    frame = camera(is_color=False).expose(1.0)
    config = OutputConfig(
        overlay=OverlayConfig(
            items=[OverlayItem(template="{date_utc}", position=Position.TOP_LEFT, font_size=10)]
        )
    )
    rendered = render_frame(frame, config)
    assert rendered.image8[:20, :40].max() == 255


def test_stats_are_reported():
    frame = camera(is_color=False).expose(1.0)
    rendered = render_frame(frame, OutputConfig())
    assert 0.0 < rendered.stats.normalized_median < 1.0


@pytest.mark.parametrize("fmt", [ImageFormat.FITS, ImageFormat.PNG, ImageFormat.JPEG])
def test_write_outputs_creates_the_configured_format(tmp_path, fmt):
    frame = camera(is_color=True).expose(1.0)
    config = OutputConfig(directory=tmp_path, format=fmt)
    rendered = render_frame(frame, config)
    written = write_outputs(tmp_path / "frame_00001", rendered, frame.metadata, config)
    assert set(written) == {fmt}
    for path in written.values():
        assert path.exists() and path.stat().st_size > 0


def test_a_configuration_with_a_legacy_format_list_still_loads():
    config = OutputConfig.model_validate({"formats": ["png"]})
    assert config.format is ImageFormat.PNG
