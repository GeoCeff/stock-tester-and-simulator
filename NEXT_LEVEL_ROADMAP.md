# Stock Backtester Next-Level Roadmap

This document outlines how to turn the current Streamlit stock backtester into a more professional, stable, and beginner-friendly trading analytics app. The goal is not to make it feel complicated. The goal is to make the product feel trustworthy, polished, and easy to learn.

## Current Sprint Progress

Started on May 21, 2026.

Completed in the first pass:

- Removed emoji-heavy visible copy from the main dashboard paths and integration test output.
- Added a shared `market_dashboard/ui/theme.py` helper for CSS theme tokens and Plotly templates.
- Added a compact app header, data status line, and beginner metric glossary.
- Added public market data schema helpers in `market_dashboard/modules/data.py`.
- Added focused offline tests for data normalization and strategy position handling.
- Added `pytest` to `requirements.txt`.
- Added a deterministic demo dataset fallback so the app can keep working when live market data is unavailable.
- Added selectable data sources: Auto, Yahoo Finance, Stooq daily data, and deterministic demo data.
- Added data freshness/status details including requested source, actual source, latest bar, loaded tickers, and unavailable tickers.
- Ran the full local pytest suite successfully after installing pytest in the project virtual environment.
- Launched the Streamlit app locally and confirmed it responds on port 8501.

Still next:

- Continue splitting the large dashboard into smaller UI modules.
- Add lightweight download caching by ticker, date range, interval, and selected provider.

## Product Direction

The app should feel like a clean research workstation for retail investors, students, and beginner quant learners.

Core positioning:

- Beginner-friendly enough that a first-time user understands what to do next.
- Professional enough that the interface feels credible and serious.
- Transparent enough that every metric, strategy, and assumption is explained.
- Stable enough that bad tickers, missing data, short date ranges, and API failures never crash the app.

The next version should focus on three pillars:

- Better presentation: cleaner theme, stronger layout, fewer emojis, better typography, and more consistent controls.
- Better guidance: guided workflows, plain-language explanations, presets, examples, and safer defaults.
- Better analytics: clearer strategy results, better comparisons, stronger risk metrics, and reusable saved analyses.

## Visual And UI Goals

The current app is functional, but the interface should move away from an emoji-heavy dashboard style and toward a calm analytics product.

Recommended design personality:

- Clean, modern, and focused.
- Dark and light themes that both feel intentional.
- Neutral background with restrained accent colors.
- Green/red used only for gain/loss and risk signals.
- Minimal decorative elements.
- Plain-language labels over playful labels.
- Icons used sparingly and consistently, not as decoration.

### Emoji Cleanup

Most emojis should be removed from the visible app copy. They currently make the app feel less professional and some appear as corrupted characters on Windows consoles or in certain encodings.

Recommended approach:

- Remove emojis from titles, subtitles, section headers, buttons, metric labels, warnings, and helper text.
- Keep only one optional app icon or favicon if desired.
- Replace emoji-heavy labels with clear text.
- Use color, layout, typography, and small status labels instead of emojis.
- Fix any mojibake/corrupted emoji text in source files.

Examples:

| Current style | Recommended style |
| --- | --- |
| `📊 Quant Market Analytics` | `Quant Market Analytics` |
| `🚀 Run Backtest` | `Run Backtest` |
| `🎯 Start Backtesting` | `Start Backtesting` |
| `💰 Starting Capital ($)` | `Starting Capital` |
| `📉 Max Drawdown` | `Max Drawdown` |
| `❌ Failed to download data` | `Unable to download market data` |

## Theme System

The app should have a small design system instead of scattered styling.

Suggested theme tokens:

- Background: off-white for light mode, near-black neutral for dark mode.
- Surface: subtle panels with low-contrast borders.
- Primary accent: restrained blue or teal for selected states and primary actions.
- Success: green only for positive performance.
- Danger: red only for losses, risk, or destructive actions.
- Warning: amber for incomplete data or caution states.
- Text: strong primary text, muted secondary text, and compact helper text.

Theme implementation ideas:

