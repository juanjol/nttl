import numpy as np
import pytest
from astropy.io import fits

from nttl.imaging.writers import ImageFormat, write_fits, write_image
from tests.imaging.test_overlay import metadata


def test_write_fits_stores_raw_data_and_headers(tmp_path):
    data = np.arange(64, dtype=np.uint16).reshape(8, 8)
    path = write_fits(tmp_path / "frame.fits", data, metadata())
    with fits.open(path) as hdul:
        header = hdul[0].header
        assert np.array_equal(hdul[0].data, data)
        assert header["EXPTIME"] == pytest.approx(12.5)
        assert header["GAIN"] == 220
        assert header["CCD-TEMP"] == pytest.approx(-9.83)
        assert header["BAYERPAT"] == "RGGB"
        assert header["XBINNING"] == 1
        assert header["INSTRUME"] == "ASI294MC Pro"
        assert header["DATE-OBS"].startswith("2026-09-21T22:30:15")
        assert header["IMAGETYP"] == "Light Frame"


def test_write_fits_marks_dark_frames(tmp_path):
    meta = metadata()
    object.__setattr__(meta, "is_dark", True)
    path = write_fits(tmp_path / "dark.fits", np.zeros((4, 4), np.uint16), meta)
    with fits.open(path) as hdul:
        assert hdul[0].header["IMAGETYP"] == "Dark Frame"


@pytest.mark.parametrize(
    ("fmt", "suffix"),
    [
        (ImageFormat.PNG, ".png"),
        (ImageFormat.TIFF, ".tif"),
        (ImageFormat.JPEG, ".jpg"),
    ],
)
def test_write_image_produces_readable_files(tmp_path, fmt, suffix):
    import cv2

    rgb = np.zeros((16, 24, 3), dtype=np.uint16)
    rgb[..., 0] = 60000
    path = write_image(tmp_path / "frame", rgb, fmt)
    assert path.suffix == suffix
    read = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    assert read is not None
    assert read.shape[:2] == (16, 24)


def test_write_image_keeps_16_bit_for_png(tmp_path):
    import cv2

    gray = np.full((8, 8), 40000, dtype=np.uint16)
    path = write_image(tmp_path / "g", gray, ImageFormat.PNG)
    read = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    assert read.dtype == np.uint16
    assert read[0, 0] == 40000


def test_write_image_converts_to_8_bit_for_jpeg(tmp_path):
    import cv2

    gray = np.full((8, 8), 65535, dtype=np.uint16)
    path = write_image(tmp_path / "g", gray, ImageFormat.JPEG, quality=90)
    read = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    assert read.dtype == np.uint8
    assert read[0, 0] > 240
