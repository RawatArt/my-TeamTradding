# M3 Plan

## Goal

Implement a stateless deterministic Risk Engine and position-sizing domain layer. M3 consumes
typed proposals, M2 snapshots, and explicit account-risk context. It produces auditable decisions
but has no MT5, execution, AI, strategy, trading-loop, or backtesting capability.

## Baseline and boundaries

- Start from accepted tag `m2-v0.3.0` on `feat/m3-risk-engine`.
- Preserve all M0-M2 safety boundaries and reports.
- Keep broker timestamp-offset handling unchanged; M3 does not infer or correct broker time.
- Require caller-supplied evaluation time and account baselines so repeated inputs are identical.

## Components

- `ProposalValidator`: traceability, prices, BUY/SELL geometry, tick alignment, broker stop
  distance, minimum RR, and trading capability.
- `AccountRiskEvaluator`: account fingerprint, context time, drawdown, daily loss, risk state, and
  account-wide position limits.
- `PositionSizer`: Decimal-only monetary risk and broker-volume calculation.
- `RiskEngine`: fixed-order orchestration and immutable final `RiskDecision` assembly.

## Account context

- Require a non-secret SHA-256 account fingerprint derived from the snapshot's account ID and
  server only for deterministic matching. Raw inputs are never logged.
- Require `context_as_of`, UTC trading-day start, cash-flow-adjusted peak equity, adjusted
  day-start equity, and account-wide open-position count.
- The caller owns cash-flow adjustments and persistence; M3 creates no ledger.

## Sizing semantics

The accepted M1 metadata has `trade_tick_value` but no independently validated
`trade_tick_value_loss`. M3 therefore uses the existing tick value as the monetary loss for one
tick and one lot, rejects invalid metadata, and records `trade_contract_size` without multiplying
it again. No pip or currency-conversion assumptions are made.

Volume is rounded down on the broker grid anchored at `volume_min`. Minimum volume is rejected if
its estimated stop loss exceeds allowed monetary risk. Every approved result revalidates min/max,
step alignment, and estimated risk.

## Verification

- Unit-test proposal validation, account state, daily loss, drawdown, sizing, final decisions,
  Decimal serialization, and deterministic repeatability.
- Add safety tests proving confidence isolation, lack of MT5/execution APIs, and continued LIVE
  rejection.
- Run full pytest, Ruff, strict mypy, and all M0-M3 safety tests.
- Update README and `M3_REPORT.md`, then commit and tag only after verification.
