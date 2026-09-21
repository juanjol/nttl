from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from nttl import __version__
from nttl.logs import memory_handler
from nttl.server.api import router
from nttl.server.state import AppState

STATIC_DIR = Path(__file__).parent / "static"

_PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>NTTL</title></head>
<body style="font-family:system-ui;background:#0b0f17;color:#e6edf3;padding:2rem">
<h1>NTTL</h1>
<p>The web interface has not been built yet. Run <code>npm --prefix web install</code> and
<code>npm --prefix web run build</code>, then reload this page.</p>
<p>The REST API is available at <a style="color:#7aa2f7" href="/api/state">/api/state</a>.</p>
</body></html>
"""


def create_app(state: AppState) -> FastAPI:
    # Start buffering records before anything else, so the live log view in the
    # interface has the whole startup sequence.
    memory_handler()
    app = FastAPI(title="NTTL", version=__version__)
    app.state.nttl = state
    app.include_router(router)

    index = STATIC_DIR / "index.html"
    if index.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
    else:

        @app.get("/", response_class=HTMLResponse)
        def placeholder() -> str:
            return _PLACEHOLDER

    return app
