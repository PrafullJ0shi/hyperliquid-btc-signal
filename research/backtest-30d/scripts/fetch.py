"""Download the inputs for the 30-day reconstructed backtest.

Run from the repository root:

    python research/backtest-30d/scripts/fetch.py            # download (about 40 minutes)
    python research/backtest-30d/scripts/fetch.py --from-raw  # rebuild data/wallet_paths.json from raw/fills.json

Public Hyperliquid endpoints only. No keys. The 1,200 weight/minute budget is
enforced by app.rate_limit. Note: Hyperliquid serves only recent fills, so a
re-run later covers a different window than the committed snapshot.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[1]
DATA, RAW = BASE / "data", BASE / "raw"
sys.path.insert(0, str(ROOT))

DAY = 86_400_000
TRUNC_FILLS = 8000  # at or above this many returned fills the API history was cut off


def build_paths(fills: list[dict], start: int) -> list[dict]:
    """Compact BTC position paths: [time, position before, position after] per BTC fill."""
    out = []
    for w in fills:
        n = w["n_fills_total"]
        trunc = bool(w.get("cap_hit")) or n >= TRUNC_FILLS
        path = []
        for f in sorted(w["fills_btc"], key=lambda f: int(f["time"])):
            sp, sz = float(f["startPosition"]), float(f["sz"])
            path.append([int(f["time"]), round(sp, 6), round(sp + (sz if f["side"] == "B" else -sz), 6)])
        out.append({
            "address": w["address"], "month_pnl": w["month_pnl"], "equity": w["equity"], "szi": w["szi"],
            "n_fills_total": n, "first_fill": w["first_fill"], "truncated": trunc,
            "covered_from": w["first_fill"] if trunc else None, "path": path,
        })
    return out


async def download(n_wallets: int) -> None:
    from app.hl_client import HyperliquidClient, extract_btc_position
    from app.signal import trader_weight

    now = int(time.time() * 1000)
    start = now - 32 * DAY
    cohort = json.loads((ROOT / "data" / "cohort.json").read_text())["traders"]
    async with HyperliquidClient() as c:
        candles = await c.candles("BTC", "1h", start - 2 * DAY, now)
        funding = await c.funding_history("BTC", start - 2 * DAY, now)
        (DATA / "market.json").write_text(json.dumps({"now": now, "start": start, "candles": candles, "funding": funding}))
        sem = asyncio.Semaphore(6)

        async def state(r):
            async with sem:
                try:
                    s = extract_btc_position(await c.clearinghouse_state(r["address"]))
                except Exception:  # noqa: BLE001
                    s = {"equity": r.get("leaderboard_equity"), "btc_szi": 0.0}
                pnl = r.get("perp_month_pnl")
                return {"address": r["address"], "month_pnl": pnl if pnl is not None else r.get("leaderboard_month_pnl"),
                        "equity": s.get("equity") or r.get("leaderboard_equity") or 0.0, "szi": s.get("btc_szi") or 0.0}

        obs = await asyncio.gather(*[state(r) for r in cohort])
        (DATA / "observed.json").write_text(json.dumps(obs))
        chosen = sorted(obs, key=lambda r: trader_weight(r["month_pnl"] or 0, r["equity"] or 0, r["equity"] or 0), reverse=True)[:n_wallets]

        async def fills(w):
            async with sem:
                allf, t, seen, cap = [], start, set(), False
                for _ in range(8):
                    page = await c._info_items({"type": "userFillsByTime", "user": w["address"], "startTime": t,
                                                "endTime": now, "aggregateByTime": True}, 20, 20)
                    keys = lambda f: (f.get("tid"), f["time"], f["coin"], f["px"], f["sz"])  # noqa: E731
                    new = [f for f in page if keys(f) not in seen]
                    seen.update(keys(f) for f in new)
                    allf.extend(new)
                    if len(page) < 2000 or not new:
                        break
                    t = int(page[-1]["time"])
                else:
                    cap = True
                return {**w, "fills_btc": [f for f in allf if f["coin"] == "BTC"], "n_fills_total": len(allf),
                        "first_fill": min((int(f["time"]) for f in allf), default=None), "cap_hit": cap}

        out = []
        for i in range(0, len(chosen), 6):
            out.extend(await asyncio.gather(*[fills(w) for w in chosen[i:i + 6]]))
            RAW.mkdir(exist_ok=True)
            (RAW / "fills.json").write_text(json.dumps(out))
            print("wallets", len(out), flush=True)
    (DATA / "wallet_paths.json").write_text(json.dumps(build_paths(out, start)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wallets", type=int, default=100)
    ap.add_argument("--from-raw", action="store_true")
    a = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    if a.from_raw:
        fills = json.loads((RAW / "fills.json").read_text())
        start = json.loads((DATA / "market.json").read_text())["start"]
        (DATA / "wallet_paths.json").write_text(json.dumps(build_paths(fills, start), separators=(",", ":")))
    else:
        asyncio.run(download(a.wallets))


if __name__ == "__main__":
    main()
