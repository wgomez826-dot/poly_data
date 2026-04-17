"""Python mirror of ``examples/fetch_active_market.js``.

Run from the repo root:

    uv run python examples/fetch_active_market.py
"""
from poly_utils import fetch_active_markets


def main() -> None:
    markets = fetch_active_markets(limit=1)
    if not markets:
        print("No active markets returned.")
        return

    market = markets[0]
    print(market["question"])
    print(market["clobTokenIds"])
    print(f"Yes token: {market['yes_token_id']}")
    print(f"No  token: {market['no_token_id']}")


if __name__ == "__main__":
    main()
