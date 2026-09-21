from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import Event

import numpy as np

from nttl.capture.autoexposure import ExposureSettings, next_settings
from nttl.capture.pipeline import RenderedFrame, render_frame, write_outputs
from nttl.config.models import CaptureConfig
from nttl.hal import Camera, ControlName, FrameMetadata, Roi
from nttl.hal.errors import CameraError
from nttl.imaging.writers import ImageFormat

MANIFEST_NAME = "manifest.jsonl"

DarkProvider = Callable[[FrameMetadata], np.ndarray | None]


class SessionState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class SessionStatus:
    session_name: str
    state: SessionState = SessionState.IDLE
    frames_captured: int = 0
    frames_failed: int = 0
    sequence: int = 0
    exposure_s: float = 0.0
    gain: float = 0.0
    sensor_temp_c: float | None = None
    level: float | None = None
    dark_applied: bool = False
    started_at: str | None = None
    updated_at: str | None = None
    last_error: str | None = None
    directory: str = ""
    extra: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["state"] = str(self.state)
        return data


class CaptureSession:
    def __init__(
        self,
        camera: Camera,
        config: CaptureConfig,
        *,
        dark_provider: DarkProvider | None = None,
        on_event: Callable[[SessionStatus], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.camera = camera
        self.config = config
        self.dark_provider = dark_provider
        self.on_event = on_event
        self._sleep = sleep
        self._now = now
        self._stop = Event()
        self._done = False
        self.directory = Path(config.output.directory) / config.session_name
        self.manifest_path = self.directory / MANIFEST_NAME
        self.latest_preview: np.ndarray | None = None
        self.status = SessionStatus(
            session_name=config.session_name,
            exposure_s=config.camera.exposure_s,
            gain=config.camera.gain,
            directory=str(self.directory),
        )

    # public API

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> SessionStatus:
        if self._done:
            raise RuntimeError("session already finished, create a new one")
        self._done = True
        self.directory.mkdir(parents=True, exist_ok=True)
        self.status.sequence = self._last_sequence()
        self.status.state = SessionState.RUNNING
        self.status.started_at = datetime.now(UTC).isoformat()
        self._apply_camera_config()

        settings = ExposureSettings(
            exposure_s=self.config.camera.exposure_s, gain=self.config.camera.gain
        )
        deadline = None
        if self.config.duration_s is not None:
            deadline = self._now() + self.config.duration_s
        consecutive_errors = 0

        while not self._stop.is_set():
            if (
                self.config.frame_count is not None
                and self.status.frames_captured >= self.config.frame_count
            ):
                break
            if deadline is not None and self._now() >= deadline:
                break

            cycle_start = self._now()
            try:
                settings = self._capture_one(settings)
                consecutive_errors = 0
            except CameraError as exc:
                consecutive_errors += 1
                self.status.frames_failed += 1
                self.status.last_error = str(exc)
                self._emit()
                if consecutive_errors >= self.config.max_consecutive_errors:
                    self.status.state = SessionState.ERROR
                    return self.status
                continue

            if self._stop.is_set():
                break
            if (
                self.config.frame_count is not None
                and self.status.frames_captured >= self.config.frame_count
            ):
                break
            self._wait_for_next(cycle_start, settings.exposure_s, deadline)

        self.status.state = SessionState.FINISHED
        self.status.updated_at = datetime.now(UTC).isoformat()
        return self.status

    # internals

    def _capture_one(self, settings: ExposureSettings) -> ExposureSettings:
        self.camera.set_control(ControlName.GAIN, settings.gain)
        frame = self.camera.expose(settings.exposure_s)
        dark = None
        if self.config.use_darks and self.dark_provider is not None:
            dark = self.dark_provider(frame.metadata)
        rendered = render_frame(frame, self.config.output, dark=dark)
        sequence = self.status.sequence + 1
        stem = self.directory / self.config.output.filename_template.format(
            session=self.config.session_name, seq=sequence
        )
        written = write_outputs(stem, rendered, frame.metadata, self.config.output)

        self.latest_preview = rendered.image8
        self.status.sequence = sequence
        self.status.frames_captured += 1
        self.status.exposure_s = settings.exposure_s
        self.status.gain = settings.gain
        self.status.sensor_temp_c = frame.metadata.sensor_temp_c
        self.status.level = rendered.stats.normalized_median
        self.status.dark_applied = rendered.dark_applied
        self.status.updated_at = datetime.now(UTC).isoformat()
        self._append_manifest(sequence, frame.metadata, rendered, written)
        self._emit()

        return next_settings(settings, rendered.stats, self.config.auto_exposure)

    def _wait_for_next(self, cycle_start: float, exposure_s: float, deadline: float | None) -> None:
        if self.config.interval_s <= 0.0:
            return
        elapsed = self._now() - cycle_start
        if elapsed <= 0.0:
            elapsed = exposure_s
        remaining = self.config.interval_s - elapsed
        if remaining <= 0.0:
            return
        if deadline is not None:
            remaining = min(remaining, max(deadline - self._now(), 0.0))
        if remaining > 0.0:
            self._sleep(remaining)

    def _append_manifest(
        self,
        sequence: int,
        metadata: FrameMetadata,
        rendered: RenderedFrame,
        written: dict[ImageFormat, Path],
    ) -> None:
        entry = {
            "sequence": sequence,
            "timestamp_utc": metadata.timestamp_utc.isoformat(),
            "exposure_s": metadata.exposure_s,
            "gain": metadata.gain,
            "offset": metadata.offset,
            "sensor_temp_c": metadata.sensor_temp_c,
            "bin": metadata.bin,
            "bayer": str(metadata.bayer_pattern),
            "level": self.status.level,
            "dark_applied": self.status.dark_applied,
            "files": {str(fmt): str(path) for fmt, path in written.items()},
        }
        with self.manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _last_sequence(self) -> int:
        if not self.manifest_path.exists():
            return 0
        last = 0
        with self.manifest_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = max(last, int(json.loads(line)["sequence"]))
                except (ValueError, KeyError):
                    continue
        return last

    def _apply_camera_config(self) -> None:
        camera_config = self.config.camera
        self.camera.set_control(ControlName.OFFSET, camera_config.offset)
        if camera_config.white_balance is not None:
            red, blue = camera_config.white_balance
            self.camera.set_control(ControlName.WB_RED, red)
            self.camera.set_control(ControlName.WB_BLUE, blue)
        info = self.camera.info
        if camera_config.roi is not None:
            x, y, width, height = camera_config.roi
        else:
            x, y, width, height = 0, 0, info.max_width, info.max_height
        self.camera.set_roi(Roi(x=x, y=y, width=width, height=height, bin=camera_config.bin))
        if info.has_cooler:
            self.camera.set_cooler(
                enabled=camera_config.cooler_enabled, target_c=camera_config.target_temp_c
            )

    def _emit(self) -> None:
        if self.on_event is not None:
            self.on_event(self.status)
