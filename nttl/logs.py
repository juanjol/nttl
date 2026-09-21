"""Logging and stream plumbing for windowless builds.

A PyInstaller application built without a console has no standard streams, so
anything that touches sys.stdout, from rich to the logging configuration of
uvicorn, fails. Redirect both streams to a log file instead, which also gives
beta testers something to attach to a report.
"""

from __future__ import annotations

import io
import logging
import os
import sys
import threading
from collections import deque
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, TextIO

LOG_FILE_NAME = "nttl.log"
_MAX_BYTES = 2_000_000
_BACKUPS = 3
_MARKER = "nttl-file-log"


def log_directory() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "nttl" / "logs"


def default_log_path() -> Path:
    return log_directory() / LOG_FILE_NAME


def ensure_streams(log_path: Path | str | None = None) -> Path | None:
    """Give the process usable streams, returning the log file when one is used."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    path = Path(log_path) if log_path is not None else default_log_path()
    handle: TextIO
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a", encoding="utf-8", buffering=1)
    except OSError:
        handle = io.StringIO()
        path = None  # type: ignore[assignment]
    if sys.stdout is None:
        sys.stdout = handle
    if sys.stderr is None:
        sys.stderr = handle
    return path


def configure_file_logging(
    path: Path | str | None, level: int = logging.INFO
) -> logging.Handler | None:
    """Send log records to a rotating file, at most once per process."""
    if path is None:
        return None
    target = Path(path).resolve()
    root = logging.getLogger()
    for existing in list(root.handlers):
        if not getattr(existing, _MARKER, False):
            continue
        if Path(getattr(existing, "baseFilename", "")) == target:
            return existing
        root.removeHandler(existing)
        existing.close()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            target, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
        )
    except OSError:
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    setattr(handler, _MARKER, True)
    root.addHandler(handler)
    if root.level > level or root.level == logging.NOTSET:
        root.setLevel(level)
    return handler


class MemoryLogHandler(logging.Handler):
    """Keep the last records in memory so the interface can show them live."""

    def __init__(self, capacity: int = 1000) -> None:
        super().__init__()
        self._records: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._next_id = 1

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info:
                message = f"{message}\n{self.format(record)}"
        except Exception:  # pragma: no cover - never break the caller
            message = str(record.msg)
        with self._lock:
            entry: dict[str, Any] = {
                "id": self._next_id,
                "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }
            self._next_id += 1
            self._records.append(entry)

    def records(self, after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            found = [entry for entry in self._records if int(entry["id"]) > after]
        return found[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


_memory_handler: MemoryLogHandler | None = None


def memory_handler() -> MemoryLogHandler:
    """The process wide buffer behind the live log view."""
    global _memory_handler
    if _memory_handler is None:
        handler = MemoryLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root = logging.getLogger()
        root.addHandler(handler)
        if root.level > logging.INFO or root.level == logging.NOTSET:
            root.setLevel(logging.INFO)
        _memory_handler = handler
    return _memory_handler
