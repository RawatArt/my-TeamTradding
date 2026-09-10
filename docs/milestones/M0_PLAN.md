# M0 Plan

## Goal

Establish a typed, testable, non-trading Python architecture that satisfies the M0 definition
of done without implementing any later milestone.

## Files and modules

- Python 3.12+ packaging and verification configuration in `pyproject.toml`.
- Safe environment template and repository ignore rules.
- Typed application and risk-constitution settings.
- A replaceable M0 startup policy that prohibits LIVE operation.
- Separate application-mode and risk-state enums.
- Minimal traceable schemas for market quotes, agent output, proposals, chief decisions, and risk
  evaluation results.
- UTC and secret-redacting structured logging utilities.
- Unit and M0 safety tests.
- README and CI workflow.

## Safety implications

- No connector, order API, trading loop, risk calculation, position sizing, LLM call, or backtest
  behavior will be implemented.
- SHADOW is the default application mode.
- The M0 startup policy rejects LIVE and all live-enablement flags while leaving LIVE in the core
  enum for a future, explicitly reviewed policy.
- Decimal values are never converted to binary floats by model validation or JSON round trips.
- Cycle-bound records always carry `cycle_id`, `schema_version`, and a UTC timestamp.

## Tests

- Configuration defaults and invariant validation.
- M0 LIVE-mode prohibition.
- Enum separation and serialization.
- Traceability and timezone validation.
- Decimal preservation through Python and JSON boundaries.
- Quote, confidence, and proposal validation.
- Structured-log context and credential redaction.

