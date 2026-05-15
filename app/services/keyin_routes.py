"""Card 2 — Key 班 routes.

Ported from `Key-Schedule-APP` (alexdodochen/Key-Schedule-APP) for the
single-user local app. Auth + audit logging stripped per `feedback-strip-auth-for-local-ports`.

Mounted at `/keyin` in `app.main`. Exposes:
  GET  /keyin/              — keyin index page (Tailwind UI)
  GET  /keyin/api/prefill   — handoff payload from /sched (year/month + VS/CR)
  POST /keyin/api/upload-schedule — parse Excel into vs_schedule/cr_schedule
  POST /keyin/api/preview   — dry-run, return [(day, doctor, shift), ...]
  POST /keyin/api/start     — launch SchedulerSession (Playwright EDR keyin)
  POST /keyin/api/continue  — release the "waiting_login" gate
  POST /keyin/api/cancel    — abort the current session
  GET  /keyin/api/status    — current state + last 100 log lines
  WS   /keyin/ws            — real-time status/log broadcast

The handoff cache is shared across the process; the upstream version keyed it
by username, but this app is single-user so we use a single-slot dict instead.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .keyin_excel_parser import parse_schedule_excel
from .keyin_scheduler import ConnectionManager, SchedulerSession, build_schedule_from_config

BASE_DIR = Path(__file__).resolve().parent.parent  # app/
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()
manager = ConnectionManager()
session: Optional[SchedulerSession] = None

# Single-slot handoff payload (year/month/vs_schedule/cr_schedule/tw_holidays)
# pushed by /api/sched/handoff-to-keyin in main.py. Single-user app, so no key.
prefill_payload: Optional[dict[str, Any]] = None


def _set_prefill(payload: dict[str, Any]) -> None:
    """Called by /api/sched/handoff-to-keyin to stage data for the next /keyin/ visit."""
    global prefill_payload
    prefill_payload = payload


# ── index page ──────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def keyin_index(request: Request):
    state = session.state if session else "idle"
    from .. import main as main_mod
    from .. import config as appconfig
    cfg = appconfig.load()
    return templates.TemplateResponse(request, "keyin.html", {
        "session_state": state,
        # Base.html topbar / settings status need these.
        "cfg":             cfg,
        "ready":           cfg.is_ready(),
        "static_version":  getattr(main_mod, "_STATIC_VERSION", "0"),
    })


# ── prefill (handoff from cv_solver) ───────────────────────────────
@router.get("/api/prefill")
async def api_keyin_prefill():
    global prefill_payload
    if prefill_payload is None:
        return JSONResponse({"ok": False, "error": "no prefill"})
    payload, prefill_payload = prefill_payload, None  # consume once
    return JSONResponse({"ok": True, "prefill": payload})


# ── Excel upload ────────────────────────────────────────────────────
@router.post("/api/upload-schedule")
async def api_upload_schedule(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".xls", ".xlsx"):
        return JSONResponse({"ok": False, "error": "僅支援 .xls 或 .xlsx 檔案"})
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = parse_schedule_excel(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return JSONResponse(result)


# ── preview ─────────────────────────────────────────────────────────
@router.post("/api/preview")
async def api_preview(request: Request):
    try:
        data = await request.json()
        schedule, _ = build_schedule_from_config(data)
        preview = [{"day": d, "doctor": doc, "shift": sh} for d, doc, sh in schedule]
        return JSONResponse({"ok": True, "preview": preview, "total": len(preview)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


# ── run controls ────────────────────────────────────────────────────
@router.post("/api/start")
async def api_start(request: Request):
    global session
    if session and session.state in ("waiting_login", "running", "starting"):
        return JSONResponse({"ok": False, "error": "排班機器人正在執行中，請先取消"})
    data = await request.json()
    session = SchedulerSession(data, manager)
    asyncio.create_task(session.run())
    return JSONResponse({"ok": True})


@router.post("/api/continue")
async def api_continue():
    if not session or session.state != "waiting_login":
        return JSONResponse({"ok": False, "error": "目前沒有等待登入的工作"})
    session.login_event.set()
    return JSONResponse({"ok": True})


@router.post("/api/cancel")
async def api_cancel():
    if session:
        await session.cancel()
    return JSONResponse({"ok": True})


@router.get("/api/status")
async def api_status():
    if not session:
        return JSONResponse({"state": "idle", "logs": []})
    return JSONResponse({"state": session.state, "logs": session.logs[-100:]})


# ── websocket ───────────────────────────────────────────────────────
@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    if session:
        await ws.send_json({"type": "status", "state": session.state})
        for line in session.logs[-50:]:
            await ws.send_json({"type": "log", "text": line})
    else:
        await ws.send_json({"type": "status", "state": "idle"})

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
