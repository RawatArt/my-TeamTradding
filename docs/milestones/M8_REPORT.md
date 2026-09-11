# M8 Completion Report

Date: 2026-09-11
Status: Fully accepted

## Baseline preservation

- Started from accepted annotated tag `m7-v0.8.0` on `feat/m8-historical-replay`.
- Preserved all M0-M7 architecture, tests, and safety boundaries.
- Did not change the accepted M0-M7 completion reports.
- Advanced the package version to `0.9.0` and preserved M8 with annotated tag `m8-v0.9.0`
  only after complete verification.

## Implemented

- Added immutable historical dataset, partition, candle, as-of observation, replay
  configuration, replay-frame, frozen-decision, outcome, metric, and segmentation contracts.
- Added deterministic in-memory and local UTF-8 JSON historical sources with canonical dataset
  sealing and digest verification. M8 performs no download or network access.
- Added separate capability-limited decision and outcome views. Decision code cannot request
  future candles, and outcome access requires an immutable frozen proposal.
- Added an explicit replay clock/schedule, deterministic replay/cycle/snapshot/frame identities,
  and content-addressed artifact references.
- Reconstructed the accepted M2 `MarketSnapshot` from complete historical as-of observations and
  calculated features through the unchanged M7 `MarketFeatureEngine`.
- Preserved M2 stale-but-valid behavior. M8 does not reinterpret validity, freshness, or broker
  source timestamps.
- Added strict dataset identity, ordering, duplicate-key, UTC, partition, finite-horizon, and
  cross-artifact consistency validation.
- Added theoretical BUY/SELL TP/SL level-touch evaluation with explicit
  `AMBIGUOUS_INTRABAR` and `UNRESOLVED_HORIZON` states.
- Added Decimal-only R outcomes, MFE/MAE, holding duration, deterministic research summaries,
  and descriptive segmentation using only frozen pre-outcome facts.
- Added in-memory and SQLite append-only replay repositories. Conflicting record identities fail
  closed and repository reads require explicit replay and partition identity.
- Added an M8 startup policy that permits inert SHADOW and explicit offline BACKTEST only. Replay
  enablement requires BACKTEST; DEMO, LIVE, and live-enablement flags remain prohibited.

## Strict post-decision boundary

For a decision cutoff `T`, a decision candle is eligible only when:

```text
candle.open_time + canonical_timeframe_duration <= T
```

An outcome candle is eligible only when:

```text
candle.open_time >= T
candle.close_time > T
candle.close_time <= partition.evaluation_end
```

This makes the candle ending at `T` part of the decision information set only. It can never
resolve TP/SL or contribute future MFE/MAE. All close times use the single accepted canonical
M15/H1/H4 timeframe-duration helper; M8 does not infer a broker timezone offset.

## Outcome termination and metric semantics

- MFE/MAE terminates on the TP/SL resolution candle for an unambiguous result.
- MFE/MAE terminates on the dual-touch candle for `AMBIGUOUS_INTRABAR`.
- MFE/MAE terminates on the last finite-horizon candle for `UNRESOLVED_HORIZON`.
- Candles following any terminal event are not included in excursions, duration, bar counts, or
  the outcome candle digest.
- `sequence_max_drawdown_r` is the peak-to-trough drawdown of the ordered resolved-R research
  sequence. It is not account drawdown, cash/equity drawdown, or a portfolio simulation.
- Undefined or unbounded research metrics use typed states; M8 emits neither NaN nor infinity.

## Partition and historical-risk integrity

- Each partition retains `context_start`, `evaluation_start`, `evaluation_end`, and explicit
  RESEARCH/VALIDATION/OUT_OF_SAMPLE identity.
- Warm-up candles may establish indicator state but cannot create replay frames, outcomes, or
  performance observations before `evaluation_start`.
- Finite outcome views cannot cross `evaluation_end`, and different evaluation ranges cannot
  overlap inside one dataset definition.
- A persisted M3 `RiskDecision` is accepted only when its cycle, snapshot, proposal identity,
  frozen proposal digest, symbol, supported schema, and exact decision digest match. Historical
  mismatches fail closed without inference or repair.

## Canonical reproducibility

- Canonical output is compact, key-sorted UTF-8 JSON.
- Decimal values use normalized decimal strings, timestamps use fixed UTC serialization, timed
  horizons use exact integer microseconds, and enums use stable string values.
- Dataset digests cover schema and metadata, partition ranges, ordered candle identity/time/OHLC
  and optional source fields, and complete accepted as-of observations.
- Replay configuration and every derived artifact carry deterministic digests and version
  provenance.
