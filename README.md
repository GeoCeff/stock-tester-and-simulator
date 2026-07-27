# Stock Research and Execution Workstation

A single repository for market research, strategy backtesting, paper trading, and guarded IBKR execution.

This project is for education and research. It is not financial advice. Live trading is disabled unless you deliberately start a live mode and every execution safety gate passes.

## One Application

Stock Lab opens one browser application for market research, backtests, strategy validation, paper trading, portfolio risk, news gates, IBKR synchronization, and deliberately armed execution.

The Python engine in `market_dashboard/modules/` and `run_research_agent.py` remains the research and validation backend. It writes validated settings to `execution_dashboard/data/bot_model_pack.json`; the unified dashboard validates and reads them. Malformed, stale, disabled, or rejected model packs cannot approve an order.

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

Stock Lab opens at `http://127.0.0.1:8787`.

Stop it:

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

To make that daily loop survive sign-out and Windows restarts, register it as
a per-user scheduled task:

```powershell
.\research_agent_task.ps1
```

The agent:

1. downloads recognized-provider daily data for a fixed 20-stock, multi-sector universe plus SPY without demo fallback, requiring full symbols, valid OHLC, recent bars, and at least 90% of the requested history;
2. tests the built-in strategies and holding periods with estimated costs;
3. selects on development folds;
4. validates the winner on one untouched final fold;
5. replays the exact published limit-entry, stop, target, and maximum-hold plan across the same folds;
6. requires the execution plan to remain profitable across time folds and a majority of symbols;
7. publishes model settings and candidates only when both the signal and execution plan pass;
8. advances a real-data forward paper ledger in `execution_dashboard/data/research_paper.json`;
9. refreshes the existing news gate for current candidates without requiring the browser to be open;
10. records compact run lessons in `execution_dashboard/data/research_history.jsonl`;
11. publishes a rejected result when nothing passes.

Fold evaluators stop opening new positions early enough for the full entry-validity window and maximum hold to remain observable inside that fold. This prevents fast stops near a fold edge from counting while unresolved trades disappear.

Every published result and compact history record carries the exact holdout start/end/row count and a deterministic trial ID, plus folds, warmup, costs, gates, engine version, candidate set, and real-data provenance. Repeated records with the same holdout ID are monitoring updates, not independent holdout evidence.

The fixed universe is predeclared but selected from current securities, so historical results can contain survivorship bias. They support decisions only for this stated universe and still require untouched-holdout and prospective paper evidence; they are not an unbiased historical-index claim.

Paper signals use the published limit entry for up to three future bars, allow only one open position per symbol/style, and are cancelled before filling if research or news withdraws them. Daily bars never claim a target on the ambiguous fill bar, and a gap through a stop exits at the worse opening price. Trades do not count as evidence until a real later bar closes them by stop, target, or maximum hold. Evidence is isolated by fingerprints of the strategy, indicators, and paper-execution code plus the news/model version, holding period, bracket rules, entry validity, and cost assumption, so old implementations cannot validate a new plan. Validation requires at least 30 closed trades in one exact plan across at least five symbols and 90 calendar days, at least 60% positive symbols, positive cost-adjusted expectancy, profit factor of 1.2, and drawdown within 15%.

The execution dashboard reloads the agent result and model pack whenever research refreshes. Its server rejects live orders until the current exact plan passes forward paper validation, the candidate and news are current, and the submitted bracket matches the published symbol, stock contract, entry, stop, target, and risk budget. Position risk is recalculated from the submitted quantity, published stop distance, and current IBKR net liquidation value; unavailable equity, an unverified contract, mixed bracket contracts, or excess quantity fails closed. Agent results and their embedded news approval expire after 24 hours; candidate signals expire after five calendar days. News refreshes with every agent run and hourly while the dashboard is open; only symbol/company-relevant headlines from the last three days count, and unavailable news reduces rather than approves a setup. News and every existing account, quote, model, learning, fee, and IBKR gate can still reduce or reject a setup.

Backtests are hypothetical, so a pass is a paper-trading candidate—not a promise of future profit. Paper trade before deliberately enabling any live mode.

## Run the Dashboard Directly

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

- `market_dashboard/modules/` — data loading, indicators, strategies, backtests, simulation, portfolio analysis, and model-pack export
- `run_research_agent.py` — bounded walk-forward search and daily repeat mode
- `research_agent_task.ps1` — persistent per-user Windows launcher
- `execution_dashboard/` — unified Stock Lab UI, local API, IBKR bridge, operator scripts, and Node self-check
- `tests/` — Python test suite
- `docs/` — implementation notes and archived documents

## License

MIT License. See [LICENSE](LICENSE).
