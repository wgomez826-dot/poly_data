"""Thin wrapper around the Polymarket Data API (``data-api.polymarket.com``).

The Data API exposes user-centric reads (positions, trades, on-chain activity,
USD value, market holders) as public REST endpoints with no authentication.
This module mirrors the style of :mod:`poly_utils.gamma`: a single private
``_get`` helper that handles retries / rate limiting, and small typed wrappers
per endpoint that forward extra keyword arguments as query parameters.
"""
from __future__ import annotations

import time
from typing import Any

import requests

DATA_API_BASE_URL = "https://data-api.polymarket.com"

POSITIONS_URL = f"{DATA_API_BASE_URL}/positions"
TRADES_URL = f"{DATA_API_BASE_URL}/trades"
ACTIVITY_URL = f"{DATA_API_BASE_URL}/activity"
HOLDERS_URL = f"{DATA_API_BASE_URL}/holders"
VALUE_URL = f"{DATA_API_BASE_URL}/value"

_BOOL_KEYS = {"redeemable", "mergeable", "takerOnly"}


def _coerce_param(key: str, value: Any) -> Any:
    if isinstance(value, bool) or key in _BOOL_KEYS and isinstance(value, (int, float)):
        return str(bool(value)).lower()
    return value


def _build_params(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {k: v for k, v in base.items() if v is not None}
    for key, value in extra.items():
        if value is None:
            continue
        params[key] = _coerce_param(key, value)
    # Re-coerce any bools that came in via the base dict.
    for key, value in list(params.items()):
        if isinstance(value, bool):
            params[key] = str(value).lower()
    return params


def _get(
    url: str,
    params: dict[str, Any],
    *,
    timeout: float,
    max_retries: int,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            if response.status_code == 429:
                time.sleep(2 ** attempt * 2)
                continue
            if response.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(2 ** attempt)

    raise RuntimeError(
        f"Data API request to {url} failed after {max_retries} attempts"
    ) from last_error


def _join_csv(value: Any) -> Any:
    """Allow list / tuple inputs for CSV-style parameters."""
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(v) for v in value)
    return value


def fetch_positions(
    user: str,
    *,
    market: str | list[str] | None = None,
    size_threshold: float | None = None,
    redeemable: bool | None = None,
    mergeable: bool | None = None,
    title: str | None = None,
    limit: int = 100,
    offset: int = 0,
    sort_by: str | None = None,
    sort_direction: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    **extra_params: Any,
) -> list[dict]:
    """Current open positions for ``user`` (a 0x proxy wallet address)."""
    base = {
        "user": user,
        "market": _join_csv(market),
        "sizeThreshold": size_threshold,
        "redeemable": redeemable,
        "mergeable": mergeable,
        "title": title,
        "limit": limit,
        "offset": offset,
        "sortBy": sort_by,
        "sortDirection": sort_direction,
    }
    return _get(
        POSITIONS_URL,
        _build_params(base, extra_params),
        timeout=timeout,
        max_retries=max_retries,
    )


def fetch_trades(
    *,
    user: str | None = None,
    market: str | list[str] | None = None,
    side: str | None = None,
    taker_only: bool | None = None,
    filter_type: str | None = None,
    filter_amount: float | None = None,
    limit: int = 100,
    offset: int = 0,
    timeout: float = 30.0,
    max_retries: int = 3,
    **extra_params: Any,
) -> list[dict]:
    """Recent trades, newest first. All filters are optional."""
    base = {
        "user": user,
        "market": _join_csv(market),
        "side": side,
        "takerOnly": taker_only,
        "filterType": filter_type,
        "filterAmount": filter_amount,
        "limit": limit,
        "offset": offset,
    }
    return _get(
        TRADES_URL,
        _build_params(base, extra_params),
        timeout=timeout,
        max_retries=max_retries,
    )


def fetch_activity(
    user: str,
    *,
    market: str | list[str] | None = None,
    type: str | list[str] | None = None,
    side: str | None = None,
    start: int | None = None,
    end: int | None = None,
    limit: int = 100,
    offset: int = 0,
    sort_by: str | None = None,
    sort_direction: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    **extra_params: Any,
) -> list[dict]:
    """On-chain activity (TRADE/SPLIT/MERGE/REDEEM/REWARD/CONVERSION) for a user."""
    base = {
        "user": user,
        "market": _join_csv(market),
        "type": _join_csv(type),
        "side": side,
        "start": start,
        "end": end,
        "limit": limit,
        "offset": offset,
        "sortBy": sort_by,
        "sortDirection": sort_direction,
    }
    return _get(
        ACTIVITY_URL,
        _build_params(base, extra_params),
        timeout=timeout,
        max_retries=max_retries,
    )


def fetch_holders(
    market: str,
    *,
    limit: int = 100,
    timeout: float = 30.0,
    max_retries: int = 3,
    **extra_params: Any,
) -> list[dict]:
    """Top holders of each outcome token for a market (by ``conditionId``).

    Returns a list with one entry per outcome token, each containing a
    ``holders`` list ranked by token balance.
    """
    base = {"market": market, "limit": limit}
    return _get(
        HOLDERS_URL,
        _build_params(base, extra_params),
        timeout=timeout,
        max_retries=max_retries,
    )


def fetch_value(
    user: str,
    *,
    market: str | list[str] | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    **extra_params: Any,
) -> list[dict]:
    """Total USD value of a user's open positions, optionally per-market."""
    base = {"user": user, "market": _join_csv(market)}
    return _get(
        VALUE_URL,
        _build_params(base, extra_params),
        timeout=timeout,
        max_retries=max_retries,
    )
