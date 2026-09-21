import time

import pytest

from nttl.config.models import AppConfig
from nttl.imaging.writers import ImageFormat
from nttl.server.state import AppState


def wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def app_config(tmp_path) -> AppConfig:
    config = AppConfig()
    config.capture.camera.backend = "simulated"
    config.capture.session_name = "test"
    config.capture.frame_count = 3
    config.capture.interval_s = 0.0
    config.capture.use_darks = False
    config.capture.camera.exposure_s = 0.01
    config.capture.output.directory = tmp_path / "sessions"
    config.capture.output.format = ImageFormat.JPEG
    config.darks_directory = tmp_path / "darks"
    config.preview_interval_s = 0.0
    return config


@pytest.fixture
def state(app_config, tmp_path):
    state = AppState(
        app_config,
        config_path=tmp_path / "config.toml",
        camera_options={"width": 64, "height": 64, "star_count": 10},
        live_view=False,
    )
    try:
        yield state
    finally:
        state.shutdown()
