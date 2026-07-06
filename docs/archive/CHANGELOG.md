# Changelog

All notable changes to the Stock Backtester project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-03-27

### Added

#### Stock Search & Discovery ≡ƒöì
- **Smart Stock Search**: Search by company name or ticker symbol with autocomplete
- **Popular Stocks Browser**: Categorized collections (Tech, Financial, Healthcare, Consumer, Energy, Industrial, Communication, Materials)
- **Quick Stock Selection**: One-click buttons for popular stocks with auto-fill
- **Stock Information**: Detailed company data (sector, industry, market cap, current price, 52-week range)
- **Session Persistence**: Selected stocks remembered across interactions

#### Trading Simulator ≡ƒÄ«
- **Manual Trading Interface**: Buy/sell buttons with quantity controls and validation
- **Real-time P&L Tracking**: Live equity, cash, positions, and unrealized gains/losses
- **Time Navigation**: Advance through historical data day-by-day or 5-day jumps
- **Interactive Charts**: 2-row layout showing price action and equity curve with trade markers
- **Trade History**: Complete transaction log with entry/exit prices, P&L, and fees
- **Performance Metrics**: Sharpe ratio, win rate, max drawdown, total return for manual trades
- **CSV Export**: Download complete trade history for external analysis
- **Buy & Hold Comparison**: Benchmark manual performance against passive strategy

#### Dual Mode Interface ≡ƒÄ»
- **Mode Selection**: Toggle between "≡ƒôè Backtesting" and "≡ƒÄ« Simulator" modes
- **Context-Aware UI**: Different sidebar controls and main content for each mode
- **Unified Data Pipeline**: Same market data and indicators used for both modes
- **Seamless Switching**: Change modes without losing data or selections

#### Enhanced User Experience
- **Improved Sidebar Organization**: Logical grouping with emoji headers
- **Session State Caching**: Prevents unnecessary backtest recalculation
- **Quick Presets**: Instant configuration for common trading styles
- **Advanced Options**: Collapsible sections for detailed configuration
- **Better Error Handling**: User-friendly messages with actionable hints
- **Loading States**: Progress indicators for long-running operations

### Changed
- **Dashboard Layout**: Reorganized for dual-mode functionality
- **Sidebar Structure**: Added stock search section and mode selection
- **Chart System**: Extended to support simulator-specific visualizations
- **Code Architecture**: Modular helper functions and display components

### Technical Improvements
- **New Modules**: `stock_search.py` and `simulator.py` for specialized functionality
- **State Management**: Enhanced session state for simulator persistence
- **Performance**: Caching for stock search and backtest results
- **Error Resilience**: Better handling of API failures and edge cases

## [1.0.0] - 2026-03-26

### Added

#### Backtesting Engine
- **Strategy Framework**: Base `Strategy` abstract class for building custom strategies
- **MovingAverageCrossover**: MA50/MA200 crossover strategy
- **RSIStrategy**: Two modes (threshold and mean-reversion) for RSI-based trading
- **BollingerBandsStrategy**: Mean-reversion strategy using Bollinger Bands
- **Position Tracking**: Support for day trading (0-day hold), swing trading (1-5 days), and position trading (20+ days)
- **Flexible Position Sizing**:
  - Fixed mode: All-in or flat (0 or 1 position)
  - Dynamic mode: Continuous 0-1 position scaling
- **Transaction Fees**: Configurable percentage-based fees applied on entry/exit
- **Performance Metrics**:
  - Total Return (%)
  - Sharpe Ratio with interval-aware annualization
  - Max Drawdown (%)
  - Win Rate (% of profitable days)
- **Buy-and-Hold Comparison**: Reference equity curve for strategy benchmarking

#### Dashboard Features
- **Data Management**:
  - Multi-ticker support with yfinance integration
  - Configurable date ranges and candle intervals (1m, 5m, 15m, 1h, 1d)
  - Real-time data downloads with split/dividend adjustment

- **Technical Indicators**:
  - Moving Averages (50 and 200-period)
  - RSI (14-period, customizable)
  - MACD with signal line
  - Bollinger Bands (20-period MA, 2╧â bands)

- **Visualizations**:
  - 5-row advanced chart (candlesticks, volume, MACD, RSI, equity curve)
  - Drawdown chart across multiple tickers
  - Correlation heatmap
  - Entry/exit signal markers on candlestick chart

- **Sidebar Controls**:
  - Strategy selector (5 strategies including "None")
  - Independent backtest date range
  - Position sizing mode selector
  - Holding period control (0-252 days)
  - Transaction fee slider (0-1%)
  - Sharpe ratio annualization selector

#### Documentation
- Comprehensive README with feature overview, usage guide, and examples
- Development guide for contributors
- API documentation for strategy development
- Troubleshooting section with common issues and solutions

