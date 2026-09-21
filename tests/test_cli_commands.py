import json

import pytest
from typer.testing import CliRunner

from nttl.cli import app

# A wide, dumb terminal keeps rich from truncating option names and paths.
runner = CliRunner(env={"COLUMNS": "200", "TERM": "dumb", "NO_COLOR": "1"})


def config_file(tmp_path) -> str:
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                f'darks_directory = "{(tmp_path / "darks").as_posix()}"',
                "[capture]",
                'session_name = "cli"',
                "use_darks = false",
                "[capture.camera]",
                'backend = "simulated"',
                "exposure_s = 0.01",
                "[capture.output]",
                f'directory = "{(tmp_path / "sessions").as_posix()}"',
                'format = "jpeg"',
            ]
        ),
        encoding="utf-8",
    )
    return str(path)


def test_capture_command_writes_frames(tmp_path):
    result = runner.invoke(
        app, ["capture", "--config", config_file(tmp_path), "--frames", "2", "--sim-size", "64"]
    )
    assert result.exit_code == 0, result.output
    manifest = tmp_path / "sessions" / "cli" / "manifest.jsonl"
    assert len(manifest.read_text().strip().splitlines()) == 2
    assert "2" in result.output


def test_capture_command_accepts_overrides(tmp_path):
    result = runner.invoke(
        app,
        [
            "capture",
            "--config",
            config_file(tmp_path),
            "--frames",
            "1",
            "--session",
            "custom",
            "--exposure",
            "0.02",
            "--gain",
            "40",
            "--sim-size",
            "64",
        ],
    )
    assert result.exit_code == 0, result.output
    entry = json.loads(
        (tmp_path / "sessions" / "custom" / "manifest.jsonl").read_text().splitlines()[0]
    )
    assert entry["exposure_s"] == 0.02
    assert entry["gain"] == 40


