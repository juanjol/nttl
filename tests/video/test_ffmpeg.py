import json

import pytest

from nttl.video.ffmpeg import (
    Codec,
    FfmpegNotFoundError,
    VideoConfig,
    build_command,
    compile_timelapse,
    find_ffmpeg,
    frames_from_manifest,
)


def write_manifest(tmp_path, count=3, fmt="jpeg", suffix=".jpg", missing=()):
    manifest = tmp_path / "manifest.jsonl"
    lines = []
    for index in range(1, count + 1):
        path = tmp_path / f"frame_{index:05d}{suffix}"
        if index not in missing:
            path.write_bytes(b"x")
        lines.append(json.dumps({"sequence": index, "files": {fmt: str(path)}}))
    manifest.write_text("\n".join(lines) + "\n")
    return manifest


def test_find_ffmpeg_uses_path(monkeypatch, tmp_path):
    binary = tmp_path / "ffmpeg"
    binary.write_text("")
    monkeypatch.setattr("shutil.which", lambda name: str(binary))
    assert find_ffmpeg() == binary


def test_find_ffmpeg_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("nttl.video.ffmpeg._CANDIDATES", ())
    assert find_ffmpeg() is None


def test_explicit_path_wins(tmp_path):
    binary = tmp_path / "custom-ffmpeg"
    binary.write_text("")
    assert find_ffmpeg(binary) == binary


def test_frames_from_manifest_is_ordered_and_skips_missing(tmp_path):
    manifest = write_manifest(tmp_path, count=4, missing=(2,))
    frames = frames_from_manifest(manifest)
    assert [frame.name for frame in frames] == [
        "frame_00001.jpg",
        "frame_00003.jpg",
        "frame_00004.jpg",
    ]


def test_frames_from_manifest_prefers_requested_format(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    png = tmp_path / "a.png"
    jpg = tmp_path / "a.jpg"
    png.write_bytes(b"x")
    jpg.write_bytes(b"x")
    manifest.write_text(
        json.dumps({"sequence": 1, "files": {"png": str(png), "jpeg": str(jpg)}}) + "\n"
    )
    assert frames_from_manifest(manifest, prefer="png")[0] == png
    assert frames_from_manifest(manifest, prefer="jpeg")[0] == jpg


def test_build_command_sets_codec_and_rate(tmp_path):
    listing = tmp_path / "frames.txt"
    listing.write_text("")
    config = VideoConfig(codec=Codec.H265, fps=30, crf=20, max_width=1920)
    argv = build_command("/usr/bin/ffmpeg", listing, tmp_path / "out.mp4", config)
    assert argv[0] == "/usr/bin/ffmpeg"
    assert "libx265" in argv
    assert "30" in argv
    assert "20" in argv
    assert any("1920" in part for part in argv)
    assert argv[-1] == str(tmp_path / "out.mp4")


def test_build_command_supports_prores(tmp_path):
    listing = tmp_path / "frames.txt"
    listing.write_text("")
    argv = build_command("ffmpeg", listing, tmp_path / "out.mov", VideoConfig(codec=Codec.PRORES))
    assert "prores_ks" in argv
    assert "-crf" not in argv


def test_compile_reports_progress_and_output(tmp_path, monkeypatch):
    manifest = write_manifest(tmp_path, count=5)
    progress = []

    def fake_run(argv, on_line):
        for index in range(1, 6):
            on_line(f"frame={index}")
        (tmp_path / "out.mp4").write_bytes(b"video")
        return 0

    result = compile_timelapse(
        manifest,
        tmp_path / "out.mp4",
        VideoConfig(),
        ffmpeg="/usr/bin/ffmpeg",
        runner=fake_run,
        on_progress=lambda done, total: progress.append((done, total)),
    )
    assert result.output.exists()
    assert result.frame_count == 5
    assert progress[-1] == (5, 5)


def test_compile_raises_when_ffmpeg_missing(tmp_path, monkeypatch):
    manifest = write_manifest(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("nttl.video.ffmpeg._CANDIDATES", ())
    with pytest.raises(FfmpegNotFoundError):
        compile_timelapse(manifest, tmp_path / "out.mp4", VideoConfig())


def test_compile_raises_without_frames(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("")
    with pytest.raises(ValueError):
        compile_timelapse(
            manifest, tmp_path / "out.mp4", VideoConfig(), ffmpeg="ffmpeg", runner=lambda *a: 0
        )


def test_compile_raises_on_ffmpeg_failure(tmp_path):
    manifest = write_manifest(tmp_path)
    with pytest.raises(RuntimeError):
        compile_timelapse(
            manifest,
            tmp_path / "out.mp4",
            VideoConfig(),
            ffmpeg="ffmpeg",
            runner=lambda argv, on_line: 1,
        )


@pytest.mark.skipif(find_ffmpeg() is None, reason="ffmpeg not installed")
def test_end_to_end_with_real_ffmpeg(tmp_path):
    import numpy as np

    from nttl.imaging.writers import ImageFormat, write_image

    manifest_lines = []
    for index in range(1, 11):
        image = np.full((64, 64, 3), index * 20, dtype=np.uint8)
        path = write_image(tmp_path / f"f_{index:05d}", image, ImageFormat.JPEG)
        manifest_lines.append(json.dumps({"sequence": index, "files": {"jpeg": str(path)}}))
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("\n".join(manifest_lines) + "\n")

    result = compile_timelapse(manifest, tmp_path / "out.mp4", VideoConfig(fps=10, crf=30))
    assert result.output.exists()
    assert result.output.stat().st_size > 0
