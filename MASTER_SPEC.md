# AI Trading Team — Master Specification

Version: 0.1.0
Status: Development
Environment: Local Windows -> Windows VPS
Trading Platform: MetaTrader 5
Primary Language: Python
Initial Mode: DEMO / SHADOW MODE ONLY

---

# 1. Project Mission

Build a production-oriented multi-agent AI trading system in which
specialized AI agents collaborate as a professional trading team.

The system's primary objective is:

MAXIMIZE LONG-TERM RISK-ADJUSTED CAPITAL GROWTH
WHILE PRIORITIZING CAPITAL SURVIVAL.

The system must NOT optimize for:

- maximum number of trades
- maximum leverage
- maximum win rate alone
- short-term account doubling
- martingale-style recovery
- revenge trading
- uncontrolled AI autonomy

Capital preservation is the first priority.

---

# 2. Core Principle

AI agents may:

- analyze
- reason
- debate
- propose
- criticize
- rank trade opportunities
- explain decisions
- recommend BUY / SELL / HOLD

AI agents may NOT:

- calculate final executable lot size
- override risk limits
- execute orders directly
- disable stop loss
- modify account-level risk rules
- bypass the Risk Engine
- change a live strategy automatically

Only deterministic code may control:

- position sizing
- maximum account risk
- daily loss limits
- drawdown rules
- spread limits
- stop loss validation
- order duplication prevention
- trade execution

---

# 3. Initial Trading Challenge

Initial virtual capital:

$50 DEMO

Primary objective:

Grow the account as much as possible
without violating survival constraints.

This is an engineering/research challenge,
not a guarantee of profit.

---

# 4. Initial Risk Constitution

The Risk Constitution is immutable during live execution.

Initial defaults:

starting_balance: 50 USD

risk_per_trade:
    normal: 0.50%
    minimum: 0.25%
    maximum: 1.00%

maximum_open_positions: 1

maximum_daily_loss: 3%

maximum_drawdown_warning: 5%

maximum_drawdown_safe_mode: 8%

maximum_drawdown_stop: 15%

minimum_risk_reward: 1.50

martingale: forbidden

averaging_down: forbidden

revenge_trading: forbidden

stop_loss_required: true

take_profit:
    optional but recommended

AI_override_risk_engine: forbidden

---

# 5. Risk State Machine

The Risk Engine must maintain explicit account states.

NORMAL

Risk allowed:
0.50%

Conditions:
Drawdown < 5%

---

CAUTION

Condition:
Drawdown >= 5%

Risk:
0.25%

System may reject lower-quality setups.

---

SAFE_MODE

Condition:
Drawdown >= 8%

Actions:

- reduce risk
- restrict strategy set
- disable aggressive entries
- require higher confidence
- require stronger confluence

---

HALTED

Condition:

Drawdown >= 15%

OR

Daily loss limit exceeded

OR

System safety violation detected

Actions:

- no new positions
- preserve existing SL
- log incident
- require manual review

AI cannot override HALTED state.

---

# 6. High-Level Architecture

Market
    |
    v
MetaTrader 5
    |
    v
Market Data Layer
    |
    v
Feature / Indicator Engine
    |
    +-----------------------------+
    |                             |
    v                             v
Technical Agents             Quant Agents
    |                             |
    +--------------+--------------+
                   |
                   v
              Debate Layer
                   |
                   v
              Skeptic Agent
                   |
                   v
              Chief Trader
                   |
                   v
        Deterministic Risk Engine
                   |
          APPROVE / REJECT
                   |
                   v
           Execution Engine
                   |
                   v
                 MT5
                   |
                   v
            Trade Logger
                   |
                   v
        Performance Analytics

---

# 7. AI Trading Team

The initial team consists of:

1. Market Context Agent
2. Trend Analyst
3. Price Action Analyst
4. Entry Analyst
5. Quant Researcher
6. Senior Quant Developer
7. Skeptic / Devil's Advocate
8. Chief Trader
9. Performance Reviewer

Deterministic components:

10. Risk Engine
11. Position Sizing Engine
12. Execution Engine
13. Market Data Engine
14. Indicator Engine
15. Logging / Audit Engine

---

# 8. Agent Responsibilities

## 8.1 Market Context Agent

Purpose:

Describe the current market environment.

Inputs:

- multi-timeframe OHLCV
- spread
- ATR
- ADX
- moving averages
- volatility
- session
- recent range
- market structure

