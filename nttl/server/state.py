from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pydantic import ValidationError

from nttl.capture.session import CaptureSession, SessionStatus
from nttl.config.models import AppConfig, CaptureConfig
from nttl.config.store import save_config
from nttl.darks.library import DarkLibrary
from nttl.hal import Camera, CameraInfo
from nttl.hal.registry import open_camera
from nttl.imaging.stats import FrameStats
from nttl.scheduler.runner import SchedulerRunner
from nttl.scheduler.windows import Window
from nttl.video.ffmpeg import VideoConfig, compile_timelapse, find_ffmpeg
from nttl.video.jobs import Job, JobQueue

CameraFactory = Callable[..., Camera]


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
        live_view: bool = True,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.camera_factory = camera_factory
        self.camera_options = camera_options or {}
        self.compile_fn: Callable[..., Any] = compile_timelapse
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

    def connect_camera(self) -> CameraInfo:
        return self.camera.info

    def disconnect_camera(self) -> None:
        with self._camera_lock:
            if self._camera is not None:
                self._camera.close()
                self._camera = None

    def camera_state(self) -> dict[str, Any]:
        try:
            camera = self.camera
        except Exception as exc:
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
        restart_live = self.config.capture.camera != config.capture.camera
        self.config = config
        self._darks = DarkLibrary(config.darks_directory, match=config.darks)
        if self.config_path is not None:
            save_config(self.config_path, config)
        if restart_live and self._live_thread is not None:
            self.stop_live_view()
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
        if overrides:
            payload = _deep_merge(payload, overrides)
        try:
            capture_config = CaptureConfig.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        self.stop_live_view()
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
                if self.config.preview_interval_s >= 0:
                    self.start_live_view()

        self._session_thread = threading.Thread(target=run, name="nttl-session", daemon=True)
        self._session_thread.start()
        return session.status.as_dict()

    def stop_session(self) -> None:
        if self._session is not None:
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
        if self._live_thread is not None and self._live_thread.is_alive():
            return
        self._stop_live.clear()
        self._live_thread = threading.Thread(target=self._live_loop, name="nttl-live", daemon=True)
        self._live_thread.start()

    def stop_live_view(self) -> None:
        self._stop_live.set()
        thread = self._live_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10.0)
        self._live_thread = None

    def _live_loop(self) -> None:
        from nttl.capture.pipeline import render_frame

        while not self._stop_live.is_set():
            if self.session_running():
                time.sleep(0.1)
                continue
            try:
                with self._camera_lock:
                    frame = self.camera.expose(self.config.capture.camera.exposure_s)
                rendered = render_frame(frame, self.config.capture.output)
            except Exception:
                time.sleep(1.0)
                continue
            self._set_preview(rendered.image8)
            self.latest_stats = rendered.stats
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
                for path in directory.glob("*")
                if path.suffix in {".mp4", ".mov", ".webm"}
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
            "live_view": self._live_thread is not None and self._live_thread.is_alive(),
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
