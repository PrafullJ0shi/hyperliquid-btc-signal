"""SQLite snapshots plus the public JSON files consumed by the static site."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import config
from .timeutil import format_ist, iso_utc, now_utc, to_ist


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    ts_ist TEXT NOT NULL,
    btc_mark REAL,
    n_traders INTEGER,
    n_long INTEGER,
    n_short INTEGER,
    n_flat INTEGER,
    notional_long REAL,
    notional_short REAL,
    p_long REAL,
    ci_low REAL,
    ci_high REAL,
    beta_ci_low REAL,
    beta_ci_high REAL,
    verdict TEXT,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts_utc);
"""


def connect(path: Path = config.DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_snapshot(payload: dict[str, Any], path: Path = config.DB_PATH) -> int:
    conn = connect(path)
    try:
        cur = conn.execute(
            """
            INSERT INTO snapshots (
                ts_utc, ts_ist, btc_mark, n_traders, n_long, n_short, n_flat,
                notional_long, notional_short, p_long, ci_low, ci_high,
                beta_ci_low, beta_ci_high, verdict, payload
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                payload.get("ts_utc"),
                payload.get("ts_ist"),
                payload.get("btc_mark"),
                payload.get("n_traders"),
                payload.get("n_long"),
                payload.get("n_short"),
                payload.get("n_flat"),
                payload.get("notional_long"),
                payload.get("notional_short"),
                payload.get("p_long"),
                payload.get("ci_low"),
                payload.get("ci_high"),
                payload.get("beta_ci_low"),
                payload.get("beta_ci_high"),
                payload.get("verdict"),
                json.dumps(payload),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def load_history(limit: int = config.HISTORY_MAX_POINTS, path: Path = config.DB_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    conn = connect(path)
    try:
        rows = conn.execute(
            """
            SELECT ts_utc, ts_ist, btc_mark, p_long, ci_low, ci_high, verdict,
                   n_long, n_short, n_flat, n_traders
            FROM snapshots
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    out = [dict(r) for r in rows]
    out.reverse()
    return out


SLIM_KEYS = (
    "ts_utc", "ts_ist", "btc_mark", "p_long", "ci_low", "ci_high", "verdict",
    "n_long", "n_short", "n_flat", "n_traders",
)


def _round(v: Any) -> Any:
    """Six decimals, or six significant digits for small values such as hourly funding."""
    if isinstance(v, float):
        if v != 0 and abs(v) < 0.01:
            return float(f"{v:.6g}")
        return round(v, 6)
    return v


def slim_row(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: payload.get(k) for k in SLIM_KEYS}


def history_text(history: list[dict[str, Any]]) -> str:
    """A JSON array with one compact row per line, so each sweep's git diff is one line."""
    lines = [json.dumps({k: _round(v) for k, v in h.items()}, separators=(",", ":")) for h in history]
    return "[\n" + ",\n".join(lines) + "\n]\n"


def write_json_files(payload: dict[str, Any], history: list[dict[str, Any]]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    tail = [slim_row(h) for h in history[-config.SIGNAL_HISTORY_POINTS:]]
    public = {**payload, "history": tail}
    text = json.dumps(public, separators=(",", ":"))
    config.SIGNAL_JSON.write_text(text)
    config.SITE_SIGNAL_JSON.write_text(text)
    hist_text = history_text(history)
    config.HISTORY_JSON.write_text(hist_text)
    config.SITE_HISTORY_JSON.write_text(hist_text)


def load_history_json() -> list[dict[str, Any]]:
    for path in (config.HISTORY_JSON, config.SITE_HISTORY_JSON):
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                continue
    return []


def load_x_sentiment() -> Optional[dict[str, Any]]:
    """Optional file written outside CI. Absent or malformed returns None."""
    if not config.X_SENTIMENT_JSON.exists():
        return None
    try:
        data = json.loads(config.X_SENTIMENT_JSON.read_text())
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def load_latest_json() -> Optional[dict[str, Any]]:
    if config.SIGNAL_JSON.exists():
        return json.loads(config.SIGNAL_JSON.read_text())
    if config.SITE_SIGNAL_JSON.exists():
        return json.loads(config.SITE_SIGNAL_JSON.read_text())
    return None


def write_cohort(cohort: dict[str, Any]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.COHORT_JSON.write_text(json.dumps(cohort, indent=2))


def load_cohort() -> Optional[dict[str, Any]]:
    if not config.COHORT_JSON.exists():
        return None
    try:
        return json.loads(config.COHORT_JSON.read_text())
    except json.JSONDecodeError:
        return None
