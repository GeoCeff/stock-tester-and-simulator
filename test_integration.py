#!/usr/bin/env python
"""
Integration test for Stock Backtester
Validates all modules work together correctly
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add market_dashboard to path
sys.path.insert(0, 'market_dashboard')

from modules.data import download_data
from modules.indicators import moving_averages, rsi, bollinger, macd
from modules.utils import compute_returns, correlation_matrix
from modules.strategies import (
    MovingAverageCrossover, RSIStrategy, BollingerBandsStrategy, buy_hold_equity
)
from modules.portfolio import sharpe_ratio, max_drawdown, win_rate

print("=" * 70)
print("STOCK BACKTESTER - INTEGRATION TEST")
print("=" * 70)

# Test 1: Data download
print("\nTest 1: Data Download")
print("-" * 70)
try:
    tickers = ["AAPL", "MSFT"]
    start = pd.to_datetime("2023-01-01")
    end = pd.to_datetime("2023-12-31")
    
    data = download_data(tickers, start, end, "1d")
    print(f"Downloaded {len(data)} rows for {len(tickers)} tickers")
    print(f"   Columns: {list(data.columns.get_level_values(0).unique())}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Test 2: Indicators
print("\nTest 2: Indicator Computation")
print("-" * 70)
try:
    aapl_data = data.xs("AAPL", level=1, axis=1)
    close = aapl_data["Close"]
    
    ma50, ma200 = moving_averages(close)
    rsi_val = rsi(close)
    upper, lower = bollinger(close)
    macd_line, signal = macd(close)
    
    print(f"Computed indicators successfully")
    print(f"   MA50: {ma50.iloc[-1]:.2f}")
    print(f"   MA200: {ma200.iloc[-1]:.2f}")
    print(f"   RSI: {rsi_val.iloc[-1]:.1f}")
    print(f"   MACD: {macd_line.iloc[-1]:.4f}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Test 3: Strategy - Moving Average Crossover
print("\nTest 3: Strategy - Moving Average Crossover")
print("-" * 70)
try:
    strategy = MovingAverageCrossover(
        holding_period=0,
        position_type="fixed",
        fee_pct=0.001
    )
    
    indicators = {
        'ma50': ma50,
        'ma200': ma200,
        'rsi': rsi_val,
        'bb_upper': upper,
        'bb_lower': lower,
        'close': close
    }
    
    signals = strategy.generate_signals(close, indicators)
    backtest_result = strategy.compute_positions_and_equity(signals, close, initial_equity=100)
    metrics = strategy.compute_metrics(
        backtest_result['equity'],
        backtest_result['daily_return'],
        interval="1d",
        risk_free_rate=0.02
    )
    
    print(f"MA Crossover backtest completed")
    print(f"   Total Return: {metrics['total_return']:.2f}%")
    print(f"   Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"   Max Drawdown: {metrics['max_drawdown']:.2f}%")
    print(f"   Win Rate: {metrics['win_rate']:.1f}%")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Test 4: Strategy - RSI Threshold
print("\nTest 4: Strategy - RSI Threshold")
print("-" * 70)
try:
    strategy = RSIStrategy(
        mode="threshold",
        holding_period=2,
        position_type="fixed",
        fee_pct=0.001
    )
    
    signals = strategy.generate_signals(close, indicators)
    backtest_result = strategy.compute_positions_and_equity(signals, close, initial_equity=100)
    metrics = strategy.compute_metrics(
        backtest_result['equity'],
        backtest_result['daily_return'],
        interval="1d"
    )
    
    print(f"RSI (Threshold) backtest completed")
    print(f"   Total Return: {metrics['total_return']:.2f}%")
    print(f"   Trades: {len(backtest_result['entries'][backtest_result['entries'] > 0])}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Test 5: Strategy - Bollinger Bands
print("\nTest 5: Strategy - Bollinger Bands")
print("-" * 70)
try:
    strategy = BollingerBandsStrategy(
        holding_period=1,
        position_type="dynamic",
        fee_pct=0.0005
    )
    
    signals = strategy.generate_signals(close, indicators)
    backtest_result = strategy.compute_positions_and_equity(signals, close, initial_equity=100)
    metrics = strategy.compute_metrics(
        backtest_result['equity'],
        backtest_result['daily_return'],
        interval="1d"
    )
    
    print(f"Bollinger Bands backtest completed")
    print(f"   Total Return: {metrics['total_return']:.2f}%")
    print(f"   Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Test 6: Portfolio metrics
print("\nTest 6: Portfolio Metrics")
print("-" * 70)
try:
    bh_equity = buy_hold_equity(close, initial_equity=100)
    bh_returns = bh_equity.pct_change(1).dropna()
    
    result = sharpe_ratio(bh_returns, interval="1d", risk_free_rate=0.02)
    dd = max_drawdown(bh_returns)
    wr = win_rate(bh_returns)
    
    print(f"Portfolio metrics computed")
    print(f"   Sharpe (Buy-Hold): {result:.2f}")
    print(f"   Max Drawdown: {dd:.2f}%")
    print(f"   Win Rate: {wr:.1f}%")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Test 7: Multi-ticker correlation
print("\nTest 7: Multi-Ticker Analysis")
print("-" * 70)
try:
    returns_multi = compute_returns(data["Close"])
    corr = correlation_matrix(returns_multi)
    
    print(f"Correlation analysis completed")
    print(f"   AAPL-MSFT correlation: {corr.loc['AAPL', 'MSFT']:.3f}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Final summary
print("\n" + "=" * 70)
print("ALL TESTS PASSED")
print("=" * 70)
print("\nThe Stock Backtester is ready for use!")
print("Run: streamlit run market_dashboard/dashboard.py")
