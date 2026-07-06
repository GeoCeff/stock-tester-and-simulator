#!/usr/bin/env python3
"""
Comprehensive function testing script for Stock Backtester
Tests every function in all modules with various inputs to catch errors
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add the modules directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'market_dashboard'))

def test_data_module():
    """Test all functions in data.py"""
    print("Testing data.py functions...")

    from modules import data

    # Test download_data with valid inputs
    try:
        result = data.download_data(['AAPL'], '2023-01-01', '2023-12-31', '1d')
        if result is None:
            print("Γ¥î download_data failed with valid inputs")
        else:
            print("Γ£à download_data with single ticker")
    except Exception as e:
        print(f"Γ¥î download_data error: {e}")

    # Test with multiple tickers
    try:
        result = data.download_data(['AAPL', 'MSFT'], '2023-01-01', '2023-12-31', '1d')
        if result is None:
            print("Γ¥î download_data failed with multiple tickers")
        else:
            print("Γ£à download_data with multiple tickers")
    except Exception as e:
        print(f"Γ¥î download_data multiple tickers error: {e}")

    # Test with invalid inputs
    try:
        result = data.download_data([], '2023-01-01', '2023-12-31', '1d')
        if result is not None:
            print("Γ¥î download_data should fail with empty tickers")
        else:
            print("Γ£à download_data handles empty tickers")
    except Exception as e:
        print(f"Γ£à download_data correctly rejects empty tickers: {e}")

    # Test invalid dates
    try:
        result = data.download_data(['AAPL'], 'invalid', '2023-12-31', '1d')
        if result is not None:
            print("Γ¥î download_data should fail with invalid start date")
        else:
            print("Γ£à download_data handles invalid start date")
    except Exception as e:
        print(f"Γ£à download_data correctly rejects invalid start date: {e}")

    # Test invalid interval
    try:
        result = data.download_data(['AAPL'], '2023-01-01', '2023-12-31', 'invalid')
        if result is not None:
            print("Γ¥î download_data should fail with invalid interval")
        else:
            print("Γ£à download_data handles invalid interval")
    except Exception as e:
        print(f"Γ£à download_data correctly rejects invalid interval: {e}")

def test_indicators_module():
    """Test all functions in indicators.py"""
    print("\nTesting indicators.py functions...")

    from modules import indicators

    # Create test data
    dates = pd.date_range('2023-01-01', periods=300, freq='D')
    prices = pd.Series(np.random.randn(300).cumsum() + 100, index=dates)

    # Test moving_averages
    try:
        ma50, ma200 = indicators.moving_averages(prices)
        if ma50 is None or len(ma50) == 0:
            print("Γ¥î moving_averages failed")
        else:
            print("Γ£à moving_averages")
    except Exception as e:
        print(f"Γ¥î moving_averages error: {e}")

    # Test with insufficient data
    short_prices = prices[:10]
    try:
        ma50, ma200 = indicators.moving_averages(short_prices)
        if ma50 is not None:
            print("Γ¥î moving_averages should return None for insufficient data")
        else:
            print("Γ£à moving_averages handles insufficient data")
    except Exception as e:
        print(f"Γ¥î moving_averages insufficient data error: {e}")

    # Test rsi
    try:
        rsi_result = indicators.rsi(prices)
        if rsi_result is None or len(rsi_result) == 0:
            print("Γ¥î rsi failed")
        else:
            print("Γ£à rsi")
    except Exception as e:
        print(f"Γ¥î rsi error: {e}")

    # Test rsi with insufficient data
    try:
        rsi_result = indicators.rsi(short_prices)
        if rsi_result is not None and len(rsi_result) > 0:
            print("Γ¥î rsi should return empty series for insufficient data")
        else:
            print("Γ£à rsi handles insufficient data")
    except Exception as e:
        print(f"Γ¥î rsi insufficient data error: {e}")

    # Test macd
    try:
        macd_result = indicators.macd(prices)
        if macd_result is None:
            print("Γ¥î macd failed")
        else:
            print("Γ£à macd")
    except Exception as e:
        print(f"Γ¥î macd error: {e}")

    # Test bollinger
    try:
        bb_result = indicators.bollinger(prices)
        if bb_result is None:
            print("Γ¥î bollinger failed")
        else:
            print("Γ£à bollinger")
    except Exception as e:
        print(f"Γ¥î bollinger error: {e}")

def test_strategies_module():
    """Test all functions in strategies.py"""
    print("\nTesting strategies.py functions...")

    from modules import strategies, indicators

    # Create test data
    dates = pd.date_range('2023-01-01', periods=300, freq='D')
    prices = pd.Series(np.random.randn(300).cumsum() + 100, index=dates)

    # Calculate indicators
    ma50, ma200 = indicators.moving_averages(prices)
    rsi_val = indicators.rsi(prices)
    bb_upper, bb_lower = indicators.bollinger(prices)
    macd_val = indicators.macd(prices)

    indicators_dict = {
        'ma50': ma50,
        'ma200': ma200,
        'rsi': rsi_val,
        'bb_upper': bb_upper,
        'bb_lower': bb_lower,
        'close': prices,
        'bollinger': bb_upper,  # for compatibility
        'macd': macd_val
    }

    # Test MA Crossover Strategy
    try:
        strategy = strategies.MovingAverageCrossover()
        signals = strategy.generate_signals(prices, indicators_dict)
        if signals is None or len(signals) == 0:
            print("Γ¥î MA Crossover generate_signals failed")
        else:
            print("Γ£à MA Crossover generate_signals")

        result = strategy.compute_positions_and_equity(signals, prices)
        if result is None or 'equity' not in result:
            print("Γ¥î MA Crossover compute_positions_and_equity failed")
        else:
            print("Γ£à MA Crossover compute_positions_and_equity")
    except Exception as e:
        print(f"Γ¥î MA Crossover error: {e}")

    # Test RSI Strategy
    try:
        strategy = strategies.RSIStrategy()
        signals = strategy.generate_signals(prices, indicators_dict)
        if signals is None or len(signals) == 0:
            print("Γ¥î RSI generate_signals failed")
        else:
            print("Γ£à RSI generate_signals")
    except Exception as e:
        print(f"Γ¥î RSI Strategy error: {e}")

    # Test Bollinger Strategy
    try:
        strategy = strategies.BollingerBandsStrategy()
        signals = strategy.generate_signals(prices, indicators_dict)
        if signals is None or len(signals) == 0:
            print("Γ¥î Bollinger generate_signals failed")
        else:
            print("Γ£à Bollinger generate_signals")
    except Exception as e:
        print(f"Γ¥î Bollinger Strategy error: {e}")

    # Test compute_metrics
    try:
        daily_returns = prices.pct_change().dropna()
        equity_series = (1 + daily_returns).cumprod() * 100
        metrics = strategy.compute_metrics(equity_series, daily_returns)
        if metrics is None:
            print("Γ¥î compute_metrics failed")
        else:
            print("Γ£à compute_metrics")
    except Exception as e:
        print(f"Γ¥î compute_metrics error: {e}")

    # Test buy_hold_equity
    try:
        equity = strategies.buy_hold_equity(prices)
        if equity is None or len(equity) == 0:
            print("Γ¥î buy_hold_equity failed")
        else:
            print("Γ£à buy_hold_equity")
    except Exception as e:
        print(f"Γ¥î buy_hold_equity error: {e}")

def test_portfolio_module():
    """Test all functions in portfolio.py"""
    print("\nTesting portfolio.py functions...")

    from modules import portfolio

    # Create test data
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    returns = pd.Series(np.random.randn(100) * 0.02, index=dates)
    prices = pd.Series(np.random.randn(100).cumsum() + 100, index=dates)

    # Test portfolio_returns
    try:
        weights = np.array([0.6, 0.4])
        port_returns = pd.DataFrame({'A': returns, 'B': returns * 0.8})
        result = portfolio.portfolio_returns(port_returns, weights)
        if result is None or len(result) == 0:
            print("Γ¥î portfolio_returns failed")
        else:
            print("Γ£à portfolio_returns")
    except Exception as e:
        print(f"Γ¥î portfolio_returns error: {e}")

    # Test sharpe_ratio
    try:
        sharpe = portfolio.sharpe_ratio(returns)
        if sharpe is None:
            print("Γ¥î sharpe_ratio failed")
        else:
            print("Γ£à sharpe_ratio")
    except Exception as e:
        print(f"Γ¥î sharpe_ratio error: {e}")

    # Test max_drawdown
    try:
        mdd = portfolio.max_drawdown(prices)
        if mdd is None:
            print("Γ¥î max_drawdown failed")
        else:
            print("Γ£à max_drawdown")
    except Exception as e:
        print(f"Γ¥î max_drawdown error: {e}")

    # Test win_rate
    try:
        wr = portfolio.win_rate(returns)
        if wr is None:
            print("Γ¥î win_rate failed")
        else:
            print("Γ£à win_rate")
    except Exception as e:
        print(f"Γ¥î win_rate error: {e}")

    # Test portfolio_backtest
    try:
        prices_df = pd.DataFrame({'A': prices, 'B': prices * 1.1})
        weights = np.array([0.5, 0.5])
        result = portfolio.portfolio_backtest(prices_df, weights)
        if result is None:
            print("Γ¥î portfolio_backtest failed")
        else:
            print("Γ£à portfolio_backtest")
    except Exception as e:
        print(f"Γ¥î portfolio_backtest error: {e}")

    # Test value_at_risk
    try:
        var = portfolio.value_at_risk(returns)
        if var is None:
            print("Γ¥î value_at_risk failed")
        else:
            print("Γ£à value_at_risk")
    except Exception as e:
        print(f"Γ¥î value_at_risk error: {e}")

    # Test conditional_value_at_risk
    try:
        cvar = portfolio.conditional_value_at_risk(returns)
        if cvar is None:
            print("Γ¥î conditional_value_at_risk failed")
        else:
            print("Γ£à conditional_value_at_risk")
    except Exception as e:
        print(f"Γ¥î conditional_value_at_risk error: {e}")

    # Test apply_stop_loss_take_profit
    try:
        trade_list = [
            {'return_pct': 10.0},
            {'return_pct': -6.0},
            {'return_pct': 15.0}
        ]
        result = portfolio.apply_stop_loss_take_profit(trade_list)
        if result is None or len(result) == 0:
            print("Γ¥î apply_stop_loss_take_profit failed")
        else:
            print("Γ£à apply_stop_loss_take_profit")
    except Exception as e:
        print(f"Γ¥î apply_stop_loss_take_profit error: {e}")

def test_simulator_module():
    """Test all functions in simulator.py"""
    print("\nTesting simulator.py functions...")

    from modules import simulator, data

    # Get some test data
    test_data = data.download_data(['AAPL'], '2023-01-01', '2023-12-31', '1d')
    if test_data is None:
        print("Γ¥î Cannot test simulator - no data available")
        return

    # Extract close prices
    if isinstance(test_data.columns, pd.MultiIndex):
        sim_data = data.get_ticker_frame(test_data, 'AAPL')
        close_prices = sim_data['Close']
    else:
        close_prices = test_data['Close']
        sim_data = test_data

    # Test create_simulator_session
    try:
        sim_session = simulator.create_simulator_session()
        if sim_session is None:
            print("Γ¥î create_simulator_session failed")
        else:
            print("Γ£à create_simulator_session")
    except Exception as e:
        print(f"Γ¥î create_simulator_session error: {e}")
        return

    # Test get_simulator_engine
    try:
        engine = simulator.get_simulator_engine()
        if engine is None:
            print("Γ¥î get_simulator_engine failed")
        else:
            print("Γ£à get_simulator_engine")
    except Exception as e:
        print(f"Γ¥î get_simulator_engine error: {e}")
        return

    # Test reset_simulator
    try:
        simulator.reset_simulator()
        print("Γ£à reset_simulator")
    except Exception as e:
        print(f"Γ¥î reset_simulator error: {e}")

    # Test TradingSimulator methods
    try:
        # Set timeframe
        start_date = close_prices.index[0]
        end_date = close_prices.index[-1]
        engine.set_timeframe(sim_data, start_date, end_date)
        print("Γ£à set_timeframe")

        # Test get_current_state
        state = engine.get_current_state()
        if state is None:
            print("Γ¥î get_current_state failed")
        else:
            print("Γ£à get_current_state")

        # Test can_buy
        can_buy, msg = engine.can_buy(10)
        print("Γ£à can_buy")

        # Test can_sell
        can_sell, msg = engine.can_sell(10)
        print("Γ£à can_sell")

        # Test execute_buy
        success = engine.execute_buy(10)
        print("Γ£à execute_buy")

        # Test execute_sell (after buying)
        success = engine.execute_sell(5)
        print("Γ£à execute_sell")

        # Test advance_time
        success = engine.advance_time(5)
        print("Γ£à advance_time")

        # Test go_to_date
        target_date = close_prices.index[50]
        success = engine.go_to_date(target_date)
        print("Γ£à go_to_date")

        # Test get_metrics
        metrics = engine.get_metrics()
        if metrics is None:
            print("Γ¥î get_metrics failed")
        else:
            print("Γ£à get_metrics")

        # Test get_trades_df
        trades_df = engine.get_trades_df()
        print("Γ£à get_trades_df")

        # Test get_equity_curve
        equity_curve = engine.get_equity_curve()
        if equity_curve is None:
            print("Γ¥î get_equity_curve failed")
        else:
            print("Γ£à get_equity_curve")

    except Exception as e:
        print(f"Γ¥î TradingSimulator method error: {e}")

def main():
    """Run all tests"""
    print("Starting comprehensive function testing...\n")

    try:
        test_data_module()
    except Exception as e:
        print(f"Γ¥î Data module testing failed: {e}")

    try:
        test_indicators_module()
    except Exception as e:
        print(f"Γ¥î Indicators module testing failed: {e}")

    try:
        test_strategies_module()
    except Exception as e:
        print(f"Γ¥î Strategies module testing failed: {e}")

    try:
        test_portfolio_module()
    except Exception as e:
        print(f"Γ¥î Portfolio module testing failed: {e}")

    try:
        test_simulator_module()
    except Exception as e:
        print(f"Γ¥î Simulator module testing failed: {e}")

    print("\nFunction testing completed!")

if __name__ == "__main__":
    main()
