"""Demonstrates the data-api.polymarket.com helpers.

Run from the repo root:

    uv run python examples/fetch_user_data.py 0x<proxy_wallet>

If no address is supplied, prints the most recent global trades instead.
"""
from __future__ import annotations

import sys

from poly_utils import fetch_positions, fetch_trades, fetch_value


def main() -> None:
    user = sys.argv[1] if len(sys.argv) > 1 else None

    if user is None:
        trades = fetch_trades(limit=3)
        print(f"Latest {len(trades)} trades on Polymarket:")
        for trade in trades:
            print(
                f"  {trade.get('side'):<4} "
                f"{trade.get('size'):>8.2f} @ ${trade.get('price'):.3f}  "
                f"{trade.get('title')}"
            )
        return

    value = fetch_value(user)
    if value:
        print(f"Total open value for {user}: ${value[0].get('value', 0):.2f}")

    positions = fetch_positions(user, limit=5, sort_by="CURRENT")
    print(f"Top {len(positions)} positions by current value:")
    for pos in positions:
        print(
            f"  {pos.get('outcome'):<5} "
            f"{pos.get('size'):>10.2f} tokens  "
            f"cur=${pos.get('currentValue'):.2f}  "
            f"pnl=${pos.get('cashPnl'):.2f}  "
            f"{pos.get('title')}"
        )


if __name__ == "__main__":
    main()
