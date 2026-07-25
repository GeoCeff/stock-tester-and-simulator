# Stock Performance Analyzer

# Run It

Safe mode, no real trades:

```powershell
cd execution_dashboard
.\start_dashboard.ps1
```

Then open `http://127.0.0.1:8787`.

Manual Codex-assisted mode, safe dashboard plus copied operator prompt:

```powershell
.\start_manual_codex_session.ps1
```

If it says the dashboard is already running, just use the link. To stop or switch modes:

```powershell
.\stop_dashboard.ps1
```

Live confirm mode:

```powershell
.\stop_dashboard.ps1
.\start_live_dashboard.ps1
```

Full-auto mode, disabled unless you intentionally run this:

```powershell
.\stop_dashboard.ps1
.\start_full_auto_dashboard.ps1
```

AI research mode, prompts for an OpenAI API key for this server session only:

```powershell
.\stop_dashboard.ps1
.\start_ai_dashboard.ps1
```

For IBKR mode:

1. Start and log into the IBKR Client Portal Gateway.
2. Run the safe, live, or full-auto script above.
3. Click `Sync IBKR`.

If IBKR Desktop is open but `Sync IBKR` fails, open the `IBKR Checklist` tab. The app now probes common Client Portal Gateway/TWS/IB Gateway ports and shows the exact local blocker. IBKR Desktop by itself is not the Client Portal Gateway this dashboard uses.

Open `index.html` directly only for offline/sample mode.

Run the logic check:

```powershell
node self_check.js
```

CSV import expects:

```csv
symbol,date,open,high,low,close,volume
AAPL,2026-06-19,210,215,208,214,52000000
```

Current build: local dashboard, local IBKR Client Portal Gateway bridge, sample data, CSV import, IBKR auth/account/position/open-order/trade sync, stock contract lookup, IBKR top-of-book snapshot updates when market data is available, market regime, rankings, day/overnight/swing setups, sector/type grouping, strategy evaluation, fee-aware net edge, day-trade eligibility gates, daily max-loss/profit stops, risk gates, durable state/audit files, paper-order journal, live bracket submission when explicitly armed, IBKR manual bracket plan, IBKR account inputs, position/open-order imports, and trade-plan CSV export.

Semi-autonomous workflow:

1. Enter the symbols you want in `Universe`.
2. Click `Apply`.
3. Click `Sync IBKR`.
4. Click `Fetch IBKR Bars` if you want IBKR daily bars for those symbols.
5. Click `Live Quotes On` to poll IBKR snapshots every second.
6. Click `Auto Scout On` to continuously surface the best ready setup.

If bot mode is `PAPER`, Auto Scout can submit paper orders. If bot mode is `LIVE_WITH_CONFIRM`, Auto Scout only queues approval; it does not transmit live orders.
If bot mode is `FULL_AUTO`, Auto Scout can transmit the best ready setup without typed per-trade confirmation, but only when the server is started with the full-auto flag and every risk gate passes.

Live quote accuracy depends on IBKR Gateway, your market-data subscriptions, quote permissions, and IBKR snapshot/Web API behavior. The app polls every second and shows the latest values it receives.

Real-money mode:

```powershell
.\start_live_dashboard.ps1
```

Then:

1. Log into IBKR Client Portal Gateway.
2. Click `Sync IBKR`.
3. Set dashboard mode to `LIVE_WITH_CONFIRM`.
4. Set IBKR mode to `Live confirm`.
5. Type `LIVE SYMBOL` in the ticket, for example `LIVE AAPL`.
6. Click `Transmit Live`.

Live submission remains blocked unless the server was started with `ENABLE_LIVE_ORDERS=1`, IBKR is authenticated, an account is selected, conid is resolved, readiness gates pass, the typed confirmation matches the selected symbol, and the backend order-ticket validator accepts the ticket. Every live-order intent/response is appended to `data/audit.jsonl`.

Full-auto mode is disabled by default. To unlock it intentionally:

```powershell
.\start_full_auto_dashboard.ps1
```

Stop the safe server first because this uses the same local port. Then sync IBKR, set bot mode to `FULL_AUTO`, keep IBKR mode on `Live confirm`, set daily stops, and turn `Auto Scout On`. The server still rejects automated live orders unless `ENABLE_FULL_AUTO=1` is active.

Added validation layers:

- Auto Scout leaderboard.
- Event blocklist.
- Strategy validator by style.
- Probability calibration buckets.
- Prediction-vs-reality tracking with MFE/MAE and error.
- Trade learning graph with nodes/edges from closed trades.
- Adaptive sizing after weak/unvalidated performance.
- Tracked open/closed paper/live orders.
- Kill switch reasons.
- Replay/backtest summary.
- Rule optimizer.
- Post-trade attribution.
- What works / what fails dashboards.
- Model registry and feature-importance view.
- AI research snapshots with OpenAI API support when `OPENAI_API_KEY` is set.
- Slippage, quote-quality, and exposure views.

IBKR reality check:

- Safe mode (`start_dashboard.ps1`) never submits live IBKR orders.
- Live mode (`start_live_dashboard.ps1`) can submit real IBKR stock bracket orders through Client Portal Gateway after all dashboard and server confirmations pass.
- Full-auto mode (`start_full_auto_dashboard.ps1`) can submit real IBKR stock bracket orders from Auto Scout without typed per-trade confirmation after all full-auto locks and risk gates pass.
- Use exported plans for manual review in Trader Workstation whenever you do not want the app to transmit.
- Click `Sync IBKR` to import positions, open orders, and recent trades through Client Portal Gateway, or import CSVs manually if the gateway is unavailable.
- Test every order type and bracket behavior in IBKR paper/live-small size before scaling; IBKR order behavior can vary by account permission, market session, route, and instrument.
- Set `Day trading` to `Not eligible` when your account cannot day trade; the app will reject `Day trade` setups and keep swing/overnight setups available.
- Fee estimates default to IBKR Pro fixed-style U.S. stock estimates. Switch `Fee plan` to IBKR Lite if that matches your IBKR pricing; final fees can still vary from actual broker statements.
- Set `Max loss/day`, `Profit target/day`, and `Max profit/day` in IBKR Prep. When day P/L crosses any enabled limit, the app stops approving new paper/live trades.

Local persistence:

- `data/app_state.json` stores dashboard state, universe, account settings, tracked orders, and resolved conids.
- `data/audit.jsonl` stores an append-only local audit log of dashboard events and live-order submissions.
- The `data` folder is ignored by Git because it can contain account IDs and trading history.

Default IBKR Gateway URL is `https://localhost:5000/v1/api`. Override it:

```powershell
$env:IBKR_BASE="https://localhost:5001/v1/api"
.\start_dashboard.ps1
```
