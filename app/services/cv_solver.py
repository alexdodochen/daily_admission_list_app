"""Pure scheduling logic for the cardiology monthly call schedule.

Card 1 (排班) backend. Ported from CV-Schedulling-APP/cv_solver.py. No I/O —
caller supplies year, month, X (展瀚 weekday count), fixed dict, avoid dict,
and baseline cumulative stats; receives schedule + per-doctor stats.

Holiday helpers (TAIWAN_HOLIDAYS, is_taiwan_holiday, make_stat_type_fn) live
here so this module stays self-contained; scheduling_service re-imports them
for the Sheet writers.

Rules:
- CR pool: 麒翔, 見賢, 常胤
- VS pool: 廖瑀, 昭佑, 朝允, 則瑋
- Mid pool: 展瀚 (weekday only), 建寬 (≤ 3 weekday)
- Caps: CR total ≤ 7/month; per-category 週五/週六/週日 hard cap from
  balanced targets; VS ≤ 2/month with ≤ 1 holiday; 建寬 ≤ 3 weekday.
- No back-to-back days for anyone except 展瀚.
- No QOD (D and D±2) for anyone except 展瀚 — hard. If solver fails with
  strict QOD, fall back to relaxed and surface violations.
"""
from __future__ import annotations

import calendar
import random
from datetime import date, timedelta
from typing import Optional


# ── Taiwan holidays (行政院人事行政總處辦公日曆表，含補假) ────────────────
# 週六、週日 already counted; only non-weekend holidays listed here.
TAIWAN_HOLIDAYS: set[date] = {
    # 2025
    date(2025, 9, 29),   # 教師節補假 (9/28 日→9/29 一)
    date(2025, 10, 6),   # 中秋節 (10/5 日→10/6 一)
    date(2025, 10, 10),  # 國慶日 (五)
    date(2025, 10, 24),  # 臺灣光復節補假 (10/25 六→10/24 五)
    date(2025, 12, 25),  # 行憲紀念日 (四)
    # 2026
    date(2026, 1, 1),    # 元旦 (四)
    date(2026, 2, 16),   # 農曆連假 (一)
    date(2026, 2, 17),   # 春節初一 (二)
    date(2026, 2, 18),   # 春節初二 (三)
    date(2026, 2, 19),   # 春節初三 (四)
    date(2026, 2, 20),   # 春節連假 (五)
    date(2026, 2, 27),   # 228 補假 (2/28 六→2/27 五)
    date(2026, 4, 3),    # 兒童節+清明補假 (五)
    date(2026, 4, 6),    # 清明補假 (一)
    date(2026, 5, 1),    # 勞動節 (五)
    date(2026, 6, 19),   # 端午節 (五)
    date(2026, 10, 9),   # 國慶補假 (10/10 六→10/9 五)
    date(2026, 10, 26),  # 臺灣光復節補假 (10/25 日→10/26 一)
    date(2026, 12, 25),  # 行憲紀念日 (五)
}


def is_taiwan_holiday(d: date) -> bool:
    """Weekend or official non-weekend holiday."""
    return d.weekday() >= 5 or d in TAIWAN_HOLIDAYS


def make_stat_type_fn(is_holiday_fn):
    """Classify a date by holiday position.

    - Holiday, next day also holiday  → 週六班 (middle of block)
    - Holiday, next day not holiday   → 週日班 (last day of block)
    - Non-holiday, next day holiday   → 週五班 (day before block)
    - Non-holiday, regular Friday     → 週五班
    - Non-holiday, Mon-Thu            → 平日
    """
    def get_stat_type(d):
        tomorrow = d + timedelta(days=1)
        if is_holiday_fn(d):
            return "週日班" if not is_holiday_fn(tomorrow) else "週六班"
        if is_holiday_fn(tomorrow):
            return "週五班"
        return "週五班" if d.weekday() == 4 else "平日"
    return get_stat_type


