# M5 Completion Report

Date: 2026-09-11
Status: Fully accepted (provider-neutral core); live-provider acceptance tracked separately

## Baseline preservation

- Started from accepted annotated tag `m4-v0.5.0` on `feat/m5-llm-runtime`.
- Preserved all M0-M4 architecture and safety boundaries.
- Did not change the accepted M0-M4 completion reports.
- Advanced the package version to `0.6.0`.

## Implemented

- Added a provider-neutral `RuntimeRouter` that handles exactly one explicit typed agent
  invocation and never schedules the M4 multi-agent graph.
- Added immutable runtime, capability, prompt, invocation, usage, telemetry, pricing, retry, and
  budget contracts.
- Removed trusted status from the model-generated contract. A model returns only confidence,
  evidence, warnings, invalidations, and its strict role payload; trusted runtime code derives
  `SUCCESS` or `DEGRADED` after complete validation.
- Added canonical role mappings for all nine M4 input/payload/output contracts.
- Added nine minimal, versioned prompt artifacts with SHA-256 content integrity, role binding,
  schema compatibility digests, UTF-8/LF enforcement, and path-containment checks.
- Added deterministic pre-dispatch checks for prompt/schema/runtime/capability/provider/model,
  context/output limits, adapter contract acceptance, and provider-specific live-smoke
  acceptance.
- Added OpenAI Responses, Anthropic Messages, and Google Gemini adapters with vendor SDK imports
  isolated inside matching provider packages. Provider SDK automatic retries are disabled.
- Added strict structured response parsing with no prose extraction or semantic repair. Unknown
  enums, missing/extra fields, invalid JSON, and envelope incompatibility produce sanitized typed
  failures.
- Added bounded `RetryPolicy` with `max_attempts` of one through three total calls. Timeout,
  transient, and rate-limit retries are independently allowed or denied by policy.
- Added normalized token/cost telemetry with explicit reported, estimated, or unavailable state.
  Provider-neutral estimates are labeled `CONSERVATIVE_ESTIMATE`, never exact.
- Added Decimal-only, caller-owned, versioned pricing and deterministic per-call/token/call-count,
  daily, and monthly budget limits.
- Added the reservation lifecycle `RESERVED -> DISPATCHED -> SETTLED`, with `RELEASED` allowed
  only before dispatch and `UNCERTAIN` retained after timeouts or unknown post-dispatch billing.
- Added a SQLite ledger that atomically reserves budget and enforces unique `invocation_id`; a
  duplicate invocation cannot dispatch twice.
- Added optional, provider-specific smoke tests gated by a flag, credential, and explicit model.
- Added M5 settings with runtime disabled by default and all API credentials represented by
  `SecretStr`.
- Added an M5 startup policy that continues to reject LIVE mode and live enablement flags. Normal
  startup makes no provider call.

## Dependency verification

Canonical environment: Windows x86-64, CPython 3.12.13.

- Installed the complete optional provider set successfully.
- `openai==2.54.0`: installed, imported, and Responses method signature validated.
- `anthropic==1.5.0`: installed, imported, and Messages structured-output method signature
  validated.
- `google-genai==1.75.0`: installed, imported, and asynchronous structured-output method
  signature validated.
- All three clients initialized with non-secret dummy values without performing network calls.
- Versions are pinned under the optional `providers` extra; default/core installation does not
  require provider SDKs.

## Provider acceptance status

| Provider | Shared fake adapter contract | Live smoke | Later runtime eligibility |
|---|---:|---:|---:|
| OpenAI | Passed | Not run: no explicit credential/flag/model | Not yet eligible |
| Anthropic | Passed | Not run: no explicit credential/flag/model | Not yet eligible |
| Google Gemini | Passed | Not run: no explicit credential/flag/model | Not yet eligible |

Missing provider credentials do not invalidate the provider-neutral M5 core. A real provider/model
must have a separately validated capability profile and successful live smoke record before the
router accepts it for later runtime use.

## Files created

Configuration and documentation:

- `.gitattributes`
- `config/llm_runtime.example.toml`
- `docs/milestones/M5_PLAN.md`
- `docs/milestones/M5_REPORT.md`

Prompt registry and artifacts:

- `src/ai_trading_team/prompts/__init__.py`
- `src/ai_trading_team/prompts/registry.py`
- `src/ai_trading_team/prompts/artifacts/manifest.toml`
- Nine role prompt Markdown artifacts under `src/ai_trading_team/prompts/artifacts/`

Runtime and storage:

- `src/ai_trading_team/schemas/runtime.py`
- `src/ai_trading_team/runtime/__init__.py`
- `src/ai_trading_team/runtime/budget.py`
- `src/ai_trading_team/runtime/contracts.py`
- `src/ai_trading_team/runtime/errors.py`
- `src/ai_trading_team/runtime/protocols.py`
- `src/ai_trading_team/runtime/router.py`
- `src/ai_trading_team/runtime/validation.py`
- `src/ai_trading_team/runtime/providers/base.py`
- OpenAI, Anthropic, and Gemini provider package markers and adapters
- `src/ai_trading_team/storage/ai_budget.py`

Tests:

- `tests/fakes/runtime.py`
- `tests/integration/test_llm_provider_smoke.py`
- `tests/safety/test_m5_runtime_boundaries.py`
- `tests/safety/test_m5_startup_policy.py`
- `tests/unit/test_ai_budget.py`
- `tests/unit/test_llm_runtime_settings.py`
- `tests/unit/test_prompt_registry.py`
- `tests/unit/test_provider_adapter_contracts.py`
- `tests/unit/test_provider_errors.py`
- `tests/unit/test_runtime_router.py`
- `tests/unit/test_runtime_schemas.py`

## Files changed

- `.env.example`
- `README.md`
- `pyproject.toml`
- `src/ai_trading_team/__init__.py`
- `src/ai_trading_team/agents/protocols.py`
- `src/ai_trading_team/config/__init__.py`
- `src/ai_trading_team/config/settings.py`
- `src/ai_trading_team/config/startup.py`
- `src/ai_trading_team/main.py`
- `src/ai_trading_team/schemas/__init__.py`
- `src/ai_trading_team/schemas/agents.py`
- `src/ai_trading_team/schemas/common.py`
- `src/ai_trading_team/schemas/enums.py`
- `src/ai_trading_team/storage/__init__.py`

## Final verification

- Full default suite: **300 passed, 5 skipped**. The skips are two explicit MT5 demo tests and
  three explicit provider smoke cases.
- Ruff: **all checks passed**.
- Strict mypy: **no issues found in 127 source files**.
- All M0-M5 safety tests: **48 passed**.
- Fake-provider end-to-end typed invocation acceptance: **1 passed**.
- Common OpenAI/Anthropic/Gemini fake adapter contract suite: **passed for all three adapters**.
- Explicit provider smoke selection: **3 skipped** because no credential, smoke flag, or model was
  configured; no external API call occurred.
- Default startup: exited successfully in SHADOW mode and confirmed no trading components active.
- LIVE startup: rejected with `StartupPolicyError`.
- Production scan found no order submission, symbol selection, order/position mutation, MT5 or
  Risk Engine access from agents/runtime, multi-agent scheduler, trading loop, or backtesting
  implementation.

## Safety confirmation

- Model-generated bodies cannot set trusted runtime status or carry runtime/budget controls.
- Confidence remains descriptive and does not enter M3 risk or position-sizing contracts.
- Credentials stay as `SecretStr`, are resolved only inside provider adapters, and never enter
  prompts, snapshots, outputs, telemetry, or logs.
- Capability/schema/budget failures occur before generation dispatch.
- No automatic provider fallback exists.
- A timeout never implies the provider did not charge; the reservation becomes `UNCERTAIN`.
- Prompt content, capability profiles, runtime profiles, retry policy, and budget policy are
  immutable and cannot be modified by model output.
- LIVE remains prohibited.

## Known limitations

- M5 supports one explicit agent invocation only. The M4 multi-agent decision graph remains
  declarative and unscheduled.
- No real provider/model has live-smoke acceptance in this environment, so none is eligible for a
  later active runtime yet.
- Default token estimation is deliberately upper-biased and may over-reserve budget. A validated
  provider tokenizer may replace it without changing the token-provenance contract.
- Pricing and capability facts are caller-owned and time-sensitive; M5 embeds neither vendor
  prices nor permanent role-to-model assignments.
- The SQLite ledger tracks AI budget reservations only; a broader decision/audit repository is
  deferred.
- The accepted broker/FX timestamp-semantics compatibility issue remains unchanged. M5 neither
  consumes broker data directly nor changes M2 timestamp handling.
- No AI strategy logic, orchestration runtime, candle scheduler, risk invocation, MT5 access,
  execution, position mutation, trading loop, or backtesting exists.

## Recommended next step

Stop at M5. Do not begin M6 until explicitly approved. Before any provider is used by a later
runtime, run and record that provider/model's opt-in smoke acceptance with an explicitly
configured credential and model identifier.
