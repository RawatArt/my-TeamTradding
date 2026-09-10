# M1 Plan

## Goal

Implement strictly read-only MetaTrader 5 connectivity on canonical CPython 3.12 for Windows.
Convert all vendor data into immutable, versioned application-owned models and expose no terminal
state mutation or trading operation.

## Baseline

- Re-run all M0 tests, Ruff, and strict mypy.
- Preserve M0 in local Git commit `3bc1c9d` with annotated tag `m0-v0.1.0`.
- Isolate M1 on branch `feat/m1-mt5-readonly`.

## Dependency

- Pin `MetaTrader5==5.0.6180` on Windows.
- Verify installation and import using CPython 3.12 x86-64 before implementation.
- Keep CI on Windows with Python 3.12; terminal integration remains opt-in.
- Add no direct data-frame, AI, execution, or backtesting dependency.

## Public interface

`MT5ReadOnlyClient` exposes only:

- `initialize()`
- `health_check()`
- `get_account_info()`
- `get_symbols(pattern=None)`
- `get_symbol_info(symbol)`
- `get_tick(symbol)`
- `get_candles(symbol, timeframe, count, include_incomplete=False)`
- `get_positions(symbol=None)`
- `shutdown()`

Explicit credentials are used internally during initialization. The client never changes symbol
selection. Candle counts must be between 1 and 5,000; the incomplete current bar is excluded by
default.

## Models

- Terminal health
- Account and margin information
- Symbol discovery summary
- Broker symbol metadata
- Current tick
- M15/H1/H4 candle
- Existing open position

All vendor objects are mapped immediately. Financial values use `Decimal`; timestamps are aware
UTC. M1 observations carry `schema_version` and retrieval time. No decision cycle is fabricated;
M2 will associate observations with a required `cycle_id` in `MarketSnapshot`.

## Errors and safety

- Use structured categories for dependency, lifecycle, terminal, authentication, account,
  symbol, tick, candle, position, invalid-request, and mapping failures.
- Treat `None` as failure except that an empty positions tuple is a valid result.
- Keep password as `SecretStr`; redact password, login, server, account ID, and terminal path.
- Do not expose the raw MetaTrader5 module or vendor records.
- Do not call any symbol-selection, order, position-modification, or execution operation.
- Continue to reject LIVE through the M1 startup policy.

## Tests

- Fake-backed lifecycle, failure, mapping, timestamp, Decimal, filter, candle, and position tests.
- Safety inspection of the exact public method allowlist and production source.
- Default-skipped integration test requiring Windows, explicit opt-in, configured symbol, and a
  connected demo terminal.
- Full M0 regression suite, Ruff, and strict mypy.

## Acceptance

- Pinned dependency imports on Python 3.12.
- All requested reads return typed models and no raw vendor objects.
- Public surface contains only the approved read methods and lifecycle.
- No terminal-state or trading mutation exists.
- Automated checks pass.
- Demo integration passes when a usable demo terminal is available; otherwise the limitation is
  reported without claiming terminal acceptance.
