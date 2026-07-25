import pandas as pd
import numpy as np
from abc import ABC, abstractmethod


class Strategy(ABC):
    """
    Base strategy class for backtesting.
    Handles position logic, equity tracking, metrics computation, and signal visualization.
    Supports fixed (0/1) and dynamic (0-1 continuous) position sizing.
    Supports holding periods for day trading, swing trading, and position trading.
    """

    def __init__(self, holding_period=0, position_type="fixed", fee_pct=0.0):
        """
        Parameters:
        -----------
        holding_period : int
            Number of days to hold position. 0 = day trading (exit same day).
            1-5 = swing trading (1-5 days). 20+ = position trading.
        position_type : str
            "fixed" (all-in/out: 0 or 1) or "dynamic" (continuous 0-1).
        fee_pct : float
            Transaction cost as percentage (0.001 = 0.1%).
        """
        self.holding_period = holding_period
        self.position_type = position_type
        self.fee_pct = fee_pct

    @abstractmethod
    def generate_signals(self, price, indicators_dict):
        """
        Generate entry signals (0/1 or 0-1 for dynamic).

        Parameters:
        -----------
        price : pd.Series
            Close price series (single ticker).
        indicators_dict : dict
            Pre-computed indicators (ma50, ma200, rsi, etc.).

        Returns:
        --------
        pd.Series
            Signal values (0 or 1 for fixed, 0-1 for dynamic).
        """
        pass

    def compute_positions_and_equity(self, signals, close, initial_equity=100):
        """
        Convert signals to held positions accounting for holding period.
        Track equity curve, entry/exit dates, and trades.

        Parameters:
        -----------
        signals : pd.Series
            Entry signals from generate_signals().
        close : pd.Series
            Close price series.
        initial_equity : float
            Starting amount.

        Returns:
        --------
        dict with keys:
            - 'position': pd.Series (held position, 0-1)
            - 'daily_return': pd.Series (daily return %)
            - 'equity': pd.Series (equity curve starting at initial_equity)
            - 'entries': pd.Series (entry dates with signal strength, 0 if no entry)
            - 'exits': pd.Series (exit dates, 0 if no exit)
            - 'trades': list of (entry_date, entry_price, exit_date, exit_price, return%)
        """
        try:
            # Input validation
            if not isinstance(signals, pd.Series) or not isinstance(close, pd.Series):
                raise ValueError("Signals and close must be pandas Series")

            if len(signals) == 0:
                raise ValueError("Empty data provided")

            if initial_equity <= 0:
                raise ValueError("Initial equity must be positive")

            if self.holding_period < 0:
                raise ValueError("Holding period cannot be negative")

            df = pd.concat(
                [
                    pd.to_numeric(close, errors="coerce").rename("close"),
                    pd.to_numeric(signals, errors="coerce").rename("signal"),
                ],
                axis=1,
            )
            df["signal"] = df["signal"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            df["signal"] = df["signal"].clip(lower=0.0, upper=1.0)
            df = df.dropna(subset=["close"])
            df = df[df["close"] > 0]

            if df.empty:
                raise ValueError("No valid price data provided")

            position = pd.Series(0.0, index=df.index, dtype=float)
            entries = pd.Series(0.0, index=df.index, dtype=float)
            exits = pd.Series(0.0, index=df.index, dtype=float)
            trades = []

            in_position = False
            entry_idx = None
            entry_price = None
            current_size = 0.0

            for i in range(len(df)):
                signal_value = float(df["signal"].iloc[i])

                if not in_position and signal_value > 0:
                    in_position = True
                    entry_idx = i
                    entry_price = float(df["close"].iloc[i])
                    current_size = signal_value if self.position_type == "dynamic" else 1.0
                    position.iloc[i] = current_size
                    entries.iloc[i] = current_size
                    continue

                if not in_position:
                    continue

                held_periods = i - entry_idx
                exit_due_to_signal = signal_value <= 0 and i > entry_idx
                exit_due_to_time = self.holding_period > 0 and held_periods >= self.holding_period

                if exit_due_to_signal or exit_due_to_time:
                    exit_price = float(df["close"].iloc[i])
                    exit_reason = "Holding period reached" if exit_due_to_time else "Strategy exit signal"
                    trades.append({
                        'entry_idx': entry_idx,
                        'entry_date': df.index[entry_idx],
                        'entry_price': entry_price,
                        'entry_reason': 'Strategy entry signal',
                        'exit_idx': i,
                        'exit_date': df.index[i],
                        'exit_price': exit_price,
                        'exit_reason': exit_reason,
                        'holding_periods': held_periods,
                        'return_pct': (exit_price / entry_price - 1) * 100 if entry_price else 0.0,
                        'fees_pct': self.fee_pct * 2 * 100
                    })
                    exits.iloc[i] = 1.0
                    in_position = False
                    entry_idx = None
                    entry_price = None
                    current_size = 0.0
                else:
                    if self.position_type == "dynamic" and signal_value > 0:
                        current_size = signal_value
                    position.iloc[i] = current_size

            # Compute daily returns based on position
            price_returns = df['close'].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
            daily_returns = position.shift(1).fillna(0.0) * price_returns

            # Apply fees on trade days (entry/exit)
            trade_days = (entries > 0) | (exits > 0)
            daily_returns[trade_days] -= self.fee_pct

            # Fill NaN values (from pct_change and shift operations)
            daily_returns = daily_returns.fillna(0)

            # Compute equity curve
            equity = initial_equity * (1 + daily_returns).cumprod()

            return {
                'position': position,
                'daily_return': daily_returns,
                'equity': equity,
                'entries': entries,
                'exits': exits,
                'trades': trades
            }

        except Exception as e:
            print(f"Error in compute_positions_and_equity: {e}")
            # Return safe default values
            index = close.index if isinstance(close, pd.Series) else pd.DatetimeIndex([])
            empty_series = pd.Series(0.0, index=index, dtype=float)
            equity = pd.Series(initial_equity, index=index, dtype=float)
            return {
                'position': empty_series,
                'daily_return': empty_series,
                'equity': equity,
                'entries': empty_series,
                'exits': empty_series,
                'trades': []
            }

    def compute_metrics(self, equity_series, daily_returns, interval="1d", risk_free_rate=0.02):
        """
        Compute backtest metrics.

        Parameters:
        -----------
        equity_series : pd.Series
            Equity curve.
        daily_returns : pd.Series
            Daily returns (as decimals, not %).
        interval : str
            "1d", "1h", "5m", "1m" for annualization.
        risk_free_rate : float
            Risk-free rate for Sharpe (annual, default 2%).

        Returns:
        --------
        dict with keys: total_return, sharpe_ratio, max_drawdown, win_rate
        """
        equity_series = pd.to_numeric(equity_series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        daily_returns = pd.to_numeric(daily_returns, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)

        if equity_series.empty:
            return {
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'win_rate': 0.0
            }

        initial_value = equity_series.iloc[0]
        final_value = equity_series.iloc[-1]
        
        if initial_value == 0 or pd.isna(initial_value):
            total_return = 0.0
        else:
            total_return = (final_value / initial_value - 1) * 100

        # Annualization factor
        periods_per_year = {
            "1d": 252,
            "1h": 252 * 6.5,
            "5m": 252 * 6.5 * 12,
            "1m": 252 * 6.5 * 60
        }
        periods = periods_per_year.get(interval, 252)

        # Sharpe ratio
        excess_return = daily_returns.mean() - (risk_free_rate / periods)
        std_dev = daily_returns.std()
        sharpe = (excess_return / std_dev) * np.sqrt(periods) if std_dev > 0 else 0.0

        # Max drawdown
        running_max = equity_series.cummax()
        drawdown = (equity_series / running_max.replace(0, np.nan) - 1) * 100
        max_dd = drawdown.replace([np.inf, -np.inf], np.nan).fillna(0.0).min()

        # Win rate (% of profitable days)
        profitable_days = (daily_returns > 0).sum()
        total_days = (daily_returns != 0).sum()
        win_rate = (profitable_days / total_days * 100) if total_days > 0 else 0

        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'win_rate': win_rate
        }


class MovingAverageCrossover(Strategy):
    """MA50/MA200 crossover strategy."""

    def generate_signals(self, price, indicators_dict):
        """
        Generate signals: 1 when MA50 > MA200, else 0.
        """
        ma50 = indicators_dict.get('ma50')
        ma200 = indicators_dict.get('ma200')

        if ma50 is None or ma200 is None:
            return pd.Series(0.0, index=price.index, dtype=float)

        # Signal: 1 when MA50 > MA200
        ma50 = ma50.reindex(price.index)
        ma200 = ma200.reindex(price.index)
        signal = (ma50 > ma200).fillna(False).astype(float)
        # Shift to avoid lookahead bias
        signal = signal.shift(1).fillna(0)

        return signal


class TrendMomentumStrategy(Strategy):
    """Long only when the long-term trend and three-month momentum agree."""

    def generate_signals(self, price, indicators_dict):
        ma50 = indicators_dict.get("ma50")
        ma200 = indicators_dict.get("ma200")
        if ma50 is None or ma200 is None:
            return pd.Series(0.0, index=price.index, dtype=float)
        signal = (ma50 > ma200) & (price.pct_change(63) > 0)
        return signal.shift(1).fillna(False).astype(float)


class RSIStrategy(Strategy):
    """RSI-based strategy with two modes: threshold and mean-reversion."""

    def __init__(self, mode="threshold", holding_period=0, position_type="fixed", fee_pct=0.0):
        """
        Parameters:
        -----------
        mode : str
            "threshold" (buy RSI<30, sell RSI>70) or
            "mean_reversion" (buy RSI<50 crossing up, sell RSI>50 crossing down)
        """
        super().__init__(holding_period, position_type, fee_pct)
        self.mode = mode

    def generate_signals(self, price, indicators_dict):
        """
        Generate RSI signals based on mode.
        """
        rsi_values = indicators_dict.get('rsi')

        if rsi_values is None:
            return pd.Series(0.0, index=price.index, dtype=float)

        rsi_values = rsi_values.reindex(price.index).fillna(50.0)

        if self.mode == "threshold":
            signal = self._threshold_mode(rsi_values)
        elif self.mode == "mean_reversion":
            signal = self._mean_reversion_mode(rsi_values)
        else:
            raise ValueError(f"Unknown RSI mode: {self.mode}")

        # Shift to avoid lookahead bias
        signal = signal.shift(1).fillna(0)

        return signal

    def _threshold_mode(self, rsi):
        """RSI threshold: buy <30, sell >70."""
        signal = pd.Series(0.0, index=rsi.index)

        for i in range(1, len(rsi)):
            prev_signal = signal.iloc[i - 1]

            # Enter on RSI < 30
            if rsi.iloc[i] < 30 and prev_signal == 0:
                signal.iloc[i] = 1
            # Stay in until RSI > 70
            elif rsi.iloc[i] > 70 and prev_signal == 1:
                signal.iloc[i] = 0
            # Hold
            else:
                signal.iloc[i] = prev_signal

        return signal

    def _mean_reversion_mode(self, rsi):
        """RSI mean-reversion: buy RSI crosses above 50, sell crosses below 50."""
        signal = pd.Series(0.0, index=rsi.index)
        prev_pos = 0

        for i in range(1, len(rsi)):
            # Crossing above 50 -> buy
            if rsi.iloc[i] > 50 and rsi.iloc[i - 1] <= 50 and prev_pos == 0:
                signal.iloc[i] = 1
                prev_pos = 1
            # Crossing below 50 -> sell
            elif rsi.iloc[i] < 50 and rsi.iloc[i - 1] >= 50 and prev_pos == 1:
                signal.iloc[i] = 0
                prev_pos = 0
            else:
                signal.iloc[i] = prev_pos

        return signal


class BollingerBandsStrategy(Strategy):
    """Bollinger Bands mean-reversion strategy."""

    def generate_signals(self, price, indicators_dict):
        """
        Buy when price touches lower band, sell when touches upper band.
        """
        upper = indicators_dict.get('bb_upper')
        lower = indicators_dict.get('bb_lower')
        close = indicators_dict.get('close')

        if upper is None or lower is None or close is None:
            return pd.Series(0.0, index=price.index, dtype=float)

        upper = upper.reindex(close.index)
        lower = lower.reindex(close.index)

        signal = pd.Series(0.0, index=close.index)

        for i in range(1, len(close)):
            prev_signal = signal.iloc[i - 1]

            # Buy when touching lower band
            if close.iloc[i] <= lower.iloc[i] and prev_signal == 0:
                signal.iloc[i] = 1
            # Sell when touching upper band
            elif close.iloc[i] >= upper.iloc[i] and prev_signal == 1:
                signal.iloc[i] = 0
            else:
                signal.iloc[i] = prev_signal

        signal = signal.shift(1).fillna(0)
        return signal


def buy_hold_equity(close, initial_equity=100):
    """
    Compute buy-and-hold equity curve for comparison.

    Parameters:
    -----------
    close : pd.Series
        Close price series.
    initial_equity : float
        Starting equity.

    Returns:
    --------
    pd.Series
        Equity curve (starting at initial_equity).
    """
    close = pd.to_numeric(close, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if close.empty or initial_equity <= 0:
        return pd.Series(dtype=float)

    first_price = close.iloc[0]
    if first_price <= 0 or pd.isna(first_price):
        return pd.Series(initial_equity, index=close.index, dtype=float)

    normalized = close / first_price
    return initial_equity * normalized