- Create a `theme.py` or `ui_theme.py` helper module.
- Store colors, chart templates, spacing, and status styles in one place.
- Use one custom CSS block loaded once near app startup.
- Standardize Plotly chart templates so charts match the app theme.
- Avoid oversized headings inside dense tool areas.
- Keep sidebar controls compact and predictable.

## Layout Improvements

The app should feel more like a tool and less like a long scrolling demo page.

Recommended layout:

- Sidebar: data inputs, mode selection, presets, and workspace actions.
- Main header: app title, selected tickers, date range, and data status.
- Tabs: `Overview`, `Backtest`, `Simulator`, `Portfolio`, `Risk`, `Settings`.
- Main work area: charts and results.
- Right-side or expandable panel: plain-language explanations and assumptions.

High-impact UI changes:

- Replace the welcome screen with a compact onboarding panel or quick-start state.
- Keep the main usable experience visible immediately.
- Use tabs for workflows instead of repeated sections.
- Use consistent metric cards with compact labels.
- Add empty states for missing data, no strategy selected, and no trades.
- Add loading states that explain what is happening.
- Add validation messages next to the relevant inputs.

## Newbie-Friendly Experience

The app should guide users without talking down to them.

Beginner features:

- A "Simple" mode as the default.
- An "Advanced" mode for optimizer, risk settings, fee modeling, and strategy tuning.
- Strategy presets with plain-language names.
- Inline explanations for metrics:
  - Total return
  - Sharpe ratio
  - Max drawdown
  - Win rate
  - VaR and CVaR
- A glossary modal or expandable guide.
- Example ticker sets:
  - Tech basket
  - Broad market
  - Dividend stocks
  - High volatility stocks
- Sample scenarios:
  - "Compare AAPL against buy-and-hold"
  - "Test RSI mean reversion"
  - "Build a simple five-stock portfolio"

Recommended copy style:

- Use short, direct labels.
- Use helper text for context, not instructions everywhere.
- Avoid jargon unless it is explained.
- Make assumptions visible: fees, interval, risk-free rate, data source, adjusted prices.

## Professional Analytics Upgrades

The current strategy and portfolio features can become much more useful with clearer outputs.

Backtesting upgrades:

- Show strategy vs. buy-and-hold in the same equity chart.
- Add a trade table with entry reason, exit reason, holding time, return, and fees.
- Add annualized return, volatility, Calmar ratio, and profit factor.
- Show drawdown duration, not only max drawdown.
- Show monthly returns as a heatmap.
- Add rolling Sharpe and rolling volatility charts.
- Add benchmark comparison against SPY by default.
- Add a strategy assumptions panel.

Portfolio upgrades:

- Add weight validation and normalization preview.
- Add allocation chart.
- Add contribution-to-return by ticker.
- Add contribution-to-risk by ticker.
- Add rebalancing events to the chart.
- Add equal-weight and market-cap-weight presets.

Risk upgrades:

- Improve VaR/CVaR display with plain-language explanation.
- Add stress scenarios:
  - 2008-style drawdown
  - COVID crash
  - rate shock
  - single-stock gap down
- Add exposure summary.
- Add worst day, best day, and longest losing streak.

Simulator upgrades:

- Add a trade journal.
- Add order preview before buy/sell.
- Add current position quantity, average cost, unrealized P&L, and realized P&L.
- Add "reset simulation" confirmation.
- Add beginner prompts that explain what changed after a trade.

## Data Reliability

Market data is one of the biggest sources of instability. The app should handle failures gracefully.

Recommended improvements:

- Add data freshness status.
- Show which tickers failed and which succeeded.
- Let partial downloads continue instead of failing the whole app.
- Add selectable providers with a recent-first Auto mode and a daily fallback provider.
- Cache downloads by ticker, date range, and interval.
- Add retry behavior for temporary Yahoo Finance failures.
- Add a fallback demo dataset so the app works offline.
- Validate intraday date ranges because Yahoo Finance limits historical intraday data.
- Normalize all downloaded data into one internal schema.

Internal data contract:

