from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import cv2
import numpy as np
from pydantic import ValidationError

from nttl.capture.autoexposure import ExposureSettings, next_settings
from nttl.capture.session import CaptureSession, SessionStatus
from nttl.config.models import AppConfig, CaptureConfig
from nttl.config.store import save_config
from nttl.darks.library import DarkLibrary
from nttl.desktop import open_in_file_manager
from nttl.hal import Camera, CameraInfo
from nttl.hal.registry import open_camera
from nttl.imaging.stats import FrameStats
from nttl.scheduler.runner import SchedulerRunner
from nttl.scheduler.windows import Window
from nttl.video.ffmpeg import VideoConfig, compile_timelapse, find_ffmpeg
from nttl.video.jobs import Job, JobQueue

CameraFactory = Callable[..., Camera]

log = logging.getLogger("nttl.server")

VIDEO_SUFFIXES = (".mp4", ".mov", ".webm", ".mkv")


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class AppState:
    """Owns the camera, the running session, the job queue and the scheduler."""

    def __init__(
        self,
        config: AppConfig,
        *,
        config_path: Path | None = None,
        camera_factory: CameraFactory = open_camera,
        camera_options: dict[str, Any] | None = None,
        live_view: bool = False,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.camera_factory = camera_factory
        self.camera_options = camera_options or {}
        self.compile_fn: Callable[..., Any] = compile_timelapse
        self.open_path: Callable[[str], None] = open_in_file_manager
        self.jobs = JobQueue()
        self.latest_stats: FrameStats | None = None

        self._camera: Camera | None = None
        self._camera_lock = threading.RLock()
        self._session: CaptureSession | None = None
        self._session_thread: threading.Thread | None = None
        self._last_status: SessionStatus | None = None
        self._preview: np.ndarray | None = None
        self._preview_lock = threading.Lock()
        self._stop_live = threading.Event()
        self._live_thread: threading.Thread | None = None
        self._live_requested = live_view
        self._live_settings: ExposureSettings | None = None
        self._live_error: str | None = None
        self._scheduler: SchedulerRunner | None = None
        self._scheduler_thread: threading.Thread | None = None
        self._darks = DarkLibrary(config.darks_directory, match=config.darks)

        if live_view:
            self.start_live_view()
        if config.schedule.enabled:
            self.start_scheduler()

    # camera

    @property
    def camera(self) -> Camera:
        with self._camera_lock:
            if self._camera is None:
                camera_config = self.config.capture.camera
                self._camera = self.camera_factory(
                    camera_config.backend, camera_config.camera_id, **self.camera_options
                )
            return self._camera

    @property
    def camera_connected(self) -> bool:
        with self._camera_lock:
            return self._camera is not None

    def connect_camera(self) -> CameraInfo:
        info = self.camera.info
        log.info("camera connected: %s (%s)", info.name, info.backend)
        return info

    def disconnect_camera(self) -> None:
        with self._camera_lock:
            if self._camera is not None:
                with contextlib.suppress(Exception):
                    self._camera.close()
                self._camera = None
                log.info("camera disconnected")

    def camera_state(self, *, connect: bool = False) -> dict[str, Any]:
        """Describe the camera, only reaching for the hardware when asked to."""
        if not connect and not self.camera_connected:
            return {"connected": False, "error": self._live_error}
        try:
            camera = self.camera
        except Exception as exc:
            self._live_error = str(exc)
            return {"connected": False, "error": str(exc)}
        with self._camera_lock:
            info = camera.info
            controls = camera.controls()
            values = {name: camera.get_control(name) for name in controls}
            roi = camera.get_roi()
        return {
            "connected": True,
            "info": {
                "name": info.name,
                "camera_id": info.camera_id,
                "backend": info.backend,
                "max_width": info.max_width,
                "max_height": info.max_height,
                "bit_depth": info.bit_depth,
                "is_color": info.is_color,
                "bayer_pattern": str(info.bayer_pattern),
                "pixel_size_um": info.pixel_size_um,
                "has_cooler": info.has_cooler,
                "supported_bins": list(info.supported_bins),
            },
            "controls": {
                name: {
                    "min": control.min_value,
                    "max": control.max_value,
                    "default": control.default,
                    "unit": control.unit,
                    "writable": control.writable,
                    "auto_supported": control.auto_supported,
                }
                for name, control in controls.items()
            },
            "values": values,
            "roi": {
                "x": roi.x,
                "y": roi.y,
                "width": roi.width,
                "height": roi.height,
                "bin": roi.bin,
            },
        }

    def set_control(self, name: str, value: float) -> float:
        with self._camera_lock:
            self.camera.set_control(name, value)
            return self.camera.get_control(name)

    def set_cooler(self, *, enabled: bool, target_c: float | None = None) -> None:
        with self._camera_lock:
            self.camera.set_cooler(enabled=enabled, target_c=target_c)

    # configuration

    def update_config(self, patch: dict[str, Any]) -> AppConfig:
        merged = _deep_merge(self.config.model_dump(mode="json"), patch)
        try:
            config = AppConfig.model_validate(merged)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        camera_changed = self.config.capture.camera != config.capture.camera
        self.config = config
        self._darks = DarkLibrary(config.darks_directory, match=config.darks)
        if self.config_path is not None:
            save_config(self.config_path, config)
        if camera_changed and not self.session_running():
            was_live = self._live_requested
            self.stop_live_view()
            self.disconnect_camera()
            if was_live:
                self.start_live_view()
        return config

    # session control

    @property
    def session(self) -> CaptureSession | None:
        return self._session

    def session_running(self) -> bool:
        return self._session_thread is not None and self._session_thread.is_alive()

    def start_session(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.session_running():
            raise RuntimeError("a capture session is already running")
        payload = self.config.capture.model_dump(mode="json")
        live = self._live_settings
        if live is not None and self.config.capture.auto_exposure.enabled:
            payload = _deep_merge(
                payload, {"camera": {"exposure_s": live.exposure_s, "gain": live.gain}}
            )
        if overrides:
            payload = _deep_merge(payload, overrides)
        try:
            capture_config = CaptureConfig.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        was_live = self._live_requested
        self.stop_live_view(remember=True)
        dark_provider = self._darks.provider() if capture_config.use_darks else None
        session = CaptureSession(
            self.camera,
            capture_config,
            dark_provider=dark_provider,
            on_event=self._on_session_event,
        )
        self._session = session
        self._last_status = session.status

        def run() -> None:
            try:
                session.run()
            finally:
                self._last_status = session.status
                log.info(
                    "session '%s' finished: %d frames, %d failed",
                    session.status.session_name,
                    session.status.frames_captured,
                    session.status.frames_failed,
                )
                if was_live:
                    self.start_live_view()
                else:
                    # Nobody is watching, so release the camera for other tools.
                    self.disconnect_camera()

        log.info("session '%s' started in %s", capture_config.session_name, session.directory)
        self._session_thread = threading.Thread(target=run, name="nttl-session", daemon=True)
        self._session_thread.start()
        return session.status.as_dict()

    def stop_session(self) -> None:
        if self._session is not None:
            log.info("stopping session '%s'", self._session.status.session_name)
            self._session.request_stop()

    def session_status(self) -> dict[str, Any]:
        if self._session is not None:
            return self._session.status.as_dict()
        if self._last_status is not None:
            return self._last_status.as_dict()
        return SessionStatus(session_name=self.config.capture.session_name).as_dict()

    def _on_session_event(self, status: SessionStatus) -> None:
        session = self._session
        if session is not None and session.latest_preview is not None:
            self._set_preview(session.latest_preview)
        if status.level is not None:
            self._last_status = status

    # preview

    def _set_preview(self, image: np.ndarray) -> None:
        with self._preview_lock:
            self._preview = image

    def preview_jpeg(self, quality: int = 85) -> bytes | None:
        with self._preview_lock:
            image = None if self._preview is None else self._preview.copy()
        if image is None:
            return None
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        max_width = self.config.preview_max_width
        if image.shape[1] > max_width:
            scale = max_width / image.shape[1]
            height = max(1, round(image.shape[0] * scale))
            image = np.asarray(cv2.resize(image, (max_width, height), interpolation=cv2.INTER_AREA))
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buffer.tobytes() if ok else None

    def start_live_view(self) -> None:
        """Connect the camera and keep a fresh frame in the preview."""
        self._live_requested = True
        if self._live_thread is not None and self._live_thread.is_alive():
            return
        self._live_error = None
        self._live_settings = None
        self._stop_live.clear()
        self._live_thread = threading.Thread(target=self._live_loop, name="nttl-live", daemon=True)
        self._live_thread.start()
        log.info("live preview started")

    def stop_live_view(self, *, remember: bool = False) -> None:
        """Stop the preview loop; `remember` keeps it as the wanted state."""
        if not remember:
            self._live_requested = False
        self._stop_live.set()
        thread = self._live_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10.0)
        self._live_thread = None
        if not remember:
            log.info("live preview stopped")

    def live_view_running(self) -> bool:
        return self._live_thread is not None and self._live_thread.is_alive()

    def _live_settings_for(self, camera_config: Any) -> ExposureSettings:
        settings = self._live_settings
        if settings is None:
            settings = ExposureSettings(
                exposure_s=camera_config.exposure_s, gain=camera_config.gain
            )
        auto = self.config.capture.auto_exposure
        if not auto.enabled:
            return ExposureSettings(exposure_s=camera_config.exposure_s, gain=camera_config.gain)
        return settings

    def _live_loop(self) -> None:
        from nttl.capture.pipeline import render_frame
        from nttl.hal import ControlName

        while not self._stop_live.is_set():
            if self.session_running():
                time.sleep(0.1)
                continue
            camera_config = self.config.capture.camera
            settings = self._live_settings_for(camera_config)
            try:
                with self._camera_lock:
                    camera = self.camera
                    with contextlib.suppress(Exception):
                        camera.set_control(ControlName.OFFSET, camera_config.offset)
                    camera.set_control(ControlName.GAIN, settings.gain)
                    frame = camera.expose(settings.exposure_s)
                rendered = render_frame(frame, self.config.capture.output)
            except Exception as exc:
                if self._live_error != str(exc):
                    log.warning("live preview failed: %s", exc)
                self._live_error = str(exc)
                self._stop_live.wait(1.0)
                continue
            self._live_error = None
            self._set_preview(rendered.image8)
            self.latest_stats = rendered.stats
            # The preview drives the same controller the session uses, so the
            # image is already well exposed by the time a capture starts.
            self._live_settings = next_settings(
                settings, rendered.stats, self.config.capture.auto_exposure
            )
            interval = self.config.preview_interval_s
            if interval > 0:
                self._stop_live.wait(interval)

    # sessions on disk

    def session_directory(self, name: str) -> Path:
        return Path(self.config.capture.output.directory) / name

    def list_sessions(self) -> list[dict[str, Any]]:
        root = Path(self.config.capture.output.directory)
        if not root.is_dir():
            return []
        sessions = []
        for directory in sorted(root.iterdir(), reverse=True):
            manifest = directory / "manifest.jsonl"
            if not manifest.exists():
                continue
            frames = 0
            first: dict[str, Any] | None = None
            last: dict[str, Any] | None = None
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                frames += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                first = first or record
                last = record
            videos = [
                path.name
                for path in sorted(directory.glob("*"))
                if path.suffix.lower() in VIDEO_SUFFIXES
            ]
            sessions.append(
                {
                    "name": directory.name,
                    "frames": frames,
                    "path": str(directory),
                    "first_frame_utc": (first or {}).get("timestamp_utc"),
                    "last_frame_utc": (last or {}).get("timestamp_utc"),
                    "videos": videos,
                }
            )
        return sessions

    def directories(self) -> dict[str, str]:
        return {
            "sessions": str(Path(self.config.capture.output.directory).resolve()),
            "darks": str(Path(self.config.darks_directory).resolve()),
        }

    def list_videos(self) -> list[dict[str, Any]]:
        """Every compiled timelapse under the sessions directory, newest first."""
        root = Path(self.config.capture.output.directory)
        if not root.is_dir():
            return []
        videos: list[dict[str, Any]] = []
        for directory in sorted(root.iterdir()):
            if not directory.is_dir():
                continue
            for path in sorted(directory.iterdir()):
                if path.suffix.lower() not in VIDEO_SUFFIXES:
                    continue
                stat = path.stat()
                videos.append(
                    {
                        "session": directory.name,
                        "name": path.name,
                        "path": str(path.resolve()),
                        "size_bytes": stat.st_size,
                        "modified_utc": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                        "url": f"/api/sessions/{quote(directory.name)}/videos/{quote(path.name)}",
                    }
                )
        videos.sort(key=lambda entry: str(entry["modified_utc"]), reverse=True)
        return videos

    def video_path(self, session_name: str, file_name: str) -> Path:
        """Resolve a video inside a session, refusing anything outside it."""
        root = Path(self.config.capture.output.directory).resolve()
        target = (root / session_name / file_name).resolve()
        if root not in target.parents or target.suffix.lower() not in VIDEO_SUFFIXES:
            raise ValueError(f"'{file_name}' is not a video of session '{session_name}'")
        if not target.is_file():
            raise FileNotFoundError(f"no video '{file_name}' in session '{session_name}'")
        return target

    def open_folder(self, target: str = "sessions", session_name: str | None = None) -> str:
        if target == "darks":
            path = Path(self.config.darks_directory)
        elif session_name:
            path = self.session_directory(session_name)
        else:
            path = Path(self.config.capture.output.directory)
        path.mkdir(parents=True, exist_ok=True)
        resolved = str(path.resolve())
        self.open_path(resolved)
        log.info("opened %s in the file manager", resolved)
        return resolved

    # jobs

    def submit_compile(self, session_name: str, video: dict[str, Any] | None = None) -> Job:
        directory = self.session_directory(session_name)
        manifest = directory / "manifest.jsonl"
        if not manifest.exists():
            raise FileNotFoundError(f"no manifest for session '{session_name}'")
        payload = _deep_merge(self.config.video.model_dump(mode="json"), video or {})
        config = VideoConfig.model_validate(payload)
        suffix = (
            ".mov" if config.codec == "prores" else ".webm" if config.codec == "vp9" else ".mp4"
        )
        output = directory / f"{session_name}{suffix}"
        ffmpeg_path = self.config.ffmpeg_path

        def work(report: Callable[[int, int], None]) -> str:
            result = self.compile_fn(
                manifest, output, config, ffmpeg=ffmpeg_path, on_progress=report
            )
            return str(getattr(result, "output", output))

        return self.jobs.submit(f"compile:{session_name}", work)

    def build_darks(self, *, exposure_s: float, gain: float, frames: int = 16) -> Job:
        def work(report: Callable[[int, int], None]) -> str:
            with self._camera_lock:
                entry = self._darks.build(
                    self.camera,
                    exposure_s=exposure_s,
                    gain=gain,
                    frames=frames,
                    on_progress=report,
                )
            return entry.path.name

        return self.jobs.submit(f"darks:{exposure_s:g}s/g{gain:g}", work)

    def darks(self) -> list[dict[str, Any]]:
        return [
            {
                "name": entry.path.name,
                "exposure_s": entry.exposure_s,
                "gain": entry.gain,
                "offset": entry.offset,
                "sensor_temp_c": entry.sensor_temp_c,
                "bin": entry.bin,
                "width": entry.width,
                "height": entry.height,
                "frames": entry.frames,
                "camera_name": entry.camera_name,
                "created_at": entry.created_at,
            }
            for entry in self._darks.entries
        ]

    def delete_dark(self, name: str) -> bool:
        for entry in list(self._darks.entries):
            if entry.path.name == name:
                self._darks.remove(entry)
                return True
        return False

    # scheduler

    def start_scheduler(self) -> None:
        if self._scheduler_thread is not None and self._scheduler_thread.is_alive():
            return
        runner = SchedulerRunner(
            self.config.schedule,
            start_session=self._scheduler_start,
            stop_session=self.stop_session,
            compile_night=self._scheduler_compile,
            is_session_active=self.session_running,
        )
        self._scheduler = runner
        self._scheduler_thread = threading.Thread(
            target=runner.run, name="nttl-scheduler", daemon=True
        )
        self._scheduler_thread.start()

    def stop_scheduler(self) -> None:
        if self._scheduler is not None:
            self._scheduler.request_stop()
        self._scheduler = None
        self._scheduler_thread = None

    def scheduler_status(self) -> dict[str, Any]:
        if self._scheduler is None:
            return {"enabled": False, "in_window": False}
        return self._scheduler.status.as_dict()

    def _scheduler_start(self, window: Window) -> None:
        name = window.session_name(self.config.schedule.session_name_template)
        with contextlib.suppress(RuntimeError):
            self.start_session({"session_name": name, "frame_count": None, "duration_s": None})

    def _scheduler_compile(self, window: Window) -> None:
        name = window.session_name(self.config.schedule.session_name_template)
        with contextlib.suppress(FileNotFoundError):
            self.submit_compile(name)

    # snapshots

    def snapshot(self) -> dict[str, Any]:
        stats = self.latest_stats
        return {
            "session": self.session_status(),
            "camera": self.camera_state(),
            "scheduler": self.scheduler_status(),
            "jobs": [job.as_dict() for job in self.jobs.list()[:20]],
            "ffmpeg": {"available": find_ffmpeg(self.config.ffmpeg_path) is not None},
            "config": self.config.model_dump(mode="json"),
            "stats": None
            if stats is None
            else {
                "median": stats.median,
                "level": stats.normalized_median,
                "saturated_fraction": stats.saturated_fraction,
                "max": stats.max_value,
            },
            "live_view": self.live_view_running(),
            "live_requested": self._live_requested,
            "live_error": self._live_error,
            "camera_connected": self.camera_connected,
            "directories": self.directories(),
        }

    def shutdown(self) -> None:
        self.stop_session()
        thread = self._session_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=15.0)
        self.stop_scheduler()
        self.stop_live_view()
        self.jobs.shutdown()
        self.disconnect_camera()
