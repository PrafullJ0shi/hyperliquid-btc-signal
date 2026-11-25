"""Build the cohort, poll BTC positions, write signal.json and SQLite."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

from . import config
from .hl_client import (
    HyperliquidClient,
    btc_ctx_from_ctxs,
    btc_mark_from_ctxs,
    extract_btc_position,
    window_from_row,
    window_pnl_from_portfolio,
)
from . import intel as I
from .layer import build_intel, fetch_market, refresh_backtest
from . import flow as FL
from .tracking import run_tracking
from .backfill import seed_state
from . import tape as TP
from .signal import compute_signal
from .store import (
    load_cohort,
    load_history_json,
    load_latest_json,
    load_x_sentiment,
    save_snapshot,
    slim_row,
    write_cohort,
    write_json_files,
)
from .timeutil import format_ist, iso_utc, now_utc

log = logging.getLogger("sweep")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def filter_leaderboard(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for row in rows:
        equity = _float(row.get("accountValue"))
        month = window_from_row(row, "month")
        pnl = _float(month.get("pnl"))
        vlm = _float(month.get("vlm"))
        if equity < config.MIN_EQUITY:
            continue
        if pnl <= config.MIN_MONTH_PNL:
            continue
        turnover = (vlm / equity) if equity > 0 else float("inf")
        if turnover > config.MAX_TURNOVER:
            continue
        kept.append(
            {
                "address": str(row.get("ethAddress") or "").lower(),
                "display_name": row.get("displayName"),
                "leaderboard_equity": equity,
                "leaderboard_month_pnl": pnl,
                "leaderboard_month_roi": _float(month.get("roi")),
                "leaderboard_month_vlm": vlm,
                "turnover": turnover,
            }
        )
    kept.sort(key=lambda r: r["leaderboard_month_pnl"], reverse=True)
    return kept


async def _map_progress(
    label: str,
    items: list[Any],
    worker,
) -> list[Any]:
    total = len(items)
    results: list[Any] = [None] * total
    started = time.monotonic()
    done = 0
    lock = asyncio.Lock()

    async def run(i: int, item: Any) -> None:
        nonlocal done
        results[i] = await worker(item)
        async with lock:
            done += 1
            if done == total or done % 50 == 0:
                elapsed = time.monotonic() - started
                log.info("%s %s/%s in %.1fs", label, done, total, elapsed)

    await asyncio.gather(*(run(i, item) for i, item in enumerate(items)))
    return results


def cohort_is_fresh(cohort: Optional[dict[str, Any]]) -> bool:
    if not cohort or not cohort.get("traders"):
        return False
    built = cohort.get("built_at_unix")
    if not built:
        return False
    return (time.time() - float(built)) < config.PORTFOLIO_TTL_SEC


async def build_cohort(
    client: HyperliquidClient,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    pool = candidates[: config.CANDIDATE_POOL]
    log.info("Scoring %s candidates with portfolio (perpMonth)", len(pool))

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = await client.portfolio(row["address"])
            perp = window_pnl_from_portfolio(payload, "perpMonth")
            month_all = window_pnl_from_portfolio(payload, "month")
            return {**row, "perp_month_pnl": perp, "portfolio_month_pnl": month_all, "portfolio_ok": True}
        except Exception as exc:  # noqa: BLE001 — one wallet must not fail the sweep
            log.warning("portfolio failed for %s: %s", row["address"], exc)
            return {**row, "perp_month_pnl": None, "portfolio_ok": False, "error": str(exc)}

    scored = await _map_progress("portfolio", pool, one)
    eligible = [
        r
        for r in scored
        if r.get("portfolio_ok")
        and r.get("perp_month_pnl") is not None
        and r["perp_month_pnl"] > config.MIN_MONTH_PNL
    ]
    eligible.sort(key=lambda r: r["perp_month_pnl"], reverse=True)
    chosen = eligible[: config.TOP_N]
    dropped = len(pool) - len(eligible)
    log.info(
        "perpMonth > 0: %s of %s candidates; taking %s (dropped or non-perp: %s)",
        len(eligible),
        len(pool),
        len(chosen),
        dropped,
    )
    built = now_utc()
    return {
        "built_at_unix": built.timestamp(),
        "built_at_utc": iso_utc(built),
        "built_at_ist": format_ist(built),
        "source": "portfolio.perpMonth",
        "candidate_count": len(pool),
        "eligible_count": len(eligible),
        "traders": chosen,
        "filters": {
            "min_equity": config.MIN_EQUITY,
            "min_month_pnl": config.MIN_MONTH_PNL,
            "max_turnover": config.MAX_TURNOVER,
            "candidate_pool": config.CANDIDATE_POOL,
            "top_n": config.TOP_N,
        },
    }


class _SkipCtx(Exception):
    pass


async def poll_positions(
    client: HyperliquidClient,
    traders: list[dict[str, Any]],
    fetch_ctx: bool = True,
    label: str = "clearinghouseState",
) -> tuple[list[dict[str, Any]], Optional[float], dict[str, Any]]:
    mark = None
    ctx: dict[str, Any] = {}
    try:
        if not fetch_ctx:
            raise _SkipCtx()
        ctxs = await client.meta_and_asset_ctxs()
        mark = btc_mark_from_ctxs(ctxs)
        ctx = btc_ctx_from_ctxs(ctxs) or {}
    except _SkipCtx:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("metaAndAssetCtxs failed: %s; trying allMids", exc)
        try:
            mids = await client.all_mids()
            if isinstance(mids, dict) and "BTC" in mids:
                mark = float(mids["BTC"])
        except Exception as exc2:  # noqa: BLE001
            log.warning("allMids failed: %s", exc2)

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        try:
            state = await client.clearinghouse_state(row["address"])
            extracted = extract_btc_position(state)
        except Exception as exc:  # noqa: BLE001
            log.warning("clearinghouseState failed for %s: %s", row["address"], exc)
            extracted = {
                "equity": row.get("leaderboard_equity"),
                "btc_szi": 0.0,
                "btc_notional": 0.0,
                "entry": None,
                "leverage_type": None,
                "leverage": None,
                "unrealized_pnl": None,
                "liquidation_px": None,
                "error": str(exc),
            }
        equity = extracted.get("equity") or row.get("leaderboard_equity") or 0.0
        return {
            "address": row["address"],
            "display_name": row.get("display_name"),
            "month_pnl": row.get("perp_month_pnl") if row.get("perp_month_pnl") is not None else row.get("leaderboard_month_pnl"),
            "equity": equity,
            "btc_szi": extracted.get("btc_szi") or 0.0,
            "btc_notional": extracted.get("btc_notional") or 0.0,
            "entry": extracted.get("entry"),
            "leverage_type": extracted.get("leverage_type"),
            "leverage": extracted.get("leverage"),
            "unrealized_pnl": extracted.get("unrealized_pnl"),
            "liquidation_px": extracted.get("liquidation_px"),
            "margin_used": extracted.get("margin_used"),
            "roe": extracted.get("roe"),
            "total_ntl": extracted.get("total_ntl"),
            "other_signed_ntl": extracted.get("other_signed_ntl") or 0.0,
            "n_positions": extracted.get("n_positions") or 0,
            "turnover": row.get("turnover"),
            "mark": mark,
            "poll_error": bool(extracted.get("error")),
        }

    log.info("Polling clearinghouseState for %s wallets (%s)", len(traders), label)
    observed = await _map_progress(label, traders, one)
    return observed, mark, ctx


def assemble_payload(
    *,
    signal,
    mark: Optional[float],
    cohort: dict[str, Any],
    leaderboard_meta: dict[str, Any],
    timings: dict[str, Any],
    issued,
) -> dict[str, Any]:
    body = signal.to_dict()
    body.update(
        {
            "ts_utc": iso_utc(issued),
            "ts_ist": format_ist(issued),
            "btc_mark": mark,
            "coin": "BTC",
            "method": {
                "cohort_source": cohort.get("source"),
                "cohort_built_at_ist": cohort.get("built_at_ist"),
                "filters": cohort.get("filters"),
                "weight": (
                    "w = log(1 + month_pnl) * min(1, equity / 100000) "
                    "* min(|btc_notional| / equity, 3)"
                ),
                "p_long": "sum(long weights) / (sum(long weights) + sum(short weights))",
                "interval": "95% bootstrap percentile interval over traders (seed 42, 5000 resamples); Beta(1+longs, 1+shorts) is also stored",
                "thresholds": {
                    "long": config.P_LONG_THRESHOLD,
                    "short": config.P_SHORT_THRESHOLD,
                },
            },
            "leaderboard": {
                "url": config.LEADERBOARD_URL,
                "etag": leaderboard_meta.get("etag"),
                "last_modified": leaderboard_meta.get("last_modified"),
                "not_modified": leaderboard_meta.get("not_modified"),
                "bytes": leaderboard_meta.get("bytes"),
            },
            "timings": timings,
            "disclaimer": (
                "This is a descriptive reading of public positions, not financial advice "
                "and not a prediction. It can be wrong. Do not trade on it."
            ),
            "repo": "https://github.com/PrafullJ0shi/hyperliquid-btc-signal",
        }
    )
    return body


async def run_sweep(*, force_portfolio: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    timings: dict[str, Any] = {}
    previous_cohort = load_cohort() or {}
    previous_payload = load_latest_json() or {}
    async with HyperliquidClient() as client:
        t0 = time.monotonic()
        rows, lb_meta = await client.fetch_leaderboard()
        timings["leaderboard_sec"] = round(time.monotonic() - t0, 2)
        log.info(
            "Leaderboard: %s rows, %.1f MB, not_modified=%s, %.2fs",
            len(rows),
            (lb_meta.get("bytes") or 0) / 1e6,
            lb_meta.get("not_modified"),
            timings["leaderboard_sec"],
        )
        filtered = filter_leaderboard(rows)
        log.info("After filters: %s wallets", len(filtered))

        cohort = None if force_portfolio else previous_cohort
        if cohort_is_fresh(cohort):
            log.info(
                "Reusing cohort built %s (%s traders)",
                cohort.get("built_at_ist"),
                len(cohort.get("traders") or []),
            )
            timings["portfolio_sec"] = 0.0
            timings["cohort_reused"] = True
        else:
            t1 = time.monotonic()
            cohort = await build_cohort(client, filtered)
            timings["portfolio_sec"] = round(time.monotonic() - t1, 2)
            timings["cohort_reused"] = False

        traders = cohort.get("traders") or []
        t2 = time.monotonic()
        observed, mark, ctx = await poll_positions(client, traders)
        timings["clearinghouse_sec"] = round(time.monotonic() - t2, 2)

        t2b = time.monotonic()
        contrast = FL.contrast_candidates(
            rows, min_equity=config.MIN_EQUITY, max_turnover=config.MAX_TURNOVER,
            exclude={t["address"] for t in traders}, n=config.CONTRAST_N,
        )
        contrast_observed, _, _ = await poll_positions(client, contrast, fetch_ctx=False,
                                                       label="clearinghouseState (worst cohort)")
        for r in contrast_observed:
            r["mark"] = mark
        timings["contrast_sec"] = round(time.monotonic() - t2b, 2)

        t3 = time.monotonic()
        now_ms = int(time.time() * 1000)
        market = await fetch_market(client, now_ms)
        prior_bt = (previous_payload.get("intel") or {}).get("backtest")
        backtest = await refresh_backtest(client, observed, market.get("candles_1h") or [], prior_bt, now_ms)
        timings["market_sec"] = round(time.monotonic() - t3, 2)

        t4 = time.monotonic()
        tracker_block, tracker_state = None, {}
        if not previous_cohort.get("flow_log"):
            try:
                seeded = seed_state(config.ROOT, previous_cohort, int(time.time() * 1000), TP.WHALE_POS_USD)
                if seeded.get("flow_log"):
                    previous_cohort["flow_log"] = seeded["flow_log"]
                if seeded.get("whales") and not previous_cohort.get("tape"):
                    previous_cohort["tape"] = {"whales": seeded["whales"]}
            except Exception as exc:  # noqa: BLE001
                log.warning("Flow log seed failed: %s", exc)
        try:
            tracker_block, tracker_state = await run_tracking(
                client=client,
                coin=config.TRACK_COIN,
                smart_observed=observed,
                contrast_observed=contrast_observed,
                smart_traders=traders,
                contrast_traders=contrast,
                lb_rows=rows,
                mark=mark,
                state=previous_cohort,
                history=load_history_json(),
                oi_now=_float(ctx.get("openInterest"), 0.0) or None,
                candles_15m=market.get("candles_15m") or [],
                now_ms=int(time.time() * 1000),
            )
        except Exception as exc:  # noqa: BLE001 — the consensus reading must still publish
            log.exception("Tracking layer failed: %s", exc)
        timings["tracking_sec"] = round(time.monotonic() - t4, 2)
        timings["sweep_sec"] = round(time.monotonic() - started, 2)
        log.info(
            "BTC mark %s; sweep wall time %.1fs (portfolio %.1fs, positions %.1fs, market %.1fs)",
            mark,
            timings["sweep_sec"],
            timings["portfolio_sec"],
            timings["clearinghouse_sec"],
            timings["market_sec"],
        )

    signal = compute_signal(observed)
    issued = now_utc()
    payload = assemble_payload(
        signal=signal,
        mark=mark,
        cohort=cohort,
        leaderboard_meta=lb_meta,
        timings=timings,
        issued=issued,
    )
    history = load_history_json()
    intel, row_extra = build_intel(
        payload=payload,
        observed=observed,
        ctx=ctx,
        market=market,
        history=history,
        prev_positions=previous_cohort.get("last_positions"),
        backtest=backtest,
        x_raw=load_x_sentiment(),
        now_ms=int(issued.timestamp() * 1000),
    )
    if tracker_block is not None:
        intel["tracker"] = tracker_block
    payload["intel"] = intel
    save_snapshot(payload)
    post_by_ts = row_extra.pop("_post_by_ts", {})
    for h in history:
        if h.get("post") is None and h.get("ts_utc") in post_by_ts:
            h["post"] = post_by_ts[h["ts_utc"]]
    row = {**slim_row(payload), **row_extra}
    history = [h for h in history if h.get("ts_utc") != row["ts_utc"]] + [row]
    history = history[-config.HISTORY_MAX_POINTS:]
    write_json_files(payload, history)

    cohort = dict(cohort)
    for k in ("tracker_positions", "flow_log", "tape"):
        if k in tracker_state:
            cohort[k] = tracker_state[k]
        elif previous_cohort.get(k) is not None:
            cohort[k] = previous_cohort[k]
    cohort["last_positions"] = {
        "ts_utc": payload["ts_utc"],
        "mark": mark,
        "positions": I.compact_positions(observed),
    }
    write_cohort(cohort)
    log.info(
        "Verdict %s  P(long)=%s  CI=[%s, %s]  n=%s (L %s / S %s / F %s)",
        payload["verdict"],
        payload["p_long"],
        payload["ci_low"],
        payload["ci_high"],
        payload["n_traders"],
        payload["n_long"],
        payload["n_short"],
        payload["n_flat"],
    )
    return payload


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run one Hyperliquid BTC consensus sweep.")
    parser.add_argument(
        "--force-portfolio",
        action="store_true",
        help="Rebuild the 500-wallet cohort even if a cohort file is younger than one hour.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    payload = asyncio.run(run_sweep(force_portfolio=args.force_portfolio))
    print(json.dumps({
        "verdict": payload["verdict"],
        "p_long": payload["p_long"],
        "ci_low": payload["ci_low"],
        "ci_high": payload["ci_high"],
        "n_traders": payload["n_traders"],
        "n_long": payload["n_long"],
        "n_short": payload["n_short"],
        "n_flat": payload["n_flat"],
        "notional_long": payload["notional_long"],
        "notional_short": payload["notional_short"],
        "btc_mark": payload["btc_mark"],
        "ts_ist": payload["ts_ist"],
        "timings": payload["timings"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