- Use one standard shape for all market data.
- Convert external data immediately after download.
- Avoid spreading `MultiIndex` assumptions across the dashboard.
- Add helper functions like:
  - `get_close_prices(data)`
  - `get_ticker_frame(data, ticker)`
  - `available_tickers(data)`
  - `validate_ohlcv(data)`

## Codebase Improvements

The dashboard file is currently doing too much. It should be split into smaller UI and business-logic modules.

Suggested structure:

```text
market_dashboard/
  dashboard.py
  ui/
    theme.py
    layout.py
    sidebar.py
    metrics.py
    charts.py
    copy.py
  modules/
    data.py
    indicators.py
    strategies.py
    portfolio.py
    simulator.py
    optimizer.py
    persistence.py
```

Refactor priorities:

- Move chart creation out of `dashboard.py`.
- Move sidebar rendering into `ui/sidebar.py`.
- Move repeated simulator UI into a simulator view module.
- Move all visible copy into a central place so emoji cleanup is easier.
- Add type hints to core data and strategy functions.
- Keep business logic independent from Streamlit where possible.

## Testing And Quality

The current integration test is useful, but the project needs more targeted tests.

Recommended tests:

- Data normalization tests:
  - single ticker
  - multiple tickers
  - missing columns
  - empty download
- Indicator tests:
  - short series
  - flat prices
  - rising prices
  - NaN values
- Strategy tests:
  - no signals
  - one entry and one exit
  - holding period exit
  - fee application
  - dynamic position sizing
- Portfolio tests:
  - invalid weights
  - missing tickers
  - rebalancing behavior
- Simulator tests:
  - buy validation
  - sell validation
  - FIFO exits
  - equity curve updates

Recommended tooling:

- Add `pytest`.
- Add a `tests/` directory.
- Add a small deterministic sample dataset.
- Add a command like `python -m pytest`.
- Add GitHub Actions to run tests on every push.

## First Implementation Sprint

This is the highest-impact first pass.

1. Remove most emojis from visible app text.
2. Fix corrupted emoji/mojibake strings in `dashboard.py` and test output.
3. Add a simple design system:
   - theme colors
   - Plotly templates
   - metric styles
   - compact section headers
4. Refactor visible copy into cleaner labels.
5. Convert the welcome page into a professional quick-start panel.
6. Add tabs for major workflows.
7. Add clear empty/error states.
8. Add a beginner glossary expander.
9. Add tests for data normalization and strategy position handling.
10. Add a demo dataset fallback.

## Suggested Visual Refresh Checklist

- Use plain title: `Quant Market Analytics`.
- Use subtitle: `Backtest strategies, compare portfolios, and learn market risk with historical data.`
- Keep primary action text simple: `Run Backtest`, `Start Simulator`, `Load Data`.
- Use status labels:
  - `Ready`
  - `Loading`
  - `Data unavailable`
  - `Backtest complete`
- Use fewer colors.
- Use consistent spacing.
- Reduce giant headers inside tool panels.
- Use compact metric cards.
- Use clear chart titles.
- Make help text optional through expanders.
- Replace noisy markdown blocks with concise panels.

## Longer-Term Product Ideas

Once the UI and stability are stronger, the app can grow into a more complete learning and research tool.

Potential next-level features:

- Saved backtest reports.
- Exportable PDF or HTML reports.
- Strategy comparison dashboard.
- Custom strategy builder.
- Watchlists.
- Screener mode.
- Walk-forward analysis.
- Monte Carlo simulation.
- Parameter sensitivity charts.
- User-defined benchmarks.
- Notes and trade journal.
- Cloud deployment guide.
- Beginner learning path built into the app.

## Definition Of Done

The next-level version should meet these standards:

- A new user can run their first backtest in under one minute.
- The app does not crash on bad tickers, missing data, or short date ranges.
- Most emojis are removed from visible UI text.
- The theme looks intentional in both light and dark modes.
- Results are easy to interpret without outside knowledge.
- Advanced features are available but do not overwhelm beginners.
- The core logic is covered by tests.
- The dashboard feels like a polished analytics tool, not a prototype.
