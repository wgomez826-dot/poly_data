# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

Dependency management uses [UV](https://docs.astral.sh/uv/):

```bash
uv sync                  # install runtime deps
uv sync --extra dev      # + jupyter/notebook/ipykernel
```

Run the full pipeline (markets → goldsky → process):

```bash
uv run python update_all.py
```

Run an individual stage (each is idempotent and resumable):

```bash
uv run python -c "from update_utils.update_markets import update_markets; update_markets()"
uv run python -c "from update_utils.update_goldsky  import update_goldsky;  update_goldsky()"
uv run python -m update_utils.process_live   # has __main__ guard
```

Backfill a large time gap in `goldsky/orderFilled.csv` with multiple workers:

```bash
uv run python parallel_sync.py --workers 5
uv run python parallel_sync.py --workers 2 --end-ts 1767000000   # bounded test
```

There is no test suite, linter, or build step configured — `pyproject.toml` only declares runtime/dev deps and a hatchling wheel target for `poly_utils` and `update_utils`.

## Pipeline architecture

Three stages orchestrated by `update_all.py`, each writing CSV that the next stage reads:

1. **`update_utils/update_markets.py`** — pages `https://gamma-api.polymarket.com/markets` by `createdAt` ascending and appends rows to `markets.csv`. Resume offset is derived from `count_csv_lines(markets.csv)`; re-running is safe.
2. **`update_utils/update_goldsky.py`** — GraphQL-pages `orderFilledEvents` from the Goldsky orderbook subgraph into `goldsky/orderFilled.csv`. Resume uses a two-level cursor persisted to `goldsky/cursor_state.json`: a `last_timestamp` plus a **sticky** `(sticky_timestamp, last_id)` pair used when a batch is full at a single timestamp — without this, events sharing one second would be silently dropped when a batch hits `BATCH_SIZE`. The cursor file is deleted on clean completion; on restart it falls back to `tail -n 1 goldsky/orderFilled.csv` minus 1 second.
3. **`update_utils/process_live.py`** — reads `goldsky/orderFilled.csv`, joins against markets, emits normalized trades to `processed/trades.csv`. Resume point is the last `(timestamp, transactionHash, maker, taker)` tuple in the output file, recovered via `subprocess.run(['tail', '-n', '1', ...])`.

`parallel_sync.py` is an alternative to stage 2: it splits `(last_synced, now)` into N equal segments, runs `sync_segment` workers in a `ThreadPoolExecutor`, writes per-worker CSVs to `goldsky/parallel_segments/`, then appends them in worker-id order into `orderFilled.csv` and rewrites `cursor_state.json`. It reimplements the same sticky-cursor logic as `update_goldsky.py` and additionally skips sticky follow-up when fewer than `STICKY_THRESHOLD=100` events sit on the boundary timestamp.

## Trade processing model (`get_processed_df`)

`orderFilledEvents` only tell you that two asset IDs swapped. The processor reconstructs semantics by:

1. Melting `markets_df` into long form `(market_id, side ∈ {token1, token2}, asset_id)`.
2. Picking the **non-USDC** side of each fill (asset id `"0"` is USDC) and left-joining it against the long table to recover `market_id` + which outcome token (`token1`/`token2`) was traded.
3. Dividing `makerAmountFilled` / `takerAmountFilled` by `10**6` (on-chain raw units → USDC / token units).
4. Assigning direction: `taker_direction = BUY` when the taker paid USDC else `SELL`; `maker_direction` is the inverse.
5. Computing `price` as `usd_amount / token_amount` (always USDC per outcome token), and `nonusdc_side` as the `token1`/`token2` label of the traded outcome.

Output columns: `timestamp, market_id, maker, taker, nonusdc_side, maker_direction, taker_direction, price, usd_amount, token_amount, transactionHash`.

## Missing-market feedback loop

`process_live` joins against markets but trades frequently reference tokens whose market wasn't in `markets.csv` yet (e.g. created between market syncs). `poly_utils.utils.update_missing_tokens` fetches those markets via Gamma (`?clob_token_ids=<id>`) and appends them to `missing_markets.csv` with the same header as `markets.csv`. `get_markets()` transparently concatenates both files, dedupes by `id`, and sorts by `createdAt`. Always load markets through `get_markets()` — never read `markets.csv` directly or you will miss those late-discovered rows.

## Gamma helper vs. CSV pipeline

`poly_utils/gamma.py` is a thin, retry/backoff-aware wrapper around `https://gamma-api.polymarket.com/markets` that returns dicts with `clobTokenIds` / `outcomes` already JSON-parsed and synthetic `yes_token_id` / `no_token_id` fields. Use it (`fetch_markets`, `fetch_active_markets`, `fetch_market_by_token`) for ad-hoc lookups — the CSV pipeline stages do **not** go through it and have their own inline HTTP + retry logic; keep them decoupled unless consolidating the three implementations intentionally.

## Data API helper

`poly_utils/data_api.py` wraps `https://data-api.polymarket.com` (user-centric reads, no auth) with the same retry/backoff shape as `gamma.py`. Helpers: `fetch_positions(user, ...)`, `fetch_trades(...)`, `fetch_activity(user, ...)`, `fetch_holders(market_condition_id, ...)`, `fetch_value(user, ...)`. List inputs to `market` / `type` are auto-joined into the CSV format the API expects, and booleans are coerced to lowercase strings. The `market` parameter on these endpoints is a **conditionId** (not a token id) — that's the same `condition_id` column written into `markets.csv`. This API is independent from the Gamma + Goldsky pipeline; it's the right tool for "what is wallet X holding right now?" style questions.

## Conventions that bite

- **Token IDs are 76-digit decimal strings.** When reading any CSV that contains `token1`/`token2`/`makerAssetId`/`takerAssetId` with polars, pass `schema_overrides={"token1": pl.Utf8, "token2": pl.Utf8}` (or the equivalent for asset id columns) — autoinference overflows them into floats and corrupts the id.
- **Filter a user's trades by the `maker` column, not `taker`.** Polymarket contracts emit `orderFilledEvents` from the maker's perspective, so even trades the user initiated appear with them as `maker`. Prices in `trades.csv` are likewise from the maker's perspective.
- **Platform wallets** `0xc5d563a36ae78145c45a50134d48a1215220f80a` and `0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e` are exported as `PLATFORM_WALLETS` from `poly_utils` — exclude them when computing user-level metrics.
- **All on-chain amounts must be divided by `10**6`** before they mean USDC / outcome-token units. `process_live` does this once for persisted trades; anything reading `goldsky/orderFilled.csv` directly must do it itself.
- **Asset id `"0"` is USDC.** Every fill has exactly one USDC leg and one outcome-token leg.

## Bootstrapping data

First-time runs download ~2 days of history. The README links a snapshot tarball that should be extracted into the repo root so stages 2 and 3 can resume instead of scraping from timestamp 0.

## Repository layout notes

- `Example 1 Trader Analysis.ipynb`, `Example 2 Backtest.ipynb`, `Isolated.ipynb` — exploratory notebooks demonstrating how to consume `processed/trades.csv`; not part of the pipeline.
- `backtrader_plotting/` — vendored plotting library used by the backtest notebook; treat as third-party.
- `examples/fetch_active_market.{py,js}` — minimal Gamma API usage demos.
