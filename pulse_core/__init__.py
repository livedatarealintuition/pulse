"""
Pulse Core — Shared calculation engine for all Pulse versions.
"""
from .market import MARKETS, MARKET_ORDER, is_market_open, check_any_market_active, check_us_market_active_hours
from .yfinance_client import batch_fetch_prices, get_realtime_data, get_fx_rate, get_usd_hkd_rate, price_cache, clear_price_cache, start_background_poller, stop_background_poller
from .calculator import calculate_portfolio_matrix, fetch_atr_20
from .prompt_builder import build_ai_prompt, call_ai_provider

__all__ = [
    "MARKETS", "MARKET_ORDER",
    "is_market_open", "check_any_market_active", "check_us_market_active_hours",
    "batch_fetch_prices", "get_realtime_data", "get_fx_rate", "get_usd_hkd_rate",
    "price_cache", "clear_price_cache",
    "start_background_poller", "stop_background_poller",
    "calculate_portfolio_matrix", "fetch_atr_20",
    "build_ai_prompt", "call_ai_provider",
]
