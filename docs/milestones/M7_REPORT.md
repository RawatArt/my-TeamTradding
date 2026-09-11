# M7 Completion Report

Date: 2026-09-11
Status: Fully accepted

## Baseline preservation

- Started from accepted annotated tag `m6-v0.7.0` on `feat/m7-market-features`.
- Preserved all M0-M6 architecture and safety boundaries.
- Did not change the accepted M0-M6 completion reports.
- Advanced the package version to `0.8.0`.
- Preserved the verified result with annotated tag `m7-v0.8.0`.

## Implemented

- Added a deterministic, stateless `MarketFeatureEngine` that transforms one immutable M2
  `MarketSnapshot` into one immutable, cycle- and snapshot-traceable `MarketFeatureSet`.
- Added typed per-timeframe feature groups for latest-candle geometry, EMA20/50/200, RSI14,
  ATR14, ADX14, recent range, confirmed swing high/low, and dependent signed distances.
- Kept feature availability unambiguous: `VALID`, `INSUFFICIENT_HISTORY`, or `UNAVAILABLE`.
  Structural invalidity raises a sanitized typed `FeatureEngineError` and produces no valid
  feature set.
- Added strict validation for trace identity, symbol and timeframe identity, UTC timestamps,
  chronological candle order, candle completion, snapshot cutoffs, positive prices, OHLC
  geometry, and feature-configuration compatibility.
- Preserved stale-but-valid M2 observations and freshness metadata. M7 calculates descriptive
  features only and makes no trading-eligibility decision.
- Added explicit timeframe provenance: source first-candle open, last-candle open, and
  last-candle close timestamps. `generated_at` is deterministically equal to
  `snapshot.snapshot_completed_at`.
- Added canonical source-candle and configuration digests plus canonical feature-set JSON bytes
  for deterministic audit and replay comparisons.
- Added an M7 startup policy that permits SHADOW only and rejects DEMO, LIVE, and live-enablement
  flags.
- Added no runtime dependency and no provider, MT5, risk, execution, strategy, scheduler, or
  backtesting integration.

## Deterministic feature definitions

The engine uses one fixed local Decimal context and never converts price, volume, or indicator
values to binary floats. Price-valued outputs are quantized to broker symbol digits; ratios and
indices use eight decimal places.

Required candle counts are explicit:

| Feature | Required completed candles |
|---|---:|
| Latest-candle geometry | 1 |
| EMA20 / EMA50 / EMA200 | 20 / 50 / 200 |
| RSI14 | 15 |
| ATR14 | 15 |
| ADX14 | 28 |
| Recent range | Configured lookback; default 20 |
| Confirmed swing | `left_window + right_window + 1`; default 5 |

EMA uses an SMA seed followed by the standard recursive update. RSI, ATR, and ADX use Wilder
smoothing. Swing candidates require strict dominance on both sides, so tied extrema are not
confirmed. Dependent distance features inherit the availability and reason of their reference
feature.

## Canonical digest contracts

Canonical bytes are compact, key-sorted UTF-8 JSON. Decimal values use a normalized plain-decimal
string with no exponent or insignificant trailing zeros; zero is serialized as `"0"`. Datetimes
use timezone-aware UTC with six fractional digits and a `Z` suffix.

The source-candle digest includes collection `symbol` and `timeframe`, then every candle in
chronological order with these fields in the canonical object:

- `schema_version`
- `retrieved_at`
- `symbol`
- `timeframe`
- `open_time`
- `open`
- `high`
- `low`
- `close`
- `tick_volume`
- `broker_spread_points`
- `real_volume`

The configuration digest includes the canonicalization version, feature-configuration version,
recent-range lookback, and swing left/right windows. Both digests use SHA-256 and include the
`sha256:` algorithm prefix.

## Typed error categories

- `INVALID_SNAPSHOT`
- `INVALID_CANDLE_ORDER`
- `FUTURE_CANDLE`
- `INCOMPLETE_CANDLE`
- `TIMEFRAME_MISMATCH`
- `SYMBOL_MISMATCH`
- `CONFIGURATION_INCOMPATIBLE`
- `CALCULATION_FAILURE`

Errors expose sanitized category and context only. Structural invalid input never becomes a
numeric feature value.

