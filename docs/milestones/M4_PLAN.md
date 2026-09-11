# M4 Plan

## Goal

Define the typed AI-agent foundation, least-privilege information views, bounded communication
rules, deterministic stage metadata, and vendor-neutral future runtime interfaces. M4 performs no
model call, agent analysis, scheduling, trading loop, risk bypass, execution, or backtesting.

## Approved architecture

- Abstract generic `BaseAgent` with nine typed role contracts and no direct agent references.
- Sanitized `AgentMarketView`; raw M2 account identifiers and server metadata never cross into an
  AI-facing context.
- Strict immutable output envelopes with cycle, snapshot, agent, prompt, runtime, invocation,
  cost-policy, and UTC provenance.
- Separate valid-output and failure records; missing output is never fabricated.
- Deterministic realtime stage definitions ending at the existing M3 Risk Engine.
- Separate retrospective pipeline for Performance Reviewer.
- Quant Researcher and Senior Quant Developer are conditional/offline-capable and are not
  mandatory on every future M15 cycle.
- Stale snapshots remain valid M2 snapshots; M4 policy merely defaults a future decision cycle to
  HOLD when the supplied view reports stale data.
- Bounded, typed Skeptic challenges with a configurable default of one round and hard maximum of
  three.

## Files

Create:

- `src/ai_trading_team/agents/access.py`, `base.py`, `protocols.py`, and `roles.py`
- `src/ai_trading_team/orchestration/debate.py`, `failures.py`, `protocols.py`, and `stages.py`
- `src/ai_trading_team/schemas/orchestration.py`
- M4 unit and safety tests under `tests/`
- `docs/milestones/M4_PLAN.md` and `M4_REPORT.md`

Change the existing agent schema and enum modules, package exports, typed configuration, startup
policy, version metadata, `.env.example`, and `README.md`. Do not alter the M1 adapter, M2 market
service, or M3 risk algorithms.

## Agent hierarchy and schemas

`BaseAgent[InputT, OutputT]` exposes metadata plus one abstract asynchronous `analyze(context)`
operation. The nine abstract specializations are Market Context, Trend Analyst, Price Action
Analyst, Entry Analyst, Quant Researcher, Senior Quant Developer, Skeptic, Chief Trader, and
Performance Reviewer. They contain no services and cannot call peers.

Every role has a strict input and result payload. Every valid output is wrapped in a common
`AgentOutput` containing schema/output/cycle/snapshot identity, agent/prompt/runtime policy
provenance, UTC production time, status, descriptive Decimal confidence, evidence, warnings,
invalidations, and the typed result. A separate `AgentFailureRecord` represents failures so an
orchestrator never fabricates an output.

`AgentDescriptor` records role and agent version, a prompt reference and optional content digest,
a vendor-neutral `runtime_profile_ref`, execution profile, invocation mode/policy reference, and
optional cost-policy reference. It contains no credential, provider, model name, or prompt body.

## Information-access matrix

| Role | Snapshot view | Upstream outputs | Proposal | Quant evidence | Risk decision | Performance history |
|---|---:|---:|---:|---:|---:|---:|
| Market Context | Yes | No | No | No | No | No |
| Trend Analyst | Yes | No | No | No | No | No |
| Price Action Analyst | Yes | No | No | No | No | No |
| Entry Analyst | Yes | Yes | No | No | No | No |
| Quant Researcher | Yes | Yes | No | Yes | No | Yes |
| Senior Quant Developer | Yes | Yes | No | Yes | No | Yes |
| Skeptic | Yes | Yes | Yes | Yes | No | No |
| Chief Trader | Yes | Yes | Yes | Yes | No | No |
| Performance Reviewer | No | Yes | Yes | Yes | Yes | Yes |

The AI-facing market view excludes account identity, server metadata, position details, broker
tick values, contract size, and volume limits. This prevents credentials and position-sizing
inputs from entering agent contracts.

## Stage and dependency graph

```text
Realtime decision pipeline
  1 parallel: Market Context | Trend Analyst | Price Action Analyst
  2 required: Entry Analyst
  3 optional/conditional: Quant Researcher | Senior Quant Developer
  4 required: Skeptic
  5 required: Chief Trader
  6 required: existing deterministic Risk Engine

Retrospective pipeline
  1 offline: Performance Reviewer
```

Stage definitions are immutable metadata. M4 implements no runtime scheduler. The realtime
pipeline permits Stage 1 to continue with two valid outputs. Quant roles are optional and support
conditional or offline descriptors; Performance Reviewer supports offline only.

## Failure policy

| Failure | M4 disposition |
|---|---|
| Invalid snapshot, schema mismatch, unknown invariant | Abort cycle |
| Stale-but-valid snapshot | HOLD in orchestration policy |
| Missing required upstream output | HOLD |
| Invalid current-cycle agent output | HOLD |
| Stage 1 timeout/unavailable with at least two successes | Continue degraded |
| Stage 1 timeout/unavailable without quorum | HOLD |
| Optional Quant Researcher timeout/unavailable | Continue degraded |
| Required downstream agent timeout/unavailable | HOLD |
| Offline Performance Reviewer failure | Continue degraded; no current-cycle effect |

This policy does not alter M2 validity/freshness or decide whether stale data is tradeable.

## Debate and versioning policy

Only typed `DebateChallenge` records are allowed. The Skeptic may target an Entry or Chief output,
round numbers are monotonic and bounded, the configurable default is one, and the hard maximum is
three. There is no free-form peer chat, recursive invocation, prompt editing, or self-modification.

Agent, prompt, schema, runtime-profile, invocation-policy, and cost-policy references are separate
versioned identities. Meaningful future prompt changes require a new prompt version and digest;
M4 stores no prompt content.

## Testing strategy

- Unit-test all nine strict inputs/outputs, trace matching, UTC and Decimal preservation, role
  descriptor/profile rules, access matrix, stage order/dependencies, failure disposition, and
  debate bounds.
- Prove stale input maps to HOLD only in M4 policy while the immutable M2-derived view is retained.
- Prove Performance Reviewer is absent from the realtime graph and Quant roles are optional.
- Prove confidence is absent from risk and sizing inputs.
- Safety-scan the agent package for MT5, Risk Engine, execution, vendor SDK, and mutation imports.
- Run the complete suite, Ruff, strict mypy, and the complete non-skipped safety suite.

## Acceptance criteria

- All nine contracts extend the shared base and have strict, traceable envelopes.
- Access rules are explicit and immutable; agents cannot see credentials or sizing metadata.
- Realtime and retrospective pipelines are separate and deterministically defined.
- Failure and bounded-debate policy produce safe deterministic outcomes.
- No network/model implementation, prompt body, MT5 access, risk bypass, execution, strategy,
  trading loop, backtest behavior, or LIVE capability is added.
- All verification commands pass before the commit and annotated tag `m4-v0.5.0` are created.

## Safety boundary

No OpenAI or other model SDK, network call, MT5 access, execution method, position-size field,
strategy implementation, prompt content, runtime scheduler, or live-trading capability will be
introduced. LIVE remains prohibited by milestone startup policy.

## Verification

Run the complete pytest suite, Ruff, strict mypy, and all M0-M4 safety tests. Preserve the verified
baseline on `feat/m4-agent-foundation` with annotated tag `m4-v0.5.0`, then stop before M5.