def test_darks_command_builds_library(tmp_path):
    result = runner.invoke(
        app,
        [
            "darks",
            "--config",
            config_file(tmp_path),
            "--exposure",
            "0.01",
            "--gain",
            "0",
            "--frames",
            "3",
            "--sim-size",
            "64",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "darks" / "index.json").exists()


def test_config_show_prints_current_settings(tmp_path):
    result = runner.invoke(app, ["config", "--config", config_file(tmp_path)])
    assert result.exit_code == 0
    assert "cli" in result.output


def test_compile_reports_missing_session(tmp_path):
    result = runner.invoke(app, ["compile", "ghost", "--config", config_file(tmp_path)])
    assert result.exit_code != 0
    assert "ghost" in result.output


def test_compile_builds_video_when_ffmpeg_is_available(tmp_path):
    from nttl.video.ffmpeg import find_ffmpeg

    if find_ffmpeg() is None:
        return
    runner.invoke(
        app, ["capture", "--config", config_file(tmp_path), "--frames", "4", "--sim-size", "64"]
    )
    result = runner.invoke(
        app, ["compile", "cli", "--config", config_file(tmp_path), "--fps", "10"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "sessions" / "cli" / "cli.mp4").exists()


def test_web_help_lists_options():
    result = runner.invoke(app, ["web", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output


def test_gui_help_is_available():
    assert runner.invoke(app, ["gui", "--help"]).exit_code == 0


def test_tray_help_is_available():
    result = runner.invoke(app, ["tray", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.output


def test_service_subcommands_are_listed():
    result = runner.invoke(app, ["service", "--help"])
    assert result.exit_code == 0
    for command in ("install", "uninstall", "status"):
        assert command in result.output


def test_service_status_runs_on_any_platform():
    result = runner.invoke(app, ["service", "status"])
    assert result.exit_code == 0
    assert "installed" in result.output


def test_tray_entry_point_injects_the_subcommand(monkeypatch):
    import sys

    from nttl.cli import tray_entry

    monkeypatch.setattr(sys, "argv", ["nttl-tray", "--help"])
    with pytest.raises(SystemExit) as exit_info:
        tray_entry()
    assert exit_info.value.code == 0
    assert sys.argv[1] == "tray"


def test_backend_override_uses_the_simulated_camera(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                f'darks_directory = "{(tmp_path / "darks").as_posix()}"',
                "[capture]",
                'session_name = "sim"',
                "use_darks = false",
                "[capture.camera]",
                'backend = "asi"',
                "exposure_s = 0.01",
                "[capture.output]",
                f'directory = "{(tmp_path / "sessions").as_posix()}"',
                'format = "jpeg"',
            ]
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "capture",
            "--config",
            str(path),
            "--frames",
            "1",
            "--backend",
            "simulated",
            "--sim-size",
            "64",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "sessions" / "sim" / "manifest.jsonl").exists()


def test_missing_asi_sdk_is_reported_clearly(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[capture.camera]\nbackend = "asi"\n', encoding="utf-8")
    result = runner.invoke(app, ["capture", "--config", str(path), "--frames", "1"])
    assert result.exit_code != 0
    assert "ASI" in str(result.exception) or "ASI" in result.output


def tray_config(tmp_path) -> str:
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                f'darks_directory = "{(tmp_path / "darks").as_posix()}"',
                "[capture]",
                "use_darks = false",
                "[capture.camera]",
                'backend = "simulated"',
                "exposure_s = 0.01",
                "[capture.output]",
                f'directory = "{(tmp_path / "sessions").as_posix()}"',
                'format = "jpeg"',
                "[web]",
                "port = 8788",
            ]
        ),
        encoding="utf-8",
    )
    return str(path)


def test_tray_runs_without_standard_streams(tmp_path, monkeypatch):
    """A windowless build has no stdout, which used to break uvicorn logging."""
    import sys

    import uvicorn

    import nttl.tray as tray_module

    captured: dict[str, object] = {}
    original_config = uvicorn.Config

    def record_config(*args, **kwargs):
        captured.update(kwargs)
        return original_config(*args, **kwargs)

    class DummyServer:
        def __init__(self, config):
            self.config = config
            self.should_exit = False

        def run(self):
            captured["served"] = True

    monkeypatch.setattr(uvicorn, "Config", record_config)
    monkeypatch.setattr(uvicorn, "Server", DummyServer)
    monkeypatch.setattr(tray_module, "run_tray", lambda state, **kwargs: None)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    result = runner.invoke(app, ["tray", "--config", tray_config(tmp_path), "--no-open"])

    assert result.exit_code == 0, result.output
    assert captured["log_config"] is None
    assert (tmp_path / "state" / "nttl" / "logs" / "nttl.log").exists()


def test_tray_starts_in_a_process_without_streams(tmp_path):
    """Reproduces the windowless build, where sys.stdout and sys.stderr are None."""
    import os
    import subprocess
    import sys
    import textwrap

    sentinel = tmp_path / "started.txt"
    child = textwrap.dedent(
        f"""
        import pathlib, sys
        sys.stdout = None
        sys.stderr = None

        import uvicorn

        class DummyServer:
            def __init__(self, config):
                self.config = config
                self.should_exit = False

            def run(self):
                pass

        uvicorn.Server = DummyServer

        import nttl.tray
        nttl.tray.run_tray = lambda state, **kwargs: None

        from nttl.cli import app

        try:
            app(["tray", "--config", {str(tray_config(tmp_path))!r}, "--no-open"])
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise
        pathlib.Path({str(sentinel)!r}).write_text("ok")
        """
    )
    environment = dict(os.environ, XDG_STATE_HOME=str(tmp_path / "state"))
    result = subprocess.run(
        [sys.executable, "-c", child], capture_output=True, text=True, env=environment
    )
    assert result.returncode == 0, result.stderr
    assert sentinel.exists()
    assert (tmp_path / "state" / "nttl" / "logs" / "nttl.log").exists()
