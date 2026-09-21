from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from astropy.io import fits
from pydantic import BaseModel, Field

from nttl.hal import Camera, ControlName, FrameMetadata

INDEX_NAME = "index.json"


class DarkMatchConfig(BaseModel):
    exposure_rel_tol: float = Field(default=0.05, ge=0.0, le=1.0)
    gain_tol: float = Field(default=1.0, ge=0.0)
    temp_tol_c: float = Field(default=3.0, ge=0.0)
    require_bin_match: bool = True


@dataclass
class DarkEntry:
    path: Path
    exposure_s: float
    gain: float
    offset: float
    sensor_temp_c: float
    bin: int
    width: int
    height: int
    frames: int
    camera_name: str
    created_at: str

    def load(self) -> np.ndarray:
        with fits.open(self.path) as hdul:
            return np.asarray(hdul[0].data, dtype=np.uint16)

    def to_dict(self) -> dict[str, object]:
        data = self.__dict__.copy()
        data["path"] = self.path.name
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object], root: Path) -> DarkEntry:
        values = dict(data)
        values["path"] = root / str(values["path"])
        return cls(**values)  # type: ignore[arg-type]


class DarkLibrary:
    def __init__(self, root: Path | str, match: DarkMatchConfig | None = None) -> None:
        self.root = Path(root)
        self.match = match or DarkMatchConfig()
        self.entries: list[DarkEntry] = []
        self._cache: dict[Path, np.ndarray] = {}
        self._load_index()

    # index handling

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_NAME

    def _load_index(self) -> None:
        if not self.index_path.exists():
            return
        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.entries = [DarkEntry.from_dict(item, self.root) for item in raw.get("entries", [])]

    def _save_index(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {"entries": [entry.to_dict() for entry in self.entries]}
        self.index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # building

    def build(
        self,
        camera: Camera,
        *,
        exposure_s: float,
        gain: float,
        frames: int = 16,
        offset: float | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> DarkEntry:
        if frames < 1:
            raise ValueError("frames must be at least 1")
        camera.set_control(ControlName.GAIN, gain)
        if offset is not None:
            camera.set_control(ControlName.OFFSET, offset)

        stack: list[np.ndarray] = []
        last: FrameMetadata | None = None
        temps: list[float] = []
        for index in range(frames):
            frame = camera.expose(exposure_s, dark=True)
            stack.append(frame.data)
            temps.append(frame.metadata.sensor_temp_c)
            last = frame.metadata
            if on_progress is not None:
                on_progress(index + 1, frames)
        assert last is not None

        master = np.median(np.stack(stack), axis=0)
        data = np.clip(master, 0, 65535).astype(np.uint16)
        created = datetime.now(UTC)
        name = (
            f"dark_e{exposure_s:g}s_g{gain:g}_b{last.bin}"
            f"_t{round(float(np.mean(temps))):+d}_{created.strftime('%Y%m%dT%H%M%S')}.fits"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / name
        header = fits.Header()
        header["EXPTIME"] = exposure_s
        header["GAIN"] = gain
        header["OFFSET"] = last.offset
        header["CCD-TEMP"] = float(np.mean(temps))
        header["XBINNING"] = last.bin
        header["INSTRUME"] = last.camera_name
        header["IMAGETYP"] = "Master Dark"
        header["NFRAMES"] = frames
        fits.PrimaryHDU(data=data, header=header).writeto(target, overwrite=True)

        entry = DarkEntry(
            path=target,
            exposure_s=float(exposure_s),
            gain=float(gain),
            offset=float(last.offset),
            sensor_temp_c=float(np.mean(temps)),
            bin=last.bin,
            width=int(data.shape[1]),
            height=int(data.shape[0]),
            frames=frames,
            camera_name=last.camera_name,
            created_at=created.isoformat(),
        )
        self.entries.append(entry)
        self._save_index()
        return entry

    # matching

    def match_entry(self, metadata: FrameMetadata) -> DarkEntry | None:
        candidates = []
        for entry in self.entries:
            if self.match.require_bin_match and entry.bin != metadata.bin:
                continue
            if abs(entry.gain - metadata.gain) > self.match.gain_tol:
                continue
            tolerance = max(metadata.exposure_s * self.match.exposure_rel_tol, 1e-6)
            if abs(entry.exposure_s - metadata.exposure_s) > tolerance:
                continue
            if abs(entry.sensor_temp_c - metadata.sensor_temp_c) > self.match.temp_tol_c:
                continue
            if (entry.width, entry.height) != (
                metadata.roi.output_width,
                metadata.roi.output_height,
            ):
                continue
            score = (
                abs(entry.exposure_s - metadata.exposure_s) / max(metadata.exposure_s, 1e-6),
                abs(entry.sensor_temp_c - metadata.sensor_temp_c),
                abs(entry.gain - metadata.gain),
            )
            candidates.append((score, entry))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]

    def find(self, metadata: FrameMetadata) -> np.ndarray | None:
        entry = self.match_entry(metadata)
        if entry is None:
            return None
        if entry.path not in self._cache:
            self._cache[entry.path] = entry.load()
        data = self._cache[entry.path]
        if data.shape != (metadata.roi.output_height, metadata.roi.output_width):
            return None
        return data

    def provider(self) -> Callable[[FrameMetadata], np.ndarray | None]:
        return self.find

    def remove(self, entry: DarkEntry) -> None:
        self.entries = [item for item in self.entries if item.path != entry.path]
        self._cache.pop(entry.path, None)
        entry.path.unlink(missing_ok=True)
        self._save_index()
