# Code Refactoring Examples: Before & After

This document shows how to transform the current code to be more natural and less "AI-generated" while maintaining clarity.

---

## Example 1: Dashboard Sidebar Organization

### BEFORE (Current - Feels Linear)
```python
st.sidebar.title("Market Dashboard")

tickers_input = st.sidebar.text_input("Tickers", "AAPL,MSFT,NVDA,TSLA,SPY")
tickers = [t.strip().upper() for t in tickers_input.split(",")]

interval = st.sidebar.selectbox("Interval", ["1m","5m","15m","1h","1d"], index=4)
start = st.sidebar.date_input("Start Date", pd.to_datetime("2023-01-01"))
end = st.sidebar.date_input("End Date", pd.to_datetime("today"))

show_price = st.sidebar.toggle("Advanced Chart", True)
show_drawdown = st.sidebar.toggle("Drawdown", True)
show_corr = st.sidebar.toggle("Correlation Heatmap", True)

st.sidebar.divider()
st.sidebar.subheader("Backtesting")

strategy_name = st.sidebar.selectbox("Strategy", [...], index=0)
# ... more controls
```

**Problems**:
- Data + visualization + backtest mixed together
- No visual grouping
- Hard to find related controls

### AFTER (Refactored - Organized)
```python
st.sidebar.title("≡ƒôè Market Analytics Dashboard")

# === DATA SELECTION ===
with st.sidebar.container():
    st.subheader("≡ƒôê Data Selection")
    
    tickers_input = st.text_input("Ticker Symbols", "AAPL,MSFT,NVDA,TSLA,SPY")
    tickers = [t.strip().upper() for t in tickers_input.split(",")]
    
    col1, col2 = st.columns(2)
    with col1:
        interval = st.selectbox("Interval", ["1m","5m","15m","1h","1d"], index=4)
    with col2:
        st.write("")  # Spacer
    
    start = st.date_input("Start Date", value=pd.to_datetime("2023-01-01"))
    end = st.date_input("End Date", value=pd.to_datetime("today"))

st.sidebar.divider()

# === DISPLAY OPTIONS ===
with st.sidebar.container():
    st.subheader("≡ƒæü∩╕Å Display Options")
    show_price = st.toggle("Advanced Chart", value=True)
    show_drawdown = st.toggle("Drawdown", value=True)
    show_corr = st.toggle("Correlation Heatmap", value=True)

st.sidebar.divider()

# === BACKTESTING ===
with st.sidebar.container():
    st.subheader("≡ƒñû Backtesting")
    strategy_config = get_strategy_config()  # New function
```

**Benefits**:
- Clear visual sections with emojis
- Easy to navigate sidebar
- Related controls grouped together

---

## Example 2: Backtest Execution Logic

### BEFORE (Current - Repetitive)
```python
if strategy_name != "None":
    # Extract selected ticker data for backtest period
    if len(tickers) > 1:
        ticker_data = data.xs(selected_ticker, level=1, axis=1)
    else:
        ticker_data = data
    
    # Filter to backtest date range
    mask = (ticker_data.index.date >= backtest_start) & (ticker_data.index.date <= backtest_end)
    ticker_data = ticker_data[mask]
    
    if len(ticker_data) > 0:
        close_bt = ticker_data["Close"]
        
        # Compute required indicators
        ma50_bt, ma200_bt = moving_averages(close_bt)
        rsi_bt = rsi(close_bt)
        bb_upper_bt, bb_lower_bt = bollinger(close_bt)
        
        indicators = {
            'ma50': ma50_bt,
            'ma200': ma200_bt,
            'rsi': rsi_bt,
            'bb_upper': bb_upper_bt,
            'bb_lower': bb_lower_bt,
            'close': close_bt
        }
        
        # Instantiate and run strategy
        try:
            position_type_enum = "fixed" if position_type == "Fixed" else "dynamic"
            
            if strategy_name == "MA Crossover":
                strategy = MovingAverageCrossover(...)
            elif strategy_name in ["RSI (Threshold)", "RSI (Mean-Reversion)"]:
                strategy = RSIStrategy(...)
            # ... more conditions
            
            signals = strategy.generate_signals(close_bt, indicators)
            backtest_result = strategy.compute_positions_and_equity(signals, close_bt, initial_equity=100)
            backtest_metrics = strategy.compute_metrics(...)
            
            backtest_data = backtest_result
            backtest_signals = {'entries': backtest_result['entries'], 'exits': backtest_result['exits']}
        except Exception as e:
            st.error(f"Backtest error: {e}")
```

**Problems**:
- 50+ lines of nested logic
- Hard to follow
- Exception handling generic
- Lots of intermediate variables

