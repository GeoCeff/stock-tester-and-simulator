"""Bounded walk-forward strategy search for the execution dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .data import get_ticker_frame
from .indicators import bollinger, moving_averages, rsi
from .bot_model_pack import build_model_pack, write_model_pack
from .strategies import BollingerBandsStrategy, MovingAverageCrossover, RSIStrategy, TrendMomentumStrategy


STYLE_CONFIG = {
    "OVERNIGHT_1D": {"holding_period": 1, "min_probability": 0.55, "stop_atr": 1.2, "target_r": 1.6, "risk_pct": 0.003},
    "SWING_5D": {"holding_period": 5, "min_probability": 0.56, "stop_atr": 2.0, "target_r": 2.0, "risk_pct": 0.005},
    "SWING_20D": {"holding_period": 20, "min_probability": 0.58, "stop_atr": 2.5, "target_r": 2.5, "risk_pct": 0.005},
}
STRATEGIES = {
    "ma_crossover": MovingAverageCrossover,
    "trend_momentum": TrendMomentumStrategy,
    "rsi_threshold": lambda **kwargs: RSIStrategy(mode="threshold", **kwargs),
    "rsi_mean_reversion": lambda **kwargs: RSIStrategy(mode="mean_reversion", **kwargs),
    "bollinger": BollingerBandsStrategy,
}
DEFAULT_CANDIDATES = [
    {"style": style, "strategy": strategy}
    for style in STYLE_CONFIG
    for strategy in STRATEGIES
]
DEFAULT_GATES = {
    "min_development_trades": 30,
    "min_final_trades": 10,
    "min_expectancy": 0.001,
    "min_profit_factor": 1.20,
    "min_positive_fold_ratio": 0.75,
    "max_drawdown": 0.15,
}
DEFAULT_AGENT_RESULT_PATH = (
    Path(__file__).resolve().parents[2] / "execution_dashboard" / "data" / "research_agent.json"
)


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


def _accept(evaluation, gates):
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
    return not failures, "; ".join(failures) or "development and untouched final holdout passed"


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
                "status": "PENDING_NEWS_AND_LIVE_GATES",
            })
    return rows


def run_research_loop(data, universe, *, candidates=None, folds=4, warmup=200, cost_bps_per_side=10, gates=None):
    """Select on development data, then expose only each winner to the final holdout."""
    universe = [str(symbol).strip().upper() for symbol in universe if str(symbol).strip()]
    if not universe:
        raise ValueError("universe required")
    if folds < 4:
        raise ValueError("at least four folds required to preserve a final holdout")
    gates = {**DEFAULT_GATES, **(gates or {})}
    candidates = candidates or DEFAULT_CANDIDATES
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
    selected = {}
    for style in STYLE_CONFIG:
        ranked = sorted(
            (row for row in development_evaluations if row["style"] == style),
            key=lambda row: row["score"],
            reverse=True,
        )
        if not ranked:
            continue
        viable = [row for row in ranked if _accept(row, gates)[0]]
        if not viable:
            winner = ranked[0]
            winner["accepted"] = False
            winner["reason"] = "no candidate passed development validation: " + _accept(winner, gates)[1]
            selected[style] = winner
            continue
        winner = evaluate_candidate(
            data,
            universe,
            {"style": style, "strategy": viable[0]["strategy"]},
            folds=folds,
            warmup=warmup,
            cost_bps_per_side=cost_bps_per_side,
        )
        winner["accepted"], winner["reason"] = _accept(winner, gates)
        selected[style] = winner

    styles = {
        "DAY_TRADE": {
            "enabled": False,
            "acceptance": {"status": "reject", "reason": "daily bars cannot validate day trading"},
        }
    }
    for style, config in STYLE_CONFIG.items():
        winner = selected.get(style)
        accepted = bool(winner and winner["accepted"])
        styles[style] = {
            **config,
            "enabled": accepted,
            "strategy": winner["strategy"] if winner else "",
            "metrics": {"development": winner["development"], "final_holdout": winner["final"]} if winner else {},
            "acceptance": {"status": "pass" if accepted else "reject", "reason": winner["reason"] if winner else "not evaluated"},
        }
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "universe": universe,
        "styles": styles,
        "entries": _latest_candidates(data, universe, selected),
        "evaluated_candidates": len(development_evaluations),
    }


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
