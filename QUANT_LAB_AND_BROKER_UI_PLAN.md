# Quant Lab And Broker UI Plan

This plan describes how to add an optional quant-style strategy tester and how to make the app feel cleaner, denser, and closer to a modern stock broker or research terminal.

The goal is not to turn the app into an unsafe code runner. The goal is to let users test custom strategy logic inside controlled boundaries while keeping the main experience simple for beginners.

## Product Goals

- Add an advanced `Quant Lab` workflow for custom strategy testing.
- Keep the existing beginner workflows intact and approachable.
- Make the app feel like a professional investing workstation: calm, dense, readable, and trustworthy.
- Keep every result explainable with assumptions, data source, benchmark, fees, and risk context.
- Make risky or advanced tools opt-in instead of part of the default path.

## User Experience Shape

The app should have two levels of use:

| Level | Audience | Experience |
| --- | --- | --- |
| Simple Mode | Beginner investors and learners | Presets, guided scenarios, tutorial text, fewer controls |
| Advanced Mode | Backtesters and quant learners | Quant Lab, parameter sweeps, code templates, risk controls |

The `Quant Lab` should be visible only when advanced tools are enabled, or shown as an optional workflow with clear safety copy.

## Quant Lab V1

### Scope

The first version should let users write a small strategy function that receives prepared market data and returns buy/sell signals. The app handles everything else: data loading, indicator calculation, portfolio simulation, benchmark comparison, charting, and reporting.

Recommended first strategy API:

```python
def strategy(data):
    buy = data["rsi"] < 30
    sell = data["rsi"] > 70
    return buy, sell
```

The user should not have to write portfolio accounting, order execution, fee logic, or chart code.

### User Flow

1. User enables `Advanced Mode`.
2. User opens `Quant Lab`.
3. User chooses ticker, date range, data source, interval, and starting capital.
4. User picks a template or writes strategy logic.
5. User clicks `Validate`.
6. App checks syntax, required outputs, signal shape, and blocked operations.
7. User clicks `Run Simulation`.
8. App shows equity curve, benchmark comparison, metrics, trade log, and explanation.

### Strategy Templates

Add starter templates so users do not begin from a blank editor:

- RSI mean reversion
- SMA crossover
- MACD trend following
- Bollinger Band bounce
- Breakout above rolling high
- Buy and hold baseline
- Multi-stock momentum rotation

Each template should include short comments explaining only the strategy logic, not basic Python syntax.

### Safety Model

Raw Python execution is the biggest risk. V1 should avoid unrestricted execution.

Required guardrails:

- Execute strategy code in a restricted namespace.
- Allow only approved builtins, if any are needed.
- Block imports by default.
- Block filesystem access.
- Block network access.
- Block subprocess access.
- Block environment access.
- Block reflection helpers like `eval`, `exec`, `open`, `compile`, and `__import__`.
- Add an execution timeout.
- Limit the rows and symbols processed during validation.
- Catch errors and show friendly messages.

Recommended V1 approach:

- Parse the submitted code with Python `ast`.
- Reject disallowed nodes and names before execution.
- Execute only a single user-defined `strategy(data)` function.
- Pass a copied DataFrame or dictionary of Series into the function.
- Require the function to return either:
  - `(buy, sell)`
  - a DataFrame with `buy` and `sell` columns
  - a Series named `position`

V1 should prefer simple signal generation over complex order simulation. The existing app should remain responsible for execution rules.

### Validation Rules

Before a simulation runs, check:

- Strategy function exists.
- Strategy returns valid buy/sell signals or positions.
- Output length matches the input data.
- Output contains no null-only signal columns.
- Buy and sell are boolean or convertible to boolean.
- Strategy produces at least one signal, or clearly explains that no trades were generated.
- Date range has enough rows for selected indicators.
- Data source is real, partial, or demo, with a visible label.

### Quant Lab Results

Show the same professional result structure every time:

- Equity curve vs buy-and-hold
- Optional benchmark comparison, default `SPY`
- Total return
- Annualized return
- Volatility
- Sharpe ratio
- Max drawdown
- Calmar ratio
- Win rate
- Trade count
- Average trade return
- Fees paid
- Longest drawdown duration
- Monthly returns heatmap
- Trade log
- Plain-English result explanation

### Plain-English Explanation

After every run, include a concise explainer:

