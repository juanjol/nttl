import pytest

from nttl.hal import Camera
from nttl.hal.asi.camera import AsiCamera
from nttl.hal.simulated import SimulatedCamera
from tests.hal.asi.fake_sdk import FakeAsiSdk


def _simulated() -> Camera:
    return SimulatedCamera(seed=7)


def _asi_over_fake_sdk() -> Camera:
    sdk = FakeAsiSdk(width=64, height=64)
    return AsiCamera(sdk, sdk.camera_info(0))


CAMERA_FACTORIES = {"simulated": _simulated, "asi-fake": _asi_over_fake_sdk}


@pytest.fixture(params=sorted(CAMERA_FACTORIES))
def camera(request):
    cam = CAMERA_FACTORIES[request.param]()
    cam.open()
    try:
        yield cam
    finally:
        cam.close()
