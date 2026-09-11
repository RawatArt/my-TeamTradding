# M6 Completion Report

Date: 2026-09-11
Status: Fully accepted (provider-neutral SHADOW core); real-provider acceptance tracked separately

## Baseline preservation

- Started from accepted annotated tag `m5-v0.6.0` on `feat/m6-shadow-runtime`.
- Preserved all M0-M5 architecture and safety boundaries.
- Did not change the accepted M0-M5 completion reports.
- Advanced the package version to `0.7.0` and preserved the verified M6 baseline with annotated
  tag `m6-v0.7.0`.

## Implemented

- Added an explicitly invoked, one-shot `ShadowCycleOrchestrator` for the accepted M4 realtime
  stages; no scheduler or continuous trading loop exists.
- Added deterministic concurrent Stage 1 execution, required Entry analysis, selectable Quant
  participation, bounded Skeptic/Chief debate, and the existing M3 Risk Engine as the sole final
  risk authority.
- Kept Performance Reviewer outside the current-trade graph.
- Added a pre-dispatch snapshot/account-context compatibility check covering trace identity, safe
  account fingerprint, and explicit UTC temporal consistency without duplicating M3 risk rules.
- Added deterministic logical invocation IDs derived from cycle, snapshot, stage, role, and
  debate round.
- Retained one logical invocation identity across retry attempts and added attempt-specific budget
  reservations and telemetry.
- Added hardened provider acceptance records bound to provider/model, adapter and SDK versions,
  capability and runtime digests, and smoke result identity/time.
- Added immutable cycle, stage, invocation-audit, risk-input-audit, shadow-intent, and final-record
  boundary models.
- Added SQLite and in-memory audit repositories with atomic cycle claims, duplicate protection,
  durable incomplete state, explicit abandonment, and no implicit resume or reuse.
- Persisted sanitized typed artifacts and references only; no raw provider response, complete
  prompt body, credential, or sensitive broker identifier is part of the M6 audit contract.
- Added an M6 startup policy that permits only SHADOW and continues to reject LIVE and all live
  enablement flags.

## Files created

Configuration and documentation:

- `config/m6_shadow_provider.example.toml`
- `config/provider_acceptance.example.toml`
- `docs/milestones/M6_PLAN.md`
- `docs/milestones/M6_REPORT.md`

Runtime, orchestration, schemas, and storage:

- `src/ai_trading_team/orchestration/context.py`
- `src/ai_trading_team/orchestration/identifiers.py`
- `src/ai_trading_team/orchestration/preflight.py`
- `src/ai_trading_team/orchestration/runtime.py`
- `src/ai_trading_team/orchestration/shadow.py`
- `src/ai_trading_team/runtime/acceptance.py`
- `src/ai_trading_team/schemas/shadow.py`
- `src/ai_trading_team/storage/shadow_audit.py`

Tests:

- `tests/fakes/shadow.py`
- `tests/integration/test_shadow_cycle_fake_provider.py`
- `tests/integration/test_shadow_cycle_provider.py`
- `tests/safety/test_m6_shadow_boundaries.py`
- `tests/safety/test_m6_startup_policy.py`
- `tests/unit/test_provider_acceptance.py`
- `tests/unit/test_shadow_identifiers.py`
- `tests/unit/test_shadow_orchestrator.py`
- `tests/unit/test_shadow_preflight.py`
- `tests/unit/test_shadow_runtime_settings.py`

## Files changed

- `.env.example`
- `README.md`
- `pyproject.toml`
- `src/ai_trading_team/__init__.py`
- `src/ai_trading_team/config/__init__.py`
- `src/ai_trading_team/config/settings.py`
- `src/ai_trading_team/config/startup.py`
- `src/ai_trading_team/main.py`
- `src/ai_trading_team/orchestration/__init__.py`
- `src/ai_trading_team/orchestration/failures.py`
- `src/ai_trading_team/runtime/__init__.py`
- `src/ai_trading_team/runtime/budget.py`
- `src/ai_trading_team/runtime/protocols.py`
- `src/ai_trading_team/runtime/providers/base.py`
- OpenAI, Anthropic, and Gemini provider adapter modules
- `src/ai_trading_team/runtime/router.py`
- `src/ai_trading_team/schemas/__init__.py`
- `src/ai_trading_team/schemas/enums.py`
- `src/ai_trading_team/schemas/runtime.py`
- `src/ai_trading_team/storage/__init__.py`
- `src/ai_trading_team/storage/ai_budget.py`
- `tests/unit/test_agent_failure_policy.py`
- `tests/unit/test_ai_budget.py`
- `tests/unit/test_runtime_router.py`