# ── Doctor pools ────────────────────────────────────────────────────
CRS: list[str] = ["麒翔", "見賢", "常胤"]
VS_LIST: list[str] = ["廖瑀", "昭佑", "朝允", "則瑋"]
INTER_MID: list[str] = ["展瀚", "建寬"]
ALL_DOCTORS: list[str] = CRS + VS_LIST + INTER_MID

CR_TOTAL_CAP = 7
JK_WEEKDAY_CAP = 3
VS_TOTAL_CAP = 2
VS_HOLIDAY_CAP = 1

# QOD 豁免：所有 VS + 展瀚 + 建寬。CR 才被嚴格 QOD 規則約束。
QOD_EXEMPT_NAMES: set[str] = set(VS_LIST) | {"展瀚", "建寬"}
# QOD 漸進放寬上限：solver 嘗試 max_qod=0..QOD_RELAX_CAP，回傳最少違規解。
QOD_RELAX_CAP = 10


# ── Public helpers ──────────────────────────────────────────────────
def month_days(year: int, month: int) -> list[date]:
    n = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, n + 1)]


def month_h_w(year: int, month: int) -> tuple[int, int]:
    days = month_days(year, month)
    H = sum(1 for d in days if is_taiwan_holiday(d))
    return H, len(days) - H


