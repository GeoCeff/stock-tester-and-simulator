import pandas as pd
import pytest

from market_dashboard.modules.data import demo_market_data, get_ticker_frame
from market_dashboard.modules.quant_lab import QuantLabError, run_quant_lab_strategy
from market_dashboard.modules.strategy_sandbox import (
    StrategyExecutionError,
    StrategyValidationError,
    execute_strategy_code,
    validate_strategy_code,
)
from market_dashboard.modules.strategy_templates import get_template_code, template_names


def _ticker_frame(rows=320):
    end = pd.Timestamp("2025-04-01")
    start = end - pd.offsets.BDay(rows)
    data = demo_market_data(["AAPL"], start=start, end=end, interval="1d")
    return get_ticker_frame(data, "AAPL")


def _config():
    return {
        "position_type": "Fixed",
        "holding_period": 0,
        "fee_pct": 0.001,
        "interval": "1d",
        "initial_capital": 10_000,
        "risk_free_rate": 0.02,
    }


def test_valid_template_runs_through_backtest_engine():
    result = run_quant_lab_strategy(
        get_template_code("RSI mean reversion"),
        _ticker_frame(),
        _config(),
        timeout_seconds=5,
    )

    assert len(result["equity"]) > 10
    assert result["validation"].output_kind == "buy/sell tuple"
    assert {"total_return", "sharpe_ratio", "max_drawdown", "win_rate"}.issubset(result)


def test_at_least_three_templates_run_on_demo_data():
    frame = _ticker_frame()

    for name in template_names()[:3]:
        result = run_quant_lab_strategy(get_template_code(name), frame, _config(), timeout_seconds=5)
        assert len(result["signals"]) == len(result["strategy_data"])


def test_missing_strategy_function_is_rejected():
    with pytest.raises(StrategyValidationError, match="strategy"):
        validate_strategy_code("def not_strategy(data):\n    return data['close'] > 0\n")


def test_imports_and_blocked_builtins_are_rejected():
    with pytest.raises(StrategyValidationError, match="Import"):
        validate_strategy_code("import os\n\ndef strategy(data):\n    return data['close'] > 0\n")

    with pytest.raises(StrategyValidationError, match="eval"):
        validate_strategy_code("def strategy(data):\n    return eval('1 + 1')\n")

    with pytest.raises(StrategyValidationError, match="open"):
        validate_strategy_code("def strategy(data):\n    return open('x.txt')\n")


def test_filesystem_style_dataframe_writes_are_rejected():
    code = "def strategy(data):\n    data.to_csv('signals.csv')\n    return data['close'] > 0\n"

    with pytest.raises(StrategyValidationError, match="to_csv"):
        validate_strategy_code(code)


def test_mismatched_signal_lengths_are_rejected():
    code = """def strategy(data):
    buy = data["close"].iloc[:-1] > 0
    sell = data["close"] < 0
    return buy, sell
"""

    with pytest.raises(QuantLabError, match="length"):
        run_quant_lab_strategy(code, _ticker_frame(), _config(), timeout_seconds=5)


def test_slow_strategy_times_out():
    data = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    code = """def strategy(data):
    while True:
        pass
    return data["close"] > 0
"""

    with pytest.raises(StrategyExecutionError, match="timed out"):
        execute_strategy_code(code, data, timeout_seconds=0.5)
