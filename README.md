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

**M1 - Read-only MetaTrader 5 connectivity**

M1 provides a narrow, typed adapter for reading terminal health, account information, broker
symbols, ticks, completed M15/H1/H4 candles, and existing positions. It cannot place, modify, or
close orders or positions and does not change Market Watch symbol selection.

`LIVE` remains part of the durable `ApplicationMode` type, but the replaceable M1 startup policy
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

## Project structure

```text
src/ai_trading_team/
|-- config/          # Typed settings and milestone startup policy
|-- schemas/         # Core and MT5 boundary contracts
|-- utils/           # UTC time and structured logging helpers
|-- mt5/             # M1 read-only client, backend protocol, and mappers
|-- market/          # Reserved for M2
|-- risk/            # Reserved for M3
|-- agents/          # Reserved for M4
|-- orchestration/   # Reserved for later decision-cycle orchestration
|-- execution/       # Reserved; no execution code exists
|-- backtest/        # Reserved for M7
`-- storage/         # Reserved for a later audit repository

tests/
|-- fakes/           # Terminal-independent MT5 test double
|-- unit/            # Domain, configuration, mapping, and client tests
|-- integration/     # Opt-in demo-terminal reads
`-- safety/          # Startup and public-surface safety tests
```

Every cycle-bound schema derives from one traceable base contract containing `cycle_id`,
`schema_version`, and a timezone-aware UTC timestamp. M1 external observations are versioned and
carry UTC retrieval times; M2 will associate them with a decision cycle without fabricating IDs.

## Known limitations

- M1 is synchronous and Windows/MetaTrader-terminal dependent.
- Broker symbols and contract properties vary and must be discovered rather than assumed.
- The standardized `MarketSnapshot` is deferred to M2.
- Risk decisions and position sizing are deferred to M3.
- Agent and LLM behavior is deferred to M4.
- Shadow automation, demo execution, and live safeguards beyond the M1 startup policy belong to
  later milestones and require their own acceptance criteria.

See `MASTER_SPEC.md`, `AGENTS.md`, and `docs/milestones/M1_REPORT.md` for the authoritative scope
and milestone status. The approved M0 baseline is recorded in `docs/milestones/M0_REPORT.md`.
