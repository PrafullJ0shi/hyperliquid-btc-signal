"""Build the research README and the site's Backtest tab from one source of text and numbers.

    python research/backtest-30d/scripts/build_docs.py

Needs the results in data/ (run analyze.py and extra.py first) and, only when a formula
changes, Node with `npm install` run in research/backtest-30d (MathJax, build time only).
Writes: research/backtest-30d/README.md, site/backtest/*, and the block between the
BACKTEST markers in site/index.html.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
DATA, FIG = BASE / "data", BASE / "figures"
SITE = ROOT / "site"
REPO = "https://github.com/PrafullJ0shi/hyperliquid-btc-signal"
RAW_BASE = "https://raw.githubusercontent.com/PrafullJ0shi/hyperliquid-btc-signal/main/research/backtest-30d"
TREE = REPO + "/tree/main/research/backtest-30d"
HL = "https://hyperliquid.gitbook.io/hyperliquid-docs"
DOCS = {
    "info": HL + "/for-developers/api/info-endpoint",
    "perps": HL + "/for-developers/api/info-endpoint/perpetuals",
    "limits": HL + "/for-developers/api/rate-limits-and-user-limits",
    "fees": HL + "/trading/fees",
    "funding": HL + "/trading/funding",
}

R = json.loads((DATA / "results.json").read_text())
X = json.loads((DATA / "extra.json").read_text())
ROWS = list(csv.DictReader((DATA / "daily_backtest.csv").open()))
S = json.loads((DATA / "series.json").read_text())

# ---------------------------------------------------------------------------
# Formulas. One TeX string is used in the README and (pre-rendered) on the site.
# ---------------------------------------------------------------------------
F = {
    "skill": (r"s_i = \ln\left(1 + \max\left(0,\ \pi_i\right)\right)", "Skill weight s sub i equals the natural log of one plus the larger of zero and the one-month perp PnL"),
    "shrink": (r"e_i = \min\left(1,\ \frac{E_i}{100000}\right)", "Equity shrink e sub i equals the smaller of one and equity over one hundred thousand dollars"),
    "conv": (r"c_{i,t} = \min\left(3,\ \frac{\left|q_{i,t}\right| B_t}{E_i}\right)", "Conviction c equals the smaller of three and absolute BTC notional over equity"),
    "weight": (r"w_{i,t} = s_i \, e_i \, c_{i,t}", "Weight w equals skill times shrink times conviction"),
    "p": (r"p_t = \frac{\sum_{i:\, q_{i,t} > 0} w_{i,t}}{\sum_{i:\, q_{i,t} \neq 0} w_{i,t}}", "P of long equals the weight on long wallets divided by the weight on all wallets with a BTC position"),
    "sigma": (r"\sigma_t = \begin{cases} +1 & p_t \ge 0.60 \\ -1 & p_t \le 0.40 \\ 0 & \text{otherwise} \end{cases}", "Signal sigma is plus one if P of long is at least 0.60, minus one if at most 0.40, otherwise zero"),
    "path": (r"q_{i,t} = q^{\mathrm{after}}_{i,j^{*}}, \qquad j^{*} = \max\{\, j : \tau_{i,j} \le t \,\}, \qquad q^{\mathrm{after}}_{i,j} = q^{\mathrm{before}}_{i,j} \pm z_{i,j}", "Position at time t equals the position after the latest fill at or before t; each fill adds or subtracts its size"),
    "step": (r"r_k = \sigma_k \left( \frac{B_{k+1}}{B_k} - 1 \right) - f \left| \sigma_k - \sigma_{k-1} \right| - \sigma_k \sum_{h \in k} \phi_h", "Step return equals position times price return, minus fee times position change, minus position times summed hourly funding"),
    "equity": (r"V_K = \prod_{k=1}^{K} \left( 1 + r_k \right), \qquad \mathrm{PnL}_K = V_K - 1", "Equity is the product of one plus each step return; P and L is equity minus one"),
    "mdd": (r"\mathrm{MDD} = \min_{K} \left( \frac{V_K}{\max_{j \le K} V_j} - 1 \right)", "Maximum drawdown is the lowest ratio of equity to its running peak, minus one"),
    "sharpe": (r"S = \frac{\bar{r}}{s_r} \sqrt{N_{\mathrm{yr}}}", "Sharpe-ish ratio is mean step return over its standard deviation times the square root of steps per year"),
    "hit": (r"\mathrm{HR} = \frac{\left| \{ k : \sigma_k \neq 0,\ \sigma_k R_k > 0 \} \right|}{\left| \{ k : \sigma_k \neq 0 \} \right|}, \qquad R_k = \frac{B_{k+1}}{B_k} - 1", "Hit rate is the share of in-market steps where the position and the price move had the same sign"),
    "compound": (r"V^{\mathrm{short}}_K = \prod_{k=1}^{K} \left( 1 - R_k \right) \quad \text{versus} \quad -\left( \frac{B_K}{B_0} - 1 \right)", "Daily-rebalanced short equity versus the simple price-only short return"),
    "corr": (r"\rho = \mathrm{corr}\left( p_t - p_{t-24},\ \frac{B_{t+24}}{B_t} - 1 \right)", "Correlation between the 24-hour change in P of long and the next 24-hour BTC return"),
}

_INLINE_RE = re.compile(r"(\$[^$\n]+\$)")


def need_inline(texts):
    out = {}
    for t in texts:
        for m in _INLINE_RE.findall(t):
            out[m[1:-1]] = {"tex": m[1:-1], "display": False}
    return out


def render_math(extra_inline: dict) -> dict:
    """Return {key: svg}; key is formula id or the TeX of an inline formula. Cached in data/math_svg.json."""
    items = {k: {"tex": v[0], "display": True} for k, v in F.items()}
    items.update({"i:" + tex: spec for tex, spec in extra_inline.items()})
    cache_path = DATA / "math_svg.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    sig = lambda spec: hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]  # noqa: E731
    todo = {k: v for k, v in items.items() if k not in cache or cache[k]["h"] != sig(v)}
    if todo:
        proc = subprocess.run(["node", str(BASE / "scripts" / "render_math.cjs")], input=json.dumps(todo), text=True,
                              capture_output=True, cwd=BASE, check=True)
        for k, svg in json.loads(proc.stdout).items():
            cache[k] = {"h": sig(items[k]), "svg": svg}
    cache = {k: v for k, v in cache.items() if k in items}
    cache_path.write_text(json.dumps(cache, separators=(",", ":")))
    return {k: v["svg"] for k, v in cache.items()}


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------
def pc(x, nd=1, sign=True):
    s = f"{x * 100:+.{nd}f}%" if sign else f"{x * 100:.{nd}f}%"
    return s.replace("-", "\u2212")


def num(x, nd=2):
    return f"{x:.{nd}f}".replace("-", "\u2212")


D, H4, HR = R["daily"], R["4h"], R["hourly"]
HOLD, SHORT = R["hold_daily"], R["short_daily"]
P = R["p_stats"]
DEC = R["decomposition"]
N_DAYS = len(ROWS)
UP_DAYS = sum(1 for r in ROWS if float(r["net_pnl_pct"]) > 0)
HIT_DAYS = round(D["hit_rate"] * D["n_directional"])
WIN = "26 Oct 2026 05:30 IST to 25 Nov 2026 05:30 IST"
_m = json.loads((DATA / "market.json").read_text())
_end = (_m["now"] // 86_400_000) * 86_400_000
_fr = [float(x["fundingRate"]) for x in _m["funding"] if _end - 30 * 86_400_000 <= int(x["time"]) < _end]
FUND_POS, FUND_N = sum(1 for x in _fr if x > 0), len(_fr)
N_W, N_TR, N_ACT = R["n_wallets"], R["n_truncated"], R["n_btc_active"]
N_FULL = N_W - N_TR
WORST_S = None
BEST = max(ROWS, key=lambda r: float(r["net_pnl_pct"]))
WORST = min(ROWS, key=lambda r: float(r["net_pnl_pct"]))
WORST_S = f"{float(WORST['net_pnl_pct']):+.2f}%".replace('-', '\u2212')
PEAK = max(ROWS, key=lambda r: float(r["cumulative_pnl_pct"]))

STAT_HEAD = ["Strategy", "Total return", "Max drawdown", "Trades", "Hit rate", "Sharpe-ish", "Time in market"]


def stat_row(label, s):
    return [label, pc(s["total_return"]), pc(s["max_drawdown"], 1, False).replace("%", "%"), str(s["trades"]),
            f"{s['hit_rate'] * 100:.0f}%", num(s["sharpe_ann"], 1), f"{s['time_in_market'] * 100:.0f}%"]


STAT_ROWS = [
    stat_row("Follow the signal, daily (primary)", D),
    stat_row("Follow the signal, 4-hourly", H4),
    stat_row("Follow the signal, hourly", HR),
    stat_row("Always short, daily", SHORT),
    stat_row("Buy and hold, daily", HOLD),
]
for r in STAT_ROWS:
    if r[2] and not r[2].startswith("\u2212"):
        r[2] = "\u2212" + r[2]

DAY_HEAD = ["Day", "Date (IST)", "Signal", "P(long)", "Action", "BTC entry", "BTC next day", "BTC move", "Fees", "Funding", "Day P&L", "Cumulative"]


def day_rows():
    out = []
    for r in ROWS:
        fee = float(r["fees_pct"])
        out.append([r["day"], r["date_ist"][5:] if False else r["date_ist"], r["signal"], f"{float(r['p_long']):.3f}", r["action"],
                    f"{float(r['btc_entry_price']):,.0f}", f"{float(r['btc_next_day_price']):,.0f}",
                    f"{float(r['btc_move_pct']):+.2f}%".replace("-", "\u2212"), (f"{fee:.3f}%".replace("-", "\u2212") if fee else "\u2013"),
                    f"{float(r['funding_pct']):+.3f}%".replace("-", "\u2212"), f"{float(r['net_pnl_pct']):+.2f}%".replace("-", "\u2212"),
                    f"{float(r['cumulative_pnl_pct']):+.2f}%".replace("-", "\u2212")])
    return out


# ---------------------------------------------------------------------------
# Content: a list of blocks, rendered to Markdown and to HTML.
# Inline markup: $tex$, **bold**, `code`, [text](url). Links use {repo:...} / {raw:...} placeholders.
# ---------------------------------------------------------------------------
def content():
    B = []
    a = B.append
    a(("kicker", "Research note, 25 November 2026"))
    a(("h1", "bt-top", "Would following the Hyperliquid BTC signal for 30 days have made money?"))
    a(("summary", None))
    a(("h2", "bt-thesis", "1. Thesis"))
    a(("p", "The live plate reads the aggregate Bitcoin positioning of the top 500 Hyperliquid traders ranked on one-month perp PnL, and turns it into one probability, "
            "$p_t$, that the weighted money is long. **The thesis under test: when that probability is far from one half, BTC tends to move the same way over the "
            "following period.** If it is true, holding the side the leaders hold should beat holding BTC and should beat a position chosen without looking at the leaders."))
    a(("p", "The test is built so that it can fail. A strategy that simply follows the signal will look good in any strong trend, so the reading has to be compared with the "
            "dumbest rule that earns the same trend: **always short** in a falling market, **always long** in a rising one. Only the part of the return that the signal adds "
            "on top of that rule counts as evidence of timing skill."))
    a(("ul", ["**Null hypothesis.** Leader positioning has no timing value: following it does no better than the best constant position over the window.",
              "**Alternative.** Following it beats the best constant position after fees and funding, with position changes that were right more often than wrong.",
              "**What would count.** At least one signal change in the window, and a return above the constant position that earned the same trend."]))
    a(("h2", "bt-data", "2. Data and sources"))
    a(("p", "Everything is public. No keys, no accounts, no private data. All requests go to `https://api.hyperliquid.xyz/info` (documented in the "
            f"[Hyperliquid info endpoint reference]({DOCS['info']}) and the [perpetuals section]({DOCS['perps']})) except the leaderboard."))
    a(("table", ["Input", "Source", "Used for"], [
        ["Cohort", "Public leaderboard `https://stats-data.hyperliquid.xyz/Mainnet/leaderboard` (no documentation page), then `portfolio` per wallet", "Top 500 wallets by one-month perp PnL, with the live filters (equity at least USD 10,000, turnover at most 100)"],
        ["Positions through time", f"`userFillsByTime`, one wallet at a time ([info endpoint]({DOCS['info']}))", "BTC position of each wallet at each signal time, rebuilt from the position before and after every BTC fill"],
        ["Now-state", "`clearinghouseState`", "Account equity and the current BTC position (the anchor for wallets with no BTC fill in the window)"],
        ["Price", "`candleSnapshot`, BTC, 1 hour", "Hourly open as the entry and exit price"],
        ["Funding", f"`fundingHistory`, BTC ([funding rules]({DOCS['funding']}))", "Hourly funding rate paid between longs and shorts"],
        ["Fees", f"[Hyperliquid fee schedule]({DOCS['fees']})", "Base-tier perp taker fee of 0.045% per side"],
        ["Rate limit", f"[Rate limits]({DOCS['limits']})", "1,200 weight per minute per IP, enforced by the downloader"],
    ], "l"))
    a(("p", f"The window is {WIN}: 30 daily steps, each read at 05:30 IST (00:00 UTC). "
            f"Of the 500 cohort wallets, the {N_W} with the largest weight potential (log of month PnL times the equity shrink) were downloaded. "
            f"{N_ACT} of them traded BTC in the window or hold BTC now."))
    a(("h2", "bt-method", "3. Method"))
    a(("h3", "bt-reconstruct", "3.1 Rebuilding the signal in the past"))
    a(("p", "The live sweep only stores snapshots from the day it was switched on, so a 30-day history has to be rebuilt. Each Hyperliquid fill carries the wallet's position before it "
            "(`startPosition`), its size and its side. The BTC position of wallet $i$ at time $t$ is therefore the position after the latest fill at or before $t$, "
            "where $\\tau_{i,j}$ is the time of fill $j$, $z_{i,j}$ its size, and the sign is plus for a buy and minus for a sell:"))
    a(("math", "path"))
    a(("p", "A wallet with no BTC fill before $t$ but a later one takes the `startPosition` of its first fill in the window. A wallet with no BTC fill at all in the window keeps "
            "its current position. The API returns only part of the history for very active wallets, so those wallets are treated as unknown, and left out of $p_t$, "
            "before their earliest returned fill."))
    a(("h3", "bt-weights", "3.2 The live weights, applied to each past hour"))
    a(("p", "The weights are exactly the live signal's. Here $\\pi_i$ is one-month perp PnL in USD, $E_i$ account equity in USD, $q_{i,t}$ the signed BTC position and $B_t$ the BTC price."))
    a(("math", "skill"))
    a(("math", "shrink"))
    a(("math", "conv"))
    a(("math", "weight"))
    a(("p", "Wallets with no BTC position do not vote. The probability that the weighted money is long, and the decision rule, are:"))
    a(("math", "p"))
    a(("math", "sigma"))
    a(("p", "$\\sigma_t = +1$ is long, $-1$ is short, $0$ is flat. The thresholds are the live ones. Note that $\\pi_i$ and $E_i$ are today's values applied to every past hour, which is a source of bias (section 7)."))
    a(("h3", "bt-exec", "3.3 Trading rule and costs"))
    a(("ul", ["**Position.** One unit of BTC perpetual, long, short or flat per $\\sigma_k$, rebalanced to one unit of the account equity at every step. No leverage, no margin model.",
              f"**Primary strategy.** One step per day: read $p_t$ at 05:30 IST, trade at the 00:00 UTC hourly open, hold 24 hours. Variants: every 4 hours and every hour.",
              "**Entry and exit price.** The hourly candle open. No slippage and no spread.",
              "**Fee.** $f = 0.00045$ per side on every change of position. A flip pays two sides. The only fee in the primary run is the opening trade.",
              "**Funding.** $\\phi_h$ is the hourly funding rate of hour $h$. When $\\phi_h > 0$ longs pay shorts, so a short earns it; the sign is carried by $\\sigma_k$. "
              "The exchange applies the rate to notional at the oracle price; the backtest applies it to notional at the entry price, a small approximation.",
              "**Comparators.** Always short and buy and hold, with the same fee and funding, on the same steps."]))
    a(("p", "For step $k$ from time $t_k$ to $t_{k+1}$, with $B_k$ the BTC price at the start and $\\sigma_{k-1}$ the position held before the step ($0$ before the first step):"))
    a(("math", "step"))
    a(("math", "equity"))
    a(("h3", "bt-metrics", "3.4 Statistics"))
    a(("math", "mdd"))
    a(("math", "hit"))
    a(("math", "sharpe"))
    a(("p", "$V_K$ is the equity multiple after $K$ steps and $\\bar r$, $s_r$ are the mean and standard deviation of the step returns. $N_{\\mathrm{yr}}$ is 365 for daily steps, 2,190 for 4-hourly and 8,760 for hourly. "
            "With 30 daily points the Sharpe-ish figure is not a reliable estimate; it is shown for completeness."))
    a(("h2", "bt-results", "4. Results"))
    a(("p", f"Following the signal once a day for 30 days would have returned **{pc(D['total_return'])}** after fees and funding, against **{pc(HOLD['total_return'])}** for holding BTC. "
            f"The signal read SHORT at every one of the {P['hours']} hourly reads, with $p_t$ between {P['p_min']:.3f} and {P['p_max']:.3f}, so it never traded again after opening a short."))
    a(("table", STAT_HEAD, STAT_ROWS, "lrrrrrr", "Table B1. Statistics for the 30 days to 25 Nov 2026 05:30 IST. Returns are after the 0.045% taker fee and hourly funding. Sharpe-ish is annualised."))
    a(("fig", "equity", "Fig. B1. Cumulative P&L of each rule, and below it hourly $p_t$ against the 0.40 and 0.60 thresholds (the PNG adds the BTC price). "
                        "The primary line lies on top of the always-short line because the position never changed."))
    a(("h3", "bt-days", "4.1 Day by day"))
    a(("table", DAY_HEAD, day_rows(), "rllrlrrrrrrr", "Table B2. All 30 daily steps. The signal is read at 05:30 IST (00:00 UTC) on the date shown, and the position is held to 05:30 IST the next day. "
                                                    "Fees and funding are as a percentage of equity. The figure version is "
                                                    "[daily_table_30d.png]({repo:figures/daily_table_30d.png})."))
    a(("p", f"The best day was {BEST['date_ist']} ({float(BEST['net_pnl_pct']):+.2f}%) and the worst {WORST['date_ist']} ({WORST_S}). The curve peaked on day {PEAK['day']} "
            f"({PEAK['date_ist']}, {float(PEAK['cumulative_pnl_pct']):+.2f}%) and gave back {float(PEAK['cumulative_pnl_pct']) - float(ROWS[-1]['cumulative_pnl_pct']):.1f} points by day 30. "
            f"The position made money on {UP_DAYS} of {N_DAYS} days after costs, and was on the right side of the daily price move on {HIT_DAYS} ({D['hit_rate'] * 100:.0f}%): "
            "day to day, the direction is close to a coin flip, and the profit comes from the size of the down days."))
    a(("h2", "bt-why", "5. Why the result looks like this"))
    a(("ul", [f"**One regime.** BTC fell from {R['btc_start']:,.0f} to {R['btc_end']:,.0f} ({pc(R['btc_return'])}) in 30 days. In a one-way fall, any rule that is short throughout makes money. The test window contains no rebound large enough to challenge the signal.",
              f"**The signal never changed its mind.** $p_t$ stayed between {P['p_min']:.3f} and {P['p_max']:.3f}, below the 0.40 short threshold for {P['hours']} of {P['hours']} hours. Following it meant one trade, on day 1. Excess return over always short is {num((D['total_return'] - SHORT['total_return']) * 100, 1)} percentage points: the signal added nothing to the trend and took nothing away.",
              f"**The cohort is a list of last month's winners.** The leaders are chosen by one-month PnL as of 25 Nov. A month in which BTC fell 25% rewards the traders who were short, so the cohort leans short by construction. Using it to trade the same month is circular (survivorship and hindsight, section 7).",
              f"**Compounding.** Rebalancing a short to one unit each day compounds gains as the price falls: a simple price-only short earns {pc(DEC['simple_short_price_only'])}, the daily-rebalanced short {pc(DEC['compounded_gross'])} before costs. "
              f"The extra {num((DEC['compounded_gross'] - DEC['simple_short_price_only']) * 100, 1)} points are a property of the trade size rule, not of the signal.",
              f"**Funding paid the short.** Funding was positive in {FUND_POS} of {FUND_N} hours, so longs paid shorts: {pc(DEC['funding'], 2)} summed over the window. Fees cost {pc(DEC['fees'], 3)}, one entry. Together they move the result by less than one point.",
              "**The Sharpe-ish figure is large for the wrong reason.** A steady one-way bet in a trend has a high mean-to-deviation ratio over 30 days; the same bet in a rising month would have a large negative one."]))
    a(("p", "The compounding gap in the fourth point is the difference between the two quantities below, with $R_k$ the daily BTC return and $B_K / B_0$ the price ratio over the window:"))
    a(("math", "compound"))
    a(("h2", "bt-checks", "6. Robustness checks"))
    a(("p", "Three checks on whether the always-short reading is an accident of how the cohort was rebuilt, and one check on whether $p_t$ leads the price at all. "
            "The last uses the correlation between the 24-hour change in $p_t$ and the next 24-hour BTC return:"))
    a(("math", "corr"))
    a(("ul", [f"**Complete wallets only.** Using only the {X['complete_wallets_only']['n_wallets']} wallets whose fills cover the whole window, $p_t$ ranged from {X['complete_wallets_only']['p_min']:.3f} to {X['complete_wallets_only']['p_max']:.3f}. It was below 0.40 in every hour, so the truncated wallets do not cause the always-short reading.",
              f"**Weights removed.** Counting wallets instead of weighting them, the long share of voting wallets ranged from {X['count_based_p_daily']['min']:.2f} to {X['count_based_p_daily']['max']:.2f} at the daily reads. The cohort leaned short however it is counted.",
              f"**Lead check.** Over {X['corr_dP24_next24h_return']['n']} overlapping hourly points, $\\rho$ is {X['corr_dP24_next24h_return']['rho']:+.2f} for the change in $p_t$, and {X['corr_level_next24h_return']['rho']:+.2f} between the level of $p_t$ and the next return. "
              "Both are small, and the points overlap so the effective sample is about 30. They give no sign of a lead.",
              "**Hourly and 4-hourly variants** give the same answer for the same reason: "
              f"{pc(HR['total_return'])} and {pc(H4['total_return'])}, with a larger drawdown ({pc(HR['max_drawdown'], 1, False)} and {pc(H4['max_drawdown'], 1, False)}) from intraday swings."]))
    a(("h2", "bt-caveats", "7. Caveats and biases"))
    a(("ul", ["**Survivorship and hindsight.** The wallets are today's leaders, and their weights use today's month PnL and equity for every past hour. Traders who were short and right are over-represented; traders who were long and liquidated are not in the leaderboard. The bias is upward and large, and it points in the direction the market went.",
              f"**Partial history.** For {N_TR} of the {N_W} wallets the API returned only recent fills, so before their earliest returned fill they are unknown. The number of covered wallets ranged from {P['covered_min']} to {P['covered_max']} and the voters from {P['voters_min']} to {P['voters_max']} per hour. Early days rest on slower traders.",
              f"**One fifth of the cohort.** {N_W} of the 500 wallets, chosen by weight potential. The live signal uses all 500.",
              "**Reconstruction, not snapshots.** Positions come from fills, not from stored `clearinghouseState` snapshots. Liquidations, auto-deleveraging, transfers and sub-account moves are not seen unless they appear as fills.",
              "**One window, one regime, one trade.** Thirty days, one direction, one position change. There is no out-of-sample period, no estimate of how often the signal flips, and no information about what it does at a turn.",
              "**Execution.** Hourly candle open prices, no slippage or spread, a base-tier taker fee, one unit of equity, no margin or liquidation risk, funding applied to entry notional.",
              "**Not financial advice.** This is a description of a historical window."]))
    a(("h2", "bt-verdict", "8. Verdict"))
    a(("verdict", f"**Profitable on paper, not evidence of an edge.** Over the 30 days to 25 Nov 2026 05:30 IST the signal would have made {pc(D['total_return'])} after fees and funding "
                  f"(maximum drawdown {pc(D['max_drawdown'], 1, False)}), while BTC fell {pc(-R['btc_return'], 1, False)} and holding lost {pc(-HOLD['total_return'], 1, False)}. "
                  f"But the signal read SHORT in all {P['hours']} hourly reads, so the strategy is the always-short strategy: the same {pc(SHORT['total_return'])}, to the decimal. "
                  "Almost all of the return is the downtrend. This window cannot show whether the signal calls turns, because it never had to. "
                  "A fair test needs a cohort fixed before the window and a window that contains a reversal. The live site now logs $p_t$ every 30 minutes (`data/history.json`) "
                  "for exactly that forward test; repeat this analysis on that log once it spans a turn."))
    a(("h2", "bt-reproduce", "9. Reproduce"))
    a(("code", "# from the repository root\n"
               "pip install -r requirements.txt matplotlib\n"
               "python research/backtest-30d/scripts/analyze.py   # data/*.csv, results.json, series.json from the committed inputs\n"
               "python research/backtest-30d/scripts/extra.py     # robustness checks -> data/extra.json\n"
               "python research/backtest-30d/scripts/plot.py      # figures/*.png\n"
               "# only if you want to re-download (about 40 minutes at 1,200 weight/minute; covers a newer window):\n"
               "python research/backtest-30d/scripts/fetch.py\n"
               "# rebuild this note and the site's Backtest tab (needs Node for MathJax only when a formula changes):\n"
               "(cd research/backtest-30d && npm install) && python research/backtest-30d/scripts/build_docs.py"))
    a(("p", "`analyze.py` is deterministic: the committed `data/market.json` and `data/wallet_paths.json` reproduce every number above. A fresh `fetch.py` covers the 30 days before the day you run it, "
            "and Hyperliquid serves only recent fills, so it cannot re-create this exact window later."))
    a(("h2", "bt-files", "10. Files"))
    a(("p", "Everything is in [research/backtest-30d]({folder}). On the site, this page is the Backtest tab."))
    a(("table", ["File", "Contents"], [
        ["[`data/daily_backtest.csv`]({raw:data/daily_backtest.csv})", "Table B2 as CSV"],
        ["[`data/hourly_signal.csv`]({raw:data/hourly_signal.csv})", f"The {P['hours']} hourly reads of $p_t$ with covered wallets and voters"],
        ["[`data/results.json`]({raw:data/results.json})", "Every statistic in Table B1, all variants, and the decomposition"],
        ["[`data/series.json`]({raw:data/series.json})", "Per-step rows and equity curves for the daily, 4-hourly and hourly runs"],
        ["[`data/extra.json`]({raw:data/extra.json})", "Robustness checks"],
        ["`data/market.json`, `data/observed.json`, `data/wallet_paths.json`", "Inputs: BTC candles and funding, cohort weights, rebuilt position paths"],
        ["[`figures/equity_curve_30d.png`]({repo:figures/equity_curve_30d.png}), [`figures/daily_table_30d.png`]({repo:figures/daily_table_30d.png})", "Fig. B1 and Table B2 as images"],
        ["`scripts/`", "`fetch.py`, `analyze.py`, `extra.py`, `plot.py`, `build_docs.py`"],
    ], "ll"))
    a(("p", "This is a description of a historical window, built from public data. It is not financial advice and not a forecast. Do not trade on it."))
    return B


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def link_md(t):
    return re.sub(r"\{(repo|raw):([^}]+)\}", lambda m: m.group(2), t).replace("{folder}", ".")


def link_html(t):
    t = t.replace("{folder}", TREE)
    return re.sub(r"\{(repo|raw):([^}]+)\}", lambda m: (TREE + "/" + m.group(2)) if m.group(1) == "repo" else (RAW_BASE + "/" + m.group(2)), t)


def inline_md(t):
    return link_md(t)


def inline_html(t, SVG):
    t = link_html(t)
    parts = _INLINE_RE.split(t)
    out = []
    for p in parts:
        if _INLINE_RE.fullmatch(p):
            tex = p[1:-1]
            svg = SVG["i:" + tex].replace("<svg ", f'<svg aria-label="{html.escape(tex, quote=True)}" ', 1).replace('role="img"', 'role="img"')
            out.append(f'<span class="m">{svg}</span>')
        else:
            e = html.escape(p, quote=False)
            e = re.sub(r"`([^`]+)`", r"<code>\1</code>", e)
            e = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", e)
            e = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', e)
            out.append(e)
    return "".join(out)


def md_table(head, rows, al):
    al = al.ljust(len(head), al[-1])
    sep = ["---:" if c in "r" else ":---" for c in al]
    lines = ["| " + " | ".join(head) + " |", "| " + " | ".join(sep) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(inline_md(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(lines)


def render_md(B):
    o = []
    for b in B:
        k = b[0]
        if k == "kicker":
            o.append(f"*{b[1]}*\n")
        elif k == "h1":
            o.append(f"# {b[2]}\n")
        elif k in ("h2", "h3"):
            o.append(f"{'#' * (2 if k == 'h2' else 3)} {b[2]}\n")
        elif k == "p":
            o.append(inline_md(b[1]) + "\n")
        elif k == "ul":
            o.append("\n".join("- " + inline_md(x) for x in b[1]) + "\n")
        elif k == "math":
            o.append("$$\n" + F[b[1]][0] + "\n$$\n")
        elif k == "table":
            cap = b[4] if len(b) > 4 else None
            o.append(md_table(b[1], b[2], b[3]) + "\n")
            if cap:
                o.append("*" + inline_md(cap) + "*\n")
        elif k == "fig":
            o.append(f'<img src="figures/equity_curve_30d.png" alt="Cumulative P&L of following the signal, always short and buy and hold over 30 days; P(long) against the thresholds; BTC price." width="100%">\n')
            o.append("*" + inline_md(b[2]) + "*\n")
        elif k == "code":
            o.append("```sh\n" + b[1] + "\n```\n")
        elif k == "verdict":
            o.append("> " + inline_md(b[1]) + "\n")
        elif k == "summary":
            o.append(summary_md())
    return "\n".join(o)


def summary_md():
    t = [
        ["Follow the signal, daily", pc(D["total_return"]), f"{pc(D['max_drawdown'], 1, False).replace('%', '%')}".replace("+", "\u2212")],
        ["Always short", pc(SHORT["total_return"]), pc(SHORT["max_drawdown"], 1, False).replace("+", "\u2212")],
        ["Buy and hold BTC", pc(HOLD["total_return"]), pc(HOLD["max_drawdown"], 1, False).replace("+", "\u2212")],
    ]
    s = ("**In one line:** the signal read SHORT in every hourly read of the last 30 days, so following it was the same trade as being short all month: "
         f"**{pc(D['total_return'])}** after fees and funding while BTC fell {pc(-R['btc_return'], 1, False)}. Profitable, but it is the trend, not evidence that the signal times turns.\n\n")
    s += md_table(["Rule, 30 days to 25 Nov 2026 05:30 IST", "Return after fees and funding", "Max drawdown"], t, "lrr") + "\n"
    s += f"\nLive site: [Backtest tab](https://prafullj0shi.github.io/hyperliquid-btc-signal/#backtest). Part of [hyperliquid-btc-signal]({REPO}). Not financial advice.\n"
    return s


def render_html(B, SVG):
    o = []
    inl = lambda t: inline_html(t, SVG)  # noqa: E731

    def table(head, rows, al, cap, cls, minw):
        al = al.ljust(len(head), al[-1])
        h = "".join(f'<th scope="col"{" class=l" if c == "l" else ""}>{html.escape(x)}</th>' for x, c in zip(head, al))
        body = []
        for r in rows:
            cells = []
            for j, (c, a_) in enumerate(zip(r, al)):
                cls_ = ' class="l"' if a_ == "l" else ""
                if cls == "bt-days" and j == 2 and c == "SHORT":
                    cls_ = ' class="l flag"'
                if cls == "bt-days" and j in (10, 11) and c.startswith("\u2212"):
                    cls_ = ' class="flag"'
                cells.append(f"<td{cls_}>{inl(c)}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        capx = f"<figcaption>{inl(cap)}</figcaption>" if cap else ""
        return (f'<figure class="fig bt-fig"><div class="bt-scroll" tabindex="0" role="region" aria-label="{html.escape(cap.split(".")[0] if cap else "Table")}">'
                f'<table class="data mono {cls}" style="min-width:{minw}em"><thead><tr>{h}</tr></thead><tbody>{"".join(body)}</tbody></table></div>{capx}</figure>')

    for b in B:
        k = b[0]
        if k == "kicker":
            o.append(f'<p class="kicker bt-kicker">{html.escape(b[1])}</p>')
        elif k == "h1":
            o.append(f'<h1 id="{b[1]}" tabindex="-1">{html.escape(b[2])}</h1>')
        elif k == "h2":
            o.append(f'<h2 class="part-title bt-h2" id="{b[1]}">{inl(b[2])}</h2>')
        elif k == "h3":
            o.append(f'<h3 class="block-title bt-h3" id="{b[1]}">{inl(b[2])}</h3>')
        elif k == "p":
            o.append(f"<p class=\"bt-p\">{inl(b[1])}</p>")
        elif k == "ul":
            o.append('<ul class="bt-list">' + "".join(f"<li>{inl(x)}</li>" for x in b[1]) + "</ul>")
        elif k == "math":
            svg = SVG[b[1]].replace("<svg ", f'<svg aria-label="{html.escape(F[b[1]][1], quote=True)}" ', 1)
            o.append(f'<div class="bt-eq" role="math" tabindex="0" aria-label="{html.escape(F[b[1]][1], quote=True)}">{svg}</div>')
        elif k == "table":
            cap = b[4] if len(b) > 4 else None
            if len(b[1]) == 12:
                o.append(table(b[1], b[2], b[3], cap, "bt-days", 58))
            elif len(b[1]) == 7:
                o.append(table(b[1], b[2], b[3], cap, "bt-stats", 40))
            else:
                o.append(table(b[1], b[2], b[3], cap, "bt-ref", 0))
        elif k == "fig":
            legend = ('<ul class="bt-legend" aria-label="Legend">'
                      '<li><svg width="30" height="8" aria-hidden="true"><line x1="0" y1="4" x2="30" y2="4" stroke="#8C1D12" stroke-width="2"/></svg>Follow the signal, daily</li>'
                      '<li><svg width="30" height="8" aria-hidden="true"><line x1="0" y1="4" x2="30" y2="4" stroke="#8A867D" stroke-width="1"/></svg>Follow the signal, hourly</li>'
                      '<li><svg width="30" height="8" aria-hidden="true"><line x1="0" y1="4" x2="30" y2="4" stroke="#141414" stroke-width="1.4" stroke-dasharray="1 3"/></svg>Always short</li>'
                      '<li><svg width="30" height="8" aria-hidden="true"><line x1="0" y1="4" x2="30" y2="4" stroke="#141414" stroke-width="1.2" stroke-dasharray="5 3"/></svg>Buy and hold</li></ul>')
            o.append('<figure class="fig fig-wide bt-fig">' + legend + '<div class="chart" id="bt-chart-equity" style="height:300px" role="img" '
                     'aria-label="Cumulative P&L of following the signal, always short and buy and hold"></div>'
                     '<div class="chart" id="bt-chart-p" style="height:130px"></div>'
                     '<noscript><img src="backtest/equity_curve_30d.png" alt="Cumulative P&L of following the signal, always short and buy and hold over 30 days" width="100%"></noscript>'
                     f'<figcaption>{inl(b[2])} <a href="backtest/equity_curve_30d.png">Static image</a>.</figcaption></figure>')
        elif k == "code":
            o.append(f'<pre class="bt-code"><code>{html.escape(b[1])}</code></pre>')
        elif k == "verdict":
            o.append(f'<p class="bt-verdict">{inl(b[1])}</p>')
        elif k == "summary":
            o.append(summary_html())
    return "\n".join(o)


def summary_html():
    rows = [
        ("Follow the signal, daily", D),
        ("Always short", SHORT),
        ("Buy and hold BTC", HOLD),
    ]
    dl = "".join(f"<dt>{n}</dt><dd>{pc(s['total_return'])} <span class=\"sub\">max drawdown {pc(s['max_drawdown'], 1, False).replace('+', chr(0x2212))}</span></dd>" for n, s in rows)
    return ('<section class="bt-summary" aria-label="Result">'
            '<p class="kicker">Result, 30 days to 25 Nov 2026 05:30 IST</p>'
            f'<p class="verdict bt-big">{pc(D["total_return"])}</p>'
            f'<dl class="metrics">{dl}<dt>Signal reads</dt><dd>SHORT in {P["hours"]} of {P["hours"]}</dd><dt>Position changes</dt><dd>1, the opening short</dd></dl>'
            f'<p class="cap-small">Research note and data: <a href="{TREE}">GitHub folder</a> · <a href="{RAW_BASE}/data/daily_backtest.csv">daily_backtest.csv</a> · '
            f'<a href="{RAW_BASE}/data/results.json">results.json</a> · <a href="#bt-reproduce">reproduce</a>.</p>'
            '<p class="note bt-p">Profitable on paper, but the signal never left SHORT, so it is the always-short trade and the profit is the 25% fall in BTC. '
            'It is not evidence that the signal times turns.</p></section>')


# ---------------------------------------------------------------------------
def main():
    B = content()
    texts = []
    for b in B:
        for x in b[1:]:
            if isinstance(x, str):
                texts.append(x)
            elif isinstance(x, list):
                for y in x:
                    if isinstance(y, str):
                        texts.append(y)
                    elif isinstance(y, list):
                        texts.extend(c for c in y if isinstance(c, str))
    SVG = render_math(need_inline(texts))
    (BASE / "README.md").write_text(render_md(B) + "\n")

    # site: data copies
    out = SITE / "backtest"
    out.mkdir(exist_ok=True)
    for name in ("daily_backtest.csv", "results.json", "extra.json", "hourly_signal.csv"):
        shutil.copy(DATA / name, out / name)
    shutil.copy(FIG / "equity_curve_30d.png", out / "equity_curve_30d.png")
    shutil.copy(FIG / "daily_table_30d.png", out / "daily_table_30d.png")
    daily_t = [t for t, _ in S["daily"][1]]
    hourly = list(csv.DictReader((DATA / "hourly_signal.csv").open()))
    import datetime as dt
    ht = [int(dt.datetime.strptime(h["time_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc).timestamp() * 1000) for h in hourly]
    chart = {
        "t": daily_t,
        "follow": [round(v - 1, 5) for _, v in S["daily"][1]],
        "short": [round(v - 1, 5) for v in S["short_curve"]],
        "hold": [round(v - 1, 5) for v in S["hold_curve"]],
        "hourly_t": [t for t, _ in S["hourly"][1]],
        "hourly": [round(v - 1, 5) for _, v in S["hourly"][1]],
        "p": [[t, round(float(h["p_long"]), 4)] for t, h in zip(ht, hourly)],
        "thresholds": [0.40, 0.60],
    }
    (out / "backtest.json").write_text(json.dumps(chart, separators=(",", ":")))

    # site: panel in index.html
    panel = render_html(B, SVG)
    idx = SITE / "index.html"
    s = idx.read_text()
    start, end = "<!-- BACKTEST:START (generated by research/backtest-30d/scripts/build_docs.py) -->", "<!-- BACKTEST:END -->"
    if start not in s:
        raise SystemExit("markers missing in site/index.html")
    s = re.sub(re.escape(start) + r".*?" + re.escape(end), lambda m: start + "\n" + panel + "\n" + end, s, flags=re.S)
    idx.write_text(s)
    print("README.md", len((BASE / "README.md").read_text()), "bytes; panel", len(panel), "bytes")


if __name__ == "__main__":
    main()
