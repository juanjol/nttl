import numpy as np
import pytest

from nttl.config.store import load_config
from nttl.hal.errors import ControlNotSupportedError
from nttl.video.jobs import JobState
from tests.server.conftest import wait_for


def test_camera_stays_disconnected_until_asked(state):
    assert state.camera_connected is False
    assert state.camera_state()["connected"] is False


def test_camera_connects_on_request_and_reports_state(state):
    state.connect_camera()
    snapshot = state.camera_state()
    assert state.camera_connected is True
    assert snapshot["connected"] is True
    assert snapshot["info"]["backend"] == "simulated"
    assert "exposure" in snapshot["controls"]
    assert snapshot["values"]["gain"] >= 0


def test_disconnecting_releases_the_camera(state):
    state.connect_camera()
    state.disconnect_camera()
    assert state.camera_connected is False


def test_set_control_updates_value(state):
    state.set_control("gain", 200)
    assert state.camera_state()["values"]["gain"] == pytest.approx(200, abs=1)


def test_unknown_control_raises(state):
    with pytest.raises(ControlNotSupportedError):
        state.set_control("warp_drive", 1)


def test_update_config_merges_and_persists(state, tmp_path):
    updated = state.update_config({"video": {"fps": 48}, "capture": {"session_name": "aralar"}})
    assert updated.video.fps == 48
    assert updated.capture.session_name == "aralar"
    assert updated.capture.frame_count == 3
    assert load_config(tmp_path / "config.toml").video.fps == 48


def test_invalid_config_patch_is_rejected(state):
    with pytest.raises(ValueError):
        state.update_config({"video": {"fps": 0}})


def test_session_runs_to_completion(state):
    state.start_session()
    assert wait_for(lambda: state.session_status()["state"] == "finished")
    assert state.session_status()["frames_captured"] == 3
    assert state.preview_jpeg() is not None


def test_session_cannot_start_twice(state):
    state.config.capture.frame_count = 200
    state.start_session()
    with pytest.raises(RuntimeError):
        state.start_session()
    state.stop_session()
    assert wait_for(lambda: state.session_status()["state"] == "finished")


def test_stop_session_ends_capture(state):
    state.config.capture.frame_count = 500
    state.start_session()
    assert wait_for(lambda: state.session_status()["frames_captured"] >= 1)
    state.stop_session()
    assert wait_for(lambda: state.session_status()["state"] == "finished")
    assert state.session_status()["frames_captured"] < 500


def test_session_overrides_are_applied(state):
    state.start_session({"session_name": "override", "frame_count": 1})
    assert wait_for(lambda: state.session_status()["state"] == "finished")
    assert state.session_status()["session_name"] == "override"
    assert state.config.capture.session_name == "test"


def test_sessions_are_listed_with_frame_counts(state):
    state.start_session()
    assert wait_for(lambda: state.session_status()["state"] == "finished")
    sessions = state.list_sessions()
    assert sessions[0]["name"] == "test"
    assert sessions[0]["frames"] == 3


def test_compile_job_uses_manifest(state):
    state.start_session()
    assert wait_for(lambda: state.session_status()["state"] == "finished")
    calls = {}

    def fake_compile(manifest, output, config, **kwargs):
        calls["manifest"] = manifest
        calls["output"] = output
        reporter = kwargs.get("on_progress")
        if reporter:
            reporter(3, 3)
        return output

    state.compile_fn = fake_compile
    job = state.submit_compile("test")
    assert wait_for(lambda: state.jobs.get(job.id).state is JobState.FINISHED)
    assert calls["manifest"].name == "manifest.jsonl"
    assert str(calls["output"]).endswith(".mp4")


def test_compile_unknown_session_raises(state):
    with pytest.raises(FileNotFoundError):
        state.submit_compile("ghost")


def test_dark_build_job_creates_library_entry(state):
    job = state.build_darks(exposure_s=0.01, gain=0.0, frames=3)
    assert wait_for(lambda: state.jobs.get(job.id).state is JobState.FINISHED)
    darks = state.darks()
    assert len(darks) == 1
    assert darks[0]["frames"] == 3


def test_dark_library_is_used_by_sessions_when_enabled(state):
    camera_config = state.config.capture.camera
    job = state.build_darks(exposure_s=camera_config.exposure_s, gain=camera_config.gain, frames=3)
    assert wait_for(lambda: state.jobs.get(job.id).state is JobState.FINISHED)
    state.config.capture.use_darks = True
    state.start_session({"frame_count": 1})
    assert wait_for(lambda: state.session_status()["state"] == "finished")
    assert state.session_status()["dark_applied"] is True


def test_delete_dark_removes_entry(state):
    job = state.build_darks(exposure_s=0.01, gain=0.0, frames=2)
    assert wait_for(lambda: state.jobs.get(job.id).state is JobState.FINISHED)
    name = state.darks()[0]["name"]
    assert state.delete_dark(name) is True
    assert state.darks() == []
    assert state.delete_dark("missing.fits") is False


def test_snapshot_contains_every_section(state):
    snapshot = state.snapshot()
    assert set(snapshot) >= {"session", "camera", "scheduler", "jobs", "ffmpeg", "config"}


def test_live_view_updates_preview(app_config, tmp_path):
    from nttl.server.state import AppState

    state = AppState(
        app_config,
        camera_options={"width": 32, "height": 32, "star_count": 5},
        live_view=True,
    )
    try:
        assert wait_for(lambda: state.preview_jpeg() is not None)
        assert isinstance(state.preview_jpeg(), bytes)
        assert state.latest_stats is not None
    finally:
        state.shutdown()


def test_preview_is_scaled_to_configured_width(state):
    state.config.preview_max_width = 16
    state.start_session({"frame_count": 1})
    assert wait_for(lambda: state.session_status()["state"] == "finished")
    import cv2

    decoded = cv2.imdecode(np.frombuffer(state.preview_jpeg(), np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[1] == 16
