"""Small helpers that talk to the desktop environment."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def open_in_file_manager(path: str | Path) -> None:
    """Show a directory in the desktop file manager, creating it when missing."""
    target = Path(path)
    if not target.exists() and not target.suffix:
        target.mkdir(parents=True, exist_ok=True)
    argv = _file_manager_argv(str(target))
    # A windowless build has no standard handles to inherit.
    subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _file_manager_argv(target: str) -> list[str]:
    if sys.platform.startswith("win"):
        return ["explorer", target]
    if sys.platform == "darwin":
        return ["open", target]
    return ["xdg-open", target]
