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

from datetime import date, datetime

from . import config as appconfig
from . import llm as llm_module
from .services import sheet_service, ocr_service, lottery_service
from .services import emr_service, ordering_service, line_service
from .services import updater, cathlab_service, format_check_service, finalize_service
from .services import cv_solver, scheduling_service
from .services import reschedule_service, upstream

BASE = Path(__file__).parent
app = FastAPI(title="心臟內科總醫師 — 本地版")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

# In-memory cache: solve preview kept here so /write can use it without
# re-running the solver. Single-user local app, so a plain dict is fine.
_solve_cache: dict = {}


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
async def api_update_sync(name: str, restart: str = Form("no")):
    """同步指定 source。
      - name='self'       → git pull 本 App（同 /api/update/apply）
      - name='admission'  → clone/pull daily-admission-list-public + 跑 mirror
      - name='schedule'   → clone/pull Key-Schedule-APP + 跑 mirror
    """
    if name not in upstream.SOURCES:
        raise HTTPException(404, f"未知 source: {name}")
    result = await upstream.sync_source(name)
    if name == "self" and result.get("ok") and restart == "yes":
        updater.schedule_restart()
    return result


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
    try:
        return {"ok": True, "sheets": sheet_service.list_sheets()}
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
        order_block = slice_block(1, main_end, 14, 23) if main_end >= 1 else []

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

    try:
        sheet = scheduling_service.get_sheet()
        baseline = scheduling_service.load_cumulative_stats(sheet)
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
        "sheet_ok": sheet_ok,
        "sheet_err": sheet_err,
    }


@app.post("/api/sched/compute")
async def api_sched_compute(payload: dict):
    year = int(payload["year"])
    month = int(payload["month"])
    X = int(payload["X"])
    baseline = payload.get("baseline") or {}
    targets = cv_solver.compute_initial_targets(year, month, X, baseline)
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

    fixed = {_parse_iso_date(k): v for k, v in fixed_in.items() if v}
    avoid = {n: [_parse_iso_date(d) for d in dates]
             for n, dates in avoid_in.items() if dates}

    result = cv_solver.solve_month(
        year, month, X, fixed, avoid, baseline,
        jk_target=int(jk_target) if jk_target is not None else None,
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
    }
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
        },
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
        scheduling_service.write_calendar_sheet(
            sheet, sheet_name, year, month, schedule,
            scheduling_service.is_taiwan_holiday,
        )
        scheduling_service.write_monthly_stats(
            sheet, f"{sheet_name} 班數統計", stats_rows,
            headers=scheduling_service.DEFAULT_MONTHLY_HEADERS + ["QOD次數"],
        )
        scheduling_service.update_cumulative_stats(sheet, baseline, monthly_stats_map)
    except Exception as e:
        return {"ok": False, "error": f"寫入失敗：{e}"}

    return {"ok": True, "sheet_name": sheet_name}
