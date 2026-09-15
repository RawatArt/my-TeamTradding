# M11 Real-DEMO One-Shot Acceptance Runbook

Status: implementation ready; real broker acceptance remains pending.

This procedure is limited to one protected initial DEMO market order. It never enables a
continuous runtime or LIVE trading. A resulting position becomes manual operator custody; the
application provides no automatic close, modification, trailing stop, scale-in, or recovery
trade.

## Preconditions

- Use the accepted Windows Python 3.12 environment and already-bound MT5 DEMO account.
- Keep `APP_MODE=DEMO`; LIVE remains rejected.
- Use one exact currently valid candidate, qualification generation, account/environment
  acceptance, execution policy, ACTIVE risk baseline, original M11 approval, and ENABLED control
  event in the local SQLite repositories.
- Copy `config/m11_real_demo_acceptance.example.toml` to an ignored local path and replace every
  placeholder. Do not commit credentials or local acceptance artifacts.
- The configured symbol must already be selected. The procedure never calls `symbol_select`.

## Phase 1: readiness only

```powershell
$env:APP_MODE="DEMO"
$env:DEMO_EXECUTION__ENABLED="false"
$env:RUN_M11_REAL_DEMO_EXECUTION="false"
.venv\Scripts\python.exe scripts\m11_real_demo_acceptance.py --config config\m11_real_demo_acceptance.local.toml --readiness-only
```

This phase performs read-only terminal, account, symbol, tick, candle, position, timestamp,
qualification, policy, and control-generation checks. It writes a sanitized, finite-TTL
readiness artifact using exclusive creation. It performs zero execution claims, zero
`order_check` operations, and zero submissions. It does not consume the candidate or readiness.
The static DEMO execution setting and mutation gate intentionally remain disabled for this phase.

Review the readiness digest and expiry. Create a new, immutable mutation approval that binds the
exact readiness run/generation/digest/timestamps, candidate/generation, account/environment,
policy, ENABLED control event, and `submission_limit = 1`. Expired readiness cannot be renewed;
run Phase 1 again with a new run and generation, then create a new approval.

## Phase 2: execute once (do not run without separate approval)

```powershell
$env:APP_MODE="DEMO"
$env:DEMO_EXECUTION__ENABLED="true"
$env:RUN_M11_REAL_DEMO_EXECUTION="true"
.venv\Scripts\python.exe scripts\m11_real_demo_acceptance.py --config config\m11_real_demo_acceptance.local.toml --execute-once
```

The command consumes readiness atomically before delegating to the accepted M11 sequence:
claim, `order_check`, FinalDispatchGuard, durable DISPATCHING, at most one submission, normalized
result, and composite reconciliation. Ambiguous dispatch is reconciliation-only and is never
resent. Clean confirmed/rejected completion moves control to PAUSED; uncertainty or mismatch
moves it to HALTED. Neither state automatically returns to ENABLED.

`REAL_DEMO_ACCEPTED` can be sealed only after CONFIRMED execution and CONFIRMED composite
reconciliation prove one compatible position, exact volume/SL/TP, policy-compliant fill, and no
duplicate candidate. A broker return code or submission acceptance alone is insufficient.

## Secrets and audit

Only safe account/environment fingerprints and sanitized typed records are written. Credentials,
raw MT5 objects, and raw broker responses must never enter the artifacts. The vendor-boundary
audit records both `Decimal.from_float(value)` (exact binary transport) and
`Decimal(str(value))` (display/API-normalized reconstruction); the latter is not proof of exact
binary representation.
