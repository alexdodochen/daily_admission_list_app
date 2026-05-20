============================================
  HANDOFF — Last Updated: 2026-05-21 (Phase 16)
============================================

[What this session did]
  Shipped a 7-issue field-batch from 2026-05-21 麒翔 usage, in 3 commits:

  c47fbbc — lottery + cathlab batch (5 fixes):
  1. 5/26 劉嚴文 排到第一位 root cause: Sheet A col is 「星期三」 but
     JS sends 「週三」 — exact-match failed, tickets={} → all non-時段
     random shuffle. `_normalize_weekday_label()` now folds 星期X → 週X
     + strips whitespace/punct. UI surfaces a yellow banner when
     tickets came back empty + lists doctor_groups (🟦時段 / 🟧非時段).
  2. 不排導管 still scheduled: SKIP_KEYWORDS expanded to
     [不排, 不做, 取消, 檢查] + _SKIP_NEGATIVE=[不排除] guard.
     UI placeholder already said 「不排導管」 — backend now matches.
  3. 第二醫師 not auto-keyed (e.g. 詹世鴻 週三 → 許毓軨): ported source
     `schedule_lookup.py` pattern → `read_schedule_overlay()` reads
     admission Sheet 主治醫師導管時段表 A1:G15. Parses 詹世鴻(軨) /
     黃鼎鈞(浩、晨) / EP(李柏增)(晨). Cache busts per Step 5 entry.
  4. 詹世鴻 週五 rule 16: `FRIDAY_DROP_DOCTORS=("詹世鴻",)` auto-pops
     詹 from tickets on 週五 so he lands in Group 2 regardless of sheet.
  5. 第二主治 dropdown: `secondDoctorCombobox()` preset =
     [蘇奕嘉, 葉建寬, 葉立浩, 許毓軨, 洪晨惠] — fg-cell pattern (▼ shows
     all), free-text still allowed.

  d5c8dd4 — EMR preserve + cancel buttons (2 fixes):
  6. Step 3 EMR writeback preserves existing C/F/G: chart with ANY of
     C/F/G non-empty → no patches for those three cells. Returns
     `preserved: [chart_no]`; UI shows 「保留既有 N 位」.
  7. Cancel buttons for long ops: new app/services/cancel_registry.py
     (cooperative checkpoint pattern; module-global flag dict;
     thread-safe). emr_service.extract_patients + cathlab_service.keyin
     accept `op_id`, poll between iterations. Endpoints register
     `step{3,5}_{date}`. New POST /api/op/cancel. admission.html gets
     red ✕ buttons (hidden by default, shown while op runs).

  b7073d1 — divUserSpec race fix (1 critical fix):
  8. 石文明 vs 周素珍 (chart 00385733) root cause: `fetch_raw_html`
     was stamping leftFrame+mainFrame before BTQuery but NOT
     #divUserSpec. divUserSpec lives in a different frame and refreshes
     async — read it without sentinel → got PREVIOUS chart's data
     (off-by-one). EXACT same bug fixed in _verify_query_and_read on
     5/12 (b3815f9) but never ported. Now: stamp divUserSpec across
     all frames + poll for sentinel-gone + 姓名 marker + 400ms settling
     delay + reject sentinel-echo on read.
     Companion: write_results_to_subtables now ALWAYS patches 姓名 (A)
     on EMR canonical-name difference, even when C/F/G preserved —
     otherwise a stuck wrong name can't be auto-corrected.

[Current state]
  - Branch: main, clean, IN SYNC with origin/main @ b7073d1
  - Tests: 416 passed (372 → 403 → 415 → 416 across the 3 commits)
  - CI release: b7073d1 is the latest deliverable. GitHub Actions
    builds the ASCII admission-app.zip; 麒翔's install can pick up
    all 8 fixes via 🔄 更新 button once the workflow finishes.

