from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from nttl import __version__
from nttl.config.models import AppConfig
from nttl.config.store import default_config_path, load_config, save_config

app = typer.Typer(add_completion=False, help="Nighttime Timelapse", no_args_is_help=True)
console = Console()

ConfigOption = Annotated[
    Path | None, typer.Option("--config", help="Path to the configuration file")
]
SimSizeOption = Annotated[
    int | None, typer.Option("--sim-size", help="Frame size for the simulated camera")
]
BackendOption = Annotated[
    str | None, typer.Option("--backend", help="Camera backend: asi or simulated")
]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"nttl {__version__}")
        raise typer.Exit


def _load(config_path: Path | None) -> tuple[AppConfig, Path]:
    path = config_path or default_config_path()
    return load_config(path), path


def _camera_options(config: AppConfig, sim_size: int | None) -> dict[str, Any]:
    if config.capture.camera.backend != "simulated" or sim_size is None:
        return {}
    return {"width": sim_size, "height": sim_size, "star_count": 40}


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="Show version and exit"
        ),
    ] = False,
) -> None:
    # Services, scheduled tasks and windowless builds can start without usable
    # streams, which breaks anything that writes to them.
    from nttl.logs import ensure_streams

    ensure_streams()


@app.command()
def web(
    config: ConfigOption = None,
    host: Annotated[str | None, typer.Option("--host", help="Interface to bind")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Port to bind")] = None,
    backend: BackendOption = None,
    live_view: Annotated[
        bool,
        typer.Option(
            "--live-view/--no-live-view",
            help="Connect the camera and preview on start, off by default",
        ),
    ] = False,
) -> None:
    """Serve the web interface (use this for headless setups)."""
    import uvicorn

    from nttl.server.app import create_app
    from nttl.server.state import AppState

    settings, path = _load(config)
    if backend:
        settings.capture.camera.backend = backend
    state = AppState(settings, config_path=path, live_view=live_view)
    application = create_app(state)
    bind_host = host or settings.web.host
    bind_port = port or settings.web.port
    console.print(f"[bold]NTTL[/bold] web interface on http://{bind_host}:{bind_port}")
    try:
        uvicorn.run(application, host=bind_host, port=bind_port, log_level="info")
    finally:
        state.shutdown()


@app.command()
def gui(
    config: ConfigOption = None,
    width: Annotated[int, typer.Option("--width")] = 1500,
    height: Annotated[int, typer.Option("--height")] = 950,
) -> None:
    """Open the desktop window with the same interface."""
    import threading

    import uvicorn

    from nttl.logs import configure_file_logging, default_log_path, ensure_streams
    from nttl.server.app import create_app
    from nttl.server.state import AppState

    configure_file_logging(ensure_streams() or default_log_path())

    try:
        import webview
    except ImportError as exc:
        raise typer.BadParameter(
            "the desktop window needs the optional dependency: pip install 'nttl[desktop]'"
        ) from exc

    settings, path = _load(config)
    state = AppState(settings, config_path=path)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(state),
            host="127.0.0.1",
            port=settings.web.port,
            log_level="warning",
            log_config=None,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        webview.create_window(
            "NTTL", f"http://127.0.0.1:{settings.web.port}", width=width, height=height
        )
        webview.start()
    finally:
        server.should_exit = True
        state.shutdown()


@app.command()
def tray(
    config: ConfigOption = None,
    host: Annotated[str | None, typer.Option("--host", help="Interface to bind")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Port to bind")] = None,
    backend: BackendOption = None,
    open_interface: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the interface on start")
    ] = True,
) -> None:
    """Run in the background with a system tray icon."""
    import threading

    import uvicorn

    from nttl.logs import configure_file_logging, default_log_path, ensure_streams
    from nttl.server.app import create_app
    from nttl.server.state import AppState
    from nttl.tray import TrayController, run_tray

    log_path = ensure_streams() or default_log_path()
    configure_file_logging(log_path)  # keep a record for a background process
    settings, path = _load(config)
    if backend:
        settings.capture.camera.backend = backend
    if host:
        settings.web.host = host
    if port:
        settings.web.port = port
    state = AppState(settings, config_path=path)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(state),
            host=settings.web.host,
            port=settings.web.port,
            log_level="warning",
            # A windowless build has no stdout, so uvicorn cannot install its
            # own handlers; records go to the log file configured above.
            log_config=None,
        )
    )
    thread = threading.Thread(target=server.run, name="nttl-web", daemon=True)
    thread.start()
    if open_interface:
        TrayController(state).open_interface()
    try:
        run_tray(state)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        server.should_exit = True


