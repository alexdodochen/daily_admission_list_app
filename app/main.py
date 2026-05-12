"""
FastAPI entry point. Run with:
    python -m app.run
(or uvicorn app.main:app --port 8766)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config as appconfig
from . import llm as llm_module
from .services import sheet_service, ocr_service, lottery_service
from .services import emr_service, ordering_service, line_service
from .services import updater, cathlab_service, format_check_service, finalize_service
from .services import reschedule_service

BASE = Path(__file__).parent
app = FastAPI(title="每日入院名單 本地版")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


def _ctx(request: Request, **kw):
    cfg = appconfig.load()
    kw.setdefault("cfg", cfg)
    kw.setdefault("ready", cfg.is_ready())
    kw.setdefault("providers", llm_module.PROVIDERS)
    kw.setdefault("bundled", appconfig.bundled_flags())
    return templates.TemplateResponse(request, kw.pop("template"), kw)


# ------------------------------- pages --------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    cfg = appconfig.load()
    if not cfg.is_ready():
        return RedirectResponse("/settings", status_code=302)
    return _ctx(request, template="index.html")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return _ctx(request, template="settings.html", message="", ok=None)


# ------------------------------ settings API ------------------------------

@app.post("/api/settings")
async def save_settings(
    llm_provider: str = Form(""),
    llm_api_key: str = Form(""),
    llm_model: str = Form(""),
    google_creds_path: str = Form(""),
    sheet_id: str = Form(""),
    emr_base_url: str = Form(""),
    cathlab_base_url: str = Form(""),
    cathlab_user: str = Form(""),
    cathlab_pass: str = Form(""),
    line_token: str = Form(""),
    line_group_id: str = Form(""),
):
    cfg = appconfig.load()
    cfg.llm_provider = llm_provider.strip()
    if llm_api_key.strip():   # don't wipe existing key on blank submit
        cfg.llm_api_key = llm_api_key.strip()
    cfg.llm_model = llm_model.strip()
    cfg.google_creds_path = google_creds_path.strip()
    cfg.sheet_id = sheet_id.strip()
    if emr_base_url.strip():
        cfg.emr_base_url = emr_base_url.strip()
    if cathlab_base_url.strip():
        cfg.cathlab_base_url = cathlab_base_url.strip()
    cfg.cathlab_user = cathlab_user.strip()
    if cathlab_pass.strip():
        cfg.cathlab_pass = cathlab_pass.strip()
    if line_token.strip():
        cfg.line_token = line_token.strip()
    cfg.line_group_id = line_group_id.strip()
    appconfig.save(cfg)
    sheet_service.reset_cache()
    return {"ok": True}


@app.get("/api/settings/test")
async def test_settings():
    cfg = appconfig.load()
    result = {"llm": None, "sheet": None}
    # LLM ping
    try:
        llm = llm_module.get_llm()
        reply = await llm.text("回答一個字：OK")
        result["llm"] = {"ok": True, "provider": cfg.llm_provider,
                         "reply": reply.strip()[:40]}
    except Exception as e:
        result["llm"] = {"ok": False, "error": str(e)}
    # Sheet ping
    try:
        ok, msg = sheet_service.connection_check()
        result["sheet"] = {"ok": ok, "msg": msg}
    except Exception as e:
        result["sheet"] = {"ok": False, "msg": str(e)}
    return result


# ------------------------------ Step 1 OCR ------------------------------

@app.post("/api/step1/ocr")
async def api_step1_ocr(image: UploadFile = File(...)):
    try:
        content = await image.read()
        rows = await ocr_service.ocr_image(content, mime=image.content_type or "image/png")
        return {"ok": True, "rows": rows}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/step1/plan")
async def api_step1_plan(date: str = Form(...), rows: str = Form(...)):
    """Preview diff vs existing date-sheet without writing."""
    import json as _json
    try:
        patients = _json.loads(rows)
        return {"ok": True, **ocr_service.plan_write(date, patients)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/step1/write")
async def api_step1_write(date: str = Form(...), rows: str = Form(...),
                          allow_overwrite: str = Form("no")):
    """
    Write main-data A-L. If sheet already has data and allow_overwrite != "yes",
    returns diff + needs_confirm=True instead of writing.
    """
    import json as _json
    try:
        patients = _json.loads(rows)
        result = ocr_service.write_to_sheet(
            date, patients, allow_overwrite=(allow_overwrite == "yes"),
        )
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Step 2 Lottery ------------------------------

@app.get("/api/step2/context")
async def api_step2_context(date: str, weekday: str = ""):
    try:
        patients = lottery_service.read_main_patients(date)
        tickets = lottery_service.read_lottery_tickets(weekday) if weekday else {}
        return {"ok": True, "patients": patients, "tickets": tickets}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/step2/run")
async def api_step2_run(date: str = Form(...), tickets_json: str = Form(...),
                        seed: int = Form(0)):
    import json as _json
    try:
        tickets = _json.loads(tickets_json)
        patients = lottery_service.read_main_patients(date)
        drawn = lottery_service.draw(patients, tickets, seed=seed or None)
        ordered = lottery_service.round_robin(drawn, tickets)
        return {"ok": True, "drawn": drawn, "ordered": ordered}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/step2/write")
async def api_step2_write(date: str = Form(...), ordered_json: str = Form(...)):
    import json as _json
    try:
        ordered = _json.loads(ordered_json)
        result = lottery_service.write_to_sheet(date, ordered)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Step 3 EMR ------------------------------

@app.post("/api/step3/run")
async def api_step3_run(session_url: str = Form(...),
                        patients_json: str = Form(...),
                        admission_date: str = Form("")):
    import json as _json
    try:
        patients = _json.loads(patients_json)
        results = await emr_service.extract_patients(
            session_url, patients, admission_date=admission_date)
        return {"ok": True, "results": results}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Step 4 Ordering ------------------------------

@app.get("/api/step4/subtables")
async def api_step4_subtables(date: str):
    try:
        tables = ordering_service.read_doctor_subtables(date)
        return {"ok": True, "tables": tables}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/step4/integrate")
async def api_step4_integrate(date: str = Form(...)):
    try:
        result = ordering_service.integrate_ordering(date)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Step 4 Sheet writeback ------------------------------

@app.post("/api/step4/cell")
async def api_step4_cell(date: str = Form(...), row: int = Form(...),
                          col: int = Form(...), value: str = Form("")):
    """Generic single-cell writeback for inline editing (F/G columns)."""
    try:
        ws = sheet_service.get_worksheet(date)
        if ws is None:
            raise ValueError(f"找不到工作表 {date}")
        ws.update_cell(row, col, value)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Step 5 Cathlab ------------------------------

@app.get("/api/step5/plan")
async def api_step5_plan(date: str):
    try:
        return {"ok": True, **cathlab_service.plan(date)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/step5/verify")
async def api_step5_verify(date: str = Form(...)):
    try:
        report = await cathlab_service.verify(date)
        return {"ok": True, **report}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/step5/keyin")
async def api_step5_keyin(date: str = Form(...), dry_run: str = Form("no")):
    try:
        result = await cathlab_service.keyin(date, dry_run=(dry_run == "yes"))
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Reschedule (V flag + full move) ------------------------------

@app.post("/api/reschedule/v_flag_plan")
async def api_reschedule_v_flag_plan(date: str = Form(...),
                                     mapping_json: str = Form(...)):
    """Preview the V-flag plan. `mapping_json` = {chart_no: target_date}."""
    import json as _json
    try:
        mapping = _json.loads(mapping_json)
        return {"ok": True, **reschedule_service.plan_v_flag(date, mapping)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/reschedule/v_flag_apply")
async def api_reschedule_v_flag_apply(date: str = Form(...),
                                      mapping_json: str = Form(...)):
    import json as _json
    try:
        mapping = _json.loads(mapping_json)
        return {"ok": True, **reschedule_service.apply_v_flag(date, mapping)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/reschedule/full_move_plan")
async def api_reschedule_full_move_plan(date: str = Form(...),
                                        mapping_json: str = Form(...)):
    """Preview a full-move reschedule: V patches, main A-L rows to copy,
    cathlab DEL list. User must confirm before applying side effects."""
    import json as _json
    try:
        mapping = _json.loads(mapping_json)
        return {"ok": True, **reschedule_service.plan_full_move(date, mapping)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/reschedule/cathlab_del")
async def api_reschedule_cathlab_del(pairs_json: str = Form(...)):
    """Run WEBCVIS DEL for [[chart, cath_date], ...] pairs."""
    import json as _json
    try:
        pairs = _json.loads(pairs_json)
        pair_list = [(c, d) for c, d in pairs]
        return {"ok": True, **(await cathlab_service.del_charts(pair_list))}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ EMR main verify ------------------------------

@app.post("/api/emr/verify_main")
async def api_emr_verify_main(date: str = Form(...),
                              session_url: str = Form(...),
                              today: str = Form("")):
    """
    Cross-check main A-L姓名/性別/年齡 against EMR #divUserSpec for each
    chart. Returns the diff + patches (caller decides whether to apply).
    """
    from datetime import date as _date
    try:
        ws = sheet_service.get_worksheet(date)
        if ws is None:
            raise ValueError(f"找不到工作表 {date}")
        main = sheet_service.read_range(ws, "A2:L200") or []
        rows: list[dict] = []
        for i, r in enumerate(main):
            rr = (r + [""] * 12)[:12]
            chart = rr[8].strip()
            if not chart:
                continue
            rows.append({
                "row": i + 2,
                "chart": chart,
                "sheet_name": rr[5],
                "sheet_gender": rr[6],
                "sheet_age": rr[7],
            })
        today_str = today or _date.today().strftime("%Y%m%d")
        result = await emr_service.verify_main_emr(session_url, rows, today_str)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Step 6 LINE ------------------------------

@app.get("/api/step6/preview")
async def api_step6_preview(date: str):
    try:
        text = await line_service.preview(date)
        return {"ok": True, "text": text}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/step6/push")
async def api_step6_push(date: str = Form(...), group_id: str = Form("")):
    try:
        result = await line_service.push(date, override_group=group_id)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Format check ------------------------------

@app.get("/api/format/check")
async def api_format_check(date: str):
    try:
        return {"ok": True, **format_check_service.check(date)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/format/fix")
async def api_format_fix(date: str = Form(...), types: str = Form("")):
    try:
        type_list = [t.strip() for t in types.split(",") if t.strip()] or None
        return {"ok": True, **format_check_service.fix(date, type_list)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Finalize readiness ------------------------------

@app.get("/api/finalize/check")
async def api_finalize_check(date: str):
    try:
        return {"ok": True, **finalize_service.check_ready(date)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Auto-update ------------------------------

@app.get("/api/update/check")
async def api_update_check():
    return await updater.check()


@app.post("/api/update/apply")
async def api_update_apply(restart: str = Form("no")):
    result = await updater.apply()
    if result.get("ok") and restart == "yes":
        updater.schedule_restart()
    return result


# --------------------- Sheet explorer (read-only) ---------------------

@app.get("/api/sheet/list")
async def api_sheet_list():
    try:
        return {"ok": True, "sheets": sheet_service.list_sheets()}
    except Exception as e:
        raise HTTPException(500, str(e))
