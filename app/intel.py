"""Market-intelligence layer. Pure functions over the sweep's observations,
stored history, and public market data. No I/O."""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional, Sequence

from . import indicators as ind
from .signal import beta_ppf, trader_weight

HOUR_MS = 3_600_000

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _f(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None or v == "":
            return default
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except (TypeError, ValueError):
        return default


def _r(x: Optional[float], nd: int = 4) -> Optional[float]:
    return None if x is None else round(x, nd)


def sign(x: float) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


# ---------------------------------------------------------------------------
# 1. Cohort risk grade
# ---------------------------------------------------------------------------

GRADE_ORDER = "ABCDF"
# Squeeze proximity: notional whose liquidation is closer than this many daily sigmas.
NEAR_Z = 4.0
# Liquidation distance measured in daily one-sigma BTC moves.
Z_BANDS = ((10.0, "A"), (6.0, "B"), (4.0, "C"), (2.5, "D"))
# Daily account volatility = effective leverage * daily BTC sigma.
VOL_BANDS = ((0.05, "A"), (0.10, "B"), (0.20, "C"), (0.35, "D"))


def grade_from_z(z: Optional[float]) -> str:
    if z is None:
        return "A"  # no liquidation price reported: not close to liquidation
    for lo, g in Z_BANDS:
        if z >= lo:
            return g
    return "F"


def grade_from_vol(v: Optional[float]) -> str:
    if v is None:
        return "C"
    for hi, g in VOL_BANDS:
        if v < hi:
            return g
    return "F"


def worse(a: str, b: str) -> str:
    return a if GRADE_ORDER.index(a) >= GRADE_ORDER.index(b) else b


def liq_distance(side: int, mark: float, liq: Optional[float]) -> Optional[float]:
    """Fractional move to liquidation: (mark - liq)/mark for longs, (liq - mark)/mark for shorts."""
    if liq is None or liq <= 0 or mark <= 0:
        return None
    d = (mark - liq) / mark if side > 0 else (liq - mark) / mark
    return max(d, 0.0)


def wallet_risk(row: dict[str, Any], mark: float, sigma_d: float) -> dict[str, Any]:
    side = sign(_f(row.get("btc_szi"), 0.0))
    equity = _f(row.get("equity"), 0.0) or 0.0
    gross = _f(row.get("total_ntl"))
    if gross is None:
        gross = _f(row.get("btc_notional"), 0.0)
    eff_lev = gross / equity if equity > 0 else None
    acct_vol = eff_lev * sigma_d if (eff_lev is not None and sigma_d) else None
    d = liq_distance(side, mark, _f(row.get("liquidation_px")))
    z = d / sigma_d if (d is not None and sigma_d) else None
    grade = worse(grade_from_z(z), grade_from_vol(acct_vol))
    return {"eff_lev": eff_lev, "acct_vol_d": acct_vol, "liq_dist": d, "z": z, "grade": grade}


def cohort_risk(
    observed: Sequence[dict[str, Any]],
    mark: Optional[float],
    sigma_d: Optional[float],
    p_long: Optional[float],
) -> dict[str, Any]:
    if not mark or not sigma_d:
        return {"available": False, "reason": "No BTC mark or volatility estimate."}
    rows = []
    for r in observed:
        szi = _f(r.get("btc_szi"), 0.0) or 0.0
        if szi == 0:
            continue
        risk = wallet_risk(r, mark, sigma_d)
        rows.append({**risk, "side": "LONG" if szi > 0 else "SHORT",
                     "ntl": _f(r.get("btc_notional"), 0.0) or 0.0,
                     "address": r.get("address")})
    if not rows:
        return {"available": False, "reason": "No BTC positions in the cohort."}

    dist = {s: {g: {"n": 0, "ntl": 0.0} for g in GRADE_ORDER} for s in ("LONG", "SHORT")}
    for x in rows:
        cell = dist[x["side"]][x["grade"]]
        cell["n"] += 1
        cell["ntl"] += x["ntl"]

    def side_stats(side: str) -> dict[str, Any]:
        sub = [x for x in rows if x["side"] == side]
        tot = sum(x["ntl"] for x in sub)
        if not sub or tot <= 0:
            return {"n": len(sub), "ntl": tot, "lev_w": None, "z_median_w": None, "df_share": None, "near_share": None}
        lev_w = sum((x["eff_lev"] or 0) * x["ntl"] for x in sub) / tot
        zs = sorted(((x["z"] if x["z"] is not None else 99.0), x["ntl"]) for x in sub)
        acc = 0.0
        zmed = zs[-1][0]
        for z, w in zs:
            acc += w
            if acc >= tot / 2:
                zmed = z
                break
        df = sum(x["ntl"] for x in sub if x["grade"] in "DF") / tot
        near = sum(x["ntl"] for x in sub if x["z"] is not None and x["z"] < NEAR_Z) / tot
        return {"n": len(sub), "ntl": tot, "lev_w": lev_w, "z_median_w": zmed, "df_share": df, "near_share": near}

    longs, shorts = side_stats("LONG"), side_stats("SHORT")
    tot = longs["ntl"] + shorts["ntl"]
    gpa = {g: 4 - i for i, g in enumerate("ABCD")}
    gpa["F"] = 0
    score = sum(gpa[x["grade"]] * x["ntl"] for x in rows) / tot if tot > 0 else None
    agg_grade = None
    if score is not None:
        agg_grade = "A" if score >= 3.5 else "B" if score >= 2.5 else "C" if score >= 1.5 else "D" if score >= 0.75 else "F"

    squeeze = {"level": "LOW", "side_at_risk": None, "text": "The crowd is not both one-sided and close to liquidation."}
    if p_long is not None:
        dom, st = (("SHORT", shorts) if p_long < 0.5 else ("LONG", longs))
        skew = abs(p_long - 0.5) * 2  # 0 balanced, 1 unanimous
        near = st["near_share"] or 0.0
        move = "rally" if dom == "SHORT" else "drop"
        if skew >= 0.5 and near >= 0.10:
            level = "HIGH" if (skew >= 0.7 and near >= 0.25) else "ELEVATED"
            squeeze = {
                "level": level,
                "side_at_risk": dom,
                "text": (
                    f"The crowd is {dom.lower()} (P(long) {p_long:.2f}) and {near * 100:.0f}% of {dom.lower()} "
                    f"notional is within {NEAR_Z:.0f} daily sigmas of liquidation; a sharp {move} could force it "
                    "to close and feed itself."
                ),
            }
        elif skew >= 0.5:
            squeeze = {
                "level": "LOW",
                "side_at_risk": dom,
                "text": (
                    f"The crowd is one-sided {dom.lower()}, but only {near * 100:.0f}% of that notional is within "
                    f"{NEAR_Z:.0f} daily sigmas of liquidation."
                ),
            }
    worst = sorted(rows, key=lambda x: (x["z"] if x["z"] is not None else 1e9))[:8]
    return {
        "available": True,
        "sigma_daily": sigma_d,
        "aggregate_grade": agg_grade,
        "aggregate_score": _r(score, 3),
        "distribution": dist,
        "long": longs,
        "short": shorts,
        "squeeze": squeeze,
        "closest_to_liq": [
            {"address": x["address"], "side": x["side"], "ntl": x["ntl"], "grade": x["grade"],
             "liq_dist": _r(x["liq_dist"]), "z": _r(x["z"], 2), "eff_lev": _r(x["eff_lev"], 2)}
            for x in worst
        ],
        "bands": {"z": Z_BANDS, "acct_vol_daily": VOL_BANDS},
    }


# ---------------------------------------------------------------------------
# 2. Liquidation map
# ---------------------------------------------------------------------------


def liquidation_map(
    observed: Sequence[dict[str, Any]],
    mark: Optional[float],
    bin_pct: float = 1.0,
    span_pct: float = 25.0,
) -> dict[str, Any]:
    if not mark:
        return {"available": False}
    nb = int(round(span_pct / bin_pct))
    edges = [(-span_pct + i * bin_pct) for i in range(2 * nb + 1)]
    bins = [{"lo_pct": edges[i], "hi_pct": edges[i + 1], "long_ntl": 0.0, "short_ntl": 0.0,
             "long_n": 0, "short_n": 0} for i in range(2 * nb)]
    beyond = {"long_ntl": 0.0, "short_ntl": 0.0}
    no_liq = {"long_ntl": 0.0, "short_ntl": 0.0}
    for r in observed:
        szi = _f(r.get("btc_szi"), 0.0) or 0.0
        if szi == 0:
            continue
        key = "long" if szi > 0 else "short"
        ntl = _f(r.get("btc_notional"), 0.0) or 0.0
        liq = _f(r.get("liquidation_px"))
        if liq is None or liq <= 0:
            no_liq[key + "_ntl"] += ntl
            continue
        rel = (liq / mark - 1.0) * 100.0
        if rel < -span_pct or rel >= span_pct:
            beyond[key + "_ntl"] += ntl
            continue
        idx = int((rel + span_pct) // bin_pct)
        idx = min(max(idx, 0), len(bins) - 1)
        bins[idx][key + "_ntl"] += ntl
        bins[idx][key + "_n"] += 1

    def cum(direction: int, within: float, key: str) -> float:
        s = 0.0
        for b in bins:
            mid = (b["lo_pct"] + b["hi_pct"]) / 2
            if direction > 0 and 0 <= mid <= within:
                s += b[key]
            if direction < 0 and -within <= mid <= 0:
                s += b[key]
        return s

    peak_above = max((b for b in bins if b["lo_pct"] >= 0), key=lambda b: b["short_ntl"] + b["long_ntl"], default=None)
    peak_below = max((b for b in bins if b["hi_pct"] <= 0), key=lambda b: b["short_ntl"] + b["long_ntl"], default=None)

    def peak(b):
        if not b or (b["short_ntl"] + b["long_ntl"]) <= 0:
            return None
        mid = (b["lo_pct"] + b["hi_pct"]) / 2
        return {"pct": mid, "price": mark * (1 + mid / 100), "ntl": b["short_ntl"] + b["long_ntl"]}

    return {
        "available": True,
        "mark": mark,
        "bin_pct": bin_pct,
        "span_pct": span_pct,
        "bins": [{**b, "long_ntl": round(b["long_ntl"]), "short_ntl": round(b["short_ntl"])} for b in bins],
        "beyond": beyond,
        "no_liq_px": no_liq,
        "shorts_liq_within_5pct_up": cum(1, 5, "short_ntl"),
        "shorts_liq_within_10pct_up": cum(1, 10, "short_ntl"),
        "longs_liq_within_5pct_down": cum(-1, 5, "long_ntl"),
        "longs_liq_within_10pct_down": cum(-1, 10, "long_ntl"),
        "peak_above": peak(peak_above),
        "peak_below": peak(peak_below),
    }


# ---------------------------------------------------------------------------
# 3 + 4. Flip detector and position-change feed
# ---------------------------------------------------------------------------

ADD_CUT_MIN_FRAC = 0.10
ADD_CUT_MIN_USD = 50_000.0


def classify_change(prev_szi: float, cur_szi: float) -> Optional[str]:
    ps, cs = sign(prev_szi), sign(cur_szi)
    if ps == 0 and cs == 0:
        return None
    if ps == 0:
        return "OPEN"
    if cs == 0:
        return "CLOSE"
    if ps != cs:
        return "FLIP"
    if abs(cur_szi) > abs(prev_szi):
        return "ADD"
    if abs(cur_szi) < abs(prev_szi):
        return "CUT"
    return None


def side_name(s: float) -> str:
    return "LONG" if s > 0 else ("SHORT" if s < 0 else "FLAT")


def position_changes(
    observed: Sequence[dict[str, Any]],
    prev: Optional[dict[str, Any]],
    mark: Optional[float],
    feed_n: int = 15,
) -> dict[str, Any]:
    """Compare per-wallet BTC size with the previous sweep's snapshot.

    prev: {"ts_utc": str, "mark": float, "positions": {address: [szi, ...]}}
    Only wallets present in both sweeps are compared (cohort churn is reported separately).
    """
    if not prev or not prev.get("positions"):
        return {"available": False, "reason": "Baseline stored; changes appear from the next sweep."}
    ppos = prev["positions"]
    px = mark or _f(prev.get("mark"), 0.0) or 0.0
    cur_addrs = set()
    changes = []
    counts = {"OPEN": 0, "CLOSE": 0, "FLIP": 0, "ADD": 0, "CUT": 0}
    flips_to_long = flips_to_short = 0
    dn_total = 0.0
    dw_total = 0.0
    w_abs = 0.0
    for r in observed:
        a = r.get("address")
        cur_addrs.add(a)
        cur = _f(r.get("btc_szi"), 0.0) or 0.0
        eq = _f(r.get("equity"), 0.0) or 0.0
        pnl = _f(r.get("month_pnl"), 0.0) or 0.0
        w_cur = trader_weight(pnl, eq, abs(cur) * px) if cur else 0.0
        w_abs += w_cur
        if a not in ppos:
            continue
        pv = ppos[a]
        p_szi = _f(pv[0] if isinstance(pv, list) else pv, 0.0) or 0.0
        kind = classify_change(p_szi, cur)
        if kind is None:
            continue
        d_btc = cur - p_szi
        d_ntl = d_btc * px
        w_prev = trader_weight(pnl, eq, abs(p_szi) * px) if p_szi else 0.0
        dw_total += sign(cur) * w_cur - sign(p_szi) * w_prev
        if kind in ("ADD", "CUT"):
            if abs(d_btc) < ADD_CUT_MIN_FRAC * abs(p_szi) or abs(d_ntl) < ADD_CUT_MIN_USD:
                dn_total += d_ntl
                continue
        counts[kind] += 1
        dn_total += d_ntl
        if kind == "FLIP":
            if cur > 0:
                flips_to_long += 1
            else:
                flips_to_short += 1
        changes.append({
            "address": a,
            "kind": kind,
            "from": side_name(p_szi),
            "to": side_name(cur),
            "prev_btc": round(p_szi, 5),
            "cur_btc": round(cur, 5),
            "d_btc": round(d_btc, 5),
            "d_ntl": round(d_ntl, 2),
        })
    churn_in = len(cur_addrs - set(ppos))
    churn_out = len(set(ppos) - cur_addrs)
    changes.sort(key=lambda c: abs(c["d_ntl"]), reverse=True)
    return {
        "available": True,
        "since_utc": prev.get("ts_utc"),
        "counts": counts,
        "flips_to_long": flips_to_long,
        "flips_to_short": flips_to_short,
        "net_flips": flips_to_long - flips_to_short,
        "net_notional_flow": round(dn_total, 2),
        "net_weight_flow": dw_total / w_abs if w_abs > 0 else 0.0,
        "cohort_churn_in": churn_in,
        "cohort_churn_out": churn_out,
        "feed": changes[:feed_n],
        "n_changes": len(changes),
    }


def p_delta(history: Sequence[dict[str, Any]], now_p: Optional[float], now_ms: int, hours: float) -> Optional[float]:
    """now_p minus the stored P(long) closest to `hours` ago (within a 40% tolerance)."""
    if now_p is None:
        return None
    target = now_ms - hours * HOUR_MS
    best = None
    for h in history:
        t = h.get("_ms")
        p = h.get("p_long")
        if t is None or p is None:
            continue
        err = abs(t - target)
        if err <= 0.4 * hours * HOUR_MS + 20 * 60_000 and (best is None or err < best[0]):
            best = (err, p)
    return None if best is None else now_p - best[1]


def flip_status(
    changes: dict[str, Any],
    d_p_last: Optional[float],
    d_p_3h: Optional[float],
    d_p_24h: Optional[float],
    n_voters: int,
) -> dict[str, Any]:
    """Plain-language answer to "are traders flipping?"."""
    flow = changes.get("net_weight_flow", 0.0) if changes.get("available") else 0.0
    nf = changes.get("net_flips", 0) if changes.get("available") else 0
    flips = (changes.get("flips_to_long", 0) + changes.get("flips_to_short", 0)) if changes.get("available") else 0
    m3 = d_p_3h if d_p_3h is not None else (d_p_last or 0.0)
    direction = 1 if (m3 + flow) > 0 else -1
    word = "LONG" if direction > 0 else "SHORT"
    nf_share = abs(nf) / n_voters if n_voters else 0.0
    if abs(m3) >= 0.12 or nf_share >= 0.05 or abs(flow) >= 0.10:
        status = f"TURNING {word}"
    elif abs(m3) >= 0.05 or abs(flow) >= 0.04 or nf_share >= 0.02:
        status = f"DRIFTING {word}"
    else:
        status = "STABLE"
    parts = []
    if changes.get("available"):
        parts.append(
            f"{flips} wallet{'s' if flips != 1 else ''} flipped since the last sweep "
            f"({changes['flips_to_long']} to long, {changes['flips_to_short']} to short)"
        )
        parts.append(f"net weight flow {flow * 100:+.1f}% toward {'long' if flow >= 0 else 'short'}")
    else:
        parts.append(changes.get("reason", "No previous sweep to compare.").rstrip("."))
    if d_p_3h is not None:
        parts.append(f"P(long) {d_p_3h:+.3f} over 3h")
    if d_p_24h is not None:
        parts.append(f"{d_p_24h:+.3f} over 24h")
    return {
        "status": status,
        "net_flips": nf,
        "net_weight_flow": flow,
        "d_p_last": d_p_last,
        "d_p_3h": d_p_3h,
        "d_p_24h": d_p_24h,
        "text": "; ".join(parts) + ".",
    }


def market_change_watch(
    flip: dict[str, Any],
    regime: dict[str, Any],
    prev_regime: Optional[str],
    squeeze: dict[str, Any],
    p_long: Optional[float],
    funding_ann: Optional[float],
    ema_state: dict[str, Any],
) -> dict[str, Any]:
    """Combine independent warnings into one 'is the market about to change?' readout."""
    signals = []
    if flip.get("status", "STABLE") != "STABLE":
        signals.append(f"Leaders are {flip['status'].lower()}.")
    if p_long is not None and (0.35 <= p_long <= 0.45 or 0.55 <= p_long <= 0.65):
        signals.append("P(long) sits near a decision threshold; the verdict can change on a small move.")
    if regime.get("label") == "HIGH-VOL":
        signals.append("Volatility is in its top 15% for the month.")
    if prev_regime and regime.get("label") and prev_regime != regime.get("label"):
        signals.append(f"Regime changed from {prev_regime} to {regime['label']}.")
    if squeeze.get("level") in ("ELEVATED", "HIGH"):
        signals.append(f"Squeeze risk {squeeze['level'].lower()} on the {squeeze['side_at_risk'].lower()} side.")
    if funding_ann is not None and abs(funding_ann) >= 0.30:
        signals.append(f"Funding is extreme ({funding_ann * 100:+.0f}% a year).")
    cross = ema_state.get("h1", {}).get("recent_cross")
    if cross:
        signals.append(f"A {cross['kind']} EMA 20/50 cross on 1h candles in the last 12 hours.")
    n = len(signals)
    level = "QUIET" if n == 0 else ("WATCH" if n <= 2 else "ALERT")
    summary = {
        "QUIET": "No warning lights. Positioning and price structure look steady.",
        "WATCH": "One or two warning lights. A change is possible but not signalled strongly.",
        "ALERT": "Several warning lights at once. Conditions that often precede a change are present.",
    }[level]
    return {"level": level, "summary": summary, "signals": signals}


def compact_positions(observed: Sequence[dict[str, Any]]) -> dict[str, float]:
    return {r["address"]: round(_f(r.get("btc_szi"), 0.0) or 0.0, 5) for r in observed if r.get("address")}


# ---------------------------------------------------------------------------
# 6 + 7. Price action, EMA study, regime
# ---------------------------------------------------------------------------


def candle_closes(candles: Sequence[dict[str, Any]]) -> list[float]:
    return [float(c["c"]) for c in candles]


def ema_study(candles_1h: Sequence[dict], candles_1d: Sequence[dict], mark: Optional[float]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, cs, recent in (("h1", candles_1h, 12), ("d1", candles_1d, 5)):
        closes = candle_closes(cs)
        if not closes:
            out[key] = {"available": False}
            continue
        e20, e50, e200 = ind.ema(closes, 20), ind.ema(closes, 50), ind.ema(closes, 200)
        px = mark or closes[-1]
        c2050 = ind.last_cross(e20, e50)
        c50200 = ind.last_cross(e50, e200)
        def at(i):
            return cs[i]["t"] if i is not None else None
        slope50 = None
        if len(e50) > 24 and e50[-1] is not None and e50[-25] is not None:
            slope50 = (e50[-1] - e50[-25]) / e50[-25]
        out[key] = {
            "available": True,
            "price": px,
            "ema20": e20[-1], "ema50": e50[-1], "ema200": e200[-1],
            "dist_ema20": (px / e20[-1] - 1) if e20[-1] else None,
            "dist_ema50": (px / e50[-1] - 1) if e50[-1] else None,
            "dist_ema200": (px / e200[-1] - 1) if e200[-1] else None,
            "state": ind.ema_trend_state(px, e20[-1], e50[-1], e200[-1]),
            "cross_20_50": {**c2050, "t": at(c2050["index"])} if c2050 else None,
            "cross_50_200": {**c50200, "t": at(c50200["index"])} if c50200 else None,
            "recent_cross": ({**c2050, "t": at(c2050["index"])}
                             if c2050 and c2050["index"] >= len(closes) - recent else None),
            "slope50": slope50,
            "_e20": e20, "_e50": e50, "_e200": e200,
        }
    return out


def price_action(candles_1h: Sequence[dict], candles_1d: Sequence[dict], mark: Optional[float]) -> dict[str, Any]:
    if not candles_1h:
        return {"available": False}
    px = mark or float(candles_1h[-1]["c"])
    def ret(cs, n):
        if len(cs) <= n:
            return None
        base = float(cs[-1 - n]["c"])
        return px / base - 1 if base else None
    last24 = candles_1h[-24:]
    hi24 = max(float(c["h"]) for c in last24)
    lo24 = min(float(c["l"]) for c in last24)
    last7 = candles_1h[-168:]
    hi7 = max(float(c["h"]) for c in last7)
    lo7 = min(float(c["l"]) for c in last7)
    return {
        "available": True,
        "price": px,
        "ret_1h": ret(candles_1h, 1),
        "ret_4h": ret(candles_1h, 4),
        "ret_24h": ret(candles_1h, 24),
        "ret_7d": ret(candles_1h, 168),
        "ret_30d": ret(candles_1d, 30) if candles_1d else None,
        "high_24h": hi24, "low_24h": lo24,
        "high_7d": hi7, "low_7d": lo7,
        "pos_in_7d_range": (px - lo7) / (hi7 - lo7) if hi7 > lo7 else None,
    }


def sigma_daily(candles_1h: Sequence[dict], hours: int = 168) -> Optional[float]:
    closes = candle_closes(candles_1h[-(hours + 1):])
    sd = ind.stdev(ind.log_returns(closes))
    return None if sd is None else sd * math.sqrt(24)


def regime(candles_1h: Sequence[dict], funding_ann: Optional[float], ema_h1: dict[str, Any]) -> dict[str, Any]:
    closes = candle_closes(candles_1h)
    if len(closes) < 100:
        return {"label": "UNKNOWN", "detail": "Not enough candles."}
    rv24 = ind.realized_vol(closes[-25:], 24 * 365)
    series = ind.rolling_vol_series(closes, 24, 24 * 365)
    pct = ind.percentile_rank(series, rv24) if rv24 is not None else None
    er = ind.efficiency_ratio(closes[-49:])
    ret24 = closes[-1] / closes[-25] - 1
    slope = ema_h1.get("slope50") or 0.0
    out = ind.classify_regime(pct, er, ret24, sign(slope))
    out.update({
        "rv_24h_ann": rv24,
        "rv_pct_30d": pct,
        "efficiency_ratio_48h": er,
        "ema50_slope_24h": slope,
        "funding_ann": funding_ann,
    })
    if funding_ann is not None and abs(funding_ann) >= 0.30:
        out["funding_note"] = "Funding is extreme; one side is paying heavily to hold."
    return out


# ---------------------------------------------------------------------------
# 8. Fear / greed
# ---------------------------------------------------------------------------


def _band(score: float) -> str:
    if score < 25:
        return "EXTREME FEAR"
    if score < 45:
        return "FEAR"
    if score <= 55:
        return "NEUTRAL"
    if score <= 75:
        return "GREED"
    return "EXTREME GREED"


def fear_greed(
    *,
    funding_ann: Optional[float],
    p_post: Optional[float],
    rv_pct: Optional[float],
    ret_7d: Optional[float],
    sigma_d: Optional[float],
    oi_change_24h: Optional[float],
    ret_24h: Optional[float],
) -> dict[str, Any]:
    comps = []
    if funding_ann is not None:
        comps.append(("Funding", 50 + 50 * math.tanh(funding_ann / 0.25),
                      f"{funding_ann * 100:+.1f}% a year; longs paying is greed."))
    if p_post is not None:
        comps.append(("Leader skew", 100 * p_post,
                      f"Posterior P(long) {p_post:.2f}; leaders long is greed."))
    if rv_pct is not None:
        comps.append(("Volatility", 100 * (1 - rv_pct),
                      f"24h vol at the {rv_pct * 100:.0f}th percentile of 30 days; high vol is fear."))
    if ret_7d is not None and sigma_d:
        z = ret_7d / (sigma_d * math.sqrt(7))
        comps.append(("Momentum", 50 + 50 * math.tanh(z / 2),
                      f"7-day return {ret_7d * 100:+.1f}% ({z:+.1f} sigma)."))
    if oi_change_24h is not None and ret_24h is not None:
        comps.append(("Open interest", 50 + 50 * math.tanh(sign(ret_24h) * oi_change_24h / 0.05),
                      f"OI {oi_change_24h * 100:+.1f}% in 24h while price {ret_24h * 100:+.1f}%."))
    if not comps:
        return {"available": False}
    score = sum(c[1] for c in comps) / len(comps)
    return {
        "available": True,
        "score": round(score, 1),
        "band": _band(score),
        "components": [{"name": n, "score": round(s, 1), "note": t} for n, s, t in comps],
        "missing": [n for n in ("Funding", "Leader skew", "Volatility", "Momentum", "Open interest")
                    if n not in {c[0] for c in comps}],
    }


# ---------------------------------------------------------------------------
# 11. Fake-signal detector
# ---------------------------------------------------------------------------


def concentration(weights: Iterable[float]) -> dict[str, Any]:
    ws = sorted((w for w in weights if w > 0), reverse=True)
    tot = sum(ws)
    if tot <= 0:
        return {"hhi": None, "n_eff": 0.0, "top5_share": None, "top1_share": None}
    shares = [w / tot for w in ws]
    hhi = sum(s * s for s in shares)
    return {"hhi": hhi, "n_eff": 1.0 / hhi, "top5_share": sum(shares[:5]), "top1_share": shares[0]}


def p_without_top(signed: Sequence[tuple[int, float]], k: int) -> Optional[float]:
    items = sorted(signed, key=lambda sw: sw[1], reverse=True)[k:]
    wl = sum(w for s, w in items if s > 0)
    ws = sum(w for s, w in items if s < 0)
    return wl / (wl + ws) if (wl + ws) > 0 else None


def hedge_like(row: dict[str, Any], turnover_mm: float = 50.0) -> Optional[str]:
    szi = _f(row.get("btc_szi"), 0.0) or 0.0
    if szi == 0:
        return None
    btc_ntl = _f(row.get("btc_notional"), 0.0) or 0.0
    other = _f(row.get("other_signed_ntl"), 0.0) or 0.0
    if btc_ntl > 0 and sign(other) == -sign(szi) and abs(other) >= 0.7 * btc_ntl:
        return "hedged"
    if (_f(row.get("turnover"), 0.0) or 0.0) >= turnover_mm:
        return "high-turnover"
    return None


def fake_signal(
    *,
    signal: dict[str, Any],
    observed: Sequence[dict[str, Any]],
    signed: Sequence[tuple[int, float]],
    data_age_sec: float = 0.0,
) -> dict[str, Any]:
    from .signal import verdict_from_p

    p = signal.get("p_long")
    conc = concentration(w for _, w in signed)
    n_voters = signal.get("n_long", 0) + signal.get("n_short", 0)
    n_traders = signal.get("n_traders", 0) or 0
    checks = []

    def add(name, flagged, value, rule):
        checks.append({"name": name, "flag": bool(flagged), "value": value, "rule": rule})

    add("Effective voters", conc["n_eff"] < 10, f"{conc['n_eff']:.1f}", "flag if 1/HHI < 10")
    add("Top-5 weight share", (conc["top5_share"] or 0) > 0.5,
        f"{(conc['top5_share'] or 0) * 100:.0f}%", "flag if > 50%")
    p5 = p_without_top(signed, 5)
    flip5 = p is not None and p5 is not None and verdict_from_p(p5) != verdict_from_p(p)
    add("Leave-top-5-out", flip5, f"{p5:.3f}" if p5 is not None else "n/a",
        "flag if the verdict changes without the 5 heaviest wallets")
    lo, hi = signal.get("ci_low"), signal.get("ci_high")
    width = (hi - lo) if (lo is not None and hi is not None) else None
    add("Interval width", width is None or width > 0.30 or (lo <= 0.5 <= hi),
        f"{width:.3f}" if width is not None else "n/a", "flag if > 0.30 or it spans 0.50")
    add("Participation", n_voters < 50 or (n_traders and n_voters / n_traders < 0.15),
        f"{n_voters} of {n_traders}", "flag if < 50 voters or < 15% of the cohort")
    hw = 0.0
    tw = 0.0
    weights = {a: w for a, w in _weights_by_addr(observed)}
    for r in observed:
        w = weights.get(r.get("address"), 0.0)
        tw += w
        if hedge_like(r):
            hw += w
    hshare = hw / tw if tw > 0 else 0.0
    add("Hedger / MM-like weight", hshare > 0.30, f"{hshare * 100:.0f}%",
        "flag if > 30% of weight is hedged elsewhere or turns over >= 50x a month")
    cnt_p = signal.get("n_long", 0) / n_voters if n_voters else None
    disagree = p is not None and cnt_p is not None and (p - 0.5) * (cnt_p - 0.5) < 0
    add("Count vs weight", disagree, f"{cnt_p:.2f} by count" if cnt_p is not None else "n/a",
        "flag if the head-count share and weighted share fall on opposite sides of 0.50")
    add("Data age", data_age_sec > 2 * 3600, f"{data_age_sec / 60:.0f} min", "flag if older than 2 hours")
    n_flags = sum(1 for c in checks if c["flag"])
    status = "CLEAN" if n_flags == 0 else ("CAUTION" if n_flags <= 2 else "SUSPECT")
    return {
        "status": status,
        "n_flags": n_flags,
        "checks": checks,
        "n_eff": conc["n_eff"],
        "hhi": conc["hhi"],
        "top5_share": conc["top5_share"],
        "p_without_top5": p5,
        "hedge_weight_share": hshare,
    }


def _weights_by_addr(observed: Sequence[dict[str, Any]]):
    for r in observed:
        szi = _f(r.get("btc_szi"), 0.0) or 0.0
        if szi == 0:
            continue
        yield r.get("address"), trader_weight(
            _f(r.get("month_pnl"), 0.0) or 0.0,
            _f(r.get("equity"), 0.0) or 0.0,
            _f(r.get("btc_notional"), 0.0) or 0.0,
        )


# ---------------------------------------------------------------------------
# 13. Bayesian updating (exponentially forgotten Beta-Binomial)
# ---------------------------------------------------------------------------

BAYES_HALF_LIFE_H = 6.0
BAYES_K_CAP = 50.0
BAYES_K_DEFAULT = 25.0
BAYES_PRIOR = (1.0, 1.0)


def bayes_replay(points: Sequence[dict[str, Any]], half_life_h: float = BAYES_HALF_LIFE_H) -> list[dict[str, Any]]:
    """Replay history oldest-first.

    A_t = lam_t * A_{t-1} + (1 - lam_t) * K_t * p_t,  B_t likewise with (1 - p_t),
    lam_t = 2^(-dt / half_life). Posterior Beta(a0 + A_t, b0 + B_t).
    K_t is the effective number of voters, capped, so repeated looks at the same
    positions do not inflate certainty.
    """
    a0, b0 = BAYES_PRIOR
    A = B = 0.0
    last_ms = None
    out = []
    for pt in points:
        p = pt.get("p_long")
        t = pt.get("_ms")
        if p is None or t is None:
            continue
        k = min(_f(pt.get("n_eff"), BAYES_K_DEFAULT) or BAYES_K_DEFAULT, BAYES_K_CAP)
        if last_ms is None:
            lam = 2 ** (-0.5 / half_life_h)  # the first look counts like one 30-minute step
        else:
            dt_h = max(0.0, (t - last_ms) / HOUR_MS)
            lam = 2 ** (-dt_h / half_life_h)
        A = lam * A + (1 - lam) * k * p
        B = lam * B + (1 - lam) * k * (1 - p)
        last_ms = t
        a, b = a0 + A, b0 + B
        out.append({"_ms": t, "a": a, "b": b, "mean": a / (a + b)})
    return out


def bayes_summary(replayed: Sequence[dict[str, Any]], raw_p: Optional[float]) -> dict[str, Any]:
    if not replayed:
        return {"available": False}
    last = replayed[-1]
    a, b = last["a"], last["b"]
    return {
        "available": True,
        "posterior_mean": a / (a + b),
        "ci_low": beta_ppf(0.025, a, b),
        "ci_high": beta_ppf(0.975, a, b),
        "alpha": a,
        "beta": b,
        "raw_p": raw_p,
        "gap": (raw_p - a / (a + b)) if raw_p is not None else None,
        "half_life_h": BAYES_HALF_LIFE_H,
        "k_cap": BAYES_K_CAP,
        "prob_long_side": 1.0 - _beta_cdf_half(a, b),
    }


def _beta_cdf_half(a: float, b: float) -> float:
    from .signal import _betainc
    return _betainc(0.5, a, b)


# ---------------------------------------------------------------------------
# 14. Accuracy tracker
# ---------------------------------------------------------------------------

HORIZONS_H = (1, 4, 24)
EXTREME_LO, EXTREME_HI = 0.15, 0.85


class PriceLookup:
    """Price at time t from candles (close of the candle containing t),
    falling back to the nearest stored mark within 20 minutes."""

    def __init__(self, candles: Sequence[dict], marks: Sequence[tuple[int, float]]):
        self.c = sorted(((int(c["t"]), int(c["T"]), float(c["c"])) for c in candles), key=lambda x: x[0])
        self.marks = sorted(marks)
        self.max_t = self.c[-1][1] if self.c else (self.marks[-1][0] if self.marks else 0)

    def at(self, t: int) -> Optional[float]:
        lo, hi = 0, len(self.c) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            s, e, px = self.c[mid]
            if t < s:
                hi = mid - 1
            elif t > e:
                lo = mid + 1
            else:
                return px
        best = None
        for mt, mp in self.marks:
            err = abs(mt - t)
            if err <= 20 * 60_000 and (best is None or err < best[0]):
                best = (err, mp)
        return best[1] if best else None


def accuracy(points: Sequence[dict[str, Any]], prices: PriceLookup, now_ms: int) -> dict[str, Any]:
    out = {}
    extreme = {}
    for h in HORIZONS_H:
        n = hits = n_dir = 0
        bs_raw = bs_post = 0.0
        n_post = 0
        ys = []
        pending = 0
        ext_n = ext_hits = 0
        for pt in points:
            t, p0 = pt.get("_ms"), pt.get("btc_mark")
            p = pt.get("p_long")
            if t is None or p0 is None or p is None:
                continue
            if t + h * HOUR_MS > now_ms:
                pending += 1
                continue
            p1 = prices.at(t + h * HOUR_MS)
            if p1 is None or p1 == p0:
                continue
            y = 1.0 if p1 > p0 else 0.0
            ys.append(y)
            n += 1
            bs_raw += (p - y) ** 2
            if pt.get("post") is not None:
                bs_post += (pt["post"] - y) ** 2
                n_post += 1
            v = pt.get("verdict")
            if v in ("LONG", "SHORT"):
                n_dir += 1
                if (v == "LONG") == (y == 1.0):
                    hits += 1
            if p <= EXTREME_LO or p >= EXTREME_HI:
                ext_n += 1
                if (p >= EXTREME_HI) == (y == 1.0):
                    ext_hits += 1
        base = sum(ys) / len(ys) if ys else None
        span_h = 0.0
        scored = [pt["_ms"] for pt in points if pt.get("_ms") is not None and pt["_ms"] + h * HOUR_MS <= now_ms]
        if len(scored) >= 2:
            span_h = (max(scored) - min(scored)) / HOUR_MS
        out[f"{h}h"] = {
            "n": n,
            "n_directional": n_dir,
            "hit_rate": hits / n_dir if n_dir else None,
            "brier_raw": bs_raw / n if n else None,
            "brier_post": bs_post / n_post if n_post else None,
            "brier_coin": 0.25,
            "brier_climatology": base * (1 - base) if base is not None else None,
            "base_rate_up": base,
            "independent_n_approx": max(1, int(span_h / h) + 1) if n else 0,
            "pending": pending,
        }
        extreme[f"{h}h"] = {
            "n": ext_n,
            "follow_hit_rate": ext_hits / ext_n if ext_n else None,
            "fade_hit_rate": (1 - ext_hits / ext_n) if ext_n else None,
        }
    return {"horizons": out, "extreme": extreme}


# ---------------------------------------------------------------------------
# 10. Contrarian mode
# ---------------------------------------------------------------------------


def contrarian(verdict: str, p_long: Optional[float], acc: dict[str, Any]) -> dict[str, Any]:
    faded = {"LONG": "SHORT", "SHORT": "LONG"}.get(verdict, "NEUTRAL")
    extreme = p_long is not None and (p_long <= EXTREME_LO or p_long >= EXTREME_HI)
    ev = acc.get("extreme", {}).get("24h", {}) if acc else {}
    n = ev.get("n", 0) or 0
    fade = ev.get("fade_hit_rate")
    if n < 30:
        judgement = (
            f"Not enough scored extreme readings yet ({n} at 24h; 30 wanted before any claim). "
            "Fading is shown for comparison only."
        )
        argues = None
    elif fade is not None and fade > 0.55:
        judgement = f"At extremes, fading has been right {fade * 100:.0f}% of the time at 24h (n={n}, overlapping)."
        argues = True
    else:
        judgement = f"At extremes, fading has been right {((fade or 0) * 100):.0f}% of the time at 24h (n={n}); no edge for fading."
        argues = False
    return {
        "verdict": verdict,
        "faded_verdict": faded,
        "faded_p_long": (1 - p_long) if p_long is not None else None,
        "extreme_now": extreme,
        "extreme_band": [EXTREME_LO, EXTREME_HI],
        "evidence_n": n,
        "fade_hit_rate_24h": fade,
        "argues_for_fading": argues,
        "text": judgement,
    }


# ---------------------------------------------------------------------------
# 12. Funding and open interest
# ---------------------------------------------------------------------------


def funding_series(rows: Sequence[dict[str, Any]], bucket_h: int = 8) -> list[dict[str, Any]]:
    buckets: dict[int, list[float]] = {}
    size = bucket_h * HOUR_MS
    for r in rows:
        t = int(r["time"])
        rate = _f(r.get("fundingRate"))
        if rate is None:
            continue
        buckets.setdefault(t // size * size, []).append(rate)
    return [{"t": k, "rate_h": sum(v) / len(v), "ann": sum(v) / len(v) * 24 * 365}
            for k, v in sorted(buckets.items())]


def funding_oi(
    ctx: dict[str, Any],
    funding_rows: Sequence[dict[str, Any]],
    history: Sequence[dict[str, Any]],
    verdict: str,
    now_ms: int,
) -> dict[str, Any]:
    rate = _f(ctx.get("funding"))
    oi = _f(ctx.get("openInterest"))
    mark = _f(ctx.get("markPx"))
    ann = rate * 24 * 365 if rate is not None else None
    rates = [_f(r.get("fundingRate")) for r in funding_rows if _f(r.get("fundingRate")) is not None]
    avg7 = None
    recent = [_f(r.get("fundingRate")) for r in funding_rows if int(r["time"]) >= now_ms - 7 * 24 * HOUR_MS]
    recent = [x for x in recent if x is not None]
    if recent:
        avg7 = sum(recent) / len(recent) * 24 * 365
    pct = ind.percentile_rank(rates, rate) if (rates and rate is not None) else None
    oi24 = None
    best = None
    for h in history:
        if h.get("oi") is None or h.get("_ms") is None:
            continue
        err = abs(h["_ms"] - (now_ms - 24 * HOUR_MS))
        if err <= 3 * HOUR_MS and (best is None or err < best[0]):
            best = (err, h["oi"])
    if best and oi:
        oi24 = oi / best[1] - 1 if best[1] else None
    fs = sign(rate or 0.0)
    if verdict == "SHORT" and fs < 0:
        reading = "Leaders short and shorts are paying longs: the short side is crowded. Fuel for a squeeze if price rises."
    elif verdict == "SHORT":
        reading = "Leaders short while longs pay funding: leaders are leaning against a long-paying market."
    elif verdict == "LONG" and fs > 0:
        reading = "Leaders long and longs are paying shorts: the long side is crowded. Fuel for a flush if price falls."
    elif verdict == "LONG":
        reading = "Leaders long while shorts pay funding: leaders are leaning against a short-paying market."
    else:
        reading = "Leaders have no clear lean; funding alone sets the tone."
    return {
        "funding_rate_h": rate,
        "funding_ann": ann,
        "funding_ann_avg_7d": avg7,
        "funding_pct_30d": pct,
        "oi_btc": oi,
        "oi_usd": oi * mark if (oi and mark) else None,
        "oi_change_24h": oi24,
        "premium": _f(ctx.get("premium")),
        "day_ntl_vlm": _f(ctx.get("dayNtlVlm")),
        "series_8h": funding_series(funding_rows),
        "reading": reading,
    }


# ---------------------------------------------------------------------------
# 15 + 16. Lead-lag and front-running
# ---------------------------------------------------------------------------


def grid_series(points: Sequence[dict[str, Any]], step_ms: int, key: str,
                t0_ms: Optional[int] = None, t1_ms: Optional[int] = None) -> list[Optional[float]]:
    """Bucket points onto a regular grid; last value per bucket; gaps are None.

    Pass the same t0_ms / t1_ms for several keys so their grids align.
    """
    timed = [p for p in points if p.get("_ms") is not None]
    if not timed:
        return []
    t0 = (t0_ms if t0_ms is not None else min(p["_ms"] for p in timed)) // step_ms
    t1 = (t1_ms if t1_ms is not None else max(p["_ms"] for p in timed)) // step_ms
    grid: list[Optional[float]] = [None] * (t1 - t0 + 1)
    for p in timed:
        i = p["_ms"] // step_ms - t0
        if 0 <= i < len(grid) and p.get(key) is not None:
            grid[i] = float(p[key])
    return grid


def diffs(series: Sequence[Optional[float]], log: bool = False) -> list[Optional[float]]:
    out: list[Optional[float]] = [None]
    for i in range(1, len(series)):
        a, b = series[i - 1], series[i]
        if a is None or b is None:
            out.append(None)
        elif log:
            out.append(math.log(b / a) if a > 0 and b > 0 else None)
        else:
            out.append(b - a)
    return out


def lead_lag(x_level: Sequence[Optional[float]], price: Sequence[Optional[float]], max_lag: int,
             step_label: str, source: str) -> dict[str, Any]:
    dx = diffs(x_level)
    ry = diffs(price, log=True)
    ccf = ind.cross_correlation(dx, ry, max_lag)
    n0 = next((c["n"] for c in ccf if c["lag"] == 0), 0)
    band = 1.96 / math.sqrt(n0) if n0 > 3 else None
    valid = [c for c in ccf if c["r"] is not None]
    peak = max(valid, key=lambda c: abs(c["r"]), default=None)
    score = ind.lead_score(ccf)
    enough = n0 >= 30
    if not valid:
        text = "Not enough paired observations yet."
    else:
        k = peak["lag"]
        sig = band is not None and abs(peak["r"]) > band
        if k > 0:
            what = f"position changes lead price by {k} {step_label}"
        elif k < 0:
            what = f"position changes follow price by {-k} {step_label}"
        else:
            what = "position changes and price move in the same step"
        text = (f"Strongest correlation r = {peak['r']:+.2f} at lag {k:+d}: {what}. "
                f"{'Outside' if sig else 'Inside'} the ±{band:.2f} noise band (n = {n0})." if band else what)
        if not enough:
            text += " Sample is small; read as provisional."
    return {
        "source": source,
        "step": step_label,
        "ccf": [{"lag": c["lag"], "r": _r(c["r"], 3), "n": c["n"]} for c in ccf],
        "n": n0,
        "noise_band": band,
        "peak": peak and {"lag": peak["lag"], "r": _r(peak["r"], 3)},
        "lead_score": _r(score, 3),
        "enough": enough,
        "text": text,
    }


def front_running(ll: dict[str, Any], flow_hits: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Label the lead score; refuse a direction when no lag clears the noise band."""
    s = ll.get("lead_score")
    band = ll.get("noise_band")
    peak = ll.get("peak") or {}
    significant = band is not None and peak.get("r") is not None and abs(peak["r"]) > band and peak.get("lag") != 0
    if s is None:
        label = "INSUFFICIENT DATA"
    elif not significant:
        label = "NO CLEAR LEAD"
    else:
        label = "FRONT-RUNNING" if s > 0.2 else "CHASING" if s < -0.2 else "MIXED"
        if not ll.get("enough"):
            label = "PROVISIONAL " + label
    return {"score": s, "label": label, "significant": significant, "source": ll.get("source"),
            "n": ll.get("n"), "flow_hits": flow_hits}


def flow_hit_rate(flow: Sequence[Optional[float]], price: Sequence[Optional[float]], ahead: int) -> dict[str, Any]:
    """Share of non-zero cohort flows followed by a price move in the same direction `ahead` steps later."""
    n = hits = 0
    for t in range(len(flow) - ahead):
        f = flow[t]
        a, b = price[t], price[t + ahead]
        if f is None or a is None or b is None or f == 0 or a == b:
            continue
        n += 1
        if sign(f) == sign(b - a):
            hits += 1
    return {"n": n, "hit_rate": hits / n if n else None, "ahead_steps": ahead}


# ---------------------------------------------------------------------------
# 14b. Reconstructed backtest from fills
# ---------------------------------------------------------------------------


def position_path(fills: Sequence[dict[str, Any]], current_szi: float, complete: bool,
                  coverage_start: Optional[int]) -> tuple[list[tuple[int, float, float]], Optional[int]]:
    """BTC position path from fills: list of (time, start_pos, end_pos), plus earliest time it is valid."""
    btc = sorted((f for f in fills if f.get("coin") == "BTC"), key=lambda f: int(f["time"]))
    path = []
    for f in btc:
        sp = _f(f.get("startPosition"), 0.0) or 0.0
        sz = _f(f.get("sz"), 0.0) or 0.0
        ep = sp + (sz if f.get("side") == "B" else -sz)
        path.append((int(f["time"]), sp, ep))
    valid_from = None if complete else coverage_start
    return path, valid_from


def position_at(path: Sequence[tuple[int, float, float]], current_szi: float, t: int,
                valid_from: Optional[int]) -> Optional[float]:
    if valid_from is not None and t < valid_from:
        return None
    last = None
    for ft, sp, ep in path:
        if ft <= t:
            last = ep
        else:
            return last if last is not None else sp
    return last if last is not None else current_szi


def reconstruct_backtest(
    wallets: Sequence[dict[str, Any]],
    candles_1h: Sequence[dict[str, Any]],
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    """wallets: {address, month_pnl, equity, szi, fills, complete, coverage_start}.

    Weighted P(long) per hour from reconstructed BTC positions, scored against price.
    """
    closes = {int(c["t"]): float(c["c"]) for c in candles_1h}
    hours = sorted(t for t in closes if start_ms <= t <= end_ms)
    paths = []
    for w in wallets:
        path, vf = position_path(w.get("fills") or [], w.get("szi") or 0.0, w.get("complete", False), w.get("coverage_start"))
        paths.append((w, path, vf))
    series = []
    for t in hours:
        px = closes[t]
        wl = ws = 0.0
        covered = voters = 0
        for w, path, vf in paths:
            pos = position_at(path, w.get("szi") or 0.0, t + HOUR_MS - 1, vf)
            if pos is None:
                continue
            covered += 1
            if pos == 0:
                continue
            voters += 1
            wt = trader_weight(w.get("month_pnl") or 0.0, w.get("equity") or 0.0, abs(pos) * px)
            if pos > 0:
                wl += wt
            else:
                ws += wt
        p = wl / (wl + ws) if (wl + ws) > 0 else None
        series.append({"t": t, "px": px, "p": _r(p, 4), "covered": covered, "voters": voters})
    # Score
    from .signal import verdict_from_p
    res = {}
    for h in (4, 24):
        n = hits = n_dir = 0
        bs = 0.0
        for i, s in enumerate(series):
            if s["p"] is None or i + h >= len(series):
                continue
            y = 1.0 if series[i + h]["px"] > s["px"] else 0.0
            n += 1
            bs += (s["p"] - y) ** 2
            v = verdict_from_p(s["p"])
            if v != "NEUTRAL":
                n_dir += 1
                hits += int((v == "LONG") == (y == 1.0))
        res[f"{h}h"] = {"n": n, "n_directional": n_dir, "hit_rate": hits / n_dir if n_dir else None,
                        "brier": bs / n if n else None, "independent_n_approx": len(series) // h}
    # Follow-the-verdict curve (no costs) vs holding
    eq_follow = 1.0
    eq_hold = 1.0
    curve = []
    for i in range(1, len(series)):
        prev = series[i - 1]
        r = series[i]["px"] / prev["px"] - 1
        v = verdict_from_p(prev["p"]) if prev["p"] is not None else "NEUTRAL"
        pos = 1 if v == "LONG" else (-1 if v == "SHORT" else 0)
        eq_follow *= 1 + pos * r
        eq_hold *= 1 + r
        curve.append({"t": series[i]["t"], "follow": round(eq_follow, 5), "hold": round(eq_hold, 5)})
    return {
        "available": bool(series),
        "n_wallets": len(wallets),
        "series": series,
        "scores": res,
        "follow_return": eq_follow - 1 if curve else None,
        "hold_return": eq_hold - 1 if curve else None,
        "curve": curve,
    }


# ---------------------------------------------------------------------------
# 9. X sentiment (slot only)
# ---------------------------------------------------------------------------

X_SENTIMENT_KEYS = ("ts_utc", "score", "n_posts")


def x_sentiment_slot(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Validate an optional data/x_sentiment.json. Absent or malformed -> planned state."""
    base = {
        "status": "PLANNED",
        "planned_release": "v2.0",
        "schema": {
            "ts_utc": "ISO-8601 UTC time of the read",
            "window_hours": "look-back window",
            "n_posts": "posts scored",
            "score": "net sentiment in [-1, 1]; +1 all bullish",
            "bull_share": "share of posts scored bullish",
            "bear_share": "share of posts scored bearish",
            "method": "short description of the scorer",
        },
    }
    if not isinstance(raw, dict) or not all(k in raw for k in X_SENTIMENT_KEYS):
        return base
    score = _f(raw.get("score"))
    if score is None or not -1.0 <= score <= 1.0:
        return base
    return {**base, "status": "CONNECTED", "data": {
        "ts_utc": raw.get("ts_utc"), "score": score, "n_posts": raw.get("n_posts"),
        "window_hours": raw.get("window_hours"), "bull_share": _f(raw.get("bull_share")),
        "bear_share": _f(raw.get("bear_share")), "method": raw.get("method")}}