service = typer.Typer(help="Manage the systemd user service (Linux)", no_args_is_help=True)
app.add_typer(service, name="service")


@service.command("install")
def service_install(
    config: ConfigOption = None,
    host: Annotated[str | None, typer.Option("--host")] = None,
    port: Annotated[int | None, typer.Option("--port")] = None,
    live_view: Annotated[bool, typer.Option("--live-view/--no-live-view")] = False,
    linger: Annotated[
        bool, typer.Option("--linger/--no-linger", help="Keep running after logout")
    ] = True,
) -> None:
    """Install and start NTTL as a user service."""
    import shutil

    from nttl.service import ServiceError, install_service

    settings, path = _load(config)
    if not path.exists():
        save_config(path, settings)
    executable = shutil.which("nttl") or str(Path(sys.executable).with_name("nttl"))
    try:
        unit = install_service(
            executable=executable,
            config=path,
            host=host,
            port=port,
            live_view=live_view,
            linger=linger,
        )
    except ServiceError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"installed {unit}")
    console.print(f"interface on http://{host or settings.web.host}:{port or settings.web.port}")


@service.command("uninstall")
def service_uninstall() -> None:
    """Stop and remove the user service."""
    from nttl.service import ServiceError, uninstall_service

    try:
        removed = uninstall_service()
    except ServiceError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print("service removed" if removed else "no service was installed")


@service.command("status")
def service_status_command() -> None:
    """Show whether the user service is installed and running."""
    from nttl.service import service_status

    status = service_status()
    table = Table("field", "value", title="NTTL service")
    for key in ("unit", "installed", "active", "enabled"):
        table.add_row(key, str(status[key]))
    if status.get("note"):
        table.add_row("note", str(status["note"]))
    console.print(table)


@app.command()
def capture(
    config: ConfigOption = None,
    frames: Annotated[int | None, typer.Option("--frames", help="Number of frames")] = None,
    interval: Annotated[float | None, typer.Option("--interval", help="Seconds")] = None,
    exposure: Annotated[float | None, typer.Option("--exposure", help="Seconds")] = None,
    gain: Annotated[float | None, typer.Option("--gain")] = None,
    session: Annotated[str | None, typer.Option("--session", help="Session name")] = None,
    backend: BackendOption = None,
    sim_size: SimSizeOption = None,
) -> None:
    """Run a capture session from the console."""
    from nttl.capture.session import CaptureSession
    from nttl.darks.library import DarkLibrary
    from nttl.hal.registry import open_camera

    settings, _ = _load(config)
    capture_config = settings.capture
    if backend:
        capture_config.camera.backend = backend
    if frames is not None:
        capture_config.frame_count = frames
    if interval is not None:
        capture_config.interval_s = interval
    if exposure is not None:
        capture_config.camera.exposure_s = exposure
    if gain is not None:
        capture_config.camera.gain = gain
    if session is not None:
        capture_config.session_name = session

    camera = open_camera(
        capture_config.camera.backend,
        capture_config.camera.camera_id,
        **_camera_options(settings, sim_size),
    )
    darks = DarkLibrary(settings.darks_directory, match=settings.darks)
    engine = CaptureSession(
        camera,
        capture_config,
        dark_provider=darks.provider() if capture_config.use_darks else None,
        on_event=lambda status: console.print(
            f"frame {status.frames_captured} "
            f"exp={status.exposure_s:g}s gain={status.gain:g} "
            f"level={status.level:.3f}"
            if status.level is not None
            else "",
            end="\r",
        ),
    )
    try:
        status = engine.run()
    finally:
        camera.close()
    console.print()
    console.print(
        f"{status.frames_captured} frames written to {engine.directory} "
        f"({status.frames_failed} failed)"
    )
    if status.state.value == "error":
        raise typer.Exit(code=1)


