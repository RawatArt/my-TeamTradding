# AI Trading Team

AI Trading Team is an experimental, safety-first platform for researching a deterministic,
auditable multi-agent trading workflow. The intended long-term boundary is: AI proposes, the
deterministic Risk Engine controls, the Execution Engine executes, and MetaTrader 5 communicates
with the broker.

This repository makes no profitability claim and is not production-ready.

## Safety philosophy

- Capital survival takes priority over trade frequency or return.
- Missing or invalid information results in no trade.
- AI will never have authority to size or execute orders or bypass deterministic risk controls.
- Martingale, averaging down, loss doubling, and automatic risk increases after losses are
  prohibited.
- Secrets must be supplied through ignored environment files or an approved secret store.
- Application mode and risk state are separate concepts.

## Current milestone

**M11 - guarded, exactly-once DEMO execution core**

M11 adds an explicitly invoked path for at most one protected market order on one accepted DEMO
environment. It requires a valid M10 qualification, exact real-provider acceptance evidence,
fresh M2 execution observations, a fresh M3 Risk approval, immutable human approval, atomic claim
ownership, and an ENABLED operator control state. It has no scheduler and startup never executes.

The final decision candle cannot also be an outcome candle. Same-bar TP/SL touches are explicitly
ambiguous, horizons are finite, and MFE/MAE terminates with the outcome. M8 reports theoretical
level-touch results only; it does not simulate fills, costs, portfolio equity, or account
drawdown.

`LIVE` remains unconditionally prohibited. `DEMO` mode alone is insufficient to submit anything;
M11 execution is disabled by default and all acceptance, approval, control, freshness, and Risk
guards must pass again immediately before the single possible broker mutation.

The real-DEMO acceptance addendum adds a separate finite-TTL readiness phase and a fresh human
approval bound to one candidate, environment, policy, and execution-control generation.
Readiness performs terminal reads only: it creates no execution claim and makes no broker check
or submission. The separately gated execute-once command consumes readiness before delegating to
the existing M11 state machine. See `docs/acceptance/M11_REAL_DEMO_RUNBOOK.md`; real broker
acceptance remains pending.

## Environment setup

Python 3.12 is the canonical runtime through M11. MetaTrader5 is available only on supported Windows
x86-64 CPython environments. From PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Do not place real credentials in `.env.example`. The local `.env` file is ignored by Git.
Install the pinned optional provider SDK set only when running explicit provider smoke tests:

```powershell
python -m pip install -e ".[dev,providers]"
```

## Commands

Run the non-trading startup check:

```powershell
python -m ai_trading_team
```

Run verification:

```powershell
python -m pytest
python -m ruff check .
python -m mypy src tests
```

## Read-only MT5 usage

The terminal must already have the target symbol selected; M1 never selects it automatically.
Explicit login is optional, but `MT5__LOGIN`, `MT5__PASSWORD`, and `MT5__SERVER` must be supplied
together when used.

```python
from ai_trading_team.config import AppSettings
from ai_trading_team.mt5 import MT5ReadOnlyClient
from ai_trading_team.schemas.enums import Timeframe

settings = AppSettings()
client = MT5ReadOnlyClient(settings.mt5)

try:
    health = client.initialize()
    account = client.get_account_info()
    symbols = client.get_symbols("*USD*")  # None explicitly requests all broker symbols.
    metadata = client.get_symbol_info("EURUSD")
    tick = client.get_tick("EURUSD")
    candles = client.get_candles("EURUSD", Timeframe.M15, 100)
    positions = client.get_positions("EURUSD")
finally:
    client.shutdown()
```

`get_candles(symbol, timeframe, count, include_incomplete=False)` accepts 1 to 5,000 bars and
excludes the terminal's current incomplete bar by default.

The demo-terminal integration test is opt-in:

```powershell
$env:RUN_MT5_INTEGRATION="true"
$env:TRADING_SYMBOL="YOUR_BROKER_SYMBOL"
python -m pytest -m mt5_integration
```

