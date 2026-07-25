"""Bounded walk-forward strategy search for the execution dashboard."""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .data import get_ticker_frame
from .indicators import bollinger, moving_averages, rsi
from .bot_model_pack import build_model_pack, write_model_pack
from .strategies import BollingerBandsStrategy, BullPullbackStrategy, LowVolatilityTrendStrategy, MacdTrendStrategy, MovingAverageCrossover, RSIStrategy, TrendMomentumStrategy


STYLE_CONFIG = {
    "OVERNIGHT_1D": {"holding_period": 1, "min_probability": 0.55, "stop_atr": 1.2, "target_r": 1.6, "risk_pct": 0.003},
    "SWING_5D": {"holding_period": 5, "min_probability": 0.56, "stop_atr": 2.0, "target_r": 2.0, "risk_pct": 0.005},
    "SWING_20D": {"holding_period": 20, "min_probability": 0.58, "stop_atr": 2.5, "target_r": 2.5, "risk_pct": 0.005},
}
STRATEGIES = {
    "ma_crossover": MovingAverageCrossover,
    "trend_momentum": TrendMomentumStrategy,
    "low_vol_trend": LowVolatilityTrendStrategy,
    "bull_pullback": BullPullbackStrategy,
    "macd_trend": MacdTrendStrategy,
    "rsi_threshold": lambda **kwargs: RSIStrategy(mode="threshold", **kwargs),
    "rsi_mean_reversion": lambda **kwargs: RSIStrategy(mode="mean_reversion", **kwargs),
    "bollinger": BollingerBandsStrategy,
}
DEFAULT_CANDIDATES = [
    {"style": style, "strategy": strategy}
    for style in STYLE_CONFIG
    for strategy in STRATEGIES
    if strategy != "low_vol_trend" or style == "SWING_20D"
]
DEFAULT_GATES = {
    "min_development_trades": 30,
    "min_final_trades": 10,
    "min_expectancy": 0.001,
    "min_profit_factor": 1.20,
    "min_positive_fold_ratio": 0.75,
    "min_positive_symbol_ratio": 0.60,
    "max_drawdown": 0.15,
}
DEFAULT_AGENT_RESULT_PATH = (
    Path(__file__).resolve().parents[2] / "execution_dashboard" / "data" / "research_agent.json"
)
DEFAULT_PAPER_LEDGER_PATH = (
    Path(__file__).resolve().parents[2] / "execution_dashboard" / "data" / "research_paper.json"
)
DEFAULT_RESEARCH_HISTORY_PATH = (
    Path(__file__).resolve().parents[2] / "execution_dashboard" / "data" / "research_history.jsonl"
)
ENTRY_VALID_BARS = 3
EXECUTION_PLAN_VERSION = "daily-bars-v2"
HOLDOUT_COOLDOWN_DAYS = 90


def _indicators(close):
    ma50, ma200 = moving_averages(close)
    upper, lower = bollinger(close)
    return {
        "ma50": ma50,
        "ma200": ma200,
        "rsi": rsi(close),
        "bb_upper": upper,
        "bb_lower": lower,
        "close": close,
    }