@app.command(name="compile")
def compile_video(
    session: Annotated[str, typer.Argument(help="Session name")],
    config: ConfigOption = None,
    fps: Annotated[int | None, typer.Option("--fps")] = None,
    codec: Annotated[str | None, typer.Option("--codec", help="h264, h265, vp9 or prores")] = None,
    crf: Annotated[int | None, typer.Option("--crf")] = None,
) -> None:
    """Compile a session into a video."""
    from nttl.video.ffmpeg import Codec, FfmpegNotFoundError, compile_timelapse

    settings, _ = _load(config)
    video = settings.video
    if fps is not None:
        video.fps = fps
    if codec is not None:
        video.codec = Codec(codec)
    if crf is not None:
        video.crf = crf

    directory = Path(settings.capture.output.directory) / session
    manifest = directory / "manifest.jsonl"
    if not manifest.exists():
        console.print(f"[red]no manifest found for session '{session}' in {directory}[/red]")
        raise typer.Exit(code=1)
    suffix = {"prores": ".mov", "vp9": ".webm"}.get(str(video.codec), ".mp4")
    output = directory / f"{session}{suffix}"
    try:
        result = compile_timelapse(
            manifest,
            output,
            video,
            ffmpeg=settings.ffmpeg_path,
            on_progress=lambda done, total: console.print(f"encoding {done}/{total}", end="\r"),
        )
    except FfmpegNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print()
    console.print(f"wrote {result.output} from {result.frame_count} frames")


@app.command()
def darks(
    config: ConfigOption = None,
    exposure: Annotated[float, typer.Option("--exposure", help="Seconds")] = 1.0,
    gain: Annotated[float, typer.Option("--gain")] = 120.0,
    frames: Annotated[int, typer.Option("--frames")] = 16,
    backend: BackendOption = None,
    sim_size: SimSizeOption = None,
) -> None:
    """Build a master dark and add it to the library."""
    from nttl.darks.library import DarkLibrary
    from nttl.hal.registry import open_camera

    settings, _ = _load(config)
    if backend:
        settings.capture.camera.backend = backend
    camera = open_camera(
        settings.capture.camera.backend,
        settings.capture.camera.camera_id,
        **_camera_options(settings, sim_size),
    )
    library = DarkLibrary(settings.darks_directory, match=settings.darks)
    try:
        entry = library.build(
            camera,
            exposure_s=exposure,
            gain=gain,
            frames=frames,
            on_progress=lambda done, total: console.print(f"dark {done}/{total}", end="\r"),
        )
    finally:
        camera.close()
    console.print()
    console.print(f"wrote {entry.path} from {entry.frames} frames at {entry.sensor_temp_c:.1f}C")


@app.command()
def config(
    config_path: ConfigOption = None,
    write: Annotated[
        bool, typer.Option("--write", help="Write the current settings to the file")
    ] = False,
) -> None:
    """Show the effective configuration and where it lives."""
    settings, path = _load(config_path)
    if write:
        save_config(path, settings)
    table = Table("setting", "value", title=str(path))
    table.add_row("camera backend", settings.capture.camera.backend)
    table.add_row("session name", settings.capture.session_name)
    table.add_row("exposure", f"{settings.capture.camera.exposure_s:g} s")
    table.add_row("gain", f"{settings.capture.camera.gain:g}")
    table.add_row("auto exposure", str(settings.capture.auto_exposure.enabled))
    table.add_row("format", str(settings.capture.output.format))
    table.add_row("output directory", str(settings.capture.output.directory))
    table.add_row("darks directory", str(settings.darks_directory))
    table.add_row(
        "video", f"{settings.video.codec} {settings.video.fps} fps crf {settings.video.crf}"
    )
    table.add_row("schedule", "enabled" if settings.schedule.enabled else "disabled")
    table.add_row("web", f"{settings.web.host}:{settings.web.port}")
    console.print(table)


def main() -> None:
    app()


def tray_entry() -> None:
    """Entry point for the windowless tray executable."""
    from nttl.logs import ensure_streams

    ensure_streams()
    sys.argv = [sys.argv[0], "tray", *sys.argv[1:]]
    app()
