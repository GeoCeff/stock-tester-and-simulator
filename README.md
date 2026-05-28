# Stock Backtester

A Streamlit market analytics app for downloading recent price data, comparing tickers, practicing manual trades, and backtesting common trading strategies.

## Quick start

1. Clone the repository and go to the project folder:
   ```powershell
   git clone <repository-url>
   cd stock-backtester
   ```
2. Install the required packages:
   ```powershell
   python -m pip install -r requirements.txt
   ```
3. Launch the dashboard:
   ```powershell
   streamlit run market_dashboard/dashboard.py
   ```

The app will open in your browser at `http://localhost:8501`.

## What this repo contains

- `market_dashboard/dashboard.py` - the main Streamlit app
- `market_dashboard/ui/` - shared theme and chart styling helpers
- `market_dashboard/modules/` - helper modules for data, indicators, backtests, simulator, search, and portfolio metrics
- `tests/` - focused pytest coverage for data, simulator, search, and strategies
- `requirements.txt` - the Python dependencies
- `README.md` - this guide
- `QUANT_LAB_AND_BROKER_UI_PLAN.md` - implementation plan for the optional Quant Lab and broker-style UI refresh
- `LICENSE` - the project license
- `test_integration.py` - a basic integration test that checks the main modules together

## Features

- Choose market data from `Auto`, `Yahoo Finance`, `Stooq` daily data, or deterministic demo data
- Learn the app through an in-app Tutorial workflow and optional guided walkthrough covering stocks, indicators, backtesting, simulation, and risk metrics
- Load optional learning scenarios for starter overview, trend backtests, RSI practice, simulator drills, ETF portfolios, and risk review
- See data status, latest bar date, loaded tickers, and unavailable tickers near the active workflow
- Use curated stock categories and ticker presets for faster setup
- Calculate common indicators like moving averages, RSI, MACD, and Bollinger Bands
- Run simple backtests for MA crossover, RSI, and Bollinger Band strategies
- Use Expert-mode Quant Lab templates or safe custom `strategy(data)` code for signal-based simulations
- Compare strategy results against buy-and-hold and optional benchmarks
- Practice manual trading in the simulator with compact status, order previews, and safer buy/sell defaults
- See performance metrics such as total return, Sharpe ratio, drawdown, win rate, rolling risk, and monthly returns

## Data sources

The default `Auto` source tries Yahoo Finance first, which is best for recent and intraday-friendly requests. For daily candles, Auto can fall back to Stooq before using demo data. The app keeps working offline or during provider outages by using deterministic demo data and clearly labeling charts and backtests as illustrative.

## Tests

Run the local test suite with:

```powershell
python -m pytest
```

## Notes

The main app lives in `market_dashboard/dashboard.py`, and reusable logic is split into modules under `market_dashboard/modules/`.

Old documentation and legacy test scripts have been moved to the `archive/` folder to keep the repository root clean.

For the next major product direction, see `QUANT_LAB_AND_BROKER_UI_PLAN.md`.
