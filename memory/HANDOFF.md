============================================
  HANDOFF — Last Updated: 2026-05-20 (Phase 15)
============================================

[What this session did]
  Shipped a 10-issue field-bug batch from 麒翔's deployed install
  (commit c47d357). All bugs surfaced from real day-to-day use:
  1. ② EMR 註記 → ③ 入院序整合 not syncing — `renderSubtables` H-col
     was a plain <td>; now a `noteInput()` editable input with the
     existing fg-input bidirectional sync wiring.
  2. 主治醫師 / 病人姓名 not canonicalised from EMR — added
     `matched_doctor` flag to `fetch_raw_html`; `extract_visit_doctor`
     parses "<date> <doc> 門診"; `apply_emr_main_fixes` patches main D
     (only when matched_doctor=True, not on FALLBACK visits).
     `_name_variants` strips OCR "?" so "李文煌?" matches.
  3. 吳石秀 / 魏瑞泰 "查無 EMR" — `FALLBACK_DOCTORS` pool grown
     6 → 28 via `_load_cv_doctor_pool()` reading doctor_codes.json.
  4. Same-day re-upload moving patients between subs — `_apply_diff_to_subtables`
     dropped the doctor_changed branch entirely; same chart_no rows
     never touched.
  5. Load-existing-date no longer auto-jumps to Step 4 tab.
  6. 資料檢查 panel moved to bottom of /admission.
  7. New floating ⬆ scroll-to-top button on every page (base.html).
  8. ③ sub-table now shows 性別 + 年齡 (parsed from c_text prefix).
  9. Step 5 per-patient overrides: 「排」 checkbox to skip + 「導管日期」
     date input to shift one patient to a different day. Backend
     `_apply_overrides` whitelist gains `skip` + `cath_date`.
  10. Step 5 missing_after now shows 原因 column paired from Phase-1
      `add_results` row — never bare "✗ 沒寫進去".

[Current state]
  - Branch: main, clean, IN SYNC with origin/main @ c47d357
  - Tests: 372 passed (2 ocr_service tests rewritten for new
    doctor-unchanged rule, all others unchanged)
  - CI release: c47d357 is the next deliverable. GitHub Actions
    should be ~5-10 min into building the release zip when this
    handoff is written.
  - 麒翔's install will pick up all 10 fixes via 🔄 更新 button
    once CI finishes.

[Next steps]
  - Watch the CI build for c47d357 (release asset = ASCII
    admission-app.zip). If it succeeds, tell 麒翔 to click 更新.
  - Field-verify: ask 麒翔 to retry 吳石秀 / 魏瑞泰 EMR fetch
    after updating — should now succeed via the 28-doctor pool.
    If still "查無 EMR" → genuinely no 一年內門診 (any CV doc),
    user fills 註記/F/G manually from inpatient notes.
  - Field-verify: 主治醫師 OCR-typo cases — should now show up
    in the "📝 EMR 自動更正主表" table with field=主治醫師.
  - Carry-over: /sched real-month solve→手調→套用重算 manual
    verify (still pending, low priority).
  - Sub-table title rows (`<doc>（N人）`) NOT auto-renamed when
    main D gets EMR-canonicalised — known limitation, no fix
    queued. Workaround: editable 📋 查閱 viewer for manual rename.

[Known issues / blockers]
  - Pre-0e3501b installs (a68c3da..4eae323) still need ONE manual
    zip download (their updater is the buggy .bat that bricks).
    All current installs should already be on PS1 updater.
  - Public CI release has NO SA + NO 3 cathlab JSONs (PHI by
    design; [[delivery-protocol-inapp-update]]).
  - Sub-table title auto-rename on EMR doctor canon: deferred.

[Don't repeat these mistakes]
  - When user says "不要動" about same-chart_no rows, that means
    EVERYTHING including doctor — don't silently re-apply
    doctor_changed in sub-table sync. [[ocr-reupload-membership-only]]
  - "Verify-after-write" results must pair STATUS with REASON in
    the same row, sourced from the write phase. Don't make users
    dig through detailed logs for a 2-line answer.
    [[missing-after-must-show-reason]]
  - Load / refresh buttons must NOT switch tabs. Hydrate data, leave
    focus alone. [[load-existing-no-tab-jump]]
  - Hardcoded fallback lists go stale as the team grows — union
    with the live JSON (doctor_codes.json) but keep the hardcoded
    floor for sanitised installs. [[emr-fallback-pool-from-doctor-codes]]

[Relevant files]
  - app/services/ocr_service.py (doctor_changed branch removed)
  - app/services/emr_service.py (matched_doctor 4-tuple,
    extract_visit_doctor, _load_cv_doctor_pool, apply_emr_main_fixes D-col)
  - app/services/cathlab_service.py (_apply_overrides skip + cath_date,
    missing_after reason pairing)
  - app/static/app.js (renderSubtables 性別/年齡 + noteInput,
    renderPlan skip/cath_date columns, missing_after reason column,
    scroll-to-top wiring, load-existing no jump)
  - app/static/app.css (.scroll-to-top styling)
  - app/templates/admission.html (資料檢查 → bottom)
  - app/templates/base.html (#scroll-to-top button)
  - tests/test_ocr_service.py (2 doctor_changed tests rewritten)

[Important memory files]
  - feedback_ocr_reupload_membership_only.md (UPDATED — 2026-05-20 rule)
  - reference_emr_fallback_pool_from_doctor_codes.md (NEW)
  - feedback_missing_after_must_show_reason.md (NEW)
  - feedback_load_existing_no_tab_jump.md (NEW)
  - project_emr_doctor_canonicalization.md (NEW)
  - project_3card_app_state.md (UPDATED — Phase 15 prepended)
