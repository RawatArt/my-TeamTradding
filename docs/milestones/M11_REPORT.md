# M11 Completion Report

Date: 2026-09-14
Status: Fully accepted (fake-adapter DEMO execution core); real MT5 DEMO acceptance pending

## Real-DEMO acceptance addendum

The operator-facing addendum is implemented but has not been run against a real broker. It adds:

- finite-TTL, single-use readiness evidence bound to one run, candidate generation, accepted
  account/environment, policy, and ENABLED execution-control event;
- a distinct post-readiness human approval with `submission_limit = 1`;
- exact Decimal-to-float transport evidence including `float.hex()`, `Decimal.from_float`, and
  the separately labeled `Decimal(str(...))` reconstruction;
- a trusted `RealDemoAcceptanceRecord` whose accepted state requires final `CONFIRMED` execution,
  `CONFIRMED` composite reconciliation, one exact position, exact volume/SL/TP, and a
  policy-compliant fill;
- a readiness-only command and reviewed execute-once command documented in
  `docs/acceptance/M11_REAL_DEMO_RUNBOOK.md`.

No real order was submitted while implementing or verifying this addendum.

### Addendum files

- `config/m11_real_demo_acceptance.example.toml`
- `docs/acceptance/M11_REAL_DEMO_RUNBOOK.md`
- `docs/acceptance/M11_REAL_DEMO_ACCEPTANCE_REPORT.md`
- `scripts/m11_real_demo_acceptance.py`
- `src/ai_trading_team/schemas/execution_acceptance.py`
- `src/ai_trading_team/execution/real_demo_acceptance.py`
- `src/ai_trading_team/execution/vendor_boundary.py`
- `src/ai_trading_team/storage/execution_acceptance.py`
- `tests/unit/test_m11_real_demo_acceptance.py`
- `tests/safety/test_m11_real_demo_acceptance_boundaries.py`

### Addendum verification

- Full default suite: **575 passed, 7 skipped**. All MT5/provider integrations, including the
  real-DEMO mutation case, remained explicitly gated.
- Ruff: **all checks passed**.
- Strict mypy: **no issues found in 262 source files**.
- All M0-M11 safety tests: **110 passed**.
- Focused addendum unit/safety acceptance: **18 passed**.
- Readiness-only tests proved zero execution claims, zero `order_check` calls, zero submissions,
  and no candidate or readiness consumption.
- Finite TTL, atomic single-use behavior across SQLite restart, and exact readiness, candidate,
  account/environment, policy, and execution-control generation binding passed.
- Vendor-boundary tests recorded the exact binary float through `Decimal.from_float` separately
  from `Decimal(str(...))` and rejected off-grid or out-of-tolerance normalization.
- A successful broker submission without final `CONFIRMED` composite reconciliation could not
  construct `REAL_DEMO_ACCEPTED`.
- Execute-once remained capped at one possible submission; reuse and ambiguous/crash paths did
  not expose a resend route.
- Default tests made no real terminal or broker call. No readiness or mutation operator command
  was run during addendum verification.

## Baseline preservation

- Started from accepted tag `m10-v0.11.0` on `feat/m11-demo-execution`.
- Preserved M1 read-only access, M2 snapshots, M3 sole Risk authority, M4-M6 agent/runtime
  boundaries, M7 features, M8 outcomes, M9 SHADOW runtime, and M10 qualification semantics.
- Did not modify accepted M0-M10 reports. Package version is `0.12.0`.

## Implemented

- Added an explicitly invoked `DemoExecutionService` for one qualified SHADOW intent and at most
  one initial protected DEMO market-order attempt. It has no scheduler or startup hook.
- Added immutable typed contracts for the accepted DEMO environment, exact human approval and
  revocation, execution policy, capabilities, fresh observations, preflight, sealed intent,
  check, final guard, submission, broker evidence, reconciliation, control, and audit lifecycle.
- Bound human approval to the exact candidate, M9 record, SHADOW intent, proposal, M3
  `RiskDecision`, M10 generation, DEMO environment, account fingerprint, symbol, and policy.
- Persisted distinct `analysis_snapshot_id` and `execution_snapshot_id` with purpose
  `PRE_SEND_REVALIDATION`. The fresh snapshot cannot alter the analysis, agents, Chief decision,
  proposal, or SHADOW record.
- Reconstructed fresh M3 context and invoked the existing M3 Risk Engine. Fresh selected volume
  must exactly equal the immutable SHADOW-approved volume.
- Added deterministic checks for time bounds, tick freshness, spread, drift, symbol execution and
  filling capability, zero account positions, and mandatory initial SL and TP.
- Enforced `CLAIMED -> order_check -> FinalDispatchGuard -> DISPATCHING -> one possible send ->
  normalize -> reconcile`. `order_check` success has no submitted/executed meaning.
- Added `FinalDispatchGuard` immediately before mutation. It rechecks unique claim ownership,
  intent expiry, effective/unrevoked approval, ENABLED control, DEMO account/environment,
  positions, tick, spread/drift, symbol capability, and sealed Risk/qualification linkage.
