"""
FastAPI entry point. Run with:
    python -m app.run
(or uvicorn app.main:app --port 8766)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from datetime import date, datetime

from . import config as appconfig
from . import llm as llm_module
from .services import sheet_service, ocr_service, lottery_service, subtable_service
from .services import emr_service, ordering_service, line_service
from .services import updater, cathlab_service, format_check_service, finalize_service
from .services import cv_solver, scheduling_service
from .services import upstream
from .services import keyin_routes
from .services import draft_service
from .services import bug_report
from .services import diagnose as diagnose_service
from . import log_buffer

log_buffer.install()  # capture recent logs for the in-app bug reporter

BASE = Path(__file__).parent
app = FastAPI(title="心臟內科總醫師 — 本地版")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
app.include_router(keyin_routes.router, prefix="/keyin", tags=["keyin"])
templates = Jinja2Templates(directory=BASE / "templates")

# In-memory cache: solve preview kept here so /write can use it without
# re-running the solver. Single-user local app, so a plain dict is fine.
_solve_cache: dict = {}

# Per-startup version stamp injected into static asset URLs so every
# server restart busts the browser cache for app.css / app.js.
import time as _time
_STATIC_VERSION = str(int(_time.time()))


def _ctx(request: Request, **kw):
    cfg = appconfig.load()
    kw.setdefault("cfg", cfg)
    kw.setdefault("ready", cfg.is_ready())
    kw.setdefault("providers", llm_module.PROVIDERS)
    kw.setdefault("bundled", appconfig.bundled_flags())
    kw.setdefault("sa", appconfig.sa_status())
    kw.setdefault("static_version", _STATIC_VERSION)
    return templates.TemplateResponse(request, kw.pop("template"), kw)


# ------------------------------- pages --------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    cfg = appconfig.load()
    if not cfg.is_ready():
        return RedirectResponse("/settings", status_code=302)
    return _ctx(request, template="home.html")


@app.get("/admission", response_class=HTMLResponse)
async def admission_page(request: Request):
    cfg = appconfig.load()
    if not cfg.is_ready():
        return RedirectResponse("/settings", status_code=302)
    return _ctx(request, template="admission.html")


@app.get("/sched", response_class=HTMLResponse)
async def sched_page(request: Request):
    cfg = appconfig.load()
    if not cfg.is_ready():
        return RedirectResponse("/settings", status_code=302)
    return _ctx(
        request, template="schedule_gen.html",
        doctors_cr=cv_solver.CRS,
        doctors_vs=cv_solver.VS_LIST,
        doctors_mid=cv_solver.INTER_MID,
    )


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
    schedule_sheet_id: str = Form(""),
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
    # Bundled builds hide this field (SA arrives via bundle / DATA_DIR drop-in),
    # so a blank submit must NOT wipe a path the user explicitly set before.
    # Mirrors the llm_api_key / cathlab_pass "don't wipe on blank" pattern.
    if google_creds_path.strip():
        cfg.google_creds_path = google_creds_path.strip()
    cfg.sheet_id = sheet_id.strip()
    cfg.schedule_sheet_id = schedule_sheet_id.strip()
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
    scheduling_service.reset_cache()
    return {"ok": True}


@app.get("/api/settings/test")
async def test_settings():
    # The user may have dropped service_account.json into DATA_DIR AFTER the
    # app first loaded config (stale _cached → empty creds path). Re-detect.
    appconfig.reset_cache()
    sheet_service.reset_cache()
    scheduling_service.reset_cache()
    cathlab_service.reset_cache()
    cfg = appconfig.load()
    result = {"llm": None, "sheet": None, "schedule_sheet": None}
    # LLM ping
    try:
        llm = llm_module.get_llm()
        reply = await llm.text("回答一個字：OK")
        result["llm"] = {"ok": True, "provider": cfg.llm_provider,
                         "reply": reply.strip()[:40]}
    except Exception as e:
        result["llm"] = {"ok": False, "error": str(e)}
    # Admission sheet ping
    try:
        ok, msg = sheet_service.connection_check()
        result["sheet"] = {"ok": ok, "msg": msg}
    except Exception as e:
        result["sheet"] = {"ok": False, "msg": str(e)}
    # Schedule sheet ping (only if configured)
    if cfg.schedule_sheet_id:
        try:
            ok, msg = scheduling_service.connection_check()
            result["schedule_sheet"] = {"ok": ok, "msg": msg}
        except Exception as e:
            result["schedule_sheet"] = {"ok": False, "msg": str(e)}
    # Attach an actionable hint to every failure so the UI can show
    # self-service guidance instead of dumping the raw stack trace.
    for scope, block in result.items():
        if isinstance(block, dict) and block.get("ok") is False:
            err = block.get("msg") or block.get("error") or ""
            hint = diagnose_service.diagnose(err, scope=scope)
            if hint:
                block["hint"] = hint
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
                          allow_overwrite: str = Form("no"),
                          original_rows: str = Form("")):
    """
    Write main-data A-L. If sheet already has data and allow_overwrite != "yes",
    returns diff + needs_confirm=True instead of writing.

    `original_rows` (optional) is the JSON snapshot of OCR output BEFORE the
    user manually edited the table. When supplied, cells where final ≠ snapshot
    are treated as manual edits and overlaid on the kept-row verbatim copy on
    re-upload (so user fixes are not silently reverted).
    """
    import json as _json
    try:
        patients = _json.loads(rows)
        originals = _json.loads(original_rows) if original_rows else None
        result = ocr_service.write_to_sheet(
            date, patients, allow_overwrite=(allow_overwrite == "yes"),
            original_patients=originals,
        )
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Step 2 Build subtables ------------------------------

@app.post("/api/step2/build_subtables")
async def api_step2_build_subtables(date: str = Form(...)):
    """Generate per-doctor sub-tables from main A-L (no lottery)."""
    try:
        result = subtable_service.build_subtables_from_main(date)
        return {"ok": True, **result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Step 2 Lottery (legacy — kept for future use) ------------------------------

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


# ------------------------------ F/G canonical options ------------------------------

@app.get("/api/options/fg")
async def api_options_fg():
    """Return canonical F (術前診斷) and G (預計心導管) option lists for dropdowns.

    Sourced from emr_service.DIAG_RULES / CATH_RULES + a few common extras
    (s/p PCI, Cover stent) the auto-detector doesn't infer.
    """
    # emr_service.get_fg_options() reads 下拉選單 first, falls back to
    # hardcoded DIAG_RULES/CATH_RULES outputs.
    f_opts, g_opts = emr_service.get_fg_options()
    src = "sheet" if sheet_service.read_fg_options_from_sheet() else "fallback"
    return {"ok": True, "f": f_opts, "g": g_opts, "source": src}


@app.post("/api/options/fg/refresh")
async def api_options_fg_refresh():
    """Force re-read of 下拉選單 from Sheet (busts cache)."""
    sheet_service.reset_cache()
    try:
        sheet_opts = sheet_service.read_fg_options_from_sheet()
    except Exception as e:
        raise HTTPException(500, f"refresh failed: {e}")
    if not sheet_opts:
        return {"ok": False, "msg": "下拉選單 worksheet 不存在或為空"}
    f_opts, g_opts = sheet_opts
    return {"ok": True, "f_count": len(f_opts), "g_count": len(g_opts)}


# ------------------------------ Step 3 EMR ------------------------------

@app.post("/api/step3/run")
async def api_step3_run(session_url: str = Form(...),
                        patients_json: str = Form(...),
                        admission_date: str = Form(""),
                        date: str = Form("")):
    """Fetch EMR for each patient and (if `date` given) write C/F/G back to
    the doctor sub-tables on the YYYYMMDD sheet.

    Registers op_id `step3_{date}` so the user can `POST /api/op/cancel`
    mid-batch (see cancel_registry).
    """
    from .services import cancel_registry
    import json as _json
    op_id = f"step3_{(date or admission_date or 'no-date').strip()}"
    cancel_registry.start(op_id, {"step": 3, "date": date or admission_date})
    try:
        patients = _json.loads(patients_json)
        target_date = (date or admission_date or "").strip()
        # Pre-filter: anyone whose sub-table row already has C/F/G is skipped
        # entirely (no EMR fetch). The rest are "new this session" — tagged so
        # renderEmrResults can flag them with a 🆕 badge.
        to_fetch, preserved_results = emr_service.filter_already_filled(
            target_date, patients)
        for p in to_fetch:
            p["is_new_this_session"] = True
        fetched_results = await emr_service.extract_patients(
            session_url, to_fetch, admission_date=admission_date, op_id=op_id)
        results = preserved_results + fetched_results
        write_info: dict = {"written": 0, "missing": [], "skipped": True}
        main_fixes: dict = {"patches_count": 0, "fixes": [], "skipped": True}
        if target_date:
            try:
                write_info = emr_service.write_results_to_subtables(target_date, results)
                write_info["skipped"] = False
            except Exception as we:
                write_info = {"written": 0, "missing": [], "skipped": True,
                              "error": str(we)}
            # Auto-correct main A-L (姓名/性別/年齡) from EMR (independent of
            # sub-table writeback — even if sub-tables fail we still try main).
            # Only fetched patients can amend main A-L; preserved/skipped
            # patients have emr_name="" so best_patient_name would fall back
            # to the OCR-input name and could clobber a user-corrected main F.
            try:
                main_fixes = emr_service.apply_emr_main_fixes(
                    target_date, fetched_results)
            except Exception as me:
                main_fixes = {"patches_count": 0, "fixes": [], "skipped": True,
                              "error": str(me)}
            # Enrich each result with sub-table row so the UI can inline-edit
            # F/G and POST /api/step4/cell with the correct row.
            try:
                tables = ordering_service.read_doctor_subtables(target_date)
                chart_to_meta = {
                    (p.get("chart_no") or "").strip(): p
                    for _, pts in tables.items() for p in pts
                    if (p.get("chart_no") or "").strip()
                }
                for r in results:
                    ch = (r.get("chart_no") or "").strip()
                    meta = chart_to_meta.get(ch)
                    if meta:
                        r["row"] = meta["row"]
                        r["note"] = meta.get("note", "")  # H 註記
            except Exception:
                pass  # row enrichment is optional UI sugar
        canceled = any(r.get("canceled") for r in results)
        return {"ok": True, "results": results,
                "writeback": write_info, "main_fixes": main_fixes,
                "skipped_existing": len(preserved_results),
                "new_this_session": sum(1 for r in results
                                        if r.get("is_new_this_session")),
                "canceled": canceled, "op_id": op_id}
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cancel_registry.finish(op_id)


# ------------------------------ Step 4 Ordering ------------------------------

@app.get("/api/step4/subtables")
async def api_step4_subtables(date: str):
    try:
        tables = ordering_service.read_doctor_subtables(date)
    except Exception as e:
        raise HTTPException(500, str(e))
    try:
        # Self-heal: re-assert the native F/G dropdown in case it was lost to a
        # prior credential/network outage (set_fg_validation failures are
        # silently swallowed at build time). Cosmetic — never break the read.
        format_check_service.ensure_fg_validation(date)
    except Exception:
        pass
    return {"ok": True, "tables": tables}


@app.post("/api/step4/integrate")
async def api_step4_integrate(date: str = Form(...)):
    try:
        result = ordering_service.integrate_ordering(date)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/step4/lottery")
async def api_step4_lottery(date: str = Form(...),
                            weekday: str = Form(""),
                            patient_pins_json: str = Form("{}"),
                            doctor_pins_json: str = Form("{}")):
    """First-time lottery + write N-V.

    Pin layers (independent):
      * Sub-table E col (per-doctor) — within-doctor sort
      * `patient_pins_json` {chart_no: seq} — global patient pin
      * `doctor_pins_json`  {doctor: rank}  — RR doctor order pin
    """
    import json as _json
    try:
        patient_pins = _json.loads(patient_pins_json or "{}") or {}
        doctor_pins  = _json.loads(doctor_pins_json  or "{}") or {}
        result = lottery_service.lottery_with_pins(
            date, weekday, patient_pins=patient_pins, doctor_pins=doctor_pins)
        return {"ok": True, **result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Step 4 Sheet writeback ------------------------------

@app.post("/api/step4/cell")
async def api_step4_cell(date: str = Form(...), row: int = Form(...),
                          col: int = Form(...), value: str = Form("")):
    """Generic single-cell writeback for inline editing (F/G/H, 備註(住服)…).

    After the write, mirror 備註↔註記 / 術前診斷 / 預計心導管 to the twin
    cell in the other block (N-V ordering ↔ sub-table) so an edit in any UI
    keeps the whole sheet consistent.
    """
    try:
        ws = sheet_service.get_worksheet(date)
        if ws is None:
            raise ValueError(f"找不到工作表 {date}")
        ws.update_cell(row, col, value)
        mirror = {"mirrored": False}
        try:
            mirror = ordering_service.propagate_field_edit(date, row, col, value)
        except Exception:
            pass  # mirroring is best-effort — never fail the primary write
        return {"ok": True, "mirror": mirror}
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
async def api_step5_verify(date: str = Form(...), overrides: str = Form("")):
    try:
        import json as _json
        ov = _json.loads(overrides) if overrides.strip() else None
        report = await cathlab_service.verify(date, overrides=ov)
        return {"ok": True, **report}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/step5/keyin")
async def api_step5_keyin(date: str = Form(...), dry_run: str = Form("no"),
                          overrides: str = Form("")):
    from .services import cancel_registry
    op_id = f"step5_{date.strip()}"
    is_dry = (dry_run == "yes")
    if not is_dry:
        cancel_registry.start(op_id, {"step": 5, "date": date})
    try:
        import json as _json
        ov = _json.loads(overrides) if overrides.strip() else None
        result = await cathlab_service.keyin(
            date, dry_run=is_dry, overrides=ov,
            op_id=(op_id if not is_dry else ""))
        return {"ok": True, "op_id": (op_id if not is_dry else ""), **result}
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        if not is_dry:
            cancel_registry.finish(op_id)


@app.post("/api/op/cancel")
async def api_op_cancel(op_id: str = Form(...)):
    """Request cooperative cancellation of a running long-op (Step 3 / Step 5).
    The op polls the flag and stops at its next safe checkpoint.
    """
    from .services import cancel_registry
    canceled = cancel_registry.request_cancel(op_id)
    return {"ok": True, "canceled": canceled, "op_id": op_id}


@app.get("/api/op/list")
async def api_op_list():
    """Diagnostic: list currently-running long-ops."""
    from .services import cancel_registry
    return {"ok": True, "running": cancel_registry.list_running()}


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
    """Legacy single-source check (本 App 自身)."""
    return await updater.check()


@app.post("/api/update/apply")
async def api_update_apply(restart: str = Form("no")):
    """Legacy single-source apply (本 App 自身 git pull)."""
    result = await updater.apply()
    if result.get("ok") and restart == "yes":
        updater.schedule_restart()
    return result


# ------------------------------ Multi-source upstream sync ------------------------------

@app.get("/api/update/check_all")
async def api_update_check_all():
    """檢查 3 個來源（本 App + 入院清單上游 + 排班/Key 班上游）的最新 commit。

    每次 App 啟動 / 開首頁時前端會打這支，UI 依結果顯示徽章。"""
    sources = await upstream.check_all()
    return {"ok": True, "sources": sources}


@app.post("/api/update/sync/{name}")
async def api_update_sync(name: str, background_tasks: BackgroundTasks,
                          restart: str = Form("no")):
    """同步指定 source。
      - name='self'       → git pull 本 App（同 /api/update/apply）
      - name='admission'  → clone/pull daily-admission-list-public + 跑 mirror
      - name='schedule'   → clone/pull Key-Schedule-APP + 跑 mirror

    Self-restart is scheduled as a BackgroundTask so FastAPI flushes the
    response BEFORE the process os._exit/os.execv's itself. Without this,
    the daemon-thread's sleep(0.8s) used to race the response write and
    the browser saw TypeError: Failed to fetch even when the update
    succeeded (field bug 2026-05-20).
    """
    if name not in upstream.SOURCES:
        raise HTTPException(404, f"未知 source: {name}")
    result = await upstream.sync_source(name)
    if name == "self" and result.get("ok") and restart == "yes":
        background_tasks.add_task(updater.schedule_restart)
    return result


@app.post("/api/bug-report/preview")
async def api_bug_report_preview(note: str = Form(""), step: str = Form(""),
                                 error: str = Form("")):
    """Build a scrubbed diagnostic + a prefilled GitHub-issue URL.
    Nothing is sent — the user reviews the markdown and opens the URL
    (or saves the file) explicitly."""
    diag = bug_report.collect({"note": note, "step": step, "error": error})
    return {
        "ok": True,
        "markdown": bug_report.render_markdown(diag),
        "issue_url": bug_report.build_issue_url(diag),
    }


@app.post("/api/bug-report/save")
async def api_bug_report_save(note: str = Form(""), step: str = Form(""),
                              error: str = Form(""),
                              images: list[UploadFile] = File(default=[])):
    """Write the scrubbed report to DATA_DIR/bug_reports for the user to
    send privately. When screenshots are attached, the report + images are
    bundled into one .zip — screenshots NEVER go to the public GitHub path
    (PHI can be rendered into the pixels and cannot be auto-scrubbed)."""
    diag = bug_report.collect({"note": note, "step": step, "error": error})
    imgs: list[tuple[str, bytes]] = []
    for f in (images or [])[:bug_report.MAX_IMAGES]:
        try:
            data = await f.read()
        except Exception:
            continue
        if data:
            imgs.append((f.filename or "screenshot", data))
    path = bug_report.write_report_bundle(diag, imgs)
    return {"ok": True, "path": str(path), "images": len(imgs)}


@app.on_event("startup")
async def _startup_check_upstreams():
    """背景檢查 3 個來源；不 block 啟動，結果存 module 變數供前端讀。

    這支只是 prefetch / cache warmup——實際 UI 顯示走 /api/update/check_all。
    """
    import asyncio as _asyncio
    async def _bg():
        try:
            await upstream.check_all()
        except Exception:
            pass   # offline / rate limited → silent
    _asyncio.create_task(_bg())


# --------------------- Sheet explorer (read-only) ---------------------

@app.get("/api/sheet/list")
async def api_sheet_list():
    """Combined tab list across both spreadsheets so the viewer can browse
    入院清單 sheets AND 排班 sheets from one dropdown.

    Returns:
      sheets: legacy flat list (admission only) — kept for backward compat
      admission: tabs of cfg.sheet_id (admission/cathlab)
      schedule:  tabs of cfg.schedule_sheet_id (duty roster) — empty if not configured
    """
    try:
        admission_tabs = sheet_service.list_sheets()
    except Exception as e:
        raise HTTPException(500, str(e))
    schedule_tabs: list[str] = []
    cfg = appconfig.load()
    if cfg.schedule_sheet_id:
        try:
            schedule_tabs = [ws.title for ws in scheduling_service.get_sheet().worksheets()]
        except Exception:
            schedule_tabs = []  # silent — keep admission viewer working
    return {"ok": True, "sheets": admission_tabs,
            "admission": admission_tabs, "schedule": schedule_tabs}


@app.post("/api/sheet/write_cell")
async def api_sheet_write_cell(sheet: str = Form(...),
                                row: int = Form(...),
                                col: int = Form(...),
                                value: str = Form(""),
                                source: str = Form("admission")):
    """Write one cell on ANY worksheet. Powers the inline-editable cells in
    the 📋 查閱 modal so any in-app tweak lands in Google Sheet immediately.

    `row` and `col` are 1-indexed (col A = 1).
    `source` ∈ {"admission", "schedule"} routes to the right spreadsheet.
    """
    name = (sheet or "").strip()
    if not name:
        raise HTTPException(400, "missing sheet name")
    try:
        if source == "schedule":
            try:
                ws = scheduling_service.get_sheet().worksheet(name)
            except Exception:
                raise HTTPException(404, f"找不到分頁 {name}（排班 Sheet）")
        else:
            ws = sheet_service.get_worksheet(name)
        if ws is None:
            raise HTTPException(404, f"找不到分頁 {name}")
        # If we're writing into a chart-no column on a date sheet, make sure
        # the column is TEXT-formatted so a typed "01937569" keeps its leading
        # zero. Best-effort — never blocks the write.
        if name.isdigit() and len(name) == 8 and col in (2, 9, 19):
            try:
                sheet_service.ensure_chart_text_format(ws)
            except Exception:
                pass
        ws.update_cell(row, col, value)
        # On an admission date sheet, mirror 備註/術前診斷/預計心導管 edits
        # between the N-V ordering block and the sub-tables so the 查閱
        # viewer stays consistent with Step 2/3/4.
        mirror = {"mirrored": False}
        if source != "schedule" and name.isdigit() and len(name) == 8:
            try:
                mirror = ordering_service.propagate_field_edit(
                    name, row, col, value)
            except Exception:
                pass
        return {"ok": True, "sheet": name, "row": row, "col": col,
                "value": value, "mirror": mirror}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/sheet/delete")
async def api_sheet_delete(names_json: str = Form(...)):
    """Batch-delete date worksheets from the ADMISSION spreadsheet.

    HARD GUARDRAIL (irreversible op): only tabs whose name is exactly
    YYYYMMDD (8 digits) are deletable. Config tabs (主治醫師抽籤表 / 下拉選單
    / 值班總數統計 / 主治醫師導管時段表 / 改期清單 …) and the whole 排班
    spreadsheet are NEVER touched — any non-date name is rejected 400, even
    if the UI somehow sent it. The last remaining worksheet is never deleted
    (a spreadsheet must keep ≥1).
    """
    import json as _json
    import re as _re
    try:
        names = _json.loads(names_json or "[]") or []
    except Exception:
        raise HTTPException(400, "names_json 格式錯誤")
    names = [str(n).strip() for n in names if str(n).strip()]
    if not names:
        raise HTTPException(400, "沒有選取任何分頁")
    bad = [n for n in names if not _re.fullmatch(r"\d{8}", n)]
    if bad:
        raise HTTPException(
            400, f"只能刪除 YYYYMMDD 日期分頁，這些不允許刪除：{'、'.join(bad)}")
    try:
        sh = sheet_service.get_spreadsheet()
        existing = {ws.title: ws for ws in sh.worksheets()}
    except Exception as e:
        raise HTTPException(500, str(e))
    deleted: list[str] = []
    failed: list[dict] = []
    remaining = len(existing)
    for n in names:
        ws = existing.get(n)
        if ws is None:
            failed.append({"name": n, "reason": "找不到此分頁"})
            continue
        if remaining <= 1:
            failed.append({"name": n, "reason": "這是最後一個分頁，不能刪除"})
            continue
        try:
            sh.del_worksheet(ws)
            deleted.append(n)
            remaining -= 1
        except Exception as e:
            failed.append({"name": n, "reason": str(e)})
    if deleted:
        try:
            sheet_service.reset_cache()
        except Exception:
            pass
    return {"ok": True, "deleted": deleted, "failed": failed}


@app.get("/api/sheet/raw")
async def api_sheet_raw(name: str, source: str = "admission"):
    """Read ANY worksheet by exact tab name and return a raw A:Z grid.

    `source` ∈ {"admission", "schedule"} chooses which spreadsheet to read.
    Default = admission (backward compat). schedule reads from cfg.schedule_sheet_id.
    """
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "missing name")
    try:
        if source == "schedule":
            try:
                ws = scheduling_service.get_sheet().worksheet(name)
            except Exception:
                return {"ok": False, "error": f"找不到分頁 {name}（排班 Sheet）"}
        else:
            ws = sheet_service.get_worksheet(name)
        if ws is None:
            return {"ok": False, "error": f"找不到分頁 {name}"}
        rows = ws.get("A:Z") or []
        # Trim fully-blank trailing rows
        while rows and not any((c or "").strip() for c in rows[-1]):
            rows.pop()
        # Find max non-blank column to size the table
        max_cols = 0
        for r in rows:
            for i, c in enumerate(r):
                if (c or "").strip():
                    max_cols = max(max_cols, i + 1)
        return {"ok": True, "name": name, "rows": rows, "cols": max_cols}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/sheet/read")
async def api_sheet_read(date: str):
    """Read a YYYYMMDD date sheet — A:L main + N:W ordering + sub-tables.

    Read-only sheet viewer endpoint. Returns the raw cells (so the viewer can
    show exactly what's on the sheet) plus the parsed sub-table structure so
    the UI can render distinct sections.
    """
    date = (date or "").strip()
    if not date:
        raise HTTPException(400, "missing date")
    try:
        ws = sheet_service.get_worksheet(date)
        if ws is None:
            return {"ok": False, "error": f"找不到分頁 {date}"}
        rows = sheet_service.read_range(ws, "A:W")
        col_a = [(r[0] if r else "") for r in rows]
        structure = format_check_service.parse_structure(col_a)
        main_end = structure["main_end"]

        def slice_block(r0: int, r1: int, c0: int, c1: int) -> list[list[str]]:
            out: list[list[str]] = []
            for r in range(r0, min(r1 + 1, len(rows) + 1)):
                row = rows[r - 1] if r - 1 < len(rows) else []
                cells = [
                    (row[c - 1] if c - 1 < len(row) else "")
                    for c in range(c0, c1 + 1)
                ]
                out.append(cells)
            return out

        main_block = slice_block(1, main_end, 1, 12) if main_end >= 1 else []

        # N-V ordering block extent is INDEPENDENT of main_end — the ordered
        # list can be longer (or shorter) than main A-L (e.g. a patient lives
        # in the sub-tables / N-V but was dropped from main, or vice versa).
        # Walk col N (序號, idx 13) + col P (姓名, idx 15) until both blank so
        # the last 序號 row is never silently truncated. (Field bug 2026-05-21
        # #4/#5: main had 9, N-V had 10 → 序號 10 vanished from 入院序結果.)
        order_end = 1
        for r in range(2, len(rows) + 1):
            row = rows[r - 1] if r - 1 < len(rows) else []
            n_val = str(row[13]).strip() if len(row) > 13 else ""
            p_val = str(row[15]).strip() if len(row) > 15 else ""
            if not (n_val or p_val):
                break
            order_end = r
        order_block = slice_block(1, max(order_end, main_end), 14, 23)

        sub_blocks = []
        for s in structure["subs"]:
            if s.get("orphan") or not s.get("title_row"):
                continue
            r0 = s["title_row"]
            r1 = s["last_patient_row"] or s["subheader_row"] or r0
            sub_blocks.append({
                "doctor": s["doctor"],
                "declared": s["declared"],
                "actual_count": s["actual_count"],
                "title_row": r0,
                "rows": slice_block(r0, r1, 1, 7),
            })

        return {
            "ok": True,
            "date": date,
            "main_end_row": main_end,
            "main": main_block,
            "ordering": order_block,
            "subs": sub_blocks,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ------------------------------ Card 1 — 排班 ------------------------------

def _parse_iso_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def _serialize_schedule(schedule: dict) -> list[dict]:
    out = []
    for d in sorted(schedule.keys()):
        out.append({
            "date": d.strftime("%Y-%m-%d"),
            "day": d.day,
            "weekday": d.weekday(),
            "is_holiday": scheduling_service.is_taiwan_holiday(d),
            "doctor": schedule[d],
        })
    return out


def _build_projection(year: int, month: int, baseline: dict,
                      monthly_map: dict) -> tuple[list[dict], bool]:
    """Projected 值班總數統計 AFTER writing this month.

    projected = baseline − prev_contribution + new_contribution, with all
    three components returned per cell so the UI can render the math
    explicitly. `prev_contribution` is read off the existing
    `{YYYYMM} 班數統計` tab (0 if first write). Shared by /api/sched/solve
    and /api/sched/apply-edits so the projection always reflects whatever
    schedule (solved or hand-edited) currently sits in the cache.
    """
    prev_monthly: dict = {}
    try:
        sheet = scheduling_service.get_sheet()
        prev_monthly = scheduling_service.read_monthly_stats(
            sheet, f"{year}{month:02d} 班數統計") or {}
    except Exception:
        prev_monthly = {}

    KEY_PAIRS = [("平日", "平日班"), ("週五", "週五班"),
                 ("週六", "週六班"), ("週日", "週日班"), ("假日", "假日班")]
    projected_cum = []
    all_names = set(baseline) | set(monthly_map) | set(prev_monthly)
    for name in sorted(all_names):
        b = baseline.get(name, {})
        new = monthly_map.get(name, {})
        prev = prev_monthly.get(name, {})
        row = {"姓名": name}
        prev_contrib: dict = {}
        new_contrib: dict = {}
        for cum_key, mon_key in KEY_PAIRS:
            row[cum_key] = b.get(cum_key, 0) - prev.get(mon_key, 0) + new.get(mon_key, 0)
            prev_contrib[cum_key] = prev.get(mon_key, 0)
            new_contrib[cum_key] = new.get(mon_key, 0)
        row["總班數"] = row["平日"] + row["週五"] + row["假日"]
        row["baseline"] = {k: b.get(k, 0) for k, _ in KEY_PAIRS}
        row["prev_contribution"] = prev_contrib
        row["new_contribution"] = new_contrib
        projected_cum.append(row)
    return projected_cum, bool(prev_monthly)


@app.post("/api/sched/init")
async def api_sched_init(payload: dict):
    year = int(payload["year"])
    month = int(payload["month"])
    days = cv_solver.month_days(year, month)
    H, W = cv_solver.month_h_w(year, month)
    get_stat_type = scheduling_service.make_stat_type_fn(scheduling_service.is_taiwan_holiday)
    calendar_info = [{
        "date": d.strftime("%Y-%m-%d"),
        "day": d.day,
        "weekday": d.weekday(),
        "is_holiday": scheduling_service.is_taiwan_holiday(d),
        "stat_type": get_stat_type(d),
    } for d in days]

    prev_year, prev_month = scheduling_service.previous_year_month(year, month)
    prev_tail: dict = {}
    try:
        sheet = scheduling_service.get_sheet()
        baseline = scheduling_service.load_cumulative_stats(sheet)
        # Last 2 filled days of the previous month → cross-month QOD / 不連兩天.
        prev_tail = scheduling_service.read_calendar_tail(
            sheet, prev_year, prev_month, n=2)
        sheet_ok = True
        sheet_err = ""
    except Exception as e:
        baseline = {n: {"平日": 0, "週五": 0, "週六": 0, "週日": 0, "假日": 0}
                    for n in cv_solver.ALL_DOCTORS}
        sheet_ok = False
        sheet_err = str(e)

    return {
        "ok": True,
        "year": year, "month": month, "H": H, "W": W,
        "calendar": calendar_info,
        "baseline": baseline,
        "doctors": {
            "cr": cv_solver.CRS,
            "vs": cv_solver.VS_LIST,
            "mid": cv_solver.INTER_MID,
        },
        "prev_tail": {d.strftime("%Y-%m-%d"): n
                      for d, n in prev_tail.items()},
        "prev_year": prev_year,
        "prev_month": prev_month,
        "sheet_ok": sheet_ok,
        "sheet_err": sheet_err,
    }


@app.post("/api/sched/compute")
async def api_sched_compute(payload: dict):
    year = int(payload["year"])
    month = int(payload["month"])
    X = int(payload["X"])
    baseline = payload.get("baseline") or {}
    vs_holiday_exempt = payload.get("vs_holiday_exempt") or []
    targets = cv_solver.compute_initial_targets(
        year, month, X, baseline,
        vs_holiday_exempt=vs_holiday_exempt,
    )
    return {"ok": True, "targets": targets}


@app.post("/api/sched/solve")
async def api_sched_solve(payload: dict):
    year = int(payload["year"])
    month = int(payload["month"])
    X = int(payload["X"])
    fixed_in = payload.get("fixed", {})
    avoid_in = payload.get("avoid", {})
    baseline = payload.get("baseline") or {}
    jk_target = payload.get("jk_target")
    prev_tail_in = payload.get("prev_tail") or {}
    vs_holiday_exempt = payload.get("vs_holiday_exempt") or []

    fixed = {_parse_iso_date(k): v for k, v in fixed_in.items() if v}
    avoid = {n: [_parse_iso_date(d) for d in dates]
             for n, dates in avoid_in.items() if dates}
    prev_tail = {_parse_iso_date(k): v for k, v in prev_tail_in.items() if v}

    result = cv_solver.solve_month(
        year, month, X, fixed, avoid, baseline,
        jk_target=int(jk_target) if jk_target is not None else None,
        prev_tail=prev_tail,
        vs_holiday_exempt=vs_holiday_exempt,
    )
    if result is None:
        return {"ok": False, "error": "找不到可行排班，請放寬偏好或檢查 X / 預先指定的日期"}

    cache_key = f"{year}{month:02d}"
    _solve_cache[cache_key] = {
        "year": year, "month": month, "X": X,
        "schedule": result["schedule"],
        "stats_rows": result["stats_rows"],
        "monthly_stats_map": result["monthly_stats_map"],
        "baseline": baseline,
        "targets": result["targets"],
    }

    projected_cum, had_prev_monthly = _build_projection(
        year, month, baseline, result["monthly_stats_map"])

    return {
        "ok": True,
        "schedule": _serialize_schedule(result["schedule"]),
        "stats_rows": result["stats_rows"],
        "qod_violations": [
            {"date": d.strftime("%Y-%m-%d"), "name": n}
            for d, n in result["qod_violations"]
        ],
        "qod_relaxed": result["qod_relaxed"],
        "targets": {
            "cr_fri_target": result["targets"]["cr_fri_target"],
            "cr_sat_target": result["targets"]["cr_sat_target"],
            "cr_sun_target": result["targets"]["cr_sun_target"],
            "cr_holiday_target": result["targets"].get("cr_holiday_target", {}),
        },
        "projected_cumulative": projected_cum,
        "had_prev_monthly": had_prev_monthly,
    }


@app.post("/api/sched/apply-edits")
async def api_sched_apply_edits(payload: dict):
    """Apply the user's manual tweaks to the solved schedule.

    Step 5 lets the user hand-edit the calendar (swap who's on which day)
    after the solver runs. This endpoint takes the FINAL edited
    `{iso_date: name}` map, recomputes stats / QOD / projection from it
    (cv_solver.recompute_from_schedule — same classification the solver
    uses), and overwrites the cached schedule so /api/sched/write and
    /api/sched/handoff-to-keyin emit the edited result, not the original
    solve. Requires a prior /api/sched/solve (the cache holds baseline +
    targets, which a bare edit doesn't carry).
    """
    year = int(payload["year"])
    month = int(payload["month"])
    sched_in = payload.get("schedule") or {}
    cache_key = f"{year}{month:02d}"
    cached = _solve_cache.get(cache_key)
    if cached is None:
        return {"ok": False, "error": "請先按 solve 產生班表，再做手動微調"}

    # Empty cells (user cleared a day) are simply dropped — that day stays
    # unassigned and is excluded from every stat, mirroring a blank cell.
    schedule = {_parse_iso_date(k): v.strip()
                for k, v in sched_in.items() if v and v.strip()}

    result = cv_solver.recompute_from_schedule(year, month, schedule)

    cached.update({
        "schedule": result["schedule"],
        "stats_rows": result["stats_rows"],
        "monthly_stats_map": result["monthly_stats_map"],
    })

    baseline = cached.get("baseline") or {}
    projected_cum, had_prev_monthly = _build_projection(
        year, month, baseline, result["monthly_stats_map"])
    targets = cached.get("targets") or {}

    return {
        "ok": True,
        "edited": True,
        "schedule": _serialize_schedule(result["schedule"]),
        "stats_rows": result["stats_rows"],
        "qod_violations": [
            {"date": d.strftime("%Y-%m-%d"), "name": n}
            for d, n in result["qod_violations"]
        ],
        "qod_relaxed": result["qod_relaxed"],
        "targets": {
            "cr_fri_target": targets.get("cr_fri_target", {}),
            "cr_sat_target": targets.get("cr_sat_target", {}),
            "cr_sun_target": targets.get("cr_sun_target", {}),
            "cr_holiday_target": targets.get("cr_holiday_target", {}),
        },
        "projected_cumulative": projected_cum,
        "had_prev_monthly": had_prev_monthly,
    }


@app.post("/api/sched/write")
async def api_sched_write(payload: dict):
    year = int(payload["year"])
    month = int(payload["month"])
    cache_key = f"{year}{month:02d}"
    cached = _solve_cache.get(cache_key)
    if cached is None:
        return {"ok": False, "error": "請先按「solve」產生班表，再寫入"}

    schedule = cached["schedule"]
    stats_rows = cached["stats_rows"]
    monthly_stats_map = cached["monthly_stats_map"]
    baseline = cached["baseline"]
    sheet_name = f"{year}{month:02d}"

    try:
        sheet = scheduling_service.get_sheet()
        # Read previously-written monthly stats for this same month BEFORE
        # we overwrite the calendar / monthly stats sheets. If they exist,
        # subtract them in update_cumulative_stats so re-running the same
        # month doesn't double-count in 值班總數統計. (Per upstream 5/12.)
        prev_monthly: dict = {}
        try:
            prev_monthly = scheduling_service.read_monthly_stats(
                sheet, f"{sheet_name} 班數統計"
            ) or {}
        except Exception:
            prev_monthly = {}

        scheduling_service.write_calendar_sheet(
            sheet, sheet_name, year, month, schedule,
            scheduling_service.is_taiwan_holiday,
        )
        scheduling_service.write_monthly_stats(
            sheet, f"{sheet_name} 班數統計", stats_rows,
            headers=scheduling_service.DEFAULT_MONTHLY_HEADERS + ["QOD次數"],
        )
        scheduling_service.update_cumulative_stats(
            sheet, baseline, monthly_stats_map,
            previous_monthly=prev_monthly,
        )
    except Exception as e:
        return {"ok": False, "error": f"寫入失敗：{e}"}

    return {"ok": True, "sheet_name": sheet_name,
            "had_prev_monthly": bool(prev_monthly)}


@app.post("/api/sched/handoff-to-keyin")
async def api_sched_handoff(payload: dict):
    """Bridge: take cached cv_solver schedule, stage as Card 2 keyin prefill.

    Splits {date: name} into vs_schedule (VS_LIST) + cr_schedule
    (CRS + INTER_MID) keyed by day-of-month. Records tw_holidays for the
    month. Prefill is one-shot — consumed by next /keyin/api/prefill call.
    """
    year  = int(payload["year"])
    month = int(payload["month"])
    cache_key = f"{year}{month:02d}"
    cached = _solve_cache.get(cache_key)
    if cached is None:
        return {"ok": False,
                "error": "請先按「solve」產生班表，再進入 key 班"}

    schedule = cached["schedule"]
    vs_schedule: dict[int, str] = {}
    cr_schedule: dict[int, str] = {}
    for d, name in schedule.items():
        if name in cv_solver.VS_LIST:
            vs_schedule[d.day] = name
        elif name in cv_solver.CRS or name in cv_solver.INTER_MID:
            cr_schedule[d.day] = name

    tw_holidays = [
        d.strftime("%Y-%m-%d")
        for d in cv_solver.month_days(year, month)
        if cv_solver.is_taiwan_holiday(d)
    ]

    keyin_routes._set_prefill({
        "year": year,
        "month": month,
        "vs_schedule": vs_schedule,
        "cr_schedule": cr_schedule,
        "tw_holidays": tw_holidays,
    })
    return {"ok": True, "redirect": "/keyin",
            "vs_count": len(vs_schedule), "cr_count": len(cr_schedule)}


# ----------------------- Drafts (Card 1 排班 + Card 2 Key 班) -----------------------
# Single-user local app — no auth. Bucket = "sched" or "keyin". UI provides
# the name; backend slugifies it. Files stored under <user_data>/drafts/<bucket>/.

def _draft_bucket(bucket: str) -> str:
    if bucket not in ("sched", "keyin"):
        raise HTTPException(400, f"unknown bucket: {bucket}")
    return bucket


@app.post("/api/draft/{bucket}/save")
async def api_draft_save(bucket: str, payload: dict):
    b = _draft_bucket(bucket)
    name = (payload.get("name") or "").strip() or f"自動存檔_{int(__import__('time').time())}"
    state = payload.get("state") or {}
    try:
        meta = draft_service.save(b, name, state)
        return {"ok": True, **meta}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/draft/{bucket}/list")
async def api_draft_list(bucket: str):
    b = _draft_bucket(bucket)
    return {"ok": True, "drafts": draft_service.list_drafts(b)}


@app.get("/api/draft/{bucket}/load")
async def api_draft_load(bucket: str, name: str):
    b = _draft_bucket(bucket)
    data = draft_service.load(b, name)
    if data is None:
        raise HTTPException(404, f"draft not found: {name}")
    return {"ok": True, **data}


@app.post("/api/draft/{bucket}/delete")
async def api_draft_delete(bucket: str, payload: dict):
    b = _draft_bucket(bucket)
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "missing name")
    ok = draft_service.delete(b, name)
    return {"ok": ok}
