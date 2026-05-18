# Memory index — daily_admission_list_app

- [3-card app integration state](project_3card_app_state.md) — Phase 14 (2026-05-18): Card 1 UI fully ported from Key-Schedule-APP (vs_holiday_exempt/prev_tail/projected_cum) + Step 5 manual edit + exe delivered (麒翔). Commits 7a94419/101f0f1. 335 tests.
- [Sync source cutover — project repo ONLY](feedback_card1_sync_source_cutover.md) — from 2026-05-18 ALL sync is daily_admission_list_app only; never touch Key-Schedule-APP / CV-Schedulling-APP / claude-skills / any other repo
- [Sub-page inline script must IIFE-wrap](feedback_subpage_iife_scope.md) — extends base.html → app.js global $ collides; redeclare aborts whole script → dead buttons. Wrap in (function(){})()
- [Key 班 upstream source](reference_keyin_upstream.md) — port target https://github.com/alexdodochen/Key-Schedule-APP (Phase 11)
- [Local source repos for porting + static data](reference_local_source_repos.md) — `排班 APP\` for CV-Schedulling-APP port; `每日入院名單 Claude\` for missing JSON
- [Strip auth when porting CV-Schedulling-APP code](feedback_strip_auth_for_local_ports.md) — this app is single-user local; never reintroduce login/users/audit
- [Weekday field is op-day, not admission day](feedback_weekday_field_is_op_day.md) — the 星期 select on /admission means 隔天 (= cath/lottery day), auto-fill is `admission +1`
- [NCKUH EMR is a frameset](reference_nckuh_emr_frameset.md) — chart query in topFrame (#txtChartNo+#BTQuery), records in leftFrame, SOAP in mainFrame div.small. FALLBACK_DOCTORS list.
- [Step 2 = build sub-tables, NOT lottery](feedback_step2_no_lottery.md) — lottery moved to Step 4 with 3-layer pin
- [3-layer pin design for 入院序](feedback_pin_layers_separated.md) — E col (within-doctor) / patient pin (global) / doctor pin (RR rank); never conflate
- [F/G must be combobox, not strict select](feedback_fg_combobox_not_select.md) — datalist input; custom F → OTHERS_PDI, custom G → 備註
- [Step 3 must write EMR back to sheet](feedback_step3_must_writeback.md) — extract_patients returns data only; endpoint must call write_results_to_subtables
- [Gemini free tier limits 2026](reference_gemini_free_tier.md) — 2.5-flash-lite has highest RPD (1,000); app default for OCR
- [Sheet writes must TEXT-format chart-no](feedback_sheet_writes_must_text_format_chart.md) — USER_ENTERED strips leading 0s; call ensure_chart_text_format BEFORE write
- [All pages share topbar via extends base](feedback_all_pages_share_topbar.md) — sub-pages must extend base.html + disable Tailwind preflight; never copy-paste header
- [F/G options come from Sheet 下拉選單 tab](feedback_fg_options_from_sheet_dropdown_tab.md) — Sheet col A=F / col D=G is canonical; hardcoded DIAG_RULES only as fallback
- [No column letters in user-facing UI](feedback_no_column_letters_in_ui.md) — never F/G/N-V/T/U/Q to user; always 術前診斷/預計心導管/入院序/備註(住服)/改期 etc.
- [F/G popup must show all on chevron click](feedback_fg_popup_must_show_all_on_click.md) — click ▼ = all options unfiltered; typing = filter; never use native datalist
