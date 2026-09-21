from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

import tomlkit
from pydantic import ValidationError

from nttl.config.models import AppConfig

APP_DIR_NAME = "nttl"
CONFIG_FILE_NAME = "config.toml"


class ConfigError(Exception):
    pass


def default_config_path() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_DIR_NAME / CONFIG_FILE_NAME


def load_config(path: Path | str | None = None) -> AppConfig:
    target = Path(path) if path is not None else default_config_path()
    if not target.exists():
        return AppConfig()
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{target} is not valid TOML: {exc}") from exc
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration in {target}: {exc}") from exc


def _strip_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_strip_none(item) for item in value if item is not None]
    return value


def save_config(path: Path | str, config: AppConfig) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _strip_none(config.model_dump(mode="json"))
    target.write_text(tomlkit.dumps(payload), encoding="utf-8")
    return target