It fails unless the connected account is classified by MT5 as DEMO. It performs reads only.

## MarketSnapshot composition

The caller owns lifecycle and trace identifiers. `MarketDataService` receives an initialized
read-only client and uses `TRADING_SYMBOL`; it does not initialize MT5, change symbol selection,
or expose a trading operation.

```python
from ai_trading_team.config import AppSettings
from ai_trading_team.market import MarketDataService
from ai_trading_team.mt5 import MT5ReadOnlyClient
from ai_trading_team.schemas.enums import Timeframe

settings = AppSettings()
client = MT5ReadOnlyClient(settings.mt5)

try:
    client.initialize()
    service = MarketDataService(client, settings.market_data, settings.trading_symbol)
    snapshot = service.build_snapshot(
        cycle_id="cycle-20260910-001",
        snapshot_id="snapshot-analysis-001",
        primary_timeframe=Timeframe.M15,
    )
finally:
    client.shutdown()
```

M2 separates three concepts:

- Validity: invalid structure or inconsistent timestamps prevent snapshot creation.
- Freshness: valid observations are classified as `FRESH` or `STALE`.
- Tradeability: deliberately not evaluated in M2.

Stale data can therefore produce a valid snapshot during a legitimate market closure. The
default completed-candle counts are 200 for M15, H1, and H4 and are configurable under
`MARKET_DATA__*` settings.

## Deterministic risk evaluation

`RiskEngine` is stateless. Its caller supplies an explicit UTC `evaluated_at`, a proposal tied to
the snapshot's `cycle_id` and `snapshot_id`, and an `AccountRiskContext`. The context identifies
the same account through a non-secret fingerprint and supplies:

- `context_as_of` and the UTC trading-day start;
- `cash_flow_adjusted_peak_equity`;
- cash-flow-adjusted day-start equity; and
- the account-wide open-position count.

The caller owns persistence and deposit/withdrawal adjustment; M3 has no cash-flow ledger. A
context from a different account or trace is rejected. M3 also retains M2's broker timestamp
rules and performs no timezone correction.

Stop-risk sizing uses percentage points and exact `Decimal` arithmetic:

```text
allowed risk = equity * (risk percent / 100)
ticks to stop = abs(entry - stop loss) / trade_tick_size
loss per lot = ticks to stop * trade_tick_value
raw volume = allowed risk / loss per lot
```

The accepted M1 contract has one `trade_tick_value`, not separately validated profit-side and
loss-side values. M3 uses that field once as the loss value for one tick and one lot. It records
and validates `trade_contract_size` but does not multiply it again. No Forex pip convention or
currency conversion is inferred. Volume is capped and rounded down on the broker grid anchored
at `volume_min`; broker minimum volume is rejected when it would exceed allowed risk.

```python
from datetime import UTC, datetime

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.risk import RiskEngine, account_fingerprint
from ai_trading_team.schemas.risk import AccountRiskContext

evaluated_at = datetime.now(UTC)
context = AccountRiskContext(
    cycle_id=snapshot.cycle_id,
    snapshot_id=snapshot.snapshot_id,
    account_ref=account_fingerprint(snapshot.account.account_id, snapshot.account.server),
    context_as_of=evaluated_at,
    trading_day_started_at=evaluated_at.replace(hour=0, minute=0, second=0, microsecond=0),
    cash_flow_adjusted_peak_equity="1000.00",
    adjusted_day_start_equity="1000.00",
    account_open_position_count=0,
)
decision = RiskEngine(RiskConstitutionSettings()).evaluate(
    proposal,
    snapshot,
    context,
    evaluated_at=evaluated_at,
)
```

## Agent contracts and orchestration policy

All role outputs use one strict envelope containing `cycle_id`, `snapshot_id`, output identity,
agent and prompt versions, vendor-neutral runtime/policy references, an explicit UTC production
time, descriptive confidence, evidence, warnings, invalidations, and a typed role payload.
Confidence is intentionally absent from `TradeProposal`, `RiskDecision`, and position-sizing
inputs.

