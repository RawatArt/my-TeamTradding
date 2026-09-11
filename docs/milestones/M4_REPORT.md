# M4 Completion Report

Date: 2026-09-11
Status: Fully accepted

## Baseline preservation

- Started from accepted annotated tag `m3-v0.4.0`.
- Isolated M4 changes on `feat/m4-agent-foundation`.
- Kept the M1 read-only adapter, M2 snapshot composition, and M3 deterministic risk
  implementation unchanged.
- Did not change the accepted M0, M1, M2, or M3 completion reports.
- Advanced the project package version to `0.5.0` and preserved M4 with annotated tag
  `m4-v0.5.0` only after full verification.

## Implemented

- Added shared generic `BaseAgent` with exactly one abstract asynchronous analysis operation and
  no service, peer-agent, MT5, risk-engine, or execution handle.
- Added abstract typed contracts for Market Context, Trend Analyst, Price Action Analyst, Entry
  Analyst, Quant Researcher, Senior Quant Developer, Skeptic, Chief Trader, and Performance
  Reviewer.
- Added immutable Pydantic input and output contracts for all nine roles.
- Added a common strict `AgentOutput` envelope with schema/output/cycle/snapshot identity, agent
  and prompt versions, vendor-neutral runtime and policy references, UTC production time,
  descriptive Decimal confidence, evidence, warnings, invalidations, and a typed role payload.
- Added a sanitized `AgentMarketView` projection that preserves validated M2 market data while
  omitting account identity, broker server metadata, position details, tick valuation, contract
  size, and broker volume limits.
- Added an explicit immutable information-access matrix for snapshot views, upstream outputs,
  proposals, quantitative evidence, risk decisions, and performance history.
- Added execution profiles `REALTIME`, `CONDITIONAL`, and `OFFLINE`, plus inert invocation modes
  `REALTIME`, `CANDIDATE_ONLY`, `PERIODIC`, and `OFFLINE`.
- Added vendor-neutral `runtime_profile_ref`, `invocation_policy_ref`, and optional
  `cost_policy_ref` metadata without selecting a provider or implementing cost accounting.
- Added deterministic stage metadata for the approved six-stage decision pipeline, ending at an
  interface to the existing deterministic Risk Engine.
- Kept Quant Researcher and Senior Quant Developer optional in the realtime graph and eligible
  for conditional or offline profiles.
- Placed Performance Reviewer only in a separate retrospective pipeline; it cannot influence a
  current trade decision.
- Added typed failure records and deterministic policies for timeout, invalid output, missing
  upstream data, unavailable roles, stale/invalid snapshots, and schema mismatch.
- Preserved M2 stale-but-valid semantics. M4 maps a stale decision input to `HOLD` only in its
  orchestration policy and does not mutate or invalidate the snapshot.
- Added structured Skeptic challenges targeting only Entry or Chief outputs, configurable debate
  rounds defaulting to one, a hard maximum of three, and monotonic round validation.
- Added a vendor-neutral future runtime protocol but no implementing model adapter, prompt body,
  network call, or scheduler.
- Added an M4 startup policy that continues to prohibit LIVE mode and both live-enablement flags.

## Information-access decisions

- Market Context, Trend, and Price Action receive only the sanitized market view.
- Entry additionally receives typed Stage 1 outputs and explicit failure records.
- Quant roles may receive upstream outputs, quantitative evidence references, and optional
  performance-history references.
- Skeptic and Chief may receive upstream analyses, proposal-bearing typed outputs, and
  quantitative evidence, but no risk decision.
- Only the offline Performance Reviewer may receive risk-decision and performance-history
  references.
- No agent receives credentials, raw MetaTrader5 objects, an MT5 client, or broker position-sizing
  metadata.

## Failure and debate policy

- Invalid snapshots, schema mismatch, or an unknown invariant abort the cycle.
- Stale-but-valid snapshots and missing required upstream outputs default to `HOLD`.
- Invalid current-cycle agent output defaults to `HOLD`.
- A Stage 1 timeout or unavailable role may continue degraded only when two valid Stage 1 outputs
  remain.
- An optional Quant Researcher or offline Performance Reviewer availability failure may continue
  degraded; failures of required downstream roles default to `HOLD`.
- Performance-review failure has no effect on the current decision cycle.
- Debate is represented only by bounded immutable challenges. No free-form peer chat, recursion,
  prompt mutation, or self-modifying behavior exists.

## Files created

