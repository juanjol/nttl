import numpy as np
import pytest

from nttl.hal import BayerPattern, ControlName, Roi
from nttl.hal.errors import CameraNotOpenError, ControlNotSupportedError


def test_info_is_consistent(camera):
    info = camera.info
    assert info.name
    assert info.max_width > 0 and info.max_height > 0
    assert info.bit_depth in (8, 12, 14, 16)
    assert 1 in info.supported_bins
    if info.is_color:
        assert info.bayer_pattern is not BayerPattern.NONE
    else:
        assert info.bayer_pattern is BayerPattern.NONE


def test_controls_expose_exposure_and_gain(camera):
    controls = camera.controls()
    assert ControlName.EXPOSURE in controls
    assert ControlName.GAIN in controls
    exposure = controls[ControlName.EXPOSURE]
    assert exposure.min_value < exposure.max_value
    assert exposure.min_value <= exposure.default <= exposure.max_value


def test_set_control_roundtrip(camera):
    camera.set_control(ControlName.GAIN, 120)
    assert camera.get_control(ControlName.GAIN) == pytest.approx(120, abs=1)


def test_set_control_clamps_to_range(camera):
    limit = camera.controls()[ControlName.GAIN].max_value
    camera.set_control(ControlName.GAIN, limit * 10)
    assert camera.get_control(ControlName.GAIN) == pytest.approx(limit, abs=1)


def test_unknown_control_raises(camera):
    with pytest.raises(ControlNotSupportedError):
        camera.set_control("not_a_control", 1)


def test_expose_returns_frame_with_metadata(camera):
    frame = camera.expose(0.5)
    info = camera.info
    assert frame.data.shape == (info.max_height, info.max_width)
    assert frame.data.dtype == np.uint16
    assert frame.metadata.exposure_s == pytest.approx(0.5)
    assert frame.metadata.camera_name == info.name
    assert frame.metadata.timestamp_utc.tzinfo is not None
    assert frame.metadata.bayer_pattern is info.bayer_pattern
    assert frame.metadata.sequence == 0


def test_sequence_increments(camera):
    assert camera.expose(0.01).metadata.sequence == 0
    assert camera.expose(0.01).metadata.sequence == 1


def test_longer_exposure_collects_more_signal(camera):
    short = camera.expose(0.05).data.mean()
    long = camera.expose(1.0).data.mean()
    assert long > short


def test_higher_gain_collects_more_signal(camera):
    camera.set_control(ControlName.GAIN, 0)
    low = camera.expose(0.2).data.mean()
    camera.set_control(ControlName.GAIN, 300)
    high = camera.expose(0.2).data.mean()
    assert high > low


def test_roi_and_binning_change_frame_shape(camera):
    info = camera.info
    roi = Roi(x=0, y=0, width=info.max_width // 2, height=info.max_height // 2, bin=2)
    camera.set_roi(roi)
    frame = camera.expose(0.05)
    assert frame.data.shape == (roi.height // 2, roi.width // 2)
    assert frame.metadata.bin == 2
    assert camera.get_roi() == roi


def test_sensor_temperature_is_reported(camera):
    frame = camera.expose(0.05)
    assert -80.0 < frame.metadata.sensor_temp_c < 80.0


def test_operations_require_open_camera(camera):
    camera.close()
    with pytest.raises(CameraNotOpenError):
        camera.expose(0.05)
