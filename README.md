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

**M2 - Immutable MarketSnapshot composition**

M2 composes the accepted M1 read-only observations into a strict, immutable `MarketSnapshot`.
Every snapshot has a caller-supplied `cycle_id` and `snapshot_id`, configured broker symbol,
completed M15/H1/H4 candle histories, account state, symbol-scoped open positions, retrieval
timestamps, duration, freshness classifications, and typed validation warnings.

`LIVE` remains part of the durable `ApplicationMode` type, but the replaceable M2 startup policy
rejects it. No execution path exists in this milestone.

## Environment setup

Python 3.12 is the canonical M1 runtime. MetaTrader5 is available only on supported Windows
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
|-- schemas/         # Core, MT5, MarketSnapshot, and timeframe contracts
|-- utils/           # UTC time and structured logging helpers
|-- mt5/             # M1 read-only client, backend protocol, and mappers
|-- market/          # M2 read-only snapshot composition and freshness
|-- risk/            # Reserved for M3
|-- agents/          # Reserved for M4
|-- orchestration/   # Reserved for later decision-cycle orchestration
|-- execution/       # Reserved; no execution code exists
|-- backtest/        # Reserved for M7
`-- storage/         # Reserved for a later audit repository

tests/
|-- fakes/           # Terminal-independent MT5 test double
|-- unit/            # Domain, configuration, adapter, and snapshot tests
|-- integration/     # Opt-in demo-terminal reads and snapshot composition
`-- safety/          # Startup and public-surface safety tests
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
- Risk decisions and position sizing are deferred to M3.
- Agent and LLM behavior is deferred to M4.
- Shadow automation, demo execution, and live safeguards beyond the M1 startup policy belong to
  later milestones and require their own acceptance criteria.

See `MASTER_SPEC.md`, `AGENTS.md`, and `docs/milestones/M1_REPORT.md` for the authoritative scope
and milestone status. The approved M0 baseline is recorded in `docs/milestones/M0_REPORT.md`.
