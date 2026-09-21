from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

UNIT_NAME = "nttl.service"

Runner = Callable[[list[str]], str]

_TEMPLATE = """[Unit]
Description=NTTL nighttime timelapse
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={command}
Restart=on-failure
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=default.target
"""


class ServiceError(Exception):
    pass


def default_unit_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "systemd" / "user"


def _run(argv: list[str]) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    return (result.stdout or result.stderr).strip()


def render_unit(
    *,
    executable: str | Path,
    config: str | Path,
    host: str | None = None,
    port: int | None = None,
    live_view: bool = True,
) -> str:
    command = f"{executable} web --config {config}"
    if host:
        command += f" --host {host}"
    if port:
        command += f" --port {port}"
    if not live_view:
        command += " --no-live-view"
    return _TEMPLATE.format(command=command)


def _require_linux(platform: str) -> None:
    if not platform.startswith("linux"):
        raise ServiceError(
            "user services are a systemd feature. On Windows use the installer option that "
            "starts NTTL at login, on macOS use a launchd agent"
        )


def install_service(
    *,
    executable: str | Path,
    config: str | Path,
    host: str | None = None,
    port: int | None = None,
    live_view: bool = True,
    unit_dir: Path | None = None,
    runner: Runner | None = None,
    platform: str | None = None,
    linger: bool = True,
) -> Path:
    _require_linux(platform or sys.platform)
    execute = runner or _run
    directory = unit_dir or default_unit_dir()
    directory.mkdir(parents=True, exist_ok=True)
    unit = directory / UNIT_NAME
    unit.write_text(
        render_unit(
            executable=executable, config=config, host=host, port=port, live_view=live_view
        ),
        encoding="utf-8",
    )
    execute(["systemctl", "--user", "daemon-reload"])
    execute(["systemctl", "--user", "enable", "--now", UNIT_NAME])
    if linger:
        execute(["loginctl", "enable-linger", os.environ.get("USER", "")])
    return unit


def uninstall_service(
    *,
    unit_dir: Path | None = None,
    runner: Runner | None = None,
    platform: str | None = None,
) -> bool:
    _require_linux(platform or sys.platform)
    execute = runner or _run
    unit = (unit_dir or default_unit_dir()) / UNIT_NAME
    if not unit.exists():
        return False
    execute(["systemctl", "--user", "disable", "--now", UNIT_NAME])
    unit.unlink()
    execute(["systemctl", "--user", "daemon-reload"])
    return True


def service_status(
    *,
    unit_dir: Path | None = None,
    runner: Runner | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    current = platform or sys.platform
    unit = (unit_dir or default_unit_dir()) / UNIT_NAME
    if not current.startswith("linux"):
        return {
            "installed": False,
            "active": False,
            "enabled": False,
            "unit": str(unit),
            "note": "systemd user services are only available on Linux",
        }
    execute = runner or _run
    if not unit.exists():
        return {
            "installed": False,
            "active": False,
            "enabled": False,
            "unit": str(unit),
            "note": None,
        }
    active = execute(["systemctl", "--user", "is-active", UNIT_NAME])
    enabled = execute(["systemctl", "--user", "is-enabled", UNIT_NAME])
    return {
        "installed": True,
        "active": active == "active",
        "enabled": enabled in {"enabled", "enabled-runtime"},
        "unit": str(unit),
        "note": None,
    }