- Two complete pipeline runs produced equal models, equal SHA-256 digests, and byte-identical
  canonical output.

## Files created

Production and documentation:

- `docs/milestones/M8_PLAN.md`
- `docs/milestones/M8_REPORT.md`
- `src/ai_trading_team/evaluation/__init__.py`
- `src/ai_trading_team/evaluation/metrics.py`
- `src/ai_trading_team/evaluation/outcomes.py`
- `src/ai_trading_team/evaluation/segmentation.py`
- `src/ai_trading_team/replay/__init__.py`
- `src/ai_trading_team/replay/clock.py`
- `src/ai_trading_team/replay/engine.py`
- `src/ai_trading_team/replay/errors.py`
- `src/ai_trading_team/replay/identifiers.py`
- `src/ai_trading_team/replay/protocols.py`
- `src/ai_trading_team/replay/serialization.py`
- `src/ai_trading_team/replay/snapshot.py`
- `src/ai_trading_team/replay/source.py`
- `src/ai_trading_team/schemas/evaluation.py`
- `src/ai_trading_team/schemas/historical.py`
- `src/ai_trading_team/schemas/replay.py`
- `src/ai_trading_team/storage/replay.py`

Tests:

- `tests/fakes/replay.py`
- `tests/integration/test_historical_replay_pipeline.py`
- `tests/safety/test_m8_replay_boundaries.py`
- `tests/safety/test_m8_startup_policy.py`
- `tests/unit/test_historical_replay.py`
- `tests/unit/test_historical_source.py`
- `tests/unit/test_replay_clock.py`
- `tests/unit/test_replay_metrics.py`
- `tests/unit/test_replay_serialization.py`
- `tests/unit/test_replay_settings.py`
- `tests/unit/test_replay_storage.py`
- `tests/unit/test_trade_outcomes.py`

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
- `src/ai_trading_team/storage/__init__.py`

## Final verification

Canonical environment: Windows x86-64, CPython 3.12.13.

- Full default suite: **469 passed, 6 skipped**. The skips remain explicitly gated MT5 demo,
  real-provider smoke, and real-provider SHADOW tests; M8 acceptance is provider- and
  terminal-independent.
- Ruff: **all checks passed**.
- Strict mypy: **no issues found in 199 source files**.
- All M0-M8 safety tests: **87 passed**.
- Decision-candle exclusion selection: **2 passed**.
- MFE/MAE resolution, ambiguity, and finite-horizon termination selection: **3 passed**.
- Partition context/evaluation isolation selection: **3 passed**.
- Persisted RiskDecision linkage selection: **6 passed**.
- Provider-free full replay pipeline acceptance: **1 passed**; the test executes the pipeline
  twice and requires equal models, digests, and bytes.
- Production M8 source scan found no MetaTrader5, order/symbol/position mutation, provider SDK,
  Risk Engine invocation, scheduler, or optimization capability.

## Safety confirmation

- No order submission, MT5 mutation, DEMO trading, LIVE trading, or execution path exists.
- M8 neither imports nor invokes a provider, LLM runtime, Risk Engine, or M6 decision-cycle
  orchestrator.
- M8 implements no strategy, trade scoring, threshold search, prompt/model tournament,
  automatic optimization, or strategy mutation.
- Historical account state is never synthesized. Exact M2 reconstruction fails when required
  as-of observations are absent.
- Outcome results are theoretical research observations and cannot become executable requests.
- The tracked broker/FX source timestamp incompatibility remains unresolved and unchanged; M8
  never guesses, shifts, or repairs a source timezone.

## Known limitations

- M8 assumes a frozen proposal is active at its stated entry at the decision cutoff. It does not
  simulate order activation, broker fills, gaps, spread, commission, slippage, swaps, or latency.
- OHLC candles cannot reveal intrabar event order, so a candle touching both TP and SL remains
  explicitly ambiguous.
- M8 does not reconstruct portfolio capital, overlapping exposure, cash flow, or historical
  `AccountRiskContext`. Its R summaries are trade-outcome research metrics only.
- Complete historical M2 reconstruction requires source-provided accepted symbol, tick, account,
  position, and candle metadata. Missing fields are not invented.
- Local file ingestion currently accepts one validated JSON dataset contract; data-vendor import
  and migration adapters are deferred.
- Replay is explicitly invoked and finite. M8 adds no scheduler, continuous backtest runner, or
  automated research-selection workflow.

## Recommended next step

Stop at M8. Begin M9 planning only after explicit approval. No deployment, runtime trading,
execution, automatic optimization, or timestamp correction should be inferred from M8 acceptance.