## Files created

Documentation:

- `docs/milestones/M7_PLAN.md`
- `docs/milestones/M7_REPORT.md`

Feature engine and schemas:

- `src/ai_trading_team/features/__init__.py`
- `src/ai_trading_team/features/definitions.py`
- `src/ai_trading_team/features/engine.py`
- `src/ai_trading_team/features/errors.py`
- `src/ai_trading_team/features/geometry.py`
- `src/ai_trading_team/features/indicators.py`
- `src/ai_trading_team/features/serialization.py`
- `src/ai_trading_team/features/structure.py`
- `src/ai_trading_team/features/validation.py`
- `src/ai_trading_team/schemas/features.py`

Tests:

- `tests/fakes/features.py`
- `tests/integration/test_market_feature_pipeline.py`
- `tests/safety/test_m7_feature_boundaries.py`
- `tests/safety/test_m7_lookahead_boundaries.py`
- `tests/safety/test_m7_startup_policy.py`
- `tests/unit/test_adx.py`
- `tests/unit/test_atr.py`
- `tests/unit/test_candle_geometry.py`
- `tests/unit/test_ema.py`
- `tests/unit/test_feature_schemas.py`
- `tests/unit/test_feature_serialization.py`
- `tests/unit/test_feature_settings.py`
- `tests/unit/test_market_feature_engine.py`
- `tests/unit/test_market_structure.py`
- `tests/unit/test_rsi.py`

## Files changed

- `.env.example`
- `README.md`
- `pyproject.toml`
- `src/ai_trading_team/__init__.py`
- `src/ai_trading_team/config/__init__.py`
- `src/ai_trading_team/config/settings.py`
- `src/ai_trading_team/config/startup.py`
- `src/ai_trading_team/main.py`
- `src/ai_trading_team/schemas/__init__.py`
- `src/ai_trading_team/schemas/enums.py`

## Final verification

Canonical environment: Windows x86-64, CPython 3.12.13.

- Full default suite: **409 passed, 6 skipped**. The skips are the explicitly gated M1/M2 MT5,
  M5 provider, and M6 provider-shadow integrations.
- Ruff: **all checks passed**.
- Strict mypy: **no issues found in 170 source files**.
- All M0-M7 safety tests: **76 passed**.
- Known-value EMA, RSI, ATR, and ADX vectors: **11 passed**.
- M7 look-ahead and prefix-invariance tests: **9 passed**, including EMA, RSI, ATR, and ADX
  prefix checks.
- Determinism and canonical serialization/digest checks: **6 passed** in the focused selection.
- Repeated feature calculation produced equal models and byte-identical canonical JSON.
- SHADOW startup exited successfully and activated no trading components; DEMO and LIVE each
  exited with `StartupPolicyError`.
- Production M7 source scan found no MetaTrader5/provider dependency, order or position mutation,
  Risk Engine access, strategy logic, scheduler, execution, or backtesting implementation.

## Safety confirmation

- No BUY/SELL signal, trade score, proposal, or strategy decision is produced.
- No AI/LLM runtime or provider dependency is used.
- No MT5 adapter or vendor API is accessed.
- No Risk Engine behavior is changed or invoked.
- No scheduler, order execution, position mutation, or backtesting is implemented.
- The tracked broker/FX source timestamp incompatibility remains unchanged. M7 never guesses or
  rewrites broker timezone offsets and invalid timestamps fail closed.
- DEMO and LIVE remain prohibited.

## Known limitations

- M7 calculates the latest feature state for each supported snapshot timeframe; it does not
  create a historical feature matrix or a backtest dataset.
- The configured M2 default of 200 candles is exactly sufficient for EMA200 and provides no
  earlier EMA200 output within that same window.
- Freshness is carried through as descriptive provenance only. Later orchestration policy remains
  responsible for deciding whether stale data is usable.
- Confirmed swings use deterministic local-window structure only; they are not trade signals.
- M7 intentionally implements the approved feature-engine scope. It does not satisfy the broader
  backtesting/quant milestone described in the original master roadmap.

## Recommended next step

Stop at M7. Begin M8 planning only after explicit approval. Do not add strategy selection,
backtesting, performance claims, execution, or live capability as part of this milestone.
