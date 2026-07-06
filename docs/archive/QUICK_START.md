# Stock Backtester - Quick Start Guide

## ≡ƒÜÇ Get Started in 2 Minutes

### Installation
```bash
cd stock-backtester
pip install -r requirements.txt
```

### Run Application
```bash
streamlit run market_dashboard/dashboard.py
```

### Run Tests
```bash
python test_integration.py
```

---

## ≡ƒôè UI Sections at a Glance

### LEFT SIDEBAR

#### ≡ƒôê Data Selection
```
Ticker Symbols: [AAPL,MSFT,NVDA]    ΓåÉ Comma-separated list
Interval:       [1d Γû╝]              ΓåÉ 1m, 5m, 15m, 1h, 1d
Start Date:     [2023-01-01]
End Date:       [Today]
```

#### ≡ƒæü∩╕Å Display Options
```
≡ƒôè Chart        Γÿæ       Show candlesticks & indicators
≡ƒôë Drawdown     Γÿæ       Show equity drawdown curve
≡ƒöù Correlation  Γÿæ       Show ticker correlation heatmap
```

#### ≡ƒñû Backtesting
```
Select Strategy:    [MA Crossover Γû╝]  ΓåÉ 3 strategies available
≡ƒôï Quick Presets:   [Swing (2-Day) Γû╝] ΓåÉ Instant configuration
Backtest Period:    [2023-01-01 to 2023-12-31]
Position Sizing:    [Fixed ΓèÖ Dynamic] ΓåÉ All-in or fractional
Hold Days:          [2]                ΓåÉ 0=day, 1-5=swing, 20+=position
ΓÜÖ∩╕Å Advanced Options  [Γû╝]               ΓåÉ Fees, Sharpe mode
```

---

## ≡ƒôê Main Content Area

### Backtest Results (if strategy selected)

```
ΓöîΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
Γöé ≡ƒÆ░ Total Return     Γöé ≡ƒôè Sharpe Ratio  Γöé ≡ƒôë Max Drawdown Γöé
Γöé +12.45%            Γöé 0.89             Γöé -8.23%          Γöé
Γöé                    Γöé                  Γöé                 Γöé
Γöé ≡ƒÄ» Win Rate        Γöé ≡ƒôà Period        Γöé                 Γöé
Γöé 54.9%              Γöé 252 days         Γöé                 Γöé
ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ

ΓöîΓöÇ Trade Log ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
Γöé Entry Date    Γöé Entry  Γöé Exit Date    Γöé Exit   Γöé Return Γöé
Γö£ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓö╝ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓö╝ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓö╝ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓö╝ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöñ
Γöé 2023-01-15   Γöé $150.2 Γöé 2023-01-17   Γöé $152.1 Γöé +1.26% Γöé
Γöé 2023-01-18   Γöé $151.8 Γöé 2023-01-20   Γöé $149.5 Γöé -1.52% Γöé
Γöé ...          Γöé ...    Γöé ...          Γöé ...    Γöé ...    Γöé
Γöé                                      Γöé [≡ƒôÑ Export CSV] Γöé
ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ

ΓöîΓöÇ Advanced Chart (5 rows) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
Γöé Row 1: Candlestick + MA50/200 + Bollinger + Signals    Γöé
Γöé Row 2: Volume                                           Γöé
Γöé Row 3: MACD                                             Γöé
Γöé Row 4: RSI                                              Γöé
Γöé Row 5: Equity Curve (Strategy vs Buy-Hold)             Γöé
ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ

ΓöîΓöÇ Optional: Drawdown & Correlation ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÉ
Γöé (toggle on/off in Display Options)                      Γöé
ΓööΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÿ
```

---

## ΓÜí Key Features

| Feature | Benefit |
|---------|---------|
| **Session Caching** | Change chart toggle? Instant. No recalculation |
| **Quick Presets** | Day Trading / Swing / Position - one click |
| **Trade Export** | Download trades as CSV for analysis |
| **Entry/Exit Markers** | Green diamonds = buy, Red X = sell |
| **Buy-Hold Comparison** | See strategy vs benchmark equity curve |
| **Error Messages** | User-friendly with hints for fixes |

