import pytest

from nttl.service import (
    ServiceError,
    install_service,
    render_unit,
    service_status,
    uninstall_service,
)


class FakeRunner:
    def __init__(self, outputs=None):
        self.calls: list[list[str]] = []
        self.outputs = outputs or {}

    def __call__(self, argv):
        self.calls.append(argv)
        key = " ".join(argv[-2:])
        return self.outputs.get(key, "")


def test_unit_declares_the_service_and_restart_policy():
    unit = render_unit(
        executable="/home/u/.local/bin/nttl", config="/home/u/.config/nttl/config.toml"
    )
    assert "[Unit]" in unit
    assert "Description=NTTL" in unit
    assert "ExecStart=/home/u/.local/bin/nttl web --config /home/u/.config/nttl/config.toml" in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=default.target" in unit


def test_unit_can_bind_a_host_and_port():
    unit = render_unit(executable="nttl", config="c.toml", host="0.0.0.0", port=9000)
    assert "--host 0.0.0.0" in unit
    assert "--port 9000" in unit


def test_unit_can_disable_the_live_view():
    assert "--no-live-view" in render_unit(executable="nttl", config="c.toml", live_view=False)


def test_install_writes_the_unit_and_enables_it(tmp_path):
    runner = FakeRunner()
    path = install_service(
        executable="nttl",
        config="c.toml",
        unit_dir=tmp_path,
        runner=runner,
        platform="linux",
    )
    assert path.name == "nttl.service"
    assert "ExecStart=nttl web" in path.read_text()
    commands = [" ".join(call) for call in runner.calls]
    assert "systemctl --user daemon-reload" in commands
    assert "systemctl --user enable --now nttl.service" in commands
    assert any(command.startswith("loginctl enable-linger") for command in commands)


def test_install_can_skip_linger(tmp_path):
    runner = FakeRunner()
    install_service(
        executable="nttl",
        config="c.toml",
        unit_dir=tmp_path,
        runner=runner,
        platform="linux",
        linger=False,
    )
    assert not any("loginctl" in " ".join(call) for call in runner.calls)


def test_install_is_rejected_outside_linux(tmp_path):
    with pytest.raises(ServiceError, match="installer"):
        install_service(executable="nttl", config="c.toml", unit_dir=tmp_path, platform="win32")


def test_uninstall_stops_disables_and_removes(tmp_path):
    runner = FakeRunner()
    install_service(
        executable="nttl", config="c.toml", unit_dir=tmp_path, runner=runner, platform="linux"
    )
    unit = tmp_path / "nttl.service"
    assert unit.exists()
    removed = uninstall_service(unit_dir=tmp_path, runner=runner, platform="linux")
    assert removed is True
    assert not unit.exists()
    commands = [" ".join(call) for call in runner.calls]
    assert "systemctl --user disable --now nttl.service" in commands


def test_uninstall_without_unit_reports_false(tmp_path):
    assert uninstall_service(unit_dir=tmp_path, runner=FakeRunner(), platform="linux") is False


def test_status_reports_installed_active_and_enabled(tmp_path):
    runner = FakeRunner({"is-active nttl.service": "active", "is-enabled nttl.service": "enabled"})
    install_service(
        executable="nttl", config="c.toml", unit_dir=tmp_path, runner=runner, platform="linux"
    )
    status = service_status(unit_dir=tmp_path, runner=runner, platform="linux")
    assert status["installed"] is True
    assert status["active"] is True
    assert status["enabled"] is True
    assert status["unit"].endswith("nttl.service")


def test_status_for_a_missing_unit(tmp_path):
    status = service_status(unit_dir=tmp_path, runner=FakeRunner(), platform="linux")
    assert status["installed"] is False
    assert status["active"] is False


def test_status_outside_linux_is_not_installed(tmp_path):
    status = service_status(unit_dir=tmp_path, runner=FakeRunner(), platform="darwin")
    assert status["installed"] is False
    assert "systemd" in (status["note"] or "")
