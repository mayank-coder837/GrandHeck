"""
HTTP + WebSocket API, and static hosting of the built dashboard.

    GET  /api/state             current run settings, crew, thresholds
    POST /api/control           {"action": ...}  see `control` below
    POST /api/ingest/{topic}    publish one sensor message (HTTP bridge for real devices)
    WS   /ws                    "init" snapshot, then one "tick" per simulated minute
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .runner import SPEEDS, DemoRunner

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"

runner = DemoRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    runner.start()
    yield


app = FastAPI(title="GrandHeck heat-strain gateway", lifespan=lifespan)


class Control(BaseModel):
    action: str                      # reset | pause | resume | speed | weather | spike | dropout | rest | step
    weather: str | None = None
    start_hour: float | None = None
    speed: float | None = None
    worker_id: str | None = None


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    return runner.state()


@app.post("/api/control")
async def control(c: Control) -> dict[str, Any]:
    sim = runner.sim
    if c.worker_id is not None and c.worker_id not in sim.workers:
        raise HTTPException(404, f"unknown worker {c.worker_id}")
    if c.action == "reset":
        runner.reset(c.weather or "normal", c.start_hour or 7.0)
        await runner.broadcast(runner.snapshot_message())
    elif c.action == "pause":
        runner.paused = True
    elif c.action == "resume":
        runner.paused = False
    elif c.action == "speed":
        if c.speed not in SPEEDS:
            raise HTTPException(400, f"speed must be one of {SPEEDS}")
        runner.speed = c.speed
    elif c.action == "weather":
        sim.set_weather(c.weather or "afternoon_build")
    elif c.action == "spike":
        sim.trigger_spike(c.worker_id or "W1")
    elif c.action == "dropout":
        sim.trigger_dropout(c.worker_id or "W5")
    elif c.action == "rest":
        sim.send_to_rest(c.worker_id or "W1")
    elif c.action == "step":
        tick = runner.step_once()
        if tick:
            await runner.broadcast({"type": "tick", "tick": tick})
    else:
        raise HTTPException(400, f"unknown action {c.action}")
    state = runner.state()
    await runner.broadcast({"type": "state", "state": state})
    return state


@app.post("/api/ingest/{topic:path}")
def ingest(topic: str, payload: dict[str, Any]) -> dict[str, str]:
    """Lets a real sensor (or a test script) publish a message over HTTP."""
    runner.bus.publish(topic, payload)
    return {"status": "accepted", "topic": topic}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()

    async def send(msg: dict[str, Any]) -> None:
        await ws.send_json(msg)

    await send(runner.snapshot_message())
    runner.listeners.add(send)
    try:
        while True:
            await ws.receive_text()          # we only push; keep the socket open
    except WebSocketDisconnect:
        runner.listeners.discard(send)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        target = FRONTEND_DIST / path
        return FileResponse(target if path and target.is_file() else FRONTEND_DIST / "index.html")
