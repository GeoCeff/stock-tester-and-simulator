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

1. Research and backtest in Streamlit.
2. Accept only results that passed the required validation.
3. Build and write the shared model pack:

   ```python
   from market_dashboard.modules.bot_model_pack import build_model_pack, write_model_pack

   pack = build_model_pack(validated_results, universe)
   write_model_pack(pack)
   ```

4. Open the execution dashboard. It automatically loads the shared pack.
5. Paper trade first. Live orders remain behind server flags, IBKR authentication, account limits, quote freshness, model/research gates, and explicit confirmation.

`write_model_pack(pack)` defaults to the correct monorepo location. Pass a path only when exporting elsewhere.

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
- `market_dashboard/ui/` — shared Streamlit theme and components
- `execution_dashboard/` — live dashboard, local API, IBKR bridge, operator scripts, and Node self-check
- `tests/` — Python test suite
- `docs/` — research-app implementation notes and archived documents

## License

MIT License. See [LICENSE](LICENSE).
