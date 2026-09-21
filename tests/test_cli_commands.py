import json

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
                'formats = ["jpeg"]',
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
