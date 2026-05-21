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
    "Tech Giants": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "Financial": ["JPM", "BAC", "WFC", "GS", "MS", "V", "MA"],
    "Healthcare": ["JNJ", "PFE", "UNH", "MRK", "ABT", "TMO", "DHR"],
    "Consumer": ["WMT", "HD", "MCD", "KO", "PEP", "PG", "COST"],
    "Energy": ["XOM", "CVX", "COP", "EOG", "SLB", "PXD"],
    "Industrial": ["BA", "CAT", "GE", "HON", "MMM", "UPS"],
    "Communication": ["VZ", "T", "CMCSA", "NFLX", "DIS"],
    "Materials": ["LIN", "APD", "ECL", "SHW", "FCX"]
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
        return list(set(all_stocks))  # Remove duplicates
    else:
        return POPULAR_STOCKS["Tech Giants"]  # Default

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
