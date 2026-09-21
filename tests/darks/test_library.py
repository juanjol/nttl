import numpy as np
import pytest

from nttl.darks.library import DarkLibrary, DarkMatchConfig
from nttl.hal import BayerPattern, FrameMetadata, Roi
from nttl.hal.simulated import SimulatedCamera


def camera():
    cam = SimulatedCamera(seed=6, width=32, height=32, star_count=5, has_cooler=True)
    cam.open()
    return cam


def metadata(exposure_s=2.0, gain=100.0, temp=10.0, bin_=1) -> FrameMetadata:
    return FrameMetadata(
        timestamp_utc=__import__("datetime").datetime.now(__import__("datetime").UTC),
        exposure_s=exposure_s,
        gain=gain,
        offset=50.0,
        sensor_temp_c=temp,
        bayer_pattern=BayerPattern.RGGB,
        bin=bin_,
        roi=Roi(0, 0, 32, 32, bin_),
        sequence=0,
        camera_name="NTTL Simulated Camera",
        bit_depth=16,
    )


def test_build_creates_master_dark_and_index(tmp_path):
    library = DarkLibrary(tmp_path)
    entry = library.build(camera(), exposure_s=2.0, gain=100.0, frames=5)
    assert entry.frames == 5
    assert entry.path.exists()
    assert entry.exposure_s == pytest.approx(2.0)
    assert (tmp_path / "index.json").exists()
    assert len(DarkLibrary(tmp_path).entries) == 1


def test_master_dark_is_less_noisy_than_a_single_frame(tmp_path):
    cam = camera()
    single = cam.expose(2.0, dark=True).data.astype(np.float32)
    master = DarkLibrary(tmp_path).build(cam, exposure_s=2.0, gain=100.0, frames=9)
    data = master.load()
    assert data.dtype == np.uint16
    assert data.std() < single.std()


def test_find_matches_within_tolerances(tmp_path):
    library = DarkLibrary(tmp_path)
    library.build(camera(), exposure_s=2.0, gain=100.0, frames=3)
    found = library.find(metadata(exposure_s=2.02, gain=100.0, temp=10.5))
    assert found is not None
    assert found.shape == (32, 32)


def test_find_rejects_mismatched_exposure_or_gain(tmp_path):
    library = DarkLibrary(tmp_path)
    library.build(camera(), exposure_s=2.0, gain=100.0, frames=3)
    assert library.find(metadata(exposure_s=20.0)) is None
    assert library.find(metadata(gain=300.0)) is None
    assert library.find(metadata(bin_=2)) is None


def test_temperature_tolerance_is_configurable(tmp_path):
    library = DarkLibrary(tmp_path, match=DarkMatchConfig(temp_tol_c=1.0))
    library.build(camera(), exposure_s=2.0, gain=100.0, frames=3)
    stored = library.entries[0].sensor_temp_c
    assert library.find(metadata(temp=stored + 0.5)) is not None
    assert library.find(metadata(temp=stored + 8.0)) is None


def test_closest_entry_wins(tmp_path):
    cam = camera()
    library = DarkLibrary(tmp_path)
    library.build(cam, exposure_s=1.0, gain=100.0, frames=3)
    library.build(cam, exposure_s=4.0, gain=100.0, frames=3)
    match = library.match_entry(metadata(exposure_s=3.9))
    assert match is not None
    assert match.exposure_s == pytest.approx(4.0)


def test_provider_returns_callable_for_sessions(tmp_path):
    library = DarkLibrary(tmp_path)
    library.build(camera(), exposure_s=2.0, gain=100.0, frames=3)
    provider = library.provider()
    assert provider(metadata()) is not None
    assert provider(metadata(exposure_s=99.0)) is None


def test_entries_survive_reload(tmp_path):
    library = DarkLibrary(tmp_path)
    library.build(camera(), exposure_s=2.0, gain=100.0, frames=3)
    reloaded = DarkLibrary(tmp_path)
    assert reloaded.find(metadata()) is not None


def test_shape_mismatch_is_not_returned(tmp_path):
    library = DarkLibrary(tmp_path)
    library.build(camera(), exposure_s=2.0, gain=100.0, frames=3)
    other = metadata()
    object.__setattr__(other, "roi", Roi(0, 0, 64, 64, 1))
    assert library.find(other) is None


def test_build_reports_progress(tmp_path):
    seen = []
    DarkLibrary(tmp_path).build(
        camera(), exposure_s=1.0, gain=0.0, frames=4, on_progress=lambda i, n: seen.append((i, n))
    )
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]