# ── Step 2/3: compute counts before preferences are collected ───────
def compute_initial_targets(
    year: int,
    month: int,
    X: int,
    baseline: dict,
    vs_holiday_exempt: Optional[list[str]] = None,
) -> dict:
    """Headline counts the UI shows after the user supplies X.

    `vs_holiday_exempt`: names of VS who do NOT take any holiday shift this
    month (e.g. ["朝允", "昭佑"]). Holiday slots distribute only among
    remaining (non-exempt) VS; unmet demand absorbed by CRs (reflected in
    cr_holiday_total). Weekday distribution unaffected.

    Adds projected CR-side numbers (cr_holiday_total / cr_weekday_total /
    cr_per_doctor) so the UI can preview each CR's expected workload.
    """
    days = month_days(year, month)
    H, W = month_h_w(year, month)
    get_stat_type = make_stat_type_fn(is_taiwan_holiday)

    jk = max(0, min(JK_WEEKDAY_CAP, W - 15 - X))
    vs_h_total = max(0, H - 6)
    vs_w_total = max(0, W - 15 - X - jk)

    exempt_set = {n for n in (vs_holiday_exempt or []) if n in VS_LIST}
    non_exempt = [n for n in VS_LIST if n not in exempt_set]

    warnings: list[str] = []
    if vs_w_total > VS_TOTAL_CAP * len(VS_LIST):
        warnings.append("VS 平日缺額已超過 4 人 × 1 班的容量；展瀚 X 可能太低")
    if vs_h_total > VS_HOLIDAY_CAP * len(non_exempt or VS_LIST):
        shortfall = vs_h_total - VS_HOLIDAY_CAP * len(non_exempt)
        if exempt_set:
            warnings.append(
                f"假日需 {vs_h_total} 班，但僅 {len(non_exempt)} 位 VS 可值"
                f"（{ '、'.join(exempt_set) } 豁免）；CR 將額外吃 {max(0, shortfall)} 班假日"
            )
        else:
            warnings.append(
                f"假日缺 {vs_h_total} 班，超過 4 位 VS × 1 = 4 班；CR 假日 ≤ 2 軟上限可能放寬到 3"
            )

    vs_per_doctor: dict[str, dict[str, int]] = {n: {"holiday": 0, "weekday": 0} for n in VS_LIST}

    holiday_order = sorted(
        non_exempt,
        key=lambda n: (
            baseline.get(n, {}).get("假日", 0),
            -(baseline.get(n, {}).get("假日", 0)
              + baseline.get(n, {}).get("平日", 0)
              + baseline.get(n, {}).get("週五", 0)),
        ),
    )
    h_remaining = vs_h_total
    idx = 0
    while h_remaining > 0 and holiday_order:
        vs = holiday_order[idx % len(holiday_order)]
        if vs_per_doctor[vs]["holiday"] < VS_HOLIDAY_CAP:
            vs_per_doctor[vs]["holiday"] += 1
            h_remaining -= 1
        idx += 1
        if idx > len(holiday_order) * 3:
            break

    weekday_order = sorted(
        VS_LIST,
        key=lambda n: baseline.get(n, {}).get("平日", 0) + baseline.get(n, {}).get("週五", 0),
    )
    w_remaining = vs_w_total
    idx = 0
    while w_remaining > 0:
        vs = weekday_order[idx % len(VS_LIST)]
        total = vs_per_doctor[vs]["holiday"] + vs_per_doctor[vs]["weekday"]
        if total < VS_TOTAL_CAP:
            vs_per_doctor[vs]["weekday"] += 1
            w_remaining -= 1
        idx += 1
        if idx > len(VS_LIST) * 3:
            break

    cr_fri_total = sum(1 for d in days if get_stat_type(d) == "週五班")
    cr_sat_total = sum(1 for d in days if get_stat_type(d) == "週六班")
    cr_sun_total = sum(1 for d in days if get_stat_type(d) == "週日班")

    # CR 總班數推算 — vs_h_total / vs_w_total 是「需求」可能超過 VS 容量；
    # vs_per_doctor 才是實際吃下的量；剩下的扣 X / jk 才是 CR 要值的量。
    actual_vs_h = sum(v["holiday"] for v in vs_per_doctor.values())
    actual_vs_w = sum(v["weekday"] for v in vs_per_doctor.values())
    cr_holiday_total = max(0, H - actual_vs_h)
    cr_weekday_total = max(0, W - X - jk - actual_vs_w)
    cr_total = cr_holiday_total + cr_weekday_total
    cr_per_avg = cr_total / 3 if cr_total else 0

    if cr_total > CR_TOTAL_CAP * len(CRS):
        warnings.append(
            f"⚠️ CR 三人需值 {cr_total} 班，超過硬上限 {CR_TOTAL_CAP}×3={CR_TOTAL_CAP*len(CRS)} 班；"
            f"請把展瀚 X 調高 ≥ {X + cr_total - CR_TOTAL_CAP * len(CRS)}，否則 solver 會找不到解。"
        )

    # Per-CR projected count: same balance rule the solver applies, at totals level.
    base_h = cr_holiday_total // 3
    sur_h = cr_holiday_total % 3
    order_h = sorted(CRS, key=lambda n: baseline.get(n, {}).get("假日", 0))
    cr_holiday_split = {n: base_h for n in CRS}
    for i in range(sur_h):
        cr_holiday_split[order_h[i]] += 1

    base_w = cr_weekday_total // 3
    sur_w = cr_weekday_total % 3
    order_w = sorted(CRS, key=lambda n: baseline.get(n, {}).get("平日", 0)
                                          + baseline.get(n, {}).get("週五", 0))
    cr_weekday_split = {n: base_w for n in CRS}
    for i in range(sur_w):
        cr_weekday_split[order_w[i]] += 1

    cr_per_doctor = {
        n: {
            "holiday": cr_holiday_split[n],
            "weekday": cr_weekday_split[n],
            "total": cr_holiday_split[n] + cr_weekday_split[n],
        }
        for n in CRS
    }

    return {
        "H": H,
        "W": W,
        "vs_holiday_total": vs_h_total,
        "vs_weekday_total": vs_w_total,
        "vs_per_doctor": vs_per_doctor,
        "vs_holiday_exempt": sorted(exempt_set),
        "jk_count": jk,
        "cr_fri_total": cr_fri_total,
        "cr_sat_total": cr_sat_total,
        "cr_sun_total": cr_sun_total,
        "cr_holiday_total": cr_holiday_total,
        "cr_weekday_total": cr_weekday_total,
        "cr_total": cr_total,
        "cr_per_avg": cr_per_avg,
        "cr_per_doctor": cr_per_doctor,
        "warnings": warnings,
    }


