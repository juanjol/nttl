from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from nttl.darks.library import DarkMatchConfig
from nttl.imaging.overlay import OverlayConfig
from nttl.imaging.stretch import StretchConfig
from nttl.imaging.writers import ImageFormat
from nttl.scheduler.windows import ScheduleConfig
from nttl.video.ffmpeg import VideoConfig


class Priority(StrEnum):
    EXPOSURE = "exposure"
    GAIN = "gain"


class AutoExposureConfig(BaseModel):
    enabled: bool = True
    target_level: float = Field(default=0.22, gt=0.0, lt=1.0)
    tolerance: float = Field(default=0.03, ge=0.0, lt=0.5)
    min_exposure_s: float = Field(default=0.001, gt=0.0)
    max_exposure_s: float = Field(default=30.0, gt=0.0)
    min_gain: float = Field(default=0.0, ge=0.0)
    max_gain: float = Field(default=400.0, ge=0.0)
    priority: Priority = Priority.EXPOSURE
    max_change_factor: float = Field(default=1.6, gt=1.0, le=16.0)
    max_gain_step: float = Field(default=40.0, gt=0.0)
    damping: float = Field(default=0.7, gt=0.0, le=1.0)
    saturation_limit: float = Field(default=0.02, ge=0.0, le=1.0)
    saturation_reduction: float = Field(default=0.7, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _check_ranges(self) -> AutoExposureConfig:
        if self.min_exposure_s > self.max_exposure_s:
            raise ValueError("min_exposure_s must not exceed max_exposure_s")
        if self.min_gain > self.max_gain:
            raise ValueError("min_gain must not exceed max_gain")
        return self


class OutputConfig(BaseModel):
    directory: Path = Path("sessions")
    formats: list[ImageFormat] = Field(default_factory=lambda: [ImageFormat.JPEG])
    filename_template: str = "{session}_{seq:05d}"
    debayer: str = "auto"
    stretch: StretchConfig = Field(default_factory=StretchConfig)
    overlay: OverlayConfig = Field(default_factory=OverlayConfig)
    jpeg_quality: int = Field(default=92, ge=1, le=100)
    png_compression: int = Field(default=3, ge=0, le=9)


class CameraConfig(BaseModel):
    backend: str = "asi"
    camera_id: str | None = None
    exposure_s: float = Field(default=1.0, gt=0.0)
    gain: float = Field(default=120.0, ge=0.0)
    offset: float = Field(default=50.0, ge=0.0)
    bin: int = Field(default=1, ge=1, le=8)
    roi: tuple[int, int, int, int] | None = None
    cooler_enabled: bool = False
    target_temp_c: float = 0.0
    white_balance: tuple[float, float] | None = None


class CaptureConfig(BaseModel):
    session_name: str = "session"
    interval_s: float = Field(default=0.0, ge=0.0)
    frame_count: int | None = Field(default=None, ge=1)
    duration_s: float | None = Field(default=None, gt=0.0)
    use_darks: bool = True
    max_consecutive_errors: int = Field(default=5, ge=1)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    auto_exposure: AutoExposureConfig = Field(
        default_factory=lambda: AutoExposureConfig(enabled=False)
    )
    output: OutputConfig = Field(default_factory=OutputConfig)

    @model_validator(mode="after")
    def _check_limits(self) -> CaptureConfig:
        if self.frame_count is not None and self.duration_s is not None:
            raise ValueError("set either frame_count or duration_s, not both")
        return self


class WebConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    open_browser: bool = False


class AppConfig(BaseModel):
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    darks: DarkMatchConfig = Field(default_factory=DarkMatchConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    darks_directory: Path = Path("darks")
    ffmpeg_path: str | None = None
    preview_max_width: int = Field(default=1280, ge=160, le=8192)
    preview_interval_s: float = Field(default=1.0, ge=0.0, le=60.0)
