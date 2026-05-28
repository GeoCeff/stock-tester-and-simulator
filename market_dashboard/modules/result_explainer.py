"""Plain-English explanations for strategy results."""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from .strategies import buy_hold_equity
except ImportError:
    from modules.strategies import buy_hold_equity


def _total_return(equity: pd.Series) -> float:
    equity = pd.to_numeric(equity, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(equity) < 2 or equity.iloc[0] == 0:
        return 0.0
    return (equity.iloc[-1] / equity.iloc[0] - 1) * 100


def explain_strategy_result(
    backtest_data: dict,
    close: pd.Series,
    data_status: dict | None = None,
    benchmark_close: pd.Series | None = None,
    benchmark_label: str = "SPY",
    fee_pct: float = 0.0,
) -> str:
    """Return a concise, plain-English interpretation of a backtest."""
    if not backtest_data or "equity" not in backtest_data:
        return "No result is available yet."

    equity = backtest_data["equity"]
    strategy_return = _total_return(equity)
    buy_hold = buy_hold_equity(close.reindex(equity.index).dropna(), initial_equity=float(equity.iloc[0]))
    buy_hold_return = _total_return(buy_hold)
    drawdown = float(backtest_data.get("max_drawdown", 0.0))
    trades = backtest_data.get("trades", []) or []
    trade_count = len(trades)

    if strategy_return > buy_hold_return:
        first = f"This strategy beat buy-and-hold by {strategy_return - buy_hold_return:.1f} percentage points."
    elif strategy_return < buy_hold_return:
        first = f"This strategy trailed buy-and-hold by {buy_hold_return - strategy_return:.1f} percentage points."
    else:
        first = "This strategy finished roughly in line with buy-and-hold."

    notes = [first]
    if drawdown <= -25:
        notes.append("The drawdown was large, so the return should be judged against a difficult holding experience.")
    elif drawdown <= -10:
        notes.append("The drawdown was meaningful, so risk matters as much as the headline return.")
    else:
        notes.append("The drawdown stayed relatively contained for this test window.")

    if trade_count == 0:
        notes.append("No completed trades were generated, so this run is mostly a signal validation check.")
    elif trade_count < 10:
        notes.append("The trade sample is small, so treat the result as exploratory rather than reliable.")
    else:
        notes.append("The trade sample is large enough to review patterns, but it is still not proof of future performance.")

    if fee_pct > 0 and trade_count > 0:
        estimated_fee_drag = trade_count * fee_pct * 2 * 100
        if estimated_fee_drag >= 1:
            notes.append(f"Estimated round-trip fees created about {estimated_fee_drag:.1f}% of gross drag across completed trades.")
        else:
            notes.append("Fees were included, but they did not dominate the result in this run.")

    if benchmark_close is not None and not benchmark_close.empty:
        benchmark = buy_hold_equity(benchmark_close.reindex(equity.index).dropna(), initial_equity=float(equity.iloc[0]))
        benchmark_return = _total_return(benchmark)
        notes.append(f"Against {benchmark_label}, the strategy return differed by {strategy_return - benchmark_return:.1f} percentage points.")

    if data_status:
        if data_status.get("status") == "demo":
            notes.append("This used demo data, so the result is illustrative only.")
        elif data_status.get("status") == "partial":
            notes.append("This used partial market data, so unavailable symbols were excluded from the analysis.")

    return " ".join(notes)