[Next steps]
  - Field-verify 5/26 lottery: re-run ② 首次抽籤 after pulling. Should
    show flash 「抽籤表 週三：詹世鴻、林佳凌、…」 + 醫師抽序 with
    🟦/🟧 grouping. 劉嚴文 belongs to 🟧 非時段組, ranks LAST in RR.
  - Field-verify chart 00385733: re-run Step 3 EMR. Race fix should
    return 周素珍 (not 石文明). Sub-table A auto-corrects to 周素珍
    even though row C/F/G are preserved.
  - Field-verify 第二醫師 auto-fill: open Step 5 ① 預覽排程. If
    主治醫師導管時段表 has 「詹世鴻(軨)」 in the 週三 cell, all
    詹世鴻 patients on 5/27 should pre-fill 第二主治=許毓軨.
  - Field-verify cancel buttons: trigger Step 3 EMR, click red
    ✕ 取消擷取 — should stop after current patient finishes; flash
    shows 「已取消，剩餘未跑」.

[Known issues / blockers]
  - Pre-fix sub-tables with wrong-name data (e.g. 石文明 stuck on
    00385733): user must re-run Step 3 EMR ONCE; the 姓名 override
    rule patches A on next run; C/F/G stay preserved (manually clear
    them in 📋 查閱 viewer if user wants those re-fetched too).
  - 主治醫師導管時段表 worksheet structure assumed: A1:G15 with
    B=room / C=Mon..G=Fri / rows 2-7=AM / rows 8-12=PM. If user
    changed the layout, overlay returns empty → 第二醫師 not auto-
    filled. Not surfaced as an error currently; consider warning if
    overlay yields zero matches.
  - Sub-table title 「<doctor>（N人）」 still NOT auto-renamed when
    main D gets EMR-canonicalised (carried from Phase 15). Deferred.

[Don't repeat these mistakes]
  - When sheet has 「星期X」 vs JS sends 「週X」: handle via
    `_normalize_weekday_label`; don't add a hardcoded fallback.
    [[lottery-empty-tickets-warning]]
  - When UI placeholder suggests a keyword (e.g. 「不排導管」), backend
    MUST match it. Out-of-sync placeholder/backend = silent bug.
    [[cathlab-skip-keyword-variants]]
  - Reading #divUserSpec without a sentinel after BTQuery → off-by-one
    every time. Stamp + poll, ALWAYS. [[emr-divuserspec-race-fix]]
  - Preserve-existing must NOT lock the 姓名 (A) column — EMR is the
    canonical source for the patient's real name. Only C/F/G are
    preserved. [[emr-preserve-existing]]

[Relevant files]
  - app/services/lottery_service.py (FRIDAY_DROP_DOCTORS, normalize,
    warning, doctor_groups)
  - app/services/cathlab_service.py (SKIP_KEYWORDS expanded,
    note_means_skip, read_schedule_overlay, lookup_schedule_doctors,
    cancel hooks in keyin)
  - app/services/emr_service.py (preserve-existing,
    fetch_raw_html sentinel-stamping #divUserSpec, op_id polling)
  - app/services/cancel_registry.py (NEW)
  - app/static/app.js (yellow lottery banner, doctor_groups display,
    secondDoctorCombobox, cancel button wiring, preserved count flash)
  - app/templates/admission.html (#cancel3-btn + #cancel5-btn)
  - app/main.py (/api/op/cancel, /api/op/list, op_id registration)
  - tests/test_lottery_service.py (rule 16 + normalize tests, 22 total)
  - tests/test_cathlab_service.py (note_means_skip + schedule overlay
    tests, 55 total)
  - tests/test_emr_service.py (5 writeback preserve + 1 name-override)
  - tests/test_cancel_registry.py (NEW)

[Important memory files]
  - feedback_emr_divuserspec_race_fix.md (NEW)
  - feedback_emr_preserve_existing.md (NEW, refined twice)
  - feedback_lottery_empty_tickets_warning.md (NEW)
  - feedback_cathlab_skip_keyword_variants.md (NEW)
  - project_cathlab_schedule_overlay.md (NEW)
  - project_cancel_registry.md (NEW)
