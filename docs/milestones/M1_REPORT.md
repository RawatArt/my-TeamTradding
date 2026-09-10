# M1 Completion Report

Date: 2026-09-10
Status: Fully accepted

## Baseline preservation

- Re-ran the approved M0 suite before M1 changes: 33 tests passed, Ruff passed, and strict mypy
  passed.
- Initialized a local Git repository on `main`.
- Preserved M0 in commit `3bc1c9d` (`chore: establish M0 baseline`).
- Created annotated tag `m0-v0.1.0`.
- Isolated M1 changes on `feat/m1-mt5-readonly`.
- No remote was configured and nothing was pushed.

## Dependency verification

- Installed isolated CPython 3.12.13 x86-64 in `.venv`.
- Installed and imported pinned `MetaTrader5==5.0.6180` successfully on Python 3.12.13.
- Configured the dependency with a Windows platform marker and changed CI to Windows with Python
  3.12 so the canonical environment installs the actual wheel.
- Added no direct pandas, OpenAI, AI-agent, execution, risk, or backtesting dependency.

## Implemented

- Added `MT5ReadOnlyClient` with the approved public lifecycle and read methods only.
- Added an internal dependency-injection protocol containing only lifecycle, authentication, and
  read operations.
- Added a lazy, narrow wrapper around the platform-specific MetaTrader5 module.
- Added optional explicit authentication during initialization. Login, password, and server must
  be provided together; an empty password is rejected.
- Added typed health, account, symbol-summary, symbol-metadata, tick, candle, and open-position
  observations.
- Added all requested account balance, equity, margin, symbol-contract, and trading-mode fields.
- Added optional MT5 group-pattern filtering to `get_symbols()`; `None` explicitly requests all
  broker symbols.
- Added `get_candles(symbol, timeframe, count, include_incomplete=False)` for M15, H1, and H4.
  Counts are restricted to 1 through 5,000, and default reads start at terminal bar position 1 to
  exclude the incomplete current candle.
- Added exact Decimal conversion through string representations and UTC conversion from terminal
  epoch timestamps, including millisecond timestamps where available.
- Added explicit MT5 error categories and sanitized exceptions.
- Added recursive logging redaction for passwords, login values, account IDs, server metadata,
  terminal paths, API keys, secrets, credentials, and tokens.
- Added an M1 startup policy that retains SHADOW as the default and rejects LIVE mode and all
  live-enablement flags.
- Added an optional demo-terminal integration test that is skipped unless explicitly enabled.
- Added a temporary, sanitized, read-only MT5 diagnostic script for terminal troubleshooting.
- Advanced the project package version to `0.2.0` for the accepted M1 milestone.

## Public adapter surface

The public `MT5ReadOnlyClient` exposes exactly:

- `initialize()`
- `health_check()`
- `get_account_info()`
- `get_symbols()`
- `get_symbol_info()`
- `get_tick()`
- `get_candles()`
- `get_positions()`
- `shutdown()`

It exposes no generic vendor-module accessor or dynamic attribute forwarding.

## Files created

- `docs/milestones/M1_PLAN.md`
- `docs/milestones/M1_REPORT.md`
- `scripts/mt5_diagnostic.py`
- `src/ai_trading_team/mt5/backend.py`
- `src/ai_trading_team/mt5/client.py`
- `src/ai_trading_team/mt5/errors.py`
- `src/ai_trading_team/mt5/mappers.py`
- `src/ai_trading_team/mt5/protocols.py`
- `src/ai_trading_team/schemas/mt5.py`
- `tests/__init__.py`
- `tests/fakes/__init__.py`
- `tests/fakes/mt5.py`
- `tests/integration/test_mt5_demo_readonly.py`
- `tests/safety/test_m1_startup_policy.py`
- `tests/safety/test_mt5_readonly_surface.py`
- `tests/unit/test_mt5_backend.py`
- `tests/unit/test_mt5_client.py`
- `tests/unit/test_mt5_errors.py`
- `tests/unit/test_mt5_mappers.py`
- `tests/unit/test_mt5_settings.py`

## Files changed

- `.env.example`
- `.github/workflows/ci.yml`
- `.gitignore`
- `README.md`
- `pyproject.toml`
- `src/ai_trading_team/__main__.py`
- `src/ai_trading_team/__init__.py`
- `src/ai_trading_team/config/__init__.py`
- `src/ai_trading_team/config/settings.py`
- `src/ai_trading_team/config/startup.py`
- `src/ai_trading_team/main.py`
- `src/ai_trading_team/mt5/__init__.py`
- `src/ai_trading_team/schemas/__init__.py`
- `src/ai_trading_team/schemas/common.py`
- `src/ai_trading_team/schemas/enums.py`
- `src/ai_trading_team/utils/logging.py`
- `tests/unit/test_logging.py`

`docs/milestones/M0_REPORT.md` was not changed.

## Final automated verification

Canonical environment: Windows x86-64, CPython 3.12.13.

- `.venv\Scripts\python.exe -m pytest`: 86 passed, 1 skipped in 0.23 seconds.
- `.venv\Scripts\python.exe -m ruff check .`: all checks passed.
- `.venv\Scripts\python.exe -m mypy src tests`: no issues in 47 source files.
- Pinned dependency load test: passed and reported MetaTrader5 5.0.6180.
- Default startup: exited 0 in SHADOW mode.
- LIVE startup: exited 2 with `StartupPolicyError`.
- Read-only surface safety tests: passed.
- Production source scan: no prohibited MT5 terminal-state or trade mutation identifiers found.

The one default skip is the deliberately opt-in demo-terminal integration test. It is excluded
from ordinary and CI runs to prevent implicit access to a local terminal; its separately enabled
acceptance run passed as recorded below.

## Demo-terminal acceptance

- The explicitly enabled M1 demo integration selection completed with **1 passed**.
- MT5 terminal initialization and connection succeeded.
- The safety precondition confirmed that the connected account was a demo account.
- Account information, symbol discovery, broker symbol metadata, current tick data, M15/H1/H4
  completed candles, and existing positions were readable through `MT5ReadOnlyClient`.
- No execution API or terminal-state mutation API was used.
- The M1 terminal acceptance criterion is satisfied.

## Historical troubleshooting context

Before the successful acceptance run, two read-only initialization attempts failed safely with
vendor error `-10005` (IPC timeout). This was an environment-level troubleshooting event and is
no longer an acceptance blocker.

## Non-blocking tooling issue

- A permission warning involving the legacy root `.pytest_cache` directory was observed during
  earlier verification. Pytest now uses `.cache/pytest`; the final suite completed successfully
  without a cache warning. The legacy directory permission is a local tooling issue and does not
  affect application behavior or M1 acceptance.

## Known limitations

- Full `MarketSnapshot` composition and cycle association remain deferred to M2.
- No risk evaluation, position sizing, order creation, order submission, position mutation,
  trading loop, AI/LLM integration, or backtesting behavior exists.
- M1 reads are synchronous because the vendor API is synchronous.

## Recommended next step

Stop at the fully accepted M1 boundary. Begin M2 planning only after explicit approval; M2 should
compose the validated read-only observations into a standardized, cycle-traceable
`MarketSnapshot` without adding AI, risk, execution, or backtesting behavior.