- Whether the strategy beat buy-and-hold.
- Whether the return was worth the drawdown.
- Whether there were enough trades to trust the result.
- Whether results may depend too much on one market period.
- Whether fees materially affected performance.
- Whether demo or partial data was used.

Example:

```text
This strategy outperformed buy-and-hold, but it did so with a larger drawdown.
The trade sample is small, so treat the result as exploratory rather than reliable.
Most gains came from two trades, which means the strategy may be fragile.
```

## Quant Lab V2

After V1 is stable, add tools that make the feature feel more like a real quant workbench.

### Parameter Sweeps

Let users test ranges of parameters:

- RSI period
- RSI buy threshold
- RSI sell threshold
- Fast moving average
- Slow moving average
- Bollinger window
- Bollinger standard deviation
- Stop loss
- Take profit

Outputs:

- Leaderboard table
- Heatmap
- Best parameter set
- Robustness warning when only one narrow setting works
- Overfitting warning when in-sample performance is much better than out-of-sample performance

### Walk-Forward Testing

Add validation beyond a single backtest:

- Train/test split
- Rolling windows
- Anchored walk-forward windows
- In-sample vs out-of-sample comparison
- Stability score

### Multi-Asset Strategies

Support strategies that rank symbols and rotate capital:

- Top momentum stocks
- Lowest volatility stocks
- Equal-weight basket
- Risk parity approximation
- Sector ETF rotation

## Broker-Style UI Direction

The interface should feel closer to a modern brokerage dashboard: clear, dense, and action-oriented. Avoid a marketing-page look. The first screen should feel like a usable trading and analytics workstation.

### Visual Principles

- Use neutral backgrounds with strong contrast.
- Keep cards compact with small radius, preferably 6-8px.
- Use green and red only for market movement, gains, losses, and risk.
- Use one restrained accent color for selected states and primary actions.
- Avoid decorative gradients, large hero sections, oversized headings, and playful copy.
- Use tabular layouts and compact status strips for repeated financial data.
- Keep typography tight, readable, and consistent.

### Layout Principles

Recommended shell:

| Region | Purpose |
| --- | --- |
| Top Bar | App name, selected tickers, data status, theme, mode |
| Left Sidebar | Watchlist, ticker search, data source, date range |
| Main Workspace | Active workflow: chart, backtest, simulator, Quant Lab |
| Right Panel | Details, assumptions, explanation, trade ticket, alerts |
| Bottom Area | Orders, trades, logs, or diagnostics when relevant |

This structure mirrors familiar broker workflows without pretending to be a live trading platform.

### Broker-Like Components

Add or refine these components:

- Watchlist table with last price, daily change, volume, and status.
- Quote header with ticker, name, price, change, latest bar, and data source.
- Compact chart toolbar for timeframe, indicators, and comparison ticker.
- Trade ticket style simulator panel.
- Positions table with quantity, average cost, market value, P&L, and exposure.
- Orders/trades table with status, side, quantity, price, fees, and timestamp.
- Risk summary strip with drawdown, volatility, VaR, beta, and exposure.
- Research notes or explanation panel for tutorial and backtest interpretation.

### Navigation

Recommended workflows:

- Overview
- Charts
- Backtest
- Simulator
- Portfolio
- Quant Lab
- Risk
- Tutorial
- Settings

For Simple Mode, hide or soften:

- Quant Lab
- optimizer controls
- parameter sweeps
- walk-forward testing
- advanced risk controls

For Advanced Mode, expose them with clear labels and assumptions.

## UI Implementation Plan

### Phase 1: Design Tokens And App Shell

Tasks:

- Expand the theme helper into a small design system.
- Standardize colors, spacing, borders, typography, and chart templates.
- Create reusable status pill styles.
- Replace large stacked metric cards with compact metric strips where appropriate.
- Make light mode and dark mode both feel complete.

Acceptance criteria:

- Light mode no longer has dark leftover surfaces.
- Dark mode is not overly blue or purple.
- Metric areas fit comfortably on laptop viewports.
- UI states look consistent across workflows.

### Phase 2: Broker Dashboard Layout

Tasks:

- Add a tighter top bar with ticker and data status.
- Move repeated market controls into a cleaner sidebar.
- Add a watchlist section or preset ticker groups.
- Add quote header component in the main workflow.
- Keep active workflow content above the fold as much as possible.

