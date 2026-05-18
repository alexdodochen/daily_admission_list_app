---
name: gemini-free-tier-2026
description: "Gemini API free tier limits (2026-05). 2.5-flash-lite has highest RPD (1,000). App default for OCR."
metadata: 
  node_type: memory
  type: reference
  originSessionId: 202e121c-0c8f-4e62-891f-fd58ee1476b3
---

Gemini API free tier rate limits as of 2026-05 (verified via WebSearch).

| Model | RPM | RPD | TPM | Context | Notes |
|-------|-----|-----|-----|---------|-------|
| `gemini-2.5-flash-lite` ⭐ | 15 | **1,000** | 250K | 1M | Highest free RPD. App default for OCR. |
| `gemini-2.5-flash` | 10 | 500 | 250K | 1M | Better quality, half the daily limit. |
| `gemini-2.5-pro` | 5 | 100 | 250K | 1M | Best reasoning; not for batch jobs. |
| `gemini-2.0-flash` | — | — | — | — | **Deprecated 2026-03-03**. Migrate to 2.5. |

**Quota rules:**
- RPD = requests per day. Resets at midnight Pacific (~台灣下午 3-4 點).
- TPM = tokens per minute (input + output combined).
- Quotas are per **project**, not per API key.

**App settings:**
- LLM provider = Gemini → model field default placeholder = `gemini-2.5-flash-lite`.
- `/settings` page shows this comparison table inside a `<details>` block
  (`#gemini-info`) that auto-expands when provider = Gemini.

**How to apply:**
- When user complains about "out of quota" → check if they're on 2.5-pro
  (only 100/day); suggest 2.5-flash-lite.
- When recommending a Gemini model for a NEW Claude-internal task, default
  to `gemini-2.5-flash-lite` unless reasoning depth matters (then 2.5-flash).

Sources: ai.google.dev/gemini-api/docs/rate-limits, aifreeapi.com,
tokenmix.ai/blog/gemini-api-free-tier-limits.
