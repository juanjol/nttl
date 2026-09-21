import numpy as np
import pytest

from nttl.hal import BayerPattern, ControlName, Roi
from nttl.hal.asi.camera import AsiCamera, list_asi_cameras, open_asi_camera
from nttl.hal.errors import (
    CameraNotFoundError,
    ControlNotSupportedError,
    ExposureFailedError,
    InvalidRoiError,
)
from tests.hal.asi.fake_sdk import FakeAsiSdk


def camera(**kwargs) -> AsiCamera:
    sdk = FakeAsiSdk(**kwargs)
    cam = AsiCamera(sdk, sdk.camera_info(0))
    cam.open()
    return cam


def test_info_is_translated_from_the_sdk():
    cam = camera()
    assert cam.info.backend == "asi"
    assert cam.info.name.startswith("ASI")
    assert cam.info.bayer_pattern is BayerPattern.RGGB
    assert cam.info.has_cooler is True


def test_mono_camera_reports_no_bayer_pattern():
    assert camera(is_color=False).info.bayer_pattern is BayerPattern.NONE


def test_exposure_control_is_reported_in_seconds():
    controls = camera().controls()
    assert controls[ControlName.EXPOSURE].unit == "s"
    assert controls[ControlName.EXPOSURE].min_value == pytest.approx(0.000032)
    assert controls[ControlName.EXPOSURE].max_value == pytest.approx(3600.0)


def test_exposure_roundtrip_converts_microseconds():
    cam = camera()
    cam.set_control(ControlName.EXPOSURE, 2.5)
    assert cam.get_control(ControlName.EXPOSURE) == pytest.approx(2.5)


def test_gain_roundtrip():
    cam = camera()
    cam.set_control(ControlName.GAIN, 300)
    assert cam.get_control(ControlName.GAIN) == pytest.approx(300)


def test_unknown_control_raises():
    with pytest.raises(ControlNotSupportedError):
        camera().set_control("hyperdrive", 1)


def test_expose_returns_a_16_bit_frame():
    cam = camera()
    frame = cam.expose(0.05)
    assert frame.data.dtype == np.uint16
    assert frame.data.shape == (cam.info.max_height, cam.info.max_width)
    assert frame.metadata.exposure_s == pytest.approx(0.05)
    assert frame.metadata.camera_name == cam.info.name
    assert frame.metadata.sequence == 0


def test_dark_flag_is_recorded():
    assert camera().expose(0.05, dark=True).metadata.is_dark is True


def test_sensor_temperature_is_scaled():
    assert -80 < camera().expose(0.01).metadata.sensor_temp_c < 80


def test_roi_and_binning_are_pushed_to_the_sdk():
    sdk = FakeAsiSdk(width=64, height=64)
    cam = AsiCamera(sdk, sdk.camera_info(0))
    cam.open()
    cam.set_roi(Roi(x=0, y=0, width=32, height=32, bin=2))
    frame = cam.expose(0.01)
    assert frame.data.shape == (16, 16)
    assert "roi:16x16/2" in sdk.calls


def test_roi_must_respect_the_sdk_alignment():
    cam = camera()
    with pytest.raises(InvalidRoiError):
        cam.set_roi(Roi(x=0, y=0, width=12, height=12, bin=1))
    with pytest.raises(InvalidRoiError):
        cam.set_roi(Roi(x=0, y=0, width=16, height=9, bin=1))


def test_roi_outside_the_sensor_is_rejected():
    with pytest.raises(InvalidRoiError):
        camera().set_roi(Roi(x=0, y=0, width=2048, height=64, bin=1))


def test_failed_exposure_raises():
    with pytest.raises(ExposureFailedError):
        camera(fail_exposure=True).expose(0.01)


def test_cooler_requires_hardware():
    with pytest.raises(ControlNotSupportedError):
        camera(has_cooler=False).set_cooler(enabled=True, target_c=-10)


def test_cooler_is_forwarded():
    cam = camera()
    cam.set_cooler(enabled=True, target_c=-15)
    assert cam.info.has_cooler


def test_open_camera_selects_by_id_or_name():
    sdk = FakeAsiSdk(cameras=2)
    by_index = open_asi_camera("1", sdk=sdk)
    assert by_index.info.camera_id == "1"
    by_name = open_asi_camera("ASI294MC Pro", sdk=sdk)
    assert by_name.info.name == "ASI294MC Pro"


def test_open_camera_without_match_raises():
    sdk = FakeAsiSdk()
    with pytest.raises(CameraNotFoundError, match="ASI999"):
        open_asi_camera("ASI999", sdk=sdk)


def test_open_camera_without_cameras_raises():
    with pytest.raises(CameraNotFoundError):
        open_asi_camera(sdk=FakeAsiSdk(cameras=0))


def test_list_cameras_returns_hal_info():
    infos = list_asi_cameras(sdk=FakeAsiSdk(cameras=2))
    assert len(infos) == 2
    assert all(info.backend == "asi" for info in infos)


def test_close_releases_the_camera():
    sdk = FakeAsiSdk()
    cam = AsiCamera(sdk, sdk.camera_info(0))
    cam.open()
    cam.close()
    assert cam.is_open is False
    assert "close" in sdk.calls