Outputs:

- TREND
- RANGE
- HIGH_VOLATILITY
- LOW_VOLATILITY
- BREAKOUT
- UNCERTAIN

Must not create orders.

---

## 8.2 Trend Analyst

Purpose:

Determine higher-timeframe directional bias.

Primary timeframes:

H1
H4

Secondary:

M15

Responsibilities:

- trend direction
- trend strength
- higher highs / lower lows
- moving-average structure
- momentum confirmation
- trend invalidation level

Output example:

{
  "bias": "BULLISH",
  "confidence": 0.78,
  "evidence": [],
  "invalidations": []
}

---

## 8.3 Price Action Analyst

Purpose:

Analyze price structure.

Responsibilities:

- support/resistance
- breakout
- fake breakout
- pullback
- retest
- liquidity sweep
- consolidation
- range boundaries
- momentum candles
- rejection candles

Must distinguish:

FACT

from

INTERPRETATION

---

## 8.4 Entry Analyst

Purpose:

Find high-quality entries.

Primary timeframe:

M15

Optional:

M5

Responsibilities:

- entry zone
- invalidation
- SL proposal
- TP proposal
- entry quality
- timing

Possible decisions:

ENTER_NOW
WAIT_PULLBACK
WAIT_BREAKOUT
NO_ENTRY

---

# 9. Quant Researcher

Role:

Professional quantitative strategy researcher.

Purpose:

Convert qualitative trading ideas into testable hypotheses.

Example:

Bad hypothesis:

"BTC looks bullish."

Good hypothesis:

"When H1 EMA50 > EMA200,
ADX > 20,
and M15 RSI crosses above 50
after a pullback,
does long expectancy become positive?"

Responsibilities:

- hypothesis formulation
- market regime research
- feature research
- strategy research
- regime segmentation
- statistical analysis

Must avoid:

- cherry picking
- hindsight bias
- look-ahead bias
- survivorship bias
- optimization on test data

---

# 10. Senior Quant Developer

Role:

Senior Quantitative Developer / Trading Systems Engineer.

This is one of the most important system roles.

Responsibilities:

- translate strategy logic into deterministic code
- implement indicators
- implement backtests
- implement statistical validation
- test data integrity
- validate trade assumptions
- validate execution assumptions
- analyze slippage
- calculate expectancy
- calculate profit factor
- calculate drawdown
- calculate R-multiple
- calculate Sharpe-like statistics
- create reproducible experiments
- identify overfitting
- detect data leakage

The Senior Quant Developer must challenge
unsupported statements from other agents.

Example:

Trend Agent:

"This setup performs well."

Quant Developer:

"Show evidence."

Required evidence may include:

trade_count
win_rate
profit_factor
expectancy
maximum_drawdown
average_R
sample_period
out_of_sample_result

---

# 11. Skeptic Agent

Role:

Devil's Advocate.

Purpose:

Attempt to DISPROVE the proposed trade.

This agent should actively search for:

- conflicting timeframe structure
- nearby resistance/support
- poor RR
- abnormal volatility
- weak momentum
- fake breakout risk
- extended price
- poor liquidity
- spread expansion
- contradictory evidence

The Skeptic must not agree merely because
other agents agree.

Output:

APPROVE
CAUTION
REJECT

---

# 12. Chief Trader

Role:

Head of the AI trading desk.

The Chief Trader receives outputs from:

- Market Context
- Trend Analyst
- Price Action
- Entry Analyst
- Quant Research
- Quant Developer
- Skeptic

The Chief Trader may output only:

BUY
SELL
HOLD

HOLD must be considered a high-quality valid decision.

The Chief Trader must NOT:

- calculate final lot size
- bypass Risk Engine
- force trade execution
- increase risk because confidence is high

---

# 13. Deterministic Risk Engine

The Risk Engine has higher authority than all AI agents.

Responsibilities:

- account balance
- equity
- open risk
- position sizing
- drawdown
- daily loss
- minimum RR
- spread
- maximum positions
- stop loss validation
- duplicate trade protection
- symbol trading availability

Example:

Chief Trader:

BUY
confidence = 0.91

Risk Engine:

REJECT

Reason:

RR = 1.2
Required RR = 1.5

Final result:

NO TRADE

Risk Engine always wins.

---

# 14. Position Size Calculation

