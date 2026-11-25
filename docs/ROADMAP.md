# Roadmap: v2.0

This is a plan for the next increment of the public instrument at [prafullj0shi.github.io/hyperliquid-btc-signal](https://prafullj0shi.github.io/hyperliquid-btc-signal/). It is not a schedule, not a promise of delivery, and **not a promise of profit**. Nothing here is financial advice. Features ship when the method, the data, and the limits can be stated as clearly as the readings that already exist.

Priorities: **P1** first, then **P2**, then **P3**. There are no target dates. A few items only become informative after enough live snapshots have accrued; those say so below. A short table also lives in the [main README](../README.md#upcoming-v20).

## Principles

- Stay inside the project's rules: public data, documented methods, GitHub-safe formulas, and the visual language in [`DESIGN.md`](../DESIGN.md).
- Do not change the signal verdict's meaning. P(long) remains a function of the cohort's Bitcoin positions. New context (sentiment, a wider liquidation tape, another coin) sits beside that reading; it does not override it.
- Do not invent numbers. Empty states stay empty until a real feed is connected, the same way the reserved X sentiment panel already behaves.
- Keep the Actions job inside a reasonable runtime and the official 1,200 weight-per-minute budget, or run any heavier or always-on work outside the 30-minute sweep and write a file the sweep already knows how to read.
- Report limits next to results. A profitable-looking number without its bias is not finished work.

## P1 — X sentiment

The core item. A reserved panel and the `data/x_sentiment.json` hook already exist. Prafull deferred the feed itself to v2.0. The sweep never calls X today. If a valid file is present (`ts_utc`, `n_posts`, and `score` in [−1, 1] required; `window_hours`, `bull_share`, `bear_share`, `method` optional), it is passed through as `intel.x_sentiment` and the panel shows the numbers; otherwise the panel stays in its planned state with no placeholder values. That contract does not change.

### Goal

Read the tone of public posts about Bitcoin on X over a fixed window, score it on [−1, 1], and place it beside the leaders' positioning and the fear and greed meter, including a clearly labelled contrarian reading.

### Data source options

1. **The existing file hook (first step).** An external process, documented and tested, writes `data/x_sentiment.json`. The sweep only validates and forwards it, which is already implemented. This keeps secrets and third-party rate limits out of the public Actions job.
2. **Official X API, curated accounts.** A developer project calls the v2 recent-search or user-timeline endpoints for a published list of accounts and a Bitcoin keyword filter. Useful volume on the official API now requires a paid tier. Credentials would live as a repository secret, or, better, in the external writer from option 1 so CI stays credential-free. Either way the cost, the tier, and the account list must be documented.
3. **Not in scope unless the first two fail and the failure is written down:** scraping, unofficial mirrors, or a paid third-party sentiment vendor. Those break the "public endpoints only, no paid API" posture the rest of the instrument still holds, and they would have to be named as such on the panel.

### Method

- Score a **fixed, versioned list** of accounts that post about Bitcoin, plus a keyword filter (for example BTC, Bitcoin). This is not "the mood of all of X".
- Give each post a score in [−1, 1]. The first scorer should be a **published lexicon** (reproducible, no hidden weights). A model scorer is a later option only if it beats the lexicon on a labelled hold-out set, and then the model and the set are documented.
- **Volume-weight** the posts, for example by log(1 + engagements), with a cap so one viral post cannot dominate silently. The headline score is the weighted mean. Bullish and bearish shares are the weighted shares of posts scored positive or negative.
- **Contrarian reading.** Compare the score to the fear and greed meter and to P(long). Extreme public bullishness while the cohort is short (or the reverse) is a context note, not a trade. The signal verdict stays a function of positions only.
- **Fear and greed.** Add an optional sixth component, 50 + 50 times the score, included only when the file is present, the status is CONNECTED, and the timestamp is fresh (for example younger than two hours). A missing component is left out, not imputed, the same as today.

### Validation

Store the score in `data/history.json` once the feed is connected. Pre-register the tests before looking at results:

- Correlation of the score with the next 4-hour and 24-hour BTC return.
- Hit rate of a rule that fades extreme sentiment (thresholds fixed in advance).
- Incremental value versus the current fear and greed meter without this component.

Refuse a conclusion until a stated sample is in (for example 30 independent windows), and say "insufficient evidence" until then, the same way contrarian mode already does. None of these tests, if they look good, would be evidence of an edge you can trade.

### Limits

Sarcasm, bots, quote-tweets, language, and the choice of accounts all bias the score. API outages and tier changes can leave the panel empty. A lexicon will miss tone that a human would catch. This is not a forecast of price, and it is not a second signal.

### Done when

- A documented scorer writes a valid `data/x_sentiment.json`, with tests for the schema and the aggregation.
- A connected file turns the reserved panel from planned to CONNECTED, with no numbers shown when the file is absent or stale.
- Fear and greed optionally includes the component under the freshness rule above.
- The README states the method, the account-list rule, the sources, and the validation plan.
- The series has started to accrue in `history.json`.

## P1 — Live out-of-sample backtest

### Goal

Score the live signal from the snapshots this repository already stores, as they were issued, and publish that record next to the reconstructed 30-day study. The existing [30-day backtest](../research/backtest-30d/README.md) rebuilds the past from last month's winners and their fills; that is useful, and it is biased by construction (survivorship, and in the published window the signal never left SHORT). The live accuracy tracker in `intel` already starts with this release. v2.0 should grow it into a true out-of-sample path: no hindsight cohort, no reconstructed fills.

### Method

Each stored row in `data/history.json` already has P(long), the verdict, and the BTC mark at issue time. After the horizon (4 hours, 24 hours, and a daily close) has elapsed, score whether following the issued verdict, or standing aside on NEUTRAL, would have been followed by a favourable move, after the same taker fee and funding used in the reconstructed study. Walk forward only: a row is scored with information that existed at that sweep. Cohort membership is whatever the live sweep had that hour, including churn.

Publish a second block on the Backtest tab, clearly labelled "live, out-of-sample", with an equity path, hit rate, and the same style of caveats as the reconstructed note. Do not mix the two series.

### Data needed

The growing `data/history.json` (already capped at 30 days; the cap may need a longer companion file if the live path should span more than a month). Marks and funding at each sweep are already stored or can be joined from the same public endpoints.

### Limits

The cohort still turns over as the leaderboard is rebuilt, so this is out-of-sample for the issued verdict, not a test of a frozen set of wallets. Thirty days of snapshots is a short record; overlapping 4-hour windows are not independent. A good or bad path can be one market regime. This will not, on its own, show that the signal has an edge.

### Done when

- A scorer with tests reads only stored snapshots and never peeks past the issue time.
- The Backtest tab shows the live path beside the reconstructed study, with sample size and a refusal to conclude below a stated count (for example 30 independent daily points).
- The README and the research note describe both series and their different biases.

## P2 — Multi-coin: ETH, SOL, and HYPE

### Goal

The same instrument for Ether, Solana, and HYPE perpetuals, without abandoning the Bitcoin plate.

### Method

The code already has a single coin setting (`TRACK_COIN`). Each `clearinghouseState` response already carries every perpetual on the account, so a second coin's size, notional, and liquidation price can be read from the same 500 (and contrast 500) polls. That part is cheap. What is not free is the market context: candles, funding, and open interest are per coin, as are the flow log, the whale tape, and the liquidation sample. The site needs either a coin control or a distinct plate per coin, with history series that do not overwrite one another.

### Data needed

Per-coin series in `signal.json` / `history.json` (or sibling files), still only from public Hyperliquid endpoints. The leaderboard and `portfolio` ranking stay account-level; they are not coin-specific.

### Limits

Rate budget grows with every candle and funding fetch, and with any extra fill scans. A wallet can be a one-month leader on BTC and not on ETH. Liquidation prices on cross-margin accounts still depend on the whole account. HYPE, as the venue's own token, is a special market and should be labelled as such. Shipping three more coins is not three times the information if the same wallets dominate.

### Done when

- ETH, SOL, and HYPE each have a P(long), a verdict, a short history, and a documented method, selectable on the plate without breaking the BTC view.
- Tests cover the extractor for a non-BTC coin and the file layout.
- The rate-limit table in the README is updated for the added fetches.

## P2 — Market-wide liquidation feed, if feasible

### Goal

Replace, or sit beside, the current sampled liquidation tape with a market-wide BTC liquidation series, so a wave is a count of what happened in the market, not only of what touched the tracked wallets' fills.

### Method and feasibility

Hyperliquid's public info API still has **no market-wide liquidation endpoint**. Official WebSocket subscriptions offer `trades` for a coin and per-user events (`userEvents`, `userFills`), and a single IP may subscribe to at most 10 users. There is no official public "all liquidations" channel in the documented subscription list. Third-party streams exist; they are not the public Hyperliquid API and would have to be named if used.

A 30-minute GitHub Actions job also **cannot hold a socket open** between runs. `recentTrades` returns only a handful of rows, so polling it every half hour will miss almost every event.

What can be tried, in order:

1. Confirm whether public `trades` messages carry a liquidation flag. If they do, a **long-running listener** (a small host, not Actions) could accumulate a BTC tape and write a file the sweep already knows how to merge, the same pattern as `x_sentiment.json`.
2. If they do not, decide whether a named third-party feed is acceptable, or keep the current design: a lower-bound tape from tracked wallets, plus the labelled open-interest proxy.

If none of those is durable and public enough, the honest v2.0 outcome is to document the gap and leave the sampled tape in place. That is a finished investigation, not a failed feature.

### Data needed

Either a documented public stream plus a host that writes a compact event file, or a clear written finding that no such public stream exists.

### Limits

A hosted listener is new infrastructure this project does not have today. A third-party feed is a dependency and may not be free. Any tape that still misses events must be labelled a lower bound. The open-interest proxy remains an upper bound, because voluntary closes also reduce open interest.

### Done when

- Either a market-wide BTC series is on the Flows tab, with source, coverage, and gap handling documented, **or** the investigation is written up and the sampled tape plus proxy remain, with the conclusion stated.
- Tests cover merge, deduplication, and the wave rule on the new series if one is added.

## P2 — Regime-conditioned accuracy

### Goal

Report the live scorer separately in HIGH-VOL, TRENDING, and RANGING regimes, so a single hit rate cannot hide a regime where the reading fails.

### Method

Slice the live out-of-sample scores (the P1 backtest above) by the regime already stored on each history row. Use the same horizons and the same refusal rule: no conclusion in a bucket until a stated independent count is in. This item depends on the live scorer having enough rows; it is not informative in the first weeks of snapshots.

### Data needed

`data/history.json` rows that already carry regime, P(long), and the mark.

### Limits

Buckets will be uneven. Overlapping windows still are not independent. A regime label is a heuristic (realised volatility percentile and Kaufman efficiency). Small counts will look dramatic; the plate should refuse them.

### Done when

- The Backtest tab, or the accuracy panel, shows per-regime hit rates with counts, and stays silent in any bucket below the threshold.
- Tests cover the split and the refusal rule.

## P3 — Alerts on flips and liquidation waves

### Goal

Notify someone when the issued verdict flips, when the market-change watch moves to ALERT, or when the liquidation wave (or its labelled proxy) fires, without turning the project into a chat product.

### Method

The lowest-infrastructure path is a **static RSS or Atom feed** published on GitHub Pages from the same sweep, one entry per flip or wave, with the issued numbers and a link to the plate. Telegram or email can sit on top of that feed, or be sent from Actions with a repository secret, as an optional extra. Alerts should fire on the issued state, not on an unpublished draft, and should not repeat on every sweep while the same state holds.

### Data needed

The existing `intel.flip`, `intel.market_watch`, and `intel.tracker.liquidations` fields, plus a small record of what was already announced.

### Limits

GitHub Actions is not a real-time bus; a flip can wait until the next 30-minute run, and a delayed or failed job is a missed alert. Telegram and email need credentials and an operator. RSS is delayed by the same cadence but needs no account. This is a notification of a public reading, not a trading trigger.

### Done when

- An RSS feed is on the public site, documented, and covered by a test for "announce once per state change".
- Telegram or email, if added, is optional, secret-based, and documented as such.

## P3 — Weekly research note

### Goal

A short, dated note once a week that records what the plate said, what the market did, and what the live scorer has accrued, in the same voice as the Backtest tab: a report, not a newsletter.

### Method

A script builds a markdown page from `history.json` and the live scorer (range of P(long), verdicts, notable flips, wave flags, accuracy counts). It is committed or published to the site, perhaps from a weekly Actions schedule. No new forecasts. If the week is uneventful, the note says so.

### Data needed

Stored snapshots and the live scorer. No extra endpoints required.

### Limits

A weekly note can overfit a story to one quiet week. It must not read like a recommendation. If the generator cannot run, skip the week rather than invent a summary.

### Done when

- A reproducible script writes a note with tests against a fixture week, and a first real note is published with its data range in the title.
- The README links the series.

## P3 — Per-wallet pages

### Goal

From the whale tape, the position feed, or the cohort tables, open a page for one tracked wallet: current BTC position, risk grade, recent flow, and the public explorer link.

### Method

Client-side route (for example a hash of the address) reading from the already-published snapshot, so 500 static files need not be committed. Fills stay limited to what the sweep already fetched. Pages are for wallets in the current cohorts, not an open search of the chain.

### Data needed

`signal.json` and the tracker already stored in that snapshot. Further fill history would need extra `userFills` budget and a cap.

### Limits

These are public positions, but a gallery of wallets is still easy to misuse as a copy-trading list; the page should say so. Membership churns hourly. Fills are partial. This is a view of one account at issue time, not a profile or a recommendation.

### Done when

- A wallet in the tape or the feed links to a page that renders from the snapshot, works at 390px, and states the limits above.
- Tests cover a fixture wallet and the empty case (address not in the current snapshot).

## Summary

| Priority | Feature | Depends on | Status |
| --- | --- | --- | --- |
| P1 | X sentiment | Official X API or an external file writer; the hook already exists | Planned |
| P1 | Live out-of-sample backtest | Growing `history.json` | Planned |
| P2 | Multi-coin (ETH, SOL, HYPE) | Same polls; extra market-context fetches | Planned |
| P2 | Market-wide liquidation feed | A public stream and a host, if they exist | Planned, if feasible |
| P2 | Regime-conditioned accuracy | The live backtest, and enough rows per regime | Planned |
| P3 | Alerts (RSS first; Telegram/email optional) | Issued flip and wave flags | Planned |
| P3 | Weekly research note | Stored snapshots | Planned |
| P3 | Per-wallet pages | Published snapshot | Planned |

Items not on this list, including a faster cron, a second visual theme, or a claim that the signal has an edge, are out of scope for v2.0.
