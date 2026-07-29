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

1. downloads recognized-provider daily data for the fixed 20-stock universe plus SPY without demo fallback or missing-bar price imputation, automatically excluding an incomplete New York session;
2. requires every symbol, valid completed-session OHLC, recent bars, and at least 90% of the requested history, then fingerprints the exact data and records per-symbol coverage plus pandas/NumPy versions;
3. evaluates only the frozen `SWING_20D / low_vol_trend` research lane by default; the broader strategy watchlist is not part of routine monitoring;
4. selects on development folds and replays the exact limit-entry, stop, target, maximum-hold, cost, risk, and fixed-universe-slot plan;
5. keeps routine monitoring excluded from another final-holdout exposure; a future holdout requires a separately implemented, predeclared authorization using genuinely new data;
6. requires the signal and execution plan to remain profitable across time folds and a majority of symbols;
7. publishes accepted settings only after every gate passes, otherwise publishes a rejected or shadow-only result;
8. advances exact-plan real-data paper and shadow ledgers without applying a later run's cost assumption to older positions;
9. refreshes the existing news gate for actionable candidates without requiring the browser to be open;
10. records compact run lessons in `execution_dashboard/data/research_history.jsonl`.

Run `python run_research_agent.py --preflight-only` to fetch, validate, and fingerprint the exact real-data snapshot without evaluating a strategy, exposing a holdout, refreshing news, publishing a result, advancing a ledger, or writing research history.

Fold evaluators first restrict every universe member—and SPY whenever benchmark-confirmed rules are candidates—to one shared calendar of complete OHLC observations, then stop opening new positions early enough for the full entry-validity window and maximum hold to remain observable inside that fold. This keeps final-holdout dates identical across symbols and prevents missing benchmark bars, fast stops near a fold edge, or unresolved trades from distorting evidence.

Every published result and compact history record carries the exact holdout start/end/row count and a deterministic trial ID, plus folds, warmup, costs, gates, engine version, candidate and cooldown-exclusion sets, and real-data provenance. Provenance includes an exact OHLC SHA-256 fingerprint and first date, last date, and row count for every symbol. Final-holdout exposure is recorded even if later publishing, news, or paper-ledger post-processing fails. A rejected strategy family cools down across every research holding style for 90 days; routine monitoring independently excludes the frozen primary candidate from another holdout. Signal and exact bracket-plan acceptance both enforce the predeclared drawdown limit. Exact-plan and paper drawdown mark each fixed universe slot daily using observed closes and actual bracket exits, while inactive slots remain in cash. Repeated records with the same holdout ID are monitoring updates, not independent holdout evidence.

The fixed universe is predeclared but selected from current securities, so historical results can contain survivorship bias. They support decisions only for this stated universe and still require untouched-holdout and prospective paper evidence; they are not an unbiased historical-index claim.

Actionable paper signals require an exact `news_action: pass`, use the published limit entry for up to three future bars, allow only one open position per symbol/style, and are cancelled before filling if research or news approval withdraws them. Reduced, rejected, unavailable, or missing news approval cannot contribute actionable paper evidence. Daily bars never claim a target on the ambiguous fill bar, and a gap through a stop exits at the worse opening price. Trades do not count as evidence until a real later bar closes them by stop, target, or maximum hold; every closed trade persists its observed daily mark path so intra-trade drawdown survives future provider changes. Duplicate trade identities, incomplete or overlapping mark paths, invalid or future-dated signal-to-fill-to-exit chronology, and returns that are non-finite or do not reconcile to positive fill/exit prices and their original recorded costs fail closed before metrics. Evidence is isolated by fingerprints of the strategy, indicators, paper-execution code, news/model version and action, holding period, bracket rules, risk percentage, portfolio slots, entry validity, and cost assumption, so old implementations cannot validate a new plan. Validation requires at least 30 closed trades in one exact plan across at least five symbols and 90 calendar days, at least 60% positive symbols, positive cost-adjusted expectancy, profit factor of 1.2, and drawdown within 15%.

The execution dashboard reloads the agent result and model pack whenever research refreshes. Its server rejects manual live orders without the exact `LIVE SYMBOL` confirmation and rejects every order until the current exact plan passes forward paper validation, the candidate and news are current, and the submitted bracket matches the published symbol, stock contract, entry, stop, target, duration, and risk budget. The server independently requires matching agent/model timestamps, the same fixed 20-stock universe and exact configuration, recognized fingerprinted real-data provenance, an exposed traceable final holdout, enabled/pass status in both artifacts, and a per-plan paper record that still satisfies all 30-trade, five-symbol, 90-day, consistency, expectancy, profit-factor, and drawdown thresholds. Research and model-pack risk settings above 1% are rejected at the server boundary. Every live order requires fresh broker P&L and bid/ask evidence, available funds, no position or open order in the contract, a spread at or below 20 bps, and daily loss above -2%. Position risk is recalculated from the submitted quantity, published stop distance, and current IBKR net liquidation value; unavailable evidence, mixed bracket contracts, a changed time-in-force, excess quantity, or another live submission already in flight fails closed. Full auto additionally permits only one automated intent per New York market day. The server rebuilds the broker payload from validated fields so unreviewed request properties cannot change execution behavior. Only responses in which IBKR acknowledges every returned order with an order ID enter the dashboard's submitted state; failed, malformed, and precautionary-warning responses remain unsubmitted. It does not expose a route that acknowledges IBKR precautionary warnings. Agent results and their embedded news approval expire after 24 hours, and news approval cannot predate the exact research snapshot it reviews; candidate signals expire after five calendar days. News refreshes with every agent run and hourly while the dashboard is open; only symbol/company-relevant headlines from the last three days count, and unavailable news reduces rather than approves a setup. News and every existing account, quote, model, learning, fee, and IBKR gate can still reduce or reject a setup.

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
