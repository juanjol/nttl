from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

_CANDIDATES = (
    Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
    Path("C:/ffmpeg/bin/ffmpeg.exe"),
    Path("/usr/bin/ffmpeg"),
    Path("/usr/local/bin/ffmpeg"),
    Path("/opt/homebrew/bin/ffmpeg"),
)

Runner = Callable[[list[str], Callable[[str], None]], int]


class FfmpegNotFoundError(RuntimeError):
    pass


class Codec(StrEnum):
    H264 = "h264"
    H265 = "h265"
    VP9 = "vp9"
    PRORES = "prores"


_ENCODERS = {
    Codec.H264: "libx264",
    Codec.H265: "libx265",
    Codec.VP9: "libvpx-vp9",
    Codec.PRORES: "prores_ks",
}


class VideoConfig(BaseModel):
    codec: Codec = Codec.H264
    fps: int = Field(default=24, ge=1, le=240)
    crf: int = Field(default=18, ge=0, le=63)
    preset: str = "medium"
    max_width: int | None = Field(default=None, ge=16)
    pix_fmt: str | None = None
    prefer_format: str = "jpeg"
    extra_args: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CompileResult:
    output: Path
    frame_count: int
    command: list[str]


def find_ffmpeg(explicit: Path | str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit)
        if path.exists() or shutil.which(str(path)):
            return path
    found = shutil.which("ffmpeg")
    if found:
        return Path(found)
    for candidate in _CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def frames_from_manifest(manifest: Path | str, prefer: str = "jpeg") -> list[Path]:
    entries: list[tuple[int, Path]] = []
    order = [prefer, "jpeg", "png", "tiff"]
    for line in Path(manifest).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        files = record.get("files", {})
        for key in order:
            if key in files:
                path = Path(files[key])
                if path.exists():
                    entries.append((int(record.get("sequence", len(entries))), path))
                break
    entries.sort(key=lambda item: item[0])
    return [path for _, path in entries]


def write_concat_file(frames: list[Path], target: Path, fps: int) -> Path:
    duration = 1.0 / fps
    lines = []
    for frame in frames:
        lines.append(f"file '{frame.as_posix()}'")
        lines.append(f"duration {duration:.6f}")
    if frames:
        lines.append(f"file '{frames[-1].as_posix()}'")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def build_command(
    ffmpeg: Path | str, listing: Path, output: Path, config: VideoConfig
) -> list[str]:
    argv = [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(listing),
        "-vsync",
        "cfr",
        "-r",
        str(config.fps),
        "-c:v",
        _ENCODERS[config.codec],
    ]
    if config.codec is Codec.PRORES:
        argv += ["-profile:v", "3", "-pix_fmt", config.pix_fmt or "yuv422p10le"]
    else:
        argv += ["-crf", str(config.crf), "-pix_fmt", config.pix_fmt or "yuv420p"]
        if config.codec in (Codec.H264, Codec.H265):
            argv += ["-preset", config.preset]
    filters = ["scale=trunc(iw/2)*2:trunc(ih/2)*2"]
    if config.max_width:
        filters = [f"scale='min({config.max_width},iw)':-2"]
    argv += ["-vf", ",".join(filters)]
    argv += config.extra_args
    argv += ["-progress", "pipe:1", str(output)]
    return argv


def _default_runner(argv: list[str], on_line: Callable[[str], None]) -> int:
    process = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    assert process.stdout is not None
    for line in process.stdout:
        on_line(line.strip())
    return process.wait()


def compile_timelapse(
    manifest: Path | str,
    output: Path | str,
    config: VideoConfig | None = None,
    *,
    ffmpeg: Path | str | None = None,
    runner: Runner | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> CompileResult:
    config = config or VideoConfig()
    binary = find_ffmpeg(ffmpeg)
    if binary is None:
        raise FfmpegNotFoundError(
            "ffmpeg was not found. Install it and make sure it is on PATH, "
            "or set the ffmpeg path in the settings."
        )
    frames = frames_from_manifest(manifest, config.prefer_format)
    if not frames:
        raise ValueError("no frames listed in the manifest")

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    listing = output.parent / f"{output.stem}_frames.txt"
    write_concat_file(frames, listing, config.fps)
    argv = build_command(binary, listing, output, config)

    total = len(frames)

    def handle(line: str) -> None:
        if on_progress is not None and line.startswith("frame="):
            try:
                done = int(line.split("=", 1)[1])
            except ValueError:
                return
            on_progress(min(done, total), total)

    code = (runner or _default_runner)(argv, handle)
    listing.unlink(missing_ok=True)
    if code != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {code}")
    return CompileResult(output=output, frame_count=total, command=argv)