### AFTER (Refactored - Clean)
```python
# Extract to functions
def extract_backtest_data(data, ticker, start, end):
    """Get data for single ticker within date range."""
    ticker_data = data.xs(ticker, level=1, axis=1) if ticker else data
    mask = (ticker_data.index.date >= start) & (ticker_data.index.date <= end)
    return ticker_data[mask]

def compute_indicators_for_backtest(close):
    """Prepare all indicators needed by strategies."""
    ma50, ma200 = moving_averages(close)
    rsi_vals = rsi(close)
    bb_upper, bb_lower = bollinger(close)
    
    return {
        'ma50': ma50,
        'ma200': ma200,
        'rsi': rsi_vals,
        'bb_upper': bb_upper,
        'bb_lower': bb_lower,
        'close': close
    }

def run_backtest(strategy_name, close, indicators, params):
    """Execute strategy and return metrics."""
    strategies = {
        "MA Crossover": MovingAverageCrossover,
        "RSI (Threshold)": lambda **kw: RSIStrategy(mode="threshold", **kw),
        "RSI (Mean-Reversion)": lambda **kw: RSIStrategy(mode="mean_reversion", **kw),
        "Bollinger Bands": BollingerBandsStrategy,
    }
    
    if strategy_name not in strategies:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    
    strategy = strategies[strategy_name](
        holding_period=params['holding_period'],
        position_type="fixed" if params['position_type'] == "Fixed" else "dynamic",
        fee_pct=params['fee_pct']
    )
    
    signals = strategy.generate_signals(close, indicators)
    positions = strategy.compute_positions_and_equity(signals, close, initial_equity=100)
    metrics = strategy.compute_metrics(positions['equity'], positions['daily_return'], 
                                       interval=params['interval'])
    
    return {**positions, **metrics}

# === MAIN LOGIC (Now just 20 lines!) ===
if strategy_name and strategy_name != "None":
    try:
        backtest_data = extract_backtest_data(data, selected_ticker, backtest_start, backtest_end)
        
        if len(backtest_data) == 0:
            st.error("Γ¥î No data in selected date range. Try adjusting dates.")
        else:
            indicators = compute_indicators_for_backtest(backtest_data["Close"])
            
            params = {
                'holding_period': int(holding_period),
                'position_type': position_type,
                'fee_pct': transaction_fee,
                'interval': interval
            }
            
            backtest_result = run_backtest(strategy_name, backtest_data["Close"], indicators, params)
            backtest_metrics = {k: v for k, v in backtest_result.items() 
                              if k in ['total_return', 'sharpe_ratio', 'max_drawdown', 'win_rate']}
            
    except ValueError as e:
        st.error(f"Γ¥î {e}")
    except Exception as e:
        st.error(f"Γ¥î Backtest failed: {e}. Please check your inputs.")
```

**Benefits**:
- MUCH cleaner main logic
- Reusable functions
- Better error messages
- Easier to test
- Easier to extend

---

## Example 3: Strategy Position Tracking

### BEFORE (Current - Complex)
```python
def compute_positions_and_equity(self, signals, close, initial_equity=100):
    df = pd.DataFrame({
        'close': close,
        'signal': signals
    })

    # Track position entry date (to enforce holding period)
    entry_dates = pd.Series(0, index=df.index, dtype=int)
    position = pd.Series(0.0, index=df.index)
    entries = pd.Series(0.0, index=df.index)
    exits = pd.Series(0.0, index=df.index)
    trades = []

    for i in range(len(df)):
        # Decrement days in position
        if i > 0 and entry_dates.iloc[i - 1] > 0:
            entry_dates.iloc[i] = entry_dates.iloc[i - 1] + 1

        # Auto-exit if holding period exceeded
        if (self.holding_period > 0 and 
            entry_dates.iloc[i] > self.holding_period and 
            (i == 0 or position.iloc[i - 1] > 0)):
            # ... handle exit
        
        # New entry signal
        if df['signal'].iloc[i] > 0 and (i == 0 or position.iloc[i - 1] == 0):
            # ... handle entry
        # ... more logic
```

**Problems**:
- 150+ lines for one method
- Hard to follow logic flow
- Complex index management
- Lots of conditionals

