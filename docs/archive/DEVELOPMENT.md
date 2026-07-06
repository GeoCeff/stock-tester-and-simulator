# Development Guide

## Project Architecture

### High-Level Flow

```
[User Input (Sidebar)]
    Γåô
[Data Download (yfinance)]
    Γåô
[Indicator Calculation]
    Γåô
[Strategy Execution (if backtest enabled)]
    Γö£ΓöÇ Generate Signals
    Γö£ΓöÇ Compute Positions & Equity
    ΓööΓöÇ Calculate Metrics
    Γåô
[Visualization (Plotly)]
    Γåô
[Display Dashboard]
```

## Code Organization

### Core Modules

#### `modules/data.py`
**Purpose**: Download market data from Yahoo Finance

```python
download_data(tickers, start, end, interval)
```

- **Input**: Ticker list, date range, candle interval
- **Output**: 
  - Single ticker: DataFrame with columns [Open, High, Low, Close, Volume]
  - Multiple tickers: MultiIndex DataFrame
- **Data handling**: Automatically adjusted for splits/dividends

#### `modules/indicators.py`
**Purpose**: Calculate technical indicators

Functions:
- `moving_averages(price)` ΓåÆ (MA50, MA200)
- `rsi(close, period=14)` ΓåÆ RSI Series (0-100)
- `macd(close)` ΓåÆ (MACD line, Signal line)
- `bollinger(close)` ΓåÆ (Upper band, Lower band)

**Key Pattern**: All accept Series, return Series or tuple of Series
**Multi-ticker handling**: Extract single ticker first, then pass to indicator

#### `modules/strategies.py` (Core Backtesting)
**Purpose**: Strategy logic, position tracking, and metrics

**Base Class: `Strategy` (Abstract)**
- `__init__(holding_period, position_type, fee_pct)`
- `generate_signals(price, indicators_dict)` ΓåÆ Signal Series (abstract)
- `compute_positions_and_equity(signals, close, initial_equity)` ΓåÆ dict
- `compute_metrics(equity_series, daily_returns, interval)` ΓåÆ dict

**Architecture Pattern**:
```python
# Create strategy instance
strategy = MyStrategy(holding_period=2, position_type="fixed", fee_pct=0.001)

# Generate entry/exit signals
signals = strategy.generate_signals(close, indicators)

# Compute positions and equity
results = strategy.compute_positions_and_equity(signals, close, initial_equity=100)
# Returns: {position, daily_return, equity, entries, exits, trades}

# Calculate metrics
metrics = strategy.compute_metrics(results['equity'], results['daily_return'])
# Returns: {total_return, sharpe_ratio, max_drawdown, win_rate}
```

**Concrete Strategies**:
1. **MovingAverageCrossover**: MA50 > MA200
2. **RSIStrategy**: Threshold or mean-reversion mode
3. **BollingerBandsStrategy**: Band touch logic

**Utility Functions**:
- `buy_hold_equity(close, initial_equity=100)`: Baseline comparison

#### `modules/portfolio.py`
**Purpose**: Portfolio metrics and performance analysis

Functions:
- `sharpe_ratio(returns, interval="1d", risk_free_rate=0.02)` ΓåÆ float
- `win_rate(daily_returns)` ΓåÆ float (0-100%)
- `max_drawdown(price)` ΓåÆ float
- `portfolio_returns(returns, weights)` ΓåÆ Series

#### `modules/utils.py`
**Purpose**: Utility functions

Functions:
- `compute_returns(close)` ΓåÆ pct_change() Series
- `correlation_matrix(returns)` ΓåÆ correlation matrix

#### `dashboard.py`
**Purpose**: Main Streamlit UI and orchestration

Flow:
1. Sidebar inputs (tickers, dates, strategy params)
2. Data download
3. Technique indicator calculation
4. **[IF strategy != "None"]** Execute backtest
5. Display metrics and charts

## Adding a New Strategy

### Step 1: Create Strategy Class

```python
# In modules/strategies.py

class MyNewStrategy(Strategy):
    """Brief description of strategy logic."""
    
    def __init__(self, custom_param=10, **kwargs):
        super().__init__(**kwargs)  # holding_period, position_type, fee_pct
        self.custom_param = custom_param
    
    def generate_signals(self, price, indicators_dict):
        """
        Generate entry/exit signals.
        
        Args:
            price: Close price Series
            indicators_dict: Pre-computed indicators {ma50, ma200, rsi, ...}
        
        Returns:
            Series of 0 (flat) or 1 (long) signals, one per candle
        """
        my_indicator = indicators_dict.get('my_indicator')
        
        # Your logic here
        signal = (my_indicator > some_threshold).astype(float)
        
        # Shift to avoid lookahead bias
        signal = signal.shift(1).fillna(0)
        
        return signal
```

### Step 2: Add to Dashboard Dropdown

```python
# In dashboard.py, update the strategy selector

if strategy_name == "My New Strategy":
    strategy = MyNewStrategy(
        custom_param=sidebar_value,
        holding_period=int(holding_period),
        position_type=position_type_enum,
        fee_pct=transaction_fee
    )
```

### Step 3: Add to UI

```python
# In dashboard.py, expand the sidebar selector options
strategy_name = st.sidebar.selectbox(
    "Strategy",
    ["None", "MA Crossover", "RSI (Threshold)", "RSI (Mean-Reversion)", 
     "Bollinger Bands", "My New Strategy"],  # Add here
    index=0
)
```

### Step 4: Test

