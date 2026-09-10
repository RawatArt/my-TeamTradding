# M3 Completion Report

Date: 2026-09-10
Status: Fully accepted

## Baseline preservation

- Started from accepted annotated tag `m2-v0.3.0`.
- Isolated M3 changes on `feat/m3-risk-engine`.
- Preserved the M1 read-only adapter and M2 snapshot composition behavior.
- Did not change the accepted M0, M1, or M2 completion reports.
- Advanced the project package version to `0.4.0` and preserved M3 with annotated tag
  `m3-v0.4.0` only after verification.

## Implemented

- Added stateless `RiskEngine` orchestration with explicit caller-supplied evaluation time.
- Added separate deterministic proposal validation, account/portfolio guards, and position
  sizing components.
- Added immutable, strict Pydantic contracts for account risk context, account metrics, typed
  reasons, position-sizing results, and final risk decisions.
- Bound proposals and account context to the snapshot's `cycle_id` and `snapshot_id`.
- Added a stable non-secret account fingerprint and rejected account-context/snapshot mismatches
  without logging raw account IDs or server values.
- Required timezone-aware UTC `context_as_of` and trading-day timestamps; future-dated or
  snapshot-predating context is rejected without inferring broker time.
- Used caller-supplied `cash_flow_adjusted_peak_equity` and adjusted day-start equity. M3 remains
  stateless and does not implement a cash-flow ledger.
- Added BUY/SELL geometry, positive price, tick alignment, mandatory stop, take-profit,
  broker-stop-distance, minimum risk/reward, symbol trading-mode, and account trading-capability
  checks.
- Added daily-loss, cash-flow-adjusted drawdown, maximum-drawdown halt, and account-wide maximum
  concurrent-position checks.
- Added deterministic `NORMAL`, `CAUTION`, `SAFE_MODE`, and `HALTED` transitions.
- Added exact Decimal-only stop-risk sizing with broker minimum/maximum/step metadata.
- Rounded volume down on the broker grid anchored at `volume_min`, rejected unsafe minimum
  volume, and revalidated all final volume/risk invariants.
- Kept AI confidence outside all Risk Engine input and sizing contracts.
- Added an M3 startup policy that continues to prohibit LIVE mode and live enablement flags.

## Position-sizing contract

M3 calculates:

```text
allowed_risk = equity * (risk_percent / 100)
ticks_to_stop = abs(entry - stop_loss) / trade_tick_size
monetary_loss_per_lot = ticks_to_stop * trade_tick_value
raw_volume = allowed_risk / monetary_loss_per_lot
```

The accepted M1 metadata contains `trade_tick_value`, but no separately validated
`trade_tick_value_loss`. M3 uses the existing field once as monetary loss per tick per lot. It
validates and records contract size but does not multiply by it, preventing double counting. No
pip convention, currency conversion, or undocumented broker assumption was introduced.

## Risk reason taxonomy

Typed reasons cover trace/account/symbol mismatch, invalid temporal context, missing or invalid
prices, invalid BUY/SELL geometry, tick alignment and broker stop rules, minimum RR, symbol and
account trading capability, non-positive equity, position limits, daily loss, maximum drawdown,
invalid broker risk metadata, unsafe minimum volume, and final sizing-invariant failure.

Decision precedence is deterministic: an account `HALTED` state produces `HALTED`; otherwise any
reason produces `REJECTED`; only a reason-free result with approved sizing is `APPROVED`.

## Files created

- `docs/milestones/M3_PLAN.md`
- `docs/milestones/M3_REPORT.md`
- `src/ai_trading_team/risk/account.py`
- `src/ai_trading_team/risk/engine.py`
- `src/ai_trading_team/risk/proposal.py`
- `src/ai_trading_team/risk/reasons.py`
- `src/ai_trading_team/risk/sizing.py`
- `src/ai_trading_team/schemas/risk.py`
- `tests/fakes/risk.py`
- `tests/safety/test_m3_risk_boundaries.py`
- `tests/safety/test_m3_startup_policy.py`
- `tests/unit/test_account_risk.py`
- `tests/unit/test_position_sizing.py`
- `tests/unit/test_proposal_validation.py`
- `tests/unit/test_risk_engine.py`
- `tests/unit/test_risk_schemas.py`

## Files changed

- `README.md`
- `pyproject.toml`
- `src/ai_trading_team/__init__.py`
- `src/ai_trading_team/config/__init__.py`
- `src/ai_trading_team/config/startup.py`
- `src/ai_trading_team/main.py`
- `src/ai_trading_team/risk/__init__.py`
- `src/ai_trading_team/schemas/__init__.py`
- `src/ai_trading_team/schemas/common.py`
- `src/ai_trading_team/schemas/decisions.py`
- `src/ai_trading_team/schemas/enums.py`
- `tests/unit/test_schemas.py`

## Verification

Canonical environment: Windows x86-64, CPython 3.12.13.

- Full default suite: **180 passed, 2 skipped**. The skips are the explicitly gated M1/M2
  demo-terminal integrations; M3 is terminal-independent.
- Ruff: all checks passed.
- Strict mypy: no issues found in 75 source files.
- All M0-M3 safety tests passed.
- Repeated evaluation with identical proposal, snapshot, context, configuration, and explicit
  timestamp produced equal models and byte-identical JSON.
- Safety scans found no MT5 vendor dependency, order/position mutation, AI/LLM integration,
  trading loop, or backtesting implementation in the M3 risk package.

## Safety confirmation

- No order submission, order request, symbol selection, or position mutation was introduced.
- No MetaTrader5 vendor import exists in the risk package.
- No AI agent, LLM, OpenAI, confidence-based sizing, or strategy behavior exists.
- No trading loop or backtesting implementation exists.
- LIVE remains prohibited by milestone startup policy.
- The tracked broker/FX source timestamp incompatibility remains unchanged. M3 neither guesses
  nor rewrites broker source times; a future runtime must reject unresolved symbols.

## Known limitations

- Account baselines and account-wide position counts are caller-owned; M3 has no persistence or
  cash-flow ledger.
- Account-context age has no independent maximum setting. It must be at least as recent as the
  completed snapshot and no later than the explicit evaluation timestamp.
- Broker `trade_tick_value` is the only accepted M1 tick valuation. M3 cannot distinguish
  profit-side and loss-side values or infer cross-currency conversion.
- M3 consumes M2 validity but intentionally makes no freshness-based tradeability decision.
- Risk decisions are not orders and cannot be executed.

## Recommended next step

Stop at M3. Begin M4 planning only after explicit approval; do not add AI agents, orchestration,
execution, trading loops, or backtesting as part of this milestone.
