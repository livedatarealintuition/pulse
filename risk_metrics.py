"""Risk Metrics (Pro) — standalone pure computation module.

Implements the A+ transaction-aware daily value reconstruction (spec §3) and
the five risk metrics (spec §4). No Flask, no pulse_free import (sibling
module loaded by pulse_free.py). yfinance is imported lazily inside the
default close provider so the validation script runs with numpy only and no
network.
"""
import datetime
import logging
import numpy as np

RISK_METHODS = ("historical", "parametric", "montecarlo")
RISK_PERIODS = (90, 120, 180, 365, 0)   # 0 = longest (5y)
RISK_LONGEST_DAYS = 365 * 5
RISK_MC_SEED = 42
TRADING_DAYS = 252
NATIVE_CURRENCY_MAP = {"US": "USD", "HK": "HKD", "CN": "CNY", "TW": "TWD", "TWO": "TWD"}

_LOGGER = logging.getLogger("risk_metrics")


def _fetch_close_series(ticker, start_date):
    """Default close provider — lazy yfinance, returns {date_str: close}."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(start=start_date, period="max")
        closes = hist["Close"].dropna()
        return {idx.strftime("%Y-%m-%d"): float(c) for idx, c in closes.items()}
    except Exception:
        return {}


def reconstruct_daily_values(portfolio, period_days, fx_matrix, prim_cur,
                             close_provider=None):
    """Rebuild the daily portfolio value series from the transaction ledger.

    Returns (dates, values, cashflows):
      dates      — list[str] trading-date axis (union of open tickers' dates)
      values     — list[float] V(d) in primary currency (cash excluded)
      cashflows  — dict[str, float] net external cash flow per trading day
    """
    if close_provider is None:
        close_provider = _fetch_close_series
    today = datetime.date.today()
    window = RISK_LONGEST_DAYS if not period_days else int(period_days)
    start = today - datetime.timedelta(days=window)
    start_str = start.isoformat()

    by_ticker = {}
    for tx in portfolio:
        tkr = str(tx.get("ticker") or "").upper().strip()
        if tkr:
            by_ticker.setdefault(tkr, []).append(tx)

    # §3.2 — keep OPEN positions only (total_buy_shares > total_sell_shares)
    open_tickers = {}
    for tkr, txs in by_ticker.items():
        buys = sum(float(t.get("shares") or 0) for t in txs if t.get("type") == "BUY")
        sells = sum(float(t.get("shares") or 0) for t in txs if t.get("type") == "SELL")
        if buys > sells:
            open_tickers[tkr] = txs
    if not open_tickers:
        return [], [], {}

    # §3.4 — fetch daily closes per open ticker over [today − N, today]
    closes = {}
    for tkr in open_tickers:
        series = {}
        for ds, c in (close_provider(tkr, start_str) or {}).items():
            try:
                d = datetime.date.fromisoformat(str(ds))
                c = float(c)
            except (ValueError, TypeError):
                continue
            if start <= d <= today and c == c:  # c == c excludes NaN
                series[ds] = c
        if series:
            closes[tkr] = series
        else:
            _LOGGER.warning("risk: ticker %s has no close data in window — dropped", tkr)
    if not closes:
        return [], [], []

    axis = sorted({ds for s in closes.values() for ds in s})

    # per-ticker forward-fill over the union axis (IPO/delisted gaps)
    ff_closes = {}
    for tkr, s in closes.items():
        filled, last = {}, None
        for ds in axis:
            if ds in s:
                last = s[ds]
            filled[ds] = last
        ff_closes[tkr] = filled

    ticker_market = {}
    for tkr, txs in open_tickers.items():
        mkt = "US"
        for tx in txs:
            if tx.get("market"):
                mkt = tx.get("market")
                break
        ticker_market[tkr] = mkt

    # §3.3 — share ledger step function + §3.6 net cash flows
    cashflows = {}
    share_ledgers = {}
    for tkr, txs in open_tickers.items():
        ticker_dates = sorted(closes[tkr])
        pre_window = 0.0
        events = {}
        for tx in txs:
            ttype = tx.get("type")
            if ttype not in ("BUY", "SELL"):
                continue
            try:
                tx_date = datetime.date.fromisoformat(str(tx.get("date") or ""))
                shares = float(tx.get("shares") or 0)
                price = float(tx.get("price") or 0)
                commission = float(tx.get("commission") or 0)
            except (ValueError, TypeError):
                continue
            if shares <= 0:
                continue
            if tx_date > today:          # future tx — not yet effective
                continue
            if tx_date < start:          # window pre-fill — initial holding
                pre_window += shares if ttype == "BUY" else -shares
                continue
            # non-trading day → first trading day ≥ its date
            map_date = next((ds for ds in ticker_dates if ds >= tx_date.isoformat()), None)
            if map_date is None:         # takes effect after the window — ignored
                continue
            delta = shares if ttype == "BUY" else -shares
            events[map_date] = events.get(map_date, 0.0) + delta
            if ttype == "SELL":
                cashflows[map_date] = cashflows.get(map_date, 0.0) + (price * shares - commission)
            else:
                cashflows[map_date] = cashflows.get(map_date, 0.0) - (price * shares + commission)
        running = pre_window
        ledger = {}
        for ds in axis:
            running += events.get(ds, 0.0)
            ledger[ds] = running
        share_ledgers[tkr] = ledger

    # §3.5 — V(d) = Σ shares_i(d) × close_i(d) × native→primary (cash excluded)
    values = []
    for ds in axis:
        v = 0.0
        for tkr in open_tickers:
            shares = share_ledgers[tkr].get(ds, 0.0)
            close = ff_closes[tkr].get(ds)
            if shares <= 0 or close is None:
                continue
            native = NATIVE_CURRENCY_MAP.get(ticker_market[tkr], "USD")
            rate = fx_matrix.get(native, {}).get(prim_cur, 1.0)
            if not rate:                 # §11.15 — 0/missing rate → 1.0
                rate = 1.0
            v += shares * close * rate
        values.append(v)

    return axis, values, cashflows


def compute_risk_metrics(dates, values, cashflows, method, paths, prim_symbol="$"):
    """Compute the five risk metrics from the reconstructed series (spec §4).

    Returns a dict with status ('no_positions' | 'insufficient' | 'ok') plus
    preformatted display strings and raw numeric values for validation.
    """
    if not dates or not values:
        return {"status": "no_positions"}
    vals = np.asarray(values, dtype=float)
    if not np.any(vals > 0):
        return {"status": "no_positions"}

    rets = []
    for i in range(1, len(vals)):
        prev, cur = vals[i - 1], vals[i]
        if prev > 0 and cur > 0:
            rets.append((cur - prev + float(cashflows.get(dates[i], 0.0))) / prev)
    if len(rets) < 2:
        return {"status": "insufficient"}

    r = np.asarray(rets, dtype=float)
    mu_d = float(r.mean())
    sigma_d = float(r.std(ddof=1))
    mu_a = mu_d * TRADING_DAYS
    sigma_a = sigma_d * np.sqrt(TRADING_DAYS)

    # §4.5 — VaR 95% (1-day), three selectable methods
    paths = max(1000, min(10000, int(paths)))
    if method == "parametric":
        z95 = 1.6448536
        var95_daily = z95 * sigma_d - mu_d
    elif method == "montecarlo":
        rng = np.random.default_rng(RISK_MC_SEED)
        draws = rng.normal(mu_d, sigma_d, size=paths)
        var95_daily = -float(np.percentile(draws, 5))
    else:
        var95_daily = -float(np.percentile(r, 5))
    var95_daily = max(0.0, var95_daily)

    # §4.1 Sharpe / §4.2 Sortino
    sharpe = (mu_a / sigma_a) if sigma_d > 0 else None
    downside = np.minimum(r, 0.0)
    sigma_down_d = float(np.sqrt(np.mean(downside ** 2)))
    sortino = (mu_a / (sigma_down_d * np.sqrt(TRADING_DAYS))) if sigma_down_d > 0 else None

    # §4.4 — max drawdown on the cash-flow-adjusted value index V*
    # V*[0] = 1; V*[t] = V*[t-1] * (1 + r_{t-1}) — compounds every return
    vstar = np.empty(len(r) + 1)
    vstar[0] = 1.0
    for t in range(len(r)):
        vstar[t + 1] = vstar[t] * (1.0 + r[t])
    peak = np.maximum.accumulate(vstar)
    mdd = float(np.min(vstar / peak - 1.0))

    v_today = float(vals[-1])
    var_amount = var95_daily * v_today

    return {
        "status": "ok",
        "method": method,
        "sharpe": f"{sharpe:.2f}" if sharpe is not None else "—",
        "sortino": f"{sortino:.2f}" if sortino is not None else "—",
        "volatility": f"{sigma_a * 100:.1f}%",
        "max_drawdown": "0.0%" if mdd == 0 else f"−{abs(mdd) * 100:.1f}%",
        "var95_daily": var95_daily,
        "var95_amount": f"{prim_symbol}{var_amount:,.0f}",
        "var95_pct": "0.0%" if var95_daily == 0 else f"−{abs(var95_daily) * 100:.1f}%",
        "sharpe_raw": sharpe,
        "sortino_raw": sortino,
        "volatility_raw": sigma_a,
        "max_drawdown_raw": mdd,
    }
