"""Async client for Hyperliquid public endpoints only."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from . import config
from .rate_limit import Backoff, WeightBucket


class HyperliquidClient:
    def __init__(self) -> None:
        self.bucket = WeightBucket()
        self.backoff = Backoff()
        self._sem = asyncio.Semaphore(config.MAX_CONCURRENCY)
        headers = {
            "User-Agent": config.USER_AGENT,
            "Accept": "application/json",
        }
        self._http = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(config.HTTP_TIMEOUT, connect=20.0),
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "HyperliquidClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        weight: int = 0,
        json_body: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        last_error: Optional[Exception] = None
        for attempt in range(config.MAX_RETRIES):
            if weight:
                await self.bucket.acquire(weight)
            async with self._sem:
                try:
                    response = await self._http.request(
                        method,
                        url,
                        json=json_body,
                        headers=headers,
                    )
                except httpx.HTTPError as exc:
                    last_error = exc
                    await asyncio.sleep(self.backoff.delay(attempt))
                    continue
            if response.status_code in config.RETRY_STATUS:
                last_error = RuntimeError(
                    f"{response.status_code} from {url} (attempt {attempt + 1})"
                )
                # 429: honour Retry-After if present, else backoff.
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    await asyncio.sleep(min(float(retry_after), 60.0))
                else:
                    await asyncio.sleep(self.backoff.delay(attempt))
                continue
            if response.status_code >= 400:
                raise RuntimeError(
                    f"{response.status_code} from {url}: {response.text[:300]}"
                )
            return response
        raise RuntimeError(f"exhausted retries for {url}: {last_error}")

    async def fetch_leaderboard(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """GET the stats-data leaderboard, using If-None-Match when cached."""
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        etag = None
        meta: dict[str, Any] = {}
        if config.LEADERBOARD_META.exists():
            try:
                meta = json.loads(config.LEADERBOARD_META.read_text())
                etag = meta.get("etag")
            except json.JSONDecodeError:
                meta = {}
        headers: dict[str, str] = {}
        if etag and config.LEADERBOARD_CACHE.exists():
            headers["If-None-Match"] = etag
        # This host is not the weighted info API; do not spend bucket tokens.
        response = await self._request("GET", config.LEADERBOARD_URL, headers=headers or None)
        fetched_at = time.time()
        if response.status_code == 304 and config.LEADERBOARD_CACHE.exists():
            data = json.loads(config.LEADERBOARD_CACHE.read_text())
            meta = {**meta, "fetched_at": fetched_at, "not_modified": True}
            config.LEADERBOARD_META.write_text(json.dumps(meta, indent=2))
            return data.get("leaderboardRows") or [], meta
        # httpx does not expose 304 if we used request that follows... 304 is valid
        data = response.json()
        config.LEADERBOARD_CACHE.write_text(json.dumps(data))
        new_meta = {
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "fetched_at": fetched_at,
            "bytes": len(response.content),
            "not_modified": False,
        }
        config.LEADERBOARD_META.write_text(json.dumps(new_meta, indent=2))
        return data.get("leaderboardRows") or [], new_meta

    async def info(self, body: dict[str, Any], weight: int) -> Any:
        response = await self._request(
            "POST",
            config.INFO_URL,
            weight=weight,
            json_body=body,
            headers={"Content-Type": "application/json"},
        )
        return response.json()

    async def portfolio(self, address: str) -> Any:
        return await self.info({"type": "portfolio", "user": address}, config.WEIGHT_PORTFOLIO)

    async def clearinghouse_state(self, address: str) -> Any:
        return await self.info(
            {"type": "clearinghouseState", "user": address},
            config.WEIGHT_CLEARINGHOUSE,
        )

    async def meta_and_asset_ctxs(self) -> Any:
        return await self.info({"type": "metaAndAssetCtxs"}, config.WEIGHT_META_AND_CTXS)

    async def all_mids(self) -> Any:
        return await self.info({"type": "allMids"}, config.WEIGHT_ALL_MIDS)


def window_from_row(row: dict[str, Any], name: str) -> dict[str, str]:
    raw = row.get("windowPerformances") or []
    try:
        return dict(raw).get(name) or {}
    except Exception:
        return {}


def window_pnl_from_portfolio(portfolio: Any, name: str = "perpMonth") -> Optional[float]:
    if not isinstance(portfolio, list):
        return None
    for item in portfolio:
        if not (isinstance(item, list) and len(item) == 2 and item[0] == name):
            continue
        hist = (item[1] or {}).get("pnlHistory") or []
        if not hist:
            return 0.0
        try:
            return float(hist[-1][1])
        except (TypeError, ValueError, IndexError):
            return None
    return None


def btc_mark_from_ctxs(payload: Any) -> Optional[float]:
    if not (isinstance(payload, list) and len(payload) >= 2):
        return None
    meta, ctxs = payload[0], payload[1]
    universe = (meta or {}).get("universe") or []
    for i, asset in enumerate(universe):
        if asset.get("name") == "BTC":
            try:
                return float(ctxs[i]["markPx"])
            except (KeyError, TypeError, ValueError, IndexError):
                return None
    return None


def extract_btc_position(state: dict[str, Any]) -> dict[str, Any]:
    """Pull the BTC perp position and account equity from clearinghouseState."""
    equity = None
    try:
        equity = float((state.get("marginSummary") or {}).get("accountValue"))
    except (TypeError, ValueError):
        equity = None
    found = {
        "equity": equity,
        "btc_szi": 0.0,
        "btc_notional": 0.0,
        "entry": None,
        "leverage_type": None,
        "leverage": None,
        "unrealized_pnl": None,
        "liquidation_px": None,
    }
    for item in state.get("assetPositions") or []:
        pos = (item or {}).get("position") or {}
        if pos.get("coin") != "BTC":
            continue
        try:
            szi = float(pos.get("szi") or 0)
        except (TypeError, ValueError):
            szi = 0.0
        try:
            notional = abs(float(pos.get("positionValue") or 0))
        except (TypeError, ValueError):
            notional = 0.0
        lev = pos.get("leverage") or {}
        found.update(
            {
                "btc_szi": szi,
                "btc_notional": notional,
                "entry": _opt_float(pos.get("entryPx")),
                "leverage_type": lev.get("type") if isinstance(lev, dict) else None,
                "leverage": _opt_float(lev.get("value") if isinstance(lev, dict) else lev),
                "unrealized_pnl": _opt_float(pos.get("unrealizedPnl")),
                "liquidation_px": _opt_float(pos.get("liquidationPx")),
            }
        )
        break
    return found


def _opt_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
