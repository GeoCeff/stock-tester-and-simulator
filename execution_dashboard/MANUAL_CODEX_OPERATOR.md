# Manual Codex Operator Runbook

Use this when you want Codex to participate manually without OpenAI API automation.

## Start

```powershell
cd execution_dashboard
.\start_manual_codex_session.ps1
```

The script starts the safe dashboard if needed, opens `http://127.0.0.1:8787`, and copies a starter prompt for Codex.

## What Codex Should Do

- Inspect the dashboard, current bot pick, model status, AI research panel, gates, quote freshness, and risk limits.
- Use current web research only when asked for latest news/trends, and cite sources.
- Explain `pass`, `reduce`, or `reject` with concrete reasons.
- Suggest universe changes, event blocklist entries, paper-trade next steps, or backtester follow-up.
- Keep live-order and full-auto gates untouched.

## Manual Trading Loop

1. Start the dashboard with `start_manual_codex_session.ps1`.
2. Optional: start and log into IBKR Client Portal Gateway.
3. In the dashboard, click `Sync IBKR`.
4. Click `Load IBKR Bars` if you want real historical bars.
5. Click `Live Quotes On` if you want quote freshness checks.
6. Ask Codex to review the current setup, for example:

```text
Review the current dashboard pick. Check technicals, model/research status, quote freshness, and current news for the symbol. Give me pass/reduce/reject and what to do next.
```

7. Paper trade first. Review `Research`, `Model`, `IBKR Checklist`, and `Model/Data Health`.
8. Only use live confirm when you intentionally start `start_live_dashboard.ps1` and every app gate passes.

## Hard Rules

- No ChatGPT Plus/API automation is used in this mode.
- Do not paste API keys into Codex chat.
- Do not treat AI/news notes as a proven strategy.
- Codex advice cannot bypass dashboard, IBKR, quote freshness, model pack, account, or typed-confirmation gates.
- Full-auto stays locked unless you intentionally start `start_full_auto_dashboard.ps1`.