# ── Step 5: solve ───────────────────────────────────────────────────
def solve_month(
    year: int,
    month: int,
    X: int,
    fixed: dict[date, str],
    avoid: dict[str, list[date]],
    baseline: dict,
    jk_target: Optional[int] = None,
    seed: Optional[int] = None,
    prev_tail: Optional[dict[date, str]] = None,
    vs_holiday_exempt: Optional[list[str]] = None,
) -> Optional[dict]:
    """Backtracking solver. None when no feasible schedule.

    QOD policy: try max_qod=0..QOD_RELAX_CAP, return min-violation feasible.
    `seed=None` → fresh randomness each call → re-running yields different
    valid schedules (lets user pick alternates).
    `prev_tail` = {date: name} from last 2 days of previous month, used so
    back-to-back / QOD checks span the month boundary.
    `vs_holiday_exempt` forwarded to compute_initial_targets for fast-fail.
    """
    days = month_days(year, month)
    get_stat_type = make_stat_type_fn(is_taiwan_holiday)
    rng = random.Random(seed)
    prev_tail = prev_tail or {}

    if jk_target is None:
        H, W = month_h_w(year, month)
        jk_target = max(0, min(JK_WEEKDAY_CAP, W - 15 - X))

    # Fast-fail: even optimistic CR demand exceeds 3 × CR_TOTAL_CAP → no solution.
    init = compute_initial_targets(year, month, X, baseline,
                                    vs_holiday_exempt=vs_holiday_exempt)
    if init["cr_total"] > CR_TOTAL_CAP * len(CRS):
        return None

    # 週五 independent (no holiday overlap). 週六/週日 DERIVED from
    # cr_holiday_target so sat[n]+sun[n] always equals holiday_target[n] —
    # otherwise the three caps can be jointly infeasible.
    cr_fri_target = _category_target(days, fixed, baseline, get_stat_type, "週五班", "週五")
    cr_holiday_target = _holiday_target(days, fixed, baseline)
    cr_sat_target, cr_sun_target = _derive_sat_sun_caps(
        days, fixed, baseline, get_stat_type, cr_holiday_target,
    )

    targets = {
        "cr_fri_target": cr_fri_target,
        "cr_sat_target": cr_sat_target,
        "cr_sun_target": cr_sun_target,
        "cr_holiday_target": cr_holiday_target,
    }

    for max_qod in range(QOD_RELAX_CAP + 1):
        result = _backtrack_run(
            days, fixed, avoid, baseline, jk_target,
            get_stat_type, targets, max_qod=max_qod, rng=rng,
            prev_tail=prev_tail,
        )
        if result is not None:
            schedule = result
            stats_rows, monthly_map = _compute_stats(schedule, get_stat_type)
            qod_violations = _scan_qod(schedule)
            return {
                "schedule": schedule,
                "stats_rows": stats_rows,
                "monthly_stats_map": monthly_map,
                "qod_violations": qod_violations,
                "qod_relaxed": max_qod > 0,
                "max_qod": max_qod,
                "targets": targets,
            }
    return None


def recompute_from_schedule(
    year: int,
    month: int,
    schedule: dict[date, str],
) -> dict:
    """Recompute stats for a manually-edited schedule — no solver run.

    The user is allowed to hand-tweak the solver's output in Step 5 (swap
    who's on which day). This re-derives the per-doctor stats and QOD
    violations from the FINAL edited `{date: name}` map using the exact
    same classification (`make_stat_type_fn` / `_compute_stats`) and QOD
    scan the solver uses, so the written sheet + cumulative reflect the
    edited reality, not the original solve.

    Returns the same shape as `solve_month` minus `targets` (targets stay
    pinned from the original solve — they describe the solver's caps, not
    the edited result). `qod_relaxed`/`max_qod` are informational only here:
    a manual edit can introduce QOD pairs the solver would have avoided,
    so `qod_violations` simply reflects whatever the edited schedule has.
    """
    get_stat_type = make_stat_type_fn(is_taiwan_holiday)
    stats_rows, monthly_map = _compute_stats(schedule, get_stat_type)
    qod_violations = _scan_qod(schedule)
    return {
        "schedule": schedule,
        "stats_rows": stats_rows,
        "monthly_stats_map": monthly_map,
        "qod_violations": qod_violations,
        "qod_relaxed": len(qod_violations) > 0,
        "max_qod": len(qod_violations),
    }


