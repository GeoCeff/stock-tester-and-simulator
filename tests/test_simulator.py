import pandas as pd

from market_dashboard.modules.simulator import TradingSimulator


def _simulator_with_data():
    data = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [10.5, 11.5],
            "Low": [9.5, 10.5],
            "Close": [10.0, 11.0],
            "Volume": [1000, 1200],
        },
        index=pd.date_range("2024-01-01", periods=2),
    )
    simulator = TradingSimulator(initial_equity=100.0, transaction_fee=0.01)
    simulator.set_timeframe(data, "2024-01-01", "2024-01-03")
    return simulator


def test_max_affordable_quantity_accounts_for_fees():
    simulator = _simulator_with_data()

    assert simulator.max_affordable_quantity() == 9


def test_quantity_for_cash_fraction_is_fee_aware_and_clipped():
    simulator = _simulator_with_data()

    assert simulator.quantity_for_cash_fraction(0.5) == 4
    assert simulator.quantity_for_cash_fraction(2.0) == simulator.max_affordable_quantity()
    assert simulator.quantity_for_cash_fraction(-1.0) == 0


def test_buy_preview_does_not_mutate_state_and_shows_post_trade_values():
    simulator = _simulator_with_data()

    preview = simulator.preview_buy(5)

    assert preview["can_execute"] is True
    assert preview["fee"] == 0.5
    assert preview["cash_after"] == 49.5
    assert preview["shares_after"] == 5
    assert simulator.cash == 100.0
    assert simulator.total_shares() == 0


def test_sell_preview_is_guarded_when_no_shares_are_held():
    simulator = _simulator_with_data()

    preview = simulator.preview_sell(1)

    assert preview["can_execute"] is False
    assert "Insufficient shares" in preview["reason"]


def test_orders_record_buys_and_sells_separately_from_closed_trades():
    simulator = _simulator_with_data()

    assert simulator.execute_buy(5) is True
    assert simulator.execute_sell(2) is True

    assert [order["action"] for order in simulator.orders] == ["BUY", "SELL"]
    assert len(simulator.trades) == 1
    assert simulator.trades[0]["action"] == "SELL"
    assert simulator.total_shares() == 3