Acceptance criteria:

- A user can see selected ticker, latest price/date, data source, and active workflow immediately.
- Main controls are visually grouped by task.
- The app looks like a workstation, not a long demo page.

### Phase 3: Simulator Streamlining

Tasks:

- Convert simulator controls into a trade ticket pattern.
- Keep account status, current position, and order entry close together.
- Add positions and trade journal tables.
- Keep order preview visible before execution.

Acceptance criteria:

- Buy/sell flow is faster and clearer.
- The simulator visually resembles a paper-trading panel.
- Users can understand cash, shares, equity, and P&L without scrolling heavily.

### Phase 4: Quant Lab V1

Tasks:

- Add `Quant Lab` workflow behind Advanced Mode.
- Add code editor text area and template selector.
- Add AST validation helper module.
- Add strategy execution helper module.
- Convert returned signals into existing backtest input format.
- Reuse existing backtest analytics and explanation panels.

Acceptance criteria:

- A valid template can run end to end.
- Invalid code fails safely with a friendly error.
- No filesystem, network, subprocess, or import access is allowed.
- Results include metrics, chart, trade log, assumptions, and explanation.

### Phase 5: Quant Lab V2

Tasks:

- Add parameter sweep UI.
- Add walk-forward testing.
- Add strategy comparison.
- Add saved strategy snippets.

Acceptance criteria:

- Users can compare multiple strategies or parameter sets.
- The app warns when a result looks overfit.
- Advanced outputs remain optional and do not overwhelm Simple Mode.

## Suggested Code Structure

Recommended new modules:

```text
market_dashboard/modules/quant_lab.py
market_dashboard/modules/strategy_sandbox.py
market_dashboard/modules/strategy_templates.py
market_dashboard/modules/result_explainer.py
market_dashboard/ui/components.py
```

Responsibilities:

| Module | Responsibility |
| --- | --- |
| `quant_lab.py` | Convert user strategy outputs into backtest-ready signals |
| `strategy_sandbox.py` | Validate and safely execute strategy code |
| `strategy_templates.py` | Store built-in strategy templates |
| `result_explainer.py` | Generate plain-English result summaries |
| `ui/components.py` | Shared broker-style UI components |

Keep the first implementation small. Do not split files unless the dashboard starts getting harder to maintain.

## Test Plan

Add tests for:

- Valid strategy code returns correct signal shapes.
- Missing `strategy(data)` is rejected.
- Imports are rejected.
- `open`, `exec`, `eval`, and subprocess access are rejected.
- Infinite or slow strategies time out.
- Mismatched signal lengths are rejected.
- Template strategies run on demo data.
- Quant Lab output connects to the existing backtest engine.
- Light and dark theme tokens exist for all major surfaces.

Manual browser checks:

- Quant Lab is hidden or marked advanced in Simple Mode.
- Template strategy validates and runs.
- Invalid code shows an error but does not crash the app.
- Result explanation appears after a run.
- Broker-style layout fits at 1280x720 and mobile width.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Unsafe code execution | AST validation, restricted namespace, timeout, no imports |
| Users overtrust results | Always show assumptions, data source, benchmark, and reliability warnings |
| UI becomes too complex | Keep Simple Mode default and Advanced Mode optional |
| Overfitting | Add walk-forward testing and robustness warnings |
| Performance issues | Limit rows for validation, cache data, and cap parameter sweeps |
| Data provider failures | Keep Auto provider, fallback sources, and clear data status |

## Recommended First Implementation Sprint

1. Create a broker-style shared component layer for metric strips, status pills, quote headers, and compact panels.
2. Add a `Quant Lab` placeholder workflow that appears only in Advanced Mode.
3. Add strategy templates and a code editor area.
4. Build AST validation for a single `strategy(data)` function.
5. Run one template strategy through the existing backtest engine.
6. Add result explanation and safety warnings.
7. Add tests for validator failures and a successful template run.

## Definition Of Done

The feature is ready when:

- Simple Mode remains easy to use.
- Advanced users can run at least three built-in Quant Lab templates.
- Custom user strategy logic can be validated and simulated safely.
- Invalid code cannot access files, network, imports, subprocesses, or environment data.
- Results are compared against buy-and-hold and clearly explained.
- The UI feels denser, cleaner, and closer to a broker dashboard.
- Tests cover the sandbox, templates, and backtest integration.
