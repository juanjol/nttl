"""Generate the application icons from the tray renderer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nttl.tray import TrayState, render_icon

SIZES = (16, 24, 32, 48, 64, 128, 256)


def main(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    base = render_icon(TrayState.IDLE, 256)
    base.save(target / "nttl.ico", sizes=[(size, size) for size in SIZES])
    base.save(target / "nttl.png")
    for state in TrayState:
        render_icon(state, 256).save(target / f"nttl-{state.value}.png")
    print(f"wrote icons to {target}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/icons"))
