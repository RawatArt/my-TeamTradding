# M2 Plan

## Goal

Build an immutable, cycle-traceable `MarketSnapshot` composition layer from the accepted M1
read-only observations. M2 adds data validation and freshness reporting only; it does not decide
whether data is tradeable and does not add indicators, strategy, risk, execution, AI, or
backtesting behavior.

## Baseline

- Start from accepted tag `m1-v0.2.0` on branch `feat/m2-market-snapshot`.
- Keep `MT5ReadOnlyClient` and the M1 report unchanged.
- Retain the M1 read-only and LIVE-mode safety boundaries.

## Architecture

- Add a narrow `MarketDataSource` protocol structurally satisfied by `MT5ReadOnlyClient`.
- Add a synchronous `MarketDataService` above that protocol.
- Require caller-supplied `cycle_id` and `snapshot_id` values for each build.
- Use only the configured broker symbol and request open positions by that symbol.
- Defensively omit otherwise-valid positions for other symbols without invalidating the snapshot.
- Fetch completed M15, H1, and H4 candles with `include_incomplete=False`.
- Keep one canonical timeframe-duration helper for M15, H1, and H4.
- Convert no raw vendor objects in M2; only typed M1 observations cross the source protocol.

## Validity, freshness, and tradeability

- Invalid structure or inconsistent timestamps fail with a typed M2 error.
- Valid stale data remains composable and is labeled `STALE` in `SnapshotFreshness`.
- Valid fresh data is labeled `FRESH`.
- M2 does not calculate or expose trade eligibility. Freshness-based trading policy belongs to a
  later milestone.
- Keep `STALE_TICK` as a stable error category for a future explicitly strict freshness policy,
  but normal M2 composition does not raise it.

## Defaults

- Completed candle counts: 200 each for M15, H1, and H4.
- Maximum tick age: 120 seconds.
- Maximum account age: 30 seconds.
- Maximum latest completed-candle ages: M15 30 minutes, H1 2 hours, H4 8 hours.
- Slow-snapshot warning threshold: 30 seconds.
- All counts and freshness thresholds are immutable typed configuration.

## Validation

- Normalize aware timestamps to UTC and reject naive timestamps.
- Require all relevant observation retrieval times to fall within the snapshot window.
- Require symbol and timeframe agreement across the aggregate.
- Require candles to be unique, strictly increasing, complete, and no later than snapshot
  completion.
- Do not require gap-free histories or broker-session alignment.
- Require exact configured candle counts and exact Decimal spread agreement.
- Record typed source retrieval timestamps, duration, freshness, and validation warnings.

## Errors

- `MISSING_SYMBOL`
- `STALE_TICK` (reserved for explicit strict freshness callers)
- `INSUFFICIENT_CANDLE_HISTORY`
- `INCONSISTENT_TIMESTAMPS`
- `INVALID_TIMEFRAME_DATA`
- `SNAPSHOT_COMPOSITION_FAILURE`

## Tests and acceptance

- Use fakes for all unit and safety tests; no unit test requires MT5.
- Test immutability, ID validation, UTC normalization, Decimal round trips, freshness without
  invalidation, multi-symbol positions, candle counts, timestamp consistency, and sanitized
  errors.
- Preserve and rerun all M0/M1 tests and safety scans.
- Add an explicitly enabled demo integration test that builds one complete snapshot without any
  terminal or trading mutation.
- Run full pytest, Ruff, and strict mypy on canonical Python 3.12.
- Update README and create `M2_REPORT.md`; commit and tag only after all acceptance checks pass.