def _category_target(
    days: list[date],
    fixed: dict[date, str],
    baseline: dict,
    get_stat_type,
    stat_label: str,
    cum_key: str,
) -> dict[str, int]:
    cr_eligible = [
        d for d in days
        if get_stat_type(d) == stat_label
        and (d not in fixed or fixed[d] in CRS)
    ]
    fixed_in_cat = {n: 0 for n in CRS}
    for d in cr_eligible:
        if d in fixed:
            fixed_in_cat[fixed[d]] += 1

    n_total = len(cr_eligible)
    base = n_total // len(CRS)
    surplus = n_total % len(CRS)
    order = sorted(CRS, key=lambda n: baseline.get(n, {}).get(cum_key, 0) + fixed_in_cat[n])
    target = {n: base for n in CRS}
    for i in range(surplus):
        target[order[i]] += 1
    for n in CRS:
        if target[n] < fixed_in_cat[n]:
            target[n] = fixed_in_cat[n]
    return target


# ── Internal: total CR holiday target (3-3-2 split when >6) ────────
def _holiday_target(
    days: list[date],
    fixed: dict[date, str],
    baseline: dict,
) -> dict[str, int]:
    """Per-CR cap on total 假日 shifts. Distribute CR-eligible holiday slots
    evenly across CRs; surplus → CRs with LOWEST cumulative 假日 in baseline.
    e.g. 8 holidays → 3-3-2 with the highest-cumulative CR getting the 2.
    """
    cr_eligible = [
        d for d in days
        if is_taiwan_holiday(d)
        and (d not in fixed or fixed[d] in CRS)
    ]
    fixed_in_cat = {n: 0 for n in CRS}
    for d in cr_eligible:
        if d in fixed:
            fixed_in_cat[fixed[d]] += 1

    n_total = len(cr_eligible)
    base = n_total // len(CRS)
    surplus = n_total % len(CRS)
    order = sorted(CRS, key=lambda n: baseline.get(n, {}).get("假日", 0) + fixed_in_cat[n])
    target = {n: base for n in CRS}
    for i in range(surplus):
        target[order[i]] += 1
    for n in CRS:
        if target[n] < fixed_in_cat[n]:
            target[n] = fixed_in_cat[n]
    return target


# ── Internal: derive 週六/週日 caps from holiday cap ────────────────
def _derive_sat_sun_caps(
    days: list[date],
    fixed: dict[date, str],
    baseline: dict,
    get_stat_type,
    holiday_target: dict[str, int],
) -> tuple[dict[str, int], dict[str, int]]:
    """Split each CR's holiday_target into 週六/週日 sub-caps such that
    sat[n]+sun[n]=holiday_target[n] AND sum across CRs equals total sat days.
    Greedy: assign each remaining 週六 slot to the CR with the lowest current
    sat (tiebreak by cumulative 週六). Capped per CR at holiday_target[n].
    """
    cr_eligible_sat = [
        d for d in days
        if get_stat_type(d) == "週六班"
        and (d not in fixed or fixed[d] in CRS)
    ]
    fixed_sat = {n: 0 for n in CRS}
    for d in cr_eligible_sat:
        if d in fixed:
            fixed_sat[fixed[d]] += 1

    sat_cap = dict(fixed_sat)
    remaining = len(cr_eligible_sat) - sum(fixed_sat.values())
    for _ in range(remaining):
        eligible = [n for n in CRS if sat_cap[n] < holiday_target.get(n, 99)]
        if not eligible:
            break
        pick = min(
            eligible,
            key=lambda n: (
                sat_cap[n] - fixed_sat[n],
                baseline.get(n, {}).get("週六", 0),
            ),
        )
        sat_cap[pick] += 1

    sun_cap = {n: max(0, holiday_target.get(n, 0) - sat_cap[n]) for n in CRS}
    return sat_cap, sun_cap


