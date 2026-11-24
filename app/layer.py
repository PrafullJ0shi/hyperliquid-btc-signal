"""Fetch market context and assemble the market-intelligence block.

Network calls live here (fetch_market, refresh_backtest); everything else is
delegated to the pure functions in intel.py and indicators.py.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from . import config
from . import intel as I
from .signal import trader_weight
from .timeutil import format_ist, iso_utc, now_utc

log = logging.getLogger("layer")

DAY_MS = 86_400_000


def ts_ms(ts_utc: Optional[str]) -> Optional[int]:
    if not ts_utc:
        return None
    try:
        return int(datetime.fromisoformat(ts_utc.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


async def fetch_market(client, now_ms: int) -> dict[str, Any]:
    out: dict[str, Any] = {"candles_1h": [], "candles_1d": [], "candles_15m": [], "funding": []}
    jobs = (
        ("candles_1h", lambda: client.candles("BTC", "1h", now_ms - config.CANDLE_DAYS_1H * DAY_MS, now_ms)),
        ("candles_1d", lambda: client.candles("BTC", "1d", now_ms - config.CANDLE_DAYS_1D * DAY_MS, now_ms)),
        ("candles_15m", lambda: client.candles("BTC", "15m", now_ms - config.CANDLE_DAYS_15M * DAY_MS, now_ms)),
        ("funding", lambda: client.funding_history("BTC", now_ms - config.FUNDING_DAYS * DAY_MS, now_ms)),
    )
    for key, job in jobs:
        try:
            out[key] = await job()
        except Exception as exc:  # noqa: BLE001 — context must not fail the sweep
            log.warning("%s failed: %s", key, exc)
    log.info(
        "Market context: %s 1h, %s 1d, %s 15m candles, %s funding rows",
        len(out["candles_1h"]), len(out["candles_1d"]), len(out["candles_15m"]), len(out["funding"]),
    )
    return out


def backtest_is_fresh(prior: Optional[dict[str, Any]]) -> bool:
    if not prior or not prior.get("built_at_unix"):
        return False
    return (time.time() - float(prior["built_at_unix"])) < config.BACKTEST_TTL_SEC


async def refresh_backtest(
    client,
    observed: list[dict[str, Any]],
    candles_1h: list[dict[str, Any]],
    prior: Optional[dict[str, Any]],
    now_ms: int,
) -> Optional[dict[str, Any]]:
    if backtest_is_fresh(prior):
        log.info("Reusing reconstructed backtest built %s", prior.get("built_at_ist"))
        return prior
    if not candles_1h:
        return prior
    # Heaviest potential voters: skill * equity shrink, independent of current side.
    def pot(r):
        return trader_weight(r.get("month_pnl") or 0.0, r.get("equity") or 0.0, r.get("equity") or 0.0)
    chosen = sorted(observed, key=pot, reverse=True)[: config.BACKTEST_WALLETS]
    log.info("Reconstructing positions from fills for %s wallets", len(chosen))
    t0 = time.monotonic()
    wallets = []
    for r in chosen:
        try:
            fills = await client.user_fills(r["address"])
        except Exception as exc:  # noqa: BLE001
            log.warning("userFills failed for %s: %s", r["address"], exc)
            continue
        complete = len(fills) < 2000
        coverage = min((int(f["time"]) for f in fills), default=None) if not complete else None
        wallets.append({
            "address": r["address"],
            "month_pnl": r.get("month_pnl") or 0.0,
            "equity": r.get("equity") or 0.0,
            "szi": r.get("btc_szi") or 0.0,
            "fills": [f for f in fills if f.get("coin") == "BTC"],
            "complete": complete,
            "coverage_start": coverage,
        })
    start = now_ms - config.BACKTEST_DAYS * DAY_MS
    result = I.reconstruct_backtest(wallets, candles_1h, start, now_ms)
    full = sum(1 for w in wallets if w["complete"] or (w["coverage_start"] or now_ms) <= start)
    built = now_utc()
    series = result["series"]
    ll = I.lead_lag(
        [s["p"] for s in series], [s["px"] for s in series], 6, "h",
        "reconstructed 7-day hourly series",
    )
    flow = I.diffs([s["p"] for s in series])
    fr_hits = I.flow_hit_rate(flow, [s["px"] for s in series], 4)
    out = {
        **{k: v for k, v in result.items()},
        "built_at_unix": built.timestamp(),
        "built_at_utc": iso_utc(built),
        "built_at_ist": format_ist(built),
        "days": config.BACKTEST_DAYS,
        "wallets_with_full_window": full,
        "lead_lag": ll,
        "flow_hits_4h": fr_hits,
        "fetch_sec": round(time.monotonic() - t0, 1),
        "limits": [
            "Wallets are today's leaders, chosen with hindsight: results are biased upward (survivorship).",
            "Weights use today's month PnL and equity for every past hour.",
            "Only the latest 2,000 fills per wallet are available; active wallets cover less than 7 days.",
            "Hourly steps overlap at 4h and 24h, so scored rows are not independent.",
            "No fees, funding, or slippage in the follow curve.",
        ],
    }
    log.info("Backtest: %s wallets, %s with full window, %.1fs", len(wallets), full, out["fetch_sec"])
    return out


def _strip_private(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _candles_compact(cs: list[dict[str, Any]], n: int) -> list[list[float]]:
    return [[int(c["t"]), float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"])] for c in cs[-n:]]


def build_intel(
    *,
    payload: dict[str, Any],
    observed: list[dict[str, Any]],
    ctx: dict[str, Any],
    market: dict[str, Any],
    history: list[dict[str, Any]],
    prev_positions: Optional[dict[str, Any]],
    backtest: Optional[dict[str, Any]],
    x_raw: Optional[dict[str, Any]],
    now_ms: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (intel block for signal.json, extra fields for this history row)."""
    mark = payload.get("btc_mark")
    p = payload.get("p_long")
    c1h, c1d, c15 = market.get("candles_1h") or [], market.get("candles_1d") or [], market.get("candles_15m") or []

    # History with millisecond timestamps, oldest first.
    hist = []
    for h in history:
        t = ts_ms(h.get("ts_utc"))
        if t is not None:
            hist.append({**h, "_ms": t})
    hist.sort(key=lambda h: h["_ms"])

    # Signal integrity first: it provides effective N for the Bayesian step.
    signed = []
    for r in observed:
        szi = r.get("btc_szi") or 0.0
        if szi:
            w = trader_weight(r.get("month_pnl") or 0.0, r.get("equity") or 0.0, r.get("btc_notional") or 0.0)
            signed.append((1 if szi > 0 else -1, w))
    fake = I.fake_signal(signal=payload, observed=observed, signed=signed, data_age_sec=0.0)

    # Bayesian posterior: replay stored history plus this observation.
    cur_pt = {"_ms": now_ms, "p_long": p, "n_eff": fake["n_eff"]}
    replay = I.bayes_replay(hist + [cur_pt])
    bayes = I.bayes_summary(replay, p)
    post_by_ms = {r["_ms"]: r["mean"] for r in replay}
    for h in hist:
        if h.get("post") is None and h["_ms"] in post_by_ms:
            h["post"] = post_by_ms[h["_ms"]]

    sigma_d = I.sigma_daily(c1h)
    risk = I.cohort_risk(observed, mark, sigma_d, p)
    liq = I.liquidation_map(observed, mark)
    emas = I.ema_study(c1h, c1d, mark)
    pa = I.price_action(c1h, c1d, mark)
    fo = I.funding_oi(ctx or {}, market.get("funding") or [], hist, payload.get("verdict", "NEUTRAL"), now_ms)
    reg = I.regime(c1h, fo.get("funding_ann"), emas.get("h1", {}))

    changes = I.position_changes(observed, prev_positions, mark)
    d_last = (p - hist[-1]["p_long"]) if (p is not None and hist and hist[-1].get("p_long") is not None) else None
    flip = I.flip_status(
        changes, d_last, I.p_delta(hist, p, now_ms, 3), I.p_delta(hist, p, now_ms, 24),
        payload.get("n_long", 0) + payload.get("n_short", 0),
    )
    prev_regime = next((h.get("regime") for h in reversed(hist) if h.get("regime")), None)
    watch = I.market_change_watch(flip, reg, prev_regime, risk.get("squeeze", {}) if risk.get("available") else {},
                                  p, fo.get("funding_ann"), emas)

    fg = I.fear_greed(
        funding_ann=fo.get("funding_ann"),
        p_post=bayes.get("posterior_mean"),
        rv_pct=reg.get("rv_pct_30d"),
        ret_7d=pa.get("ret_7d"),
        sigma_d=sigma_d,
        oi_change_24h=fo.get("oi_change_24h"),
        ret_24h=pa.get("ret_24h"),
    )

    prices = I.PriceLookup(c15 or c1h, [(h["_ms"], h["btc_mark"]) for h in hist if h.get("btc_mark")])
    acc = I.accuracy(hist, prices, now_ms)
    contra = I.contrarian(payload.get("verdict", "NEUTRAL"), p, acc)

    # Lead-lag on stored snapshots (30-minute grid), including this one.
    pts = hist + [{"_ms": now_ms, "p_long": p, "btc_mark": mark, "flow": changes.get("net_weight_flow")}]
    step = 30 * 60_000
    g0 = min(x["_ms"] for x in pts)
    g1 = max(x["_ms"] for x in pts)
    p_grid = I.grid_series(pts, step, "p_long", g0, g1)
    m_grid = I.grid_series(pts, step, "btc_mark", g0, g1)
    ll_live = I.lead_lag(p_grid, m_grid, 6, "half-hour steps", "live snapshots (30-minute grid)")
    f_grid = I.grid_series(pts, step, "flow", g0, g1)
    live_hits = I.flow_hit_rate(f_grid, m_grid, 2)
    bt_ll = (backtest or {}).get("lead_lag")
    primary = ll_live if (ll_live["enough"] or not bt_ll) else bt_ll
    fr = I.front_running(primary, live_hits if primary is ll_live else (backtest or {}).get("flow_hits_4h"))

    e_h1 = emas.get("h1", {})
    e_d1 = emas.get("d1", {})
    chart = {
        "candles_1h": _candles_compact(c1h, config.CHART_CANDLES_1H),
        "ema_1h": {k: [None if v is None else round(v, 1) for v in e_h1.get("_" + k, [])[-config.CHART_CANDLES_1H:]]
                   for k in ("e20", "e50", "e200")},
        "candles_1d": _candles_compact(c1d, config.CHART_CANDLES_1D),
        "ema_1d": {k: [None if v is None else round(v, 1) for v in e_d1.get("_" + k, [])[-config.CHART_CANDLES_1D:]]
                   for k in ("e20", "e50", "e200")},
    }
    bt_public = None
    if backtest:
        bt_public = {k: v for k, v in backtest.items() if k not in ("series",)}
        bt_public["series"] = [{"t": s["t"], "p": s["p"], "px": s["px"], "covered": s["covered"]}
                               for s in backtest.get("series", [])]

    intel = {
        "version": "1.0",
        "risk": risk,
        "liquidation_map": liq,
        "flip": flip,
        "market_watch": watch,
        "changes": changes,
        "price_action": pa,
        "ema": {"h1": _strip_private(e_h1), "d1": _strip_private(e_d1)},
        "regime": reg,
        "fear_greed": fg,
        "x_sentiment": I.x_sentiment_slot(x_raw),
        "contrarian": contra,
        "integrity": fake,
        "funding_oi": fo,
        "bayes": bayes,
        "accuracy": acc,
        "backtest": bt_public,
        "lead_lag": {"live": ll_live, "reconstructed": bt_ll},
        "front_running": fr,
        "chart": chart,
    }
    row_extra = {
        "post": round(bayes["posterior_mean"], 4) if bayes.get("available") else None,
        "n_eff": round(fake["n_eff"], 2),
        "funding": fo.get("funding_rate_h"),
        "oi": fo.get("oi_btc"),
        "fg": fg.get("score"),
        "regime": reg.get("label"),
        "flow": round(changes["net_weight_flow"], 4) if changes.get("available") else None,
        "flips_l": changes.get("flips_to_long") if changes.get("available") else None,
        "flips_s": changes.get("flips_to_short") if changes.get("available") else None,
        "grade": risk.get("aggregate_grade"),
        "integrity": fake["status"],
    }
    # Rows stored before the posterior existed get it from the replay.
    row_extra["_post_by_ts"] = {h.get("ts_utc"): round(h["post"], 4) for h in hist if h.get("post") is not None}
    return intel, row_extra
