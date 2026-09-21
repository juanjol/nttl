"""Discovery of the fonts installed on the machine, for the overlay selector."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

SUFFIXES = (".ttf", ".otf", ".ttc")
_MAX_FONTS = 1000


def font_directories() -> list[Path]:
    home = Path.home()
    if sys.platform.startswith("win"):
        windows = Path(r"C:\Windows\Fonts")
        return [windows, home / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"]
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library" / "Fonts"]
    return [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / ".local" / "share" / "fonts",
        home / ".fonts",
    ]


def font_name(path: Path) -> str:
    """The family and style the font reports, falling back to the file name."""
    try:
        family, style = ImageFont.truetype(str(path), 12).getname()
    except (OSError, ValueError):
        return path.stem.replace("_", " ").replace("-", " ")
    if not family:
        return path.stem
    return f"{family} {style}" if style and style.lower() != "regular" else family


@lru_cache(maxsize=1)
def available_fonts() -> tuple[dict[str, str], ...]:
    """Every usable font on the machine, by name, without duplicates."""
    found: dict[str, str] = {}
    for directory in font_directories():
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() not in SUFFIXES or not path.is_file():
                continue
            found.setdefault(font_name(path), str(path))
    ordered = sorted(found.items(), key=lambda entry: entry[0].lower())
    return tuple({"name": name, "path": path} for name, path in ordered[:_MAX_FONTS])
