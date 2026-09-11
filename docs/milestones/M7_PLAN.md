# M7 Implementation Plan

Date: 2026-09-11
Status: Approved and implemented

## Scope

Add a deterministic Market Feature Engine that consumes only the completed candles already held
by an accepted M2 `MarketSnapshot` and produces an immutable, cycle-traceable
`MarketFeatureSet`. M7 does not implement strategies, signals, scores, AI, risk changes, MT5
access, scheduling, execution, backtesting, or timezone correction.

The legacy master specification describes a broader M7 backtesting definition of done. This
approved milestone is deliberately narrower and does not claim that broader work is complete.

## Architecture

```text
MarketSnapshot
  -> defensive structural/completion validation
  -> independent M15/H1/H4 Decimal calculations
  -> availability and provenance composition
  -> immutable MarketFeatureSet
```

The public API is `MarketFeatureEngine(settings).calculate(snapshot)`. It has no data-source,
clock, agent, provider, Risk Engine, or execution dependency.

## Feature contract

`MarketFeatureSet` carries schema/engine/feature-set versions, cycle and snapshot IDs, symbol,
primary timeframe, deterministic generation time, preserved M2 validity/freshness, fixed M15/H1/H4
feature collections, warnings, and complete provenance.

Each timeframe records:

- source candle count;
- first and last candle open timestamps;
- last candle close timestamp;
- evaluation candle open timestamp;
- source-candle digest;
- input validity and aggregate availability;
- EMA20/50/200 and dependent signed distances;
- RSI14, ATR14, and ADX14;
- latest candle range/body/wicks/body-range ratio;
- latest confirmed swing high/low and dependent signed distances;
- recent range high/low and dependent signed distances.

Structural invalidity raises a sanitized typed error and produces no `MarketFeatureSet`.
Per-feature availability is limited to `VALID`, `INSUFFICIENT_HISTORY`, and `UNAVAILABLE`.

## Required completed-candle counts

| Feature | Required candles |
|---|---:|
| Latest candle geometry | 1 |
| EMA20 | 20 |
| EMA50 | 50 |
| EMA200 | 200 |
| RSI14 | 15 |
| ATR14 | 15 |
| ADX14 | 28 |
| Recent range | configured lookback; default 20 |
| Confirmed swing | `left_bars + right_bars + 1`; default 5 |

Every distance feature inherits the exact availability, required count, available count, and
reason of its EMA, swing, or range reference. Missing values are never replaced with zero.

## Mathematical definitions

- EMA is seeded with the arithmetic mean of the first N closes and then uses
  `alpha = 2 / (N + 1)` and `EMA = alpha * close + (1 - alpha) * prior_EMA`.
- RSI14 uses 14 close changes, arithmetic seed averages, and Wilder smoothing. Positive movement
  with zero loss maps to 100; a completely flat window maps to 50.
- True range is the maximum of high-low, absolute high-previous-close, and absolute
  low-previous-close. No pre-window close is guessed. ATR14 averages the first 14 true ranges and
  then uses Wilder smoothing.
- Directional movement uses strict positive dominance of up/down moves. DI and DX use Wilder
  smoothed TR/DM sums. ADX14 is the mean of the first 14 DX values and then Wilder-smoothed.
  Zero denominators produce factual zero strength.
- Candle geometry uses exact OHLC subtraction. A zero-range candle has an unavailable ratio.
- A swing high/low is strictly greater/lower than all configured left and right neighbors. Ties
  are not swings, and a pivot is exposed only after its complete right confirmation window.
- Recent range is max(high)/min(low) over the latest configured completed-candle window.
- All distances are signed broker price units: `latest_close - reference`.

## Canonical provenance and precision

The source-candle digest hashes a canonical object containing collection-level symbol/timeframe
identity and chronological candle records. Every record includes, in a fixed schema:
`schema_version`, `retrieved_at`, `symbol`, `timeframe`, `open_time`, `open`, `high`, `low`,
`close`, `tick_volume`, `broker_spread_points`, and `real_volume`.

Decimals are serialized without exponent, insignificant trailing zeros, or signed zero.
Timestamps are normalized to UTC and rendered with six fractional digits plus `Z`. JSON keys are
sorted, separators are compact, text is UTF-8, and record order remains oldest to newest.

The configuration digest uses the same canonicalization and includes canonicalization version,
configuration version, recent-range lookback, and both swing windows. Provenance also records
source digests, per-definition versions, engine/feature-set versions, Decimal precision, rounding
mode, and the completed-candles-only invariant.

All arithmetic uses a local precision of 50 and `ROUND_HALF_EVEN`. Price outputs are quantized at
the broker digit scale; indices and ratios use eight decimal places. Intermediates are not
repeatedly rounded. `generated_at` is exactly `snapshot.snapshot_completed_at`.

## Look-ahead protection

- Revalidate the entire snapshot boundary and each candle collection.
- Reject wrong symbol/timeframe, duplicate or decreasing opens, future opens, and candles whose
  close lies after snapshot completion.
- Never fetch, resample, interpolate, or reconstruct candles.
- Calculate M15, H1, and H4 independently using the central timeframe-duration helper.
- Exclude unconfirmed swing candidates lacking the full right window.
- Require prefix invariance for EMA, RSI, ATR, and ADX: a value calculated at historical prefix N
  must equal the value at index N when a longer suffix exists but is excluded.

## Agent boundary

M7 does not modify `AgentMarketView`, M5 prompt/schema digests, or M6 orchestration. A future
reviewed integration must introduce a versioned allowlisted projection, update affected prompt
compatibility records, and preserve the M4 information-access matrix.

## Testing and acceptance

- Hand-verifiable known-value vectors for EMA, RSI, ATR, and ADX.
- Required-history, unavailable, geometry, swing, tie, range, and dependent-distance tests.
- Exact digest construction and mutation sensitivity for every candle/configuration field.
- Ordering, future-candle, incomplete-candle, and prefix-invariance safety tests.
- M15/H1/H4 separation, UTC preservation, stale-valid preservation, Decimal JSON round trips,
  ambient Decimal-context isolation, equal models, and byte-identical canonical JSON.
- Source scans proving no signal/score fields and no LLM, provider, MT5 adapter, Risk Engine,
  execution, scheduler, or backtest dependency.
- Full pytest, Ruff, strict mypy, and M0-M7 safety suites must pass before commit/tag.