---

## ≡ƒÄ» Use Cases

### Day Trading Analysis
1. Select quick preset **"Day Trading"** (0-day holding)
2. Set interval to **1h** (hourly candles)
3. Choose strategy (e.g., RSI)
4. Review trade log for daily scalps
5. Export trades to CSV

### Swing Trading Backtest
1. Select preset **"Swing (2-Day)"**
2. Use default interval **1d** (daily candles)
3. Test MA Crossover strategy
4. Check Sharpe ratio and win rate
5. Compare equity curve to buy-hold

### Position Trading Study
1. Select preset **"Position Trading"** (20+ days)
2. Use **1d** interval
3. Backtest Bollinger Bands strategy
4. Focus on max drawdown metric
5. Analyze correlation of holdings

---

## ≡ƒÆí Pro Tips

1. **Faster Backtests**: Use shorter date ranges for quick iterations
2. **Fair Comparison**: Enable Buy-Hold to benchmark strategy
3. **Transaction Costs**: Add 0.05-0.1% fees to simulate real slippage
4. **Multiple Backtests**: Cache remembers results (fast on repeat)
5. **Different Time Frames**: Test same strategy on 1h vs 1d
6. **CSV Analysis**: Export trades to Excel for deeper analysis

---

## ≡ƒöì Troubleshooting

### "No data for ticker in range"
- Γ£ô Check ticker symbol (AAPL not Apple)
- Γ£ô Verify date range has market activity
- Γ£ô Try well-known tickers (AAPL, MSFT, NVDA)

### Backtest shows "NaN"
- Γ£ô Strategy may not generate signals in period
- Γ£ô Try longer date range (more opportunities)
- Γ£ô Adjust holding period or position sizing

### App runs slow
- Γ£ô Reduce number of tickers
- Γ£ô Shorter date range
- Γ£ô Disable correlation heatmap toggle

---

## ≡ƒôÜ Documentation Files

| File | Purpose |
|------|---------|
| README.md | Overview & feature descriptions |
| DEVELOPMENT.md | Architecture & adding new strategies |
| CODE_REFACTORING.md | Code style & patterns |
| ROADMAP.md | Planned features (Tier 1-3) |
| COMPLETION_SUMMARY.md | Full project summary |
| requirements.txt | Python dependencies |

---

## ≡ƒÄ« Strategy Reference

### Moving Average Crossover
- **Signal**: MA50 crosses above MA200 = buy, below = sell
- **Best For**: Trend following
- **Holding**: Usually multi-day

### RSI Strategy (Threshold Mode)
- **Signal**: RSI < 30 = buy, RSI > 70 = sell
- **Best For**: Overbought/oversold detection
- **Holding**: Short-term reversals

### RSI Strategy (Mean-Reversion Mode)
- **Signal**: RSI crosses 50 line
- **Best For**: Range-bound markets
- **Holding**: Intraday to swing

### Bollinger Bands
- **Signal**: Price touches lower band = buy, upper band = sell
- **Best For**: Volatility-based entries
- **Holding**: Variable based on volatility

---

## Γ£¿ Release Notes (v1.1.2)

### New Features Γ£¿
- Session caching for instant parameter changes
- Quick presets (Day Trading, Swing, Position)
- Trade log with statistics and CSV export
- 5-row advanced chart with equity curve
- Organized sidebar with emojis
- Collapsible advanced options

### Improvements ≡ƒÜÇ
- Modular code with helper functions
- Better error messages
- Faster backtest execution
- Cleaner UI layout
- Comprehensive testing suite

### Bug Fixes ≡ƒÉ¢
- Fixed metric display alignment
- Proper date filtering
- Correct fee calculation
- Signal marker placement

---

**Ready to backtest? Run:** 
```bash
streamlit run market_dashboard/dashboard.py
```

**Questions?** See DEVELOPMENT.md for code architecture.