Position sizing must be calculated
from stop-loss distance and account risk.

Never determine lot size directly from:

- AI confidence
- desired profit
- previous loss
- emotional recovery
- account growth target

Required relationship:

Risk Amount =
Account Equity * Risk %

Position Size =
Risk Amount / Stop Loss Monetary Distance

Broker specifications must be considered:

- contract size
- volume minimum
- volume maximum
- volume step
- tick size
- tick value

If broker minimum size causes risk to exceed
allowed risk:

REJECT TRADE.

---

# 15. Execution Engine

Execution Engine communicates with MT5.

Responsibilities:

- validate symbol
- validate market status
- validate latest price
- validate spread
- validate SL
- validate TP
- validate position size
- generate unique trade ID
- prevent duplicate execution
- submit order
- confirm broker response
- record broker order ID

Execution must be idempotent.

Calling the same trade command twice
must not generate duplicate orders.

---

# 16. Data Model

Every decision cycle must produce a DecisionRecord.

Required fields:

timestamp
cycle_id
symbol
timeframe
market_snapshot
indicator_snapshot
agent_outputs
chief_decision
risk_engine_result
execution_result

Trade record:

trade_id
symbol
side
entry
stop_loss
take_profit
position_size
risk_percent
risk_amount
open_time
close_time
exit_price
pnl
R_multiple
MFE
MAE
exit_reason

---

# 17. Structured Agent Output

Agents must return machine-readable structured output.

Avoid free-form output whenever possible.

Example:

{
  "agent": "trend_analyst",
  "version": "1.0",
  "timestamp": "...",
  "bias": "BULLISH",
  "confidence": 0.76,
  "evidence": [
    {
      "type": "EMA_STRUCTURE",
      "description": "EMA50 above EMA200"
    }
  ],
  "invalidations": [
    "H1 close below ..."
  ]
}

Invalid JSON must trigger:

AGENT_OUTPUT_INVALID

and no trade may be executed.

---

# 18. Confidence Rules

AI confidence must NOT be treated as true probability.

Confidence is descriptive only.

Confidence may be used as a filter
after empirical calibration.

Example:

Do not assume:

confidence 0.80
=
80% probability of winning.

Performance Reviewer must compare:

confidence bins

against

actual outcomes.

---

# 19. Initial Instruments

Do not hard-code BTCUSD.

The symbol must be configurable.

Example:

TRADING_SYMBOL=BTCUSD

Broker-specific symbols may differ:

BTCUSD
BTCUSDm
BTCUSD.a
BTCUSD#

The system must discover symbol properties
from MT5.

---

# 20. Initial Timeframes

Recommended initial configuration:

Context:

H4
H1

Entry:

M15

Optional future:

M5

The first production experiment should use
one symbol and one primary entry timeframe.

Avoid multi-market expansion in V1.

---

# 21. Decision Timing

Do not call AI on every tick.

Initial policy:

Run one decision cycle when
a new M15 candle closes.

Reason:

- lower API cost
- lower noise
- better reproducibility
- easier debugging
- easier backtesting

Ticks may still be used for:

- order execution
- SL/TP monitoring
- spread validation

---

# 22. Agent Communication Protocol

Agents do not freely chat indefinitely.

Communication is orchestrated.

Cycle:

Market Snapshot

-> Parallel Analysis

Trend
Price Action
Market Context

-> Entry Proposal

-> Quant Evaluation

-> Skeptic Review

-> Chief Trader

-> Risk Engine

-> Execution

This prevents:

- infinite debate
- excessive token cost
- uncontrolled agent behavior

---

# 23. Debate Rules

Agents may disagree.

Disagreement is expected.

Consensus is NOT required.

The Chief Trader evaluates evidence quality.

Example:

Trend:
BUY 80%

Price Action:
BUY 68%

Entry:
WAIT

Skeptic:
REJECT

Result may legitimately be:

HOLD

---

# 24. Memory

Two forms of memory exist.

## Short-term memory

Current:

- candles
- active positions
- latest analyses
- current regime

## Long-term analytical memory

Historical:

- trade outcomes
- strategy performance
- agent performance
- setup performance
- confidence calibration

Agents may read analytical memory.

Agents may NOT directly rewrite trading rules.

---

# 25. Performance Reviewer

Runs periodically.

Not on every candle.

Example interval:

every 20 closed trades

or

daily review

Metrics:

