"""
Stock Search and Discovery Module
Provides functionality to search, discover, and get information about stocks
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from typing import List, Dict, Optional
import time

# Popular stocks by category
POPULAR_STOCKS = {
    "Tech Giants": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "ORCL", "CRM", "ADBE", "IBM", "INTC"],
    "AI & Semiconductors": ["NVDA", "AMD", "AVGO", "TSM", "ASML", "ARM", "MU", "QCOM", "AMAT", "LRCX", "KLAC", "MRVL"],
    "Cloud & Software": ["MSFT", "AMZN", "GOOGL", "CRM", "NOW", "ADBE", "SNOW", "DDOG", "NET", "MDB", "TEAM", "ZS"],
    "Cybersecurity": ["CRWD", "PANW", "FTNT", "ZS", "S", "OKTA", "CHKP", "CYBR", "TENB", "RPD"],
    "Index ETFs": ["SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "VEA", "VWO", "ACWI", "VT"],
    "Sector ETFs": ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLC", "XLB", "XLU", "XLRE"],
    "Financial": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "V", "MA", "PYPL"],
    "Healthcare": ["LLY", "UNH", "JNJ", "ABBV", "PFE", "MRK", "ABT", "TMO", "DHR", "ISRG", "SYK", "MDT"],
    "Biotech": ["AMGN", "GILD", "VRTX", "REGN", "BIIB", "MRNA", "BNTX", "ILMN", "ALNY", "NBIX"],
    "Consumer Staples": ["WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "KMB", "KHC", "GIS"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX", "BKNG", "ABNB", "CMG", "ORLY"],
    "Energy": ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "HAL", "BKR", "LNG"],
    "Industrial": ["GE", "CAT", "BA", "HON", "UNP", "UPS", "RTX", "LMT", "DE", "ETN", "PH", "MMM"],
    "Communication": ["GOOGL", "META", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS", "CHTR", "EA", "TTWO", "SPOT"],
    "Materials": ["LIN", "APD", "ECL", "SHW", "FCX", "NEM", "DD", "DOW", "NUE", "MLM", "VMC", "ALB"],
    "Real Estate": ["PLD", "AMT", "EQIX", "WELL", "SPG", "O", "DLR", "PSA", "CCI", "VICI"],
    "Utilities": ["NEE", "SO", "DUK", "CEG", "AEP", "SRE", "D", "EXC", "XEL", "PEG"],
    "International ADRs": ["TSM", "ASML", "NVO", "SAP", "TM", "SONY", "BABA", "PDD", "SHOP", "MELI", "SE", "JD"],
    "Dividend Leaders": ["JNJ", "PG", "KO", "PEP", "MCD", "WMT", "COST", "HD", "ABBV", "XOM", "CVX", "O"],
    "High Beta": ["TSLA", "NVDA", "AMD", "COIN", "RIVN", "PLTR", "SOFI", "SHOP", "SNOW", "NET", "U", "ROKU"],
}

STOCK_PRESETS = {
    "Default Mix": ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"],
    "Magnificent 7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "Broad Market ETFs": ["SPY", "QQQ", "DIA", "IWM", "VTI", "VEA", "VWO"],
    "Sector Rotation": ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLU", "XLRE"],
    "AI Stack": ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MSFT", "AMZN", "GOOGL"],
    "Defensive Basket": ["JNJ", "PG", "KO", "PEP", "WMT", "COST", "NEE", "SO"],
    "Dividend Basket": ["JNJ", "PG", "KO", "PEP", "MCD", "ABBV", "XOM", "CVX", "O"],
    "Growth Basket": ["NVDA", "MSFT", "AMZN", "GOOGL", "META", "CRM", "NOW", "CRWD"],
}

# Cache for stock info to avoid repeated API calls
STOCK_INFO_CACHE = {}
SEARCH_CACHE = {}

def search_stocks(query: str, limit: int = 10) -> List[Dict]:
    """
    Search for stocks by symbol or company name

    Args:
        query: Search term (symbol or company name)
        limit: Maximum number of results

    Returns:
        List of stock dictionaries with symbol, name, etc.
    """
    if not query or len(query) < 2:
        return []

    cache_key = f"{query.lower()}_{limit}"
    if cache_key in SEARCH_CACHE:
        return SEARCH_CACHE[cache_key]

    try:
        # Use yfinance search (limited functionality)
        # For better search, we could integrate with other APIs like Alpha Vantage
        # or IEX Cloud, but sticking with yfinance for now

        # First try exact symbol match
        try:
            ticker = yf.Ticker(query.upper())
            info = ticker.info
            if info and 'symbol' in info:
                result = [{
                    'symbol': info.get('symbol', query.upper()),
                    'name': info.get('longName', info.get('shortName', 'Unknown')),
                    'sector': info.get('sector', 'Unknown'),
                    'industry': info.get('industry', 'Unknown'),
                    'marketCap': info.get('marketCap'),
                    'currency': info.get('currency', 'USD'),
                    'exchange': info.get('exchange', 'Unknown')
                }]
                SEARCH_CACHE[cache_key] = result
                return result
        except:
            pass

        # If no exact match, try some common variations
        variations = [
            query.upper(),
            query.upper() + ".TO",  # Toronto exchange
            query.upper() + ".L",   # London exchange
            query.upper() + ".DE",  # German exchange
        ]

        results = []
        for symbol in variations[:limit]:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                if info and 'symbol' in info and len(info.get('longName', '')) > 0:
                    results.append({
                        'symbol': info.get('symbol', symbol),
                        'name': info.get('longName', info.get('shortName', 'Unknown')),
                        'sector': info.get('sector', 'Unknown'),
                        'industry': info.get('industry', 'Unknown'),
                        'marketCap': info.get('marketCap'),
                        'currency': info.get('currency', 'USD'),
                        'exchange': info.get('exchange', 'Unknown')
                    })
                    if len(results) >= limit:
                        break
            except:
                continue

        SEARCH_CACHE[cache_key] = results
        return results

    except Exception as e:
        print(f"Search error: {e}")
        return []

def get_stock_info(symbol: str) -> Optional[Dict]:
    """
    Get detailed information about a stock

    Args:
        symbol: Stock symbol

    Returns:
        Dictionary with stock information or None if not found
    """
    if symbol in STOCK_INFO_CACHE:
        return STOCK_INFO_CACHE[symbol]

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        if not info or 'symbol' not in info:
            return None

        # Get additional data
        try:
            history = ticker.history(period="1y")
            if not history.empty:
                current_price = history['Close'].iloc[-1]
                year_high = history['High'].max()
                year_low = history['Low'].min()
                avg_volume = history['Volume'].mean()
                volatility = history['Close'].pct_change().std() * (252 ** 0.5)  # Annualized
            else:
                current_price = year_high = year_low = avg_volume = volatility = None
        except:
            current_price = year_high = year_low = avg_volume = volatility = None

        stock_info = {
            'symbol': info.get('symbol', symbol),
            'name': info.get('longName', info.get('shortName', 'Unknown')),
            'sector': info.get('sector', 'Unknown'),
            'industry': info.get('industry', 'Unknown'),
            'country': info.get('country', 'Unknown'),
            'currency': info.get('currency', 'USD'),
            'exchange': info.get('exchange', 'Unknown'),
            'marketCap': info.get('marketCap'),
            'current_price': current_price,
            'year_high': year_high,
            'year_low': year_low,
            'avg_volume': avg_volume,
            'volatility': volatility,
            'pe_ratio': info.get('trailingPE'),
            'pb_ratio': info.get('priceToBook'),
            'dividend_yield': info.get('dividendYield'),
            'beta': info.get('beta'),
            'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
            'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
            'description': info.get('longBusinessSummary', ''),
        }

        STOCK_INFO_CACHE[symbol] = stock_info
        return stock_info

    except Exception as e:
        print(f"Error getting stock info for {symbol}: {e}")
        return None

def get_popular_stocks(category: str = None) -> List[str]:
    """
    Get list of popular stocks, optionally filtered by category

    Args:
        category: Category to filter by, or None for all

    Returns:
        List of stock symbols
    """
    if category and category in POPULAR_STOCKS:
        return POPULAR_STOCKS[category]
    elif category == "All":
        # Flatten all categories
        all_stocks = []
        for stocks in POPULAR_STOCKS.values():
            all_stocks.extend(stocks)
        return list(dict.fromkeys(all_stocks))  # Remove duplicates while preserving order
    else:
        return POPULAR_STOCKS["Tech Giants"]  # Default


def get_stock_presets() -> List[str]:
    """Get curated ticker-list presets."""
    return list(STOCK_PRESETS.keys())


def get_stock_preset_symbols(preset: str) -> List[str]:
    """Get symbols for a curated ticker-list preset."""
    return STOCK_PRESETS.get(preset, STOCK_PRESETS["Default Mix"])

def format_market_cap(market_cap: Optional[float]) -> str:
    """Format market cap in billions/trillions"""
    if market_cap is None or pd.isna(market_cap):
        return "N/A"

    if market_cap >= 1e12:
        return f"${market_cap/1e12:.1f}T"
    elif market_cap >= 1e9:
        return f"${market_cap/1e9:.1f}B"
    elif market_cap >= 1e6:
        return f"${market_cap/1e6:.1f}M"
    else:
        return f"${market_cap:,.0f}"

def format_price(price: Optional[float]) -> str:
    """Format price with appropriate decimals"""
    if price is None or pd.isna(price):
        return "N/A"
    elif price >= 100:
        return f"${price:.2f}"
    elif price >= 1:
        return f"${price:.2f}"
    else:
        return f"${price:.4f}"

def get_stock_categories() -> List[str]:
    """Get list of available stock categories"""
    return list(POPULAR_STOCKS.keys()) + ["All"]

def clear_cache():
    """Clear all caches"""
    STOCK_INFO_CACHE.clear()
    SEARCH_CACHE.clear()