Agents receive `AgentMarketView`, a sanitized projection of the accepted M2 snapshot. It omits
account identity, broker server metadata, open-position details, tick valuation, contract size,
and volume limits. Agents have no MT5, credential, risk-engine, execution, or peer-agent handle.
Only a future orchestrator may invoke an agent through `BaseAgent.analyze()`.

The declared realtime dependency order is:

```text
Stage 1 (parallel): Market Context | Trend Analyst | Price Action Analyst
Stage 2:            Entry Analyst
Stage 3 (optional): Quant Researcher | Senior Quant Developer
Stage 4:            Skeptic
Stage 5:            Chief Trader
Stage 6:            deterministic Risk Engine
```

M4 defines policy only; it does not schedule these stages. Stale-but-valid M2 data remains valid.
For a future realtime decision cycle, M4 policy maps a stale snapshot to `HOLD` without changing
the snapshot or making stale synonymous with invalid.

## Single-agent model runtime

M5 accepts one caller-constructed `AgentInvocationRequest` at a time. It verifies the prompt
digest and exact role schemas, checks the requested runtime profile against a separate validated
`ModelCapabilityProfile`, reserves a conservative Decimal budget, and calls exactly one provider
adapter. There is no provider fallback, and a referenced retry policy permits at most three total
calls through unambiguous `max_attempts` semantics.

Models generate only semantic role content: confidence, evidence, warnings, invalidations, and a
typed role payload. They cannot declare `SUCCESS`/`DEGRADED`, alter trace or policy metadata,
choose a provider, size risk, or execute. Trusted runtime code constructs status and the final
M4 `AgentOutput` after successful validation. Invalid JSON/schema is not repaired or guessed.

Token estimates expose whether they are provider-reported, tokenizer-derived, conservatively
estimated, or unavailable. Budget reservations move through `RESERVED`, `DISPATCHED`, `SETTLED`,
`RELEASED`, or `UNCERTAIN`; a timeout after dispatch never assumes the provider did not charge.
Each provider attempt has its own reservation while retaining one deterministic logical
invocation identity. SQLite rejects a duplicate attempt and prevents the same logical invocation
from being dispatched twice outside its bounded retry sequence.

Provider smoke tests require an explicit flag, matching secret, and explicit model identifier:

```powershell
$env:RUN_OPENAI_SMOKE="true"
$env:OPENAI_SMOKE_MODEL="YOUR_ACCEPTED_MODEL_ID"
python -m pytest tests/integration/test_llm_provider_smoke.py -m llm_smoke
```

Use the analogous `RUN_ANTHROPIC_SMOKE` / `ANTHROPIC_SMOKE_MODEL` or
`RUN_GEMINI_SMOKE` / `GEMINI_SMOKE_MODEL` variables. Credentials are loaded through the ignored
`.env` settings shown in `.env.example`. Missing credentials leave that provider unaccepted for
later runtime use but do not invalidate the provider-neutral M5 core.

## One-shot SHADOW decision cycle

M6 exposes an explicitly invoked `ShadowCycleOrchestrator`; it does not schedule itself. Before
the first agent call, trusted code claims the cycle and validates snapshot/context trace IDs, the
safe account fingerprint, and UTC temporal consistency. Duplicate or previously incomplete cycle
IDs fail closed without redispatch. A crash leaves the claim auditable as `INCOMPLETE`; an
operator may mark it `ABANDONED`, but neither state can be reused or resumed automatically.

Stage 1 runs Market Context, Trend, and Price Action concurrently. Entry follows, optional Quant
roles run only when the configured cycle policy selects them, and the bounded Skeptic/Chief
exchange runs for one round by default (maximum three). Only a Chief BUY/SELL proposal reaches
the existing deterministic M3 Risk Engine. Chief HOLD, policy HOLD, risk rejection, risk halt,
and orchestration aborts remain non-executable outcomes.

