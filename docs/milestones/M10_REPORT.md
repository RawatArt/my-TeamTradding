# M10 Completion Report

Date: 2026-09-14
Status: Fully accepted (provider-neutral SHADOW qualification core)

## Baseline preservation

- Started from accepted annotated tag `m9-v0.10.0` on
  `feat/m10-shadow-qualification`.
- Preserved the M1 read-only adapter, M2 snapshot semantics, M3 final Risk authority,
  M4-M6 agent/runtime boundaries, M7 feature calculations, M8 outcome algorithms, and M9
  continuous SHADOW runtime.
- Did not modify accepted M0-M9 completion reports.
- Advanced the package version to `0.11.0`.
- Preserved the verified M10 baseline with annotated tag `m10-v0.11.0`.

## Implemented

- Added immutable qualification contracts for exact dependency manifests, predeclared
  partitions, append-only evidence revisions, validity assessments, reviewed graduation
  policies, metrics, gates, evaluations, current status, and advisory performance review.
- Added the strict evidence lifecycle `OPEN -> SEALED -> EVALUATED`. Sealing creates a canonical
  content digest; sealed/evaluated evidence cannot accept decisions, outcomes, pricing changes,
  acceptance changes, dependency changes, or missing-evidence backfill.
- Separated evidence validity (`VALID`, `EXPIRED`, `INVALIDATED`, `CONTAMINATED`) from historical
  graduation (`ELIGIBLE_FOR_DEMO_REVIEW`, `NOT_ELIGIBLE`). Current eligibility requires both.
- Added exact material-generation binding for agent role/provider/model, agent/prompt identity,
  adapter/SDK versions, capability/runtime profiles, input/output schemas, M5/M6/M9 acceptance,
  AgentMarketView/AgentFeatureView, feature/Risk/orchestration/outcome policy, pricing, and symbol
  timestamp semantics.
- Added a read-only bounded M9 evidence collector. It queries only the predeclared evaluation
  interval and never starts or polls the M9 runtime.
- Reused M8 `summarize_performance`; M10 introduces no second outcome or performance algorithm.
- Added deterministic, canonically ordered gates for sample sufficiency, operational reliability,
  zero-tolerance safety events, observed/projected costs, partition purpose, ambiguity/unresolved
  rates, and reviewed R-based evidence.
- Prevented win-rate-only graduation. Win rate remains descriptive unless a versioned policy adds
  both an explicit threshold and justification alongside a substantive non-win-rate rule.
- Added separate observed and projected cost contracts. Observed totals retain settled costs and
  conservative `UNCERTAIN` reservations; projected 30-day cost is explicitly policy-labeled and
  never represented as provider spend or billing.
- Added append-only in-memory and SQLite qualification repositories with atomic final evaluation.
- Added inert M10 settings, example policy/run configuration, and an M10 startup policy that
  prohibits DEMO/LIVE and prevents qualification from running concurrently with M8/M9 tasks.

## Evidence and decision semantics

- Only exact M9 claims and decisions inside the declared evaluation range may enter a dataset.
- M8 outcomes must match partition, cycle, actual snapshot ID, proposal ID, and canonical proposal
  digest; historical linkage is never inferred or repaired.
- `RESEARCH` and `VALIDATION` evidence may be measured but fail the out-of-sample graduation gate.
- Evidence used for a material system change can be marked `CONTAMINATED`; this changes current
  validity without rewriting its historical graduation evaluation.
- Acceptance expiration is not a trading-performance failure. It makes current evidence
  `EXPIRED` and leaves the past gate result unchanged.
- The strongest result is eligibility for human DEMO review. No result activates an application
  mode, submits an order, or creates a broker-facing request.

## Files created

Configuration and documentation:

- `config/qualification_run.example.toml`
- `config/shadow_graduation_policy.example.toml`
- `docs/milestones/M10_PLAN.md`
- `docs/milestones/M10_REPORT.md`

Qualification, schemas, and persistence:

- `src/ai_trading_team/qualification/__init__.py`
- `src/ai_trading_team/qualification/acceptance.py`
- `src/ai_trading_team/qualification/errors.py`
- `src/ai_trading_team/qualification/evaluator.py`
- `src/ai_trading_team/qualification/evidence.py`
- `src/ai_trading_team/qualification/metrics.py`
- `src/ai_trading_team/qualification/protocols.py`
- `src/ai_trading_team/qualification/service.py`
- `src/ai_trading_team/qualification/source.py`
- `src/ai_trading_team/schemas/qualification.py`
- `src/ai_trading_team/storage/qualification.py`