def _backtrack_run(
    days, fixed, avoid, baseline, jk_target,
    get_stat_type, targets, max_qod: int, rng: random.Random,
    prev_tail: Optional[dict[date, str]] = None,
) -> Optional[dict[date, str]]:
    num_days = len(days)
    schedule: dict[date, str] = dict(fixed)
    prev_tail = prev_tail or {}
    cr_w = {n: 0 for n in CRS}
    cr_h = {n: 0 for n in CRS}
    cr_fri = {n: 0 for n in CRS}
    cr_sat = {n: 0 for n in CRS}
    cr_sun = {n: 0 for n in CRS}
    jk_count = 0

    for d, name in fixed.items():
        if name in CRS:
            if is_taiwan_holiday(d):
                cr_h[name] += 1
            else:
                cr_w[name] += 1
            stat = get_stat_type(d)
            if stat == "週五班":
                cr_fri[name] += 1
            elif stat == "週六班":
                cr_sat[name] += 1
            elif stat == "週日班":
                cr_sun[name] += 1
        if name == "建寬":
            jk_count += 1

    for n in CRS:
        if cr_w[n] + cr_h[n] > CR_TOTAL_CAP:
            return None
    if jk_count > jk_target:
        return None

    # Pre-existing QOD pairs from `fixed` count against the budget.
    fixed_pairs = 0
    for d, name in fixed.items():
        if name in QOD_EXEMPT_NAMES:
            continue
        d2 = d + timedelta(days=2)
        if fixed.get(d2) == name:
            fixed_pairs += 1
        d_minus_2 = d - timedelta(days=2)
        if prev_tail.get(d_minus_2) == name:
            fixed_pairs += 1
    if fixed_pairs > max_qod:
        return None
    qod_used = fixed_pairs

    open_days = [d for d in days if d not in fixed]
    # 隨機處理順序：每次跑 solver 從不同日期開始決策 → 探索不同分支 → 不同合規班表
    rng.shuffle(open_days)
    cr_fri_target = targets["cr_fri_target"]
    cr_sat_target = targets["cr_sat_target"]
    cr_sun_target = targets["cr_sun_target"]
    cr_holiday_target = targets["cr_holiday_target"]

    for n in CRS:
        if cr_h[n] > cr_holiday_target.get(n, 99):
            return None

    def neighbor_doctor(target_idx: int) -> Optional[str]:
        """Doctor at relative day index target_idx; falls back to prev_tail
        for indices before day 1 (cross-month boundary check)."""
        if 0 <= target_idx < num_days:
            return schedule.get(days[target_idx])
        if target_idx < 0:
            return prev_tail.get(days[0] + timedelta(days=target_idx))
        return None

    def qod_score(name: str, d_idx: int) -> int:
        if name in QOD_EXEMPT_NAMES:
            return 0
        s = 0
        for off in (-2, 2):
            if neighbor_doctor(d_idx + off) == name:
                s += 1
        return s

    def backtrack(i: int) -> bool:
        nonlocal jk_count, qod_used
        if i == len(open_days):
            return True
        d = open_days[i]
        d_idx = (d - days[0]).days
        is_h = is_taiwan_holiday(d)
        stat = get_stat_type(d)

        if is_h:
            candidates = list(CRS)
        else:
            candidates = list(CRS) + (["建寬"] if jk_count < jk_target else [])

        def sort_key(name: str) -> tuple:
            qp = qod_score(name, d_idx)
            # ±1.5 jitter on balance 讓累計差距 ≤1 的醫師有機會輪換 →
            # 重新跑 solver 產出明顯不同合規班表；硬規則不受影響。
            if name == "建寬":
                return (qp, 99, 99, rng.random())
            cum_key = {"週五班": "週五", "週六班": "週六", "週日班": "週日"}.get(stat, "平日")
            count_dict = {"週五班": cr_fri, "週六班": cr_sat, "週日班": cr_sun}.get(stat, cr_w)
            return (
                qp,
                baseline.get(name, {}).get(cum_key, 0) + count_dict[name] + rng.uniform(0, 1.49),
                cr_w[name] + cr_h[name],
                rng.random(),
            )

        candidates.sort(key=sort_key)

        for name in candidates:
            if name not in QOD_EXEMPT_NAMES:
                # 跨月 back-to-back 檢查：第一天若 prev_tail 最後一天同名 → 拒絕
                if neighbor_doctor(d_idx - 1) == name:
                    continue
                if neighbor_doctor(d_idx + 1) == name:
                    continue
            qod_inc = qod_score(name, d_idx)
            if qod_used + qod_inc > max_qod:
                continue
            if name in avoid and d in avoid[name]:
                continue

            if name in CRS:
                if cr_w[name] + cr_h[name] >= CR_TOTAL_CAP:
                    continue
                if is_h and cr_h[name] >= cr_holiday_target.get(name, 99):
                    continue
                if stat == "週五班" and cr_fri[name] >= cr_fri_target.get(name, 99):
                    continue
                if stat == "週六班" and cr_sat[name] >= cr_sat_target.get(name, 99):
                    continue
                if stat == "週日班" and cr_sun[name] >= cr_sun_target.get(name, 99):
                    continue

            if name == "建寬" and jk_count >= jk_target:
                continue

            schedule[d] = name
            qod_used += qod_inc
            if name in CRS:
                if is_h:
                    cr_h[name] += 1
                else:
                    cr_w[name] += 1
                if stat == "週五班":
                    cr_fri[name] += 1
                elif stat == "週六班":
                    cr_sat[name] += 1
                elif stat == "週日班":
                    cr_sun[name] += 1
            if name == "建寬":
                jk_count += 1

            if backtrack(i + 1):
                return True

            if name in CRS:
                if is_h:
                    cr_h[name] -= 1
                else:
                    cr_w[name] -= 1
                if stat == "週五班":
                    cr_fri[name] -= 1
                elif stat == "週六班":
                    cr_sat[name] -= 1
                elif stat == "週日班":
                    cr_sun[name] -= 1
            if name == "建寬":
                jk_count -= 1
            qod_used -= qod_inc
            del schedule[d]

        return False

    if backtrack(0):
        return schedule
    return None


