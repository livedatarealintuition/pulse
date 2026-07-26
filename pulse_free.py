import os
import json
import secrets
import requests
from requests.exceptions import Timeout, ConnectionError as ReqConnectionError
import time
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_from_directory, g
import yfinance as yf

app = Flask(__name__)
CLOUD_MODE = os.getenv("CLOUD_MODE", "").lower() in ("1", "true", "yes", "cloud")

if CLOUD_MODE:
    from supabase import create_client

    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")             # anon key (for auth)
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")  # service_role (for DB)

    if not SUPABASE_URL:
        raise RuntimeError("CLOUD_MODE is enabled but SUPABASE_URL is not set")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)           # auth client
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)  # DB client (bypasses RLS)

# ==================== 🎯 1. 基礎路徑與配置 ====================
# 用 PULSE_HOME 環境變數指向 data 目錄，未設定時 fallback 到 script 所在目錄
BASE_DIR = os.environ.get("PULSE_HOME", os.path.dirname(os.path.abspath(__file__)))

PORTFOLIO_JSON = os.path.join(BASE_DIR, "portfolio.json")
WATCHLIST_JSON = os.path.join(BASE_DIR, "watchlist.json")  
CONFIG_JSON = os.path.join(BASE_DIR, "system_config.json")

VERSION = "V1.820"
IS_PRO = False  # 由 pulse_pro.py 覆蓋為 True
CHANGELOG = [
    ("V1.820", "[Session 8] 20 items: Editable prompt (3 levels), mode toggle, i18n rebuild, Weight%, Market Dist, Cash Ratio, API confirm, smart errors, settings tabs, timeout, modal, label a11y"),
    ("V1.8", "[Session 8] AI Audit: rich portfolio prompt + local inference presets (Ollama/vLLM/LM Studio)"),
    ("V1.716", "[Session 7] Remove Crucix macro report integration"),
    ("V1.715", "[Session 7] 15 fixes: PULSE_HOME, Free/Pro split, local CSS, form labels, JS escape, EUR/GBP FX"),
    ("V1.612", "[Session 6] 12 fixes: yfinance refactor, batch fetch, TTL cache, atomic write, TWO market, Pulse rebrand"),
    ("V1.5", "[Session 5] Initial release: multi-market, buy/sell, i18n, watchlist, multi-currency"),
]

DEFAULT_CONFIG = {
    "api_key": "", "refresh_interval": 30, "language": "zh_tw",
    "ai_provider": "gemini", "ai_model": "gemini-2.5-flash",
    "custom_api_url": "https://generativelanguage.googleapis.com/v1beta/models/",
    "secondary_currency": "HKD",
    "ai_timeout": 60,
    "cash_balance": 0,
    "prompt_level": "balanced",
    "custom_prompt": "",
    "prompt_mode": "style"
}
# ==================== 翻译字典 (i18n) ====================
TRANSLATIONS = {
    "zh_tw": {
        "title": "Pulse",
        "subtitle": "Live Data · Real Intuition",
        "auto_refresh_label": "⏱️ 更新 (秒):",
        "refresh_tooltip": "Yahoo Finance API 限制，建議 ≥30 秒以避免請求過多。休市時自動延長至數小時。",
        "ai_report_btn": "⚡ 產生AI報告",
        "total_mv_label": "當前持倉總市值",
        "total_pnl_label": "🚨 全局持倉盈虧 (PnL)",
        "summary_label": "📊 Summary 時間鎖狀態",
        "buy_title": "🟢 新增股票持倉",
        "buy_ticker_ph": "ASTS",
        "buy_price_ph": "價格",
        "buy_shares_ph": "股數",
        "buy_confirm": "確認買入",
        "buy_est_cost": "預計成本",
        "ticker_label": "代碼",
        "market_label": "市場",
        "date_label": "日期",
        "price_label": "單價",
        "shares_label": "股數",
        "commission_label": "手續費",
        "sell_title": "🔴 賣出股票持倉",
        "sell_select_ticker": "-- 選擇股票 --",
        "sell_price_ph": "價格",
        "sell_shares_ph": "股數",
        "sell_confirm": "確認賣出",
        "sell_est_income": "預計收入",
        "sell_ticker_label": "選擇股票",
        "sell_date_label": "日期",
        "sell_price_label": "單價",
        "sell_shares_label": "股數",
        "sell_commission_label": "手續費",
        "table_expand": "展開",
        "table_ticker": "股票",
        "table_shares": "總持股",
        "tab_all": "全部",
        "table_avg_price": "平衡價",
        "table_current_price": "即時現價與日變動",
        "table_stop_loss": "ATR 移動止蝕(2x)",
        "table_mv": "當前總現值",
        "table_pnl": "持倉盈虧",
        "history_title": "歷史流水明細",
        "history_type": "類型",
        "history_date": "交易日期",
        "history_price": "價格",
        "history_shares": "股數",
        "history_commission": "佣金",
        "history_action": "操作",
        "history_delete": "🗑️ 刪除",
        "settings_title": "⚙️ 系統設定",
        "settings_close": "✕ 關閉",
        "settings_tab_general": "一般設定",
        "settings_tab_ai": "AI 模型",
        "settings_timeout": "Timeout (秒)",
        "settings_prompt_level": "分析風格",
        "settings_custom_prompt": "自訂 Prompt",
        "prompt_level_strict": "嚴格 — 聚焦風險與止損紀律",
        "prompt_level_balanced": "平衡 — 綜合分析與建議",
        "prompt_level_relaxed": "寬鬆 — 成長導向、樂觀評估",
        "settings_prompt_mode": "Prompt 來源",
        "prompt_mode_style": "使用分析風格",
        "prompt_mode_custom": "使用自訂 Prompt",
        "table_weight": "持股權重",
        "card_market_dist": "市場分佈",
        "card_cash_ratio": "現金比率",
        "settings_cash_balance": "現金餘額 (USD)",
        "settings_timeout_hint": "建議 30-120 秒",
        "settings_prompt_hint": "可用變數：{summary} {holdings} {alloc} {lang}。留空使用分析風格的預設 Prompt。",
        "changelog_title": "更新日誌",
        "settings_ai_provider": "AI Provider",
        "settings_model": "Model Name",
        "settings_api_url": "Custom API URL",
        "settings_api_key": "API Key",
        "settings_language": "介面語言",
        "settings_currency": "顯示貨幣",
        "settings_save": "儲存設定",
        "wl_add_cat": "+ 新增分組",
        "wl_delete_cat": "刪除組",
        "wl_input_placeholder": "輸入代碼",
        "wl_new_cat_prompt": "新分組名稱",
        "watchlist_title": "🔍 WATCHLIST 自選股",
        "capital_recovered_badge": "💰 本金已收回",
        "capital_recover_hint": "💡 需再賣出",
        "capital_recover_hint_end": "股即可收回本金",
        "capital_recovered_label": "已收回本金",
        "target_set_btn": "🎯 設定目標價",
        "target_alert_title": "🎯 目標價警示",
        "target_alert_hit": "跌至目標價",
        "target_alert_current": "現價",
        "audit_title": "🧠 AI 投資組合分析報告",
        "audit_loading": "AI 分析中，請稍候...",
        "audit_confirm": "將會使用你的 API Key 呼叫 AI 模型產生報告，確定要繼續嗎？"
    },
    "zh_cn": {
        "title": "Pulse",
        "subtitle": "Live Data · Real Intuition",
        "auto_refresh_label": "⏱️ 更新 (秒):",
        "refresh_tooltip": "Yahoo Finance API 限制，建议 ≥30 秒以避免请求过多。休市时自动延长至数小时。",
        "ai_report_btn": "⚡ 生成AI报告",
        "total_mv_label": "当前持仓总市值",
        "total_pnl_label": "🚨 全局持仓盈亏 (PnL)",
        "summary_label": "📊 Summary 时间锁状态",
        "buy_title": "🟢 新增股票持仓",
        "buy_ticker_ph": "ASTS",
        "buy_price_ph": "价格",
        "buy_shares_ph": "股数",
        "buy_confirm": "确认买入",
        "buy_est_cost": "预计成本",
        "ticker_label": "代码",
        "market_label": "市场",
        "date_label": "日期",
        "price_label": "单价",
        "shares_label": "股数",
        "commission_label": "手续费",
        "sell_title": "🔴 卖出股票持仓",
        "sell_select_ticker": "-- 选择股票 --",
        "sell_price_ph": "价格",
        "sell_shares_ph": "股数",
        "sell_confirm": "确认卖出",
        "sell_est_income": "预计收入",
        "sell_ticker_label": "选择股票",
        "sell_date_label": "日期",
        "sell_price_label": "单价",
        "sell_shares_label": "股数",
        "sell_commission_label": "手续费",
        "table_expand": "展开",
        "table_ticker": "股票",
        "table_shares": "总持股",
        "tab_all": "全部",
        "table_avg_price": "平衡价",
        "table_current_price": "即时现价与日变动",
        "table_stop_loss": "ATR 移动止损(2x)",
        "table_mv": "当前总现值",
        "table_pnl": "持仓盈亏",
        "history_title": "历史流水明细",
        "history_type": "类型",
        "history_date": "交易日期",
        "history_price": "价格",
        "history_shares": "股数",
        "history_commission": "佣金",
        "history_action": "操作",
        "history_delete": "🗑️ 删除",
        "settings_title": "⚙️ 系统设定",
        "settings_close": "✕ 关闭",
        "settings_tab_general": "一般设定",
        "settings_tab_ai": "AI 模型",
        "settings_timeout": "Timeout (秒)",
        "settings_prompt_level": "分析风格",
        "settings_custom_prompt": "自订 Prompt",
        "prompt_level_strict": "严格 — 聚焦风险与止损纪律",
        "prompt_level_balanced": "平衡 — 综合分析建议",
        "prompt_level_relaxed": "宽松 — 成长导向、乐观评估",
        "settings_prompt_mode": "Prompt 来源",
        "prompt_mode_style": "使用分析风格",
        "prompt_mode_custom": "使用自订 Prompt",
        "table_weight": "持股权重",
        "card_market_dist": "市场分布",
        "card_cash_ratio": "现金比率",
        "settings_cash_balance": "现金余额 (USD)",
        "settings_timeout_hint": "建议 30-120 秒",
        "settings_prompt_hint": "可用变数：{summary} {holdings} {alloc} {lang}。留空使用分析风格的预设 Prompt。",
        "changelog_title": "更新日志",
        "settings_ai_provider": "AI Provider",
        "settings_model": "Model Name",
        "settings_api_url": "Custom API URL",
        "settings_api_key": "API Key",
        "settings_language": "界面语言",
        "settings_currency": "显示货币",
        "settings_save": "保存设定",
        "wl_add_cat": "+ 新增分组",
        "wl_delete_cat": "删除组",
        "wl_input_placeholder": "输入代码",
        "wl_new_cat_prompt": "新分组名称",
        "watchlist_title": "🔍 WATCHLIST 自选股",
        "capital_recovered_badge": "💰 本金已收回",
        "capital_recover_hint": "💡 需再卖出",
        "capital_recover_hint_end": "股即可收回本金",
        "capital_recovered_label": "已收回本金",
        "target_set_btn": "🎯 设定目标价",
        "target_alert_title": "🎯 目标价警示",
        "target_alert_hit": "跌至目标价",
        "target_alert_current": "现价",
        "audit_title": "🧠 AI 投资组合分析报告",
        "audit_loading": "AI 分析中，请稍候...",
        "audit_confirm": "将会使用你的 API Key 调用 AI 模型生成报告，确定要继续吗？"
    },
    "en": {
        "title": "Pulse",
        "subtitle": "Live Data · Real Intuition",
        "auto_refresh_label": "⏱️ Refresh (sec):",
        "refresh_tooltip": "Yahoo Finance API rate limit. Recommend ≥30s to avoid excessive requests. Auto-extends to hours when markets closed.",
        "ai_report_btn": "⚡ Generate AI Report",
        "total_mv_label": "Total Market Value",
        "total_pnl_label": "🚨 Total P&L",
        "summary_label": "📊 Summary Time Lock",
        "buy_title": "🟢 Add Position",
        "buy_ticker_ph": "ASTS",
        "buy_price_ph": "Price",
        "buy_shares_ph": "Shares",
        "buy_confirm": "Confirm Buy",
        "buy_est_cost": "Est. Cost",
        "ticker_label": "Ticker",
        "market_label": "Market",
        "date_label": "Date",
        "price_label": "Price",
        "shares_label": "Shares",
        "commission_label": "Commission",
        "sell_title": "🔴 Sell Position",
        "sell_select_ticker": "-- Select Ticker --",
        "sell_price_ph": "Price",
        "sell_shares_ph": "Shares",
        "sell_confirm": "Confirm Sell",
        "sell_est_income": "Est. Proceeds",
        "sell_ticker_label": "Ticker",
        "sell_date_label": "Date",
        "sell_price_label": "Price",
        "sell_shares_label": "Shares",
        "sell_commission_label": "Commission",
        "table_expand": "Expand",
        "table_ticker": "Ticker",
        "table_shares": "Total Shares",
        "tab_all": "All",
        "table_avg_price": "Avg Cost",
        "table_current_price": "Price & Day Change",
        "table_stop_loss": "ATR Trailing Stop(2x)",
        "table_mv": "Market Value",
        "table_pnl": "P&L",
        "history_title": "Transaction History",
        "history_type": "Type",
        "history_date": "Date",
        "history_price": "Price",
        "history_shares": "Shares",
        "history_commission": "Commission",
        "history_action": "Action",
        "history_delete": "🗑️ Delete",
        "settings_title": "⚙️ System Settings",
        "settings_close": "✕ Close",
        "settings_tab_general": "General",
        "settings_tab_ai": "AI Model",
        "settings_timeout": "Timeout (sec)",
        "settings_prompt_level": "Analysis Style",
        "settings_custom_prompt": "Custom Prompt",
        "prompt_level_strict": "Strict — Risk & stop-loss focused",
        "prompt_level_balanced": "Balanced — Comprehensive analysis",
        "prompt_level_relaxed": "Relaxed — Growth-oriented, optimistic",
        "settings_prompt_mode": "Prompt Source",
        "prompt_mode_style": "Use Analysis Style",
        "prompt_mode_custom": "Use Custom Prompt",
        "table_weight": "Weight %",
        "card_market_dist": "Market Distribution",
        "card_cash_ratio": "Cash Ratio",
        "settings_cash_balance": "Cash Balance (USD)",
        "settings_timeout_hint": "Recommend 30-120 sec",
        "settings_prompt_hint": "Variables: {summary} {holdings} {alloc} {lang}. Leave empty to use Analysis Style preset.",
        "changelog_title": "Changelog",
        "settings_ai_provider": "AI Provider",
        "settings_model": "Model Name",
        "settings_api_url": "Custom API URL",
        "settings_api_key": "API Key",
        "settings_language": "Language",
        "settings_currency": "Currency",
        "settings_save": "Save Settings",
        "wl_add_cat": "+ Add Group",
        "wl_delete_cat": "Delete Group",
        "wl_input_placeholder": "Enter ticker",
        "wl_new_cat_prompt": "New group name",
        "watchlist_title": "🔍 WATCHLIST",
        "capital_recovered_badge": "💰 Capital Recovered",
        "capital_recover_hint": "💡 Sell",
        "capital_recover_hint_end": "more shares to recover cost",
        "capital_recovered_label": "Capital Recovered",
        "target_set_btn": "🎯 Set Target",
        "target_alert_title": "🎯 Target Alerts",
        "target_alert_hit": "Hit target",
        "target_alert_current": "Current",
        "audit_title": "🧠 AI Portfolio Analysis Report",
        "audit_loading": "Analyzing with AI model...",
        "audit_confirm": "This will use your API key to call the AI model. Continue?"
    },
}
def get_translations(lang):
    return TRANSLATIONS.get(lang, TRANSLATIONS["zh_tw"])


