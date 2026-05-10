============================================
  CV_APP Integration HANDOFF — Last Updated: 2026-05-10 evening
============================================

[Project — final direction confirmed at end of 2026-05-10 session]
  Goal: turn THIS repo (public_daily_admission_app) into a 3-feature app
        modeled after CV-Schedulling-APP's home/cards UI pattern.

  Three feature cards on the home page:
    1. 排班   — port the cv_solver + schedule_gen.html flow from CV-Schedulling-APP
    2. key 班 — port the keyin_routes + keyin_index.html flow from CV-Schedulling-APP
    3. 入院清單 (this repo's existing app/) — keep + extend with new rules from
                每日入院名單 main project (5/4-5/10 updates)

  Target repo / where this file is pushed:
    https://github.com/alexdodochen/public_daily_admission_app

  Reference repos (READ-ONLY today; do not modify):
    https://github.com/alexdodochen/CV-Schedulling-APP — for cards 1 & 2 pattern
    https://github.com/alexdodochen/daily-admission-list (private, mirrored from
        D:\心臟內科 總醫師\行政總醫師\每日入院名單) — for admission workflow rules
        and reference impls (cathlab_keyin / process_emr / verify_cathlab /
        webcvis_*.py / schedule_lookup)

  Working dir on this machine:
    D:\心臟內科 總醫師\行政總醫師\CV ALL APP

  Source of v2 admission code already in this repo:
    Was synced from D:\心臟內科 總醫師\行政總醫師\每日入院名單\.claude\worktrees\
        friendly-solomon-026502\app\ (last sync 2026-04-19, 113 unit tests).
    Needs updates for post-4/19 main-project changes (see [Pending updates] below).

  Public data source sheet:
    1u2FZE6-Ldich_b2jI-i0gNnxu1ZsZtZ2Ra6ffCU2Er8 (Claude-admission-sheet-public)
    35 worksheets confirmed: 主治醫師抽籤表 / 主治醫師導管時段表 / 下拉選單 /
        麻醉 / Duration / 35 historical date sheets

