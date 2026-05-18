---
name: all-pages-share-topbar
description: "Every page in the 3-card app must show the same topbar — sub-pages (sched / keyin) MUST `{% extends \"base.html\" %}` and disable Tailwind preflight."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2e27ecbd-39a1-425a-b28b-3c4df41994ad
---

The topbar (主畫面 / 排班 / Key 班 / 入院清單 / 設定 / 📋 查閱 / 🔗 入院 Sheet
/ 🔗 排班 Sheet / 說明) must be identical across every page. User (2026-05-15):
> 你的上方工作列 key班 排班 好像沒有整合
> 長得不一樣
> 我希望他們都長一樣

**Why:** Both `schedule_gen.html` (ported from CV-Schedulling-APP) and
`keyin.html` (ported from Key-Schedule-APP) originally shipped as
self-contained Tailwind pages with their own indigo-700 header. After
integration into the 3-card app they need to share base.html's topbar,
otherwise users hit a different visual language navigating between cards.

**How to apply:**
- Sub-page templates: `{% extends "base.html" %}` + `{% block head_extras %}`
  for Tailwind CDN + page-specific `<style>`, `{% block body %}` for the
  main content (NOT wrapped in `<main>` since base.html provides that),
  `{% block scripts %}` for page-specific `<script>`.
- Disable Tailwind preflight: `tailwind.config = { corePlugins: { preflight: false } }`.
  Otherwise Tailwind's CSS reset would strip base.html's `.topbar`, `.brand`
  and `nav` styling.
- Sub-page routes must pass `cfg`, `ready`, `static_version` in the
  template context — base.html's topbar uses all three. The
  `main._ctx()` helper does this automatically; `keyin_routes.keyin_index`
  builds it manually (don't forget to update).

**Don't:** copy-paste the topbar HTML into each sub-page — when base.html
gets a new nav link (like 📋 查閱 being added in Phase 9), the
copy-pasted ones drift. Extends is the single source of truth.

**Related:** [[strip-auth-for-local-ports]] — same port pattern; auth gets
stripped, but topbar consistency gets ADDED.
