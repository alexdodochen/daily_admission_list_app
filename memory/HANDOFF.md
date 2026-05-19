============================================
  HANDOFF — Last Updated: 2026-05-19 02:10
============================================

[What this session did]
  1. Step 5 (導管排程 key-in) UI fully de-jargoned for non-engineer
     用戶 (incoming 行政總醫師):
     - Buttons: 計畫(dry-run)/驗證/Keyin → ①預覽排程(不寫入)/
       ②與現有排程對照(只查)/③開始 key in 排程(寫入)
     - Added foldable 「這三個按鈕在做什麼?」 explainer panel
     - Result headings: ADD→第一階段-建立排程, UPT→第二階段-補上術前
       診斷與預計術式; pdijson/phcjson never shown (explained as the
       data format of 術前診斷/預計術式; pdi=術前診斷, phc=預計術式)
     - Status words: ok/skip/error, OK/NG/SKIP, MISSING → plain Chinese
       (✓成功 / 已存在略過 / ✗失敗 / ✓已在排程 / 還沒進排程 / 沒寫進去)
     - Long log moved into foldable 「詳細執行記錄」
  2. Name 「翁潘淑琴?」 fix — double safety net:
     - backend cathlab_service.read_patients regex extended
       [?？] → [?？�⁇‽]
     - NEW JS cleanName()/escName() in setupStep5: strips trailing
       ?？�⁇‽ at the display layer for ALL Step 5 render paths
       (preview / verify / keyin result) regardless of sheet/old build

[Current state]
  - Branch: main, IN SYNC with origin/main @ 886005f before this work
  - This session's edits NOT yet committed (await user "授權 push")
  - Tests: tests/test_cathlab_service.py 28 passed (regex change safe)
  - Dev server: not running this session

[Next steps]
  - Commit + push (needs explicit user "授權 push"):
    files = app/templates/admission.html, app/static/app.js,
    app/services/cathlab_service.py, memory/*
  - Optional: user clicks through Step 5 on /admission to eyeball copy
  - Carry-over from prev handoff: deliver 麒翔 zip + SA separately;
    /sched real-month solve→手調→套用重算 manual verify

[Known issues / blockers]
  - Push to main gated by auto-mode classifier — needs explicit user
    "授權 push" each time.
  - User reported 「翁潘淑琴?」 from a real run — likely an OLDER
    shipped exe (predates acb012f) or sub-table cell stored the ?.
    JS cleanName() guarantees UI-side fix even on stale builds.

[Don't repeat these mistakes]
  - User-facing copy: NO engineering jargon at all (not just column
    letters) — dry-run/ADD/UPT/pdijson/phcjson/OK-NG-SKIP all banned.
    [[no-column-letters-in-ui]] (now generalised)
  - OCR `?？�` must never reach the screen — strip backend AND add a
    display-layer net.

[Relevant files]
  - app/templates/admission.html (Step 5 panel + explainer details)
  - app/static/app.js (setupStep5: cleanName/escName, renderPlan,
    verify handler, keyin handler wording)
  - app/services/cathlab_service.py:285 (name strip regex)

[Important memory files]
  - feedback_no_column_letters_in_ui.md (GENERALISED 2026-05-19 —
    all jargon, not just letters)
  - project_3card_app_state.md (Phase 14 context)
