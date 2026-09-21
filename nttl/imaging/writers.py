from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import cv2
import numpy as np
from astropy.io import fits

from nttl.hal import BayerPattern, FrameMetadata


class ImageFormat(StrEnum):
    FITS = "fits"
    PNG = "png"
    TIFF = "tiff"
    JPEG = "jpeg"


_SUFFIXES = {
    ImageFormat.FITS: ".fits",
    ImageFormat.PNG: ".png",
    ImageFormat.TIFF: ".tif",
    ImageFormat.JPEG: ".jpg",
}


def suffix_for(fmt: ImageFormat) -> str:
    return _SUFFIXES[fmt]


def write_fits(path: Path | str, data: np.ndarray, metadata: FrameMetadata) -> Path:
    target = Path(path).with_suffix(".fits")
    target.parent.mkdir(parents=True, exist_ok=True)
    header = fits.Header()
    header["DATE-OBS"] = metadata.timestamp_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    header["EXPTIME"] = metadata.exposure_s
    header["GAIN"] = metadata.gain
    header["OFFSET"] = metadata.offset
    header["CCD-TEMP"] = metadata.sensor_temp_c
    header["XBINNING"] = metadata.bin
    header["YBINNING"] = metadata.bin
    header["INSTRUME"] = metadata.camera_name
    header["IMAGETYP"] = "Dark Frame" if metadata.is_dark else "Light Frame"
    header["SEQNUM"] = metadata.sequence
    header["BITDEPTH"] = metadata.bit_depth
    header["XORGSUBF"] = metadata.roi.x
    header["YORGSUBF"] = metadata.roi.y
    if metadata.bayer_pattern is not BayerPattern.NONE:
        header["BAYERPAT"] = str(metadata.bayer_pattern)
        header["XBAYROFF"] = 0
        header["YBAYROFF"] = 0
    for key, value in metadata.extra.items():
        if isinstance(value, (int, float, str, bool)):
            header[key[:8].upper()] = value
    fits.PrimaryHDU(data=data, header=header).writeto(target, overwrite=True)
    return target


def write_image(
    path: Path | str,
    image: np.ndarray,
    fmt: ImageFormat,
    *,
    quality: int = 92,
    compression: int = 3,
) -> Path:
    if fmt is ImageFormat.FITS:
        raise ValueError("use write_fits for FITS output")
    target = Path(path).with_suffix(_SUFFIXES[fmt])
    target.parent.mkdir(parents=True, exist_ok=True)
    data = image
    if fmt is ImageFormat.JPEG and data.dtype == np.uint16:
        data = (data >> 8).astype(np.uint8)
    if data.ndim == 3:
        data = cv2.cvtColor(data, cv2.COLOR_RGB2BGR)
    params: list[int] = []
    if fmt is ImageFormat.JPEG:
        params = [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    elif fmt is ImageFormat.PNG:
        params = [cv2.IMWRITE_PNG_COMPRESSION, int(compression)]
    if not cv2.imwrite(str(target), data, params):
        raise OSError(f"could not write {target}")
    return target
