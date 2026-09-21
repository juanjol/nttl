# NTTL: Nighttime Timelapse

High quality night timelapse capture for astronomy cameras (ZWO ASI first, open HAL for other
backends). Live preview, fine grained auto exposure, dark frame library, configurable overlay and
deferred video compilation.

## Features

- Live preview with a configuration panel (capture, camera, darks, overlay, output, schedule)
- Manual or advanced automatic exposure with anti flicker ramping
- Dark frame library with automatic matching by exposure, gain, offset, binning and temperature
- FITS 16-bit, PNG/TIFF 16-bit and JPEG output, automatic or forced debayer
- Configurable metadata overlay (date, time, exposure, gain, sensor temperature, and more)
- Unattended scheduler based on sun and twilight windows, for allsky setups
- Deferred video compilation with system ffmpeg, so capture never saturates the machine
- Single web UI, also embedded in a native desktop window; headless web only mode for Raspberry Pi

## Requirements

- Python 3.12 or newer
- ffmpeg on PATH (for video compilation)
- The vendor camera SDK already installed (`libASICamera2.so` on Linux, `ASICamera2.dll` on
  Windows). NTTL does not bundle it.

## Install

```sh
uv tool install nttl          # or: pipx install nttl
```

## Usage

```sh
nttl web                      # headless, web interface only
nttl gui                      # desktop window with the same interface
nttl capture --help
nttl compile --help
nttl darks --help
```

## Development

```sh
uv sync
uv run pytest
uv run ruff check .
uv run mypy nttl
```

## License

MIT
