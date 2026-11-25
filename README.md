# Bitcoin positioning among Hyperliquid one-month leaders

[![License: MIT](https://img.shields.io/badge/license-MIT-8C1D12?labelColor=141414)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-EFECE6?labelColor=141414&color=8C1D12)](https://www.python.org/)
[![Live plate](https://img.shields.io/badge/live-GitHub%20Pages-EFECE6?labelColor=141414&color=8C1D12)](https://prafullj0shi.github.io/hyperliquid-btc-signal/)
[![Sweep](https://github.com/PrafullJ0shi/hyperliquid-btc-signal/actions/workflows/sweep.yml/badge.svg)](https://github.com/PrafullJ0shi/hyperliquid-btc-signal/actions/workflows/sweep.yml)
[![Not financial advice](https://img.shields.io/badge/not-financial%20advice-EFECE6?labelColor=141414&color=3F3F3A)](https://prafullj0shi.github.io/hyperliquid-btc-signal/)

<p align="center">
  <img src="docs/banner.svg" alt="Instrument plate title: Bitcoin positioning among Hyperliquid one-month leaders. A wireframe sphere with an accent ring marks consensus inclination." width="100%">
</p>

A public, open-source instrument that answers one question: among the top 500 Hyperliquid traders ranked on **last-month perp PnL**, are their Bitcoin perpetual positions, on balance, long or short — and how concentrated is that weight?

The live plate is at [prafullj0shi.github.io/hyperliquid-btc-signal](https://prafullj0shi.github.io/hyperliquid-btc-signal/). The machine-readable snapshot is [`site/data/signal.json`](site/data/signal.json) (same file as [`data/signal.json`](data/signal.json)).

Around that reading sits a **market-intelligence layer**: cohort risk grades, a liquidation map, a flip detector with a market-change watch, a position-change feed, the history of P(long) with a Bayesian posterior, price action with an EMA study, a regime detector, a fear and greed meter, funding and open interest, a fake-signal detector, contrarian mode, backtesting, a lead-lag study, and a front-running meter. All of it is computed in the same sweep from public Hyperliquid data and documented under [Methodology](#methodology). A reconstructed [30-day backtest](#research-30-day-backtest) of the signal is published under [`research/`](research/backtest-30d/README.md) and on the site's Backtest tab.

This is **not financial advice** and **not a forecast**. It is a descriptive reading of public positions at the issue time. It can be wrong. Do not trade on it.

<p align="center">
  <img src="docs/demo.gif" alt="A scroll through the live plate: verdict, instrument readout, history with posterior, positions, and the market-intelligence figures." width="100%">
</p>

## What it measures

1. Download the public Hyperliquid leaderboard and keep it under an ETag cache.
2. Keep wallets with month PnL strictly greater than zero, account equity of at least $10,000, and month volume / equity of at most 100 (a turnover cap aimed at extreme market-maker-like flow; see below).
3. Take the top 700 of those by leaderboard month PnL and score them with the official `portfolio` endpoint. Rank by **perpMonth** PnL, keep those still above zero, and take the top 500.
4. Poll `clearinghouseState` for those 500 wallets (weight 2 each, under the official 1,200 weight/minute budget) and read their BTC positions.
5. Compute a weighted P(long), a 95% bootstrap interval, and a verdict.

## Algorithm

Each wallet $i$ with a non-zero Bitcoin perpetual is a vote. Long is $s_i = +1$, short is $s_i = -1$. Wallets that are flat in BTC do not vote.

The skill, size, and conviction weight is

$$
w_i = \log\bigl(1 + \mathrm{PnL}_i^{\mathrm{perpMonth}}\bigr)
\cdot \min\bigl(1,\, E_i / 10^{5}\bigr)
\cdot \min\bigl(|N_i^{\mathrm{BTC}}| / E_i,\, 3\bigr)
$$

where $E_i$ is account equity (USD) and $N_i^{\mathrm{BTC}}$ is the Bitcoin position notional (USD). Equity below USD 100,000 shrinks the vote toward zero. Conviction is BTC notional over equity, capped at 3.

The headline probability is the share of that weight on the long side:

$$
P(\mathrm{long})
= \frac{\sum_{s_i=+1} w_i}{\sum_{s_i=+1} w_i + \sum_{s_i=-1} w_i}
$$

If the denominator is zero (no BTC votes), the verdict is NEUTRAL and $P(\mathrm{long})$ is undefined.

The interval shown on the plate is a **95% bootstrap percentile interval**: traders are resampled with replacement 5,000 times (seed 42), $P(\mathrm{long})$ is recomputed, and the 2.5th and 97.5th percentiles are reported. As a robustness check the snapshot also stores an equal-tailed interval from the unweighted Beta posterior

$$
\theta \sim \mathrm{Beta}\bigl(1 + n_{\mathrm{long}},\, 1 + n_{\mathrm{short}}\bigr).
$$

The decision rule, applied to the point estimate, is:

- LONG if $P(\mathrm{long}) \ge 0.60$
- SHORT if $P(\mathrm{long}) \le 0.40$
- NEUTRAL otherwise.

When the bootstrap interval includes 0.5, the plate states that the point verdict is weakly held.

## Methodology

<p align="center">
  <img src="docs/intel.png" alt="The market-intelligence section of the plate: hourly candles with EMA 20, 50 and 200, daily small multiple, price-action table, regime detector, fear and greed meter, and the liquidation map." width="100%">
</p>

Notation: $p_t$ is the weighted P(long) at sweep $t$, $m_t$ the BTC mark, $\sigma_d$ the daily BTC volatility (standard deviation of hourly log returns over 7 days, times $\sqrt{24}$). Every number below is written to `data/signal.json` under `intel`; the field is named in brackets.

### 1. Cohort risk grade `[intel.risk]`

For each wallet with a BTC position, effective leverage is gross notional over equity, $L_i = \mathrm{totalNtlPos}_i / E_i$, and daily account volatility is approximated as $v_i = L_i \sigma_d$ (all exposure treated as moving with BTC, a conservative simplification).

Distance to liquidation, as a fraction of the mark, is $d_i = (m - \ell_i)/m$ for a long and $d_i = (\ell_i - m)/m$ for a short, where $\ell_i$ is the reported liquidation price. In sigma units, $z_i = d_i / \sigma_d$.

| Grade | $z_i$ (liquidation distance in daily sigmas) | $v_i$ (daily account volatility) |
| --- | --- | --- |
| A | at least 10, or no liquidation price | under 5% |
| B | 6 to 10 | 5% to 10% |
| C | 4 to 6 | 10% to 20% |
| D | 2.5 to 4 | 20% to 35% |
| F | under 2.5 | 35% or more |

A wallet's grade is the worse of the two columns. The aggregate grade is the notional-weighted mean on a 4-3-2-1-0 scale (A to F), mapped back to a letter.

**Squeeze warning.** Let skew $= |2p_t - 1|$ and let $q$ be the share of the dominant side's notional with $z_i < 4$. Squeeze risk is ELEVATED when skew $\ge 0.5$ and $q \ge 0.10$, and HIGH when skew $\ge 0.7$ and $q \ge 0.25$. Otherwise it is LOW.

### 2. Liquidation map `[intel.liquidation_map]`

Each position's liquidation price is placed in 1% bins of $\ell_i / m - 1$ within ±25%, and its BTC notional is summed per bin and side. Longs liquidate below the mark, shorts above it. The plate also reports cumulative notional within 5% and 10% each way, the largest cluster on each side, and notional beyond ±25% or with no liquidation price (common for low-leverage cross accounts).

### 3. Flip detector and market-change watch `[intel.flip]`, `[intel.market_watch]`

Each sweep stores every wallet's signed BTC size $s_i$ in `data/cohort.json`. On the next sweep, for wallets present both times, the net weight flow is

$$
F_t = \frac{\sum_i \left( \mathrm{sgn}(s_i^{t}) w_i^{t} - \mathrm{sgn}(s_i^{t-1}) w_i^{t-1} \right)}{\sum_i w_i^{t}}
$$

with both weights computed from current PnL and equity, so only size and side changes move it. Momentum is $\Delta_{3h} = p_t - p_{t-3h}$ and $\Delta_{24h} = p_t - p_{t-24h}$ (nearest stored snapshot).

- TURNING if $|\Delta_{3h}| \ge 0.12$, or $|F_t| \ge 0.10$, or net flips are at least 5% of voters.
- DRIFTING if $|\Delta_{3h}| \ge 0.05$, or $|F_t| \ge 0.04$, or net flips are at least 2% of voters.
- STABLE otherwise. The direction is the sign of $\Delta_{3h} + F_t$.

The market-change watch counts independent warning lights: the flip status is not STABLE; $p_t$ lies within 0.05 of a decision threshold; the regime is HIGH-VOL; the regime changed since the last sweep; squeeze risk is ELEVATED or HIGH; funding is beyond ±30% a year; an EMA 20/50 cross happened on 1h candles in the last 12 hours. None lit is QUIET, one or two is WATCH, three or more is ALERT.

### 4. Position-change feed `[intel.changes]`

Each compared wallet is classified as OPEN (flat to positioned), CLOSE, FLIP (side change), ADD, or CUT (same side, size changed by at least 10% and USD 50,000). The feed lists the 15 largest by $|\Delta s_i| \cdot m$. Wallets that joined or left the cohort between sweeps are counted as churn, not as trades.

### 5. History of P(long) `[data/history.json]`

One compact row per sweep, newest last, capped at 1,440 rows (30 days at 30 minutes). Each row holds $p_t$, the posterior mean, the interval, the mark, hourly funding, open interest, the fear and greed score, regime, flow, flips, aggregate grade, and integrity status.

### 6. Price action and EMA study `[intel.price_action]`, `[intel.ema]`

From `candleSnapshot`, the exponential moving average with span $n$ is

$$
\mathrm{EMA}_t = \alpha c_t + (1-\alpha)\,\mathrm{EMA}_{t-1}, \qquad \alpha = \frac{2}{n+1},
$$

seeded with the simple mean of the first $n$ closes. Spans 20, 50, and 200 are computed on 1h candles (35 days) and 1d candles (400 days). The stack label is UPTREND when price > EMA20 > EMA50 > EMA200, DOWNTREND for the reverse order, otherwise "above 200, mixed" or "below 200, mixed". Crosses are the last sign change of EMA20 − EMA50 and EMA50 − EMA200. Returns over 1h, 4h, 24h, 7d, and 30d and the position inside the 7-day range are shown beside the chart.

### 7. Regime detector `[intel.regime]`

Realised volatility over 24 hours, annualised, is

$$
\mathrm{RV}_{24} = \mathrm{sd}\left(\ln c_t - \ln c_{t-1}\right) \sqrt{24 \cdot 365}.
$$

Its percentile $\pi$ is taken against every rolling 24-hour window in the last 35 days. The Kaufman efficiency ratio over 48 hours is

$$
\mathrm{ER} = \frac{|c_t - c_{t-48}|}{\sum_{k=1}^{48} |c_{t-k+1} - c_{t-k}|} \in [0, 1].
$$

- HIGH-VOL if $\pi \ge 0.85$, labelled panic when the 24-hour return is negative and euphoria otherwise.
- TRENDING if $\mathrm{ER} \ge 0.30$, with the direction from the 24-hour slope of the 1h EMA50.
- RANGING otherwise. Funding beyond ±30% a year adds a crowding note.

### 8. Fear and greed meter `[intel.fear_greed]`

The score is the plain mean of the available components, each on 0 to 100 (100 is greed):

| Component | Formula |
| --- | --- |
| Funding | $50 + 50 \tanh(f_{\mathrm{ann}} / 0.25)$, where $f_{\mathrm{ann}}$ is the hourly rate times 8,760 |
| Leader skew | $100 \cdot \hat p_t$, the Bayesian posterior mean |
| Volatility | $100 (1 - \pi)$ |
| Momentum | $50 + 50 \tanh(z/2)$ with $z = r_{7d} / (\sigma_d \sqrt 7)$ |
| Open interest | $50 + 50 \tanh\left(\mathrm{sgn}(r_{24h}) \cdot \Delta \mathrm{OI}_{24h} / 0.05\right)$, once 24 hours of sweeps are stored |

Bands: under 25 extreme fear, 25 to 44 fear, 45 to 55 neutral, 56 to 75 greed, above 75 extreme greed. A missing component is left out, not imputed.

### 9. X sentiment `[intel.x_sentiment]`

Reserved for v2.0 (see [Roadmap](#roadmap-v20)). The sweep never calls X. If a valid `data/x_sentiment.json` exists (`ts_utc`, `n_posts`, and `score` in $[-1, 1]$ required; `window_hours`, `bull_share`, `bear_share`, `method` optional), it is passed through; otherwise the panel shows its planned state and no numbers.

### 10. Contrarian mode `[intel.contrarian]`

The faded reading is the opposite verdict with $1 - p_t$. A reading is extreme when $p_t \le 0.15$ or $p_t \ge 0.85$. From the accuracy tracker, the fade hit rate at 24 hours is the share of extreme readings followed by a move against the crowd. Fading is argued for only when at least 30 extreme readings have been scored and the fade hit rate exceeds 0.55. Until then the panel says the evidence is insufficient.

### 11. Fake-signal detector `[intel.integrity]`

With weight shares $u_i = w_i / \sum_j w_j$, the Herfindahl index is $\mathrm{HHI} = \sum_i u_i^2$ and the effective number of voters is $N_{\mathrm{eff}} = 1/\mathrm{HHI}$. Eight checks, each flagged on a fixed rule:

| Check | Flag when |
| --- | --- |
| Effective voters | $N_{\mathrm{eff}} < 10$ |
| Top-5 weight share | above 50% |
| Leave-top-5-out | the verdict changes when the five heaviest wallets are removed |
| Interval width | bootstrap width above 0.30, or the interval spans 0.50 |
| Participation | fewer than 50 voters, or under 15% of the cohort |
| Hedger / MM-like weight | over 30% of weight from wallets whose other perps offset at least 70% of their BTC notional, or whose month turnover is at least 50× equity |
| Count vs weight | head-count share and weighted share fall on opposite sides of 0.50 |
| Data age | the snapshot is older than two hours (re-checked in the browser) |

Status is CLEAN with no flags, CAUTION with one or two, SUSPECT with three or more.

### 12. Funding and open interest `[intel.funding_oi]`

Hourly funding comes from `fundingHistory` (30 days, shown as 8-hour means) and the live rate, open interest, and premium from `metaAndAssetCtxs`. Open interest history accrues one point per sweep in `history.json`. The combined reading crosses the crowd's verdict with the funding sign: leaders short while shorts pay funding means a crowded short side (squeeze fuel); leaders short while longs pay means leaders lean against the market, and the mirror cases for LONG.

### 13. Bayesian updating `[intel.bayes]`

An exponentially forgotten Beta-Binomial. Each sweep contributes $K_t = \min(N_{\mathrm{eff}}, 50)$ pseudo-observations split by $p_t$, and older evidence decays with a six-hour half-life:

$$
A_t = \lambda_t A_{t-1} + (1-\lambda_t) K_t p_t, \qquad B_t = \lambda_t B_{t-1} + (1-\lambda_t) K_t (1-p_t), \qquad \lambda_t = 2^{-\Delta t / 6\,\mathrm{h}}
$$

$$
\theta_t \sim \mathrm{Beta}(1 + A_t,\; 1 + B_t)
$$

The total pseudo-count tends to $K_t$, so repeated looks at the same positions do not manufacture certainty. The posterior is replayed from `history.json` each sweep, so it needs no hidden state. Rows stored before $N_{\mathrm{eff}}$ was recorded use $K = 25$. The plate shows the posterior mean, the 95% equal-tailed credible interval, $P(\theta > 0.5)$, and the gap between raw and posterior.

### 14. Backtesting `[intel.accuracy]`, `[intel.backtest]`

**Live accuracy tracker.** Each stored verdict at time $t$ is scored against the BTC price at $t+h$ for $h \in \{1, 4, 24\}$ hours, taken from the 15-minute candle containing $t+h$ (or the nearest stored mark within 20 minutes). Let $y = 1$ if price rose. Below, the denominator counts LONG and SHORT verdicts, and the numerator counts LONG verdicts followed by a rise plus SHORT verdicts followed by a fall:

$$
\text{hit rate} = \frac{n_{L,1} + n_{S,0}}{n_L + n_S}, \qquad \mathrm{BS} = \frac{1}{n}\sum (p_t - y)^2
$$

Brier scores are reported for the raw P(long) and the posterior, beside a coin (0.25) and the climatology baseline $\bar y(1-\bar y)$. Because snapshots are 30 minutes apart, rows overlap at 4h and 24h; the table shows an approximate independent count, the scored span divided by the horizon.

**Reconstructed seven-day backtest.** Once a day, the 30 wallets with the largest potential weight (skill times equity shrink) are read with `userFills` (latest 2,000 fills each). Each BTC fill carries its `startPosition`, so the position after a fill is $s = s_{\mathrm{start}} \pm \mathrm{sz}$, and the position at any hour is the end position of the last fill before it. Where a wallet's 2,000 fills do not reach back seven days, it is treated as unknown before its earliest fill. Hourly P(long) is recomputed with today's PnL and equity, scored at 4h and 24h, and turned into a "follow the verdict" curve (long when LONG, short when SHORT, flat when NEUTRAL; no costs) against holding BTC.

### 15. Lead-lag study `[intel.lead_lag]`

With $x_t = p_t - p_{t-1}$ and $y_t = \ln m_t - \ln m_{t-1}$ on a regular grid (30 minutes for live snapshots, 1 hour for the reconstructed series), the cross-correlation is

$$
r_k = \mathrm{corr}(x_t,\; y_{t+k}), \qquad k = -6, \dots, 6.
$$

Positive $k$ means the leaders' positioning changed first. The noise band is $\pm 1.96 / \sqrt{n}$. Gaps are skipped pairwise.

### 16. Front-running meter `[intel.front_running]`

$$
S = \frac{\sum_{k>0} r_k^2 - \sum_{k<0} r_k^2}{\sum_{k \ne 0} r_k^2} \in [-1, 1]
$$

$S > 0.2$ reads as FRONT-RUNNING (changes come before price moves) and $S < -0.2$ as CHASING, but only if the largest $|r_k|$ at a non-zero lag clears the noise band; otherwise the label is NO CLEAR LEAD. The live series is used once it has at least 30 paired steps; until then the reconstructed series is used and named. A companion number is the share of non-zero flows followed by a same-direction price move one hour (live) or four hours (reconstructed) later.

## Research: 30-day backtest

Would following this signal for 30 days have made money? A reconstructed backtest rebuilds the hourly P(long) from the fills of 100 cohort wallets and trades one unit of BTC perp on it, with the 0.045% taker fee and the hourly funding.

| Rule, 30 days to 25 Nov 2026 05:30 IST | Return after fees and funding | Max drawdown |
| --- | ---: | ---: |
| Follow the signal, daily | +32.2% | −4.7% |
| Always short | +32.2% | −4.7% |
| Buy and hold BTC | −25.9% | −28.0% |

**Profitable on paper, not evidence of an edge.** The signal read SHORT in all 721 hourly reads, so following it was the same trade as being short all month while BTC fell 25.4%. The window held no reversal, so it says nothing about whether the signal can call a turn. The cohort is also last month's winners, which biases it toward the side that won.

- Research note, with every formula, the 30-row day-by-day table, the reasons and the caveats: [`research/backtest-30d/README.md`](research/backtest-30d/README.md)
- Same page on the site: [Backtest tab](https://prafullj0shi.github.io/hyperliquid-btc-signal/#backtest)
- Data: [`daily_backtest.csv`](research/backtest-30d/data/daily_backtest.csv), [`results.json`](research/backtest-30d/data/results.json), [`hourly_signal.csv`](research/backtest-30d/data/hourly_signal.csv)
- Reproduce: `python research/backtest-30d/scripts/analyze.py`

## Limits

- Everything here describes public positions. Positions can be hedges, inventory, collateral management, or copy-flow; none of it is a forecast.
- **Survivorship in the reconstructed backtest.** Wallets are chosen because they won last month, then their past positions are scored. That is biased upward by construction. Only the live accuracy tracker is out-of-sample, and it starts with this release.
- **Fill cap.** `userFills` returns at most the latest 2,000 fills (10,000 by time query). Active wallets cover only part of the seven days; coverage is reported.
- **Overlapping samples.** Scored rows at 4h and 24h overlap heavily. Hit rates and Brier scores from a few days of snapshots are noisy; the independent count is shown for that reason.
- **Risk grade approximations.** Account volatility treats all exposure as moving one-for-one with BTC. Cross-margin liquidation prices depend on the whole account and move as other positions move.
- **Market-maker detection is heuristic.** Without per-wallet order books, "hedged elsewhere" and "high turnover" are proxies.
- **Lead-lag needs time.** With few stored sweeps the correlogram is mostly noise; the plate says so rather than drawing a conclusion. Correlation at a lag is not causation.
- **Open interest and its 24-hour change** are only as long as the stored history, so that fear and greed component starts empty.
- **Cohort churn.** The cohort is rebuilt hourly; wallets that join or leave are excluded from flows, but the P(long) series still reflects membership changes.
- The bootstrap interval and the Bayesian pseudo-count treat wallets as independent. They are not.

## Roadmap: v2.0

- **X sentiment.** Read the tone of public posts about Bitcoin on X over a fixed window, score it on $[-1, 1]$, and place it beside the leaders' positioning and the fear and greed meter. The panel and the `data/x_sentiment.json` schema are already in place; it stays empty, with no placeholder numbers, until the feed is connected.
- Longer live accuracy record, so contrarian mode and the front-running meter can move past "insufficient evidence".
- The same instrument for ETH, SOL, and HYPE.

## Architecture

```mermaid
flowchart LR
  A["Leaderboard file"] --> B["Filter and rank"]
  B --> C["portfolio top 500"]
  C --> D["clearinghouseState"]
  E["BTC mark"] --> F["Signal"]
  D --> F
  M["Candles, funding, OI"] --> L["Intelligence layer"]
  D --> L
  P["Previous sweep"] --> L
  F --> L
  L --> G["signal.json"]
  F --> G
  G --> H["GitHub Pages plate"]
  L --> Q["history.json"]
  Q --> H
  I["Actions every 30 min"] --> C
  I --> D
```

<p align="center">
  <img src="docs/architecture.svg" alt="Data flow from the public leaderboard and info endpoints, through the weighted signal, into signal.json and the GitHub Pages plate." width="100%">
</p>

A GitHub Actions workflow runs the Python sweep on a 30-minute cron and on manual dispatch. The heavier `portfolio` ranking is reused for up to an hour, and the fills-based backtest is rebuilt at most once a day. The job writes `data/signal.json` (verdict plus the `intel` block), `data/history.json` (one row per sweep, capped at 30 days), and `data/cohort.json` (cohort plus the previous sweep's per-wallet BTC sizes), commits them, and publishes the `site/` directory to GitHub Pages. No paid API and no private node are required.

### Data files

| File | Contents | Size policy |
| --- | --- | --- |
| `data/signal.json` | Verdict, interval, top positions, and `intel` (every panel's numbers and chart series) | about 75 KB |
| `data/history.json` | One compact row per sweep: P(long), posterior, mark, funding, OI, fear and greed, regime, flow, flips, grade, integrity | capped at 1,440 rows (30 days) |
| `data/cohort.json` | The 500 wallets and `last_positions` (BTC size per wallet at the previous sweep) | rewritten each sweep |
| `site/backtest/` | Backtest tab data: CSV, results, chart series and figures copied from `research/backtest-30d/` by `build_docs.py`. Static: the sweep neither writes nor deletes it | fixed |
| `data/x_sentiment.json` | Optional. Reserved for the v2.0 X sentiment feed; absent today | not read in CI unless present |

The workflow file is [`.github/workflows/sweep.yml`](.github/workflows/sweep.yml). A copy is also kept at [`docs/github-workflow-sweep.yml`](docs/github-workflow-sweep.yml).

## How to run it locally

Python 3.11 or newer, then:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.sweep          # first run rebuilds the cohort (about 10–15 min)
.venv/bin/python -m app.sweep          # later runs inside the hour skip portfolio
```

Serve the plate:

```bash
.venv/bin/pip install -r requirements.txt   # includes uvicorn
.venv/bin/python -m app.main                # http://127.0.0.1:8000/
# or:  python3 -m http.server 8000 --directory site --bind 127.0.0.1
```

`GET /api/signal` and `GET /api/history` are served by the local FastAPI process. The public site is static and only needs `site/data/signal.json`.

Unit tests (no network):

```bash
.venv/bin/pytest -q
```

## Filters, rate limits, and cadence

| Rule | Value | Why |
| --- | --- | --- |
| Minimum equity | $10,000 | Drops dust accounts. |
| Month PnL | strictly greater than 0 | The cohort is last month’s winners, not lifetime. |
| Turnover cap | month volume / equity $\le 100$ | In a 24 Nov 2026 snapshot, wallets at 117–217× turnover looked market-maker-like; a named discretionary trader sat near 94×. 100 is a heuristic, not a perfect filter. |
| Ranking field | `portfolio` window `perpMonth` | The raw leaderboard month PnL is not perp-only (spot and other PnL can dominate, sometimes with near-zero volume). |
| Candidate pool | 700, then 500 | Extra names backfill wallets whose perp month PnL is not positive. |
| Info API budget | 1,200 weight / minute / IP | `portfolio` weighs 20; `clearinghouseState` and `allMids` weigh 2; `candleSnapshot`, `fundingHistory`, and `userFills` weigh 20 plus one unit per 60 candles or 20 rows, which the client charges after each response. The sweep uses a token bucket and backs off on HTTP 429. |
| Market context | about 120 weight / sweep | Three candle series (1h for 35 days, 1d for 400 days, 15m for 16 days) and 30 days of hourly funding. |
| Backtest refresh | once a day, about 3,600 weight | `userFills` for 30 wallets, spread over about three minutes by the bucket. |
| Actions | every 30 minutes | A full 700-wallet `portfolio` pass is about ten to fifteen minutes, which would overlap a 15-minute cron. Portfolio is refreshed at most hourly. |

The leaderboard is the undocumented public file [https://stats-data.hyperliquid.xyz/Mainnet/leaderboard](https://stats-data.hyperliquid.xyz/Mainnet/leaderboard) (about 38 MB, typically close to hourly). It is cached with `If-None-Match`. All other reads are official `POST https://api.hyperliquid.xyz/info` requests.

## Operational limits

- A WebSocket cannot subscribe to 500 users from one IP (the official cap is 10 unique users). This project polls REST.
- GitHub Actions shares a datacenter IP; 429s will slow a run. The job is allowed 40 minutes; a run with a cohort rebuild and the daily backtest takes about 15.
- The turnover cap will admit some market makers and exclude some active discretionary traders.
- Leaderboard and `portfolio` windows are not intra-minute. Positions are polled more often than the cohort is rebuilt.

## License

MIT, Copyright (c) 2026 Prafull Joshi. IBM Plex fonts are included under the SIL Open Font License (see `site/fonts/OFL.txt`).
