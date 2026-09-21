import pytest

from nttl.hal.errors import CameraNotFoundError
from nttl.hal.registry import available_backends, list_cameras, open_camera


def test_simulated_backend_is_available():
    assert "simulated" in available_backends()
    assert "asi" in available_backends()


def test_open_simulated_camera():
    camera = open_camera("simulated")
    try:
        assert camera.is_open
        assert camera.info.backend == "simulated"
    finally:
        camera.close()


def test_open_simulated_camera_accepts_options():
    camera = open_camera("simulated", width=320, height=240, is_color=False)
    try:
        assert (camera.info.max_width, camera.info.max_height) == (320, 240)
        assert camera.info.is_color is False
    finally:
        camera.close()


def test_unknown_backend_raises():
    with pytest.raises(CameraNotFoundError):
        open_camera("nikon")


def test_list_cameras_for_simulated_backend():
    cameras = list_cameras("simulated")
    assert len(cameras) == 1
    assert cameras[0].backend == "simulated"


def test_asi_backend_reports_missing_sdk_clearly(monkeypatch):
    from nttl.hal import registry

    def boom(*args, **kwargs):
        from nttl.hal.errors import SdkNotAvailableError

        raise SdkNotAvailableError("libASICamera2 not found")

    monkeypatch.setitem(registry._BACKENDS, "asi", boom)
    with pytest.raises(Exception, match="libASICamera2"):
        open_camera("asi")
