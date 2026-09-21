from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nttl.hal.base import Camera
from nttl.hal.errors import CameraNotFoundError
from nttl.hal.simulated import SimulatedCamera
from nttl.hal.types import CameraInfo


def _open_simulated(camera_id: str | None = None, **options: Any) -> Camera:
    camera = SimulatedCamera(**options)
    camera.open()
    return camera


def _open_asi(camera_id: str | None = None, **options: Any) -> Camera:
    from nttl.hal.asi import open_asi_camera

    return open_asi_camera(camera_id, **options)


_BACKENDS: dict[str, Callable[..., Camera]] = {
    "simulated": _open_simulated,
    "asi": _open_asi,
}


def available_backends() -> list[str]:
    return sorted(_BACKENDS)


def open_camera(backend: str, camera_id: str | None = None, **options: Any) -> Camera:
    try:
        factory = _BACKENDS[backend]
    except KeyError:
        raise CameraNotFoundError(
            f"unknown camera backend '{backend}', available: {', '.join(available_backends())}"
        ) from None
    return factory(camera_id, **options)


def list_cameras(backend: str) -> list[CameraInfo]:
    if backend == "simulated":
        camera = _open_simulated()
        try:
            return [camera.info]
        finally:
            camera.close()
    if backend == "asi":
        from nttl.hal.asi import list_asi_cameras

        return list_asi_cameras()
    raise CameraNotFoundError(f"unknown camera backend '{backend}'")
