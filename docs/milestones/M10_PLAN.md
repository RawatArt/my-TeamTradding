# M10 Implementation Plan

Date: 2026-09-14
Status: Approved and implemented

## Scope

Build a deterministic, offline/forward-SHADOW qualification and graduation-evidence layer above
the accepted M9 audit records and M8 outcome contracts. M10 measures evidence sufficiency,
operational reliability, safety-boundary adherence, provider cost, and descriptive R-based
outcomes. Its strongest positive result is `ELIGIBLE_FOR_DEMO_REVIEW`; it cannot enable DEMO,
LIVE, execution, scheduling, provider fallback, optimization, or strategy/prompt changes.

## Architecture

The data flow is:

M9 append-only claims/decisions + compatible M8 outcomes + M5 telemetry/pricing + exact
acceptance/dependency references -> OPEN evidence revisions -> SEALED evidence -> deterministic
graduation gates -> EVALUATED evidence + immutable historical evaluation -> separately reassessed
current eligibility.

`QualificationService` coordinates sealing and evaluation. `ShadowGraduationEvaluator` is a pure
gate evaluator. The M10 collector only reads a predeclared time range from the accepted M9
repository and never starts or polls `ContinuousShadowRuntime`.

## Evidence lifecycle and identity

- `OPEN` evidence may receive append-only revisions.
- `SEALED` evidence has a canonical content digest and cannot accept decisions, outcomes,
  pricing replacements, acceptance changes, dependency changes, or backfill.
- `EVALUATED` is terminal and references exactly one graduation evaluation.
- Additional observations require a new dataset/run; an existing sealed dataset is never reopened.
- Evidence is linked to an exact generation manifest, M9 decision identity, M6 record, M3 Risk
  decision, M8 proposal/outcome linkage, partition, pricing, and timestamp acceptance.

## Validity versus graduation

Current evidence validity is one of `VALID`, `EXPIRED`, `INVALIDATED`, or `CONTAMINATED`.
Historical graduation is separately `ELIGIBLE_FOR_DEMO_REVIEW` or `NOT_ELIGIBLE`. Expiry or a
later material dependency change never rewrites a past performance result. Current eligibility
requires both currently valid evidence and a passing historical graduation evaluation.

Exact role assignments bind provider/model, agent and prompt versions/digests, adapter and SDK
versions, capability/runtime identities, input/output schemas, and the applicable M5/M6/M9
acceptance chain. Incompatible or expired dependencies fail closed.

## Metrics and gates

Gates are explicit, versioned, and canonically ordered. They cover:

- completed decisions, AI-invoked cycles, candidates, Risk-approved SHADOW intents, and resolved
  outcomes;
- runtime/provider failure rates, duplicates, abandoned cycles, trace/schema failures, source
  revisions, and current timestamp-semantic acceptance;
- zero-tolerance Risk bypass, confidence/risk coupling, order or broker mutation, DEMO/LIVE use,
  provider fallback, and automatic strategy/prompt mutation;
- settled observed cost, conservative uncertain reserved cost, and separately projected 30-day
  cost;
- out-of-sample partition identity, ambiguity/unresolved rates, and reviewed R-based performance
  rules.

Win rate is descriptive by default. A reviewed policy may add a justified win-rate gate, but the
schema rejects any policy in which win rate is the only trading-performance rule. Domain logic
contains no universal profitability threshold.

## Cost semantics

Observed cost reports settled provider cost, conservative `UNCERTAIN` reservations, their exact
assessed sum, observed decision count, observed evidence duration, and dispatched attempts.
Projected cost is a separate contract labeled with its policy/version, expected 30-day decision
count, and projection basis. Projection is never represented as spend or billing. Missing or
ambiguous pricing makes cost evidence unavailable and fails the related gates.

## Partition and contamination policy

The context/warm-up range and evaluation range remain distinct. Only decisions and outcomes in
the predeclared evaluation interval enter evidence. `RESEARCH` and `VALIDATION` partitions may be
measured but cannot graduate; only `OUT_OF_SAMPLE` can pass the partition gate. Evidence used to
drive a material system change becomes `CONTAMINATED` for current eligibility.

## Persistence and safety

In-memory and SQLite repositories preserve immutable revision chains, runs, validity assessments,
evaluations, and current-status assessments. Stored data is sanitized: no credentials, raw
provider response, prompt body, raw MT5 object, broker mutation, or execution request is added.
Qualification is disabled by default and mutually exclusive with M9 observation and M8 replay.
DEMO and LIVE remain prohibited.

## Files

Create M10 qualification schemas, evidence/acceptance/metric/evaluator/service/source modules,
append-only storage, example configuration, unit/integration/safety tests, and this plan/report.
Update configuration, startup policy, exports, README, environment example, and package version.

## Acceptance criteria

- Full pytest, Ruff, strict mypy, and all M0-M10 safety tests pass.
- OPEN -> SEALED -> EVALUATED is append-only and sealed content cannot be backfilled or replaced.
- Evidence expiry/invalidation/contamination remains distinct from performance failure.
- Observed and projected costs cannot be confused; uncertain charges remain conservative.
- Win rate alone cannot grant eligibility.
- Dependency/acceptance changes invalidate current eligibility.
- Research, validation, and contaminated evidence cannot qualify for current review.
- Two provider-free qualification runs produce equal models/digests, canonical gate ordering,
  and byte-identical canonical records.
- Production M10 code contains no broker execution, second runtime, provider dispatch, Risk
  calculation, optimization, or mode-enablement capability.
