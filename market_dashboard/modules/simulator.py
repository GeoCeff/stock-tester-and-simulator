"""
Trading Simulator Module
Provides functionality for manual trading simulation with real-time feedback
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import copy

REQUIRED_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume']


def _single_ticker_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Return a single-ticker OHLCV frame from either supported column shape."""
    if not isinstance(data.columns, pd.MultiIndex):
        return data.copy()

    level0 = {str(value) for value in data.columns.get_level_values(0)}
    level1 = {str(value) for value in data.columns.get_level_values(1)}

    if set(REQUIRED_COLUMNS) & level0:
        ticker = data.columns.get_level_values(1)[0]
        return data.xs(ticker, level=1, axis=1).copy()

    if set(REQUIRED_COLUMNS) & level1:
        ticker = data.columns.get_level_values(0)[0]
        return data.xs(ticker, level=0, axis=1).copy()

    raise ValueError("Could not identify OHLCV columns in simulator data")


class TradingSimulator:
    """
    Manual trading simulator that allows users to make buy/sell decisions
    in a historical timeframe with real-time P&L tracking
    """

    def __init__(self, initial_equity: float = 10000.0, transaction_fee: float = 0.001):
        """
        Initialize the trading simulator

        Args:
            initial_equity: Starting capital
            transaction_fee: Transaction fee as decimal (0.001 = 0.1%)
        """
        self.initial_equity = initial_equity
        self.transaction_fee = transaction_fee
        self.reset()

    def reset(self):
        """Reset simulator to initial state"""
        self.cash = self.initial_equity
        self.positions: List[Dict] = []  # Open positions
        self.trades: List[Dict] = []     # Completed trades
        self.orders: List[Dict] = []     # All submitted orders
        self.equity_history: List[Dict] = []
        self.current_date = None
        self.current_price = None
        self.start_date = None
        self.end_date = None
        self.sim_data = None

    def set_timeframe(self, data: pd.DataFrame, start_date, end_date):
        """
        Set the historical timeframe for simulation

        Args:
            data: OHLCV data for the stock
            start_date: Start date for simulation (date or Timestamp)
            end_date: End date for simulation (date or Timestamp)
        """
        try:
            # Input validation
            if not isinstance(data, pd.DataFrame):
                raise ValueError("Data must be a pandas DataFrame")

            if data.empty:
                raise ValueError("Data DataFrame is empty")

            data = _single_ticker_frame(data)
            data.index = pd.to_datetime(data.index)
            if isinstance(data.index, pd.DatetimeIndex) and data.index.tz is not None:
                data.index = data.index.tz_convert(None)

            self.start_date = pd.Timestamp(start_date)
            self.end_date = pd.Timestamp(end_date)
            if self.end_date == self.end_date.normalize():
                self.end_date = self.end_date + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)

            if self.start_date >= self.end_date:
                raise ValueError("Start date must be before end date")

            # Filter data to timeframe
            mask = (data.index >= self.start_date) & (data.index <= self.end_date)
            self.sim_data = data[mask].copy()

            if len(self.sim_data) == 0:
                raise ValueError("No data available for the selected timeframe")

            # Validate required columns exist
            available_columns = self.sim_data.columns

            missing_columns = [col for col in REQUIRED_COLUMNS if col not in available_columns]
            if missing_columns:
                raise ValueError(f"Missing required columns: {missing_columns}")

            self.sim_data = self.sim_data.dropna(subset=['Close'])
            if self.sim_data.empty:
                raise ValueError("No valid close prices available for the selected timeframe")

            # Set initial date and price - ensure scalar values
            self.current_date = self.sim_data.index[0]
            close_price = self.sim_data.iloc[0]['Close']
            # Handle both single ticker and multi-ticker cases
            if isinstance(close_price, pd.Series):
                self.current_price = float(close_price.iloc[0])
            else:
                self.current_price = float(close_price)

            # Initialize equity history
            self.equity_history = [{
                'date': self.current_date,
                'equity': self.initial_equity,
                'cash': self.cash,
                'positions_value': 0.0
            }]

        except Exception as e:
            print(f"Error setting timeframe: {e}")
            raise

    def get_current_state(self) -> Dict:
        """
        Get current simulator state

        Returns:
            Dictionary with current state information
        """
        total_shares = self.total_shares()
        positions_value = total_shares * self.current_price
        total_equity = self.cash + positions_value

        return {
            'date': self.current_date,
            'price': self.current_price,
            'cash': self.cash,
            'positions_value': positions_value,
            'total_equity': total_equity,
            'positions': len(self.positions),
            'shares': total_shares,
            'total_trades': len(self.trades),
            'unrealized_pnl': positions_value - sum(pos['cost'] for pos in self.positions)
        }

    def total_shares(self) -> int:
        """Return the total number of currently held shares."""
        return int(sum(pos['quantity'] for pos in self.positions))

    def max_affordable_quantity(self) -> int:
        """Return the largest whole-share buy order the current cash can cover."""
        if self.current_price is None or self.current_price <= 0:
            return 0

        cost_per_share = self.current_price * (1 + self.transaction_fee)
        if cost_per_share <= 0:
            return 0

        return max(int(float(self.cash) // cost_per_share), 0)

    def quantity_for_cash_fraction(self, fraction: float) -> int:
        """Return a whole-share quantity for a fraction of available cash."""
        if self.current_price is None or self.current_price <= 0:
            return 0

        fraction = max(min(float(fraction), 1.0), 0.0)
        deployable_cash = float(self.cash) * fraction
        cost_per_share = self.current_price * (1 + self.transaction_fee)
        if cost_per_share <= 0:
            return 0

        return max(min(int(deployable_cash // cost_per_share), self.max_affordable_quantity()), 0)

    def preview_buy(self, quantity: int) -> Dict:
        """Preview a buy order without mutating simulator state."""
        quantity = int(quantity or 0)
        trade_value = float(quantity * (self.current_price or 0.0))
        fee = trade_value * self.transaction_fee
        total_cost = trade_value + fee
        shares_after = self.total_shares() + quantity
        cash_after = float(self.cash) - total_cost
        position_value_after = shares_after * float(self.current_price or 0.0)
        equity_after = cash_after + position_value_after
        exposure_after = (position_value_after / equity_after * 100) if equity_after > 0 else 0.0
        can_execute, reason = self.can_buy(quantity)

        return {
            'action': 'BUY',
            'quantity': quantity,
            'trade_value': trade_value,
            'fee': fee,
            'cash_after': cash_after,
            'shares_after': shares_after,
            'equity_after': equity_after,
            'exposure_after': exposure_after,
            'can_execute': can_execute,
            'reason': reason,
        }

    def preview_sell(self, quantity: int) -> Dict:
        """Preview a sell order without mutating simulator state."""
        quantity = int(quantity or 0)
        total_shares = self.total_shares()
        trade_value = float(quantity * (self.current_price or 0.0))
        fee = trade_value * self.transaction_fee
        proceeds = trade_value - fee
        shares_after = max(total_shares - quantity, 0)
        cash_after = float(self.cash) + proceeds
        position_value_after = shares_after * float(self.current_price or 0.0)
        equity_after = cash_after + position_value_after
        exposure_after = (position_value_after / equity_after * 100) if equity_after > 0 else 0.0
        cost_basis = self._cost_basis_for_sale(min(quantity, total_shares))
        realized_pnl = proceeds - cost_basis
        can_execute, reason = self.can_sell(quantity)

        return {
            'action': 'SELL',
            'quantity': quantity,
            'trade_value': trade_value,
            'fee': fee,
            'proceeds': proceeds,
            'cost_basis': cost_basis,
            'realized_pnl': realized_pnl,
            'cash_after': cash_after,
            'shares_after': shares_after,
            'equity_after': equity_after,
            'exposure_after': exposure_after,
            'can_execute': can_execute,
            'reason': reason,
        }

    def _cost_basis_for_sale(self, quantity: int) -> float:
        """Estimate FIFO cost basis for a potential sale."""
        shares_to_sell = int(quantity or 0)
        total_cost_basis = 0.0

        for pos in self.positions:
            if shares_to_sell <= 0:
                break

            sell_quantity = min(shares_to_sell, pos['quantity'])
            if pos['quantity'] > 0:
                total_cost_basis += float((sell_quantity / pos['quantity']) * pos['cost'])
            shares_to_sell -= sell_quantity

        return total_cost_basis

    def can_buy(self, quantity: int) -> Tuple[bool, str]:
        """
        Check if a buy order can be executed

        Args:
            quantity: Number of shares to buy

        Returns:
            Tuple of (can_buy, reason)
        """
        cost = float(quantity * self.current_price * (1 + self.transaction_fee))
        try:
            cash_available = float(self.cash)
        except (TypeError, ValueError):
            cash_available = 0.0

        if cash_available < cost:
            return False, f"Insufficient cash. Need ${cost:.2f}, have ${cash_available:.2f}"

        if quantity <= 0:
            return False, "Quantity must be positive"

        return True, ""

    def can_sell(self, quantity: int) -> Tuple[bool, str]:
        """
        Check if a sell order can be executed

        Args:
            quantity: Number of shares to sell

        Returns:
            Tuple of (can_sell, reason)
        """
        total_shares = sum(pos['quantity'] for pos in self.positions)

        if total_shares < quantity:
            return False, f"Insufficient shares. Have {total_shares}, trying to sell {quantity}"

        if quantity <= 0:
            return False, "Quantity must be positive"

        return True, ""

    def execute_buy(self, quantity: int) -> bool:
        """
        Execute a buy order

        Args:
            quantity: Number of shares to buy

        Returns:
            True if successful, False otherwise
        """
        try:
            can_buy, reason = self.can_buy(quantity)
            if not can_buy:
                return False

            cost = float(quantity * self.current_price * (1 + self.transaction_fee))

            # Create position
            position = {
                'entry_date': self.current_date,
                'entry_price': self.current_price,
                'quantity': quantity,
                'cost': cost,
                'fee': cost - (quantity * self.current_price)
            }

            self.positions.append(position)
            self.cash = float(self.cash) - cost
            self.orders.append({
                'date': self.current_date,
                'action': 'BUY',
                'quantity': quantity,
                'price': self.current_price,
                'trade_value': quantity * self.current_price,
                'fee': position['fee'],
                'cash_after': self.cash,
                'shares_after': self.total_shares(),
            })

            # Record in equity history
            self._update_equity_history()

            return True

        except Exception as e:
            print(f"Error executing buy order: {e}")
            return False

    def execute_sell(self, quantity: int) -> bool:
        """
        Execute a sell order (FIFO - First In, First Out)

        Args:
            quantity: Number of shares to sell

        Returns:
            True if successful, False otherwise
        """
        try:
            can_sell, reason = self.can_sell(quantity)
            if not can_sell:
                return False

            shares_to_sell = quantity
            total_proceeds = 0.0
            total_cost_basis = 0.0

            # Sell from positions (FIFO)
            positions_to_remove = []
            for i, pos in enumerate(self.positions):
                if shares_to_sell <= 0:
                    break

                sell_quantity = min(shares_to_sell, pos['quantity'])
                sell_proceeds = float(sell_quantity * self.current_price * (1 - self.transaction_fee))
                sell_cost_basis = float((sell_quantity / pos['quantity']) * pos['cost'])

                total_proceeds += sell_proceeds
                total_cost_basis += sell_cost_basis

                # Update or remove position
                if sell_quantity >= pos['quantity']:
                    positions_to_remove.append(i)
                else:
                    pos['quantity'] -= sell_quantity
                    pos['cost'] -= sell_cost_basis

                shares_to_sell -= sell_quantity

            # Remove closed positions
            for i in reversed(positions_to_remove):
                del self.positions[i]

            # Record trade
            trade = {
                'date': self.current_date,
                'action': 'SELL',
                'quantity': quantity,
                'price': self.current_price,
                'proceeds': total_proceeds,
                'cost_basis': total_cost_basis,
                'realized_pnl': total_proceeds - total_cost_basis,
                'fee': quantity * self.current_price * self.transaction_fee
            }

            self.trades.append(trade)
            self.cash = float(self.cash) + float(total_proceeds)
            self.orders.append({
                'date': self.current_date,
                'action': 'SELL',
                'quantity': quantity,
                'price': self.current_price,
                'trade_value': quantity * self.current_price,
                'fee': trade['fee'],
                'proceeds': total_proceeds,
                'cost_basis': total_cost_basis,
                'realized_pnl': trade['realized_pnl'],
                'cash_after': self.cash,
                'shares_after': self.total_shares(),
            })

            # Record in equity history
            self._update_equity_history()

            return True

        except Exception as e:
            print(f"Error executing sell order: {e}")
            return False

    def advance_time(self, steps: int = 1) -> bool:
        """
        Advance simulation time by specified number of steps

        Args:
            steps: Number of time steps to advance (can be negative to go backwards)

        Returns:
            True if successful, False if end of data reached
        """
        if self.sim_data is None or self.current_date is None:
            return False

        current_idx = self.sim_data.index.get_loc(self.current_date)

        new_idx = current_idx + steps

        # Check bounds
        if new_idx < 0 or new_idx >= len(self.sim_data):
            return False

        self.current_date = self.sim_data.index[new_idx]
        close_price = self.sim_data.iloc[new_idx]['Close']
        # Handle both single ticker and multi-ticker cases
        if isinstance(close_price, pd.Series):
            self.current_price = float(close_price.iloc[0])
        else:
            self.current_price = float(close_price)

        # Update equity history
        self._update_equity_history()

        return True

    def go_to_date(self, target_date: pd.Timestamp) -> bool:
        """
        Jump to a specific date in the simulation

        Args:
            target_date: Target date to jump to

        Returns:
            True if successful, False if date not in range
        """
        if self.sim_data is None:
            return False

        target_date = pd.Timestamp(target_date)
        if target_date not in self.sim_data.index:
            return False

        self.current_date = target_date
        close_price = self.sim_data.loc[target_date, 'Close']
        # Handle both single ticker and multi-ticker cases
        if isinstance(close_price, pd.Series):
            self.current_price = float(close_price.iloc[0])
        else:
            self.current_price = float(close_price)

        # Update equity history
        self._update_equity_history()

        return True

    def _update_equity_history(self):
        """Update equity history with current state"""
        positions_value = sum(pos['quantity'] * self.current_price for pos in self.positions)
        total_equity = self.cash + positions_value

        self.equity_history.append({
            'date': self.current_date,
            'equity': total_equity,
            'cash': self.cash,
            'positions_value': positions_value
        })

    def get_metrics(self) -> Dict:
        """
        Calculate performance metrics for the simulation

        Returns:
            Dictionary with performance metrics
        """
        if not self.equity_history:
            return {}

        equity_df = pd.DataFrame(self.equity_history).set_index('date')
        equity_series = equity_df['equity']

        # Basic metrics
        total_return = (equity_series.iloc[-1] - self.initial_equity) / self.initial_equity * 100
        total_trades = len(self.trades)

        # Win rate
        winning_trades = [t for t in self.trades if t['realized_pnl'] > 0]
        win_rate = len(winning_trades) / max(total_trades, 1) * 100

        # Drawdown
        peak = equity_series.expanding().max()
        drawdown = (equity_series - peak) / peak
        max_drawdown = drawdown.min() * 100

        # Sharpe ratio (simplified)
        if len(equity_series) > 1:
            returns = equity_series.pct_change().dropna()
            if len(returns) > 0:
                sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
            else:
                sharpe = 0
        else:
            sharpe = 0

        return {
            'total_return': total_return,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe,
            'final_equity': equity_series.iloc[-1],
            'total_realized_pnl': sum(t['realized_pnl'] for t in self.trades)
        }

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as a DataFrame for display"""
        if not self.trades:
            return pd.DataFrame()

        df = pd.DataFrame(self.trades)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        return df

    def get_equity_curve(self) -> pd.Series:
        """Get equity curve as a pandas Series"""
        if not self.equity_history:
            return pd.Series()

        df = pd.DataFrame(self.equity_history).set_index('date')
        return df['equity']

def create_simulator_session():
    """Create a new simulator session in session state"""
    if 'simulator' not in st.session_state or not isinstance(st.session_state.simulator, dict):
        st.session_state.simulator = {
            'active': False,
            'engine': TradingSimulator(),
            'current_step': 0,
            'total_steps': 0,
            'is_playing': False
        }
        return

    simulator_state = st.session_state.simulator
    if simulator_state.get('engine') is None or not isinstance(simulator_state.get('engine'), TradingSimulator):
        simulator_state['engine'] = TradingSimulator()
    elif not hasattr(simulator_state['engine'], 'orders'):
        simulator_state['engine'].orders = []
    simulator_state.setdefault('active', False)
    simulator_state.setdefault('current_step', 0)
    simulator_state.setdefault('total_steps', 0)
    simulator_state.setdefault('is_playing', False)

def get_simulator_engine() -> TradingSimulator:
    """Get the current simulator engine"""
    create_simulator_session()
    return st.session_state.simulator['engine']

def reset_simulator():
    """Reset the simulator to initial state"""
    create_simulator_session()
    st.session_state.simulator['engine'].reset()
    st.session_state.simulator['active'] = False
    st.session_state.simulator['current_step'] = 0
    st.session_state.simulator['is_playing'] = False
