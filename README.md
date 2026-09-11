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

**M4 - Agent foundation and orchestration contracts**

M4 defines nine typed agent roles, immutable input/output envelopes, least-privilege information
views, deterministic stage metadata, bounded debate rules, and vendor-neutral future runtime
interfaces. It makes no model or network call and implements no scheduler or trading loop.

The Performance Reviewer is confined to a separate retrospective pipeline. Quant Researcher and
Senior Quant Developer are conditional/offline-capable rather than mandatory on every decision
cycle. The realtime graph ends at the existing deterministic M3 Risk Engine; no agent can invoke
it or bypass it.

`LIVE` remains part of the durable `ApplicationMode` type, but the replaceable M4 startup policy
rejects it. No execution path exists in this milestone.

## Environment setup

Python 3.12 is the canonical runtime through M4. MetaTrader5 is available only on supported Windows
x86-64 CPython environments. From PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Do not place real credentials in `.env.example`. The local `.env` file is ignored by Git.

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

The M2 demo integration test is also explicit and read-only:

```powershell
$env:RUN_MT5_INTEGRATION="true"
$env:TRADING_SYMBOL="YOUR_ALREADY_SELECTED_BROKER_SYMBOL"
python -m pytest tests/integration/test_market_snapshot_demo.py -m mt5_integration
```

## Project structure

```text
src/ai_trading_team/
|-- config/          # Typed settings and milestone startup policy
|-- schemas/         # Core, market, risk, agent, and orchestration contracts
|-- utils/           # UTC time and structured logging helpers
|-- mt5/             # M1 read-only client, backend protocol, and mappers
|-- market/          # M2 read-only snapshot composition and freshness
|-- risk/            # M3 proposal, account-guard, sizing, and decision logic
|-- agents/          # M4 abstract roles, access rules, and runtime protocol
|-- orchestration/   # M4 stages, failures, debate, and orchestration protocols
|-- execution/       # Reserved; no execution code exists
|-- backtest/        # Reserved for M7
`-- storage/         # Reserved for a later audit repository

tests/
|-- fakes/           # Terminal-independent MT5, market, risk, and agent fixtures
|-- unit/            # Domain, adapter, market, risk, agent, and policy tests
|-- integration/     # Opt-in demo-terminal reads and snapshot composition
`-- safety/          # Startup, read-only, and deterministic-risk safety tests
```

Every snapshot retains both its decision/evaluation `cycle_id` and its distinct `snapshot_id`.
This permits multiple immutable captures in a future cycle without conflating their identities.
M1 observations remain independently versioned and retain their UTC retrieval timestamps inside
the M2 aggregate.

## Known limitations

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
- M4 contains contracts and policy only: no concrete agent analysis, model adapter, prompt
  content, scheduler, API cost accounting, or orchestration runtime exists.
- Quant roles may be assigned conditional or offline profiles, but M4 does not decide when to
  invoke them.
- Performance review is reference-based and offline; no performance store or automatic strategy
  change exists.
- Shadow automation, demo execution, and live safeguards beyond the M4 startup policy belong to
  later milestones and require their own acceptance criteria.

See `MASTER_SPEC.md`, `AGENTS.md`, and `docs/milestones/M4_REPORT.md` for the authoritative scope
and milestone status. Earlier accepted baselines remain documented under `docs/milestones/`.