Logical agent invocation IDs are derived from cycle, snapshot, stage, role, and debate round;
provider retries keep that ID and use distinct attempt numbers. Real-provider eligibility also
requires a current acceptance record bound to provider/model, adapter and SDK versions,
capability digest, runtime-profile digest, and smoke-test identity. The checked-in acceptance
example is intentionally empty.

The terminal-independent full-cycle acceptance test is:

```powershell
python -m pytest tests/integration/test_shadow_cycle_fake_provider.py
```

The real-provider SHADOW test is an explicit opt-in and requires a locally supplied accepted
profile, acceptance registry, credential, and `RUN_M6_PROVIDER_SHADOW=true`. It never accesses
MT5 or executes an order.

The M2 demo integration test is also explicit and read-only:

```powershell
$env:RUN_MT5_INTEGRATION="true"
$env:TRADING_SYMBOL="YOUR_ALREADY_SELECTED_BROKER_SYMBOL"
python -m pytest tests/integration/test_market_snapshot_demo.py -m mt5_integration
```

## Deterministic market features

`MarketFeatureEngine` is explicitly invoked with an accepted snapshot and requires no terminal,
provider, Risk Engine, or clock:

```python
from ai_trading_team.config import AppSettings
from ai_trading_team.features import MarketFeatureEngine, canonical_feature_json

settings = AppSettings()
feature_set = MarketFeatureEngine(settings.features).calculate(snapshot)
canonical_bytes = canonical_feature_json(feature_set)
```

All calculations use a fixed local Decimal context. `generated_at` is the snapshot completion
time, not wall-clock time. Candle and configuration digests use canonical sorted JSON, normalized
Decimal strings, and fixed-width UTC timestamps. The same snapshot, configuration, and engine
version therefore produce equal models and byte-identical canonical JSON.

## Offline historical replay

M8 sources deterministic local fixtures/files through separate decision and outcome views. At
cutoff T, decision candles must close by T; outcome candles must open at or after T and close
inside the selected partition and finite horizon. Partitions explicitly separate warm-up context
from scored evaluation time and retain `RESEARCH`, `VALIDATION`, or `OUT_OF_SAMPLE` identity.

The core outcome assumption is versioned and explicit: the frozen proposal is treated as active
at its entry at T, and results describe theoretical TP/SL level touches without broker fills,
commission, spread, slippage, or gap-price adjustment. `sequence_max_drawdown_r` measures an
ordered sequence of resolved trade outcomes; it is not account, equity, or portfolio drawdown.

Run the provider-free deterministic pipeline acceptance with:

```powershell
python -m pytest tests/integration/test_historical_replay_pipeline.py
```

## Continuous SHADOW observation

ContinuousShadowRuntime exposes only start, health, poll_once, and shutdown. It has no internal
scheduler or execution interface. Each poll reads completed M15 candles, claims at most one
timely unclaimed decision, builds an M2 snapshot with an opaque snapshot ID, validates the exact
decision candle, calculates M7 features, constructs the M3 account context, and delegates the
one-shot graph to M6.

The persisted identity chain is decision_key to cycle_id to actual snapshot_id. Snapshot IDs are
never derived from candle identity. Unfinished claims become ABANDONED on restart and are never
automatically resumed. Missing or ambiguous risk baselines, stale snapshots, and pre-dispatch
provider ineligibility produce typed policy HOLD records with zero provider dispatch.

Risk baselines have explicit ACTIVE, SUPERSEDED, and INVALIDATED states. Exactly one compatible
active record must cover the safe account fingerprint, UTC day, and context time. M9 never picks
the newest baseline implicitly and never infers deposits or withdrawals.

## SHADOW qualification evidence

M10 is a separate, explicitly invoked evidence task. It reads a bounded predeclared interval from
the accepted M9 audit repository, attaches only exact compatible M8 outcomes, and records the
material provider, prompt, runtime, feature, Risk, outcome, pricing, and timestamp-acceptance
dependencies. It never starts or polls the M9 runtime.

