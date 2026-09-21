from __future__ import annotations

from typing import Any

from nttl.hal.base import Camera
from nttl.hal.errors import SdkNotAvailableError
from nttl.hal.types import CameraInfo

_MESSAGE = (
    "the ASI backend is not available yet in this build; "
    "install the ZWO ASI SDK and use a release that includes the bindings"
)


def open_asi_camera(camera_id: str | None = None, **options: Any) -> Camera:
    raise SdkNotAvailableError(_MESSAGE)


def list_asi_cameras() -> list[CameraInfo]:
    return []
