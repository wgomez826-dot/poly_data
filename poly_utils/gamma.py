"""Thin wrapper around the Polymarket Gamma markets endpoint.

Mirrors the JS reference in ``examples/fetch_active_market.js`` but returns
Python dicts with ``clobTokenIds`` and ``outcomes`` already parsed, plus
convenience ``yes_token_id`` / ``no_token_id`` fields for binary markets.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterable

import requests

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"


def _parse_json_field(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value if value is not None else default


def _normalize_market(market: dict) -> dict:
    clob_token_ids = _parse_json_field(market.get("clobTokenIds"), [])
    outcomes = _parse_json_field(market.get("outcomes"), [])

    market["clobTokenIds"] = clob_token_ids
    market["outcomes"] = outcomes
    market["yes_token_id"] = clob_token_ids[0] if len(clob_token_ids) > 0 else None
    market["no_token_id"] = clob_token_ids[1] if len(clob_token_ids) > 1 else None
    return market


def fetch_markets(
    *,
    active: bool | None = True,
    closed: bool | None = False,
    limit: int = 100,
    offset: int = 0,
    timeout: float = 30.0,
    max_retries: int = 3,
    **extra_params: Any,
) -> list[dict]:
    """Fetch markets from the Gamma API with parsed JSON fields.

    Any extra keyword arguments are forwarded as query params (e.g.
    ``order='volume'``, ``ascending=False``, ``clob_token_ids=...``).
    """
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if active is not None:
        params["active"] = str(active).lower()
    if closed is not None:
        params["closed"] = str(closed).lower()
    for key, value in extra_params.items():
        if value is None:
            continue
        params[key] = value if not isinstance(value, bool) else str(value).lower()

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = requests.get(GAMMA_MARKETS_URL, params=params, timeout=timeout)
            if response.status_code == 429:
                time.sleep(2 ** attempt * 2)
                continue
            if response.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return [_normalize_market(m) for m in response.json()]
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(2 ** attempt)

    raise RuntimeError(
        f"Gamma API request failed after {max_retries} attempts"
    ) from last_error


def fetch_active_markets(limit: int = 100, **kwargs: Any) -> list[dict]:
    """Convenience wrapper: active, non-closed markets only."""
    return fetch_markets(active=True, closed=False, limit=limit, **kwargs)


def fetch_market_by_token(token_id: str, **kwargs: Any) -> dict | None:
    """Look up the single market containing ``token_id`` in its CLOB pair."""
    markets = fetch_markets(
        active=None, closed=None, limit=1, clob_token_ids=token_id, **kwargs
    )
    return markets[0] if markets else None


def iter_token_ids(markets: Iterable[dict]) -> Iterable[tuple[str, str]]:
    """Yield ``(yes_token_id, no_token_id)`` pairs for binary markets."""
    for m in markets:
        yes, no = m.get("yes_token_id"), m.get("no_token_id")
        if yes and no:
            yield yes, no
