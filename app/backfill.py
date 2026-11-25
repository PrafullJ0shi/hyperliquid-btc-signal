"""Seed the top cohort's flow log from snapshots already in git history.

Every snapshot commit since the intelligence layer stored the full per-wallet
BTC size of the top cohort in data/cohort.json ("last_positions"). Replaying
consecutive snapshots gives exactly the steps the live sweep computes. The
worst-performing cohort has no stored snapshots and builds its own history.
Runs once, when cohort.json has no flow_log yet; the Actions checkout has the
full history (fetch-depth 0).
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from . import flow as F
from .tracking import ts_ms

log = logging.getLogger("backfill")


def git_snapshots(root: Path, max_commits: int = 600) -> list[tuple[int, float, dict[str, float]]]:
    shas = subprocess.run(
        ["git", "log", f"-n{max_commits}", "--format=%H", "--", "data/cohort.json"],
        cwd=root, capture_output=True, text=True, check=True, timeout=60,
    ).stdout.split()
    seen: dict[int, tuple[int, float, dict[str, float]]] = {}
    for sha in shas:
        raw = subprocess.run(["git", "show", f"{sha}:data/cohort.json"], cwd=root,
                             capture_output=True, text=True, timeout=60).stdout
        try:
            lp = json.loads(raw).get("last_positions")
        except json.JSONDecodeError:
            continue
        if not lp or not lp.get("positions") or not lp.get("mark"):
            continue
        t = ts_ms(lp.get("ts_utc"))
        if t and t not in seen:
            seen[t] = (t, float(lp["mark"]), {a: F._szi(v) for a, v in lp["positions"].items()})
    return [seen[t] for t in sorted(seen)]


def flow_log_from_snapshots(snaps: list[tuple[int, float, dict[str, float]]], now_ms: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    prev = None
    for t, mark, pos in snaps:
        if t < now_ms - F.FLOW_LOG_MAX_MS:
            prev = (t, mark, pos)
            continue
        step = F.flow_step(prev[2] if prev else None, pos, mark)
        out = F.append_log(out, t, prev[0] if prev else None, {"s": step, "c": None}, src="git")
        prev = (t, mark, pos)
    return out


def events_from_snapshots(snaps: list[tuple[int, float, dict[str, float]]], now_ms: int,
                          min_usd: float) -> list[dict[str, Any]]:
    """Whale position entries replayed from stored snapshots (no fills, so no fill price,
    leverage, or margin: only what the two snapshots show)."""
    from .tape import action_of, TAPE_MAX_MS
    out = []
    for (tp, _, prev), (t, mark, cur) in zip(snaps, snaps[1:]):
        if t < now_ms - TAPE_MAX_MS:
            continue
        for a, c in cur.items():
            if a not in prev:
                continue
            p = prev[a]
            if abs(c - p) * mark < min_usd:
                continue
            act = action_of(p, c)
            if not act:
                continue
            out.append({
                "key": f"pos:{a}:{t}", "kind": "position", "t": t, "t_snap": t, "t_prev": tp,
                "address": a, "cohort": "smart", "verb": act[0], "side": act[1],
                "change_usd": round(abs(c - p) * mark, 2), "before_usd": round(abs(p) * mark, 2),
                "now_usd": round(abs(c) * mark, 2), "before_side": "LONG" if p > 0 else ("SHORT" if p < 0 else "FLAT"),
                "px": None, "px_source": "mark", "mark": round(mark, 2), "src": "git",
            })
    return out


def seed_flow_log(root: Path, cohort: dict[str, Any], now_ms: int) -> Optional[list[dict[str, Any]]]:
    """Flow log replayed from git, including the current file's last_positions."""
    try:
        snaps = git_snapshots(root)
    except Exception as exc:  # noqa: BLE001 — no git, shallow clone, or timeout
        log.warning("Could not read snapshots from git: %s", exc)
        snaps = []
    lp = cohort.get("last_positions") or {}
    t = ts_ms(lp.get("ts_utc"))
    if t and lp.get("positions") and lp.get("mark") and all(s[0] != t for s in snaps):
        snaps.append((t, float(lp["mark"]), {a: F._szi(v) for a, v in lp["positions"].items()}))
        snaps.sort(key=lambda s: s[0])
    if not snaps:
        return None
    out = flow_log_from_snapshots(snaps, now_ms)
    log.info("Seeded flow log from %s stored snapshots (%s rows)", len(snaps), len(out))
    return out


def seed_state(root: Path, cohort: dict[str, Any], now_ms: int, whale_min_usd: float) -> dict[str, Any]:
    """flow_log and replayed whale entries for a cohort.json that has neither."""
    try:
        snaps = git_snapshots(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read snapshots from git: %s", exc)
        snaps = []
    lp = cohort.get("last_positions") or {}
    t = ts_ms(lp.get("ts_utc"))
    if t and lp.get("positions") and lp.get("mark") and all(s[0] != t for s in snaps):
        snaps.append((t, float(lp["mark"]), {a: F._szi(v) for a, v in lp["positions"].items()}))
        snaps.sort(key=lambda s: s[0])
    if not snaps:
        return {}
    out = {"flow_log": flow_log_from_snapshots(snaps, now_ms),
           "whales": events_from_snapshots(snaps, now_ms, whale_min_usd)}
    log.info("Seeded %s flow rows and %s whale entries from %s stored snapshots",
             len(out["flow_log"]), len(out["whales"]), len(snaps))
    return out