def _metrics(returns, trade_returns):
    returns = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    trades = np.asarray(trade_returns, dtype=float)
    wins = trades[trades > 0]
    losses = trades[trades < 0]
    equity = (1 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1 if not equity.empty else pd.Series(dtype=float)
    return {
        "trades": int(trades.size),
        "win_rate": float((trades > 0).mean()) if trades.size else 0.0,
        "expectancy": float(trades.mean()) if trades.size else 0.0,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.size else (999.0 if wins.size else 0.0),
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
        "total_return": float(equity.iloc[-1] - 1) if not equity.empty else 0.0,
    }


def _folds(length, folds, warmup):
    if folds < 3:
        raise ValueError("at least three folds required")
    if length < warmup + folds * 10:
        raise ValueError(f"need at least {warmup + folds * 10} rows")
    edges = np.linspace(warmup, length, folds + 1, dtype=int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(folds)]


def _bracket_exit(bar, entry, stop, target, *, fill_bar=False):
    """Conservative long-bracket exit from daily OHLC data."""
    opening = float(bar["Open"])
    if fill_bar and entry <= stop:
        return entry, "gap_stop"
    if float(bar["Low"]) <= stop:
        return min(opening, stop), "stop"
    if not fill_bar and float(bar["High"]) >= target:
        return target, "target"
    return None, ""


def evaluate_candidate(data, universe, candidate, *, folds=4, warmup=200, cost_bps_per_side=10):
    """Evaluate one fixed rule across chronological folds and symbols."""
    style = candidate["style"]
    strategy_name = candidate["strategy"]
    if style not in STYLE_CONFIG or strategy_name not in STRATEGIES:
        raise ValueError("unsupported candidate")

    config = STYLE_CONFIG[style]
    prepared = {}
    for symbol in universe:
        frame = get_ticker_frame(data, symbol)
        close = pd.to_numeric(frame.get("Close"), errors="coerce").dropna()
        if len(close) >= warmup + folds * 10:
            prepared[symbol] = (frame.reindex(close.index), close)
    if not prepared:
        raise ValueError("no symbol has enough data")

    usable_length = min(len(close) for _, close in prepared.values())
    fold_metrics = []
    for start, end in _folds(usable_length, folds, warmup):
        returns_by_symbol = {}
        trade_returns = []
        for symbol, (_, close) in prepared.items():
            close = close.iloc[-usable_length:]
            strategy = STRATEGIES[strategy_name](
                holding_period=config["holding_period"],
                position_type="fixed",
                fee_pct=cost_bps_per_side / 10_000,
            )
            signals = strategy.generate_signals(close.iloc[:end], _indicators(close.iloc[:end]))
            signals.iloc[:start] = 0.0
            result = strategy.compute_positions_and_equity(signals, close.iloc[:end])
            returns_by_symbol[symbol] = result["daily_return"].iloc[start:end]
            trade_returns.extend(
                trade["exit_price"] / trade["entry_price"] - 1 - 2 * cost_bps_per_side / 10_000
                for trade in result["trades"]
                if start <= trade["entry_idx"] < end
            )
        portfolio_returns = pd.concat(returns_by_symbol, axis=1).mean(axis=1)
        fold_metrics.append(_metrics(portfolio_returns, trade_returns))

    development_returns = pd.Series(
        [value for fold in fold_metrics[:-1] for value in [fold["total_return"]]],
        dtype=float,
    )
    development = {
        "trades": sum(fold["trades"] for fold in fold_metrics[:-1]),
        "win_rate": np.average(
            [fold["win_rate"] for fold in fold_metrics[:-1]],
            weights=[max(fold["trades"], 1) for fold in fold_metrics[:-1]],
        ),
        "expectancy": np.average(
            [fold["expectancy"] for fold in fold_metrics[:-1]],
            weights=[max(fold["trades"], 1) for fold in fold_metrics[:-1]],
        ),
        "profit_factor": min(fold["profit_factor"] for fold in fold_metrics[:-1]),
        "max_drawdown": min(fold["max_drawdown"] for fold in fold_metrics[:-1]),
        "total_return": float((1 + development_returns).prod() - 1),
        "positive_fold_ratio": float(np.mean([fold["expectancy"] > 0 for fold in fold_metrics[:-1]])),
    }
    score = (
        development["expectancy"] * 100
        + min(development["profit_factor"], 5)
        + development["positive_fold_ratio"]
        - abs(development["max_drawdown"])
    )
    return {**candidate, "development": development, "final": fold_metrics[-1], "folds": fold_metrics, "score": float(score)}


def _accept(evaluation, gates, *, validation_label="untouched final holdout"):
    development = evaluation["development"]
    final = evaluation["final"]
    failures = []
    if development["trades"] < gates["min_development_trades"]:
        failures.append("not enough development trades")
    if final["trades"] < gates["min_final_trades"]:
        failures.append("not enough final-holdout trades")
    if development["expectancy"] < gates["min_expectancy"] or final["expectancy"] < gates["min_expectancy"]:
        failures.append("expectancy was too small")
    if development["profit_factor"] < gates["min_profit_factor"] or final["profit_factor"] < gates["min_profit_factor"]:
        failures.append("profit factor failed")
    if development["positive_fold_ratio"] < gates["min_positive_fold_ratio"]:
        failures.append("fold consistency failed")
    if min(development["max_drawdown"], final["max_drawdown"]) < -gates["max_drawdown"]:
        failures.append("drawdown limit failed")
    return not failures, "; ".join(failures) or f"development and {validation_label} passed"


def evaluate_execution_plan(data, universe, candidate, *, folds=4, warmup=200, cost_bps_per_side=10):
    """Replay the published limit, stop, target, and maximum hold rules."""
    config = STYLE_CONFIG[candidate["style"]]
    strategy_name = candidate["strategy"]
    prepared = {}
    for symbol in universe:
        frame = get_ticker_frame(data, symbol).dropna(subset=["Open", "High", "Low", "Close"])
        if len(frame) >= warmup + folds * 10:
            prepared[symbol] = frame
    if not prepared:
        raise ValueError("no symbol has enough OHLC data")
    usable_length = min(map(len, prepared.values()))
    fold_metrics = []
    symbol_folds = {symbol: [] for symbol in prepared}
    for start, end in _folds(usable_length, folds, warmup):
        trade_returns = []
        for symbol, frame in prepared.items():
            symbol_trade_returns = []
            frame = frame.iloc[-usable_length:]
            close = pd.to_numeric(frame["Close"], errors="coerce")
            signals = STRATEGIES[strategy_name](
                holding_period=config["holding_period"],
                position_type="fixed",
                fee_pct=0,
            ).generate_signals(close, _indicators(close))
            previous = close.shift(1)
            atr = pd.concat([
                frame["High"] - frame["Low"],
                (frame["High"] - previous).abs(),
                (frame["Low"] - previous).abs(),
            ], axis=1).max(axis=1).rolling(14).mean()
            index = start
            while index < end:
                if signals.iloc[index] <= 0 or not np.isfinite(atr.iloc[index]):
                    index += 1
                    continue
                limit_entry = float(close.iloc[index])
                stop_distance = max(float(atr.iloc[index]) * config["stop_atr"], limit_entry * 0.004)
                stop = limit_entry - stop_distance
                target = limit_entry + stop_distance * config["target_r"]
                fill_index = next(
                    (
                        row
                        for row in range(index + 1, min(index + 1 + ENTRY_VALID_BARS, end))
                        if float(frame["Low"].iloc[row]) <= limit_entry
                    ),
                    None,
                )
                if fill_index is None:
                    index += 1
                    continue
                entry = min(float(frame["Open"].iloc[fill_index]), limit_entry)
                if not np.isfinite(entry) or entry <= 0 or entry >= target:
                    index += 1
                    continue
                exit_index = min(fill_index + config["holding_period"], end) - 1
                exit_price = None
                for row in range(fill_index, exit_index + 1):
                    exit_price, _ = _bracket_exit(
                        frame.iloc[row], entry, stop, target, fill_bar=row == fill_index
                    )
                    if exit_price is not None:
                        exit_index = row
                        break
                if exit_price is None and fill_index + config["holding_period"] <= end:
                    exit_price = float(close.iloc[exit_index])
                if exit_price is None:
                    break
                trade_return = exit_price / entry - 1 - 2 * cost_bps_per_side / 10_000
                trade_returns.append(trade_return)
                symbol_trade_returns.append(trade_return)
                index = exit_index + 1
            symbol_folds[symbol].append(_metrics(pd.Series(dtype=float), symbol_trade_returns))
        trades = np.asarray(trade_returns, dtype=float)
        wins = trades[trades > 0]
        losses = trades[trades < 0]
        fold_metrics.append({
            "trades": int(trades.size),
            "win_rate": float((trades > 0).mean()) if trades.size else 0.0,
            "expectancy": float(trades.mean()) if trades.size else 0.0,
            "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.size else (999.0 if wins.size else 0.0),
        })

    def development_summary(rows):
        return {
            "trades": sum(row["trades"] for row in rows),
            "win_rate": float(np.average(
                [row["win_rate"] for row in rows],
                weights=[max(row["trades"], 1) for row in rows],
            )),
            "expectancy": float(np.average(
                [row["expectancy"] for row in rows],
                weights=[max(row["trades"], 1) for row in rows],
            )),
            "profit_factor": min(row["profit_factor"] for row in rows),
            "positive_fold_ratio": float(np.mean([row["expectancy"] > 0 for row in rows])),
        }

    development_folds = fold_metrics[:-1]
    development = development_summary(development_folds)
    by_symbol = {
        symbol: {
            "development": development_summary(rows[:-1]),
            "final": rows[-1],
        }
        for symbol, rows in symbol_folds.items()
    }
    development["positive_symbol_ratio"] = float(np.mean([
        row["development"]["expectancy"] > 0 for row in by_symbol.values()
    ]))
    final = {
        **fold_metrics[-1],
        "positive_symbol_ratio": float(np.mean([
            row["final"]["expectancy"] > 0 for row in by_symbol.values()
        ])),
    }
    return {
        "development": development,
        "final": final,
        "folds": fold_metrics,
        "by_symbol": by_symbol,
    }


def _accept_execution_plan(evaluation, gates):
    development = evaluation["development"]
    final = evaluation["final"]
    failures = []
    if development["trades"] < gates["min_development_trades"] or final["trades"] < gates["min_final_trades"]:
        failures.append("execution plan had too few trades")
    if development["expectancy"] < gates["min_expectancy"] or final["expectancy"] < gates["min_expectancy"]:
        failures.append("execution-plan expectancy failed")
    if development["profit_factor"] < gates["min_profit_factor"] or final["profit_factor"] < gates["min_profit_factor"]:
        failures.append("execution-plan profit factor failed")
    if development["positive_fold_ratio"] < gates["min_positive_fold_ratio"]:
        failures.append("execution-plan fold consistency failed")
    if min(development["positive_symbol_ratio"], final["positive_symbol_ratio"]) < gates["min_positive_symbol_ratio"]:
        failures.append("execution-plan symbol consistency failed")
    return not failures, "; ".join(failures) or "published entry and bracket plan passed"


def _execution_score(evaluation):
    development = evaluation["development"]
    return (
        development["expectancy"] * 100
        + min(development["profit_factor"], 5)
        + development["positive_fold_ratio"]
        + development["positive_symbol_ratio"]
    )


def _common_length(data, universe):
    lengths = [len(pd.to_numeric(get_ticker_frame(data, symbol).get("Close"), errors="coerce").dropna()) for symbol in universe]
    return min(lengths) if lengths else 0


def _latest_candidates(data, universe, selected):
    rows = []
    for style, evaluation in selected.items():
        if not evaluation.get("accepted"):
            continue
        config = STYLE_CONFIG[style]
        for symbol in universe:
            frame = get_ticker_frame(data, symbol)
            close = pd.to_numeric(frame.get("Close"), errors="coerce").dropna()
            if len(close) < 200:
                continue
            strategy = STRATEGIES[evaluation["strategy"]](
                holding_period=config["holding_period"],
                position_type="fixed",
                fee_pct=0.0,
            )
            signal = strategy.generate_signals(close, _indicators(close))
            if signal.empty or float(signal.iloc[-1]) <= 0:
                continue
            aligned = frame.reindex(close.index)
            previous = close.shift(1)
            true_range = pd.concat(
                [
                    aligned["High"] - aligned["Low"],
                    (aligned["High"] - previous).abs(),
                    (aligned["Low"] - previous).abs(),
                ],
                axis=1,
            ).max(axis=1)
            atr = float(true_range.rolling(14).mean().iloc[-1])
            entry = float(close.iloc[-1])
            stop_distance = max(atr * config["stop_atr"], entry * 0.004)
            rows.append({
                "symbol": symbol,
                "side": "LONG",
                "style": style,
                "strategy": evaluation["strategy"],
                "signal_date": str(close.index[-1].date()),
                "entry": entry,
                "stop": entry - stop_distance,
                "target": entry + stop_distance * config["target_r"],
                "max_hold": config["holding_period"],
                "entry_valid_bars": ENTRY_VALID_BARS,
                "stop_atr": config["stop_atr"],
                "target_r": config["target_r"],
                "risk_pct": config["risk_pct"],
                "status": "PENDING_NEWS_AND_LIVE_GATES",
            })
    return rows


def _paper_plan_id(row, cost_bps_per_side):
    config = STYLE_CONFIG[row["style"]]
    holding_period = row.get("max_hold", row.get("holding_period", config["holding_period"]))
    strategy_fingerprint = hashlib.sha256(
        inspect.getsource(STRATEGIES[row["strategy"]]).encode("utf-8")
    ).hexdigest()[:12]
    return (
        f"{row['style']}:{row['strategy']}@{strategy_fingerprint}:hold={holding_period}:"
        f"stop={row.get('stop_atr', config['stop_atr']):g}atr:"
        f"target={row.get('target_r', config['target_r']):g}r:"
        f"entry={row.get('entry_valid_bars', ENTRY_VALID_BARS)}:"
        f"engine={EXECUTION_PLAN_VERSION}:"
        f"cost={cost_bps_per_side:g}bps:"
        f"news={row.get('news_version', 'news-unversioned')}"
    )


def update_paper_ledger(result, data, *, path=None, cost_bps_per_side=10):
    """Advance prior signals on real future bars, then queue today's new signals."""
    path = Path(path or DEFAULT_PAPER_LEDGER_PATH)
    if path.exists():
        ledger = json.loads(path.read_text(encoding="utf-8"))
        if (
            ledger.get("schema_version") != 1
            or not isinstance(ledger.get("positions"), list)
            or not isinstance(ledger.get("closed"), list)
        ):
            raise ValueError("invalid paper ledger")
    else:
        ledger = {"schema_version": 1, "positions": [], "closed": [], "cancelled": []}
    ledger.setdefault("cancelled", [])

    for entry in result["entries"]:
        entry["plan_id"] = _paper_plan_id(entry, cost_bps_per_side)
    current_candidates = {
        (entry["symbol"], entry["style"]): entry
        for entry in result["entries"]
    }
    still_open = []
    for position in ledger["positions"]:
        candidate = current_candidates.get((position["symbol"], position["style"]))
        if not position.get("plan_id") and candidate:
            position["plan_id"] = candidate["plan_id"]
        if not position.get("entry_date") and (
            not candidate
            or candidate.get("news_action") == "reject"
            or position.get("plan_id") != candidate["plan_id"]
        ):
            ledger["cancelled"].append({**position, "reason": "research or news gate withdrew pending entry"})
            continue
        frame = get_ticker_frame(data, position["symbol"])
        if not position.get("entry_date"):
            position.setdefault("limit_entry", candidate.get("entry"))
            position.setdefault("entry_valid_bars", candidate.get("entry_valid_bars", ENTRY_VALID_BARS))
        future = frame.loc[frame.index > pd.Timestamp(position["signal_date"])]
        if future.empty:
            still_open.append(position)
            continue
        if not position.get("entry_date"):
            if not position["limit_entry"]:
                ledger["cancelled"].append({**position, "reason": "legacy signal missing limit entry"})
                continue
            entry_window = future.head(int(position["entry_valid_bars"]))
            fill = next(
                (
                    (date, bar)
                    for date, bar in entry_window.iterrows()
                    if np.isfinite(float(bar["Low"])) and float(bar["Low"]) <= position["limit_entry"]
                ),
                None,
            )
            if not fill:
                if len(entry_window) >= position["entry_valid_bars"]:
                    ledger["cancelled"].append({**position, "reason": "limit entry expired"})
                else:
                    still_open.append(position)
                continue
            fill_date, fill_bar = fill
            position["entry_date"] = str(fill_date.date())
            position["entry"] = min(float(fill_bar["Open"]), float(position["limit_entry"]))
            if not np.isfinite(position["entry"]) or position["entry"] <= 0 or position["entry"] >= position["target"]:
                ledger["cancelled"].append({**position, "reason": "invalid fill price"})
                continue
        holding = frame.loc[frame.index >= pd.Timestamp(position["entry_date"])].head(int(position["max_hold"]))
        exit_price = None
        exit_reason = ""
        exit_date = None
        for date, bar in holding.iterrows():
            exit_price, exit_reason = _bracket_exit(
                bar,
                position["entry"],
                position["stop"],
                position["target"],
                fill_bar=date == pd.Timestamp(position["entry_date"]),
            )
            if not exit_reason and date == holding.index[-1] and len(holding) >= position["max_hold"]:
                exit_price, exit_reason = float(bar["Close"]), "time"
            if exit_reason:
                exit_date = str(date.date())
                break
        if not exit_reason:
            still_open.append(position)
            continue
        gross_return = exit_price / position["entry"] - 1
        ledger["closed"].append({
            **position,
            "exit": exit_price,
            "exit_date": exit_date,
            "exit_reason": exit_reason,
            "return": gross_return - 2 * cost_bps_per_side / 10_000,
        })

    existing = {
        (row["symbol"], row["style"], row["signal_date"])
        for row in [*still_open, *ledger["closed"]]
    }
    for entry in result["entries"]:
        key = (entry["symbol"], entry["style"], entry["signal_date"])
        matching = [
            row for row in still_open
            if (row["symbol"], row["style"], row["signal_date"]) == key
        ]
        if matching:
            for field in ("news_action", "news_status", "news", "news_reasons", "status"):
                if field in entry:
                    matching[0][field] = entry[field]
        elif (
            key not in existing
            and not any((row["symbol"], row["style"]) == key[:2] for row in still_open)
            and entry.get("news_action") != "reject"
        ):
            still_open.append({
                **entry,
                "limit_entry": entry["entry"],
                "entry": None,
                "entry_date": None,
            })
    rejected = [row for row in still_open if row.get("news_action") == "reject" and not row.get("entry_date")]
    ledger["cancelled"].extend({**row, "reason": "rejected by news gate"} for row in rejected)
    still_open = [row for row in still_open if row not in rejected]
    ledger["positions"] = still_open

    current_plan_ids = {entry["plan_id"] for entry in result["entries"]}
    for style, row in result.get("styles", {}).items():
        if style in STYLE_CONFIG and row.get("acceptance", {}).get("status") == "pass":
            current_plan_ids.add(_paper_plan_id({
                "style": style,
                **row,
                "news_version": result.get("news_version", "news-unversioned"),
            }, cost_bps_per_side))

    by_plan = {}
    plan_ids = {row.get("plan_id", "legacy-unversioned") for row in ledger["closed"]}
    for plan_id in sorted(plan_ids | current_plan_ids):
        rows = [row for row in ledger["closed"] if row.get("plan_id", "legacy-unversioned") == plan_id]
        returns = np.asarray([row["return"] for row in rows], dtype=float)
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        equity = pd.Series((1 + returns).cumprod())
        max_drawdown = float((equity / equity.cummax() - 1).min()) if not equity.empty else 0.0
        profit_factor = float(wins.sum() / abs(losses.sum())) if losses.size else (999.0 if wins.size else 0.0)
        expectancy = float(returns.mean()) if returns.size else 0.0
        by_plan[plan_id] = {
            "status": "validated" if len(rows) >= 30 and expectancy >= 0.001 and profit_factor >= 1.2 and max_drawdown >= -0.15 else "warming_up",
            "closed_trades": len(rows),
            "expectancy": expectancy,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
        }
    validated_plans = [
        plan_id for plan_id in current_plan_ids
        if by_plan.get(plan_id, {}).get("status") == "validated"
    ]
    ledger["summary"] = {
        "status": "validated" if validated_plans else "warming_up",
        "closed_trades": len(ledger["closed"]),
        "current_closed_trades": sum(by_plan[plan_id]["closed_trades"] for plan_id in current_plan_ids),
        "validated_plans": validated_plans,
        "by_plan": by_plan,
    }
    ledger["updated_at"] = result["created_at"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return ledger["summary"]


def run_research_loop(
    data,
    universe,
    *,
    candidates=None,
    folds=4,
    warmup=200,
    cost_bps_per_side=10,
    gates=None,
    excluded_holdout_trials=None,
):
    """Select on development data, then expose only each winner to the final holdout."""
    universe = [str(symbol).strip().upper() for symbol in universe if str(symbol).strip()]
    if not universe:
        raise ValueError("universe required")
    if folds < 4:
        raise ValueError("at least four folds required to preserve a final holdout")
    gates = {**DEFAULT_GATES, **(gates or {})}
    candidates = candidates or DEFAULT_CANDIDATES
    excluded_holdout_trials = set(excluded_holdout_trials or ())
    usable_length = _common_length(data, universe)
    final_start = _folds(usable_length, folds, warmup)[-1][0]
    common_dates = get_ticker_frame(data, universe[0]).dropna(subset=["Close"]).index[-usable_length:]
    development_data = data.loc[data.index < common_dates[final_start]]
    development_evaluations = [
        evaluate_candidate(
            development_data,
            universe,
            candidate,
            folds=folds - 1,
            warmup=warmup,
            cost_bps_per_side=cost_bps_per_side,
        )
        for candidate in candidates
    ]
    diagnostics = []
    diagnostics_by_candidate = {}
    for row in development_evaluations:
        signal_accepted, signal_reason = _accept(row, gates, validation_label="internal validation")
        diagnostic = {
            "style": row["style"],
            "strategy": row["strategy"],
            "score": row["score"],
            "signal_status": "pass" if signal_accepted else "reject",
            "signal_reason": signal_reason,
            "development": row["development"],
            "development_validation": row["final"],
            "execution_status": "not_evaluated",
            "execution_reason": "signal failed development validation" if not signal_accepted else "pending",
            "selected": False,
        }
        diagnostics.append(diagnostic)
        diagnostics_by_candidate[(row["style"], row["strategy"])] = diagnostic
    selected = {}
    for style in STYLE_CONFIG:
        ranked = sorted(
            (row for row in development_evaluations if row["style"] == style),
            key=lambda row: row["score"],
            reverse=True,
        )
        if not ranked:
            continue
        viable = [
            row
            for row in ranked
            if _accept(row, gates, validation_label="internal validation")[0]
        ]
        if not viable:
            winner = ranked[0]
            winner["accepted"] = False
            winner["exposed_to_final"] = False
            winner["reason"] = "no candidate passed development validation: " + _accept(
                winner, gates, validation_label="internal validation"
            )[1]
            selected[style] = winner
            continue
        executable = []
        for row in viable:
            execution_plan = evaluate_execution_plan(
                development_data,
                universe,
                {"style": style, "strategy": row["strategy"]},
                folds=folds - 1,
                warmup=warmup,
                cost_bps_per_side=cost_bps_per_side,
            )
            execution_accepted, execution_reason = _accept_execution_plan(execution_plan, gates)
            diagnostic = diagnostics_by_candidate[(style, row["strategy"])]
            diagnostic["execution_status"] = "pass" if execution_accepted else "reject"
            diagnostic["execution_reason"] = execution_reason
            diagnostic["execution_plan"] = {
                "development": execution_plan["development"],
                "development_validation": execution_plan["final"],
            }
            if execution_accepted:
                executable.append({
                    **row,
                    "selection_execution_plan": execution_plan,
                    "execution_score": _execution_score(execution_plan),
                })
        if not executable:
            winner = viable[0]
            winner["accepted"] = False
            winner["exposed_to_final"] = False
            winner["reason"] = "no candidate passed development execution validation"
            selected[style] = winner
            continue
        executable.sort(key=lambda row: row["execution_score"], reverse=True)
        eligible = [
            row
            for row in executable
            if (style, row["strategy"]) not in excluded_holdout_trials
        ]
        if not eligible:
            winner = executable[0]
            winner["accepted"] = False
            winner["exposed_to_final"] = False
            winner["reason"] = "recent rejected candidates remain in holdout cooldown"
            selected[style] = winner
            continue
        selection_winner = eligible[0]
        winner = evaluate_candidate(
            data,
            universe,
            {"style": style, "strategy": selection_winner["strategy"]},
            folds=folds,
            warmup=warmup,
            cost_bps_per_side=cost_bps_per_side,
        )
        winner["selection_evaluation"] = selection_winner
        winner["exposed_to_final"] = True
        signal_accepted, signal_reason = _accept(winner, gates)
        winner["execution_plan"] = evaluate_execution_plan(
            data,
            universe,
            {"style": style, "strategy": winner["strategy"]},
            folds=folds,
            warmup=warmup,
            cost_bps_per_side=cost_bps_per_side,
        )
        execution_accepted, execution_reason = _accept_execution_plan(winner["execution_plan"], gates)
        winner["accepted"] = signal_accepted and execution_accepted
        winner["reason"] = signal_reason if not signal_accepted else execution_reason
        selected[style] = winner
        diagnostics_by_candidate[(style, winner["strategy"])]["selected"] = True

    styles = {
        "DAY_TRADE": {
            "enabled": False,
            "acceptance": {"status": "reject", "reason": "daily bars cannot validate day trading"},
        }
    }
    for style, config in STYLE_CONFIG.items():
        winner = selected.get(style)
        accepted = bool(winner and winner["accepted"])
        exposed_to_final = bool(winner and winner.get("exposed_to_final"))
        selection_evaluation = winner.get("selection_evaluation", {}) if winner else {}
        styles[style] = {
            **config,
            "enabled": accepted,
            "strategy": winner["strategy"] if winner else "",
            "metrics": {
                "development": winner["development"],
                "development_validation": (
                    selection_evaluation.get("final", {})
                    if exposed_to_final
                    else winner["final"]
                ),
                "final_holdout": winner["final"] if exposed_to_final else {},
                "holdout_exposed": exposed_to_final,
                "execution_plan": winner.get("execution_plan", {}),
            } if winner else {},
            "acceptance": {"status": "pass" if accepted else "reject", "reason": winner["reason"] if winner else "not evaluated"},
        }
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "universe": universe,
        "styles": styles,
        "entries": _latest_candidates(data, universe, selected),
        "evaluated_candidates": len(development_evaluations),
        "development_diagnostics": diagnostics,
        "research_notes": {
            "what_worked": [
                f"{row['style']} {row['strategy']}: signal and execution plan passed development validation"
                for row in diagnostics
                if row["signal_status"] == "pass" and row["execution_status"] == "pass"
            ],
            "what_failed": [
                f"{row['style']} {row['strategy']}: "
                f"{row['signal_reason'] if row['signal_status'] == 'reject' else row['execution_reason']}"
                for row in diagnostics
                if row["signal_status"] == "reject" or row["execution_status"] == "reject"
            ],
            "holdout_results": [
                f"{style} {row['strategy']}: {row['reason']}"
                for style, row in selected.items()
                if row.get("exposed_to_final")
            ],
            "mistakes_avoided": [
                "unselected candidates were not exposed to the final holdout",
                "development-only validation folds are labeled separately from the final holdout",
                "selection ranks plans by executable development evidence, not signal score alone",
                "recently rejected rules are not repeatedly exposed to the same rolling holdout",
            ],
        },
    }


def recent_rejected_holdout_trials(*, path=None, now=None, cooldown_days=HOLDOUT_COOLDOWN_DAYS):
    """Return rejected strategy names still inside their next holdout trial cooldown."""
    path = Path(path or DEFAULT_RESEARCH_HISTORY_PATH)
    if not path.exists():
        return set()
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=cooldown_days)
    trials = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        created_at = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
        if created_at < cutoff:
            continue
        for style, row in record.get("styles", {}).items():
            # ponytail: strategy names are trial IDs; use a new name for materially changed rules.
            if row.get("holdout_exposed") and row.get("status") == "reject":
                trials.add((style, row.get("strategy", "")))
    return trials