Evidence follows an append-only `OPEN -> SEALED -> EVALUATED` lifecycle. Once sealed, decisions,
outcomes, pricing, acceptance evidence, and dependencies cannot be changed or backfilled. More
collection requires a new qualification run. Graduation consumes only sealed evidence.

Evidence validity (`VALID`, `EXPIRED`, `INVALIDATED`, or `CONTAMINATED`) is separate from the
historical graduation result (`ELIGIBLE_FOR_DEMO_REVIEW` or `NOT_ELIGIBLE`). Current eligibility
requires both a passing result and currently valid evidence. Expiration therefore never becomes a
false trading-performance failure and never rewrites the historical evaluation.

Observed costs report settled spend and conservative uncertain reservations. The 30-day cost
projection is a separate policy-labeled estimate and is never presented as provider billing.
Win rate is descriptive by default and cannot be the sole graduation gate. Out-of-sample
evidence, reviewed R-based performance rules, operational gates, and zero-tolerance safety gates
remain explicit and versioned.

Run the provider-free qualification acceptance with:

```powershell
python -m pytest tests/integration/test_m10_fake_qualification.py
```

## Guarded DEMO execution

`DemoExecutionService` is a one-shot coordinator, not a trading loop. It preserves the original
analysis snapshot and SHADOW decision, builds a distinct `PRE_SEND_REVALIDATION` snapshot, and
requires the existing deterministic M3 Risk Engine to approve the exact current price and account
context. AI confidence is not an execution or sizing input.

The durable sequence is `CLAIMED -> order_check -> FinalDispatchGuard -> DISPATCHING -> one
possible order_send -> reconciliation`. `order_check` is non-submitting and never creates a
`SUBMITTED` state. `DISPATCHING` is persisted before the external call. A timeout, crash, or
unknown broker result can only enter reconciliation; the intent can never be resent.

`FinalDispatchGuard` rechecks claim ownership, intent lifetime, human approval, execution-control
state, DEMO account/environment identity, open positions, tick age, spread, price drift, symbol
capability, and sealed Risk/qualification linkage. Any failed check produces zero submissions.
Broker reconciliation uses composite account, symbol, side, volume, timing, broker ID, position,
fill, SL, and TP evidence; comment and magic are supporting fields only.

Run the broker-free core acceptance with:

```powershell
python -m pytest tests/integration/test_m11_fake_demo_execution.py
```

Real MT5 DEMO acceptance is separately gated and remains pending until reviewed environment and
human-approval artifacts are explicitly configured. The core suite never uses a real account to
make M11 pass. `LIVE` is prohibited under every M11 configuration.

## Project structure

```text
src/ai_trading_team/
|-- config/          # Typed settings and milestone startup policy
|-- schemas/         # Core, market, risk, agent, orchestration, and runtime contracts
|-- utils/           # UTC time and structured logging helpers
|-- mt5/             # M1 read-only client, backend protocol, and mappers
|-- market/          # M2 read-only snapshot composition and freshness
|-- features/        # M7 Decimal-only indicators, geometry, structure, and provenance
|-- replay/          # M8 offline clocks, capped sources, snapshots, frames, and freezing
|-- evaluation/      # M8 finite outcomes, R metrics, and descriptive segmentation
|-- observation/     # M9 bounded continuous SHADOW coordination and eligibility gates
|-- qualification/   # M10 evidence sealing, validity, metrics, and graduation gates
|-- risk/            # M3 proposal, account-guard, sizing, and decision logic
|-- agents/          # M4 abstract roles, access rules, and runtime protocol
|-- prompts/         # M5 immutable prompt artifacts and verified registry
|-- runtime/         # M5 single-agent router, budgets, validation, and provider adapters
|-- orchestration/   # M4 contracts plus the M6 one-shot SHADOW cycle runtime
|-- execution/       # M11 guarded one-shot DEMO execution and composite reconciliation
|-- backtest/        # Reserved; no strategy backtester or optimizer exists
`-- storage/         # Append-only budget, audit, replay, qualification, and execution stores

