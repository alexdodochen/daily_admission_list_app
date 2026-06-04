---
name: subtable H 註記 → 入院序 R 備註 sync
description: 子表格 H「註記」非空時必須同步到入院序區的 R「備註」欄;H 空則保留 R 手填值
type: feedback
---

`ordering_service.integrate_ordering` 與 `sync_ordering_after_diff` 在寫
N-U 入院序時,R 欄(備註)取值規則:

```
R = subtable_H if subtable_H else existing_R
```

**Why:**
- 對齊 reference repo `daily-admission-list-public` 的 canonical mapping
  (其 `feedback_subtable_H_to_R_ordering.md` 與 CLAUDE.md Rule 18 明文)
- 子表格 H 是醫師端的真實意圖(例:不排導管、待會診);R 欄如果不同步,
  入院序區看不到關鍵 flag,Step 5 cathlab keyin 與 LINE 推播會缺資訊
- 但 R 也允許使用者手填(直接在 Google Sheet 編輯),所以 H 空時必須保留 R
  ── 否則使用者的手填會被無腦清掉

**How to apply:**
- 改 `ordering_service.py` 時,R 欄絕對不要寫回 `r[4]`(無腦保留)也不要寫回
  `info["note"]`(無腦覆蓋),要用 `sub_note if sub_note else r[4]` 的 fallback
- Q(備註住服)規則不同 ── 永遠保留 existing Q 或從子表格 I 同步,不從 H 同步
- `sync_ordering_after_diff` 新增 patient(沒有 existing row)的情況,R 直接
  寫 `info.get("note", "")`,因為沒有手填值可保留
- Phase 18 / 2026-05-20:使用者明示「within the 入院序 area 沒錯就是那邊」
