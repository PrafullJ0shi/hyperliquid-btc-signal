"""Robustness checks for the 30-day backtest. Writes data/extra.json.

    python research/backtest-30d/scripts/extra.py     (after analyze.py)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze as A  # noqa: E402


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(
        sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def main() -> dict:
    mk, W, opn, fund, end, start = A.load()
    ts = list(range(start, end + 1, A.H))
    P = {t: A.cohort_p(W, opn, t)[0] for t in ts}
    p = [P[t] for t in ts]
    px = [opn[t] for t in ts]
    out = {}
    # 1. weights removed: share of voting wallets that are long
    def count_p(wallets, t):
        l = s = 0
        for w in wallets:
            q = A.pos_at(w, t)
            if q is None or abs(q) < 1e-9:
                continue
            l, s = (l + 1, s) if q > 0 else (l, s + 1)
        return l / (l + s) if l + s else None
    c = [count_p(W, t) for t in ts[::24]]
    out["count_based_p_daily"] = {"min": min(c), "max": max(c)}
    # 2. only wallets whose fills cover the whole window
    full = [w for w in W if not w["truncated"]]
    pf = [A.cohort_p(full, opn, t)[0] for t in ts]
    pf = [x for x in pf if x is not None]
    out["complete_wallets_only"] = {"n_wallets": len(full), "p_min": min(pf), "p_max": max(pf), "hours_not_short": sum(1 for x in pf if x > 0.4)}
    # 3. does the level or the change of P(long) lead BTC?
    xs = [p[i] - p[i - 24] for i in range(24, len(p) - 24)]
    ys = [px[i + 24] / px[i] - 1 for i in range(24, len(p) - 24)]
    out["corr_dP24_next24h_return"] = {"rho": corr(xs, ys), "n": len(xs)}
    xs = [p[i] for i in range(len(p) - 24)]
    ys = [px[i + 24] / px[i] - 1 for i in range(len(p) - 24)]
    out["corr_level_next24h_return"] = {"rho": corr(xs, ys), "n": len(xs)}
    # 4. is the signal's own direction ever contradicted? days where the cohort level rose and BTC rose
    out["p_first_day"], out["p_last_day"] = p[0], p[-1]
    (A.DATA / "extra.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
