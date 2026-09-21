# NTTL: Nighttime Timelapse

High quality night timelapse capture for astronomy cameras (ZWO ASI first, open HAL for other
backends). Live preview, fine grained auto exposure, dark frame library, configurable overlay and
deferred video compilation.

## Features

- Live preview with a configuration panel (capture, camera, darks, overlay, output, schedule)
- The camera stays untouched until you press "Live preview" or "Start recording"
- Manual or advanced automatic exposure with anti flicker ramping, also while previewing
- Dark frame library with automatic matching by exposure, gain, offset, binning and temperature
- One output format at a time: FITS 16-bit, PNG/TIFF 16-bit or JPEG, automatic or forced debayer
- Metadata overlay on by default, with ready made templates and a custom editor (date, time,
  exposure, gain, sensor temperature, and more)
- A list of the compiled timelapses, a button that opens the captures folder and a live log view
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

Releases are betas for now and are published on the
[releases page](https://github.com/juanjol/nttl/releases).

### Windows

Download `NTTL-<version>-Setup.exe` and run it. It installs for the current user, so it does not
ask for administrator rights, and offers a checkbox to start NTTL when you sign in.

Once running, NTTL lives in the system tray next to the clock. The icon is blue when idle, green
while capturing and red after an error, and its menu opens the interface, starts or stops a
capture, opens the sessions folder and quits the application.

### Linux

From PyPI, which is the lightest option:

```sh
uv tool install nttl              # or: pipx install nttl
uv tool install 'nttl[tray]'      # adds the tray icon
uv tool install 'nttl[desktop]'   # adds the native desktop window
```

Or download the self contained tarball, which needs no Python:

```sh
tar -xzf nttl-<version>-linux-x86_64.tar.gz
cd nttl-<version>-linux-x86_64
./install.sh
```

For an unattended allsky, register the systemd user service:

```sh
nttl service install          # writes ~/.config/systemd/user/nttl.service and starts it
nttl service status
nttl service uninstall
```

The service enables linger, so it keeps running after you log out and starts on boot. On desktops
with a notification area (KDE, XFCE, Cinnamon) `nttl tray` also works; on GNOME the tray needs an
extension, so there the service plus the web interface is the better fit.

### Docker

```sh
docker run -d --name nttl -p 8765:8765 \
  -v /srv/nttl/config:/config -v /srv/nttl/data:/data \
  --device /dev/bus/usb \
  -v /opt/zwo:/opt/zwo -e NTTL_ASI_SDK=/opt/zwo/lib/libASICamera2.so \
  ghcr.io/juanjol/nttl:beta
```

### Logs

A windowless build has no console, so the tray writes its log to
`%LOCALAPPDATA%\nttl\logs\nttl.log` on Windows and `~/.local/state/nttl/logs/nttl.log` on Linux.
Attach that file when reporting a problem.

### Build the artifacts yourself

```sh
npm --prefix web ci && npm --prefix web run build
uv run --group build python packaging/make_icons.py build/icons
uv run --group build pyinstaller --noconfirm --distpath build/dist --workpath build/work packaging/nttl.spec
# Windows only, with Inno Setup installed:
iscc /DAppVersion=0.1.0b2 packaging\installer\nttl.iss
```

## Defaults

Out of the box NTTL captures a frame every 5 seconds with automatic exposure between 1 ms and
5 seconds, writes a JPEG per frame into `sessions/` and stamps the date, the exposure and the gain
on every frame. Nothing needs to be configured for a first run, and the camera is only opened when
you ask for the live preview or start recording.

## Usage

```sh
nttl web                      # headless, web interface only
nttl tray                     # background with a system tray icon
nttl gui                      # desktop window with the same interface
nttl capture --help
nttl compile --help
nttl darks --help
nttl service --help           # systemd user service (Linux)
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