tests/
|-- fakes/           # Terminal-independent MT5, market, risk, agent, provider, and cycle fixtures
|-- unit/            # Domain, market-feature, risk, agent, runtime, audit, and policy tests
|-- integration/     # Deterministic feature pipeline, fake SHADOW cycle, and opt-in tests
`-- safety/          # M0-M11 startup, look-ahead, and architectural safety tests
```

Every snapshot retains both its decision/evaluation `cycle_id` and its distinct `snapshot_id`.
This permits multiple immutable captures in a future cycle without conflating their identities.
M1 observations remain independently versioned and retain their UTC retrieval timestamps inside
the M2 aggregate.

## Known limitations

- M11 core acceptance uses a fake adapter. Real MT5 DEMO submission/reconciliation acceptance is
  separately gated and remains pending until an exact reviewed environment is configured.
- M11 supports one initial protected market order only. It has no pending orders, pyramiding,
  position closing/modification, SL/TP modification, blind resend, scheduler, or LIVE path.
- M10 is not a portfolio simulator and reuses M8's theoretical R metrics without creating a
  second outcome algorithm.
- M9 has no internal scheduler; callers must explicitly poll the bounded runtime.
- M9 core acceptance uses fake providers. A real provider/model/role remains ineligible until
  its exact M5, M6, and M9 evidence chain is recorded and current.
- Risk baselines remain caller-attested; M9 does not infer deposits or withdrawals.
- M2 and its M1 source are synchronous and Windows/MetaTrader-terminal dependent.
- Broker symbols and contract properties vary and must be discovered rather than assumed.
- M2 does not infer undocumented broker-server timezone offsets. Source times that appear in the
  future relative to host UTC are rejected as inconsistent instead of silently shifted.
- The caller must maintain cash-flow-adjusted peak/day-start equity and account-wide position
  counts; M3 deliberately has no persistence or cash-flow ledger.
- M1 exposes only a single broker `trade_tick_value`; symbols requiring distinct validated
  loss-side valuation or currency conversion must be rejected by a future runtime until that
  contract gap is resolved.
- M3 evaluates risk from a valid snapshot but does not decide whether stale data is tradeable.
- M7 exposes only latest-per-timeframe feature facts; it does not create signals, strategies, or
  historical backtest series.
- M9 exposes M7 output through a strictly allowlisted, versioned `AgentFeatureView`; it does not
  permit agents to recompute features or access raw feature-engine internals.
- M8 outcomes are theoretical OHLC level-touch measurements, not executed fills or cash P&L.
- M8 does not reconstruct portfolio equity or fabricate historical `AccountRiskContext` values.
- OHLC cannot reveal intrabar event ordering; dual TP/SL touches remain ambiguous.
- Historical datasets lacking complete accepted as-of observations cannot reproduce an M2
  snapshot; M8 never fabricates the missing snapshot or historical account state.
- M6 runs only one explicitly requested decision cycle. It has no new-candle scheduler,
  continuous trading loop, automatic crash recovery, or provider fallback.
- Optional real-provider smoke acceptance is tracked separately per provider. An untested
  provider/model is not eligible for later runtime use.
- Provider-neutral token estimation is explicitly conservative and may over-reserve; caller-owned
  validated capability and pricing profiles remain required.
- Quant roles may be assigned conditional or offline profiles, but M4 does not decide when to
  invoke them.
- Performance review is reference-based and offline; no performance store or automatic strategy
  change exists.
- Real-provider M6 acceptance remains provider/model-specific and requires a current hardened
  smoke record; the provider-neutral fake cycle does not confer real-provider eligibility.
- M10 qualification remains human-review evidence; M11 adds independent approval and environment
  gates rather than treating qualification as automatic execution permission.

See `MASTER_SPEC.md`, `AGENTS.md`, and `docs/milestones/M11_REPORT.md` for the authoritative scope
and milestone status. Earlier accepted baselines remain documented under `docs/milestones/`.
