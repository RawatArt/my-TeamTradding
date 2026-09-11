# M6 Implementation Plan

Date: 2026-09-11
Status: Approved and implemented

## Scope

Build a one-shot, auditable multi-agent decision cycle in `SHADOW` mode by composing the accepted
M2 snapshot, M3 deterministic Risk Engine, M4 role graph, and M5 single-agent runtime. M6 does not
add a scheduler, broker execution, order or position mutation, demo/live trading, strategy
mutation, or backtesting.

## Architecture

- Add a `ShadowCycleOrchestrator` above the existing agent runtime and Risk Engine.
- Keep agent invocation behind a narrow orchestrator-owned interface; agents never call one
  another, MT5, Risk, storage, or execution.
- Construct role inputs through an access-controlled factory using the sanitized M4
  `AgentMarketView` and only the upstream outputs allowed for that role.
- Execute the fixed realtime graph: Stage 1 Market Context/Trend/Price Action concurrently,
  Stage 2 Entry, optional Stage 3 Quant roles, bounded Stage 4/5 Skeptic/Chief debate, then the
  existing deterministic Risk Engine as Stage 6.
- Keep Performance Reviewer outside the live decision graph.
- Store an immutable `DecisionCycle` and `ShadowDecisionRecord`. An approved risk result may
  produce only a non-executable `ShadowTradeIntent` labeled `NOT_EXECUTED_SHADOW`.

## Safety preflight

Before any agent/provider dispatch:

- Atomically claim the supplied `cycle_id` and `snapshot_id`.
- Validate snapshot/context cycle and snapshot identity.
- Recompute and compare the safe account fingerprint without persisting raw account or server
  identifiers.
- Require timezone-aware UTC-compatible timestamps, reject future context, and require the
  account context to be no older than snapshot completion.
- Apply M6 stale-snapshot policy as HOLD without changing M2 validity/freshness semantics.
- Do not duplicate M3 loss, drawdown, position-limit, proposal, or sizing calculations.

## Identity and retry model

- Derive logical invocation identity deterministically from `cycle_id`, `snapshot_id`, stage,
  role, and debate round.
- Retain one logical identity across provider retries and number attempts from one through the
  M5 maximum of three.
- Reserve budget independently before every provider attempt.
- Treat a dispatched timeout or uncertain provider outcome conservatively as `UNCERTAIN`.
- Reject duplicate cycle claims and duplicate invocation attempts before redispatch.

## Provider acceptance

Real-provider eligibility requires a current immutable acceptance record bound to:

- provider and model;
- provider-adapter version;
- provider SDK version;
- capability-profile digest;
- compatible runtime-profile digest;
- successful smoke-test timestamp and result identity.

Any incompatible adapter, SDK, capability, or runtime-profile change makes the prior record
ineligible. The fake provider remains independently contract-tested and needs no live smoke.

## Failure policy

- Trace, account, temporal, schema, duplicate, and trusted invariant failures abort the cycle.
- A stale-but-valid snapshot produces policy HOLD before provider dispatch.
- Required-agent timeout, invalid output, unavailable runtime, or missing upstream data produces
  HOLD according to the accepted M4 policy.
- Stage 1 may continue degraded when at least two valid outputs remain after availability or
  timeout failures; invalid output still produces HOLD.
- Selected Quant roles are conditional and their availability failures may continue degraded.
- Chief HOLD is a valid terminal decision and skips Risk.
- Risk rejection or halt is authoritative; only Risk approval can create a shadow intent.

## Crash and audit semantics

- A claim begins as durable `INCOMPLETE` before any provider call.
- A successful terminal record changes the claim to `FINALIZED` atomically.
- A process failure leaves the claim `INCOMPLETE`; there is no implicit resume or redispatch.
- An operator may explicitly mark an incomplete claim `ABANDONED`, but neither incomplete nor
  abandoned identities may be reused. A rerun requires a new cycle identity.
- Persist typed outputs, sanitized failures and telemetry, minimized market view, safe risk
  input, stage records, and deterministic references.
- Never persist raw provider responses, credentials, sensitive broker identifiers, or complete
  prompt bodies when prompt metadata and digest are sufficient.

## Files

Create:

- `config/m6_shadow_provider.example.toml`
- `config/provider_acceptance.example.toml`
- `src/ai_trading_team/schemas/shadow.py`
- `src/ai_trading_team/orchestration/context.py`
- `src/ai_trading_team/orchestration/identifiers.py`
- `src/ai_trading_team/orchestration/preflight.py`
- `src/ai_trading_team/orchestration/runtime.py`
- `src/ai_trading_team/orchestration/shadow.py`
- `src/ai_trading_team/runtime/acceptance.py`
- `src/ai_trading_team/storage/shadow_audit.py`
- M6 fake, unit, integration, and safety tests
- `docs/milestones/M6_REPORT.md`

Change only the necessary configuration, exports, runtime budget/telemetry contracts, provider
adapter metadata, README, package version, and startup policy. Preserve accepted milestone
reports and the M1-M5 behavioral boundaries.

## Testing strategy

- Unit-test trace/account/temporal preflight, deterministic IDs, provider-record invalidation,
  stage order, Stage 1 concurrency, quorum/degraded behavior, optional Quant selection, bounded
  debate, failure dispositions, Risk outcomes, immutable schemas, Decimal round-trips, and
  deterministic serialization.
- Verify attempt-aware budget reservations and duplicate invocation protection.
- Verify in-memory and SQLite duplicate-cycle, incomplete-after-restart, explicit-abandonment,
  and no-reuse behavior.
- Run a full fake-provider cycle through the real M5 router and M3 Risk Engine without MT5.
- Keep a separate explicit opt-in real-provider SHADOW test gated by credentials, configuration,
  and an exact current provider acceptance record.
- Add safety tests for SHADOW-only startup, confidence isolation, non-executable intent, forbidden
  imports/APIs, and preservation of M0-M5 boundaries.

## Acceptance criteria

- A complete one-shot fake-provider cycle produces a deterministic immutable SHADOW record.
- Preflight incompatibility, duplicate cycle, or duplicate invocation cannot dispatch a provider.
- Retry attempts share one logical invocation and have distinct reservation identities.
- Crash/incomplete and abandoned claims remain durable and cannot be silently reused.
- Provider eligibility fails closed when any bound acceptance fact changes.
- Risk remains the final authority and confidence never affects sizing.
- No MT5 access, order/execution API, scheduler, trading loop, strategy mutation, backtest, or
  LIVE/DEMO capability is introduced.
- Full pytest, Ruff, strict mypy, all M0-M6 safety tests, and fake full-cycle acceptance pass.

