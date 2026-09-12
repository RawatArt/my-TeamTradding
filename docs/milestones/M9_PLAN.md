# M9 Implementation Plan

Date: 2026-09-12
Status: Approved and implemented

## Scope

Build a bounded continuous SHADOW observation runtime that reuses the accepted M1 read-only
adapter, M2 snapshot composer, M7 feature engine, M6 one-shot orchestration graph, M3 Risk Engine,
and M8 outcome contracts. M9 introduces no order, broker mutation, strategy optimization,
timezone correction, or background scheduler.

## Architecture

The explicitly invoked pipeline is:

MT5 read-only observations -> completed M15 discovery -> durable decision claim -> M2 snapshot
-> risk-context preflight -> M7 features -> AgentMarketView v2 -> provider eligibility preflight
-> existing M6 SHADOW cycle -> sanitized research record.

Outcome collection is a separate capability. It attaches a compatible M8 TradeOutcome to a
frozen shadow intent and never changes the decision.

## Identity and snapshot binding

- decision_key hashes symbol, M15 identity, candle open, and canonical close time.
- cycle_id is deterministically derived from decision_key.
- snapshot_id is opaque and allocated for the actual M2 build; it is never derived from candle
  identity.
- The repository persists decision_key -> cycle_id -> actual accepted snapshot_id.
- Before processing, the runtime validates snapshot trace, symbol/timeframe, and the exact
  claimed candle content.
- The candle-content digest excludes retrieval time because discovery and snapshot construction
  are separate reads. It includes schema, symbol, timeframe, UTC open time, canonical Decimal
  OHLC values, volumes, and broker spread points.

## Exactly-once and lifecycle model

Claim states are DISCOVERED, CLAIMED, PROCESSING, COMPLETED, FAILED, MISSED, and ABANDONED.
Duplicate discovery is idempotent only when candle content is identical. Claimed or processing
records found after restart become ABANDONED and are never redispatched. A rerun requires a new
decision identity under a future reviewed recovery protocol.

The runtime exposes start, health, poll_once, and shutdown only. It has no internal thread or
timer. Shutdown stops new polls and lets an already awaited poll reach one persisted terminal
state. An external process crash is handled by the ABANDONED restart rule.

## Feature-enriched agent boundary

AgentMarketView v2 contains AgentFeatureView v1. The projection includes allowlisted M15/H1/H4
feature values, availability, units, required/available history, source range timestamps,
warnings, source candle digests, definition/configuration versions, Decimal policy, and engine
versions. It contains no signal, score, recommendation, account identity, or execution field.

The exact projection is serialized as sorted compact UTF-8 JSON with Pydantic JSON boundary
semantics and hashed with SHA-256. M9 prompts are version 2.0.0 and explicitly instruct roles to
consume deterministic features without recomputing indicators.

## Risk context and baselines

AccountRiskContextProvider reads current account and account-wide positions, derives the accepted
non-secret account fingerprint, and requires exactly one ACTIVE RiskBaselineRecord covering that
account, UTC trading day, and effective time. Baselines carry adjusted day-start equity,
cash-flow-adjusted peak equity, explicit provenance, evidence digest, and lifecycle.

Replacement uses an explicit atomic supersession operation. Zero or multiple compatible active
baselines result in POLICY_HOLD. M9 does not implement a cash-flow ledger or duplicate M3 risk
calculations. The existing M6 structural preflight runs again before any provider dispatch.

## Eligibility

SymbolTimestampAcceptanceRecord binds exact symbol, M15/H1/H4 semantics, safe account reference,
adapter version, validation-policy digest, result identity, and expiry. Missing or ambiguous
acceptance fails closed without timezone adjustment.

ContinuousProviderAcceptanceRecord is role-specific and binds provider/model, adapter and SDK
versions, capability/runtime digests, prompt digest, input/output schema digests, feature
allowlist version/digest, expiry, and exact M5 live-smoke, M6 full-SHADOW, and M9 feature-input
evidence. Any changed or missing dependency makes the provider ineligible before dispatch.
Fake providers require accepted adapter contracts but no fabricated live-smoke record.

## Backpressure and failures

Only one cycle can be in flight and at most one timely unclaimed candle is selected per poll.
Older excess candidates are marked MISSED with explicit BACKPRESSURE metadata. Old decisions
are also marked MISSED instead of being processed hours later.

Typed failures distinguish provider configuration ineligibility from provider/runtime failure,
along with MT5, symbol timestamp, candle, snapshot, feature, baseline, account context, duplicate,
restart, backpressure, storage, and outcome-source failures. Valid stale snapshots produce
POLICY_HOLD; M2 validity/freshness semantics remain unchanged.

## Persistence and observability

In-memory and SQLite repositories retain claim bindings, sanitized decision records, baseline
lifecycle, and outcome tracking. Records contain digests, typed views, agent/M6 audit data,
telemetry, Chief/Risk decisions, and optional shadow intent. They exclude credentials, raw
provider responses, raw broker objects, and full prompt bodies.

Health reports runtime state, last poll/candle/cycle, in-flight and missed counts, eligibility,
and the last typed failure without raw account identity.

## Files

Create observation modules for discovery, identifiers, eligibility, protocols, risk context,
runtime, outcomes, and errors; add M9 schemas and SQLite persistence; add v2 prompt artifacts and
registry entries; update configuration, startup policy, exports, README, version, and examples;
add unit, integration, and safety tests.

## Acceptance

- Full pytest, Ruff, strict mypy, and all M0-M9 safety tests pass.
- The fake-provider runtime processes several candles exactly once with deterministic records.
- Repeated scripted runs produce equal models, digests, and canonical bytes.
- Snapshot identity comes from the accepted M2 result and the exact claimed candle is verified.
- AgentFeatureView digest is stable and content-sensitive.
- M5/M6/M9 acceptance-chain changes fail closed.
- Missing or conflicting baselines HOLD before provider dispatch.
- Restart, duplicate, backpressure, shutdown, and separate M8 outcome attachment are verified.
- Production code contains no broker mutation, execution, strategy optimizer, or timezone guess.