[What this 2026-05-10 session did]
  Brainstorming-only. No code written. Design progress:
    1. Verified public sheet structure has all required worksheets.
    2. Decided integration approach: keep this repo's existing app/ as the basis
       for card 3 (入院清單), add cards 1 & 2 by porting from CV-Schedulling-APP.
    3. Locked design rules for card 3 (入院清單):
       a. Step 1 (OCR) — supports same-day re-paste; uses diff-update on subtable
          (only ADD missing chart_no / DELETE absent chart_no, never overwrite
          existing rows). Preserves EMR / F / G / ordering already filled in.
       b. Step 2 (subtables) — group-by-doctor only, no random shuffle. Subtable
          F (術前診斷) and G (預計心導管) cells are inline-editable (contenteditable
          + AJAX blur write — pattern already exists in this repo's v2 app/).
          (NOTE: this differs from main project's admission-lottery skill, which
          keeps random shuffle inside lottery + subtable. Main project intentionally
          NOT backported — different tools, different patterns.)
       c. Step 3 (EMR) — Playwright scrape, write raw EMR text to subtable C
          column with "<age> y/o <gender>\n" prefix. Auto-detect F/G from raw
          text via keyword rules. NO LLM summary (matches main project a824e14).
       d. Step 4 (ordering) — at this stage do the lottery (random shuffle of
          抽籤表 pool) + round-robin (時段組 then 非時段組) + write N-V 9 cols.
       e. Step 5 (cathlab) — week-scan Mon-Fri before ADD; supports
          recommendationDoctor (3rd doctor); Mon EP forces 洪晨惠 as 2nd;
          外科開刀房 25 房 ROOM_CODES; non-schedule 詹週五 → H1 21:00+.
       f. Step 6 (reschedule) — V mark + main A-L copy + subtable rebuild +
          WEBCVIS DEL via chk-checkbox + new cathlab ADD on target date.
    4. LLM providers: 3 supported (Anthropic / OpenAI / Gemini), used for OCR only.
    5. Auth: login bypass like CV-Schedulling-APP (synthetic local admin).

[Current state]
  - This commit: design checkpoint (CV_APP_INTEGRATION_HANDOFF.md only).
  - Existing app/ code: untouched this session (last sync 2026-04-19).
  - No tests changed, no services changed, no templates changed.
  - User explicitly paused implementation: "之後步驟我改天再弄".

[Pending updates — for next session]
  1. Read this file + scan main project's commits since 2026-04-19 to enumerate
     post-sync changes that need to flow into this repo's app/services/*.py.
     Key items already known:
       - cathlab third doctor (recommendationDoctor) field in JSON schema
       - Mon EP 洪晨惠 forced as attendingdoctor2
       - 外科開刀房 25 房 added to ROOM_CODES
       - process_emr writes "XX y/o M\n" prefix to subtable C
       - admission-list age = EMR DOB-based age, not screenshot age
       - WEBCVIS DEL via chk-checkbox (per-row click) — implement in
         reschedule_service for card 3 / Step 6
       - week-scan Mon-Fri before any cathlab ADD (prevent dup)
       - _normalize_diag — angina/unstable → CAD enforcement
       - reschedule full-move workflow (V mark + main copy + subtable rebuild)
       - post-write enforce_sheet_format with SOLID_THICK borders
       - Q col 備註(住服) does NOT default to "V" (user manually marks)
       - 詹世鴻 Friday → non-schedule (lottery + cathlab consistent)
       - 陳則瑋 + 劉秉彥 OPD → cathlab attendingdoctor2 = 劉秉彥
       - 張獻元 Wed admission → same-day PM C2 cathlab (special)
       - 5/4 EMR summary feature dropped — D=EMR摘要 stays as header placeholder

  2. Plan cards 1 & 2 port from CV-Schedulling-APP:
       - cv_solver.py (pure module, 排班 backtracking solver)
       - keyin_routes.py + keyin_scheduler.py + keyin_excel_parser.py
       - templates: schedule_gen.html, keyin_index.html
       - shared infra: gsheet_io.py (NCKU's same SHEET_ID approach)
       - auth bypass pattern (CV-Schedulling-APP does it, this repo also does)

  3. Update home.html / templates/index.html to show 3 cards instead of the
     current single-flow admission UI; admission becomes /admission route.

  4. Update README + this repo's HANDOFF.md (the existing 年度交接指南) to note
     the 3-feature scope expansion.

  5. Service account / Sheet IDs:
       - Default sheet_id in app/bundled/defaults.json must stay as the public
         mirror 1u2FZE6... — never substitute in private SHEET_ID.
       - Per-user LLM key in user-side config.json (already supported).

[Constraints — DO NOT VIOLATE]
  - DO NOT modify https://github.com/alexdodochen/CV-Schedulling-APP. It is
    reference-only. Port code by copying into this repo and adapting.
  - DO NOT modify D:\心臟內科 總醫師\行政總醫師\每日入院名單. Use it as a read-only
    reference for workflow rules and reference impl scripts.
  - PHI safety: this repo is PUBLIC. Never commit real chart numbers, real
    patient names, DOBs, phone numbers, or raw EMR text. Public sheet's date
    sheets are assumed sanitised (35 worksheets contain placeholder data).
  - Internal artifacts (this file, code comments, commit messages, memory files)
    must be in English. User-facing 工作流程 .txt may stay Chinese.

[Known issues / blockers]
  None — paused on user's own decision to resume another day.

[Don't repeat these mistakes]
  - Don't push CV_APP-style code changes into CV-Schedulling-APP repo.
    All implementation lands HERE (public_daily_admission_app).
  - Don't backport CV_APP design rules to 每日入院名單 main project — explicitly
    rejected this session. Main project's admission-lottery / admission-ordering
    skills stay as-is.
  - Don't auto-trigger LLM EMR summary — D column stays as header placeholder.
  - Don't hardcode cathlab PDI/PHC IDs in .py — load from cathlab_id_maps.json.
  - Don't use random.shuffle in subtable writer (Step 2) — randomness only at
    Step 4 ordering.

[Reference notes captured this session]
  - Public mirror sheet structure (35 worksheets) verified via service account
    sigma-sector-492215-d2-0612bef3b39b.json on 2026-05-10. The 35 sheets
    include date sheets going back to 20260330. Assume user-sanitised content.
  - Friendly-solomon-026502 worktree branch latest commit: 34e7ad4 (2026-04-19).
    113 unit tests pass; covers cathlab_service / lottery / ordering / line /
    updater / ocr / emr / llm extract_json / config / main endpoints with
    FastAPI TestClient.