Tests:

- `tests/fakes/qualification.py`
- `tests/integration/test_m10_fake_qualification.py`
- `tests/safety/test_m10_qualification_boundaries.py`
- `tests/unit/test_m10_qualification.py`
- `tests/unit/test_m10_qualification_storage.py`
- `tests/unit/test_m10_settings.py`

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
- `src/ai_trading_team/storage/observation.py`

## Final verification

Canonical environment: Windows x86-64, CPython 3.12.13.

- Full default suite: **529 passed, 6 skipped**.
- Ruff: **all checks passed**.
- Strict mypy: **no issues found in 235 source files**.
- All M0-M10 safety tests: **99 passed**.
- Explicit M10 unit/integration/safety selection: **24 passed**.
- Provider-free qualification acceptance produced a Risk-approved SHADOW intent, exact linked M8
  outcome, valid cost evidence, passing canonical gates, and
  `ELIGIBLE_FOR_DEMO_REVIEW` without any execution capability.
- Repeated qualification runs produced equal models, equal content/evaluation digests, identical
  gate ordering, and byte-identical canonical output.
- OPEN, SEALED, and EVALUATED transitions and SQLite round trips passed; duplicate runs and
  terminal evidence mutations failed closed.
- Expired, invalidated, and contaminated evidence remained distinct from graduation performance;
  dependency and role-assignment mutations invalidated current eligibility.
- Missing pricing made observed/projected cost evidence unavailable and failed cost gates.
- Win-rate-only policy construction failed schema validation.
- RESEARCH and VALIDATION partitions failed the out-of-sample gate.
- Default startup completed in SHADOW and started no runtime. DEMO and LIVE startup were rejected.
- Production scans found no MT5 mutation, order/position mutation, provider dispatch, second M9
  runtime, duplicate M8 outcome algorithm, strategy/prompt mutation, optimization, or mode
  enablement in M10 modules.

The six default skips remain the two explicit MT5 demo tests, three provider-specific live smoke
tests, and one provider-specific M6 SHADOW test. They are intentionally opt-in and do not affect
provider-neutral M10 acceptance.

Workspace-local pytest temporary/cache paths were used because of the previously documented
Windows permission issue in legacy pytest locations. This is a non-blocking tooling issue.

## Safety confirmation

- M10 never starts, schedules, or duplicates `ContinuousShadowRuntime`.
- No broker execution, DEMO enablement, LIVE enablement, order API, or MT5 mutation exists.
- M3 remains the sole Risk authority; M10 only verifies and measures persisted Risk linkage.
- Agent confidence is measured only for safety-boundary violations and never enters sizing.
- No provider fallback, mandatory real-provider call, model tournament, prompt optimization,
  threshold search, automatic strategy mutation, or self-modification exists.
- No fabricated historical account state, broker timezone offset, fill, cash P&L, or portfolio
  equity behavior is introduced.
- Graduation means human review eligibility only and cannot mutate configuration or application
  mode.

## Known limitations

- Qualification policies, material dependency manifests, acceptance records, pricing, and
  contamination declarations are caller-reviewed inputs; M10 validates and seals them but does
  not discover vendor facts automatically.
- Forward evidence collection remains explicitly invoked. M10 has no scheduler and does not
  decide how long a qualification run should remain open.
- Observed provider cost is only as complete as accepted M5 telemetry and caller-supplied pricing.
  `UNCERTAIN` reservations remain conservatively assessed rather than guessed.
- The 30-day projection is a simple versioned cost-per-completed-decision projection, not billing
  or a market-activity forecast.
- M8 outcomes remain theoretical OHLC level-touch research records, not broker fills or account
  equity simulation.
- Real-provider current eligibility still requires the exact current M5/M6/M9 acceptance chain;
  provider-neutral fake qualification does not confer real-provider acceptance.
- The tracked broker/FX timestamp-semantic issue remains fail-closed and unchanged. M10 neither
  guesses nor rewrites a timezone offset.

## Recommended next step

Stop at M10. Do not begin M11 until explicitly approved. Any future DEMO milestone must treat
`ELIGIBLE_FOR_DEMO_REVIEW` as evidence for human review only and add its own reviewed execution,
idempotency, broker reconciliation, restart recovery, and fail-safe acceptance boundaries.
