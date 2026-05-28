"""Built-in Quant Lab strategy templates."""

from __future__ import annotations


STRATEGY_TEMPLATES = {
    "RSI mean reversion": {
        "description": "Buy oversold RSI readings and exit when RSI becomes overbought.",
        "code": '''def strategy(data):
    # Buy oversold RSI readings and exit when momentum looks stretched.
    buy = data["rsi"] < 30
    sell = data["rsi"] > 70
    return buy, sell
''',
    },
    "SMA crossover": {
        "description": "Follow the trend when the 50-period average is above the 200-period average.",
        "code": '''def strategy(data):
    # Hold while the faster trend is above the slower trend.
    buy = data["ma50"] > data["ma200"]
    sell = data["ma50"] < data["ma200"]
    return buy, sell
''',
    },
    "MACD trend following": {
        "description": "Enter when MACD is above its signal line and exit when it crosses below.",
        "code": '''def strategy(data):
    # Follow improving MACD momentum and step aside when it weakens.
    buy = data["macd"] > data["macd_signal"]
    sell = data["macd"] < data["macd_signal"]
    return buy, sell
''',
    },
    "Bollinger Band bounce": {
        "description": "Look for mean reversion from the lower band toward the middle or upper band.",
        "code": '''def strategy(data):
    # Buy lower-band weakness and exit near the upper volatility band.
    buy = data["close"] < data["bb_lower"]
    sell = data["close"] > data["bb_upper"]
    return buy, sell
''',
    },
    "Breakout above rolling high": {
        "description": "Enter when price breaks above a recent high and exit when momentum fades.",
        "code": '''def strategy(data):
    # Trade upside breakouts above the prior 20-period high.
    prior_high = data["high"].rolling(20).max().shift(1)
    buy = data["close"] > prior_high
    sell = data["close"] < data["close"].rolling(10).mean()
    return buy, sell
''',
    },
    "Buy and hold baseline": {
        "description": "Stay invested for the whole selected period as a baseline comparison.",
        "code": '''def strategy(data):
    # Hold the selected ticker for the full test window.
    position = data["close"] > 0
    position.name = "position"
    return position
''',
    },
    "Momentum rotation proxy": {
        "description": "Use single-symbol momentum as a lightweight proxy for rotation readiness.",
        "code": '''def strategy(data):
    # Hold only when recent momentum is positive and above its own trend.
    momentum = data["close"].pct_change(63)
    momentum_floor = momentum.rolling(20).median()
    buy = momentum > momentum_floor
    sell = momentum < 0
    return buy, sell
''',
    },
}


DEFAULT_TEMPLATE_NAME = "RSI mean reversion"


def template_names() -> list[str]:
    """Return template names in display order."""
    return list(STRATEGY_TEMPLATES.keys())


def get_template(name: str | None = None) -> dict[str, str]:
    """Return a strategy template by name, falling back to the default."""
    selected = name if name in STRATEGY_TEMPLATES else DEFAULT_TEMPLATE_NAME
    return STRATEGY_TEMPLATES[selected].copy()


def get_template_code(name: str | None = None) -> str:
    """Return only the Python code for a template."""
    return get_template(name)["code"]
