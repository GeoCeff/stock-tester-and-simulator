"""Quant Lab helpers for running custom strategy signals through the app engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

try:
    from .indicators import bollinger, macd, moving_averages, rsi
    from .strategies import Strategy
    from .strategy_sandbox import StrategySandboxResult, execute_strategy_code
except ImportError:
    from modules.indicators import bollinger, macd, moving_averages, rsi
    from modules.strategies import Strategy
    from modules.strategy_sandbox import StrategySandboxResult, execute_strategy_code


class QuantLabError(ValueError):
    """Raised when Quant Lab input or strategy output is invalid."""


@dataclass(frozen=True)
class QuantLabValidation:
    """Validation metadata for a Quant Lab run."""

    output_kind: str
    signal_count: int
    rows_used: int
    warnings: tuple[str, ...] = ()


class CustomSignalStrategy(Strategy):
    """Strategy wrapper that feeds precomputed custom signals to the engine."""

    def __init__(self, signals: pd.Series, holding_period=0, position_type="fixed", fee_pct=0.0):
        super().__init__(holding_period=holding_period, position_type=position_type, fee_pct=fee_pct)
        self._signals = signals

    def generate_signals(self, price, indicators_dict):
        return self._signals.reindex(price.index).fillna(0.0)


def build_strategy_data(ticker_data: pd.DataFrame) -> pd.DataFrame:
    """Create the DataFrame exposed to user strategy code."""
    if not isinstance(ticker_data, pd.DataFrame) or ticker_data.empty:
        raise QuantLabError("No ticker data is available for Quant Lab.")

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in ticker_data.columns]
    if missing:
        raise QuantLabError(f"Ticker data is missing required columns: {missing}.")

    close = pd.to_numeric(ticker_data["Close"], errors="coerce")
    ma50, ma200 = moving_averages(close)
    rsi_values = rsi(close)
    macd_line, macd_signal = macd(close)
    bb_upper, bb_lower = bollinger(close)

    strategy_data = pd.DataFrame(index=ticker_data.index)
    strategy_data["open"] = pd.to_numeric(ticker_data["Open"], errors="coerce")
    strategy_data["high"] = pd.to_numeric(ticker_data["High"], errors="coerce")
    strategy_data["low"] = pd.to_numeric(ticker_data["Low"], errors="coerce")
    strategy_data["close"] = close
    strategy_data["volume"] = pd.to_numeric(ticker_data["Volume"], errors="coerce")
    strategy_data["return"] = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    strategy_data["ma50"] = ma50
    strategy_data["ma200"] = ma200
    strategy_data["rsi"] = rsi_values
    strategy_data["macd"] = macd_line
    strategy_data["macd_signal"] = macd_signal
    strategy_data["bb_upper"] = bb_upper
    strategy_data["bb_lower"] = bb_lower
    strategy_data["rolling_high_20"] = strategy_data["high"].rolling(20).max()
    strategy_data["rolling_low_20"] = strategy_data["low"].rolling(20).min()

    strategy_data = strategy_data.replace([np.inf, -np.inf], np.nan)
    if len(strategy_data.dropna(subset=["close"])) < 10:
        raise QuantLabError("Quant Lab needs at least 10 usable close prices.")

    return strategy_data


def _coerce_output_series(value: Any, index: pd.Index, label: str) -> pd.Series:
    """Coerce strategy output into a Series with the input index."""
    if isinstance(value, pd.Series):
        series = value.copy()
    elif isinstance(value, (list, tuple, np.ndarray)):
        series = pd.Series(value)
    else:
        raise QuantLabError(f"{label} must be a pandas Series, list, tuple, or array.")

    if len(series) != len(index):
        raise QuantLabError(f"{label} length must match the input data length.")

    series.index = index
    return series


def _coerce_boolean_signal(value: Any, index: pd.Index, label: str) -> pd.Series:
    """Coerce a returned buy/sell output to a boolean Series."""
    series = _coerce_output_series(value, index, label)
    non_null = series.dropna()
    if non_null.empty:
        raise QuantLabError(f"{label} cannot be empty or all null.")

    if non_null.map(lambda item: isinstance(item, (bool, np.bool_))).all():
        return series.fillna(False).astype(bool)

    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().empty:
        raise QuantLabError(f"{label} must be boolean or numeric.")
    return numeric.fillna(0.0) != 0.0


def _position_from_buy_sell(buy: pd.Series, sell: pd.Series) -> pd.Series:
    """Convert entry/exit signals into a held-position Series."""
    position = pd.Series(0.0, index=buy.index, dtype=float)
    in_position = False
    for idx in buy.index:
        if bool(sell.loc[idx]):
            in_position = False
        if bool(buy.loc[idx]):
            in_position = True
        position.loc[idx] = 1.0 if in_position else 0.0
    return position


def signals_from_strategy_output(
    output: Any,
    index: pd.Index,
    shift_signals: bool = True,
) -> tuple[pd.Series, QuantLabValidation]:
    """Normalize allowed strategy return shapes into backtest-ready signals."""
    output_kind = ""

    if isinstance(output, (tuple, list)) and len(output) == 2:
        buy = _coerce_boolean_signal(output[0], index, "buy")
        sell = _coerce_boolean_signal(output[1], index, "sell")
        signal = _position_from_buy_sell(buy, sell)
        output_kind = "buy/sell tuple"
    elif isinstance(output, pd.DataFrame):
        lower_columns = {str(column).lower(): column for column in output.columns}
        if "position" in lower_columns:
            signal = _coerce_output_series(output[lower_columns["position"]], index, "position")
            output_kind = "position DataFrame"
        elif {"buy", "sell"}.issubset(lower_columns):
            buy = _coerce_boolean_signal(output[lower_columns["buy"]], index, "buy")
            sell = _coerce_boolean_signal(output[lower_columns["sell"]], index, "sell")
            signal = _position_from_buy_sell(buy, sell)
            output_kind = "buy/sell DataFrame"
        else:
            raise QuantLabError("Returned DataFrame must include buy/sell columns or a position column.")
    elif isinstance(output, pd.Series):
        if str(output.name or "").lower() != "position":
            raise QuantLabError("Returned Series must be named 'position'.")
        signal = _coerce_output_series(output, index, "position")
        output_kind = "position Series"
    else:
        raise QuantLabError("Strategy must return (buy, sell), a buy/sell DataFrame, or a Series named position.")

    signal = pd.to_numeric(signal, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if signal.dropna().empty:
        raise QuantLabError("Strategy output cannot be empty or all null.")
    signal = signal.clip(lower=0.0, upper=1.0)

    if shift_signals:
        signal = signal.shift(1).fillna(0.0)

    signal_count = int((signal > 0).sum())
    warnings = []
    if signal_count == 0:
        warnings.append("No long exposure was generated. The simulation will stay in cash.")

    return signal, QuantLabValidation(
        output_kind=output_kind,
        signal_count=signal_count,
        rows_used=len(index),
        warnings=tuple(warnings),
    )


def run_quant_lab_strategy(
    code: str,
    ticker_data: pd.DataFrame,
    config: dict,
    timeout_seconds: float = 2.0,
    max_rows: int = 1_500,
) -> dict:
    """Run custom strategy code and return app-compatible backtest output."""
    strategy_data = build_strategy_data(ticker_data)
    if len(strategy_data) > max_rows:
        strategy_data = strategy_data.tail(max_rows).copy()

    sandbox_result: StrategySandboxResult = execute_strategy_code(
        code,
        strategy_data,
        timeout_seconds=timeout_seconds,
        max_rows=max_rows,
    )
    signals, validation = signals_from_strategy_output(sandbox_result.output, strategy_data.index)

    close = strategy_data["close"].dropna()
    signals = signals.reindex(close.index).fillna(0.0)

    strategy = CustomSignalStrategy(
        signals=signals,
        holding_period=int(config.get("holding_period", 0)),
        position_type=str(config.get("position_type", "Fixed")).lower(),
        fee_pct=float(config.get("fee_pct", 0.0)),
    )
    backtest = strategy.compute_positions_and_equity(
        signals,
        close,
        initial_equity=float(config.get("initial_capital", 100.0)),
    )
    metrics = strategy.compute_metrics(
        backtest["equity"],
        backtest["daily_return"],
        interval=str(config.get("interval", "1d")),
        risk_free_rate=float(config.get("risk_free_rate", 0.02)),
    )

    return {
        **backtest,
        **metrics,
        "signals": signals,
        "strategy_data": strategy_data,
        "validation": validation,
        "elapsed_seconds": sandbox_result.elapsed_seconds,
        "rows_used": sandbox_result.rows_used,
    }
