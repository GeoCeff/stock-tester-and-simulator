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
    "min_positive_symbol_ratio": 0.60,
    "max_drawdown": 0.15,
}
DEFAULT_AGENT_RESULT_PATH = (
    Path(__file__).resolve().parents[2] / "execution_dashboard" / "data" / "research_agent.json"
)
DEFAULT_PAPER_LEDGER_PATH = (
    Path(__file__).resolve().parents[2] / "execution_dashboard" / "data" / "research_paper.json"
)
ENTRY_VALID_BARS = 3


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
                if not stop < entry < target:
                    index += 1
                    continue
                exit_index = min(fill_index + config["holding_period"], end) - 1
                exit_price = None
                for row in range(fill_index, exit_index + 1):
                    if float(frame["Low"].iloc[row]) <= stop:
                        exit_index, exit_price = row, stop
                        break
                    if float(frame["High"].iloc[row]) >= target:
                        exit_index, exit_price = row, target
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
                "status": "PENDING_NEWS_AND_LIVE_GATES",
            })
    return rows


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

    current_candidates = {
        (entry["symbol"], entry["style"]): entry
        for entry in result["entries"]
    }
    still_open = []
    for position in ledger["positions"]:
        candidate = current_candidates.get((position["symbol"], position["style"]))
        if not position.get("entry_date") and (not candidate or candidate.get("news_action") == "reject"):
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
            if not position["stop"] < position["entry"] < position["target"]:
                ledger["cancelled"].append({**position, "reason": "opening gap invalidated bracket"})
                continue
        holding = frame.loc[frame.index >= pd.Timestamp(position["entry_date"])].head(int(position["max_hold"]))
        exit_price = None
        exit_reason = ""
        exit_date = None
        for date, bar in holding.iterrows():
            if float(bar["Low"]) <= position["stop"]:
                exit_price, exit_reason = position["stop"], "stop"
            elif float(bar["High"]) >= position["target"]:
                exit_price, exit_reason = position["target"], "target"
            elif date == holding.index[-1] and len(holding) >= position["max_hold"]:
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

    by_style = {}
    for style in STYLE_CONFIG:
        rows = [row for row in ledger["closed"] if row["style"] == style]
        returns = np.asarray([row["return"] for row in rows], dtype=float)
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        equity = pd.Series((1 + returns).cumprod())
        max_drawdown = float((equity / equity.cummax() - 1).min()) if not equity.empty else 0.0
        profit_factor = float(wins.sum() / abs(losses.sum())) if losses.size else (999.0 if wins.size else 0.0)
        expectancy = float(returns.mean()) if returns.size else 0.0
        by_style[style] = {
            "status": "validated" if len(rows) >= 30 and expectancy >= 0.001 and profit_factor >= 1.2 and max_drawdown >= -0.15 else "warming_up",
            "closed_trades": len(rows),
            "expectancy": expectancy,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
        }
    validated_styles = [style for style, summary in by_style.items() if summary["status"] == "validated"]
    ledger["summary"] = {
        "status": "validated" if validated_styles else "warming_up",
        "closed_trades": len(ledger["closed"]),
        "validated_styles": validated_styles,
        "by_style": by_style,
    }
    ledger["updated_at"] = result["created_at"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return ledger["summary"]


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
            "metrics": {
                "development": winner["development"],
                "final_holdout": winner["final"],
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
