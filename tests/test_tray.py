from types import SimpleNamespace

import pytest
from PIL import Image

from nttl.tray import TrayController, TrayState, render_icon


class FakeState:
    def __init__(self, session_state="idle", error=None, port=8765):
        self._session = {"state": session_state, "last_error": error, "frames_captured": 7}
        self.started = 0
        self.stopped = 0
        self.shutdowns = 0
        self.config = SimpleNamespace(
            web=SimpleNamespace(host="127.0.0.1", port=port),
            capture=SimpleNamespace(output=SimpleNamespace(directory="/tmp/sessions")),
        )

    def session_status(self):
        return self._session

    def start_session(self, overrides=None):
        self.started += 1
        self._session["state"] = "running"
        return self._session

    def stop_session(self):
        self.stopped += 1
        self._session["state"] = "finished"

    def shutdown(self):
        self.shutdowns += 1


def test_state_is_idle_when_no_session_runs():
    controller = TrayController(FakeState())
    assert controller.state() is TrayState.IDLE


def test_state_is_capturing_while_running():
    assert TrayController(FakeState("running")).state() is TrayState.CAPTURING


def test_state_is_error_when_the_session_failed():
    controller = TrayController(FakeState("error", error="camera unplugged"))
    assert controller.state() is TrayState.ERROR


def test_tooltip_reports_state_and_frames():
    tooltip = TrayController(FakeState("running")).tooltip()
    assert "NTTL" in tooltip
    assert "7" in tooltip
    assert "127.0.0.1:8765" in tooltip


def test_url_uses_the_configured_web_settings():
    assert TrayController(FakeState(port=9001)).url() == "http://127.0.0.1:9001"


def test_url_replaces_a_wildcard_host():
    state = FakeState()
    state.config.web.host = "0.0.0.0"
    assert TrayController(state).url() == "http://127.0.0.1:8765"


def test_menu_items_depend_on_the_session_state():
    idle = TrayController(FakeState())
    assert [item.label for item in idle.menu_items()][:3] == [
        "Open interface",
        "Start capture",
        "Open sessions folder",
    ]
    running = TrayController(FakeState("running"))
    assert "Stop capture" in [item.label for item in running.menu_items()]
    assert "Start capture" not in [item.label for item in running.menu_items()]


def test_menu_always_offers_quit():
    assert TrayController(FakeState()).menu_items()[-1].label == "Quit"


def test_start_and_stop_actions_reach_the_state():
    state = FakeState()
    controller = TrayController(state)
    controller.start_capture()
    assert state.started == 1
    controller.stop_capture()
    assert state.stopped == 1


def test_start_capture_reports_errors_without_raising():
    state = FakeState()

    def boom(overrides=None):
        raise RuntimeError("already running")

    state.start_session = boom
    controller = TrayController(state)
    controller.start_capture()
    assert "already running" in (controller.last_error or "")


def test_quit_shuts_the_state_down_and_signals_exit():
    state = FakeState()
    controller = TrayController(state)
    controller.quit()
    assert state.shutdowns == 1
    assert controller.should_exit is True


def test_open_interface_uses_the_injected_browser():
    opened = []
    controller = TrayController(FakeState(), open_url=opened.append)
    controller.open_interface()
    assert opened == ["http://127.0.0.1:8765"]


def test_open_sessions_folder_uses_the_injected_opener():
    opened = []
    controller = TrayController(FakeState(), open_path=opened.append)
    controller.open_sessions_folder()
    assert opened == ["/tmp/sessions"]


@pytest.mark.parametrize("state", list(TrayState))
def test_icons_are_distinct_images_per_state(state):
    image = render_icon(state)
    assert isinstance(image, Image.Image)
    assert image.size == (64, 64)


def test_icon_colours_differ_between_states():
    colours = {render_icon(state).getpixel((32, 48)) for state in TrayState}
    assert len(colours) == len(TrayState)


def test_run_tray_reports_the_missing_extra(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pystray":
            raise ImportError("no module named pystray")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="nttl\\[tray\\]"):
        from nttl.tray import run_tray

        run_tray(FakeState())


def test_menu_includes_the_window_entry_only_when_available():
    with_window = TrayController(FakeState(), open_window=lambda url: None)
    assert "Open desktop window" in [item.label for item in with_window.menu_items()]
    assert with_window.has_window is True
    assert TrayController(FakeState()).has_window is False


def test_file_manager_launch_does_not_inherit_handles(monkeypatch, tmp_path):
    import subprocess

    from nttl.tray import open_in_file_manager

    captured = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return None

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    open_in_file_manager(str(tmp_path))
    assert str(tmp_path) in captured["argv"]
    assert captured["kwargs"]["stdout"] is subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] is subprocess.DEVNULL
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