### AFTER (Refactored - Clean)
```python
def compute_positions_and_equity(self, signals, close, initial_equity=100):
    """Track positions accounting for holding period and compute equity curve."""
    positions = self._track_positions(signals)
    daily_returns = self._compute_daily_returns(positions, close)
    daily_returns = self._apply_fees(daily_returns, positions)
    equity = self._build_equity_curve(daily_returns, initial_equity)
    
    return {
        'position': positions,
        'daily_return': daily_returns,
        'equity': equity,
        'entries': self._get_entries(positions),
        'exits': self._get_exits(positions),
        'trades': self._extract_trades(positions, close)
    }

def _track_positions(self, signals):
    """Convert signals to held positions accounting for holding period."""
    positions = pd.Series(0.0, index=signals.index)
    days_held = 0
    
    for i in range(len(signals)):
        if days_held > 0:
            days_held += 1
        
        # Auto-exit if holding period exceeded
        if self.holding_period > 0 and days_held > self.holding_period:
            positions.iloc[i] = 0.0
            days_held = 0
            continue
        
        # New entry
        if signals.iloc[i] > 0 and (i == 0 or positions.iloc[i-1] == 0):
            positions.iloc[i] = signals.iloc[i]
            days_held = 1
        # Hold position
        elif i > 0 and positions.iloc[i-1] > 0:
            positions.iloc[i] = positions.iloc[i-1]
        # Exit signal
        elif signals.iloc[i] == 0 and (i == 0 or positions.iloc[i-1] > 0):
            positions.iloc[i] = 0.0
            days_held = 0
    
    return positions

def _compute_daily_returns(self, positions, close):
    """Compute returns based on held positions."""
    returns = close.pct_change()
    return positions.shift(1).fillna(0) * returns

def _apply_fees(self, returns, positions):
    """Deduct fees on trade days."""
    trade_days = positions.diff().abs() > 0
    returns[trade_days] -= self.fee_pct
    return returns

def _get_entries(self, positions):
    """Extract entry points from position series."""
    return (positions.diff() > 0).astype(float)

def _get_exits(self, positions):
    """Extract exit points from position series."""
    return (positions.diff() < 0).astype(float)

def _build_equity_curve(self, returns, initial):
    """Build cumulative equity curve."""
    return initial * (1 + returns).cumprod()
```

**Benefits**:
- Each method ~15-20 lines max
- Clear responsibility per method
- Much easier to unit test
- Logic is self-documenting
- Easier to debug

---

## Example 4: Sidebar Parameter Collection

### BEFORE (Current - Scattered)
```python
col1, col2 = st.sidebar.columns(2)
with col1:
    position_type = st.radio("Position Sizing", ["Fixed", "Dynamic"], horizontal=True)
with col2:
    holding_period = st.number_input("Hold Days (0=day trade)", value=0, min_value=0, max_value=252)

transaction_fee = st.sidebar.slider("Transaction Fee (%)", 0.0, 1.0, 0.0, step=0.01) / 100

sharpe_interval = st.sidebar.selectbox("Sharpe Annualization", [...])
sharpe_interval_map = {"1d (252 days/yr)": "1d", ...}
sharpe_interval = sharpe_interval_map[sharpe_interval]

rsi_mode = None
if strategy_name in ["RSI (Threshold)", "RSI (Mean-Reversion)"]:
    rsi_mode = "threshold" if strategy_name == "RSI (Threshold)" else "mean_reversion"
```

**Problems**:
- Scattered logic
- Manual mapping required
- String keys error-prone
- Duplicate enum logic

### AFTER (Refactored - Clean)
```python
def get_strategy_config():
    """Collect all backtest configuration from sidebar."""
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Position Sizing**")
        position_type = st.radio("", ["Fixed", "Dynamic"], horizontal=True, key="pos_type")
    
    with col2:
        st.markdown("**Holding Period**")
        holding_period = st.number_input("", value=0, min_value=0, max_value=252,
                                        help="0=day trade, 1-5=swing, 20+=position", 
                                        key="hold_days")
    
    transaction_fee = st.slider("Transaction Fee (%)", 0.0, 1.0, 0.0, 0.01, key="fee") / 100
    
    sharpe_modes = {
        "Fixed (252 days/yr)": "1d",
        "Hourly": "1h",
        "5-Minute": "5m",
        "1-Minute": "1m"
    }
    sharpe_mode = st.selectbox("Sharpe Annualization", list(sharpe_modes.keys()), 
                               key="sharpe_mode")
    sharpe_interval = sharpe_modes[sharpe_mode]
    
    return {
        'position_type': position_type,
        'holding_period': holding_period,
        'transaction_fee': transaction_fee,
        'sharpe_interval': sharpe_interval
    }

# In main
if strategy_name and strategy_name != "None":
    config = get_strategy_config()
    # Use config['position_type'], config['holding_period'], etc.
```

**Benefits**:
- All config collection in one place
- Easy to reuse elsewhere
- Cleaner main code
- Type-safe mapping

---

## Example 5: Documentation Strings (More Natural)

### BEFORE (Current - Overly Formal)
```python
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
```

### AFTER (Refactored - More Natural)
```python
def generate_signals(self, price, indicators_dict):
    """
    Generate trading signals based on strategy logic.
    
    Signals represent entry opportunities:
    - 0: Stay flat (no position)
    - 1: Enter long position
    
    Args:
        price: Close prices for the period
        indicators_dict: Pre-computed indicators (ma50, ma200, rsi, bb_upper, bb_lower)
    
    Returns:
        Series of 0/1 signals (one per candle)
    """
    pass
```

