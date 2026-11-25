"""Reconstructed 30-day backtest of the live signal.

    python research/backtest-30d/scripts/analyze.py

Reads data/market.json, data/wallet_paths.json. Writes data/daily_backtest.csv,
data/hourly_signal.csv, data/results.json, data/series.json.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
DATA = BASE / "data"
sys.path.insert(0, str(ROOT))
from app.signal import trader_weight, verdict_from_p  # noqa: E402

H = 3_600_000
D = 24 * H
FEE = 0.00045  # Hyperliquid base-tier perp taker fee, per side
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
UTC = dt.timezone.utc


def load():
    mk = json.loads((DATA / "market.json").read_text())
    wallets = json.loads((DATA / "wallet_paths.json").read_text())
    opn = {int(c["t"]): float(c["o"]) for c in mk["candles"]}
    fund = {int(r["time"]) // H * H: float(r["fundingRate"]) for r in mk["funding"]}
    end = (mk["now"] // D) * D  # latest 00:00 UTC = 05:30 IST
    return mk, wallets, opn, fund, end, end - 30 * D


def pos_at(w, t):
    """BTC position of wallet w at time t (ms), or None if the fills do not reach back that far."""
    if w["covered_from"] is not None and t < w["covered_from"]:
        return None
    last = None
    for ft, sp, ep in w["path"]:
        if ft <= t:
            last = ep
        else:
            return last if last is not None else sp
    return last if last is not None else w["szi"]


def cohort_p(wallets, opn, t):
    """Weighted P(long), covered wallets, voters at hour t, same weights as the live signal."""
    px = opn[t]
    wl = ws = 0.0
    cov = vot = 0
    for w in wallets:
        p = pos_at(w, t)
        if p is None:
            continue
        cov += 1
        if abs(p) < 1e-9:
            continue
        vot += 1
        wt = trader_weight(w["month_pnl"] or 0, w["equity"] or 0, abs(p) * px)
        if p > 0:
            wl += wt
        else:
            ws += wt
    return (wl / (wl + ws) if wl + ws > 0 else None), cov, vot


def run(P, opn, fund, start, end, step_h):
    steps = range(start, end, step_h * H)
    eq, pos, rows, curve = 1.0, 0, [], [(start, 1.0)]
    for t in steps:
        t1 = min(t + step_h * H, end)
        p = P[t][0]
        v = verdict_from_p(p) if p is not None else "NEUTRAL"
        tgt = 1 if v == "LONG" else -1 if v == "SHORT" else 0
        p0, p1 = opn[t], opn[t1]
        fee = abs(tgt - pos) * FEE
        fsum = sum(fund.get(h, 0.0) for h in range(t, t1, H))
        gross = tgt * (p1 / p0 - 1)
        r = gross - fee - tgt * fsum
        eq *= 1 + r
        if tgt == pos:
            act = "hold " + {1: "long", -1: "short", 0: "flat"}[tgt]
        elif pos == 0:
            act = "open long" if tgt > 0 else "open short"
        elif tgt == 0:
            act = "close to flat"
        else:
            act = "flip to " + ("long" if tgt > 0 else "short")
        rows.append(dict(t=t, verdict=v, p=p, cov=P[t][1], vot=P[t][2], pos_before=pos, pos=tgt, action=act, p0=p0, p1=p1,
                         gross=gross, fee=fee, funding=-tgt * fsum, net=r, cum=eq - 1, btc=p1 / p0 - 1))
        pos = tgt
        curve.append((t1, eq))
    return rows, curve


def fixed(pos_const, opn, fund, start, end, step_h):
    rows, pos = [], 0
    for t in range(start, end, step_h * H):
        t1 = min(t + step_h * H, end)
        p0, p1 = opn[t], opn[t1]
        fee = abs(pos_const - pos) * FEE
        fsum = sum(fund.get(h, 0.0) for h in range(t, t1, H))
        gross = pos_const * (p1 / p0 - 1)
        rows.append(dict(net=gross - fee - pos_const * fsum, pos=pos_const, pos_before=pos, btc=p1 / p0 - 1,
                         fee=fee, funding=-pos_const * fsum, gross=gross))
        pos = pos_const
    return rows


def stats(rows, step_h):
    n = len(rows)
    rets = [r["net"] for r in rows]
    eq = peak = 1.0
    mdd = 0.0
    for r in rets:
        eq *= 1 + r
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    m = sum(rets) / n
    sd = (sum((x - m) ** 2 for x in rets) / (n - 1)) ** 0.5
    ann = (8760 / step_h) ** 0.5
    dirn = [r for r in rows if r["pos"] != 0]
    return dict(
        total_return=eq - 1, max_drawdown=mdd, trades=sum(1 for r in rows if r["pos"] != r["pos_before"]),
        hit_rate=sum(1 for r in dirn if r["pos"] * r["btc"] > 0) / len(dirn) if dirn else None,
        n_directional=len(dirn), sharpe_ann=m / sd * ann if sd > 0 else None, time_in_market=len(dirn) / n,
        fees=sum(r["fee"] for r in rows), funding=sum(r["funding"] for r in rows), gross=sum(r["gross"] for r in rows),
        n_steps=n, up=sum(1 for r in rows if r["net"] > 0))


def cumcurve(rows):
    e, o = 1.0, [1.0]
    for r in rows:
        e *= 1 + r["net"]
        o.append(e)
    return o


def main() -> dict:
    mk, wallets, opn, fund, end, start = load()
    ts = list(range(start, end + 1, H))
    P = {t: cohort_p(wallets, opn, t) for t in ts}
    out = {"start_utc": dt.datetime.fromtimestamp(start / 1000, UTC).isoformat(),
           "end_utc": dt.datetime.fromtimestamp(end / 1000, UTC).isoformat(),
           "n_wallets": len(wallets), "n_truncated": sum(w["truncated"] for w in wallets),
           "n_btc_active": sum(bool(w["path"]) or w["szi"] != 0 for w in wallets)}
    res = {}
    for sh, lab in ((24, "daily"), (4, "4h"), (1, "hourly")):
        rows, curve = run(P, opn, fund, start, end, sh)
        res[lab] = (rows, curve)
        out[lab] = stats(rows, sh)
        out["hold_" + lab] = stats(fixed(1, opn, fund, start, end, sh), sh)
        out["short_" + lab] = stats(fixed(-1, opn, fund, start, end, sh), sh)
    out["btc_return"] = opn[end] / opn[start] - 1
    out["btc_start"], out["btc_end"] = opn[start], opn[end]
    ps = [P[t][0] for t in ts]
    out["p_stats"] = {"hours": len(ts), "with_p": sum(p is not None for p in ps), "p_min": min(ps), "p_max": max(ps),
                      "hours_not_short": sum(1 for p in ps if p > 0.40),
                      "voters_min": min(P[t][2] for t in ts), "voters_max": max(P[t][2] for t in ts),
                      "covered_min": min(P[t][1] for t in ts), "covered_max": max(P[t][1] for t in ts)}
    # Where the +32% comes from
    drows = res["daily"][0]
    comp_gross = 1.0
    for r in drows:
        comp_gross *= 1 - r["btc"]
    out["decomposition"] = {
        "simple_short_price_only": -out["btc_return"],
        "compounded_gross": comp_gross - 1,
        "compounding_effect": (comp_gross - 1) + out["btc_return"],
        "fees": -out["daily"]["fees"],
        "funding": out["daily"]["funding"],
        "net_compounded": out["daily"]["total_return"],
    }
    (DATA / "results.json").write_text(json.dumps(out, indent=1))
    ser = {k: [v[0], v[1]] for k, v in res.items()}
    ser["hold_curve"] = cumcurve(fixed(1, opn, fund, start, end, 24))
    ser["short_curve"] = cumcurve(fixed(-1, opn, fund, start, end, 24))
    (DATA / "series.json").write_text(json.dumps(ser, separators=(",", ":")))
    with (DATA / "daily_backtest.csv").open("w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["day", "date_ist", "signal_time_ist", "signal", "p_long", "voters", "action", "position", "btc_entry_price",
                     "btc_next_day_price", "btc_move_pct", "gross_pnl_pct", "fees_pct", "funding_pct", "net_pnl_pct", "cumulative_pnl_pct"])
        for i, r in enumerate(drows, 1):
            d = dt.datetime.fromtimestamp(r["t"] / 1000, IST)
            wr.writerow([i, d.strftime("%Y-%m-%d"), d.strftime("%H:%M"), r["verdict"], round(r["p"], 3), r["vot"], r["action"],
                         {1: "LONG", -1: "SHORT", 0: "FLAT"}[r["pos"]], round(r["p0"], 1), round(r["p1"], 1),
                         round(r["btc"] * 100, 2), round(r["gross"] * 100, 3), round(-r["fee"] * 100, 3),
                         round(r["funding"] * 100, 3), round(r["net"] * 100, 3), round(r["cum"] * 100, 2)])
    with (DATA / "hourly_signal.csv").open("w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["time_utc", "p_long", "verdict", "wallets_covered", "voters", "btc_open"])
        for t in ts:
            p, cov, vot = P[t]
            wr.writerow([dt.datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%dT%H:%MZ"), round(p, 4), verdict_from_p(p), cov, vot, opn[t]])
    return out


if __name__ == "__main__":
    r = main()
    print(json.dumps({k: r[k] for k in ("daily", "btc_return", "decomposition", "p_stats")}, indent=1))
