from __future__ import annotations

import subprocess
import sys
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageDraw

ICON_SIZE = 64

_LOOPBACK = "127.0.0.1"
_WILDCARDS = {"0.0.0.0", "::", "[::]", ""}


class TrayState(StrEnum):
    IDLE = "idle"
    CAPTURING = "capturing"
    ERROR = "error"


_COLOURS = {
    TrayState.IDLE: (122, 162, 247, 255),
    TrayState.CAPTURING: (52, 211, 153, 255),
    TrayState.ERROR: (244, 63, 94, 255),
}


@dataclass(frozen=True, slots=True)
class MenuItem:
    label: str
    action: Callable[[], None]
    enabled: bool = True


class StateLike(Protocol):
    config: Any

    def session_status(self) -> dict[str, Any]: ...

    def start_session(self, overrides: dict[str, Any] | None = None) -> Any: ...

    def stop_session(self) -> None: ...

    def shutdown(self) -> None: ...


def render_icon(state: TrayState, size: int = ICON_SIZE) -> Image.Image:
    image = Image.new("RGBA", (size, size), (11, 15, 23, 255))
    draw = ImageDraw.Draw(image)
    colour = _COLOURS[state]
    margin = size // 8
    draw.ellipse((margin, margin, size - margin, size - margin), fill=colour)
    draw.ellipse(
        (size // 2 - 3, size // 2 - 3, size // 2 + 3, size // 2 + 3), fill=(11, 15, 23, 255)
    )
    for position in ((size // 5, size // 4), (size - size // 4, size // 3)):
        draw.ellipse(
            (position[0] - 2, position[1] - 2, position[0] + 2, position[1] + 2),
            fill=(230, 237, 243, 255),
        )
    return image


def open_in_browser(url: str) -> None:
    webbrowser.open(url)


def open_in_file_manager(path: str) -> None:
    target = str(Path(path))
    if sys.platform.startswith("win"):
        argv = ["explorer", target]
    elif sys.platform == "darwin":
        argv = ["open", target]
    else:
        argv = ["xdg-open", target]
    # A windowless build has no standard handles to inherit.
    subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class TrayController:
    """State and actions behind the system tray icon."""

    def __init__(
        self,
        state: StateLike,
        *,
        open_url: Callable[[str], None] = open_in_browser,
        open_path: Callable[[str], None] = open_in_file_manager,
        open_window: Callable[[str], None] | None = None,
    ) -> None:
        self.state_source = state
        self._open_url = open_url
        self._open_path = open_path
        self._open_window = open_window
        self.should_exit = False
        self.last_error: str | None = None

    @property
    def has_window(self) -> bool:
        return self._open_window is not None

    # status

    def state(self) -> TrayState:
        status = self.state_source.session_status()
        if status.get("state") == "running":
            return TrayState.CAPTURING
        if status.get("state") == "error" or status.get("last_error"):
            return TrayState.ERROR
        return TrayState.IDLE

    def url(self) -> str:
        web = self.state_source.config.web
        host = web.host if web.host not in _WILDCARDS else _LOOPBACK
        return f"http://{host}:{web.port}"

    def tooltip(self) -> str:
        status = self.state_source.session_status()
        frames = status.get("frames_captured", 0)
        return f"NTTL: {self.state().value}, {frames} frames\n{self.url().removeprefix('http://')}"

    # actions

    def open_interface(self) -> None:
        self._open_url(self.url())

    def open_desktop_window(self) -> None:
        if self._open_window is not None:
            self._open_window(self.url())

    def open_sessions_folder(self) -> None:
        self._open_path(str(self.state_source.config.capture.output.directory))

    def start_capture(self) -> None:
        try:
            self.state_source.start_session()
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)

    def stop_capture(self) -> None:
        try:
            self.state_source.stop_session()
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)

    def quit(self) -> None:
        self.state_source.shutdown()
        self.should_exit = True

    # menu

    def menu_items(self) -> list[MenuItem]:
        running = self.state() is TrayState.CAPTURING
        items = [MenuItem("Open interface", self.open_interface)]
        if running:
            items.append(MenuItem("Stop capture", self.stop_capture))
        else:
            items.append(MenuItem("Start capture", self.start_capture))
        items.append(MenuItem("Open sessions folder", self.open_sessions_folder))
        if self._open_window is not None:
            items.append(MenuItem("Open desktop window", self.open_desktop_window))
        items.append(MenuItem("Quit", self.quit))
        return items


def _load_pystray() -> Any:
    try:
        import pystray
    except ImportError as exc:  # the extra is optional
        raise RuntimeError(
            "the tray icon needs the optional dependency: pip install 'nttl[tray]'"
        ) from exc
    return pystray


def build_menu(pystray: Any, controller: TrayController, icon_holder: dict[str, Any]) -> Any:
    def wrap(action: Callable[[], None], *, quit_after: bool = False) -> Callable[..., None]:
        def handler(*_: object) -> None:
            action()
            icon = icon_holder.get("icon")
            if quit_after and icon is not None:
                icon.stop()

        return handler

    def idle(*_: object) -> bool:
        return controller.state() is not TrayState.CAPTURING

    def capturing(*_: object) -> bool:
        return controller.state() is TrayState.CAPTURING

    items = [
        pystray.MenuItem("Open interface", wrap(controller.open_interface), default=True),
        pystray.MenuItem("Start capture", wrap(controller.start_capture), visible=idle),
        pystray.MenuItem("Stop capture", wrap(controller.stop_capture), visible=capturing),
        pystray.MenuItem("Open sessions folder", wrap(controller.open_sessions_folder)),
    ]
    if controller.has_window:
        items.append(pystray.MenuItem("Open desktop window", wrap(controller.open_desktop_window)))
    items += [
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", wrap(controller.quit, quit_after=True)),
    ]
    return pystray.Menu(*items)


def run_tray(
    state: StateLike,
    *,
    open_window: Callable[[str], None] | None = None,
    refresh_s: float = 1.0,
) -> None:
    """Show the tray icon and block until the user quits."""
    import threading

    pystray = _load_pystray()
    controller = TrayController(state, open_window=open_window)
    holder: dict[str, Any] = {}
    icon = pystray.Icon(
        "nttl",
        render_icon(controller.state()),
        controller.tooltip(),
        menu=build_menu(pystray, controller, holder),
    )
    holder["icon"] = icon

    stop = threading.Event()

    def refresh() -> None:
        current = controller.state()
        while not stop.wait(refresh_s):
            latest = controller.state()
            if latest is not current:
                current = latest
                icon.icon = render_icon(latest)
            icon.title = controller.tooltip()

    worker = threading.Thread(target=refresh, name="nttl-tray-refresh", daemon=True)
    worker.start()
    try:
        icon.run()
    finally:
        stop.set()
        if not controller.should_exit:
            state.shutdown()