---

## Example 6: Metrics Display Function

### BEFORE (Current - Repetitive)
```python
if backtest_metrics is not None:
    st.subheader(f"Strategy Performance: {strategy_name}")
    
    metric_cols = st.columns(4)
    
    with metric_cols[0]:
        st.metric(
            "Total Return",
            f"{backtest_metrics['total_return']:.2f}%"
        )
    
    with metric_cols[1]:
        st.metric(
            "Sharpe Ratio",
            f"{backtest_metrics['sharpe_ratio']:.2f}"
        )
    
    with metric_cols[2]:
        st.metric(
            "Max Drawdown",
            f"{backtest_metrics['max_drawdown']:.2f}%"
        )
    
    with metric_cols[3]:
        st.metric(
            "Win Rate",
            f"{backtest_metrics['win_rate']:.1f}%"
        )
```

### AFTER (Refactored - DRY)
```python
def display_backtest_summary(metrics, strategy_name):
    """Show strategy performance metrics in a clean 4-column layout."""
    st.subheader(f"≡ƒôè Strategy Performance: {strategy_name}")
    
    metric_specs = [
        ("≡ƒôê Total Return", metrics['total_return'], ".2f", "%"),
        ("ΓÜû∩╕Å Sharpe Ratio", metrics['sharpe_ratio'], ".2f", ""),
        ("≡ƒôë Max Drawdown", metrics['max_drawdown'], ".2f", "%"),
        ("≡ƒÄ» Win Rate", metrics['win_rate'], ".1f", "%"),
    ]
    
    cols = st.columns(4)
    for col, (label, value, fmt, suffix) in zip(cols, metric_specs):
        formatted = f"{value:{fmt}}{suffix}"
        col.metric(label, formatted)

# In main
if backtest_metrics:
    display_backtest_summary(backtest_metrics, strategy_name)
```

---

## Quick Refactoring Checklist

- [ ] Extract long functions into smaller helpers (max 30 lines each)
- [ ] Replace magic strings with Enum/constants
- [ ] Group related sidebar controls into sections
- [ ] Use descriptive variable names (not `df`, `i`, `x`)
- [ ] Replace nested if/else with early returns or try/except
- [ ] Add type hints to function signatures
- [ ] Use f-strings instead of .format()
- [ ] Replace repetitive code with loops/helpers
- [ ] Add emojis to headers for visual scanning
- [ ] Write docstrings like documentation, not specifications
- [ ] Use session_state for caching expensive computations
- [ ] Handle errors with user-friendly messages

---

## Example Refactored Section: Complete

Here's what a section might look like after applying all improvements:

```python
# ============================================================================
# BACKTESTING ENGINE
# ============================================================================

@st.cache_data
def execute_backtest(strategy_name, price, indicators, config):
    """Run backtesting for given strategy and configuration."""
    
    # Validate inputs
    if strategy_name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    
    # Create strategy instance
    strategy_class = STRATEGY_REGISTRY[strategy_name]
    strategy = strategy_class(
        holding_period=config['holding_period'],
        position_type=config['position_type'],
        fee_pct=config['fee_pct']
    )
    
    # Run backtest
    signals = strategy.generate_signals(price, indicators)
    results = strategy.compute_positions_and_equity(signals, price)
    metrics = strategy.compute_metrics(results['equity'], results['daily_return'],
                                      interval=config['interval'])
    
    return {**results, **metrics}

def display_results(backtest, strategy_name):
    """Display backtest results with metrics and charts."""
    
    # Metrics panel
    display_backtest_summary(backtest, strategy_name)
    st.divider()
    
    # Trade log
    if backtest['trades']:
        display_trade_log(backtest['trades'])
        st.divider()
    
    # Equity curve
    display_equity_chart(backtest)

# === MAIN ===
if strategy_name and strategy_name != "None":
    with st.spinner("ΓÜÖ∩╕Å Running backtest..."):
        try:
            # Prepare data
            backtest_data = extract_backtest_data(data, selected_ticker, 
                                                  backtest_start, backtest_end)
            if len(backtest_data) == 0:
                st.warning("No data available for selected date range")
            else:
                # Run backtest
                indicators = compute_indicators(backtest_data["Close"])
                config = get_strategy_config()
                
                backtest = execute_backtest(strategy_name, backtest_data["Close"], 
                                           indicators, config)
                
                # Display results
                display_results(backtest, strategy_name)
        
        except ValueError as e:
            st.error(f"Configuration error: {e}")
        except Exception as e:
            st.error(f"Backtest failed: {e}")
            with st.expander("Debug Info"):
                st.write(f"Error details: {str(e)}")
```

This is MUCH cleaner and more maintainable! ≡ƒÄë
