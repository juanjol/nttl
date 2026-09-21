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

### Camera SDK

NTTL loads the SDK that is already on the system. It looks at `NTTL_ASI_SDK`, `ASI_SDK_LIB` and
`ZWO_ASI_LIB`, then at the usual install locations. Set one of those variables when the library
lives somewhere else:

```sh
export NTTL_ASI_SDK=/opt/zwo/lib/libASICamera2.so
```

On Linux the camera also needs the vendor udev rule and a large USB buffer, both shipped with the
ZWO SDK package (`install.sh` in `lib/`). Without them the camera is only visible to root. On
Windows the ASI driver installer already registers `ASICamera2.dll`.

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

Tests that need a real camera are marked `hardware` and are skipped by default:

```sh
uv run pytest -m hardware
```

The web interface lives in `web/` and builds into `nttl/server/static`, from where the server
serves it:

```sh
npm --prefix web install
npm --prefix web run build     # production bundle
npm --prefix web run dev       # dev server proxying the API to port 8765
npm --prefix web test
```

## License

MIT
