from pathlib import Path

import pytest

from nttl.hal.asi._bindings import AsiError, AsiSdk, ControlType, find_sdk
from nttl.hal.errors import SdkNotAvailableError


def test_env_variable_takes_precedence(monkeypatch, tmp_path):
    library = tmp_path / "libASICamera2.so"
    library.write_bytes(b"")
    monkeypatch.setenv("NTTL_ASI_SDK", str(library))
    assert find_sdk() == library


def test_explicit_path_wins(monkeypatch, tmp_path):
    library = tmp_path / "custom.so"
    library.write_bytes(b"")
    monkeypatch.setenv("NTTL_ASI_SDK", "/does/not/exist.so")
    assert find_sdk(library) == library


def test_missing_sdk_returns_none(monkeypatch):
    for name in ("NTTL_ASI_SDK", "ASI_SDK_LIB", "ZWO_ASI_LIB"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("nttl.hal.asi._bindings.find_library", lambda name: None)
    monkeypatch.setattr("nttl.hal.asi._bindings._LINUX_CANDIDATES", ())
    monkeypatch.setattr("nttl.hal.asi._bindings._WINDOWS_CANDIDATES", ())
    assert find_sdk() is None


def test_sdk_reports_a_helpful_error_when_absent(monkeypatch):
    monkeypatch.setattr("nttl.hal.asi._bindings.find_sdk", lambda path=None: None)
    with pytest.raises(SdkNotAvailableError, match="NTTL_ASI_SDK"):
        AsiSdk()


def test_sdk_reports_load_failures(monkeypatch, tmp_path):
    broken = tmp_path / "libASICamera2.so"
    broken.write_text("not a library")
    monkeypatch.setattr("nttl.hal.asi._bindings.find_sdk", lambda path=None: broken)
    with pytest.raises(SdkNotAvailableError):
        AsiSdk()


def test_error_messages_are_descriptive():
    error = AsiError("ASIOpenCamera", 5)
    assert "camera removed" in str(error)
    assert error.code == 5


def test_control_types_match_the_vendor_header():
    assert ControlType.GAIN == 0
    assert ControlType.EXPOSURE == 1
    assert ControlType.TEMPERATURE == 8
    assert ControlType.COOLER_ON == 17


@pytest.mark.hardware
def test_real_sdk_lists_cameras():
    path = find_sdk()
    if path is None:
        pytest.skip("ASI SDK not installed")
    sdk = AsiSdk(Path(path))
    assert sdk.camera_count() >= 0
