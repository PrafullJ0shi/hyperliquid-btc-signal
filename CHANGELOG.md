# Changelog

Notable changes to this project are listed here. Dates are in IST (UTC+5:30). The live plate is [prafullj0shi.github.io/hyperliquid-btc-signal](https://prafullj0shi.github.io/hyperliquid-btc-signal/).

## 1.2.0 — 25 November 2026

The current public release: a Backtest tab, a Flows tab, and a more reliable publish path.

### Added

- A **Backtest tab** on the plate, and a reconstructed 30-day research note under `research/backtest-30d/`, with data, figures, and a method that states its survivorship bias. In the published window the signal read SHORT in every hour, so following it was the same trade as being short while Bitcoin fell; the note says this is not evidence of an edge.
- A **Flows tab**: a past-4-hour flow box (opened, added, closed, trimmed) with 1h to 1w timeframes, the top cohort set against a worst-performing contrast cohort, a whale tape (large position changes, large orders, and orders worked over time), and a sampled liquidation tape with a wave detector and a labelled open-interest proxy. The step log is seeded once from snapshots in git history.

### Fixed

- **Publishing.** The sweep and GitHub Pages deploy were split into two jobs, with retries, after several runs had a successful sweep but failed at deploy with a missing Pages artifact or a transient "try again later" error.

## 1.1.0 — 25 November 2026

### Added

- A **market-intelligence layer** computed in the same sweep from public Hyperliquid data: cohort risk grades and a squeeze warning, a liquidation map, a flip detector and market-change watch, a position-change feed, the history of P(long) with a Bayesian posterior, price action with an EMA study, a regime detector, a fear and greed meter, funding and open interest, a fake-signal detector, contrarian mode, a fills-based backtest, a lead-lag study, and a front-running meter.
- A reserved **X sentiment** panel and the `data/x_sentiment.json` hook, left empty and planned for v2.0; the sweep does not call X.

## 1.0.0 — 24 November 2026

### Added

- The initial public instrument: a weighted P(long) over Bitcoin perpetual positions held by the top 500 Hyperliquid wallets ranked on last-month perp PnL, a 95% bootstrap interval, and a LONG / SHORT / NEUTRAL verdict.
- A typographic GitHub Pages plate (inclination sphere, instrument tables, figure captions), a 30-minute GitHub Actions sweep against public endpoints, and the documented method in the README.
