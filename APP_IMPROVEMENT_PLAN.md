# Quant Market Analytics Improvement Plan

This plan captures the highest-impact improvements observed while reviewing the running Streamlit app at `http://localhost:8501/`. The goal is to make the product feel more guided, compact, reliable, and professional without making it harder for beginners.

## Priority 1: Simulator Order UX

The simulator is currently the most visible workflow, and it has the clearest friction.

### Problems

- The default buy quantity can cost more than the available cash.
- The sell form is active even when the user owns zero shares.
- The app does not preview the result of a buy or sell before execution.
- Reset happens immediately without confirmation.
- After a trade, the user gets a short success message but little context about what changed.

### Improvements

- Set the default buy quantity to the maximum affordable quantity, capped to a beginner-friendly value.
- Show `Max affordable shares` next to the buy quantity input.
- Disable or guard the sell action when no shares are held.
- Add an order preview for each side:
  - estimated trade value
  - estimated fee
  - cash after trade
  - shares after trade
  - portfolio exposure after trade
- Add a reset confirmation checkbox or dialog.
- After a trade, show a short explanation:
  - what changed
  - new cash balance
  - new position count
  - realized or unrealized P&L impact

### Acceptance Criteria

- A first-time user cannot accidentally start with an invalid default order.
- Sell controls clearly communicate when there is nothing to sell.
- Every trade action shows a preview before execution.
- Reset requires confirmation.

## Priority 2: Compact Layout

The current app uses a lot of vertical space, especially in the simulator. Important controls are pushed below the fold.

### Problems

- Metric cards are tall and stack heavily in narrow layouts.
- Current position metrics take too much space before the user reaches trading controls.
- The sidebar and main content both feel widget-heavy.

### Improvements

- Replace large simulator metric cards with a compact status strip:
  - Date
  - Cash
  - Shares
  - Equity
  - Price
- Use smaller section headings inside tool areas.
- Keep the trading panel visible without requiring as much scrolling.
- Group related controls into compact rows.
- Reduce repeated dividers.

### Acceptance Criteria

- On a 1280x720 viewport, a user can see simulator status and at least the buy controls at the same time.
- No important button appears disconnected from its related inputs.
- Metric labels and values remain readable without oversized cards.

## Priority 3: Workflow Navigation

The app should feel like a research workstation with clear workflows, not a long page controlled only by sidebar radio buttons.

### Problems

- Mode selection is hidden in the sidebar.
- Users do not get a clear top-level mental model of the app.
- The simulator can appear active immediately, which may not be the best default first experience.

### Improvements

- Add top-level tabs:
  - `Overview`
  - `Backtest`
  - `Simulator`
  - `Portfolio`
  - `Risk`
  - `Settings`
- Make `Overview` or `Backtest` the default landing workflow.
- Keep sidebar focused on data selection and workspace settings.
- Move workflow-specific settings into the relevant tab.
- Add empty states for workflows that need setup.

### Acceptance Criteria

- A new user can tell what the main workflows are within five seconds.
- Switching between workflows does not require hunting through the sidebar.
- Advanced options do not crowd beginner workflows.

## Priority 4: Data Status And Reliability

The app now has a demo fallback and selectable providers, but the status should stay explicit and useful.

### Problems

- Users may not understand whether they are looking at Yahoo Finance, Stooq, or generated demo data.
- Mixed ticker failures are not yet surfaced.
- Data warnings can feel separate from the charts they affect.

### Improvements

- Show a clear data status pill near the app header:
  - `Live data`
  - `Demo data`
  - `Partial data`
  - `Data unavailable`
- If demo data is used, explain that charts and backtests are illustrative only.
- Track successful and failed tickers separately.
- Let partial downloads continue when some tickers fail.
- Show a compact data summary:
  - requested source
  - source
  - latest bar
  - row count
  - date range
  - interval
  - tickers loaded
  - tickers unavailable

### Implementation Status

- Added a sidebar `Data Source` selector with `Auto`, `Yahoo Finance`, `Stooq`, and `Demo dataset`.
- `Auto` tries Yahoo Finance first, then Stooq for daily candles, then demo data if real data is unavailable.
- The status strip now shows requested source, actual source, latest bar, row count, date range, interval, loaded tickers, and unavailable tickers.

### Acceptance Criteria

- Users always know whether data is real or demo.
- One bad ticker does not block analysis for valid tickers.
- Data status appears close to the charts and results it affects.

## Priority 5: Analytics Upgrades

Once the core UX is smoother, analytics should become clearer and more useful.

### Improvements

- Show strategy equity vs. buy-and-hold equity in the same chart.
- Add a benchmark comparison, defaulting to `SPY`.
- Add a trade table with:
  - entry date
  - exit date
  - entry reason
  - exit reason
  - holding time
  - return
  - fees
- Add monthly returns heatmap.
- Add rolling Sharpe chart.
- Add rolling volatility chart.
- Add drawdown duration, not only max drawdown.
- Add strategy assumptions panel:
  - fees
  - interval
  - starting capital
  - risk-free rate
  - position sizing

### Acceptance Criteria

- A user can compare a strategy against buy-and-hold without changing screens.
- Trade results are explainable, not just summarized.
- Risk and return metrics have plain-language context.

## Suggested Implementation Order

1. Improve simulator order validation and previews.
2. Compact the simulator layout.
3. Add data status pills and clearer demo-data messaging.
4. Introduce top-level tabs.
5. Add strategy vs. buy-and-hold comparison.
6. Add richer trade table fields.
7. Add rolling risk charts and monthly heatmap.

## First Coding Task

Start with simulator order UX because it is visible immediately and has the highest beginner-safety value.

Recommended first patch:

- Compute `max_affordable_qty` from cash, current price, and fee.
- Use it to set a safer default buy quantity.
- Disable sell execution when current shares are zero.
- Add a compact order preview under buy and sell inputs.
- Add reset confirmation.