def _compute_stats(schedule: dict[date, str], get_stat_type) -> tuple[list[dict], dict]:
    stats_rows: list[dict] = []
    by_name: dict[str, dict] = {}
    for name in ALL_DOCTORS:
        personal = [d for d, n in schedule.items() if n == name]
        personal_set = set(personal)
        row = {
            "姓名": name,
            "平日班": sum(1 for d in personal if get_stat_type(d) == "平日"),
            "假日班": sum(1 for d in personal if is_taiwan_holiday(d)),
            "週五班": sum(1 for d in personal if get_stat_type(d) == "週五班"),
            "週六班": sum(1 for d in personal if get_stat_type(d) == "週六班"),
            "週日班": sum(1 for d in personal if get_stat_type(d) == "週日班"),
            "QOD次數": 0 if name in QOD_EXEMPT_NAMES else _qod_count(personal_set),
        }
        stats_rows.append(row)
        by_name[name] = row
    return stats_rows, by_name


def _qod_count(dates_set: set[date]) -> int:
    return sum(1 for d in dates_set if (d + timedelta(days=2)) in dates_set)


def _scan_qod(schedule: dict[date, str]) -> list[tuple[date, str]]:
    by_doctor: dict[str, set[date]] = {}
    for d, n in schedule.items():
        by_doctor.setdefault(n, set()).add(d)
    violations: list[tuple[date, str]] = []
    for n, ds in by_doctor.items():
        if n in QOD_EXEMPT_NAMES:
            continue
        for d in sorted(ds):
            if (d + timedelta(days=2)) in ds:
                violations.append((d, n))
    return violations
