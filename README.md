# Stock Backtester

Version `1.2.0`

A Streamlit market analytics workstation for downloading market data, comparing tickers, running strategy backtests, testing safe Quant Lab strategy snippets, and practicing manual trades in a paper-trading simulator.

This project is for education and research. It is not financial advice and does not place live trades.

## Quick Start

1. Clone the repository:
   ```powershell
   git clone https://github.com/GeoCeff/Stock-Tester-and-Simulator.git
   cd Stock-Tester-and-Simulator
   ```

2. Install dependencies:
   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Launch the dashboard:
   ```powershell
   streamlit run market_dashboard/dashboard.py
   ```

The app opens at `http://localhost:8501`.

## Features

- Broker-style dashboard with top bar, watchlist, quote header, compact analytics, and dark/light themes
- Market data from `Auto`, `Yahoo Finance`, `Stooq` daily data, or deterministic demo data
- Common chart indicators with quick `Common`, `All`, and `Off` toggles
- Guided tutorial workflow and optional learning scenarios for newer investors
- Backtests for moving-average crossover, RSI, and Bollinger Band strategies
- Expert-mode Quant Lab with built-in templates and safe custom `strategy(data)` signal code
- Strategy comparison against buy-and-hold and optional benchmarks
- Paper-trading simulator with order previews, positions, equity, cash, exposure, and trade journal
- Portfolio and risk views with Sharpe ratio, drawdown, VaR, CVaR, rolling risk, and monthly returns

## Quant Lab Safety

Quant Lab is designed for signal generation, not unrestricted code execution. Custom strategies must define one `strategy(data)` function and return buy/sell signals or a position series. The sandbox blocks imports, filesystem access, network/subprocess access, environment access, reflection helpers, and pandas write methods before execution. Strategy code also runs with a timeout and row limits.

## Project Structure

- `market_dashboard/dashboard.py` - main Streamlit app
- `market_dashboard/modules/` - data loading, indicators, backtests, simulator, Quant Lab, portfolio, and search helpers
- `market_dashboard/ui/` - shared theme and broker-style UI components
- `tests/` - pytest coverage for data, simulator, search, strategies, and Quant Lab
- `docs/` - implementation plans, roadmap notes, and archived legacy documents
- `CHANGELOG.md` - release notes
- `SECURITY.md` - security and vulnerability reporting policy

## Tests

Run the local test suite:

```powershell
python -m pytest
```

The test suite is configured to collect only files under `tests/` so archived scripts and old notes do not affect public CI runs.

## Data Sources

The default `Auto` source tries Yahoo Finance first. For daily candles, Auto can fall back to Stooq before using deterministic demo data. Demo data keeps the app usable offline or during provider outages and is always labeled as illustrative.

## Documentation

- [Quant Lab and Broker UI plan](docs/QUANT_LAB_AND_BROKER_UI_PLAN.md)
- [Next-level roadmap](docs/NEXT_LEVEL_ROADMAP.md)
- [App improvement plan](docs/APP_IMPROVEMENT_PLAN.md)

## License

MIT License. See [LICENSE](LICENSE).
