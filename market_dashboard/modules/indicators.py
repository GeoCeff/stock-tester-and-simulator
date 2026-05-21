import pandas as pd
import numpy as np

def moving_averages(price):
    """
    Calculate moving averages with proper error handling.

    Args:
        price: pandas Series of prices

    Returns:
        tuple: (ma50, ma200) or (None, None) if insufficient data
    """
    try:
        if not isinstance(price, pd.Series):
            raise ValueError("Price must be a pandas Series")

        ma50 = price.rolling(50).mean()
        ma200 = price.rolling(200).mean()

        return ma50, ma200

    except Exception as e:
        print(f"Error calculating moving averages: {e}")
        return None, None


def rsi(close, period=14):
    """
    Calculate RSI with proper error handling.

    Args:
        close: pandas Series of closing prices
        period: RSI period (default 14)

    Returns:
        pandas Series of RSI values or None if error
    """
    try:
        if not isinstance(close, pd.Series):
            raise ValueError("Close must be a pandas Series")

        close = pd.to_numeric(close, errors="coerce")

        if len(close) < period + 1:
            return pd.Series(50.0, index=close.index, dtype=float)

        delta = close.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()

        with np.errstate(divide="ignore", invalid="ignore"):
            rs = avg_gain / avg_loss

        rsi_values = 100 - (100/(1+rs))
        rsi_values = rsi_values.mask((avg_loss == 0) & (avg_gain > 0), 100)
        rsi_values = rsi_values.mask((avg_loss == 0) & (avg_gain == 0), 50)

        # Fill NaN values with neutral RSI (50)
        rsi_values = rsi_values.replace([np.inf, -np.inf], np.nan).fillna(50)

        return rsi_values

    except Exception as e:
        print(f"Error calculating RSI: {e}")
        return pd.Series(dtype=float)


def macd(close):
    """
    Calculate MACD with proper error handling.

    Args:
        close: pandas Series of closing prices

    Returns:
        tuple: (macd_line, signal) or (None, None) if insufficient data
    """
    try:
        if not isinstance(close, pd.Series):
            raise ValueError("Close must be a pandas Series")

        close = pd.to_numeric(close, errors="coerce")

        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()

        macd_line = ema12 - ema26
        signal = macd_line.ewm(span=9).mean()

        return macd_line, signal

    except Exception as e:
        print(f"Error calculating MACD: {e}")
        return None, None


def bollinger(close, period=20, std_dev=2):
    """
    Calculate Bollinger Bands with proper error handling.

    Args:
        close: pandas Series of closing prices
        period: Moving average period (default 20)
        std_dev: Standard deviation multiplier (default 2)

    Returns:
        tuple: (upper, lower) or (None, None) if insufficient data
    """
    try:
        if not isinstance(close, pd.Series):
            raise ValueError("Close must be a pandas Series")

        close = pd.to_numeric(close, errors="coerce")

        ma20 = close.rolling(period).mean()
        std20 = close.rolling(period).std()

        upper = ma20 + std_dev * std20
        lower = ma20 - std_dev * std20

        return upper, lower

    except Exception as e:
        print(f"Error calculating Bollinger Bands: {e}")
        return None, None
