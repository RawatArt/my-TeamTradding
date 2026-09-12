# M9 Completion Report

Date: 2026-09-12
Status: Fully accepted (provider-neutral continuous SHADOW core); real-provider eligibility tracked separately

## Baseline preservation

- Started from the accepted annotated tag `m8-v0.9.0` on
  `feat/m9-continuous-shadow`.
- Preserved the M1 read-only MT5 adapter, M2 snapshot contract, M3 Risk Engine authority,
  M4/M5 agent boundaries, M6 one-shot orchestration graph, M7 feature calculations, and M8
  outcome rules.
- Did not modify the accepted M0-M8 completion reports.
- Advanced the package version to `0.10.0`.
- Preserved the verified M9 baseline with annotated tag `m9-v0.10.0`.

## Implemented

- Added a bounded, explicitly polled `ContinuousShadowRuntime` for one configured symbol and
  completed M15 candles. It has no internal scheduler or automatic startup.
- Added stable decision-candle identity and deterministic `decision_key` and `cycle_id`.
  The runtime obtains `snapshot_id` exclusively from the actual accepted M2 snapshot and
  persists `decision_key -> cycle_id -> actual_snapshot_id`.
- Added exact claimed-candle validation using canonical candle content. Snapshot trace, symbol,
  M15 identity, close boundary, candle fields, and unique accepted snapshot identity must match
  before processing.
- Added durable claim states: `DISCOVERED`, `CLAIMED`, `PROCESSING`, `COMPLETED`,
  `FAILED`, `MISSED`, and `ABANDONED`. Duplicate discovery is idempotent only for identical
  candle content; restart recovery abandons unfinished claims and never redispatches them.
- Added single-flight/backpressure behavior. At most one timely candidate is processed per poll;
  excess or late candles receive explicit `MISSED` records.
- Added `AgentMarketView` v2 with a strictly allowlisted `AgentFeatureView` projection of the
  existing M7 output. The exact projection has canonical bytes and a content-sensitive SHA-256
  digest.
- Added feature-aware v2 prompt artifacts for all nine typed roles without adding a second agent
  graph, strategy logic, or prompt self-modification.
- Added deterministic pre-dispatch account-context construction. It reads current account and
  account-wide positions, requires one exact ACTIVE risk baseline, constructs M3
  `AccountRiskContext`, and applies the existing M6 structural preflight before any provider
  call.
- Added explicit risk-baseline lifecycle states `ACTIVE`, `SUPERSEDED`, and `INVALIDATED`.
  Replacement is explicit and auditable; zero or multiple compatible ACTIVE records fail closed.
- Added symbol timestamp acceptance records. An exact symbol/account/adapter/M15-H1-H4 acceptance
  is required at startup; no broker timezone offset is inferred or rewritten.
- Added hardened continuous-provider eligibility records binding the exact M5 live-smoke,
  M6 full-cycle SHADOW, and M9 feature-input evidence plus provider/model, adapter/SDK,
  capability/runtime, prompt, input/output schema, and feature-projection digests.
- Separated pre-dispatch `PROVIDER_CONFIGURATION_INELIGIBLE` policy failures from post-dispatch
  `PROVIDER_RUNTIME_FAILURE` failures. Configuration ineligibility produces `POLICY_HOLD`
  with zero agent/provider calls.
- Preserved valid-but-stale M2 snapshots and applied the M9 policy decision separately:
  stale inputs create an auditable `POLICY_HOLD` without changing M2 semantics.
- Added sanitized in-memory and SQLite persistence for claims, decision records, baseline
  lifecycle, and pending outcomes. SQLite state is rolled back in memory when a durable
  transition fails.
- Added separate M8 outcome attachment. Only a compatible accepted outcome may terminate a
  pending shadow intent; outcome tracking cannot mutate the frozen decision.

## Identity and audit boundaries

- The decision-candle digest contains schema identity, symbol, timeframe, UTC candle open,
  canonical Decimal OHLC values, tick/real volume, and broker spread points in fixed order.
  Retrieval time is intentionally excluded because discovery and M2 composition are separate
  reads.
- `snapshot_id` is opaque, comes from the returned M2 snapshot, and is never derived from the
  decision candle.
- The `AgentFeatureView` digest covers projection schema/version, trace IDs, symbol/timeframe,
  values, statuses, units, history requirements and availability, source time ranges, warnings,
  candle/configuration/definition provenance, Decimal policy, and engine versions.
- Persisted records contain typed sanitized views, digests, evidence references, telemetry, and
  decisions. They exclude credentials, raw MT5 objects, raw provider responses, and full prompt
  bodies.

## Provider acceptance status

| Layer | Provider-neutral/fake acceptance | Real-provider acceptance |
|---|---:|---:|
| M5 adapter contract | Passed for OpenAI, Anthropic, and Gemini adapters | Live smoke remains provider/model-specific |
| M6 full SHADOW cycle | Passed with fake provider | Must be explicitly recorded per accepted provider/model |
| M9 feature-input continuous cycle | Passed with fake provider across three candles | No real-provider M9 record was configured |

Missing real-provider evidence does not invalidate the provider-neutral M9 core. It makes that
provider/model/role ineligible, producing a pre-dispatch policy HOLD with zero API calls.

## Files created

Configuration and documentation:

- `config/continuous_shadow_acceptance.example.toml`
- `config/symbol_timestamp_acceptance.example.toml`
- `docs/milestones/M9_PLAN.md`
- `docs/milestones/M9_REPORT.md`

Observation, schemas, and persistence:

