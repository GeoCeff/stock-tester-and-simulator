import numpy as np
import pandas as pd

def portfolio_returns(returns, weights):
    if returns is None or len(returns) == 0:
        return pd.Series(dtype=float)

    weights = np.array(weights)

    port_returns = returns.dot(weights)

    return port_returns


def sharpe_ratio(returns, interval="1d", risk_free_rate=0.02):
    """
    Compute Sharpe ratio with interval-adjusted annualization.
    
    Parameters:
    -----------
    returns : pd.Series or pd.DataFrame
        Daily returns (as decimals, not %).
    interval : str
        "1d", "1h", "5m", "1m" for annualization.
    risk_free_rate : float
        Annual risk-free rate (default 2%).
    
    Returns:
    --------
    float
        Annualized Sharpe ratio.
    """
    periods_per_year = {
        "1d": 252,
        "1h": 252 * 6.5,
        "5m": 252 * 6.5 * 12,
        "1m": 252 * 6.5 * 60
    }
    periods = periods_per_year.get(interval, 252)
    
    if isinstance(returns, pd.DataFrame):
        returns = returns.stack()

    returns = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return 0.0

    excess_return = returns.mean() - (risk_free_rate / periods)
    std_dev = returns.std()
    
    # Check for valid standard deviation (not NaN, not zero)
    if pd.isna(std_dev) or std_dev <= 0:
        return 0.0
    
    return (excess_return / std_dev) * np.sqrt(periods)


def max_drawdown(price):
    """
    Calculate maximum drawdown with proper error handling.
    
    Parameters:
    -----------
    price : pd.Series
        Price series.
    
    Returns:
    -----------
    float
        Maximum drawdown as percentage.
    """
    if price is None or len(price) == 0:
        return 0.0

    price = pd.to_numeric(price, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()

    if price.empty:
        return 0.0

    # Accept either an equity/price series or a return series for resilience.
    if (price < 0).any():
        price = (1 + price).cumprod()
    
    rolling_max = price.cummax()
    
    # Avoid division by zero
    with np.errstate(divide='ignore', invalid='ignore'):
        drawdown = price / rolling_max.replace(0, np.nan) - 1
    
    # Handle any remaining NaN or inf values
    drawdown = drawdown.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    return drawdown.min() * 100


def win_rate(daily_returns):
    """
    Compute win rate (percentage of profitable days).
    
    Parameters:
    -----------
    daily_returns : pd.Series
        Daily returns (as decimals, not %).
    
    Returns:
    --------
    float
        Win rate as percentage (0-100).
    """
    if isinstance(daily_returns, pd.DataFrame):
        daily_returns = daily_returns.stack()

    daily_returns = pd.to_numeric(daily_returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    profitable_days = (daily_returns > 0).sum()
    total_days = (daily_returns != 0).sum()
    
    if total_days > 0:
        return (profitable_days / total_days) * 100
    else:
        return 0.0


def portfolio_backtest(prices, weights, rebalance='monthly'):
    """
    Simulate portfolio backtest with periodic rebalancing.

    Args:
        prices: DataFrame with price data
        weights: Dictionary or array of weights
        rebalance: Rebalancing frequency ('monthly', 'weekly', 'daily')

    Returns:
        Dictionary with backtest results
    """
    try:
        # Input validation
        if not isinstance(prices, pd.DataFrame):
            raise ValueError("Prices must be a pandas DataFrame")

        if prices.empty:
            raise ValueError("Prices DataFrame is empty")

        prices = prices.copy().dropna(how='all')

        if prices.empty:
            raise ValueError("No valid price data after dropping NaN values")

        returns = prices.pct_change().fillna(0)

        if isinstance(weights, dict):
            weights = np.array([weights.get(t, 0) for t in prices.columns])
        else:
            weights = np.array(weights)

        # Validate weights
        if len(weights) != len(prices.columns):
            raise ValueError(f"Weights length ({len(weights)}) must match number of assets ({len(prices.columns)})")

        # Normalize weights
        total_weight = np.sum(weights)
        if total_weight == 0:
            raise ValueError("Total weight cannot be zero")

        weights = weights / total_weight

        nav = pd.Series(1.0, index=prices.index)
        holdings = weights.copy()

        for i in range(1, len(returns)):
            nav.iloc[i] = nav.iloc[i - 1] * (1 + np.dot(returns.iloc[i], holdings))

            # Rebalance at period starts
            if rebalance in ['monthly', 'weekly', 'daily']:
                date = prices.index[i]
                should_rebalance = False

                if rebalance == 'monthly' and date.day == 1:
                    should_rebalance = True
                elif rebalance == 'weekly' and date.weekday() == 0:  # Monday
                    should_rebalance = True
                elif rebalance == 'daily':
                    should_rebalance = True

                if should_rebalance:
                    holdings = weights

        daily_returns = nav.pct_change().fillna(0)

        return {
            'nav': nav,
            'returns': daily_returns,
            'sharpe_ratio': sharpe_ratio(daily_returns, interval='1d'),
            'max_drawdown': max_drawdown(nav),
            'win_rate': win_rate(daily_returns)
        }

    except Exception as e:
        print(f"Error in portfolio_backtest: {e}")
        # Return safe default values
        empty_nav = pd.Series([1.0], index=prices.index[:1] if isinstance(prices, pd.DataFrame) and not prices.empty else pd.DatetimeIndex([]))
        empty_returns = pd.Series(dtype=float)
        return {
            'nav': empty_nav,
            'returns': empty_returns,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'win_rate': 0.0
        }


def value_at_risk(returns, confidence=0.95):
    """Compute historical Value at Risk (VaR)."""
    if isinstance(returns, pd.DataFrame):
        returns = returns.stack()
    returns = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return 0.0
    return -np.percentile(returns, 100 * (1 - confidence))


def conditional_value_at_risk(returns, confidence=0.95):
    """Compute Conditional Value at Risk (CVaR)."""
    if isinstance(returns, pd.DataFrame):
        returns = returns.stack()
    returns = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return 0.0
    tail = returns[returns <= np.percentile(returns, 100 * (1 - confidence))]
    if len(tail) > 0:
        return -tail.mean()
    else:
        return 0.0


def apply_stop_loss_take_profit(trade_df, stop_loss=0.05, take_profit=0.1):
    """Adjust trades by stop-loss and take-profit percentages."""
    adjusted_trades = []
    for trade in trade_df:
        r = trade.get('return_pct', 0) / 100.0
        if r <= -abs(stop_loss):
            trade['exit_reason'] = 'stop_loss'
        elif r >= abs(take_profit):
            trade['exit_reason'] = 'take_profit'
        else:
            trade['exit_reason'] = 'normal'
        adjusted_trades.append(trade)
    return adjusted_trades