# 確保檔案存在
for path, default_content in [(PORTFOLIO_JSON, []), (WATCHLIST_JSON, {"categories": {}}), (CONFIG_JSON, DEFAULT_CONFIG)]:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f: json.dump(default_content, f, indent=4, ensure_ascii=False)

def load_json_file(path, default_val):
    with open(path, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return default_val

_save_lock = threading.Lock()

def save_json_file(path, data):
    """Thread-safe atomic write: Lock + tmp file + os.replace."""
    tmp = path + '.tmp'
    with _save_lock:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, path)

def load_portfolio():
    """Load portfolio transactions. JSON (selfhosted) or Supabase (cloud)."""
    if not CLOUD_MODE:
        return load_json_file(PORTFOLIO_JSON, [])
    try:
        rows = supabase_admin.table("transactions").select("*").eq("user_id", g.user_id).order("date").execute()
        result = []
        for r in (rows.data or []):
            result.append({
                "type": r["type"],
                "market": r.get("market", "US"),
                "date": r["date"],
                "ticker": r["ticker"].upper(),
                "price": str(r["price"]),
                "commission": str(r.get("commission", 0)),
                "shares": str(r["shares"])
            })
        return result
    except Exception as e:
        print(f"[load_portfolio] Supabase error: {e}")
        return []

def save_portfolio(data):
    """Save portfolio transactions atomically. JSON (selfhosted) or Supabase (cloud)."""
    if not CLOUD_MODE:
        save_json_file(PORTFOLIO_JSON, data)
        return
    try:
        supabase_admin.table("transactions").delete().eq("user_id", g.user_id).execute()
        if data:
            rows = []
            for tx in data:
                rows.append({
                    "user_id": g.user_id,
                    "ticker": tx["ticker"].upper(),
                    "type": tx["type"],
                    "market": tx.get("market", "US"),
                    "date": tx["date"],
                    "price": float(tx["price"]),
                    "shares": float(tx["shares"]),
                    "commission": float(tx.get("commission", 0))
                })
            supabase_admin.table("transactions").insert(rows).execute()
    except Exception as e:
        print(f"[save_portfolio] Supabase error: {e}")
def load_watchlist():
    """Load watchlist. JSON (selfhosted) or Supabase (cloud)."""
    if not CLOUD_MODE:
        return load_json_file(WATCHLIST_JSON, {"categories": {}})
    try:
        rows = supabase_admin.table("watchlist").select("*").eq("user_id", g.user_id).order("sort_order").execute()
        cats = {}
        targets = {}
        for r in (rows.data or []):
            cat = r.get("category", "Default")
            ticker = r["ticker"].upper()
            cats.setdefault(cat, []).append(ticker)
            if r.get("target_price"):
                targets[ticker] = float(r["target_price"])
        return {"categories": cats, "targets": targets}
    except Exception as e:
        print(f"[load_watchlist] Supabase error: {e}")
        return {"categories": {}}

def save_watchlist(data):
    """Save watchlist. JSON (selfhosted) or Supabase (cloud)."""
    if not CLOUD_MODE:
        save_json_file(WATCHLIST_JSON, data)
        return
    try:
        supabase_admin.table("watchlist").delete().eq("user_id", g.user_id).execute()
        rows = []
        sort = 0
        targets = data.get("targets", {})
        for cat_name, tickers in data.get("categories", {}).items():
            for tk in tickers:
                row = {
                    "user_id": g.user_id,
                    "category": cat_name,
                    "ticker": tk.upper(),
                    "sort_order": sort,
                }
                if tk in targets:
                    row["target_price"] = targets[tk]
                rows.append(row)
                sort += 1
        if rows:
            supabase_admin.table("watchlist").insert(rows).execute()
    except Exception as e:
        print(f"[save_watchlist] Supabase error: {e}")
def load_config():
    """Load user config. JSON (selfhosted) or Supabase profiles (cloud)."""
    if not CLOUD_MODE:
        return load_json_file(CONFIG_JSON, DEFAULT_CONFIG)
    try:
        profile = supabase_admin.table("profiles").select("*").eq("user_id", g.user_id).single().execute()
        if profile.data:
            return {**DEFAULT_CONFIG, **profile.data}
        supabase_admin.table("profiles").insert({"user_id": g.user_id}).execute()
        return dict(DEFAULT_CONFIG)
    except Exception as e:
        print(f"[load_config] Supabase error: {e}")
        return dict(DEFAULT_CONFIG)

def save_config(data):
    """Save user config. JSON (selfhosted) or Supabase profiles (cloud)."""
    if not CLOUD_MODE:
        save_json_file(CONFIG_JSON, data)
        return
    try:
        supabase_admin.table("profiles").upsert({
            "user_id": g.user_id,
            **data
        }).execute()
    except Exception as e:
        print(f"[save_config] Supabase error: {e}")

# ==================== 🎯 2. 數據抓取與工具 (yfinance) ====================
ATR_CACHE = {}
HIGHEST_PRICE_CACHE = {}
PRICE_CACHE = {}
PRICE_CACHE_TTL = 30          # seconds — active trading hours
PRICE_CACHE_TTL_IDLE = 14400  # seconds (4h) — all markets closed

def get_effective_ttl():
    """Return short TTL during trading hours, long TTL when all markets closed."""
    return PRICE_CACHE_TTL if check_any_market_active() else PRICE_CACHE_TTL_IDLE

def _batch_fetch_prices(tickers_list):
    """Fetch prices for multiple tickers with TTL-aware caching.
    Returns cached data for fresh tickers; only calls yfinance for stale ones
    (as ONE batch call). Result dict: {ticker: {'price': float, 'prev_close': float}}"""
    if not tickers_list:
        return {}
    now = datetime.now()
    ttl = get_effective_ttl()
    results = {}
    stale_tickers = []

    # Split: fresh from cache, stale need re-fetch
    for tk in tickers_list:
        cached = PRICE_CACHE.get(tk)
        if cached and (now - cached['ts']).total_seconds() < ttl:
            results[tk] = {'price': cached['price'], 'prev_close': cached['prev_close'], 'cached': True}
        else:
            stale_tickers.append(tk)

    # Batch fetch only stale tickers in ONE yfinance call
    if stale_tickers:
        try:
            yt = yf.Tickers(" ".join(stale_tickers))
            for sym, t in yt.tickers.items():
                try:
                    fi = t.fast_info
                    price = float(fi.last_price) if fi.last_price else 0.0
                    prev = float(fi.previous_close) if fi.previous_close else 0.0
                    if price > 0:
                        PRICE_CACHE[sym] = {'price': price, 'prev_close': prev, 'ts': now}
                        results[sym] = {'price': price, 'prev_close': prev}
                    elif cached:
                        results[sym] = {'price': cached['price'], 'prev_close': cached['prev_close']}
                    else:
                        results[sym] = {'price': 0.0, 'prev_close': 0.0}
                except Exception:
                    # Fallback to cache even if expired — better than 0.0
                    cached = PRICE_CACHE.get(sym)
                    results[sym] = {'price': cached['price'], 'prev_close': cached['prev_close']} if cached else {'price': 0.0, 'prev_close': 0.0}
        except Exception:
            # Entire batch failed — return cached for everything
            for tk in stale_tickers:
                cached = PRICE_CACHE.get(tk)
                results[tk] = {'price': cached['price'], 'prev_close': cached['prev_close']} if cached else {'price': 0.0, 'prev_close': 0.0}

    return results

def get_realtime_data(ticker):
    """Return {'price', 'prev_close', 'stale'} for a ticker.
    Uses PRICE_CACHE with TTL; calls yfinance on cache miss."""
    cached = PRICE_CACHE.get(ticker)
    if cached:
        age = (datetime.now() - cached['ts']).total_seconds()
        if age < get_effective_ttl():
            return {'price': cached['price'], 'prev_close': cached['prev_close'], 'stale': False, 'cached': True}

    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        price = float(fi.last_price) if fi.last_price else 0.0
        prev = float(fi.previous_close) if fi.previous_close else 0.0
        if price > 0:
            PRICE_CACHE[ticker] = {'price': price, 'prev_close': prev, 'ts': datetime.now()}
        elif cached:
            # API returned 0.0 — fall back to last known good price
            return {'price': cached['price'], 'prev_close': cached['prev_close'], 'stale': True}
        return {'price': price, 'prev_close': prev, 'stale': False}
    except Exception as e:
        if cached:
            age = (datetime.now() - cached['ts']).total_seconds()
            return {'price': cached['price'], 'prev_close': cached['prev_close'], 'stale': True, 'age_sec': age}
        return {'price': 0.0, 'prev_close': 0.0, 'stale': True, 'error': str(e)[:80]}