- `src/ai_trading_team/observation/__init__.py`
- `src/ai_trading_team/observation/candles.py`
- `src/ai_trading_team/observation/eligibility.py`
- `src/ai_trading_team/observation/errors.py`
- `src/ai_trading_team/observation/identifiers.py`
- `src/ai_trading_team/observation/outcomes.py`
- `src/ai_trading_team/observation/protocols.py`
- `src/ai_trading_team/observation/risk_context.py`
- `src/ai_trading_team/observation/runtime.py`
- `src/ai_trading_team/schemas/observation.py`
- `src/ai_trading_team/storage/observation.py`

Prompt artifacts:

- Nine role-specific `*_v2.md` prompt artifacts under
  `src/ai_trading_team/prompts/artifacts/`

Tests:

- `tests/integration/test_m9_fake_continuous_shadow.py`
- `tests/safety/test_m9_continuous_shadow_boundaries.py`
- `tests/unit/test_m9_agent_feature_view.py`
- `tests/unit/test_m9_candle_discovery.py`
- `tests/unit/test_m9_observation_storage.py`
- `tests/unit/test_m9_outcome_tracking.py`
- `tests/unit/test_m9_provider_eligibility.py`
- `tests/unit/test_m9_risk_context.py`

## Files changed

- `.env.example`
- `.gitignore`
- `README.md`
- `pyproject.toml`
- `src/ai_trading_team/__init__.py`
- `src/ai_trading_team/config/__init__.py`
- `src/ai_trading_team/config/settings.py`
- `src/ai_trading_team/config/startup.py`
- `src/ai_trading_team/main.py`
- `src/ai_trading_team/orchestration/shadow.py`
- `src/ai_trading_team/prompts/artifacts/manifest.toml`
- `src/ai_trading_team/replay/serialization.py`
- `src/ai_trading_team/schemas/__init__.py`
- `src/ai_trading_team/schemas/agents.py`
- `src/ai_trading_team/schemas/enums.py`
- `src/ai_trading_team/storage/__init__.py`
- `tests/safety/test_m7_feature_boundaries.py`

## Final verification

Canonical environment: Windows x86-64, CPython 3.12.13.

- Full default suite: **505 passed, 6 skipped**.
- Ruff: **all checks passed**.
- Strict mypy: **no issues found in 218 source files**.
- All M0-M9 safety tests: **93 passed**.
- Explicit M9 unit/integration/safety acceptance selection: **36 passed**.
- Fake-provider continuous SHADOW acceptance processed three sequential candles exactly once.
  The expected six-stage M6 graph produced 18 unique logical invocations.
- Repeating the scripted three-candle run produced equal models and byte-identical canonical
  records.
- Actual M2 snapshot binding was verified as different from the requested opaque candidate and
  persisted exactly once.
- AgentFeatureView digest reproducibility and content sensitivity passed.
- Provider acceptance-chain mutation across M5, M6, M9, adapter/SDK, capability/runtime,
  prompt/schema, and feature allowlist dependencies failed closed.
- Zero, multiple, superseded, and invalidated risk-baseline cases behaved deterministically;
  zero/multiple compatible ACTIVE baselines failed closed.
- Provider/configuration ineligibility, invalid account context, and stale snapshot policy
  produced zero provider calls.
- Duplicate polling, restart abandonment, source-candle revision, backpressure, and unique
  snapshot protection passed.
- Production safety scans found no order submission, symbol selection, order/position mutation,
  second Risk Engine, duplicate feature calculations, duplicate M8 outcome algorithm, provider
  fallback, strategy mutation, or timezone-offset correction in M9 modules.

The six default skips are the two explicit MT5 demo tests, three provider-specific live smoke
tests, and the provider-specific M6 SHADOW test. They remain opt-in and do not affect the
provider-neutral M9 acceptance.

A local Windows permission issue affects the legacy pytest cache/temp locations. Verification was
run with workspace-local `--basetemp` and `cache_dir`; it completed successfully. This is a
non-blocking local tooling issue, not an application failure.

## Safety confirmation

- M9 is SHADOW-only. DEMO and LIVE are rejected by startup policy.
- Application startup validates configuration and exits; it does not start the runtime.
- No MT5 execution, order API, symbol mutation, or position mutation exists.
- The existing deterministic M3 Risk Engine remains the sole final risk authority.
- Agent confidence remains descriptive and cannot affect position sizing.
- No scheduler, provider fallback, second agent graph, strategy mutation, prompt
  self-modification, or automatic optimization exists.
- The tracked broker/FX timestamp-semantic incompatibility remains unresolved and fails closed
  unless exact symbol evidence is explicitly accepted. No timezone offset is guessed.

## Known limitations

- The runtime is explicitly polled and single-symbol/M15; it has no internal scheduler.
- Real-provider continuous use remains ineligible until exact non-expired M5, M6, and M9
  acceptance evidence exists for every required role and dependency digest.
- Risk baselines are caller-attested. M9 has no cash-flow ledger and never infers deposits or
  withdrawals.
- The M1/M2 MT5 source is synchronous and depends on a supported Windows terminal environment.
- Outcome evaluation remains the existing M8 offline theoretical OHLC process; M9 only attaches
  compatible results and does not simulate fills, cash P&L, or portfolio equity.
- M9 does not execute trades and creates no broker-facing request.

## Recommended next step

Stop at M9. Do not begin M10 until explicitly approved. A later milestone must retain fail-closed
timestamp eligibility, real-provider acceptance-chain validation, exactly-once identity, and the
deterministic M3 risk boundary before any broader runtime capability is considered.