The accepted M0-M5 reports were not changed.

## Safety behavior

- Invalid trace/account/context compatibility aborts before the first provider call.
- A stale-but-valid M2 snapshot remains valid data but produces an M6 policy HOLD before agent
  dispatch; M2 semantics are unchanged.
- Required-agent failures follow deterministic HOLD/abort rules; permitted Stage 1 and optional
  Quant availability failures can continue with explicitly degraded context.
- Chief HOLD skips Risk. BUY/SELL proposals always pass through M3 Risk.
- Rejected or halted Risk never creates a shadow intent.
- Approved Risk creates only `NOT_EXECUTED_SHADOW`, using the exact M3-approved volume and proposal
  prices.
- Confidence remains descriptive and cannot enter M3 position sizing.

## Provider acceptance status

Provider-neutral fake acceptance is part of M6 core. Real-provider full-cycle acceptance remains
separate and requires an explicit credential, configuration, and current hardened acceptance
record. No provider fallback exists.

| Provider path | Contract/core result | M6 full-cycle result | Later runtime eligibility |
|---|---:|---:|---:|
| Fake provider | Passed | Passed | Test-only |
| OpenAI | M5 adapter contract passed | Not run: no explicit accepted configuration | Not yet eligible |
| Anthropic | M5 adapter contract passed | Not run: no explicit accepted configuration | Not yet eligible |
| Google Gemini | M5 adapter contract passed | Not run: no explicit accepted configuration | Not yet eligible |

## Final verification

Canonical environment: Windows x86-64, CPython 3.12.13.

- Full default suite: **348 passed, 6 skipped**. The skips are two explicit MT5 demo tests, three
  explicit M5 provider smoke cases, and the explicit real-provider M6 SHADOW case.
- Ruff: **all checks passed**.
- Strict mypy: **no issues found in 145 source files**.
- All M0-M6 safety tests: **57 passed**.
- Fake-provider full SHADOW cycle through the real M5 router and M3 Risk Engine: **1 passed**.
- Duplicate-cycle, duplicate-invocation, retry-attempt identity, incomplete-cycle persistence,
  and abandonment selection: **11 passed**.
- Explicit real-provider SHADOW selection: skipped because no flag and accepted provider/profile
  paths were configured; no external API call occurred.
- Default SHADOW startup: exited successfully and confirmed no trading components active.
- DEMO and LIVE startup: rejected with `StartupPolicyError`.
- Production scan found no order submission, symbol selection, order/position mutation, scheduler,
  trading loop, or backtesting implementation. Agent/orchestration/risk packages contain no MT5
  or execution dependency; provider SDK imports remain isolated in their adapter packages.
- Deterministic repeatability tests produced equal typed records and byte-identical JSON for
  identical explicit inputs and clocks.

## Known limitations

- M6 runs only when explicitly invoked; it has no new-M15-candle scheduler or continuous loop.
- There is no automatic recovery protocol. An incomplete or abandoned cycle cannot be resumed;
  an explicit rerun requires a new cycle identity.
- Provider acceptance facts and pricing/capability profiles remain caller-owned and
  time-sensitive.
- Real-provider SHADOW acceptance is provider/model-specific and does not follow automatically
  from provider-neutral fake acceptance.
- The accepted broker/FX timestamp-semantics compatibility issue remains unchanged. A future
  trading runtime must reject affected symbols unless their timestamp semantics are validated;
  M6 performs no offset guessing or rewriting.
- No MT5 access, order execution, position mutation, demo/live trading, strategy mutation, or
  backtesting behavior exists in M6.

## Recommended next step

Stop at the accepted M6 boundary. Begin M7 planning only after explicit approval.
