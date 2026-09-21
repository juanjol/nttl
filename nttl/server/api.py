from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from nttl import __version__
from nttl.hal.errors import CameraError, ControlNotSupportedError
from nttl.hal.registry import available_backends
from nttl.server.state import AppState

router = APIRouter(prefix="/api")

STREAM_BOUNDARY = "nttlframe"


def _state(request: Request) -> AppState:
    return request.app.state.nttl  # type: ignore[no-any-return]


class ControlRequest(BaseModel):
    name: str
    value: float


class CoolerRequest(BaseModel):
    enabled: bool
    target_c: float | None = None


class SessionStartRequest(BaseModel):
    overrides: dict[str, Any] | None = None


class CompileRequest(BaseModel):
    session: str
    video: dict[str, Any] | None = None


class DarkRequest(BaseModel):
    exposure_s: float
    gain: float
    frames: int = 16


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/state")
def state_snapshot(request: Request) -> dict[str, Any]:
    return _state(request).snapshot()


@router.get("/camera")
def camera(request: Request) -> dict[str, Any]:
    return _state(request).camera_state()


@router.get("/camera/backends")
def backends() -> dict[str, list[str]]:
    return {"backends": available_backends()}


@router.post("/camera/control")
def set_control(request: Request, payload: ControlRequest) -> dict[str, Any]:
    try:
        value = _state(request).set_control(payload.name, payload.value)
    except ControlNotSupportedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CameraError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"name": payload.name, "value": value}


@router.post("/camera/cooler")
def set_cooler(request: Request, payload: CoolerRequest) -> dict[str, Any]:
    try:
        _state(request).set_cooler(enabled=payload.enabled, target_c=payload.target_c)
    except ControlNotSupportedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"enabled": payload.enabled, "target_c": payload.target_c}


@router.get("/config")
def get_config(request: Request) -> dict[str, Any]:
    return _state(request).config.model_dump(mode="json")


@router.patch("/config")
def patch_config(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        config = _state(request).update_config(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return config.model_dump(mode="json")


@router.get("/session")
def session(request: Request) -> dict[str, Any]:
    return _state(request).session_status()


@router.post("/session/start")
def start_session(request: Request, payload: SessionStartRequest) -> dict[str, Any]:
    try:
        return _state(request).start_session(payload.overrides)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/session/stop")
def stop_session(request: Request) -> dict[str, Any]:
    state = _state(request)
    state.stop_session()
    return state.session_status()


@router.get("/sessions")
def sessions(request: Request) -> dict[str, Any]:
    return {"sessions": _state(request).list_sessions()}


@router.post("/compile")
def compile_session(request: Request, payload: CompileRequest) -> dict[str, Any]:
    try:
        job = _state(request).submit_compile(payload.session, payload.video)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job.as_dict()


@router.get("/jobs")
def jobs(request: Request) -> dict[str, Any]:
    return {"jobs": [job.as_dict() for job in _state(request).jobs.list()]}


@router.get("/jobs/{job_id}")
def job(request: Request, job_id: str) -> dict[str, Any]:
    found = _state(request).jobs.get(job_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'")
    return found.as_dict()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: str) -> dict[str, Any]:
    state = _state(request)
    if state.jobs.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'")
    return {"cancelled": state.jobs.cancel(job_id)}


@router.get("/darks")
def darks(request: Request) -> dict[str, Any]:
    return {"darks": _state(request).darks()}


@router.post("/darks")
def build_darks(request: Request, payload: DarkRequest) -> dict[str, Any]:
    job = _state(request).build_darks(
        exposure_s=payload.exposure_s, gain=payload.gain, frames=payload.frames
    )
    return job.as_dict()


@router.delete("/darks/{name}")
def delete_dark(request: Request, name: str) -> dict[str, Any]:
    if not _state(request).delete_dark(name):
        raise HTTPException(status_code=404, detail=f"unknown dark '{name}'")
    return {"deleted": name}


@router.get("/schedule")
def schedule(request: Request) -> dict[str, Any]:
    state = _state(request)
    return {
        "config": state.config.schedule.model_dump(mode="json"),
        "status": state.scheduler_status(),
    }


@router.put("/schedule")
def update_schedule(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    state = _state(request)
    try:
        config = state.update_config({"schedule": payload})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if config.schedule.enabled:
        state.stop_scheduler()
        state.start_scheduler()
    else:
        state.stop_scheduler()
    return {"config": config.schedule.model_dump(mode="json"), "status": state.scheduler_status()}


@router.get("/preview.jpg")
def preview(request: Request) -> Response:
    data = _state(request).preview_jpeg()
    if data is None:
        raise HTTPException(status_code=404, detail="no preview available yet")
    return Response(content=data, media_type="image/jpeg")


@router.get("/stream.mjpg")
def stream(request: Request) -> StreamingResponse:
    state = _state(request)

    async def frames() -> AsyncIterator[bytes]:
        while True:
            data = state.preview_jpeg()
            if data is not None:
                yield (
                    f"--{STREAM_BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                    f"Content-Length: {len(data)}\r\n\r\n".encode()
                    + data
                    + b"\r\n"
                )
            await asyncio.sleep(max(state.config.preview_interval_s, 0.2))

    return StreamingResponse(
        frames(), media_type=f"multipart/x-mixed-replace; boundary={STREAM_BOUNDARY}"
    )


@router.websocket("/ws")
async def websocket_status(websocket: WebSocket) -> None:
    await websocket.accept()
    state: AppState = websocket.app.state.nttl
    try:
        while True:
            await websocket.send_json(state.snapshot())
            await asyncio.sleep(0.5)
    except (WebSocketDisconnect, RuntimeError):
        return