def fetch_atr_20(ticker):
    """Calculate 20-period ATR using yfinance history."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    if ticker in ATR_CACHE and ATR_CACHE[ticker].get('date') == today_str:
        return ATR_CACHE[ticker]['atr']
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="1mo")
        if df.empty or len(df) < 2:
            return ATR_CACHE.get(ticker, {}).get('atr', 0.0)
        highs, lows, closes = df['High'].values, df['Low'].values, df['Close'].values
        tr_list = []
        for i in range(1, len(closes)):
            tr_list.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            ))
        atr_20 = sum(tr_list[-20:]) / min(len(tr_list[-20:]), 20) if tr_list else 0.0
        ATR_CACHE[ticker] = {'date': today_str, 'atr': atr_20}
        return atr_20
    except Exception:
        if ticker in ATR_CACHE:
            return ATR_CACHE[ticker]['atr']
        return 0.0

def get_fx_rate(currency):
    rate_data = get_realtime_data(f"{currency}=X")
    return rate_data['price'] if rate_data['price'] > 0 else None

def get_usd_hkd_rate():
    return get_fx_rate("HKD") or 7.80

# ==================== 🌍 多市場時段 ====================
MARKETS = {
    "US": {"tz": "America/New_York", "open": (9, 30), "close": (16, 0)},
    "HK": {"tz": "Asia/Hong_Kong", "open": (9, 30), "close": (16, 0), "lunch": ((12, 0), (13, 0))},
    "CN": {"tz": "Asia/Shanghai", "open": (9, 30), "close": (15, 0), "lunch": ((11, 30), (13, 0))},
    "TW": {"tz": "Asia/Taipei", "open": (9, 0), "close": (13, 30)},
    "TWO": {"tz": "Asia/Taipei", "open": (9, 0), "close": (13, 30)},
}

def is_market_open(key):
    m = MARKETS.get(key)
    if not m: return False
    now = datetime.now(ZoneInfo(m["tz"]))
    if now.weekday() >= 5: return False
    minutes = now.hour * 60 + now.minute
    open_m = m["open"][0] * 60 + m["open"][1]
    close_m = m["close"][0] * 60 + m["close"][1]
    if "lunch" in m:
        l_start = m["lunch"][0][0] * 60 + m["lunch"][0][1]
        l_end = m["lunch"][1][0] * 60 + m["lunch"][1][1]
        if l_start <= minutes < l_end: return False
    return open_m <= minutes <= close_m

def check_us_market_active_hours():
    return is_market_open("US")

def check_any_market_active():
    """Return True if at least one tracked market (US/HK/CN/TW) is currently open."""
    return any(is_market_open(m) for m in ["US", "HK", "CN", "TW", "TWO"])

# ==================== 🎯 3. 核心數據聚合（內嵌流水明細） ====================
def calculate_portfolio_matrix():
    portfolio = load_portfolio()
    config = load_config()
    sec_cur = config.get("secondary_currency", "HKD")
    usd_hkd = get_fx_rate(sec_cur) or get_usd_hkd_rate()
    if sec_cur in ("EUR", "GBP") and usd_hkd:
        usd_hkd = 1.0 / usd_hkd  # Yahoo quotes EUR/GBP as 1 CUR = X USD (indirect)
    aggregated = {}
    
    # 掃描原始流水帳，一邊分類一邊保留它在原始陣列的「絕對位置 index」
    for idx, tx in enumerate(portfolio):
        ticker = tx['ticker'].upper()
        aggregated.setdefault(ticker, {'ticker': ticker, 'buys': [], 'sells': [], 'history_txs': []})
        
        # 把帶有原始索引的交易包裝起來
        tx_with_idx = tx.copy()
        tx_with_idx['original_index'] = idx
        aggregated[ticker]['history_txs'].append(tx_with_idx)
        
        if tx['type'] == 'BUY': aggregated[ticker]['buys'].append(tx)
        else: aggregated[ticker]['sells'].append(tx)
        
    processed_holdings, open_tickers_set, ticker_market = [], set(), {}
    total_market_value_usd = total_open_cost_usd = 0.0

    # Batch fetch all prices in ONE yfinance call (massive reduction in API requests)
    all_tickers = list(aggregated.keys())
    batch_prices = _batch_fetch_prices(all_tickers) if all_tickers else {}

    for ticker, data in aggregated.items():
        # 按日期排序各股票內部的明細
        data['history_txs'].sort(key=lambda x: x['date'])

        total_buy_shares = sum(float(x['shares']) for x in data['buys'])
        total_buy_spend = sum(float(x['shares']) * float(x['price']) + float(x['commission']) for x in data['buys'])
        total_sell_shares = sum(float(x['shares']) for x in data['sells'])
        total_sell_proceeds = sum(float(x['shares']) * float(x['price']) - float(x['commission']) for x in data['sells'])

        current_shares = max(0.0, total_buy_shares - total_sell_shares)
        avg_buy_price = (total_buy_spend / total_buy_shares) if total_buy_shares > 0 else 0.0
        current_open_cost = current_shares * avg_buy_price

        # Batch-fetched prices include TTL cache hits + fresh yfinance data
        bp = batch_prices.get(ticker, {})
        current_price = bp.get('price', 0.0) if bp.get('price', 0.0) > 0 else 0.0
        prev_close = bp.get('prev_close', 0.0)
        if current_price <= 0:
            # Last resort: individual cache/API fallback
            rt_data = get_realtime_data(ticker)
            current_price, prev_close = rt_data['price'], rt_data['prev_close']
        day_change = current_price - prev_close
        day_change_pct = (day_change / prev_close * 100) if prev_close > 0 else 0
        current_mv = current_shares * current_price
        pnl_usd = current_mv - current_open_cost if current_shares > 0 else 0.0
        roi = (pnl_usd / current_open_cost) * 100 if current_open_cost > 0 else 0.0
        
        # 本金收回追蹤
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
            ticker_market[ticker] = data['history_txs'][0].get('market') or 'US'
            status = "OPEN"
            atr_20 = fetch_atr_20(ticker)
            HIGHEST_PRICE_CACHE[ticker] = max(HIGHEST_PRICE_CACHE.get(ticker, current_price), current_price, avg_buy_price)
            stop_loss = HIGHEST_PRICE_CACHE[ticker] - (2.0 * atr_20)
            is_danger = (current_price <= stop_loss) and (atr_20 > 0)
        else:
            status, atr_20, stop_loss, is_danger = "CLOSED", 0, 0, False
            
        processed_holdings.append({
            'ticker': ticker, 'status': status, 'total_shares': f"{int(current_shares)}", 'avg_buy_price': f"{avg_buy_price:,.2f}", 'current_price': f"{current_price:,.2f}",
            'day_change': day_change, 'day_change_pct': day_change_pct, 'stop_loss': stop_loss, 'atr_20': atr_20, 'is_danger': is_danger, 'current_mv': f"{current_mv:,.2f}" if current_shares > 0 else '-', 'current_mv_raw': current_mv,
            'pnl_usd_str': f"{pnl_usd:+,.2f}" if current_shares > 0 else '-', 'pnl_hkd_str': f"{(pnl_usd * usd_hkd):+,.2f}" if current_shares > 0 else '-', 'roi_str': f"{roi:+.2f}%" if current_shares > 0 else '-',
            'market': data['history_txs'][0].get('market') or 'US',
            'praw': pnl_usd,
            'capital_recovered': capital_recovered_flag,
            'capital_recovered_str': f"{total_sell_proceeds:,.2f}" if total_sell_proceeds > 0 else '-',
            'shares_to_sell_to_recover': f"{shares_to_sell_to_recover:.1f}",
            'history_txs': data['history_txs']  # 🌟 該股票專屬的流水帳明細
        })
    # Sort by market: US first, then HK, CN, TW
    market_order = {"US": 0, "HK": 1, "CN": 2, "TW": 3, "TWO": 4}
    processed_holdings.sort(key=lambda s: (market_order.get(s.get('market', 'US'), 99), s['ticker']))
    open_tickers_sorted = sorted(open_tickers_set, key=lambda t: (market_order.get(ticker_market.get(t, "US"), 99), t))
    return processed_holdings, open_tickers_sorted, ticker_market, total_market_value_usd, total_open_cost_usd, usd_hkd, sec_cur

def build_watchlist_html(t):
    wl_data = load_watchlist()
    targets = wl_data.get("targets", {})
    categories = wl_data.get("categories", {})
    esc_js = lambda s: s.replace("'", "\\'")

    # Collect ALL watchlist tickers first, then batch-fetch prices once
    all_wl_tickers = []
    for tickers in categories.values():
        all_wl_tickers.extend(tickers)
    batch_prices = _batch_fetch_prices(all_wl_tickers) if all_wl_tickers else {}

    html = ""
    wl_del_label = t["wl_delete_cat"]
    wl_placeholder = t["wl_input_placeholder"]
    target_btn = t["target_set_btn"]
    for cat_name, tickers in categories.items():
        esc_cat = esc_js(cat_name)
        html += f"""
        <div class="wl-cat-group mb-4 border-b border-slate-800/60 pb-2 bg-slate-950/20 p-1.5 rounded transition-all" data-cat="{cat_name}" ondragover="handleDragOver(event); return false" ondragend="handleDragEnd(event)" ondrop="handleDrop(event); return false">
            <div class="flex justify-between items-center mb-2 group" draggable="true" ondragstart="handleDragStart(event)">
                <div class="flex items-center gap-1.5 w-2/3">
                    <span class="text-slate-600 group-hover:text-emerald-400 font-mono text-xs transition-colors cursor-grab active:cursor-grabbing" title="拖曳排序">☰</span>
                    <input type="text" name="cat_name" id="wl-cat-{cat_name}" value="{cat_name}" onblur="renameCategory('{esc_cat}', this.value)" class="bg-transparent text-xs font-black text-emerald-400 font-sans tracking-wide border-b border-transparent focus:outline-none focus:border-emerald-500 w-full">
                </div>
                <button onclick="deleteCategory('{esc_cat}')" class="text-[10px] text-slate-600 hover:text-rose-400 transition-colors">{wl_del_label}</button>
            </div>
            <div class="flex gap-1 mb-2">
                <input type="text" name="ticker" id="wl-input-{cat_name}" placeholder="{wl_placeholder}" class="wl-ticker-input bg-slate-900 border border-slate-800 text-[11px] p-1 rounded w-full uppercase focus:outline-none" onkeypress="if(event.key==='Enter') addTickerToCategory('{esc_cat}', this)">
                <button onclick="addTickerToCategory('{esc_cat}', this)" class="bg-slate-800 text-xs px-2 rounded hover:bg-slate-700 transition-colors">+</button>
            </div>
            <div class="space-y-1">
        """
        for tk in tickers:
            q = batch_prices.get(tk, get_realtime_data(tk))
            change = q['price'] - q['prev_close']
            pct = (change / q['prev_close'] * 100) if q['prev_close'] > 0 else 0
            color = "text-emerald-400" if change >= 0 else "text-rose-500"
            arrow = "▲ +" if change > 0 else ("▼ " if change < 0 else "■ ")
            target_price = targets.get(tk)
            if IS_PRO:
                if target_price:
                    target_html = '<span id="wl-target-' + tk + '"><button onclick="deleteTarget(\'' + tk + '\')" class="text-[9px] text-amber-400 hover:text-rose-400 font-mono" title="刪除目標價">🎯$' + f'{target_price:.2f}' + ' ✕</button></span>'
                else:
                    target_html = '<span id="wl-target-' + tk + '"><button onclick="setTarget(\'' + tk + '\')" class="text-[9px] text-slate-600 hover:text-amber-400 font-mono" title="' + target_btn + '">' + target_btn + '</button></span>'
            else:
                target_html = ''
            html += f"""
            <div class="flex justify-between items-center p-1.5 rounded bg-slate-900/40 hover:bg-slate-900/90 transition-colors text-xs">
                <div class="flex items-center gap-1">
                    <span class="font-bold font-mono text-slate-300">${tk}</span>
                    <button onclick="deleteTickerFromCategory('{esc_cat}', '{tk}')" class="text-slate-600 hover:text-rose-500">×</button>
                </div>
                <div class="flex items-center gap-2">
                    {target_html}
                    <div class="text-right font-mono">
                        <div id="wl-price-{tk}" class="text-cyan-400 font-bold">${q['price']:.2f}</div>
                        <div id="wl-pct-{tk}" class="text-[10px] {color}">{arrow}{pct:.2f}%</div>
                    </div>
                </div>
            </div>
            """
        html += "</div></div>"
    return html

# ==================== 🎯 AUTH MIDDLEWARE (CLOUD MODE) ====================
PUBLIC_PATHS = {"/", "/health", "/webhook", "/pulse_logo.png", "/pulse.css"}

@app.before_request
def cloud_auth_middleware():
    """JWT auth middleware — active only in CLOUD_MODE."""
    if not CLOUD_MODE:
        return  # no-op for selfhosted

    g.user_id = None
    g.tier = "free"

    if request.path in PUBLIC_PATHS or request.path.startswith("/static/"):
        return

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.cookies.get("sb-access-token")

    if not token:
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect("/")

    try:
        user_resp = supabase.auth.get_user(token)
        g.user_id = user_resp.user.id
    except Exception as e:
        err_msg = str(e).lower()
        if "expired" in err_msg:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Token expired"}), 401
            return redirect("/")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Invalid token"}), 401
        return redirect("/")

    try:
        profile = supabase_admin.table("profiles").select("tier").eq("user_id", g.user_id).single().execute()
        if profile.data:
            g.tier = profile.data.get("tier", "free")
    except Exception:
        g.tier = "free"


def get_is_pro():
    """Return True if user has Pro features.
    Selfhosted: checks IS_PRO module flag.
    Cloud: checks g.tier from Supabase profiles."""
    if CLOUD_MODE:
        return g.get("tier", "free") == "pro"
    return IS_PRO


# ==================== 🎯 LANDING PAGE (CLOUD MODE ONLY) ====================
LANDING_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <title>Pulse — Live Data · Real Intuition</title>
    <link rel="icon" href="/pulse_logo.png" type="image/png">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            background: linear-gradient(135deg, #020617 0%, #0f172a 50%, #1e1b4b 100%);
            color: #e2e8f0; font-family: system-ui, -apple-system, sans-serif;
            min-height: 100vh; display: flex; flex-direction: column; align-items: center;
        }
        .container { max-width: 480px; width: 100%; padding: 40px 20px; }
        .logo { text-align: center; margin-bottom: 40px; }
        .logo h1 { font-size: 3rem; font-weight: 900; letter-spacing: -0.03em;
            background: linear-gradient(135deg, #34d399, #22d3ee);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text; }
        .logo p { color: #94a3b8; font-size: 0.9rem; margin-top: 8px; }
        .card {
            background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px; padding: 32px; backdrop-filter: blur(12px);
        }
        .card h2 { font-size: 1.2rem; font-weight: 700; margin-bottom: 24px; color: #e2e8f0; }
        .card label { display: block; font-size: 0.75rem; font-weight: 600;
            color: #94a3b8; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
        .card input {
            width: 100%; padding: 12px 16px; margin-bottom: 16px;
            background: #1e293b; border: 1px solid #334155; border-radius: 8px;
            color: #e2e8f0; font-size: 0.95rem; outline: none; transition: border 0.2s;
        }
        .card input:focus { border-color: #22d3ee; }
        .btn {
            width: 100%; padding: 12px; border-radius: 8px; font-weight: 700;
            font-size: 0.95rem; cursor: pointer; transition: all 0.2s; border: none;
        }
        .btn-primary { background: linear-gradient(135deg, #22d3ee, #34d399);
            color: #0f172a; margin-bottom: 12px; }
        .btn-primary:hover { opacity: 0.9; transform: translateY(-1px); }
        .btn-google {
            background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
            display: flex; align-items: center; justify-content: center; gap: 8px;
        }
        .btn-google:hover { background: #334155; }
        .divider {
            display: flex; align-items: center; gap: 12px;
            color: #64748b; font-size: 0.75rem; margin: 20px 0;
        }
        .divider::before, .divider::after {
            content: ""; flex: 1; height: 1px; background: #334155;
        }
        .toggle { text-align: center; font-size: 0.85rem; color: #94a3b8; margin-top: 16px; }
        .toggle a { color: #22d3ee; cursor: pointer; text-decoration: none; font-weight: 600; }
        .toggle a:hover { text-decoration: underline; }
        .error { background: rgba(239,68,68,0.15); color: #fca5a5; padding: 10px 14px;
            border-radius: 8px; font-size: 0.8rem; margin-bottom: 16px; display: none; }
        .error.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>Pulse</h1>
            <p>Live Data &middot; Real Intuition</p>
        </div>
        <div class="card" id="auth-card">
            <div class="error" id="auth-error"></div>

            <div id="signin-form">
                <h2>Sign In</h2>
                <label for="signin-email">Email</label>
                <input type="email" id="signin-email" placeholder="you@example.com">
                <label for="signin-password">Password</label>
                <input type="password" id="signin-password" placeholder="••••••••">
                <button class="btn btn-primary" onclick="signIn()">Sign In</button>
                <button class="btn btn-google" onclick="signInWithGoogle()">
                    <svg width="18" height="18" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
                    Continue with Google
                </button>
                <div class="toggle">Don't have an account? <a onclick="toggleAuthMode('signup')">Sign Up</a></div>
            </div>

            <div id="signup-form" style="display:none;">
                <h2>Create Account</h2>
                <label for="signup-email">Email</label>
                <input type="email" id="signup-email" placeholder="you@example.com">
                <label for="signup-password">Password</label>
                <input type="password" id="signup-password" placeholder="•••••••• (min 8 characters)">
                <button class="btn btn-primary" onclick="signUp()">Create Account</button>
                <div class="toggle">Already have an account? <a onclick="toggleAuthMode('signin')">Sign In</a></div>
            </div>
        </div>
    </div>

    <script>
        const SUPABASE_URL = "{{ supabase_url }}";
        const SUPABASE_KEY = "{{ supabase_key }}";
        const sb = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

        function showError(msg) {
            const el = document.getElementById('auth-error');
            el.textContent = msg;
            el.classList.add('show');
            setTimeout(function(){ el.classList.remove('show'); }, 5000);
        }

        function setCookie(name, value, days) {
            var expires = '';
            if (days) {
                var d = new Date();
                d.setTime(d.getTime() + (days * 86400000));
                expires = '; expires=' + d.toUTCString();
            }
            document.cookie = name + '=' + (value || '') + expires + '; path=/; SameSite=Lax';
        }

        function toggleAuthMode(mode) {
            document.getElementById('signin-form').style.display = (mode === 'signin') ? '' : 'none';
            document.getElementById('signup-form').style.display = (mode === 'signup') ? '' : 'none';
            document.getElementById('auth-error').classList.remove('show');
        }

        async function signIn() {
            const email = document.getElementById('signin-email').value.trim();
            const password = document.getElementById('signin-password').value;
            if (!email || !password) { showError('Please enter email and password.'); return; }
            try {
                const { data, error } = await sb.auth.signInWithPassword({ email: email, password: password });
                if (error) { showError(error.message); return; }
                if (data.session && data.session.access_token) {
                    setCookie('sb-access-token', data.session.access_token, 7);
                    window.location.href = '/dashboard';
                }
            } catch(e) { showError('Sign in failed. Please try again.'); }
        }

        async function signUp() {
            const email = document.getElementById('signup-email').value.trim();
            const password = document.getElementById('signup-password').value;
            if (!email || !password) { showError('Please enter email and password.'); return; }
            if (password.length < 8) { showError('Password must be at least 8 characters.'); return; }
            try {
                const { data, error } = await sb.auth.signUp({ email: email, password: password });
                if (error) { showError(error.message); return; }
                if (data.session && data.session.access_token) {
                    setCookie('sb-access-token', data.session.access_token, 7);
                    window.location.href = '/dashboard';
                } else {
                    showError('Please check your email for a confirmation link.');
                }
            } catch(e) { showError('Sign up failed. Please try again.'); }
        }

        async function signInWithGoogle() {
            try {
                const { data, error } = await sb.auth.signInWithOAuth({
                    provider: 'google',
                    options: { redirectTo: window.location.origin + '/dashboard' }
                });
                if (error) { showError(error.message); }
            } catch(e) { showError('Google sign in failed.'); }
        }

        (async function() {
            const { data: { session } } = await sb.auth.getSession();
            if (session && session.access_token) {
                setCookie('sb-access-token', session.access_token, 7);
                window.location.href = '/dashboard';
            }
        })();
    </script>
</body>
</html>"""


