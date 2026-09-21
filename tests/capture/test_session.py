import json

import numpy as np
import pytest

from nttl.capture.autoexposure import AutoExposureConfig
from nttl.capture.session import CaptureSession, SessionState
from nttl.config.models import CameraConfig, CaptureConfig, OutputConfig
from nttl.hal.errors import ExposureFailedError
from nttl.hal.simulated import SimulatedCamera
from nttl.imaging import ImageFormat


def make_camera(**kwargs):
    cam = SimulatedCamera(seed=4, width=64, height=64, star_count=15, **kwargs)
    cam.open()
    return cam


def make_config(tmp_path, **kwargs) -> CaptureConfig:
    base = dict(
        session_name="test",
        frame_count=3,
        interval_s=0.0,
        use_darks=False,
        camera=CameraConfig(exposure_s=1.0, gain=120.0),
        auto_exposure=AutoExposureConfig(enabled=False),
        output=OutputConfig(directory=tmp_path, format=ImageFormat.JPEG),
    )
    base.update(kwargs)
    return CaptureConfig(**base)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


def test_session_captures_requested_frames(tmp_path):
    clock = FakeClock()
    session = CaptureSession(make_camera(), make_config(tmp_path), sleep=clock.sleep, now=clock.now)
    status = session.run()
    assert status.state is SessionState.FINISHED
    assert status.frames_captured == 3
    assert len(list((tmp_path / "test").glob("*.jpg"))) == 3


def test_manifest_records_one_line_per_frame(tmp_path):
    clock = FakeClock()
    session = CaptureSession(make_camera(), make_config(tmp_path), sleep=clock.sleep, now=clock.now)
    session.run()
    lines = (tmp_path / "test" / "manifest.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3
    entry = json.loads(lines[0])
    assert entry["sequence"] == 1
    assert entry["exposure_s"] > 0
    assert entry["files"]["jpeg"].endswith(".jpg")
    assert "sensor_temp_c" in entry and "level" in entry


def test_session_resumes_numbering_from_manifest(tmp_path):
    clock = FakeClock()
    config = make_config(tmp_path)
    CaptureSession(make_camera(), config, sleep=clock.sleep, now=clock.now).run()
    status = CaptureSession(make_camera(), config, sleep=clock.sleep, now=clock.now).run()
    lines = (tmp_path / "test" / "manifest.jsonl").read_text().strip().splitlines()
    assert len(lines) == 6
    assert json.loads(lines[-1])["sequence"] == 6
    assert status.frames_captured == 3


def test_interval_is_respected_between_frames(tmp_path):
    clock = FakeClock()
    config = make_config(tmp_path, interval_s=10.0)
    CaptureSession(make_camera(), config, sleep=clock.sleep, now=clock.now).run()
    assert len(clock.slept) == 2
    assert all(0 < value <= 10.0 for value in clock.slept)


def test_stop_request_ends_session_early(tmp_path):
    clock = FakeClock()
    config = make_config(tmp_path, frame_count=100)
    session = CaptureSession(make_camera(), config, sleep=clock.sleep, now=clock.now)

    def on_event(status):
        if status.frames_captured == 2:
            session.request_stop()

    session.on_event = on_event
    status = session.run()
    assert status.state is SessionState.FINISHED
    assert status.frames_captured == 2


def test_duration_limit_stops_session(tmp_path):
    clock = FakeClock()
    config = make_config(tmp_path, frame_count=None, duration_s=25.0, interval_s=10.0)
    status = CaptureSession(make_camera(), config, sleep=clock.sleep, now=clock.now).run()
    assert status.frames_captured == 3


def test_auto_exposure_updates_settings(tmp_path):
    clock = FakeClock()
    config = make_config(
        tmp_path,
        frame_count=6,
        auto_exposure=AutoExposureConfig(
            enabled=True, target_level=0.3, min_exposure_s=0.01, max_exposure_s=20.0
        ),
    )
    config.camera.exposure_s = 0.02
    config.camera.gain = 0.0
    status = CaptureSession(make_camera(), config, sleep=clock.sleep, now=clock.now).run()
    assert status.exposure_s > 0.02
    assert status.frames_captured == 6


def test_exposure_errors_are_retried_and_counted(tmp_path):
    clock = FakeClock()
    camera = make_camera()
    original = camera.expose
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ExposureFailedError("usb glitch")
        return original(*args, **kwargs)

    camera.expose = flaky  # type: ignore[method-assign]
    status = CaptureSession(camera, make_config(tmp_path), sleep=clock.sleep, now=clock.now).run()
    assert status.frames_captured == 3
    assert status.frames_failed == 1
    assert status.state is SessionState.FINISHED


def test_session_aborts_after_consecutive_errors(tmp_path):
    clock = FakeClock()
    camera = make_camera()

    def always_fail(*args, **kwargs):
        raise ExposureFailedError("camera unplugged")

    camera.expose = always_fail  # type: ignore[method-assign]
    config = make_config(tmp_path, max_consecutive_errors=2)
    status = CaptureSession(camera, config, sleep=clock.sleep, now=clock.now).run()
    assert status.state is SessionState.ERROR
    assert status.frames_failed == 2
    assert "camera unplugged" in (status.last_error or "")


def test_dark_provider_is_used_when_enabled(tmp_path):
    clock = FakeClock()
    camera = make_camera(is_color=False)
    dark = np.full((64, 64), 100, dtype=np.uint16)
    requested = []

    def provider(metadata):
        requested.append(metadata.exposure_s)
        return dark

    config = make_config(tmp_path, use_darks=True)
    status = CaptureSession(
        camera, config, sleep=clock.sleep, now=clock.now, dark_provider=provider
    ).run()
    assert len(requested) == 3
    assert status.dark_applied is True


def test_events_are_emitted_for_each_frame(tmp_path):
    clock = FakeClock()
    seen = []
    session = CaptureSession(
        make_camera(),
        make_config(tmp_path),
        sleep=clock.sleep,
        now=clock.now,
        on_event=lambda status: seen.append(status.frames_captured),
    )
    session.run()
    assert seen == [1, 2, 3]


def test_latest_preview_is_available(tmp_path):
    clock = FakeClock()
    session = CaptureSession(make_camera(), make_config(tmp_path), sleep=clock.sleep, now=clock.now)
    session.run()
    assert session.latest_preview is not None
    assert session.latest_preview.dtype == np.uint8


def test_session_directory_is_created_once(tmp_path):
    clock = FakeClock()
    config = make_config(tmp_path)
    session = CaptureSession(make_camera(), config, sleep=clock.sleep, now=clock.now)
    assert session.directory == tmp_path / "test"
    session.run()
    assert session.directory.is_dir()


def test_run_twice_is_rejected(tmp_path):
    clock = FakeClock()
    session = CaptureSession(make_camera(), make_config(tmp_path), sleep=clock.sleep, now=clock.now)
    session.run()
    with pytest.raises(RuntimeError):
        session.run()
