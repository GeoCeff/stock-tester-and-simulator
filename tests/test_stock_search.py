from market_dashboard.modules.stock_search import (
    get_popular_stocks,
    get_stock_categories,
    get_stock_preset_symbols,
    get_stock_presets,
)


def test_stock_categories_include_expanded_discovery_options():
    categories = get_stock_categories()

    assert "AI & Semiconductors" in categories
    assert "Index ETFs" in categories
    assert "Dividend Leaders" in categories


def test_all_popular_stocks_preserves_unique_symbols():
    symbols = get_popular_stocks("All")

    assert len(symbols) == len(set(symbols))
    assert "AAPL" in symbols
    assert "SPY" in symbols


def test_stock_presets_return_curated_lists():
    presets = get_stock_presets()

    assert "Magnificent 7" in presets
    assert get_stock_preset_symbols("Magnificent 7") == [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "META",
        "NVDA",
        "TSLA",
    ]