def render_landing_page():
    """Render the cloud landing page with Supabase auth UI."""
    return render_template_string(
        LANDING_PAGE_HTML,
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY
    )


# ==================== 🎯 4. 路由控制 ====================

def _render_dashboard():
    """Render the Pulse dashboard — shared between selfhosted index() and cloud /dashboard."""
    config = load_config()
    if "secondary_currency" not in config:
        config["secondary_currency"] = "HKD"
    t = get_translations(config.get("language", "zh_tw"))
    stocks, open_tickers, ticker_market, total_mv_usd, total_open_cost, usd_hkd, sec_cur = calculate_portfolio_matrix()
    active_markets = set(ticker_market.values())
    watchlist_html = build_watchlist_html(t)
    wl_data = load_watchlist()
    targets_json = wl_data.get("targets", {})
    total_pnl_usd = total_mv_usd - total_open_cost
    total_roi = (total_pnl_usd / total_open_cost) * 100 if total_open_cost > 0 else 0.0
    total_roi_str = f"{total_roi:+.2f}%"
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    is_active = check_us_market_active_hours()
    markets_status = {k: is_market_open(k) for k in MARKETS}
    is_pro = get_is_pro()

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en" class="dark">
    <head>
        <meta charset="UTF-8">
        <title>Pulse — Live Data · Real Intuition</title>
        <link rel="icon" href="/pulse_logo.png" type="image/png">
        {% if CLOUD_MODE %}
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {
                darkMode: 'class',
                theme: { extend: {} }
            };
        </script>
        {% else %}
        <link rel="stylesheet" href="/pulse.css">
        {% endif %}
        <style>
            @keyframes pulse-alert { 0%, 100% { background-color: rgba(159, 18, 57, 0.2); } 50% { background-color: rgba(225, 29, 72, 0.5); } }
            .danger-row { animation: pulse-alert 2s infinite; border-left: 4px solid #f43f5e; }
            .watchlist-sidebar { position: fixed; top: 0; left: 0; width: 280px; height: 100vh; background: #0f172a; border-right: 1px solid rgba(255, 255, 255, 0.1); z-index: 1000; padding: 20px 15px; transform: translateX(-265px); transition: transform 0.3s; }
            .watchlist-sidebar:hover { transform: translateX(0); }
            .wl-cat-group.dragging { opacity: 0.4; }
            .wl-cat-group.drag-over { border-top: 2px solid #34d399; }
            .modal-bg { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(2, 6, 23, 0.75); backdrop-filter: blur(4px); z-index: 2000; align-items: center; justify-content: center; }
            .modal-active { display: flex; }
        </style>
    </head>
    <body class="bg-slate-950 text-slate-100 min-h-screen font-sans">

        <!-- Watchlist Sidebar -->
        <div class="watchlist-sidebar">
            <div class="flex justify-between items-center border-b border-slate-800 pb-2 mb-3">
                <span class="text-xs font-black tracking-widest text-slate-200">{{ t.watchlist_title }}</span>
                <button onclick="createNewCategory()" class="text-[10px] bg-slate-800 px-2 py-0.5 rounded hover:bg-slate-700 text-emerald-400 font-bold">{{ t.wl_add_cat }}</button>
            </div>
            <div id="watchlist-master-box" class="overflow-y-auto space-y-3" style="height: calc(100vh - 80px);">
                {{ watchlist_html|safe }}
            </div>
        </div>

        <!-- ⚙️ 系統設定 -->
        <div id="settingsModal" class="modal-bg">
            <div class="bg-slate-900 border border-slate-800 p-8 rounded-2xl shadow-2xl w-full max-w-2xl border-l-4 border-l-cyan-500 m-4">
                <div class="flex justify-between items-center border-b border-slate-800 pb-4 mb-6">
                    <h3 class="text-lg font-black text-cyan-400 tracking-wide">{{ t.settings_title }} <span class="text-slate-600 text-xs font-mono ml-2">{{ version }}</span></h3>
                    <button onclick="toggleSettingsModal()" class="text-slate-400 hover:text-slate-200 font-bold text-sm">{{ t.settings_close }}</button>
                </div>

                <!-- Tab buttons -->
                <div class="flex gap-1 mb-6">
                    <button type="button" id="tab-btn-general" onclick="switchSettingsTab('general')" class="px-4 py-1.5 text-xs font-bold rounded bg-cyan-600 text-slate-900">{{ t.settings_tab_general }}</button>
                    <button type="button" id="tab-btn-ai" onclick="switchSettingsTab('ai')" class="px-4 py-1.5 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700">{{ t.settings_tab_ai }}</button>
                </div>

                <form action="/api/config/save" method="POST" class="space-y-4 text-xs">

                    <!-- GENERAL TAB -->
                    <div id="settings-tab-general" class="space-y-4">
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-language">{{ t.settings_language }}</label>
                            <select name="language" id="settings-language" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-bold">
                                <option value="zh_tw" {% if config.language == 'zh_tw' %}selected{% endif %}>繁體中文</option>
                                <option value="zh_cn" {% if config.language == 'zh_cn' %}selected{% endif %}>簡體中文</option>
                                <option value="en" {% if config.language == 'en' %}selected{% endif %}>English</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-cash-balance">{{ t.settings_cash_balance }}</label>
                            <input type="number" step="0.01" name="cash_balance" id="settings-cash-balance" value="{{ config.cash_balance }}" min="0" class="w-40 bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-mono">
                        </div>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-currency">{{ t.settings_currency }}</label>
                            <select name="secondary_currency" id="settings-currency" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-bold">
                                <option value="HKD" {% if config.secondary_currency == 'HKD' %}selected{% endif %}>HKD 港幣</option>
                                <option value="CNY" {% if config.secondary_currency == 'CNY' %}selected{% endif %}>CNY 人民幣</option>
                                <option value="TWD" {% if config.secondary_currency == 'TWD' %}selected{% endif %}>TWD 新台幣</option>
                                <option value="JPY" {% if config.secondary_currency == 'JPY' %}selected{% endif %}>JPY 日圓</option>
                                <option value="EUR" {% if config.secondary_currency == 'EUR' %}selected{% endif %}>EUR 歐元</option>
                                <option value="GBP" {% if config.secondary_currency == 'GBP' %}selected{% endif %}>GBP 英鎊</option>
                            </select>
                        </div>
                    </div>

                    <!-- AI TAB -->
                    <div id="settings-tab-ai" class="hidden space-y-4">
                        {% if is_pro %}
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="block text-slate-400 font-bold mb-1" for="settings-ai-provider">{{ t.settings_ai_provider }}</label>
                                <select name="ai_provider" id="settings-ai-provider" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-bold">
                                    <option value="gemini" {% if config.ai_provider == 'gemini' %}selected{% endif %}>Google Gemini</option>
                                    <option value="openai" {% if config.ai_provider == 'openai' %}selected{% endif %}>OpenAI API compatible</option>
                                    <option value="deepseek" {% if config.ai_provider == 'deepseek' %}selected{% endif %}>DeepSeek (Official)</option>
                                    <option disabled class="text-slate-600">── Local Inference ──</option>
                                    <option value="ollama" {% if config.ai_provider == 'ollama' %}selected{% endif %}>🖥️ Ollama (Local)</option>
                                    <option value="vllm" {% if config.ai_provider == 'vllm' %}selected{% endif %}>🖥️ vLLM (Local)</option>
                                    <option value="lmstudio" {% if config.ai_provider == 'lmstudio' %}selected{% endif %}>🖥️ LM Studio (Local)</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-slate-400 font-bold mb-1" for="settings-model">{{ t.settings_model }}</label>
                                <input type="text" name="ai_model" id="settings-model" value="{{ config.ai_model }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-mono">
                            </div>
                        </div>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-api-url">{{ t.settings_api_url }}</label>
                            <input type="text" name="custom_api_url" id="settings-api-url" value="{{ config.custom_api_url }}" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-mono">
                        </div>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-api-key">{{ t.settings_api_key }}</label>
                            <input type="password" name="api_key" id="settings-api-key" value="{{ config.api_key }}" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-mono">
                        </div>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-timeout">{{ t.settings_timeout }}</label>
                            <input type="number" name="ai_timeout" id="settings-timeout" value="{{ config.ai_timeout }}" min="10" max="300" class="w-24 bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-mono text-center">
                            <span class="text-slate-600 text-[10px] ml-2">{{ t.settings_timeout_hint }}</span>
                        </div>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1">{{ t.settings_prompt_mode }}</label>
                            <div class="flex gap-4 mb-3">
                                <label class="flex items-center gap-1.5 text-slate-300 cursor-pointer">
                                    <input type="radio" name="prompt_mode" value="style" {% if config.prompt_mode != 'custom' %}checked{% endif %} class="accent-cyan-500">
                                    <span class="text-xs">{{ t.prompt_mode_style }}</span>
                                </label>
                                <label class="flex items-center gap-1.5 text-slate-300 cursor-pointer">
                                    <input type="radio" name="prompt_mode" value="custom" {% if config.prompt_mode == 'custom' %}checked{% endif %} class="accent-cyan-500">
                                    <span class="text-xs">{{ t.prompt_mode_custom }}</span>
                                </label>
                            </div>
                        </div>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-prompt-level">{{ t.settings_prompt_level }}</label>
                            <select name="prompt_level" id="settings-prompt-level" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-bold">
                                <option value="strict" {% if config.prompt_level == 'strict' %}selected{% endif %}>{{ t.prompt_level_strict }}</option>
                                <option value="balanced" {% if config.prompt_level == 'balanced' %}selected{% endif %}>{{ t.prompt_level_balanced }}</option>
                                <option value="relaxed" {% if config.prompt_level == 'relaxed' %}selected{% endif %}>{{ t.prompt_level_relaxed }}</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-custom-prompt">{{ t.settings_custom_prompt }}</label>
                            <textarea name="custom_prompt" id="settings-custom-prompt" rows="6" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-300 font-mono text-[11px]" placeholder="留空則使用預設 Prompt...">{{ config.custom_prompt }}</textarea>
                            <p class="text-slate-600 text-[10px] mt-1">{{ t.settings_prompt_hint }}</p>
                        </div>
                        {% else %}
                        <p class="text-slate-500 text-sm">AI 模型設定僅在 Pro 版本可用。</p>
                        {% endif %}
                    </div>

                    <div class="border-t border-slate-800 pt-4 flex justify-end">
                        <button type="submit" class="px-6 py-2 bg-cyan-600 hover:bg-cyan-500 font-black rounded text-slate-900 tracking-wider">{{ t.settings_save }}</button>
                    </div>
                </form>

                <!-- 📋 更新日誌 -->
                <div class="border-t border-slate-800 mt-4 pt-4">
                    <p class="text-slate-500 text-[10px] font-bold uppercase mb-2">{{ t.changelog_title }}</p>
                    <div class="space-y-1 max-h-32 overflow-y-auto">
                        {% for ver, msg in changelog %}
                        <div class="text-[10px]"><span class="text-cyan-400 font-mono">{{ ver }}</span> <span class="text-slate-500">{{ msg }}</span></div>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>

        <div class="container mx-auto px-6 py-8 pl-12">
            <!-- 頂部 Bar -->
            <div class="flex justify-between items-center border-b border-slate-800 pb-6 mb-8">
                <div class="flex items-center gap-4">
                    <img src="/pulse_logo.png" alt="Pulse" class="w-10 h-10 rounded-lg">
                    <div>
                        <h1 class="text-3xl font-black tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">{{ t.title }}</h1>
                        <p class="text-slate-400 text-sm mt-1">{{ t.subtitle }}
                            <span class="ml-2 text-[10px] font-mono space-x-2">
                                <span>US<span class="ml-0.5 inline-block w-1.5 h-1.5 rounded-full {% if markets_status.US %}bg-emerald-400{% else %}bg-rose-500{% endif %}"></span></span>
                                <span>HK<span class="ml-0.5 inline-block w-1.5 h-1.5 rounded-full {% if markets_status.HK %}bg-emerald-400{% else %}bg-rose-500{% endif %}"></span></span>
                                <span>CN<span class="ml-0.5 inline-block w-1.5 h-1.5 rounded-full {% if markets_status.CN %}bg-emerald-400{% else %}bg-rose-500{% endif %}"></span></span>
                                <span>TW<span class="ml-0.5 inline-block w-1.5 h-1.5 rounded-full {% if markets_status.TW %}bg-emerald-400{% else %}bg-rose-500{% endif %}"></span></span>
                                <span>TWO<span class="ml-0.5 inline-block w-1.5 h-1.5 rounded-full {% if markets_status.TWO %}bg-emerald-400{% else %}bg-rose-500{% endif %}"></span></span>
                            </span>
                        </p>
                    </div>
                </div>
                <div class="flex items-center gap-3">
                    <div class="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 flex items-center gap-2 text-xs">
                        <span class="text-slate-400 font-bold">{{ t.auto_refresh_label }}</span>
                        <input type="number" id="refreshIntervalInput" name="refresh_interval" value="{{ config.refresh_interval }}" min="10" title="{{ t.refresh_tooltip }}" class="w-12 bg-slate-950 text-center text-emerald-400 font-mono rounded font-bold" onchange="updateLiveInterval(this.value)">
                        <span id="refreshIndicator" class="h-2 w-2 rounded-full bg-emerald-500"></span>
                    </div>
                    {% if is_pro %}<button onclick="runAiAudit()" class="px-5 py-2.5 bg-gradient-to-r from-cyan-500 to-emerald-500 font-bold rounded-lg text-xs tracking-widest">{{ t.ai_report_btn }}</button>{% endif %}
                    <button onclick="toggleSettingsModal()" class="p-2.5 bg-slate-900 border border-slate-800 rounded-lg text-slate-300">⚙️</button>
                    {% if CLOUD_MODE %}
                    <button onclick="logout()" class="px-3 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-400 hover:text-rose-400 hover:border-rose-700 transition-colors font-bold">Logout</button>
                    {% endif %}
                </div>
            </div>

            <!-- 三大數據卡片 -->
            <div class="grid {% if is_pro %}grid-cols-3{% else %}grid-cols-2{% endif %} gap-6 mb-8">
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl">
                    <p class="text-slate-400 text-xs font-bold uppercase">{{ t.total_mv_label }} (USD / {{ sec_cur }})</p>
                    <p id="top-total-mv-usd" class="text-3xl font-black text-cyan-400 mt-2">${{ "{:,.2f}".format(total_mv_usd) }}</p>
                    <p id="top-total-mv-hkd" class="text-xs font-mono text-slate-500 mt-1">≈ {{ sec_cur }}${{ "{:,.2f}".format(total_mv_usd * usd_hkd) }}</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl">
                    <p class="text-slate-400 text-xs font-bold uppercase">{{ t.total_pnl_label }} (USD / {{ sec_cur }})</p>
                    <p id="top-total-pnl-usd" class="text-3xl font-black mt-2 {% if total_pnl_usd >= 0 %}text-emerald-400{% else %}text-rose-500{% endif %}">${{ "{:+,.2f}".format(total_pnl_usd) }} <span class="text-xl font-medium">({{ total_roi_str }})</span></p>
                    <p id="top-total-pnl-hkd" class="text-xs font-mono mt-1 {% if total_pnl_usd >= 0 %}text-emerald-500/80{% else %}text-rose-500/80{% endif %}">≈ {{ sec_cur }}${{ "{:+,.2f}".format(total_pnl_usd * usd_hkd) }}</p>
                </div>
{% if is_pro %}
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl">
                    <p class="text-slate-400 text-xs font-bold uppercase mb-2">{{ t.target_alert_title }}</p>
                    <div id="target-alerts" class="overflow-y-auto space-y-1 text-xs" style="max-height: 80px;">
                        <p class="text-slate-600 italic">—</p>
                    </div>
                </div>
{% endif %}
            </div>

            {% if is_pro %}
            <!-- Pro: 市場分佈 + 現金比率 -->
            <div class="grid grid-cols-2 gap-6 mb-8">
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl">
                    <p class="text-slate-400 text-xs font-bold uppercase mb-3">{{ t.card_market_dist }}</p>
                    {% set ns = namespace(markets={}) %}
                    {% for stock in stocks %}
                        {% if stock.status == 'OPEN' and stock.current_mv_raw > 0 %}
                            {% set _ = ns.markets.update({stock.market: ns.markets.get(stock.market, 0) + stock.current_mv_raw}) %}
                        {% endif %}
                    {% endfor %}
                    {% for mkt, mv in ns.markets.items()|sort(attribute='1', reverse=True) %}
                    <div class="flex justify-between items-center mb-1.5 text-sm">
                        <span class="text-slate-300 font-bold">{{ mkt }}</span>
                        <span class="text-slate-400 font-mono">${{ "{:,.0f}".format(mv) }}</span>
                        <span class="text-cyan-400 font-mono text-xs">{{ "%.1f"|format(mv / total_mv_usd_raw * 100) if total_mv_usd_raw > 0 else 0 }}%</span>
                    </div>
                    <div class="w-full bg-slate-800 rounded-full h-1.5 mb-2">
                        <div class="bg-cyan-500 h-1.5 rounded-full" style="width: {{ "%.0f"|format(mv / total_mv_usd_raw * 100) if total_mv_usd_raw > 0 else 0 }}%"></div>
                    </div>
                    {% endfor %}
                </div>
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl flex flex-col justify-center items-center">
                    <p class="text-slate-400 text-xs font-bold uppercase mb-2">{{ t.card_cash_ratio }}</p>
                    <p class="text-4xl font-black text-emerald-400">{{ "%.1f"|format(cash_balance / (total_mv_usd_raw + cash_balance) * 100) if (total_mv_usd_raw + cash_balance) > 0 else 0 }}%</p>
                    <p class="text-slate-500 text-xs mt-1">${{ "{:,.0f}".format(cash_balance) }} / ${{ "{:,.0f}".format(total_mv_usd_raw + cash_balance) }}</p>
                </div>
            </div>
            {% endif %}

            <!-- 交易輸入表單 -->
            <div class="grid grid-cols-2 gap-6 mb-8">
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl border-l-4 border-l-emerald-500">
                    <h3 class="text-md font-black text-emerald-400 mb-4">{{ t.buy_title }}</h3>
                    <form id="buy-form" class="grid grid-cols-2 gap-3 text-xs" onsubmit="submitTrade(event, 'buy')">
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="buy-ticker">{{ t.ticker_label }}</label><input type="text" name="ticker" id="buy-ticker" placeholder="{{ t.buy_ticker_ph }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2 font-mono uppercase"></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="buy-market">{{ t.market_label }}</label><select name="market" id="buy-market" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-bold"><option value="US">US</option><option value="HK">HK</option><option value="CN">CN</option><option value="TW">TW</option><option value="TWO">TWO</option></select></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="buy-date">{{ t.date_label }}</label><input type="date" name="buy_date" id="buy-date" value="{{ today_date }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="buy-price">{{ t.price_label }}</label><input type="number" step="0.0001" name="buy_price" id="buy-price" placeholder="{{ t.buy_price_ph }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="buy-shares">{{ t.shares_label }}</label><input type="number" name="buy_shares" id="buy-shares" placeholder="{{ t.buy_shares_ph }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="buy-commission">{{ t.commission_label }}</label><input type="number" step="0.01" name="buy_commission" id="buy-commission" value="0.00" class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
                        <button type="submit" class="col-span-2 py-2 bg-emerald-600 hover:bg-emerald-700 font-bold rounded">{{ t.buy_confirm }}</button>
                        <div id="buy-estimated-cost" class="col-span-2 text-center text-xs font-mono text-emerald-300 mt-1">{{ t.buy_est_cost }}: $0.00</div>
                    </form>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl border-l-4 border-l-rose-500">
                    <h3 class="text-md font-black text-rose-400 mb-4">{{ t.sell_title }}</h3>
                    <form id="sell-form" class="grid grid-cols-2 gap-3 text-xs" onsubmit="submitTrade(event, 'sell')">
                        <div class="col-span-2"><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="sell-ticker">{{ t.sell_ticker_label }}</label><select name="ticker" id="sell-ticker" required class="w-full bg-slate-950 border border-slate-800 rounded p-2 font-bold"><option value="">{{ t.sell_select_ticker }}</option>{% set ns = namespace(current_market='') %}{% for tk in open_tickers %}{% set m = ticker_market.get(tk, 'US') %}{% if m != ns.current_market %}{% if ns.current_market != '' %}</optgroup>{% endif %}<optgroup label="{{ m }}">{% set ns.current_market = m %}{% endif %}<option value="{{ tk }}">{{ tk }}</option>{% endfor %}</optgroup></select></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="sell-date">{{ t.sell_date_label }}</label><input type="date" name="sell_date" id="sell-date" value="{{ today_date }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="sell-price">{{ t.sell_price_label }}</label><input type="number" step="0.0001" name="sell_price" id="sell-price" placeholder="{{ t.sell_price_ph }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="sell-shares">{{ t.sell_shares_label }}</label><input type="number" name="sell_shares" id="sell-shares" placeholder="{{ t.sell_shares_ph }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="sell-commission">{{ t.sell_commission_label }}</label><input type="number" step="0.01" name="sell_commission" id="sell-commission" value="0.00" class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
                        <button type="submit" class="col-span-2 py-2 bg-rose-600 hover:bg-rose-700 font-bold rounded">{{ t.sell_confirm }}</button>
                        <div id="sell-estimated-cost" class="col-span-2 text-center text-xs font-mono text-rose-300 mt-1">{{ t.sell_est_income }}: $0.00</div>
                    </form>
                </div>
            </div>

            <!-- 🌍 市場標籤 -->
            <div id="market-tabs" class="flex gap-1 mb-3">
                <button onclick="filterMarket('all')" class="market-tab px-3 py-1 text-xs font-bold rounded bg-cyan-600 text-slate-900" data-market="all">{{ t.tab_all }}</button>
                {% if "US" in active_markets %}<button onclick="filterMarket('US')" class="market-tab px-3 py-1 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700" data-market="US">US</button>{% endif %}
                {% if "HK" in active_markets %}<button onclick="filterMarket('HK')" class="market-tab px-3 py-1 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700" data-market="HK">HK</button>{% endif %}
                {% if "CN" in active_markets %}<button onclick="filterMarket('CN')" class="market-tab px-3 py-1 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700" data-market="CN">CN</button>{% endif %}
                {% if "TW" in active_markets %}<button onclick="filterMarket('TW')" class="market-tab px-3 py-1 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700" data-market="TW">TW</button>{% endif %}
                {% if "TWO" in active_markets %}<button onclick="filterMarket('TWO')" class="market-tab px-3 py-1 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700" data-market="TWO">TWO</button>{% endif %}
            </div>

            <!-- 持倉與明細整合表格 -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl mb-8">
                <table class="w-full text-left border-collapse text-xs">
                    <thead>
                        <tr class="bg-slate-950/60 text-slate-400 border-b border-slate-800 uppercase tracking-wider">
                            <th class="px-6 py-4 w-12 text-center">{{ t.table_expand }}</th>
                            <th class="px-4 py-4">{{ t.table_ticker }}</th>
                            <th class="px-4 py-4">{{ t.table_shares }}</th>
                            <th class="px-4 py-4">{{ t.table_avg_price }}</th>
                            <th class="px-4 py-4">{{ t.table_current_price }}</th>
                            <th class="px-4 py-4">{{ t.table_stop_loss }}</th>
                            <th class="px-4 py-4">{{ t.table_mv }}</th>
                            <th class="px-6 py-4 text-right">{{ t.table_pnl }}</th>
                            {% if is_pro %}<th class="px-4 py-4 text-right">{{ t.table_weight }}</th>{% endif %}
                        </tr>
                    </thead>
                    
                    {% for stock in stocks %}
                    <!-- 🌟 股票核心資料列 -->
                    <tbody class="border-b border-slate-800/80" data-market="{{ stock.market }}">
                        <tr class="hover:bg-slate-800/30 cursor-pointer transition-colors {% if stock.is_danger %}danger-row{% endif %}" onclick="toggleHistory('details-{{ stock.ticker }}')">
                            <td class="px-6 py-4 text-center text-cyan-400 font-bold select-none text-sm">▶</td>
                            <td class="px-4 py-4 font-black text-slate-100 text-sm">${{ stock.ticker }}
                                <span id="badge-recovered-{{ stock.ticker }}" class="text-[10px] px-1.5 py-0.5 font-black rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 ml-1 {% if not stock.capital_recovered %}hidden{% endif %}">{{ t.capital_recovered_badge }}</span>
                            </td>
                            <td class="px-4 py-4 font-mono text-slate-300">{{ stock.total_shares }}</td>
                            <td class="px-4 py-4 font-mono text-slate-300">${{ stock.avg_buy_price }}</td>
                            <td id="price-{{ stock.ticker }}" class="px-4 py-4 font-mono">
                                <div class="font-bold text-cyan-400">${{ stock.current_price }}</div>
                                <div class="{% if stock.day_change >= 0 %}text-emerald-400{% else %}text-rose-500{% endif %}">
                                    {{ "▲ +" if stock.day_change >= 0 else "▼ " }}{{ "%.2f"|format(stock.day_change_pct) }}%
                                </div>
                            </td>
                            <td class="px-4 py-4 font-mono text-slate-400">
                                {% if stock.status == 'OPEN' %} <div class="text-rose-400 font-bold">${{ "%.2f"|format(stock.stop_loss) }}</div> {% else %} - {% endif %}
                            </td>
                            <td id="mv-{{ stock.ticker }}" class="px-4 py-4 font-mono font-bold">${{ stock.current_mv }}</td>
                            <td id="pnl-{{ stock.ticker }}" class="px-6 py-4 text-right font-mono font-bold {% if stock.praw >= 0 %}text-emerald-400{% else %}text-rose-500{% endif %}">
                                {{ stock.pnl_usd_str }} ({{ stock.roi_str }})
                            </td>
                            {% if is_pro %}
                            <td class="px-4 py-4 text-right font-mono text-slate-400 text-sm">
                                {{ "%.1f"|format(stock.current_mv_raw / total_mv_usd_raw * 100) if total_mv_usd_raw > 0 and stock.current_mv_raw > 0 else "-" }}%
                            </td>
                            {% endif %}
                        </tr>
                        
                        <!-- 💡 本金收回提示 -->
                        <tr id="recover-hint-{{ stock.ticker }}" class="{% if stock.capital_recovered or stock.status == 'CLOSED' %}hidden{% endif %}">
                            {% if is_pro %}<td colspan="9" class="px-4 py-1 text-[11px] text-amber-500/80 font-medium tracking-wide">{% else %}<td colspan="8" class="px-4 py-1 text-[11px] text-amber-500/80 font-medium tracking-wide">{% endif %}
                                {{ t.capital_recover_hint }} <span id="recover-shares-{{ stock.ticker }}" class="font-bold underline">{{ stock.shares_to_sell_to_recover }}</span> {{ t.capital_recover_hint_end }}
                            </td>
                        </tr>
                        <!-- 🌟 內嵌式歷史交易明細 (該股票專屬) -->
                        <tr id="details-{{ stock.ticker }}" class="hidden bg-slate-950/40">
                            {% if is_pro %}<td colspan="9" class="px-8 py-4">{% else %}<td colspan="8" class="px-8 py-4">{% endif %}
                                <div class="border-l-2 border-slate-700 pl-4 py-2">
                                    <div class="text-slate-400 font-bold mb-2 uppercase font-mono tracking-wider text-[11px]">{{ t.history_title }} — ${{ stock.ticker }} | {{ t.capital_recovered_label }}: ${{ stock.capital_recovered_str }}</div>
                                    <table class="w-full text-left font-mono text-[11px] text-slate-400">
                                        <thead>
                                            <tr class="text-slate-500 border-b border-slate-800">
                                                <th class="py-1">{{ t.history_type }}</th>
                                                <th class="py-1">{{ t.history_date }}</th>
                                                <th class="py-1">{{ t.history_price }}</th>
                                                <th class="py-1">{{ t.history_shares }}</th>
                                                <th class="py-1">{{ t.history_commission }}</th>
                                                <th class="py-1 text-right">{{ t.history_action }}</th>
                                            </tr>
                                        </thead>
                                        <tbody class="divide-y divide-slate-900">
                                            {% for tx in stock.history_txs %}
                                            <tr class="hover:bg-slate-900/60">
                                                <td class="py-2 font-bold {% if tx.type == 'BUY' %}text-emerald-400/90{% else %}text-rose-500/90{% endif %}">{{ tx.type }}</td>
                                                <td class="py-2 text-slate-300">{{ tx.date }}</td>
                                                <td class="py-2 text-slate-300">${{ tx.price }}</td>
                                                <td class="py-2 text-slate-300">{{ tx.shares }}</td>
                                                <td class="py-2">${{ tx.commission }}</td>
                                                <td class="py-2 text-right">
                                                    <button onclick="deleteHistoryEntry({{ tx.original_index }})" class="text-rose-500 hover:text-rose-400 font-bold">{{ t.history_delete }}</button>
                                                </td>
                                            </tr>
                                            {% endfor %}
                                        </tbody>
                                    </table>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                    {% endfor %}
                </table>
            </div>

            <!-- AI 審計區塊（已移至 Modal） -->
            <div id="auditModal" class="modal-bg">
                <div class="bg-slate-900 border border-slate-800 p-8 rounded-2xl shadow-2xl w-full max-w-4xl border-l-4 border-l-emerald-500 m-4" style="max-height: 85vh; display: flex; flex-direction: column;">
                    <div class="flex justify-between items-center border-b border-slate-800 pb-4 mb-6 flex-shrink-0">
                        <h3 class="text-lg font-black text-emerald-400 tracking-wide">{{ t.audit_title }} <span class="text-slate-600 text-xs font-mono ml-2">{{ config.ai_model }}</span></h3>
                        <button onclick="closeAuditModal()" class="text-slate-400 hover:text-slate-200 font-bold text-sm">{{ t.settings_close }}</button>
                    </div>
                    <div id="auditResult" class="text-slate-300 text-sm whitespace-pre-wrap font-sans leading-relaxed overflow-y-auto flex-1"></div>
                </div>
            </div>
        </div>

        <script>
            // 🌐 i18n for JS
            window.__t = { target_alert_hit: "{{ t.target_alert_hit }}", target_alert_current: "{{ t.target_alert_current }}" };
            // 🎯 Targets data for client-side checking (no extra API calls)
{% if is_pro %}
            window.__targets = {{ targets_json|tojson }};
{% endif %}
            // 點擊股票列，切換展開與折疊明細
            function toggleHistory(id) {
                const el = document.getElementById(id);
                // Find the main row (first tr in the same tbody)
                const tbody = el.closest('tbody');
                const mainRow = tbody.querySelector('tr');
                const arrowTd = mainRow.querySelector('td');
                if (el.classList.contains('hidden')) {
                    el.classList.remove('hidden');
                    arrowTd.innerText = "▼";
                } else {
                    el.classList.add('hidden');
                    arrowTd.innerText = "▶";
                }
            }

            function toggleSettingsModal() { document.getElementById('settingsModal').classList.toggle('modal-active'); }

            // 🔀 Settings tab switching
            function switchSettingsTab(tab) {
                document.getElementById('settings-tab-general').classList.toggle('hidden', tab !== 'general');
                document.getElementById('settings-tab-ai').classList.toggle('hidden', tab !== 'ai');
                var gb = document.getElementById('tab-btn-general');
                var ab = document.getElementById('tab-btn-ai');
                if (tab === 'general') {
                    gb.className = 'px-4 py-1.5 text-xs font-bold rounded bg-cyan-600 text-slate-900';
                    ab.className = 'px-4 py-1.5 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700';
                } else {
                    ab.className = 'px-4 py-1.5 text-xs font-bold rounded bg-cyan-600 text-slate-900';
                    gb.className = 'px-4 py-1.5 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700';
                }
            }

            // 🤖 AI Provider presets — auto-fill URL & model
            const AI_PRESETS = {
                'gemini':   { url: 'https://generativelanguage.googleapis.com/v1beta/models/', model: 'gemini-2.5-flash' },
                'openai':   { url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
                'deepseek': { url: 'https://api.deepseek.com/v1', model: 'deepseek-v4-flash' },
                'ollama':   { url: 'http://localhost:11434/v1', model: 'qwen2.5:7b' },
                'vllm':     { url: 'http://localhost:8000/v1', model: '' },
                'lmstudio': { url: 'http://localhost:1234/v1', model: '' },
            };
            (function() {
                var sel = document.getElementById('settings-ai-provider');
                if (sel) sel.addEventListener('change', function() {
                    var p = AI_PRESETS[this.value];
                    if (p) {
                        document.getElementById('settings-api-url').value = p.url;
                        if (p.model) document.getElementById('settings-model').value = p.model;
                    }
                });
            })();

            // 🌍 市場篩選（隱藏整個 tbody）
            function filterMarket(market) {
                sessionStorage.setItem('activeMarket', market);
                document.querySelectorAll('.market-tab').forEach(btn => {
                    btn.className = (btn.dataset.market === market)
                        ? 'market-tab px-3 py-1 text-xs font-bold rounded bg-cyan-600 text-slate-900'
                        : 'market-tab px-3 py-1 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700';
                });
                document.querySelectorAll('tbody[data-market]').forEach(tb => {
                    tb.style.display = (market === 'all' || tb.dataset.market === market) ? '' : 'none';
                });
            }
            // Restore market tab on load
            const savedMarket = sessionStorage.getItem('activeMarket') || 'all';
            filterMarket(savedMarket);

            let updateTimer = null;
            function startHighFrequencyUpdater() {
                const intervalSec = parseInt(document.getElementById('refreshIntervalInput').value) || 5;
                if (updateTimer) clearInterval(updateTimer);
                updateTimer = setInterval(() => {
                    const indicator = document.getElementById('refreshIndicator');
                    indicator.classList.replace('bg-emerald-500', 'bg-cyan-400');
                    fetch('/api/portfolio/realtime_feed')
                        .then(res => res.json())
                        .then(data => {
                            setTimeout(() => { indicator.classList.replace('bg-cyan-400', 'bg-emerald-500'); }, 200);
{% if is_pro %}
                            checkTargetAlerts();
{% endif %}                            if (!data.market_active) return;
                            document.getElementById('top-total-mv-usd').innerText = '$' + data.total_mv_usd_str;
                            document.getElementById('top-total-mv-hkd').innerText = '≈ ' + data.sec_cur + '$' + data.total_mv_sec_str;
                        }).catch(() => {});
                }, intervalSec * 1000);
            }

            function updateLiveInterval(val) {
                fetch('/api/config/update_interval', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_interval: parseInt(val) })
                }).then(() => { startHighFrequencyUpdater(); });
            }
{% if is_pro %}

            function runAiAudit() {
                const modal = document.getElementById('auditModal');
                const result = document.getElementById('auditResult');
                modal.classList.add('modal-active');
                var provider = document.getElementById('settings-ai-provider');
                var isLocal = provider && ['ollama','vllm','lmstudio'].includes(provider.value);
                if (!isLocal && !confirm('{{ t.audit_confirm }}')) {
                    modal.classList.remove('modal-active');
                    return;
                }
                result.textContent = '{{ t.audit_loading }}';
                fetch('/api/ai_audit', { method: 'POST' }).then(res => res.json()).then(data => {
                    if (data.success) {
                        result.textContent = data.report;
                    } else {
                        result.textContent = '[Error] ' + data.error;
                    }
                }).catch(err => {
                    result.textContent = '[Error] ' + err.message;
                });
            }

            function closeAuditModal() {
                document.getElementById('auditModal').classList.remove('modal-active');
            }

            // Click outside modal to close
            document.getElementById('auditModal').addEventListener('click', function(e) {
                if (e.target === this) closeAuditModal();
            });

            // 🧮 預計成本/收入即時計算
            {% endif %}
            function attachCostCalculator(formSelector, inputsSelector, resultId, label, sign) {
                const form = document.querySelector(formSelector);
                if (!form) return;
                const inputs = form.querySelectorAll(inputsSelector);
                const resultEl = document.getElementById(resultId);
                const calc = () => {
                    let price = parseFloat(inputs[0]?.value) || 0;
                    let shares = parseFloat(inputs[1]?.value) || 0;
                    let commission = parseFloat(inputs[2]?.value) || 0;
                    let total = (price * shares) + (sign * commission);
                    resultEl.innerText = label + ': $' + total.toFixed(2);
                };
                inputs.forEach(el => el.addEventListener('input', calc));
            }

            // 📋 Watchlist Management
            function createNewCategory() {
                const name = prompt('{{ t.wl_new_cat_prompt }}');
                if (!name || !name.trim()) return;
                fetch('/api/wl/add_category', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: name.trim()}) })
                .then(r => r.json()).then(d => { if (d.success) location.reload(); else alert(d.error); });
            }
            function deleteCategory(name) {
                if (!confirm('{{ t.wl_delete_cat }}: ' + name + '?')) return;
                fetch('/api/wl/delete_category', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: name}) })
                .then(r => r.json()).then(d => { if (d.success) location.reload(); });
            }
            function renameCategory(oldName, newName) {
                if (!newName.trim() || newName.trim() === oldName) return;
                fetch('/api/wl/rename_category', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({old_name: oldName, new_name: newName.trim()}) })
                .then(r => r.json()).then(d => { if (d.success) location.reload(); });
            }
            function addTickerToCategory(catName, el) {
                const input = el.tagName === 'INPUT' ? el : el.previousElementSibling;
                const ticker = input.value.trim().toUpperCase();
                if (!ticker) return;
                fetch('/api/wl/add_ticker', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({category: catName, ticker: ticker}) })
                .then(r => r.json()).then(d => { if (d.success) location.reload(); });
            }
            function deleteTickerFromCategory(catName, ticker) {
                fetch('/api/wl/delete_ticker', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({category: catName, ticker: ticker}) })
                .then(r => r.json()).then(d => { if (d.success) location.reload(); });
            }
{% if is_pro %}
            // 🎯 Target Price Management
            function setTarget(ticker) {
                const price = prompt(ticker + ' 目標價 (USD)');
                if (!price || isNaN(price)) return;
                const p = parseFloat(price);
                fetch('/api/wl/set_target', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ticker: ticker, price: p}) })
                .then(r => r.json()).then(d => {
                    if (d.success) {
                        updateTargetBtn(ticker, p);
                        window.__targets[ticker] = p;
                        checkTargetAlerts();
                    }
                });
            }
            function deleteTarget(ticker) {
                if (!confirm('刪除 ' + ticker + ' 的目標價？')) return;
                fetch('/api/wl/delete_target', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ticker: ticker}) })
                .then(r => r.json()).then(d => {
                    if (d.success) {
                        updateTargetBtn(ticker, null);
                        delete window.__targets[ticker];
                        checkTargetAlerts();
                    }
                });
            }
            function updateTargetBtn(ticker, targetPrice) {
                const span = document.getElementById('wl-target-' + ticker);
                if (!span) return;
                span.innerHTML = '';
                const btn = document.createElement('button');
                btn.className = 'text-[9px] font-mono';
                if (targetPrice !== null) {
                    btn.className += ' text-amber-400 hover:text-rose-400';
                    btn.title = '刪除目標價';
                    btn.textContent = '🎯$' + targetPrice.toFixed(2) + ' ✕';
                    btn.onclick = function() { deleteTarget(ticker); };
                } else {
                    btn.className += ' text-slate-600 hover:text-amber-400';
                    btn.title = '🎯';
                    btn.textContent = '🎯';
                    btn.onclick = function() { setTarget(ticker); };
                }
                span.appendChild(btn);
            }
            function checkTargetAlerts(data) {
                // Reads prices from watchlist DOM (instant, no API call)
                const alertsDiv = document.getElementById('target-alerts');
                if (!alertsDiv) return;
                const targets = window.__targets || {};
                const reached = [];
                for (const [tk, target] of Object.entries(targets)) {
                    const priceEl = document.getElementById('wl-price-' + tk);
                    if (!priceEl) continue;
                    const price = parseFloat(priceEl.textContent.replace('$', ''));
                    if (price > 0 && price <= target) {
                        reached.push({ticker: tk, price: price, target: target});
                    }
                }
                if (reached.length === 0) {
                    alertsDiv.innerHTML = '<p class="text-slate-600 italic">—</p>';
                } else {
                    alertsDiv.innerHTML = reached.map(r =>
                        '<div class="text-rose-400 font-mono">🎯 ' + r.ticker +
                        ' ' + window.__t.target_alert_hit + ' $' + r.target.toFixed(2) +
                        ' <span class="text-slate-500">(' + window.__t.target_alert_current + ' $' + r.price.toFixed(2) + ')</span></div>'
                    ).join('');
                }
            }
{% endif %}

            // 🔄 Drag & Drop: Watchlist Category Reordering
            let draggedCat = null;
            function handleDragStart(e) {
                const header = e.currentTarget;
                const el = header.closest('.wl-cat-group');
                if (!el) return;
                draggedCat = el;
                el.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', el.dataset.cat);
            }
            function handleDragOver(e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                return false;
            }
            function handleDragEnter(e) {
                const el = e.currentTarget;
                if (el !== draggedCat) {
                    el.classList.add('drag-over');
                }
            }
            function handleDragLeave(e) {
                e.currentTarget.classList.remove('drag-over');
            }
            function handleDragEnd(e) {
                const el = e.currentTarget;
                el.classList.remove('dragging');
                document.querySelectorAll('.wl-cat-group').forEach(el2 => el2.classList.remove('drag-over'));
                draggedCat = null;
            }
            function handleDrop(e) {
                e.stopPropagation();
                e.preventDefault();
                const el = e.currentTarget;
                if (!draggedCat || draggedCat === el) return;
                // Swap positions in DOM
                const parent = el.parentNode;
                const all = [...parent.querySelectorAll('.wl-cat-group')];
                const fromIdx = all.indexOf(draggedCat);
                const toIdx = all.indexOf(el);
                if (fromIdx < toIdx) {
                    parent.insertBefore(draggedCat, el.nextSibling);
                } else {
                    parent.insertBefore(draggedCat, el);
                }
                // Persist new order
                const newOrder = [...parent.querySelectorAll('.wl-cat-group')].map(el2 => el2.dataset.cat);
                fetch('/api/wl/reorder_categories', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({order: newOrder})
                }).then(r => r.json()).then(d => {
                    if (!d.success) console.error('Reorder failed:', d.error);
                });
                el.classList.remove('drag-over');
            }
            // Attach dragenter/dragleave to all cat groups after DOM ready
            document.addEventListener('DOMContentLoaded', function() {
                document.querySelectorAll('.wl-cat-group').forEach(el => {
                    el.addEventListener('dragenter', handleDragEnter);
                    el.addEventListener('dragleave', handleDragLeave);
                });
            });

            window.onload = function() {
                startHighFrequencyUpdater();
                attachCostCalculator('#buy-form', 'input[type="number"]', 'buy-estimated-cost', '預計成本', 1);
                attachCostCalculator('#sell-form', 'input[type="number"]', 'sell-estimated-cost', '預計收入', -1);
            };

            // 🔄 AJAX trade submission + history delete
            function submitTrade(e, type) {
                e.preventDefault();
                const form = e.target;
                const btn = form.querySelector('button[type="submit"]');
                const origText = btn.textContent;
                btn.textContent = '...';
                btn.disabled = true;
                const data = new FormData(form);
                fetch('/api/portfolio/' + type, { method: 'POST', body: data })
                .then(r => { location.reload(); })
                .catch(() => { btn.textContent = origText; btn.disabled = false; });
            }
            function deleteHistoryEntry(index) {
                if (!confirm('確認刪除此交易？')) return;
                fetch('/delete/' + index, { method: 'POST' })
                .then(r => { location.reload(); })
                .catch(() => {});
            }
            {% if CLOUD_MODE %}
            function logout() {
                if (typeof supabase !== 'undefined' && supabase.auth) {
                    supabase.auth.signOut().catch(function(){});
                }
                document.cookie = 'sb-access-token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
                window.location.href = '/';
            }
            {% endif %}
        </script>
        {% if CLOUD_MODE %}
        <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
        <script>
            const sb = supabase.createClient("{{ supabase_url }}", "{{ supabase_key }}");
        </script>
        {% endif %}
    </body>
    </html>
    """, t=t, stocks=stocks, open_tickers=open_tickers, ticker_market=ticker_market,
        total_mv_usd=total_mv_usd, total_open_cost=total_open_cost,
        total_pnl_usd=total_pnl_usd, total_roi_str=total_roi_str,
        usd_hkd=usd_hkd, sec_cur=sec_cur, watchlist_html=watchlist_html,
        targets_json=targets_json, markets_status=markets_status,
        active_markets=active_markets, version=VERSION, changelog=CHANGELOG,
        today_date=date_str, config=config, is_pro=get_is_pro(),
        CLOUD_MODE=CLOUD_MODE,
        supabase_url=SUPABASE_URL if CLOUD_MODE else "",
        supabase_key=SUPABASE_KEY if CLOUD_MODE else "",
        total_mv_usd_raw=total_mv_usd, total_open_cost_raw=total_open_cost,
        cash_balance=config.get("cash_balance", 0))


@app.route('/')
def index():
    """Main route. Cloud: landing page (if unauthenticated) or redirect to /dashboard.
    Selfhosted: render dashboard directly."""
    if CLOUD_MODE:
        token = request.cookies.get("sb-access-token")
        if token:
            try:
                supabase.auth.get_user(token)
                return redirect("/dashboard")
            except Exception:
                pass
        return render_landing_page()
    return _render_dashboard()


@app.route('/dashboard')
def dashboard():
    """Dashboard route. Cloud: auth-gated. Selfhosted: redirect to /."""
    if CLOUD_MODE:
        return _render_dashboard()
    return redirect("/")


@app.route('/health')
def health():
    if CLOUD_MODE:
        return jsonify({"status": "ok", "cache_size": len(PRICE_CACHE)})
    return jsonify({"status": "ok"})
# ==================== 🎯 5. Watchlist 管理 API ====================
@app.route('/api/wl/add_category', methods=['POST'])
def api_wl_add_category():
    data = request.get_json()
    cat_name = data.get('name', '').strip()
    if not cat_name: return jsonify({'success': False, 'error': 'Category name required'})
    wl = load_watchlist()
    if cat_name in wl.get('categories', {}): return jsonify({'success': False, 'error': 'Category exists'})
    wl.setdefault('categories', {})[cat_name] = []
    save_watchlist(wl)
    return jsonify({'success': True})

@app.route('/api/wl/delete_category', methods=['POST'])
def api_wl_delete_category():
    data = request.get_json()
    cat_name = data.get('name', '').strip()
    wl = load_watchlist()
    if cat_name in wl.get('categories', {}):
        del wl['categories'][cat_name]
        save_watchlist(wl)
    return jsonify({'success': True})

@app.route('/api/wl/rename_category', methods=['POST'])
def api_wl_rename_category():
    data = request.get_json()
    old_name = data.get('old_name', '').strip()
    new_name = data.get('new_name', '').strip()
    if not old_name or not new_name: return jsonify({'success': False})
    wl = load_watchlist()
    cats = wl.get('categories', {})
    if old_name in cats and new_name not in cats:
        cats[new_name] = cats.pop(old_name)
        save_watchlist(wl)
    return jsonify({'success': True})

@app.route('/api/wl/add_ticker', methods=['POST'])
def api_wl_add_ticker():
    data = request.get_json()
    cat_name = data.get('category', '').strip()
    ticker = data.get('ticker', '').strip().upper()
    if not cat_name or not ticker: return jsonify({'success': False})
    wl = load_watchlist()
    cats = wl.get('categories', {})
    if cat_name in cats and ticker not in cats[cat_name]:
        cats[cat_name].append(ticker)
        save_watchlist(wl)
    return jsonify({'success': True})

@app.route('/api/wl/delete_ticker', methods=['POST'])
def api_wl_delete_ticker():
    data = request.get_json()
    cat_name = data.get('category', '').strip()
    ticker = data.get('ticker', '').strip().upper()
    wl = load_watchlist()
    cats = wl.get('categories', {})
    if cat_name in cats and ticker in cats[cat_name]:
        cats[cat_name].remove(ticker)
        save_watchlist(wl)
    return jsonify({'success': True})

@app.route('/api/wl/reorder_categories', methods=['POST'])
def api_wl_reorder_categories():
    data = request.get_json()
    new_order = data.get('order', [])
    if not new_order:
        return jsonify({'success': False, 'error': 'Order list required'})
    wl = load_watchlist()
    old_cats = wl.get('categories', {})
    # Rebuild dict in new order
    new_cats = {}
    for cat in new_order:
        if cat in old_cats:
            new_cats[cat] = old_cats[cat]
    # Append any categories not in the order list
    for cat, tickers in old_cats.items():
        if cat not in new_cats:
            new_cats[cat] = tickers
    wl['categories'] = new_cats
    save_watchlist(wl)
    return jsonify({'success': True})

@app.route('/api/wl/set_target', methods=['POST'])
def api_wl_set_target():
    if not get_is_pro(): return jsonify({'error': 'Pro feature'}), 403
    data = request.get_json()
    ticker = data.get('ticker', '').strip().upper()
    price = data.get('price')
    if not ticker or price is None:
        return jsonify({'success': False, 'error': 'ticker and price required'})
    try:
        price = float(price)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid price'})
    wl = load_watchlist()
    wl.setdefault('targets', {})[ticker] = price
    save_watchlist(wl)
    return jsonify({'success': True})

@app.route('/api/wl/delete_target', methods=['POST'])
def api_wl_delete_target():
    if not get_is_pro(): return jsonify({'error': 'Pro feature'}), 403
    data = request.get_json()
    ticker = data.get('ticker', '').strip().upper()
    wl = load_watchlist()
    targets = wl.get('targets', {})
    if ticker in targets:
        del targets[ticker]
        save_watchlist(wl)
    return jsonify({'success': True})

@app.route('/api/wl/targets', methods=['GET'])
def api_wl_targets():
    if not get_is_pro(): return jsonify({'error': 'Pro feature'}), 403
    wl = load_watchlist()
    targets = wl.get('targets', {})
    # Return targets with current prices
    result = {}
    for tk, tp in targets.items():
        q = get_realtime_data(tk)
        result[tk] = {'target': tp, 'price': q['price']}
    return jsonify(result)

# ==================== 🎯 6. 精準刪除路由 ====================
@app.route('/delete/<int:index>', methods=['POST'])
def delete_entry(index):
    portfolio = load_portfolio()
    if 0 <= index < len(portfolio):
        portfolio.pop(index)
        save_portfolio(portfolio)
    return redirect(url_for('index'))

# ==================== 🎯 7. 其餘 API ====================
@app.route('/api/config/save', methods=['POST'])
def api_save_config():
    config = load_config()
    if get_is_pro():
        config["api_key"] = request.form.get("api_key", "").strip()
        config["ai_provider"] = request.form.get("ai_provider", "gemini")
        config["ai_model"] = request.form.get("ai_model", "").strip()
        config["custom_api_url"] = request.form.get("custom_api_url", "").strip()
    if get_is_pro():
        config["ai_timeout"] = int(request.form.get("ai_timeout", "60"))
        config["prompt_level"] = request.form.get("prompt_level", "balanced")
        config["custom_prompt"] = request.form.get("custom_prompt", "").strip()
        config["prompt_mode"] = request.form.get("prompt_mode", "style")
    config["language"] = request.form.get("language", "zh_tw")
    config["cash_balance"] = float(request.form.get("cash_balance", "0") or 0)
    config["secondary_currency"] = request.form.get("secondary_currency", "HKD")
    save_config(config)
    return redirect(url_for('index'))

@app.route('/api/config/update_interval', methods=['POST'])
def api_update_interval():
    config = load_config()
    config["refresh_interval"] = max(10, request.json.get("refresh_interval", 30))
    save_config(config)
    return jsonify({"success": True})

@app.route('/api/ai_audit', methods=['POST'])
def api_ai_audit():
    if not get_is_pro(): return jsonify({'error': 'Pro feature'}), 403
    config = load_config()
    api_key = config.get("api_key", "")
    provider = config.get("ai_provider", "gemini")
    model_name = config.get("ai_model", "")
    base_url = config.get("custom_api_url", "")
    local_providers = {'ollama', 'vllm', 'lmstudio'}
    if not api_key and provider not in local_providers:
        return jsonify({'success': False, 'error': 'Please configure your API Key.'})
    
    stocks, _, _, total_mv_usd, total_open_cost_usd, usd_hkd, sec_cur = calculate_portfolio_matrix()
    open_stocks = [s for s in stocks if s['status'] == 'OPEN']
    if not open_stocks: return jsonify({'success': False, 'error': 'No open positions.'})
    
    # Build rich portfolio context
    total_pnl = total_mv_usd - total_open_cost_usd
    total_roi = (total_pnl / total_open_cost_usd * 100) if total_open_cost_usd > 0 else 0
    
    # Market allocation
    market_mv = {}
    for s in open_stocks:
        mkt = s['market']
        market_mv[mkt] = market_mv.get(mkt, 0) + float(s.get('current_mv', '0').replace(',', '') or '0')
    alloc_lines = [f"  {m}: ${v:,.2f} ({v/total_mv_usd*100:.1f}%)" for m, v in sorted(market_mv.items(), key=lambda x: -x[1]) if total_mv_usd > 0]
    
    holding_lines = []
    for s in open_stocks:
        danger = " ⚠️ STOP-LOSS TRIGGERED" if s.get('is_danger') else ""
        holding_lines.append(
            f"${s['ticker']} [{s['market']}] | Shares: {s['total_shares']} | "
            f"Avg Cost: ${s['avg_buy_price']} | Current: ${s['current_price']} | "
            f"P&L: {s['pnl_usd_str']} | ROI: {s['roi_str']}{danger}"
        )
    
    lang_map = {"zh_tw": "Traditional Chinese (繁體中文)", "zh_cn": "Simplified Chinese (簡體中文)", "en": "English"}
    lang = lang_map.get(config.get("language", "zh_tw"), "Traditional Chinese (繁體中文)")

    # Build summary strings for prompt templates
    summary_str = f"Total MV: ${total_mv_usd:,.2f}, Cost: ${total_open_cost_usd:,.2f}, PnL: ${total_pnl:+,.2f} ({total_roi:+.2f}%), Holdings: {len(open_stocks)}"
    holdings_str = "; ".join([f"${s['ticker']} [{s['market']}] Shs:{s['total_shares']} Cost:${s['avg_buy_price']} Now:${s['current_price']} PnL:{s['pnl_usd_str']} ROI:{s['roi_str']}" for s in open_stocks])
    alloc_str = "; ".join(alloc_lines) if alloc_lines else "N/A"

    custom = config.get("custom_prompt", "").strip()
    level = config.get("prompt_level", "balanced")

    prompt_mode = config.get("prompt_mode", "style")
    if prompt_mode == "custom" and custom:
        prompt_text = custom.replace("{summary}", summary_str).replace("{holdings}", holdings_str).replace("{alloc}", alloc_str)
        if "{lang}" in custom:
            prompt_text = prompt_text.replace("{lang}", lang)
        else:
            prompt_text += "\n\nRespond in " + lang + "."
    elif level == "strict":
        prompt_text = f"You are a strict risk-focused portfolio auditor. Be blunt about problems. Recommend concrete sell/stop-loss actions. Report in {lang}. Use markdown.\n\nPortfolio Summary: {summary_str}\nAllocation: {alloc_str}\n\nHoldings:\n{chr(10).join(holding_lines)}\n\nRequired Sections:\n1. Risk Audit — Flag EVERY danger, stop-loss violation, concentration issue\n2. Stop-Loss Compliance — Which holdings violated stops? Immediate actions required\n3. Sell Recommendations — Which positions to exit NOW and why\n4. Max 3 Hold/Buy picks with brief justification\n\nBe direct. No sugar-coating."
    elif level == "relaxed":
        prompt_text = f"You are an optimistic growth-focused portfolio coach. Highlight strengths and future potential. Suggest adding to winners. Report in {lang}. Use markdown.\n\nPortfolio Summary: {summary_str}\nAllocation: {alloc_str}\n\nHoldings:\n{chr(10).join(holding_lines)}\n\nRequired Sections:\n1. Growth Outlook — Market trends and tailwinds benefiting the portfolio\n2. Strength Analysis — What each holding is doing RIGHT\n3. Opportunity Spotting — Undervalued positions, add-more candidates\n4. Portfolio Expansion — New sectors or themes to consider\n\nBe encouraging. Focus on upside."
    else:  # balanced (default)
        prompt_text = f"You are a professional portfolio analyst. Provide a comprehensive portfolio analysis report in {lang}. Use markdown formatting with clear section headers.\n\n## Portfolio Overview\n- Total Market Value: ${total_mv_usd:,.2f} USD\n- Total Cost Basis: ${total_open_cost_usd:,.2f} USD\n- Total P&L: ${total_pnl:+,.2f} USD ({total_roi:+.2f}%)\n- Number of Holdings: {len(open_stocks)}\n\n## Market Allocation\n{chr(10).join(alloc_lines) if alloc_lines else '  N/A'}\n\n## Holdings Detail\n{chr(10).join(holding_lines)}\n\n## Required Analysis Sections\n1. Overall Assessment\n2. Per-Stock Analysis\n3. Risk Alerts\n4. Actionable Suggestions\n\nKeep it concise. Use a summary table."
    try:
        if provider == "gemini":
            if not base_url.endswith('/'): base_url += '/'
            url = f"{base_url}{model_name}:generateContent?key={api_key}"
            payload = {"contents": [{"role": "user", "parts": [{"text": prompt_text}]}]}
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=config.get("ai_timeout", 60)).json()
            report = res['candidates'][0]['content']['parts'][0]['text']
        else:
            url = f"{base_url}/chat/completions" if not base_url.endswith('/chat/completions') else base_url
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"model": model_name, "messages": [{"role": "user", "content": prompt_text}], "temperature": 0.3}
            res = requests.post(url, json=payload, headers=headers, timeout=config.get("ai_timeout", 60)).json()
            report = res['choices'][0]['message']['content']
        return jsonify({'success': True, 'report': report})
    except Timeout:
        msg = 'Request timed out. Try increasing the timeout in Settings → AI Model.' if config.get('language','zh_tw') == 'en' else '請求超時，請在設定 → AI 模型 中調高 Timeout 秒數。'
        return jsonify({'success': False, 'error': msg})
    except ReqConnectionError:
        msg = 'Cannot connect to AI server. Check your API URL in Settings → AI Model (is the service running?).' if config.get('language','zh_tw') == 'en' else '無法連線到 AI 伺服器，請檢查設定 → AI 模型中的 API URL（服務是否已啟動？）'
        return jsonify({'success': False, 'error': msg})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/portfolio/realtime_feed')
def api_portfolio_realtime_feed():
    if not check_any_market_active(): return jsonify({'market_active': False})
    stocks, _, _, total_mv_usd, total_open_cost, usd_hkd, _ = calculate_portfolio_matrix()
    config = load_config()
    sec_cur = config.get('secondary_currency', 'HKD')
    return jsonify({'market_active': True, 'total_mv_usd_str': f"{total_mv_usd:,.2f}", 'total_mv_sec_str': f"{(total_mv_usd * usd_hkd):,.2f}", 'sec_cur': sec_cur})

@app.route('/api/portfolio/buy', methods=['POST'])
def api_portfolio_buy():
    p = load_portfolio()
    market = request.form.get("market", "US")
    ticker = request.form.get("ticker").strip().upper()
    # Auto-append market suffix + zero-pad if not already present
    SUFFIX_MAP = {"HK": ".HK", "TW": ".TW", "TWO": ".TWO"}
    PAD_MAP = {"HK": 4, "CN": 6}  # HK=4-digit, CN=6-digit
    if market in SUFFIX_MAP and "." not in ticker:
        if market in PAD_MAP and ticker.isdigit():
            ticker = ticker.zfill(PAD_MAP[market])
        ticker += SUFFIX_MAP[market]
    elif market == "CN" and "." not in ticker:
        if ticker.isdigit():
            ticker = ticker.zfill(6)
        # Auto-detect Shanghai (.SS) vs Shenzhen (.SZ) by ticker prefix
        SH_PREFIXES = ('600', '601', '603', '605', '688')          # 上海主板+科創板
        SZ_PREFIXES = ('000', '001', '002', '003', '300', '301')  # 深圳主板+創業板+中小板
        if ticker[:3] in SH_PREFIXES:
            ticker += '.SS'
        elif ticker[:3] in SZ_PREFIXES:
            ticker += '.SZ'
        else:
            ticker += '.SS'  # fallback: default to Shanghai
    p.append({"type": "BUY", "market": market, "date": request.form.get("buy_date"), "ticker": ticker, "price": request.form.get("buy_price"), "commission": request.form.get("buy_commission"), "shares": request.form.get("buy_shares")})
    save_portfolio(p)
    return redirect(url_for('index'))

@app.route('/api/portfolio/sell', methods=['POST'])
def api_portfolio_sell():
    p = load_portfolio()
    ticker = request.form.get("ticker").strip().upper()
    # Auto-detect market from existing entries
    market = "US"
    for tx in p:
        if tx.get("ticker", "").upper() == ticker:
            market = tx.get("market") or "US"
            break
    p.append({"type": "SELL", "market": market, "date": request.form.get("sell_date"), "ticker": ticker, "price": request.form.get("sell_price"), "commission": request.form.get("sell_commission"), "shares": request.form.get("sell_shares")})
    save_portfolio(p)
    return redirect(url_for('index'))

@app.route('/pulse_logo.png')
def pulse_logo():
    return send_from_directory(BASE_DIR, 'pulse_logo.png')

@app.route('/pulse.css')
def pulse_css():
    return send_from_directory(BASE_DIR, 'pulse.css')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)