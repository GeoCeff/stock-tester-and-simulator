# Stock Research and Execution Workstation

A single repository for market research, strategy backtesting, paper trading, and guarded IBKR execution.

This project is for education and research. It is not financial advice. Live trading is disabled unless you deliberately start a live mode and every execution safety gate passes.

## Applications

- `market_dashboard/` — Python/Streamlit research lab for market data, indicators, backtests, Quant Lab strategies, portfolio risk, and paper simulation.
- `execution_dashboard/` — dependency-free Node dashboard for live quotes, model/research gates, IBKR synchronization, order planning, audits, and deliberately armed execution.

The applications share `execution_dashboard/data/bot_model_pack.json`. The backtester writes validated strategy settings; the execution dashboard validates and reads them. Malformed, stale, disabled, or rejected model packs cannot approve an order.

## Quick Start

Requirements:

- Python with the packages in `requirements.txt`
- Node.js
- Windows PowerShell

```powershell
git clone https://github.com/GeoCeff/stock-tester-and-simulator.git
cd stock-tester-and-simulator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start_all.ps1
```

The research lab opens at `http://127.0.0.1:8501`; the execution dashboard opens at `http://127.0.0.1:8787`.

Stop both:

```powershell
.\stop_all.ps1
```

## Research-to-Execution Flow

Run the bounded research agent once:

```powershell
.\.venv\Scripts\python.exe .\run_research_agent.py
```

Or keep it running once per day:

```powershell
.\.venv\Scripts\python.exe .\run_research_agent.py --watch-minutes 1440
```

The agent:

1. downloads real daily data without demo fallback;
2. tests the built-in strategies and holding periods with estimated costs;
3. selects on development folds;
4. validates the winner on one untouched final fold;
5. publishes passing model settings and current entry/stop/target candidates;
6. advances a real-data forward paper ledger in `execution_dashboard/data/research_paper.json`;
7. publishes a rejected result when nothing passes.

Paper signals are filled at the next available market open and do not count as evidence until a later bar closes them by stop, target, or maximum hold. At least 30 closed trades in one style, positive cost-adjusted expectancy, profit factor of 1.2, and drawdown within 15% are required for the ledger to report that style as validated.

The execution dashboard reloads the agent result and model pack whenever research refreshes. Only matching, fresh signals can pass its research-agent gate. While the dashboard is open, technical/news research refreshes hourly; unavailable news stays explicitly unavailable. News and every existing account, quote, model, learning, fee, and IBKR gate can still reduce or reject a setup.

Backtests are hypothetical, so a pass is a paper-trading candidate—not a promise of future profit. Paper trade before deliberately enabling any live mode.

## Run Applications Separately

Research lab:

```powershell
.\.venv\Scripts\python.exe -m streamlit run market_dashboard\dashboard.py
```

Safe execution dashboard:

```powershell
cd execution_dashboard
.\start_dashboard.ps1
```

See [execution_dashboard/README.md](execution_dashboard/README.md) for IBKR, live-confirm, full-auto, and AI-research modes.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
node execution_dashboard\self_check.js
```

## Project Structure

- `market_dashboard/modules/` — data loading, indicators, strategies, backtests, simulator, Quant Lab, portfolio, and model-pack export
- `run_research_agent.py` — bounded walk-forward search and daily repeat mode
- `market_dashboard/ui/` — shared Streamlit theme and components
- `execution_dashboard/` — live dashboard, local API, IBKR bridge, operator scripts, and Node self-check
- `tests/` — Python test suite
- `docs/` — research-app implementation notes and archived documents

## License

MIT License. See [LICENSE](LICENSE).
