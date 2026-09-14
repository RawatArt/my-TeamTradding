# M11 Implementation Plan

Date: 2026-09-14
Status: Approved and implemented

## Goal

Add the first narrowly bounded, explicitly invoked DEMO execution path. M11 may submit at most
one protected market order for one already qualified, Risk-approved SHADOW intent. LIVE remains
unconditionally prohibited. M11 adds no scheduler, strategy, provider fallback, position
management, pending orders, or automatic mode transition.

## Architecture

- Keep the accepted M1 read-only adapter unchanged. Add a separate internal DEMO adapter whose
  only mutation is one semantically narrow protected-market submission method.
- Consume an exact M9 decision, current valid M10 human-review eligibility, real-provider
  acceptance evidence, an accepted DEMO environment, and an immutable human approval.
- Rebuild a fresh M2 execution snapshot with a distinct `execution_snapshot_id`, bind it to the
  immutable `analysis_snapshot_id`, reconstruct the current M3 account context, and invoke the
  existing M3 Risk Engine as the sole risk authority.
- Seal a deterministic immutable `DemoOrderIntent`; claim it atomically by intent, source SHADOW
  intent, and client trade identity before any broker mutation.
- Persist the state sequence `CREATED -> CLAIMED -> DISPATCHING -> SUBMITTED -> CONFIRMED`, with
  terminal `REJECTED`, `UNKNOWN`, or `RECONCILIATION_FAILED` branches.
- Run `order_check` while still `CLAIMED`. Then run `FinalDispatchGuard`, persist `DISPATCHING`,
  make exactly one possible submission, normalize the result, and reconcile composite evidence.
- Treat any crash or uncertain result after `DISPATCHING` as reconciliation-only. Never resend.

## FinalDispatchGuard

Immediately before mutation, trusted code revalidates unique claim ownership, intent expiry,
effective and unrevoked human approval, ENABLED control state, accepted DEMO account/environment,
zero conflicting positions, fresh tick, spread and drift bounds, trade-capable symbol metadata,
and unchanged intent/Risk/qualification linkage. Any failure results in zero submission calls.

## Identity and reconciliation

`client_trade_id`, broker magic, and comments are supporting correlation fields, never sole proof.
Confirmation requires compatible account/environment fingerprints, symbol, side, exact volume,
bounded dispatch time, broker order/deal identity, resulting position identity, fill, and exact
mandatory SL/TP. Altered or truncated comments must not cause false rejection or confirmation.

## Files

- Add typed execution schemas/enums, error taxonomy, deterministic IDs/digests, acceptance and
  preflight policies, service, reconciliation, observation source, and repository protocols.
- Add a separate `execution/mt5_demo/` backend, mappers, and adapter.
- Add append-only in-memory and SQLite repositories.
- Add inert M11 settings, startup policy, example policy/acceptance/approval files, README, and
  `M11_REPORT.md`.
- Add unit, safety, persistence, provider-free integration, and separately gated real-DEMO tests.

## Acceptance criteria

- Fake-adapter end-to-end flow confirms exactly one submission with mandatory SL and TP.
- `order_check` success never implies submission or confirmation.
- Every FinalDispatchGuard failure occurs before `DISPATCHING` and produces zero submissions.
- Duplicate identities cannot be claimed or submitted twice.
- Crash/uncertainty at or after `DISPATCHING` can only reconcile; it cannot resend.
- Composite reconciliation does not depend on comment or magic alone.
- Analysis and execution snapshots remain distinct, immutable, and auditable.
- Full pytest, Ruff, strict mypy, and M0-M11 safety suites pass.
- Real MT5 DEMO broker acceptance is separately gated and may remain pending without weakening
  provider-free M11 core acceptance.