```python
# Quick test script (save as test_strategy.py)
import pandas as pd
from modules.data import download_data
from modules.indicators import moving_averages, rsi
from modules.strategies import MyNewStrategy

# Download test data
data = download_data("AAPL", "2023-01-01", "2024-01-01", "1d")
close = data["Close"]

# Compute indicators
ma50, ma200 = moving_averages(close)
rsi_vals = rsi(close)

indicators = {
    'ma50': ma50,
    'ma200': ma200,
    'rsi': rsi_vals
}

# Run strategy
strategy = MyNewStrategy(holding_period=2, position_type="fixed", fee_pct=0.001)
signals = strategy.generate_signals(close, indicators)
results = strategy.compute_positions_and_equity(signals, close, initial_equity=100)
metrics = strategy.compute_metrics(results['equity'], results['daily_return'])

print(f"Total Return: {metrics['total_return']:.2f}%")
print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {metrics['max_drawdown']:.2f}%")
print(f"Win Rate: {metrics['win_rate']:.1f}%")
```

## Key Design Patterns

### 1. Single Ticker Processing
MultiIndex data must be extracted before processing:

```python
if len(tickers) > 1:
    ticker_data = data.xs(selected_ticker, level=1, axis=1)
else:
    ticker_data = data
```

### 2. Indicator Computation
All indicators operate on Series, not DataFrames:

```python
# Γ£ô Correct
price_series = df["Close"]
ma50, ma200 = moving_averages(price_series)

# Γ£ù Wrong
try_this = moving_averages(df[["Close"]])  # DataFrame, will fail
```

### 3. Position Tracking
Positions held from signal generation through holding period:

```python
# Signal on day 1 ΓåÆ Position held days 1-2 (holding_period=2)
# Then auto-exit on day 3
entry_date_idx = 0
holding_period = 2
exit_idx = entry_date_idx + holding_period + 1  # Day 3
```

### 4. Fee Application
Fees deducted on trade days only:

```python
trade_days = (entries > 0) | (exits > 0)
daily_returns[trade_days] -= fee_pct
```

### 5. Equity Curve Calculation
Compound returns to track cumulative P&L:

```python
equity = initial_equity * (1 + daily_returns).cumprod()
```

## Testing Checklist

Before submitting a new strategy or module:

- [ ] Import successfully (no syntax errors)
- [ ] Runs on sample data without crashes
- [ ] Metrics are numerical (no NaN/Inf unless expected)
- [ ] Backtest produces reasonable results (total_return in realistic range)
- [ ] Signals align visually with chart markers
- [ ] Win rate is between 0-100%
- [ ] Sharpe ratio is reasonable (typically -2 to +2 for most strategies)
- [ ] Max drawdown is negative (or 0 if no losses)
- [ ] Holding period logic works correctly (position count matches intent)
- [ ] Fees decrease equity appropriately

## Performance Optimization

### For Strategy Developers
- Vectorize operations where possible (use Series methods instead of loops)
- Pre-compute expensive calculations outside `generate_signals()`
- Use `.iloc` for positional indexing (faster than `.loc`)

### For Dashboard Optimization
- Use `@st.cache_data` to cache data downloads
- Filter date ranges early to reduce computation
- Use daily interval for initial testing (faster than 1m/5m)

```python
@st.cache_data
def download_cached(tickers, start, end, interval):
    return download_data(tickers, start, end, interval)
```

## Common Issues & Solutions

### Issue: "Strategy never enters position"
**Solution**: 
- Check signal generation logic (print signals to debug)
- Verify indicators are not all NaN (first 200 bars for MA200)
- Check date range has sufficient data

### Issue: "Backtest slower than expected"
**Solution**:
- Use daily interval instead of 1m/5m
- Reduce date range (6 months instead of 5 years)
- Use fixed position sizing (faster than dynamic)

### Issue: "Equity curve doesn't match expected returns"
**Solution**:
- Verify holding_period implementation
- Check fee application timing
- Confirm initial_equity is correct (should start at 100)

## Code Style Guide

### Naming Conventions
- Functions: `snake_case` (e.g., `moving_averages()`)
- Classes: `PascalCase` (e.g., `MovingAverageCrossover`)
- Constants: `UPPER_CASE` (rarely used in this project)
- Private methods: `_underscore_prefix()` (e.g., `_threshold_mode()`)

### Documentation
```python
def my_function(param1, param2):
    """
    Brief one-line description.
    
    Args:
        param1 (type): Description
        param2 (type): Description
    
    Returns:
        type: Description
    """
    pass
```

### Code Formatting
- Line length: 88 characters (Black standard)
- Indentation: 4 spaces
- Imports: Group stdlib, third-party, local packages

## Git Workflow

### Commit Message Format
```
type(scope): brief description

Optional longer explanation if needed.
```

**Types**: `feat`, `fix`, `docs`, `refactor`, `test`, `perf`

**Examples**:
- `feat(strategies): add MACD crossover strategy`
- `fix(portfolio): correct Sharpe ratio annualization`
- `docs(readme): update installation instructions`

### Branch Naming
```
feature/strategy-name
bugfix/issue-description
docs/documentation-update
```

## Resources & References

- **Streamlit Docs**: https://docs.streamlit.io/
- **Pandas Docs**: https://pandas.pydata.org/docs/
- **Plotly Docs**: https://plotly.com/python/
- **yfinance Docs**: https://github.com/ranaroussi/yfinance

## Questions?

For questions about the codebase or architecture, please open an issue on GitHub.
