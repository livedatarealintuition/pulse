"""
Pulse Core — Portfolio calculation engine.
Takes portfolio data as a parameter (no file I/O).
"""
from typing import List, Dict, Tuple

from .yfinance_client import (
    batch_fetch_prices, get_realtime_data, fetch_atr_20,
    get_fx_rate, get_usd_hkd_rate, HIGHEST_PRICE_CACHE,
)
from .market import MARKET_ORDER


def calculate_portfolio_matrix(
    portfolio: List[Dict],
    sec_cur: str = "HKD",
) -> Tuple[List[Dict], List[str], Dict[str, str], float, float, float, str]:
    """
    Core portfolio calculation. Takes raw portfolio list, returns computed data.

    Args:
        portfolio: List of transactions, each with keys:
            ticker, type ('BUY'/'SELL'), shares, price, commission, date, market
        sec_cur: Secondary currency for display (HKD, EUR, GBP, etc.)

    Returns:
        processed_holdings: List of computed holdings with P&L, ROI, stop-loss, etc.
        open_tickers_sorted: Sorted list of currently-open tickers
        ticker_market: Dict mapping ticker → market
        total_market_value_usd: Total USD market value
        total_open_cost_usd: Total USD cost basis
        usd_hkd: USD-to-secondary-currency rate
        sec_cur: The secondary currency used
    """
    usd_hkd = get_fx_rate(sec_cur) or get_usd_hkd_rate()
    if sec_cur in ("EUR", "GBP") and usd_hkd:
        usd_hkd = 1.0 / usd_hkd  # Indirect quote correction

    # Aggregate by ticker
    aggregated = {}
    for idx, tx in enumerate(portfolio):
        ticker = tx["ticker"].upper()
        aggregated.setdefault(ticker, {"ticker": ticker, "buys": [], "sells": [], "history_txs": []})
        tx_with_idx = tx.copy()
        tx_with_idx["original_index"] = idx
        aggregated[ticker]["history_txs"].append(tx_with_idx)
        if tx["type"] == "BUY":
            aggregated[ticker]["buys"].append(tx)
        else:
            aggregated[ticker]["sells"].append(tx)

    # Batch fetch all prices
    all_tickers = list(aggregated.keys())
    batch_prices = batch_fetch_prices(all_tickers) if all_tickers else {}

    processed_holdings, open_tickers_set, ticker_market = [], set(), {}
    total_market_value_usd = total_open_cost_usd = 0.0

    for ticker, data in aggregated.items():
        data["history_txs"].sort(key=lambda x: x["date"])

        total_buy_shares = sum(float(x["shares"]) for x in data["buys"])
        total_buy_spend = sum(float(x["shares"]) * float(x["price"]) + float(x.get("commission", 0)) for x in data["buys"])
        total_sell_shares = sum(float(x["shares"]) for x in data["sells"])
        total_sell_proceeds = sum(float(x["shares"]) * float(x["price"]) - float(x.get("commission", 0)) for x in data["sells"])

        current_shares = max(0.0, total_buy_shares - total_sell_shares)
        avg_buy_price = (total_buy_spend / total_buy_shares) if total_buy_shares > 0 else 0.0
        current_open_cost = current_shares * avg_buy_price

        bp = batch_prices.get(ticker, {})
        current_price = bp.get("price", 0.0) if bp.get("price", 0.0) > 0 else 0.0
        prev_close = bp.get("prev_close", 0.0)
        if current_price <= 0:
            rt_data = get_realtime_data(ticker)
            current_price, prev_close = rt_data["price"], rt_data["prev_close"]

        day_change = current_price - prev_close
        day_change_pct = (day_change / prev_close * 100) if prev_close > 0 else 0
        current_mv = current_shares * current_price
        pnl_usd = current_mv - current_open_cost if current_shares > 0 else 0.0
        roi = (pnl_usd / current_open_cost) * 100 if current_open_cost > 0 else 0.0

        capital_recovered_flag = (total_sell_proceeds >= total_buy_spend) and (total_buy_spend > 0)
        shares_to_sell_to_recover = 0.0
        if current_shares > 0 and not capital_recovered_flag:
            remaining_cost = total_buy_spend - total_sell_proceeds
            if current_price > 0:
                shares_to_sell_to_recover = min(remaining_cost / current_price, current_shares)

        if current_shares > 0:
            total_market_value_usd += current_mv
            total_open_cost_usd += current_open_cost
            open_tickers_set.add(ticker)
            ticker_market[ticker] = data["history_txs"][0].get("market") or "US"
            status = "OPEN"
            atr_20 = fetch_atr_20(ticker)
            HIGHEST_PRICE_CACHE[ticker] = max(
                HIGHEST_PRICE_CACHE.get(ticker, current_price),
                current_price, avg_buy_price,
            )
            stop_loss = HIGHEST_PRICE_CACHE[ticker] - (2.0 * atr_20)
            is_danger = (current_price <= stop_loss) and (atr_20 > 0)
        else:
            status, atr_20, stop_loss, is_danger = "CLOSED", 0, 0, False

        processed_holdings.append({
            "ticker": ticker, "status": status,
            "total_shares": f"{int(current_shares)}",
            "avg_buy_price": f"{avg_buy_price:,.2f}",
            "current_price": f"{current_price:,.2f}",
            "day_change": day_change, "day_change_pct": day_change_pct,
            "stop_loss": stop_loss, "atr_20": atr_20, "is_danger": is_danger,
            "current_mv": f"{current_mv:,.2f}" if current_shares > 0 else "-",
            "current_mv_raw": current_mv,
            "pnl_usd_str": f"{pnl_usd:+,.2f}" if current_shares > 0 else "-",
            "pnl_hkd_str": f"{(pnl_usd * usd_hkd):+,.2f}" if current_shares > 0 else "-",
            "roi_str": f"{roi:+.2f}%" if current_shares > 0 else "-",
            "market": data["history_txs"][0].get("market") or "US",
            "praw": pnl_usd,
            "capital_recovered": capital_recovered_flag,
            "capital_recovered_str": f"{total_sell_proceeds:,.2f}" if total_sell_proceeds > 0 else "-",
            "shares_to_sell_to_recover": f"{shares_to_sell_to_recover:.1f}",
            "history_txs": data["history_txs"],
        })

    # Sort by market order
    processed_holdings.sort(key=lambda s: (MARKET_ORDER.get(s.get("market", "US"), 99), s["ticker"]))
    open_tickers_sorted = sorted(open_tickers_set, key=lambda t: (MARKET_ORDER.get(ticker_market.get(t, "US"), 99), t))

    return processed_holdings, open_tickers_sorted, ticker_market, total_market_value_usd, total_open_cost_usd, usd_hkd, sec_cur
