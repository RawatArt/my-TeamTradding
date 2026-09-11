# M5 Implementation Plan

Date: 2026-09-11
Status: Approved and implemented

## Scope

Build a provider-neutral, single-agent LLM runtime foundation above the accepted M4 role
contracts. M5 proves one typed context can pass through a verified prompt, requested runtime
profile, validated capability profile, isolated provider adapter, strict structured-output
validation, trusted output-envelope construction, telemetry, and deterministic budget controls.

M5 does not schedule multiple agents and does not call MT5, the Risk Engine, execution,
backtesting, or any trading loop. LIVE remains prohibited.

## Architecture

```text
typed M4 context
  -> immutable PromptRegistry artifact
  -> requested RuntimeProfile
  -> validated ModelCapabilityProfile
  -> conservative budget reservation
  -> one selected provider adapter
  -> semantic-only ModelGeneratedAgentBody
  -> strict role-schema validation
  -> trusted AgentOutput or AgentFailureRecord
```

- `prompts/` owns versioned UTF-8/LF artifacts, manifest metadata, SHA-256 integrity checks, and
  input/output schema compatibility references.
- `runtime/` owns schema mapping, compatibility validation, routing, bounded attempts, normalized
  failures, telemetry, and budget preflight.
- `runtime/providers/` contains OpenAI, Anthropic, and Gemini adapters. Vendor SDK imports occur
  only inside the matching provider package and SDK retries are disabled.
- `storage/ai_budget.py` provides a SQLite reservation ledger with atomic duplicate and budget
  checks. An in-memory implementation supports deterministic tests.
- M4 agent contracts, M3 risk contracts, and M1/M2 data boundaries remain unchanged.

## Trusted versus model-generated data

The model body may contain only descriptive confidence, evidence, warnings, invalidations, and
the role-specific payload. It cannot emit status, trace identifiers, runtime/provider settings,
budget policy, executable volume, or risk percentage. Trusted runtime code derives `SUCCESS` or
`DEGRADED` only after JSON parsing, schema validation, compatibility checks, and envelope
construction succeed.

## Runtime and capability profiles

`RuntimeProfile` records requested provider/model, per-request and total timeouts, output bound,
reasoning request, and policy/profile references. Its referenced `RetryPolicy` owns
`max_attempts` (one through three total provider calls) and explicit timeout, transient, and
rate-limit eligibility. `ModelCapabilityProfile` separately records validated structured-output/JSON Schema
support, reasoning support, context/output limits, available usage metrics, token-estimation
methods, adapter contract acceptance, and provider-specific live-smoke acceptance.

Every combination is checked before dispatch. There is no automatic provider fallback. A real
provider/model is runtime-ineligible until its own live smoke is recorded as accepted; fake
contract acceptance remains sufficient for provider-neutral core verification.

## Prompt registry

Nine minimal role prompts correspond to the nine accepted M4 contracts. The registry verifies
the exact content digest, role, semantic version, path containment, UTF-8 encoding, LF endings,
and canonical input/body schema digests. Prompts instruct roles to treat supplied context as data
and cannot be modified through model output.

## Structured output and failures

Each invocation dispatches one canonical JSON Schema for `ModelGeneratedAgentBody[RolePayload]`.
Responses receive one JSON parse without prose extraction or semantic repair. Unknown enums,
missing fields, extra fields such as `status`, schema drift, and invalid role payloads produce a
sanitized `AgentFailureRecord` plus a typed `RuntimeFailureCategory`.

Failure categories distinguish invalid request/prompt/schema/capability, budget and duplicate
rejection, provider availability/authentication/permission/rate-limit/transient/timeout/refusal,
invalid model output, and unknown provider failures. Existing M4 failure policy chooses the safe
disposition.

## Budget and token model

Token quantities include provenance: `PROVIDER_REPORTED`, `PROVIDER_TOKENIZER`,
`CONSERVATIVE_ESTIMATE`, or `UNAVAILABLE`. Default real adapters expose an explicitly
upper-biased UTF-8 byte estimate (twice the byte count plus a fixed envelope allowance), never an
exact token claim. Unavailable preflight counts fail closed when budget checks require them.

Pricing is caller-owned, versioned, Decimal-based, and time-bounded; no live vendor prices are
embedded. Preflight reserves full uncached estimated input cost plus the configured maximum
output cost. Per-call, daily, monthly, per-cycle/day call counts, and input/output limits are
checked before dispatch.

Reservation states are `RESERVED`, `DISPATCHED`, `SETTLED`, `RELEASED`, and `UNCERTAIN`.
Reservations are released only before dispatch. Timeouts and other post-dispatch failures with
unknown billing retain the reservation as `UNCERTAIN`. `invocation_id` is unique, so a duplicate
cannot dispatch twice.

## Provider strategy

All three adapters are implemented in M5 and must pass the same injected fake-transport contract
suite. Optional SDK versions are pinned and verified on Python 3.12. Real smoke tests are
provider-specific, minimal-token, explicitly gated, and never required by CI. Credentials use
`SecretStr`, stay inside provider adapters, and are excluded from prompts, outputs, snapshots,
and logs.

## Tests

- Prompt manifest, version, path, digest, and role/schema compatibility.
- Semantic-body schema, status exclusion, enum/extra-field rejection, Decimal preservation.
- Runtime/capability compatibility before dispatch and live-smoke eligibility.
- Hard three-call attempt limit, retryable/non-retryable behavior, and timeouts.
- Reservation transitions, duplicate suppression, conservative limits, and SQLite persistence.
- Normalized usage/cost availability and deterministic trace metadata.
- Common fake contract suite for OpenAI, Anthropic, and Gemini adapters.
- Fake-provider end-to-end typed invocation.
- Opt-in real provider smoke tests with explicit credential/model/flag gates.
- Safety scans for SDK isolation and absence of MT5, risk, execution, orchestration runtime, LIVE,
  and confidence-to-sizing paths.

## Acceptance criteria

- Full pytest, Ruff, strict mypy, and all M0-M5 safety tests pass on Python 3.12.
- A fake-provider invocation produces a typed trusted M4 output with complete trace/telemetry.
- Model output cannot set runtime status or runtime policy.
- Capability and budget failures happen before provider dispatch.
- One invocation performs at most three provider calls; duplicate IDs never dispatch twice.
- Post-dispatch billing uncertainty remains reserved as `UNCERTAIN`.
- All three vendor adapters pass one common contract suite; each live provider is reported
  separately and remains ineligible until its own smoke acceptance passes.
- No multi-agent cycle, scheduler, MT5/risk/execution access, trading loop, strategy mutation,
  backtesting, or LIVE capability exists.
