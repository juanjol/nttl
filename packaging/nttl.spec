# PyInstaller specification: one directory with a console and a windowless binary.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
STATIC = ROOT / "nttl" / "server" / "static"
ICONS = ROOT / "build" / "icons"

if not STATIC.exists():
    raise SystemExit("build the web interface first: npm --prefix web ci && npm --prefix web run build")

datas = [(str(STATIC), "nttl/server/static")]

hiddenimports = [
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "nttl.hal.asi",
]
hiddenimports += collect_submodules("pystray")

# uvloop only speeds up the event loop and costs 16 MB; asyncio is plenty for a
# handful of clients.
excludes = [
    "IPython",
    "matplotlib",
    "pytest",
    "scipy",
    "tkinter",
    "setuptools._distutils",
    "uvloop",
]

analysis = Analysis(
    [str(ROOT / "packaging" / "entry_cli.py"), str(ROOT / "packaging" / "entry_tray.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "packaging" / "hooks")],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(analysis.pure)

icon = str(ICONS / "nttl.ico") if (ICONS / "nttl.ico").exists() else None

console_exe = EXE(
    pyz,
    [script for script in analysis.scripts if script[0] == "entry_cli"],
    exclude_binaries=True,
    name="nttl",
    console=True,
    icon=icon,
)
tray_exe = EXE(
    pyz,
    [script for script in analysis.scripts if script[0] == "entry_tray"],
    exclude_binaries=True,
    name="nttl-tray",
    console=False,
    icon=icon,
)
COLLECT(
    console_exe,
    tray_exe,
    analysis.binaries,
    analysis.datas,
    name="nttl",
)