- Added one narrow `MT5DemoExecutionAdapter`; the only production `order_send` reference is in
  `execution/mt5_demo/backend.py`.
- Added composite reconciliation using account/environment, symbol, side, exact volume, bounded
  dispatch time, broker IDs, resulting position, fill, and exact SL/TP. Comment and magic are
  supporting evidence only.
- Added append-only in-memory/SQLite repositories with unique intent, source SHADOW intent, and
  client trade ID claims. After restart, `DISPATCHING`/`SUBMITTED` becomes reconciliation-only
  `UNKNOWN`; no resend path exists.
- Added an append-only `DISABLED`/`ENABLED`/`PAUSED`/`HALTED` control. HALTED cannot directly
  become ENABLED.
- Added disabled-by-default settings and an inert M11 startup policy. LIVE remains prohibited.

## Original M11 core verification

Canonical environment: Windows x86-64, CPython 3.12.13.

- Full suite: **557 passed, 7 skipped**.
- Ruff: **all checks passed**.
- Strict mypy: **no issues found in 256 source files**.
- M0-M11 safety suite: **107 passed**.
- Fake-adapter end-to-end acceptance: **1 passed**.
- The fake flow produced `CREATED -> CLAIMED -> DISPATCHING -> SUBMITTED -> CONFIRMED` with
  exactly one submission.
- Repeated fake flows produced equal models/digests and byte-identical canonical records;
  Decimal values remained JSON strings.
- Changed account, position, tick age, spread, drift, symbol capability, approval, or control
  state failed the final guard with zero submissions.
- Successful `order_check` plus failed guard produced no `DISPATCHING`, `SUBMITTED`, or
  `CONFIRMED` state.
- A crash after durable `DISPATCHING` recovered to `UNKNOWN`; reconciliation confirmed evidence
  without a second submission.
- Duplicate claims, SQLite recovery, snapshot separation, and altered comment/magic composite
  reconciliation all passed.
- SHADOW and inert DEMO startup exited 0. LIVE startup exited 2 with `StartupPolicyError`.

The seven skips are two MT5 read tests, three provider smokes, one M6 provider SHADOW test, and
the separately gated M11 real-DEMO test.

## Real MT5 DEMO acceptance

Status: **PENDING**.

The real-DEMO marker was explicitly selected and skipped because no reviewed M11 environment and
human-approval artifacts were configured. No real order was submitted. This does not invalidate
the provider-free core, but this environment is not eligible for real-DEMO execution. A real
acceptance must be deliberate, use an accepted DEMO account, and bind the exact current artifacts.

## Files created

- `config/demo_execution_policy.example.toml`
- `config/demo_environment_acceptance.example.toml`
- `config/demo_execution_approval.example.toml`
- `docs/milestones/M11_PLAN.md`
- `docs/milestones/M11_REPORT.md`
- `src/ai_trading_team/execution/{acceptance,errors,identifiers,observation,preflight,protocols,reconciliation,service}.py`
- `src/ai_trading_team/execution/mt5_demo/{__init__,adapter,backend,mappers}.py`
- `src/ai_trading_team/schemas/execution.py`
- `src/ai_trading_team/storage/execution.py`
- `tests/fakes/execution.py`
- `tests/integration/test_m11_fake_demo_execution.py`
- `tests/integration/test_m11_real_demo_execution.py`
- `tests/safety/test_m11_demo_execution_boundaries.py`
- `tests/unit/test_m11_execution.py`
- `tests/unit/test_m11_execution_storage.py`
- `tests/unit/test_m11_settings.py`

## Files changed

- `.env.example`, `README.md`, and `pyproject.toml`
- Package version, configuration/startup, execution/schema/storage exports, common/enums, main
  entry point, and canonical replay serialization.
- The M6 mutation scan now protects M6 agent/runtime/orchestration modules instead of the entire
  repository. M11 separately proves that its sole reviewed mutation reference exists only in the
  DEMO backend.

## Safety confirmation

- LIVE is unconditionally prohibited; no automatic DEMO/LIVE upgrade exists.
- Agents/model runtime cannot access execution; M3 remains sole Risk authority; confidence is
  absent from sizing and execution inputs.
- No pending orders, pyramiding, martingale, averaging down, close/modify API, SL/TP modification,
  `symbol_select`, provider fallback, strategy mutation, scheduler, trading loop, or blind resend
  exists.
- Raw MT5 objects and credentials do not cross the adapter or enter persisted audit records.
- The broker/FX timestamp issue remains fail-closed; M11 requires exact timestamp acceptance and
  never guesses an offset.

## Known limitations

- Real MT5 DEMO submission/reconciliation is not accepted in this environment.
- M11 supports one initial protected entry only and has no position-management lifecycle.
- MT5 requires floats at the final vendor-request boundary; internal price/volume/risk contracts
  retain Decimal semantics.
- Acceptance, approval, qualification, and policy artifacts are externally reviewed inputs.
- Startup remains inert and never invokes the execution service.

## Recommended next step

Stop at M11. Do not broaden execution scope or begin another milestone without explicit approval.
Real-DEMO acceptance may be attempted only through a separately reviewed operator procedure.
