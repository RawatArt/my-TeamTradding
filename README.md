# AI Trading Team

AI Trading Team is an experimental, safety-first platform for researching a deterministic,
auditable multi-agent trading workflow. The intended long-term boundary is: AI proposes,
the deterministic Risk Engine controls, the Execution Engine executes, and MetaTrader 5
communicates with the broker.

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

**M0 — Architecture**

M0 contains configuration, stable typed boundaries, structured logging, project tooling, and
tests only. It does not connect to MT5, retrieve market data, call an LLM, calculate position
sizes, evaluate risk, execute orders, or run a backtest.

`LIVE` is part of the durable `ApplicationMode` type, but the replaceable M0 startup policy
rejects it. The core configuration model therefore remains suitable for intentional extension
in a later approved milestone while live operation remains impossible now.

## Environment setup

Python 3.12 or newer is required. From PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Do not place real credentials in `.env.example`. The local `.env` file is ignored by Git.

## Commands

Run the non-trading M0 startup check:

```powershell
python -m ai_trading_team
```

Run verification:

```powershell
python -m pytest
python -m ruff check .
python -m mypy src tests
```

## Project structure

```text
src/ai_trading_team/
├── config/          # Typed settings and milestone startup policy
├── schemas/         # Core enums and minimal boundary contracts
├── utils/           # UTC time and structured logging helpers
├── mt5/             # Reserved for M1; no connector exists in M0
├── market/          # Reserved for M2
├── risk/            # Reserved for M3
├── agents/          # Reserved for M4
├── orchestration/   # Reserved for later decision-cycle orchestration
├── execution/       # Reserved; no execution code exists in M0
├── backtest/        # Reserved for M7
└── storage/         # Reserved for a later audit repository

tests/
├── unit/            # Domain, configuration, and utility tests
├── integration/     # Reserved for milestone integration tests
└── safety/          # Non-negotiable safety-policy tests
```

Every cycle-bound schema derives from one traceable base contract containing `cycle_id`,
`schema_version`, and a timezone-aware UTC timestamp. Future agent, decision, risk, execution,
and audit records must preserve that contract.

## Known limitations

- M0 contains no trading behavior.
- Broker symbol metadata has not been validated and is not assumed.
- The standardized `MarketSnapshot` is deferred to M2.
- Risk decisions and position sizing are deferred to M3.
- Agent and LLM behavior is deferred to M4.
- Shadow automation, demo execution, and live safeguards beyond the M0 startup policy belong to
  later milestones and require their own acceptance criteria.

See `MASTER_SPEC.md`, `AGENTS.md`, and `docs/milestones/M0_REPORT.md` for the authoritative scope
and milestone status.

