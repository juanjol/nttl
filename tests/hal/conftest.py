import pytest

from nttl.hal import Camera
from nttl.hal.simulated import SimulatedCamera


def _simulated() -> Camera:
    return SimulatedCamera(seed=7)


CAMERA_FACTORIES = {"simulated": _simulated}


@pytest.fixture(params=sorted(CAMERA_FACTORIES))
def camera(request):
    cam = CAMERA_FACTORIES[request.param]()
    cam.open()
    try:
        yield cam
    finally:
        cam.close()
