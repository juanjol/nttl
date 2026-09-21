from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from nttl.capture.autoexposure import AutoExposureConfig
from nttl.imaging.overlay import OverlayConfig
from nttl.imaging.stretch import StretchConfig
from nttl.imaging.writers import ImageFormat


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
    backend: str = "simulated"
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