total trades
win rate
loss rate
profit factor
expectancy
average R
max drawdown
average win
average loss
consecutive losses
MFE
MAE

Agent-level metrics:

trend_agent_accuracy
price_action_accuracy
entry_agent_accuracy
skeptic_value
chief_trader_accuracy

---

# 26. Strategy Promotion Pipeline

AI cannot change live strategy automatically.

Any proposed strategy change follows:

IDEA

-> RESEARCH

-> IMPLEMENTATION

-> BACKTEST

-> WALK-FORWARD TEST

-> OUT-OF-SAMPLE TEST

-> PAPER / SHADOW MODE

-> DEMO FORWARD TEST

-> HUMAN APPROVAL

-> PRODUCTION

Skipping stages is prohibited.

---

# 27. Backtesting Requirements

Backtesting must include:

- trading fees
- spread
- slippage assumptions
- correct candle chronology
- correct signal timing
- no future data
- broker contract information where applicable

Must separate:

TRAIN / DEVELOPMENT DATA

from

OUT-OF-SAMPLE TEST DATA

---

# 28. Minimum Strategy Evaluation

A strategy should not be promoted because
of win rate alone.

Evaluate:

trade_count
win_rate
profit_factor
expectancy
max_drawdown
average_R
Sharpe-like ratio
worst_loss_streak
market_regime_performance

Initial research target:

Trades >= 300 preferred.

This is a research threshold,
not a guarantee of validity.

---

# 29. Shadow Mode

Before Demo Auto Trading:

SHADOW MODE must be implemented.

In Shadow Mode:

Agents analyze normally.

Chief Trader makes decisions.

Risk Engine evaluates trades.

BUT

Execution Engine does not send orders.

System records:

"WOULD_BUY"
"WOULD_SELL"
"WOULD_HOLD"

Hypothetical outcomes can be studied.

---

# 30. Demo Mode

After Shadow Mode passes:

Enable DEMO_AUTOTRADE.

All real execution code must first be tested
with a demo account.

Demo mode must visibly show:

ENVIRONMENT=DEMO

---

# 31. Live Trading Protection

Live trading must default to disabled.

Example:

ENABLE_LIVE_TRADING=false

Live environment requires explicit manual configuration.

Never automatically switch from Demo to Live.

---

# 32. Fail-Safe Philosophy

When uncertain:

DO NOTHING.

Examples:

MT5 disconnected
-> no trade

GPT timeout
-> no trade

Invalid JSON
-> no trade

Missing market data
-> no trade

Risk calculation failure
-> no trade

Broker specification unavailable
-> no trade

Unknown error
-> no trade

Safety > availability.

---

# 33. API Failure Handling

AI API call must support:

- timeout
- retry
- exponential backoff
- maximum retries
- fallback to HOLD

Example:

retry count: 2

After failure:

decision = HOLD
reason = AGENT_UNAVAILABLE

---

# 34. Logging Requirements

Log every:

- application startup
- MT5 connection
- market data request
- candle cycle
- agent request
- agent response
- risk decision
- order request
- broker response
- error
- shutdown

Never log:

API keys
passwords
account passwords
sensitive credentials

---

# 35. Security

Secrets must use environment variables.

.env

Examples:

OPENAI_API_KEY
MT5_LOGIN
MT5_PASSWORD
MT5_SERVER

.env must be added to .gitignore.

Provide:

.env.example

Never commit real secrets.

---

# 36. Project Structure

ai-trading-team/

    README.md
    MASTER_SPEC.md
    AGENTS.md

    pyproject.toml
    .env.example
    .gitignore

    src/

        main.py

        config/
            settings.py

        mt5/
            connection.py
            symbols.py
            market_data.py

        market/
            indicators.py
            features.py
            regime.py

        agents/
            base.py
            market_context.py
            trend.py
            price_action.py
            entry.py
            quant_researcher.py
            quant_developer.py
            skeptic.py
            chief_trader.py
            performance.py

        orchestration/
            orchestrator.py
            decision_cycle.py

        risk/
            risk_engine.py
            position_sizing.py
            drawdown.py

        execution/
            order_manager.py
            position_manager.py

        backtest/
            engine.py
            metrics.py

        storage/
            models.py
            repository.py

        schemas/
            market.py
            agents.py
            decisions.py
            trades.py

        utils/
            logger.py
            time.py

    tests/

        unit/
        integration/
        safety/

    data/

    logs/

