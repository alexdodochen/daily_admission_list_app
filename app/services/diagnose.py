"""Map common connection errors to user-actionable suggestions.

When 設定/測試連線 fails, the UI used to dump raw error JSON. This module
produces a structured `{title, cause, suggestions, is_code_bug}` block the
settings UI renders as a friendly tip card so users get a self-service fix
path instead of an inscrutable stack trace.
"""

from __future__ import annotations


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(n in haystack for n in needles)


def diagnose(error_msg: str, *, scope: str) -> dict | None:
    """scope ∈ {'sheet', 'schedule_sheet', 'llm'}.

    Returns None if no pattern matched (UI then falls back to raw error)."""
    if not error_msg:
        return None
    e = error_msg.lower()
    raw = error_msg

    if _contains_any(e, (
        "getaddrinfo failed", "failed to resolve",
        "name or service not known",
        "temporary failure in name resolution",
        "nodename nor servname provided",
        "no address associated with hostname",
        "name resolution",
    )):
        return {
            "title": "DNS 解析失敗 — 網路或防火牆問題",
            "cause": "你的電腦這一刻沒辦法把 Google 伺服器的網域翻譯成 IP。常見原因是 VPN/防火牆擋住、DNS server 暫時掛掉、或公司 / 醫院網路白名單沒放行。",
            "suggestions": [
                "等 30 秒再按一次「② 測試連線」（DNS 經常是短暫故障）",
                "換到不同網路試試看（手機熱點最快驗證 — 若熱點 OK 就是公司網路擋的）",
                "若在醫院 / 公司網路：請 IT 將 *.googleapis.com 加入防火牆白名單",
                "暫時關閉 VPN / 代理伺服器再測一次",
                "若 LLM 顯示正常但 Sheet 失敗，代表 firewall 只擋特定 Google 主機 → 一定是網路規則問題，不是這個 app 的 bug",
            ],
            "is_code_bug": False,
        }

    if _contains_any(e, (
        "timed out", "timeout", "connection refused",
        "connect timeout", "read timeout",
        "connection aborted", "connection reset",
    )):
        return {
            "title": "連線逾時 — 網路太慢或被擋",
            "cause": "送出去的請求超過時限還沒回應。通常是網路太慢、Google 暫時忙、或防火牆悄悄丟封包。",
            "suggestions": [
                "等 30 秒後再按一次「② 測試連線」",
                "確認其他網站打得開（試試 https://google.com）",
                "若有 VPN/Proxy，試試暫時關掉",
            ],
            "is_code_bug": False,
        }

    if _contains_any(e, (
        "403", "forbidden",
        "caller does not have permission",
        "does not have edit permissions",
        "permission_denied", "permissiondenied",
        "the caller does not have",
    )):
        which = "排班 Sheet" if scope == "schedule_sheet" else "Sheet"
        return {
            "title": f"Google 拒絕 — service account 沒被加入「{which}」",
            "cause": "連線到 Google 了，但這個 service account 不是該 Sheet 的協作者。",
            "suggestions": [
                f"打開那份「{which}」→ 右上「共用」",
                "把 service_account.json 裡的 client_email（長長的 xxx@xxx.iam.gserviceaccount.com）加為「編輯者」",
                "加完之後等 30 秒，再按「② 測試連線」",
            ],
            "is_code_bug": False,
        }

    if _contains_any(e, (
        "404", "not found",
        "requested entity was not found",
        "unable to parse range",
    )):
        return {
            "title": "找不到 Sheet — Sheet ID 錯了",
            "cause": "Sheet ID 填錯、那份 Sheet 已被刪除、或搬移到別的位置。",
            "suggestions": [
                "看一下 Google Sheet 網址：https://docs.google.com/spreadsheets/d/【中間這段就是 Sheet ID】/edit",
                "把 Sheet ID 整段重新貼回設定頁的對應欄位，按「① 儲存」再「② 測試連線」",
            ],
            "is_code_bug": False,
        }

    if _contains_any(e, (
        "invalid_grant", "invalid jwt",
        "could not deserialize key",
        "no key could be detected",
        "invalid service account",
        "malformed",
    )):
        return {
            "title": "service account 金鑰無效",
            "cause": "service_account.json 檔案損壞、不是 service account 金鑰、或 GCP 那邊已撤銷。",
            "suggestions": [
                "確認下載的是「service account key」JSON（不是 OAuth client）",
                "回到設定頁按「📁 打開資料夾」確認檔案在那裡",
                "若用了一陣子才壞，可能是 GCP 撤銷了金鑰 → 重新下載一份",
            ],
            "is_code_bug": False,
        }

    if "找不到 service-account" in raw or "service_account.json" in e:
        return {
            "title": "service_account.json 還沒放進去",
            "cause": "App 找不到 service account 金鑰檔。",
            "suggestions": [
                "回到設定頁按「📁 打開資料夾」",
                "把整份 service_account.json 拖進那個資料夾（不要丟到子資料夾）",
                "回來再按「② 測試連線」（不必重啟 app）",
            ],
            "is_code_bug": False,
        }

    if _contains_any(e, (
        "ssl", "certificate_verify_failed",
        "tlsv1", "handshake failure",
        "self-signed certificate",
    )):
        return {
            "title": "SSL/TLS 連線錯誤",
            "cause": "通常是公司網路有中間人攔截（zscaler / 防火牆 / 防毒軟體攔包），或系統時間錯誤。",
            "suggestions": [
                "確認電腦右下角的時間正確（差超過 5 分鐘就會壞 SSL）",
                "若在公司網路：請 IT 確認沒對 *.googleapis.com 做 SSL inspection",
                "暫時關掉防毒軟體的「網路保護」/「SSL 掃描」再測",
            ],
            "is_code_bug": False,
        }

    if _contains_any(e, (
        "quota", "rate_limit_exceeded",
        "429", "rate limit", "resource_exhausted",
    )):
        return {
            "title": "Google API 配額超過",
            "cause": "短時間內測太多次，或 Google 那邊的免費額度用完了。",
            "suggestions": [
                "等 60 秒後再試一次",
                "若連續跳 quota，到 Google Cloud Console 的 Quotas 頁看現況",
            ],
            "is_code_bug": False,
        }

    return None