def append_research_history(result, *, path=None, max_records=200):
    """Persist compact run lessons without mixing them into acceptance evidence."""
    path = Path(path or DEFAULT_RESEARCH_HISTORY_PATH)
    record = {
        "created_at": result["created_at"],
        "research_notes": result.get("research_notes", {}),
        "paper_evidence": result.get("paper_evidence", {}),
        "entries": [
            {
                key: entry.get(key)
                for key in ("symbol", "style", "strategy", "signal_date", "entry", "stop", "target", "news_action", "status", "plan_id")
            }
            for entry in result.get("entries", [])
        ],
        "styles": {
            style: {
                "strategy": row.get("strategy", ""),
                "status": row.get("acceptance", {}).get("status", "reject"),
                "reason": row.get("acceptance", {}).get("reason", "not evaluated"),
                "holdout_exposed": row.get("metrics", {}).get("holdout_exposed", False),
            }
            for style, row in result.get("styles", {}).items()
        },
    }
    existing = []
    if path.exists():
        existing = [
            line for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if existing and json.loads(existing[-1]).get("created_at") == result["created_at"]:
            return record
    lines = [*existing, json.dumps(record, sort_keys=True)][-max_records:]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)
    return record


def publish_research_result(result, *, model_pack_path=None, agent_result_path=None):
    """Publish one accepted/rejected research snapshot for the execution app."""
    pack = build_model_pack(result["styles"], result["universe"], created_at=result["created_at"])
    path = Path(agent_result_path or DEFAULT_AGENT_RESULT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    write_model_pack(pack, model_pack_path)
    return pack
