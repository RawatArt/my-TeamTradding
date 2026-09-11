# M8 Implementation Plan

Date: 2026-09-11
Status: Approved and implemented

## Scope

Build an offline deterministic historical replay, theoretical price-path outcome evaluation,
and R-based performance foundation. M8 does not implement execution, account/equity simulation,
strategy or prompt optimization, provider replay, scheduling, MT5 connectivity, or timezone
correction.

## Pipeline and information boundary

```text
HistoricalDataset -> ReplayClock -> DecisionDataView -> HistoricalSnapshotBuilder
  -> MarketSnapshot -> existing M7 MarketFeatureEngine -> ReplayFrame
  -> FrozenReplayDecision -> finite OutcomeDataView -> TradeOutcome
  -> deterministic PerformanceSummary -> append-only ReplayRepository
```

Decision code receives a capability with no future-data method. At decision cutoff T, a decision
candle must have `open_time + canonical_timeframe_duration <= T`. Outcome candles must have
`open_time >= T`, `close_time > T`, and a close no later than the partition evaluation end. Thus
the final decision candle can never resolve TP/SL or contribute outcome MFE/MAE.

The outcome capability can be requested only with a valid immutable `FrozenReplayDecision`.

## Historical source and partition model

The source is storage-neutral, requires no MT5 runtime, and initially supports in-memory fixtures
and local UTF-8 JSON files. It never downloads data. Candle OHLC values remain Decimal and source
timestamps remain aware UTC. Optional volume/spread metadata stays optional and is never invented.

Every partition declares context/warm-up start, scored evaluation start, evaluation end, and
`RESEARCH`, `VALIDATION`, or `OUT_OF_SAMPLE` identity. Warm-up observations may establish
indicator state, but cannot create frames, outcomes, or performance records. Outcome horizons stop
at evaluation end. Repository access always requires an explicit partition and never implicitly
merges partitions.

Exact M2 snapshot reproduction additionally requires as-of symbol, tick, account, position, and
complete candle metadata. Missing observations fail with a typed error; candle closes are never
substituted for ticks and historical account state is never fabricated.

## Replay and outcome contracts

`ReplayFrame` stores deterministic replay/frame/cycle/snapshot identity, dataset and partition
identity, decision cutoff, snapshot and M7 feature references/digests, and configuration/version
provenance. It is structurally unable to hold outcome data.

`FrozenReplayDecision` retains the exact proposal and digest. An optional persisted M3
`RiskDecision` must match cycle, snapshot, proposal ID and digest, symbol, supported schema, and
its own digest. Mismatch fails closed without inference or repair.

Outcome evaluation uses only fully post-decision completed candles and a finite maximum-bar or
maximum-elapsed horizon. Core M8 assumes the frozen proposal is active at its entry at T and
reports theoretical level touches without fills, spread, commission, slippage, or gap-price
simulation.

Statuses are `TAKE_PROFIT_REACHED`, `STOP_LOSS_REACHED`, `UNRESOLVED_HORIZON`, and
`AMBIGUOUS_INTRABAR`. A candle touching both levels is ambiguous; event order is never guessed.
MFE/MAE ends at the resolution candle, ambiguity candle, or final horizon candle and excludes all
later observations.

## Metrics and provenance

Deterministic summaries report counts, win rate, cumulative/average/median/expectancy R, profit
factor, `sequence_max_drawdown_r`, holding bars/seconds, and average MFE/MAE R. The sequence
drawdown is an ordered research-outcome statistic, not account drawdown, cash/equity drawdown, or
a portfolio simulation. Undefined and unbounded metric cases have typed states rather than NaN
or infinity.

Descriptive segmentation uses only pre-outcome recorded facts. M8 contains no search, ranking,
feature selection, threshold optimization, or strategy promotion.

Canonical compact key-sorted UTF-8 JSON uses normalized Decimal strings, fixed UTC timestamps,
explicit order, and SHA-256. Dataset, configuration, snapshot, feature, proposal, risk, outcome,
and summary provenance is content-addressed. Identical inputs must yield equal objects, equal
digests, and byte-identical output.

## Persistence and safety

In-memory and SQLite repositories expose append-only typed writes. Conflicting duplicate IDs fail
closed. Persisted replay artifacts contain sanitized references/digests, frozen proposals,
outcomes, metrics, and versions—never credentials, raw provider responses, prompt bodies, raw
broker identifiers, or local source paths.

M8 startup allows inert SHADOW and explicit offline BACKTEST. Replay enablement requires BACKTEST.
DEMO, LIVE, and live flags remain prohibited.

## Acceptance

- Full pytest, Ruff, strict mypy, and M0-M8 safety tests pass.
- Decision candle and future-data exclusion are directly proven.
- MFE/MAE terminal boundaries, finite horizons, and ambiguity pass known paths.
- Context/evaluation/OOS partition isolation is proven.
- Persisted RiskDecision linkage fails closed on every mismatch.
- Snapshot reconstruction passes unchanged M2 validation and M7 replay features equal direct M7
  calculation.
- The complete fixture pipeline repeats with equal models, digests, and canonical bytes.
- No provider, MT5 runtime, execution, scheduler, optimization, account simulation, or timezone
  correction is added.