#### Project Structure
- Modular architecture with separate concerns:
  - `modules/data.py`: Data download and preprocessing
  - `modules/indicators.py`: Technical indicator calculations
  - `modules/strategies.py`: Strategy implementations and backtesting logic
  - `modules/portfolio.py`: Portfolio metrics and calculations
  - `modules/utils.py`: Utility functions
  - `dashboard.py`: Main Streamlit application

#### Configuration Files
- `requirements.txt`: Pinned dependencies for reproducible environments
- `.gitignore`: Python-specific exclusions for clean repository
- `DEVELOPMENT.md`: Developer onboarding and contribution guidelines
- `CHANGELOG.md`: This file

### Technical Details

#### Supported Intervals
- 1m (1-minute): 252 ├ù 6.5 ├ù 60 = 98,280 trading periods/year for Sharpe annualization
- 5m (5-minute): 252 ├ù 6.5 ├ù 12 = 19,656 trading periods/year
- 15m (15-minute): 252 ├ù 6.5 ├ù 4 = 6,552 trading periods/year
- 1h (1-hour): 252 ├ù 6.5 = 1,638 trading periods/year
- 1d (1-day): 252 trading days/year

#### Backtesting Logic
- Signals generated with 1-day lookahead prevention (`.shift(1)`)
- Positions auto-exit after holding period expires
- Fees deducted on trade entry/exit days only
- Equity curve uses compound returns: `initial_equity ├ù (1 + daily_returns).cumprod()`

#### Strategy Guidelines
- All strategies are long-only (no shorting)
- No partial fills (position = 0 or full size)
- No limit or stop orders (market execution only)
- Entry signals override previous signals (no overlap)

### Known Limitations

- **No slippage modeling**: Assumes execution at close price
- **No partial fills**: Position size is binary (fixed) or continuous (dynamic)
- **Limited order types**: Only market orders supported
- **Indicator lag**: First N bars produce NaN (e.g., MA200 needs 200+ bars)
- **No dynamic position sizing** based on signal strength (planned for v1.1)
- **Single-asset backtests only** (portfolio-level backtesting planned for v1.1)
- **No walk-forward analysis** for parameter robustness testing

### Testing Notes

Validated with:
- Python 3.8+ syntax compliance
- Streamlit app startup and rendering
- Sample data from Yahoo Finance (AAPL, MSFT, NVDA, TSLA, SPY)
- OHLCV data handling (splits/dividends auto-adjusted)

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| streamlit | 1.28.1 | Web dashboard framework |
| pandas | 2.1.3 | Data manipulation |
| plotly | 5.17.0 | Interactive charts |
| yfinance | 0.2.32 | Market data download |
| numpy | 1.24.3 | Numerical computing |

---

## [Unreleased]

### Planned for v1.1

#### Features
- [ ] Dynamic position sizing based on indicator strength
- [ ] Portfolio-level backtesting (multiple assets with weights)
- [ ] Parameter optimization (grid search, Bayesian optimization)
- [ ] Walk-forward analysis for parameter stability testing
- [ ] Trade logging and export (CSV with entry/exit details)
- [ ] More strategies: MACD crossover, Stochastic, ATR breakouts
- [ ] Risk management: Stop-loss, take-profit, position-sizing by risk
- [ ] Monte Carlo simulation for drawdown estimation
- [ ] Live/paper trading integration (via broker APIs)

#### Bug Fixes & Improvements
- [ ] Cache strategy computation to avoid recalculation on slider changes
- [ ] Better handling of missing data (holidays, delisted symbols)
- [ ] Improved error messages for invalid date ranges
- [ ] Performance optimization for large datasets (1m interval, 5+ years)

### Planned for v1.2+
- [ ] Multi-chart comparison (side-by-side strategy results)
- [ ] Custom indicator builder (user-defined SMA/EMA/etc.)
- [ ] Strategy backtesting comparison dashboard
- [ ] Performance attribution analysis (what drove returns?)
- [ ] Transaction cost modeling (market impact, slippage)
- [ ] Stress testing under different market regimes

---

## Version History Timeline

| Version | Release Date | Status |
|---------|---|---|
| 1.0.0 | 2026-03-26 | Γ£à Stable |
| 1.1.0 | TBD | ≡ƒöä Planned |
| 1.2.0 | TBD | ≡ƒöä Planned |

---

## Contributing

When contributing, please:
1. Follow the [Development Guide](DEVELOPMENT.md)
2. Document changes in this CHANGELOG
3. Use clear commit messages
4. Test with sample data before submitting PR

---

## Support

For issues or questions, please refer to:
- [README.md](README.md) - Feature overview and usage
- [DEVELOPMENT.md](DEVELOPMENT.md) - Developer documentation
- GitHub Issues - Bug reports and feature requests

