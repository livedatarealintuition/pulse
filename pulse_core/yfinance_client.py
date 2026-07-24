"""
Pulse Core — yfinance client with batch fetch, TTL cache, and background poller.
No dependencies on Flask, Supabase, or file I/O.
"""
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Set

import yfinance as yf
from .market import check_any_market_active

# ----- Cache -----
ATR_CACHE: Dict = {}
HIGHEST_PRICE_CACHE: Dict = {}
PRICE_CACHE: Dict = {}
price_cache = PRICE_CACHE  # lowercase alias for external access

PRICE_CACHE_TTL = 30          # seconds — active trading hours
PRICE_CACHE_TTL_IDLE = 14400  # seconds (4h) — all markets closed


def get_effective_ttl() -> int:
    return PRICE_CACHE_TTL if check_any_market_active() else PRICE_CACHE_TTL_IDLE


def clear_price_cache():
    PRICE_CACHE.clear()
    HIGHEST_PRICE_CACHE.clear()


# ----- Single-ticker fetch -----
def get_realtime_data(ticker: str) -> Dict:
    """Return {'price', 'prev_close', 'stale'} for a single ticker."""
    cached = PRICE_CACHE.get(ticker)
    if cached:
        age = (datetime.now() - cached["ts"]).total_seconds()
        if age < get_effective_ttl():
            return {"price": cached["price"], "prev_close": cached["prev_close"], "stale": False, "cached": True}

    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        price = float(fi.last_price) if fi.last_price else 0.0
        prev = float(fi.previous_close) if fi.previous_close else 0.0
        if price > 0:
            PRICE_CACHE[ticker] = {"price": price, "prev_close": prev, "ts": datetime.now()}
        elif cached:
            return {"price": cached["price"], "prev_close": cached["prev_close"], "stale": True}
        return {"price": price, "prev_close": prev, "stale": False}
    except Exception:
        if cached:
            age = (datetime.now() - cached["ts"]).total_seconds()
            return {"price": cached["price"], "prev_close": cached["prev_close"], "stale": True, "age_sec": age}
        return {"price": 0.0, "prev_close": 0.0, "stale": True}


# ----- Batch fetch (used by calculator) -----
def _batch_fetch_prices(tickers_list: List[str]) -> Dict:
    """Fetch prices for multiple tickers with TTL-aware caching.
    Only calls yfinance for stale tickers — as ONE batch call."""
    if not tickers_list:
        return {}
    now = datetime.now()
    ttl = get_effective_ttl()
    results = {}
    stale_tickers = []

    for tk in tickers_list:
        cached = PRICE_CACHE.get(tk)
        if cached and (now - cached["ts"]).total_seconds() < ttl:
            results[tk] = {"price": cached["price"], "prev_close": cached["prev_close"], "cached": True}
        else:
            stale_tickers.append(tk)

    if stale_tickers:
        try:
            yt = yf.Tickers(" ".join(stale_tickers))
            for sym, t in yt.tickers.items():
                try:
                    fi = t.fast_info
                    price = float(fi.last_price) if fi.last_price else 0.0
                    prev = float(fi.previous_close) if fi.previous_close else 0.0
                    if price > 0:
                        PRICE_CACHE[sym] = {"price": price, "prev_close": prev, "ts": now}
                        results[sym] = {"price": price, "prev_close": prev}
                    else:
                        cached = PRICE_CACHE.get(sym)
                        if cached:
                            results[sym] = {"price": cached["price"], "prev_close": cached["prev_close"]}
                        else:
                            results[sym] = {"price": 0.0, "prev_close": 0.0}
                except Exception:
                    cached = PRICE_CACHE.get(sym)
                    results[sym] = {"price": cached["price"], "prev_close": cached["prev_close"]} if cached else {"price": 0.0, "prev_close": 0.0}
        except Exception:
            for tk in stale_tickers:
                cached = PRICE_CACHE.get(tk)
                results[tk] = {"price": cached["price"], "prev_close": cached["prev_close"]} if cached else {"price": 0.0, "prev_close": 0.0}

    return results


# Alias for external callers
batch_fetch_prices = _batch_fetch_prices


# ----- ATR -----
def fetch_atr_20(ticker: str) -> float:
    """Calculate 20-period ATR using yfinance history."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    if ticker in ATR_CACHE and ATR_CACHE[ticker].get("date") == today_str:
        return ATR_CACHE[ticker]["atr"]
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="1mo")
        if df.empty or len(df) < 2:
            return ATR_CACHE.get(ticker, {}).get("atr", 0.0)
        highs, lows, closes = df["High"].values, df["Low"].values, df["Close"].values
        tr_list = []
        for i in range(1, len(closes)):
            tr_list.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        atr_20 = sum(tr_list[-20:]) / min(len(tr_list[-20:]), 20) if tr_list else 0.0
        ATR_CACHE[ticker] = {"date": today_str, "atr": atr_20}
        return atr_20
    except Exception:
        return ATR_CACHE.get(ticker, {}).get("atr", 0.0)


# ----- Forex -----
def get_fx_rate(currency: str) -> Optional[float]:
    rate_data = get_realtime_data(f"{currency}=X")
    return rate_data["price"] if rate_data["price"] > 0 else None


def get_usd_hkd_rate() -> float:
    return get_fx_rate("HKD") or 7.80


# ----- Background Poller (cloud mode) -----
_poller_thread: Optional[threading.Thread] = None
_poller_stop = threading.Event()
_poller_tickers_callback = None  # Callable that returns Set[str]
_poller_interval = 60  # seconds


def start_background_poller(tickers_callback, interval: int = 60):
    """
    Start a daemon thread that periodically fetches ALL user tickers in ONE batch.
    tickers_callback: callable returning Set[str] of all tickers to track.
    """
    global _poller_tickers_callback, _poller_interval, _poller_thread, _poller_stop
    _poller_tickers_callback = tickers_callback
    _poller_interval = interval
    _poller_stop.clear()

    def _poll_loop():
        while not _poller_stop.is_set():
            try:
                tickers = _poller_tickers_callback()
                if tickers:
                    unique = list(tickers)
                    _batch_fetch_prices(unique)
            except Exception:
                pass
            _poller_stop.wait(_poller_interval)

    _poller_thread = threading.Thread(target=_poll_loop, daemon=True, name="pulse-poller")
    _poller_thread.start()


def stop_background_poller():
    _poller_stop.set()
