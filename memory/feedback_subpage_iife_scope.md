---
name: feedback-subpage-iife-scope
description: Any template that extends base.html MUST IIFE-wrap its inline <script> — base.html loads app.js (global const $ = querySelector) and a top-level redeclare aborts the whole inline script
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8f6f0aa1-7ff3-4682-bd49-26deb4d1f986
---

`base.html` loads `/static/app.js` (which declares a global `const $ = (sel,root)=>root.querySelector(sel)`) BEFORE the page's `{% block scripts %}`. Any sub-page (`schedule_gen.html`, `keyin.html`, future ones) that extends base.html and declares its own top-level identifier colliding with app.js — most commonly `function $(id){return document.getElementById(id)}` — triggers an early `SyntaxError: Identifier '$' has already been declared`. That error aborts the **entire** inline `<script>` before any line runs, so **every** handler silently fails to bind (symptom: buttons do nothing, no network request, no obvious error to the user).

This bit us on `/sched` (2026-05-18): 「載入月份資料」button was dead — backend was fine, the inline script just never executed. Fixed by wrapping the whole inline block in an IIFE `(function(){ ... })();`.

**Why:** classic scripts share one global lexical scope; a `const`/`function` redeclaration across separate `<script>` tags is an early error for the second tag. The two `$`s also have different semantics (querySelector vs getElementById, sub-pages call `$('btn-id')` with bare ids), so you can't just delete one and reuse app.js's.

**How to apply:** when porting/creating any template that `{% extends "base.html" %}`, wrap the inline `{% block scripts %}` body in `(function(){ ... })();`. Verify with Playwright: load the page, assert `pageerror` is empty and a key button actually fires its fetch. Generalises [[feedback-all-pages-share-topbar]]. Diagnostic that nails it fast: Playwright `page.on('pageerror')` → "Identifier '$' has already been declared".
