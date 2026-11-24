"""Tunable constants. Documented in the README."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
SITE_DIR = ROOT / "site"
SITE_DATA_DIR = SITE_DIR / "data"
DB_PATH = DATA_DIR / "signal.db"
SIGNAL_JSON = DATA_DIR / "signal.json"
SITE_SIGNAL_JSON = SITE_DATA_DIR / "signal.json"
HISTORY_JSON = DATA_DIR / "history.json"
SITE_HISTORY_JSON = SITE_DATA_DIR / "history.json"
COHORT_JSON = DATA_DIR / "cohort.json"
LEADERBOARD_CACHE = CACHE_DIR / "leaderboard.json"
LEADERBOARD_META = CACHE_DIR / "leaderboard_meta.json"

LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
INFO_URL = "https://api.hyperliquid.xyz/info"
USER_AGENT = (
    "hyperliquid-btc-signal/0.1 "
    "(+https://github.com/PrafullJ0shi/hyperliquid-btc-signal)"
)

# Cohort filters
MIN_EQUITY = 10_000.0
# Month PnL must be strictly greater than this value (USD).
MIN_MONTH_PNL = 0.0
# Month volume / account value. Names with 117–217x turnover in the
# 24 Nov 2026 snapshot looked market-maker-like; a named discretionary
# trader sat near 94x. A cap of 100 keeps the latter and drops the tail.
MAX_TURNOVER = 100.0
TOP_N = 500
# Extra leaderboard names to score with `portfolio` so drop-outs
# (non-perp month PnL) can be backfilled toward TOP_N.
CANDIDATE_POOL = 700

# Weights
EQUITY_FULL_WEIGHT = 100_000.0  # shrink reaches 1.0 at this equity
CONVICTION_CAP = 3.0

# Verdict
P_LONG_THRESHOLD = 0.60
P_SHORT_THRESHOLD = 0.40

# Interval
BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 42
BETA_PRIOR_A = 1.0
BETA_PRIOR_B = 1.0
CI_LEVEL = 0.95

# Rate limits (official info API, per IP)
WEIGHT_CAPACITY = 1200
WEIGHT_REFILL_PER_MINUTE = 1200
WEIGHT_CLEARINGHOUSE = 2
WEIGHT_ALL_MIDS = 2
WEIGHT_PORTFOLIO = 20
WEIGHT_META_AND_CTXS = 20
MAX_CONCURRENCY = 6
HTTP_TIMEOUT = 60.0
RETRY_STATUS = (429, 500, 502, 503, 504)
MAX_RETRIES = 6

# Refresh policy
PORTFOLIO_TTL_SEC = 60 * 60
LEADERBOARD_TTL_SEC = 60 * 60
HISTORY_MAX_POINTS = 200

# HTTP
REQUEST_TIMEOUT = HTTP_TIMEOUT