---

# 37. Technology Stack

Primary:

Python 3.12+

Trading:

MetaTrader5 Python package

Validation:

Pydantic

Data:

pandas
numpy

Testing:

pytest

Configuration:

pydantic-settings
python-dotenv

Logging:

Python structured logging

Database V1:

SQLite

Future production:

PostgreSQL

AI:

OpenAI API

---

# 38. Development Modes

The application must support:

BACKTEST

SHADOW

DEMO

LIVE

LIVE must be disabled by default.

Example:

APP_MODE=SHADOW

---

# 39. Testing Strategy

Three testing layers.

UNIT TESTS

Examples:

position sizing
RR calculation
drawdown calculation
indicator functions

INTEGRATION TESTS

Examples:

MT5 connectivity
market data retrieval
agent orchestration
database storage

SAFETY TESTS

Examples:

AI attempts risk override
invalid JSON
negative stop distance
duplicate order
excessive lot
drawdown exceeded

Safety tests are mandatory.

---

# 40. Mandatory Safety Tests

At minimum create tests for:

1.

Chief Trader says BUY
but Risk Engine rejects.

Expected:
NO ORDER

2.

Risk > max risk.

Expected:
REJECT

3.

No stop loss.

Expected:
REJECT

4.

Max open positions reached.

Expected:
REJECT

5.

Daily loss limit reached.

Expected:
HALTED

6.

Maximum drawdown reached.

Expected:
HALTED

7.

Agent returns malformed JSON.

Expected:
HOLD

8.

MT5 unavailable.

Expected:
NO ORDER

9.

Duplicate trade ID.

Expected:
NO DUPLICATE ORDER

10.

Broker minimum volume exceeds risk.

Expected:
REJECT

---

# 41. Observability

Console dashboard should show:

APP MODE
MT5 connection
symbol
latest candle
account balance
equity
drawdown
open positions
agent decision
risk decision

Example:

AI TRADING TEAM

MODE: SHADOW

BTCUSD M15

Trend:
BULLISH 78%

Price Action:
NEUTRAL 55%

Skeptic:
CAUTION

Chief:
HOLD

Risk:
N/A

Balance:
$50.00

Drawdown:
0.00%

---

# 42. Definition of Done — M0

Architecture complete.

Required:

MASTER_SPEC.md
AGENTS.md
README.md
project structure
configuration system
test framework

No trading implementation required.

---

# 43. Definition of Done — M1

Python successfully connects to MT5.

Must read:

account info
balance
equity
symbol
bid
ask
open positions
M15 candles
H1 candles
H4 candles

No trading.

---

# 44. Definition of Done — M2

Market Data Engine complete.

Must produce standardized MarketSnapshot.

Tests required.

---

# 45. Definition of Done — M3

Risk Engine complete.

All safety tests pass.

Still no AI execution.

---

# 46. Definition of Done — M4

Agent framework operational.

Create initial:

Trend Agent
Price Action Agent
Skeptic Agent
Chief Trader

Structured output mandatory.

---

# 47. Definition of Done — M5

Shadow Trading operational.

System runs automatically on new M15 candle.

No orders sent.

Every decision logged.

---

# 48. Definition of Done — M6

Demo Trading operational.

Orders may be sent only to verified demo account.

Every trade passes deterministic Risk Engine.

---

# 49. Definition of Done — M7

Quant research and backtest framework complete.

Historical strategy evaluation available.

---

# 50. Definition of Done — M8

Performance analytics operational.

Generate:

Return
Win Rate
Profit Factor
Expectancy
Average R
Max Drawdown
Trade Count

---

# 51. Deployment

Only after local development is stable:

Local Windows

-> Windows VPS

VPS runs:

MT5
Python Trading Application

Remote access:

RDP

The system must recover gracefully
after process restart.

---

# 52. Non-Goals for V1

Do NOT build yet:

multi-exchange arbitrage
high-frequency trading
reinforcement learning
automatic strategy mutation
copy trading
social sentiment
complex macro/news feeds
multi-account management
mobile app
custom web dashboard

Keep V1 focused.

---

# 53. Coding Philosophy

Correctness > cleverness

Safety > speed

Explicit > implicit

Testable > magical

Deterministic rules > AI guesses

Evidence > confidence

HOLD > bad trade

Capital survival > aggressive return

---

# END MASTER SPECIFICATION