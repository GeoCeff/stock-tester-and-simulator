import pandas as pd

from market_dashboard.modules.strategies import BullPullbackStrategy, LowVolatilityTrendStrategy, MacdTrendStrategy, Strategy


class FixedSignalStrategy(Strategy):
    def generate_signals(self, price, indicators_dict):
        return indicators_dict["signals"].reindex(price.index).fillna(0.0)


def test_bull_pullback_waits_one_bar_and_exits_when_stretched():
    index = pd.date_range("2026-01-01", periods=5, freq="B")
    indicators = {
        "ma50": pd.Series([2, 2, 2, 2, 2], index=index),
        "ma200": pd.Series([1, 1, 1, 1, 1], index=index),
        "rsi": pd.Series([35, 42, 55, 72, 65], index=index),
    }

    signal = BullPullbackStrategy().generate_signals(pd.Series(range(5), index=index), indicators)

    assert signal.tolist() == [0, 0, 1, 1, 0]


def test_macd_trend_uses_only_prior_bar_information():
    index = pd.date_range("2026-01-01", periods=40, freq="B")
    price = pd.Series([*range(100, 139), 1], index=index)
    indicators = {"ma200": pd.Series(50, index=index)}

    signal = MacdTrendStrategy().generate_signals(price, indicators)

    assert signal.iloc[-1] == 1


def test_low_volatility_trend_waits_for_below_normal_volatility():
    index = pd.date_range("2024-01-01", periods=420, freq="B")
    returns = pd.Series(([0.02, -0.018] * 150) + ([0.001] * 120), index=index)
    price = 100 * (1 + returns).cumprod()

    signal = LowVolatilityTrendStrategy().generate_signals(
        price,
        {"ma200": price.rolling(200).mean()},
    )

    assert signal.iloc[:200].sum() == 0
    assert signal.iloc[-1] == 1


def test_no_signals_keeps_equity_flat_and_no_trades():
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.Series([100.0, 101.0, 102.0, 103.0], index=index)
    signals = pd.Series([0.0, 0.0, 0.0, 0.0], index=index)

    result = FixedSignalStrategy().compute_positions_and_equity(signals, close, initial_equity=1000)

    assert result["trades"] == []
    assert result["position"].sum() == 0.0
    assert result["equity"].iloc[-1] == 1000.0


def test_holding_period_exit_records_trade_and_fee():
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.Series([100.0, 105.0, 110.0, 120.0], index=index)
    signals = pd.Series([1.0, 1.0, 1.0, 1.0], index=index)

    result = FixedSignalStrategy(holding_period=2, fee_pct=0.01).compute_positions_and_equity(
        signals,
        close,
        initial_equity=1000,
    )

    assert len(result["trades"]) == 1
    assert result["entries"].iloc[0] == 1.0
    assert result["exits"].iloc[2] == 1.0
    assert result["trades"][0]["entry_price"] == 100.0
    assert result["trades"][0]["exit_price"] == 110.0
    assert result["daily_return"].iloc[0] == -0.01
    assert result["daily_return"].iloc[2] < close.pct_change().iloc[2]


def test_dynamic_position_size_is_clipped_to_valid_range():
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.Series([100.0, 101.0, 102.0, 103.0], index=index)
    signals = pd.Series([-1.0, 0.5, 1.5, 0.0], index=index)

    result = FixedSignalStrategy(position_type="dynamic").compute_positions_and_equity(
        signals,
        close,
        initial_equity=1000,
    )

    assert result["position"].min() >= 0.0
    assert result["position"].max() <= 1.0
    assert result["entries"].iloc[1] == 0.5