- `docs/milestones/M4_PLAN.md`
- `docs/milestones/M4_REPORT.md`
- `src/ai_trading_team/agents/access.py`
- `src/ai_trading_team/agents/base.py`
- `src/ai_trading_team/agents/protocols.py`
- `src/ai_trading_team/agents/roles.py`
- `src/ai_trading_team/orchestration/debate.py`
- `src/ai_trading_team/orchestration/failures.py`
- `src/ai_trading_team/orchestration/protocols.py`
- `src/ai_trading_team/orchestration/stages.py`
- `src/ai_trading_team/schemas/orchestration.py`
- `tests/fakes/agents.py`
- `tests/safety/test_m4_agent_boundaries.py`
- `tests/safety/test_m4_confidence_isolation.py`
- `tests/safety/test_m4_startup_policy.py`
- `tests/unit/test_agent_access_policy.py`
- `tests/unit/test_agent_adapter_protocol.py`
- `tests/unit/test_agent_failure_policy.py`
- `tests/unit/test_agent_framework_settings.py`
- `tests/unit/test_agent_inputs.py`
- `tests/unit/test_agent_role_contracts.py`
- `tests/unit/test_agent_schemas.py`
- `tests/unit/test_debate_policy.py`
- `tests/unit/test_orchestration_stages.py`

## Files changed

- `.env.example`
- `README.md`
- `pyproject.toml`
- `src/ai_trading_team/__init__.py`
- `src/ai_trading_team/agents/__init__.py`
- `src/ai_trading_team/config/__init__.py`
- `src/ai_trading_team/config/settings.py`
- `src/ai_trading_team/config/startup.py`
- `src/ai_trading_team/main.py`
- `src/ai_trading_team/orchestration/__init__.py`
- `src/ai_trading_team/schemas/__init__.py`
- `src/ai_trading_team/schemas/agents.py`
- `src/ai_trading_team/schemas/enums.py`
- `tests/unit/test_schemas.py`

## Verification

Canonical environment: Windows x86-64, CPython 3.12.13.

- Full default suite: **262 passed, 2 skipped**. The skips are the explicitly gated M1/M2
  demo-terminal integrations; M4 requires neither MT5 nor network access.
- Complete safety suite: **42 passed** across M0 through M4 safety boundaries.
- Ruff: all checks passed.
- Strict mypy: no issues found in 97 source files.
- Default startup: exited 0 in SHADOW mode and confirmed no trading components were active.
- LIVE startup: exited 2 with `StartupPolicyError`.
- Production source scan: no order submission, symbol selection, or order/position mutation
  identifier exists.
- Agent-package scan: no MT5, risk package, execution package, model-vendor SDK, or network-client
  import exists.
- Baseline diff: no M4 change was made inside the accepted `mt5`, `market`, `risk`, `execution`, or
  `backtest` packages.

## Safety confirmation

- No model or LLM call, SDK, network access, or real prompt was introduced.
- Agents cannot call each other; only the future orchestrator protocol accepts an agent instance.
- Agents cannot access MT5, credentials, the Risk Engine, execution, or position sizing.
- Agent confidence is exact Decimal metadata and is absent from proposals, risk decisions,
  account-risk context, sizing results, and Risk Engine/position-sizer call signatures.
- Chief Trader may produce a trace-matched `TradeProposal`, but it cannot approve risk or execute.
- No order submission, order/position mutation, trading loop, backtest, strategy optimization, or
  autonomous strategy change exists.
- LIVE remains prohibited.
- The tracked broker/FX source timestamp incompatibility remains unchanged. M4 neither guesses nor
  rewrites broker timestamps; a future trading runtime must reject unresolved symbols.

## Known limitations

- M4 defines abstractions, contracts, and deterministic policy only. It contains no concrete agent
  analysis, runtime adapter, orchestrator implementation, scheduler, or decision-cycle runner.
- Prompt references contain identity/version metadata and an optional digest, but no prompt
  content or prompt registry exists.
- Runtime, invocation, and cost policy references are inert. No model selection, token budgeting,
  API cost accounting, or retry behavior exists.
- Identifier uniqueness and historical agent-output persistence remain caller-owned because no
  audit repository exists yet.
- Performance history is represented by immutable references; no performance repository or
  automatic strategy modification exists.
- M4 defines a stale-input `HOLD` policy but does not make a tradeability determination or change
  M2 freshness calculations.

## Recommended next step

Stop at M4. Begin M5 planning only after explicit approval. M5 should introduce the separately
specified SHADOW-mode runtime without execution or LIVE capability and must preserve the
deterministic M3 Risk Engine as final authority.
