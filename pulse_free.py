import os
import json
import requests
from requests.exceptions import Timeout, ConnectionError as ReqConnectionError
import time
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_from_directory, g, abort
import yfinance as yf

CLOUD_MODE = os.getenv("CLOUD_MODE", "").lower() in ("1", "true", "yes", "cloud")

if CLOUD_MODE:
    from supabase import create_client
    import stripe
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not SUPABASE_URL:
        raise RuntimeError("CLOUD_MODE is enabled but SUPABASE_URL is not set")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    STRIPE_SECRET = os.getenv("STRIPE_SECRET", "")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
    FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "5"))
else:
    supabase = None
    supabase_admin = None
    SUPABASE_URL = ""
    SUPABASE_KEY = ""
    STRIPE_SECRET = ""
    STRIPE_WEBHOOK_SECRET = ""
    STRIPE_PRICE_ID = ""
    FREE_DAILY_LIMIT = 999999

app = Flask(__name__)

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
LANDING_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <title>Pulse — Investment Portfolio Tracker</title>
    <link rel="icon" href="/pulse_logo.png" type="image/png">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #020617; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; }
        .container { max-width: 1100px; margin: 0 auto; padding: 40px 20px; }
        .hero { text-align: center; padding: 80px 20px 60px; }
        .hero h1 { font-size: 4rem; font-weight: 900; background: linear-gradient(135deg, #34d399, #22d3ee); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .hero p { color: #94a3b8; font-size: 1.2rem; margin-top: 16px; }
        .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 24px; margin: 60px 0; }
        .feature-card { background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 28px 24px; text-align: center; }
        .feature-card .icon { font-size: 2.5rem; margin-bottom: 12px; }
        .feature-card h3 { font-size: 1.1rem; font-weight: 700; color: #34d399; margin-bottom: 8px; }
        .feature-card p { color: #64748b; font-size: 0.9rem; line-height: 1.5; }
        .pricing { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; margin: 60px 0; }
        .pricing-card { background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 32px 28px; text-align: center; }
        .pricing-card.pro { border-color: #22d3ee; background: linear-gradient(135deg, #0f172a, #0c1929); }
        .pricing-card h3 { font-size: 1.3rem; font-weight: 800; margin-bottom: 8px; }
        .pricing-card .price { font-size: 2.5rem; font-weight: 900; color: #22d3ee; margin: 16px 0; }
        .pricing-card .price span { font-size: 1rem; color: #64748b; }
        .pricing-card ul { list-style: none; text-align: left; margin: 20px 0; color: #94a3b8; font-size: 0.9rem; line-height: 2; }
        .pricing-card ul li::before { content: "✓ "; color: #34d399; font-weight: bold; }
        .btn { display: inline-block; padding: 12px 32px; border-radius: 12px; font-weight: 700; font-size: 1rem; cursor: pointer; border: none; transition: all 0.2s; text-decoration: none; }
        .btn-primary { background: linear-gradient(135deg, #34d399, #22d3ee); color: #020617; }
        .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(34, 211, 238, 0.3); }
        .btn-outline { background: transparent; border: 2px solid #22d3ee; color: #22d3ee; }
        .btn-outline:hover { background: rgba(34, 211, 238, 0.1); }
        .auth-section { text-align: center; padding: 40px 0 20px; }
        .auth-section h2 { font-size: 1.5rem; margin-bottom: 20px; }
        .auth-form { display: flex; flex-direction: column; gap: 12px; max-width: 360px; margin: 0 auto; }
        .auth-form input { padding: 12px 16px; border-radius: 10px; border: 1px solid #1e293b; background: #0f172a; color: #e2e8f0; font-size: 1rem; }
        .auth-form input:focus { outline: none; border-color: #22d3ee; }
        .auth-form button { margin-top: 8px; }
        .footer { text-align: center; padding: 60px 20px 20px; color: #475569; font-size: 0.8rem; }
        .divider { display: flex; align-items: center; gap: 16px; margin: 20px 0; color: #475569; font-size: 0.85rem; }
        .divider::before, .divider::after { content: ""; flex: 1; height: 1px; background: #1e293b; }
        #auth-message { color: #f87171; font-size: 0.85rem; margin-top: 8px; display: none; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
</head>
<body>
    <div class="container">
        <div class="hero">
            <h1>Pulse</h1>
            <p>Live Data · Real Intuition — Track your portfolio across US, HK, CN, TW markets</p>
        </div>

        <div class="features">
            <div class="feature-card">
                <div class="icon">📊</div>
                <h3>Multi-Market</h3>
                <p>Track US, HK, CN, and TW stocks in one unified dashboard with real-time prices.</p>
            </div>
            <div class="feature-card">
                <div class="icon">🤖</div>
                <h3>AI Analysis</h3>
                <p>Get AI-powered portfolio audit reports with risk assessment and recommendations.</p>
            </div>
            <div class="feature-card">
                <div class="icon">📈</div>
                <h3>Live Tracking</h3>
                <p>Real-time price updates, P&L calculation, stop-loss alerts, and target price monitoring.</p>
            </div>
            <div class="feature-card">
                <div class="icon">🔍</div>
                <h3>Smart Watchlist</h3>
                <p>Organized watchlists with drag-and-drop, target prices, and instant price checking.</p>
            </div>
            <div class="feature-card">
                <div class="icon">🌍</div>
                <h3>Multi-Currency</h3>
                <p>View in USD, HKD, TWD, CNY, JPY, EUR, or GBP with live forex rates.</p>
            </div>
        </div>

        <div class="pricing">
            <div class="pricing-card">
                <h3>Free</h3>
                <div class="price">$0<span>/month</span></div>
                <ul>
                    <li>Unlimited portfolio tracking</li>
                    <li>Real-time price data</li>
                    <li>Multi-market support</li>
                    <li>Watchlist management</li>
                    <li>Basic analytics</li>
                </ul>
            </div>
            <div class="pricing-card pro">
                <h3>Pro</h3>
                <div class="price">$5<span>/month</span></div>
                <ul>
                    <li>Everything in Free</li>
                    <li>AI portfolio audit reports</li>
                    <li>Advanced analytics & charts</li>
                    <li>Target price alerts</li>
                    <li>Custom AI model configuration</li>
                    <li>Priority background updates</li>
                </ul>
            </div>
        </div>

        <div class="auth-section">
            <h2>Get Started</h2>
            <div class="auth-form" id="auth-form">
                <button class="btn btn-outline" onclick="signInWithGoogle()">Sign in with Google</button>
                <div class="divider">or</div>
                <input type="email" id="auth-email" placeholder="Email address">
                <input type="password" id="auth-password" placeholder="Password">
                <button class="btn btn-primary" onclick="signInWithEmail()">Continue</button>
                <div id="auth-message"></div>
            </div>
        </div>

        <div class="footer">
            <p>Pulse v{{ version }} — Self-host your own data or use Pulse Cloud.</p>
            <p><a href="https://github.com/nousresearch/pulse" style="color:#22d3ee;">View on GitHub</a></p>
        </div>
    </div>

    <script>
        const supabaseClient = supabase.createClient("{{ supabase_url }}", "{{ supabase_key }}");
        function setCookie(name, value) {
            document.cookie = name + "=" + value + ";path=/;max-age=86400;SameSite=Lax";
        }
        function showMessage(msg, isError) {
            const el = document.getElementById("auth-message");
            el.textContent = msg;
            el.style.color = isError ? "#f87171" : "#34d399";
            el.style.display = "block";
        }
        function redirectToDashboard() { window.location.href = "/dashboard"; }
        async function signInWithGoogle() {
            const { data, error } = await supabaseClient.auth.signInWithOAuth({
                provider: "google",
                options: { redirectTo: window.location.origin + "/dashboard" }
            });
            if (error) showMessage(error.message, true);
        }
        async function signInWithEmail() {
            const email = document.getElementById("auth-email").value;
            const password = document.getElementById("auth-password").value;
            if (!email || !password) { showMessage("Please enter email and password", true); return; }
            const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });
            if (error) {
                if (error.message.includes("Invalid login")) {
                    const { data: signUpData, error: signUpError } = await supabaseClient.auth.signUp({ email, password });
                    if (signUpError) { showMessage(signUpError.message, true); return; }
                    showMessage("Account created! Check your email to confirm.", false);
                    return;
                }
                showMessage(error.message, true);
                return;
            }
            if (data.session) {
                setCookie("sb-access-token", data.session.access_token);
                redirectToDashboard();
            }
        }
        supabaseClient.auth.onAuthStateChange((event, session) => {
            if (event === "SIGNED_IN" && session) {
                setCookie("sb-access-token", session.access_token);
                redirectToDashboard();
            }
        });
    </script>
</body>
</html>
"""

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
    if CLOUD_MODE and g.get("user_id"):
        try:
            resp = supabase_admin.table("portfolios").select("*").eq("user_id", g.user_id).execute()
            return [{"ticker": r["ticker"], "shares": r["shares"], "avg_price": r["avg_price"],
                     "market": r.get("market", "US"), "date": r.get("buy_date", ""),
                     "type": "BUY", "price": r["avg_price"], "commission": 0}
                    for r in (resp.data or [])]
        except Exception:
            return []
    return load_json_file(PORTFOLIO_JSON, [])

def save_portfolio(data):
    if CLOUD_MODE and g.get("user_id"):
        try:
            # Delete existing rows for this user that are not in new data
            new_tickers = {d.get("ticker", "").upper() for d in data if d.get("type") == "BUY"}
            existing = supabase_admin.table("portfolios").select("ticker").eq("user_id", g.user_id).execute()
            for row in (existing.data or []):
                if row["ticker"].upper() not in new_tickers:
                    supabase_admin.table("portfolios").delete().eq("user_id", g.user_id).eq("ticker", row["ticker"]).execute()
            # Aggregate BUY entries by ticker
            agg = {}
            for d in data:
                if d.get("type") != "BUY":
                    continue
                tk = d["ticker"].upper()
                if tk not in agg:
                    agg[tk] = {"user_id": g.user_id, "ticker": tk,
                               "shares": 0.0, "avg_price": 0.0, "market": d.get("market", "US"),
                               "buy_date": d.get("date", "")}
                idx = agg[tk]
                shares = float(d.get("shares", 0))
                price = float(d.get("price", 0))
                total_spend = idx["shares"] * idx["avg_price"] + shares * price
                idx["shares"] += shares
                idx["avg_price"] = total_spend / idx["shares"] if idx["shares"] > 0 else 0.0
            for row in agg.values():
                supabase_admin.table("portfolios").upsert(row, on_conflict="user_id,ticker").execute()
        except Exception:
            pass
        return
    save_json_file(PORTFOLIO_JSON, data)

def load_config():
    if CLOUD_MODE and g.get("user_id"):
        try:
            resp = supabase_admin.table("profiles").select("*").eq("user_id", g.user_id).single().execute()
            if resp.data:
                return {k: v for k, v in resp.data.items() if k not in ("user_id", "tier", "pro_expiry", "created_at")}
            else:
                # Auto-create profile with defaults
                default_profile = dict(DEFAULT_CONFIG)
                default_profile["user_id"] = g.user_id
                default_profile["tier"] = "free"
                default_profile.setdefault("secondary_currency", "HKD")
                supabase_admin.table("profiles").insert(default_profile).execute()
                return default_profile
        except Exception:
            return dict(DEFAULT_CONFIG)
    return load_json_file(CONFIG_JSON, DEFAULT_CONFIG)

def save_config(data):
    if CLOUD_MODE and g.get("user_id"):
        try:
            row = {k: v for k, v in data.items() if k in DEFAULT_CONFIG or k == "secondary_currency"}
            row["user_id"] = g.user_id
            supabase_admin.table("profiles").upsert(row, on_conflict="user_id").execute()
        except Exception:
            pass
        return
    save_json_file(CONFIG_JSON, data)

def load_watchlist():
    if CLOUD_MODE and g.get("user_id"):
        try:
            resp = supabase_admin.table("watchlist").select("*").eq("user_id", g.user_id).order("sort_order").execute()
            cats = {}
            targets = {}
            for row in (resp.data or []):
                cat = row.get("category", "Default")
                tk = row["ticker"].upper()
                cats.setdefault(cat, []).append(tk)
                if row.get("target_price"):
                    targets[tk] = float(row["target_price"])
            return {"categories": cats, "targets": targets}
        except Exception:
            return {"categories": {}, "targets": {}}
    return load_json_file(WATCHLIST_JSON, {"categories": {}})

def save_watchlist(data):
    if CLOUD_MODE and g.get("user_id"):
        try:
            # Delete all rows for user, then batch insert
            supabase_admin.table("watchlist").delete().eq("user_id", g.user_id).execute()
            rows = []
            targets = data.get("targets", {})
            sort = 0
            for cat_name, tickers in data.get("categories", {}).items():
                for tk in tickers:
                    row = {"user_id": g.user_id, "category": cat_name,
                           "ticker": tk.upper(), "sort_order": sort}
                    if tk in targets:
                        row["target_price"] = targets[tk]
                    rows.append(row)
                    sort += 1
            if rows:
                supabase_admin.table("watchlist").insert(rows).execute()
        except Exception:
            pass
        return
    save_json_file(WATCHLIST_JSON, data)

def get_is_pro():
    """Return pro status: selfhosted uses IS_PRO flag, cloud uses g.tier."""
    if CLOUD_MODE:
        return g.get("tier", "free") == "pro"
    return IS_PRO

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

# ==================== 🎯 4. 路由控制 ====================

PUBLIC_PATHS = {"/", "/health", "/webhook", "/favicon.ico"}

@app.before_request
def cloud_auth():
    if not CLOUD_MODE:
        return
    g.user_id = None
    g.tier = "free"
    g.user_email = ""

    if request.path in PUBLIC_PATHS or request.path.startswith("/static"):
        return

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.cookies.get("sb-access-token")

    if not token:
        if request.path.startswith("/api/"):
            abort(401, description=jsonify({"error": "Unauthorized"}).get_data(as_text=True))
        return redirect("/")

    try:
        user_resp = supabase.auth.get_user(token)
        g.user_id = user_resp.user.id
        g.user_email = getattr(user_resp.user, "email", "")
    except Exception as e:
        err_msg = str(e).lower()
        if "expired" in err_msg:
            if request.path.startswith("/api/"):
                abort(401, description=jsonify({"error": "Token expired"}).get_data(as_text=True))
            return redirect("/")
        if request.path.startswith("/api/"):
            abort(401, description=jsonify({"error": "Invalid token"}).get_data(as_text=True))
        return redirect("/")

    try:
        profile = supabase_admin.table("profiles").select("tier").eq("user_id", g.user_id).single().execute()
        g.tier = profile.data.get("tier", "free") if profile.data else "free"
    except Exception:
        g.tier = "free"

@app.route('/')
def index():
    if CLOUD_MODE:
        # Return landing page for cloud mode (unauthenticated users)
        if not g.get("user_id"):
            try:
                return render_template_string(LANDING_TEMPLATE,
                    supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY,
                    version=VERSION)
            except Exception as e:
                import traceback
                return f"<pre>Landing Error:\n{traceback.format_exc()}</pre>", 500
        # Authenticated users go to dashboard
        return redirect("/dashboard")

    return redirect("/dashboard")

@app.route('/dashboard')
def dashboard():
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
    markets_status = {k: is_market_open(k) for k in MARKETS}
    is_pro = get_is_pro()

    from flask import Response

    # Load template from file (shared between selfhosted and cloud)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'dashboard.html'), 'r') as f:
        dashboard_template = f.read()

    return render_template_string(dashboard_template,
        t=t, stocks=stocks, open_tickers=open_tickers, ticker_market=ticker_market,
        total_mv_usd=total_mv_usd, total_open_cost=total_open_cost, total_pnl_usd=total_pnl_usd,
        total_roi_str=total_roi_str, usd_hkd=usd_hkd, sec_cur=sec_cur,
        watchlist_html=watchlist_html, targets_json=targets_json,
        markets_status=markets_status, active_markets=active_markets,
        version=VERSION, changelog=CHANGELOG, today_date=date_str,
        config=config, is_pro=is_pro,
        total_mv_usd_raw=total_mv_usd, total_open_cost_raw=total_open_cost,
        cash_balance=config.get("cash_balance", 0),
        CLOUD_MODE=CLOUD_MODE,
        supabase_url=SUPABASE_URL if CLOUD_MODE else "",
        supabase_key=SUPABASE_KEY if CLOUD_MODE else "",
        user_email=g.get("user_email", "") if CLOUD_MODE else "")

@app.route('/health')
def health():
    if CLOUD_MODE:
        return jsonify({"status": "ok", "cache_size": len(PRICE_CACHE)})
    return jsonify({"status": "ok"})

if CLOUD_MODE:
    @app.route('/api/checkout')
    def api_checkout():
        if not g.get("user_id"):
            return jsonify({"error": "Unauthorized"}), 401
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
                mode="subscription",
                success_url=request.host_url.rstrip("/") + "/dashboard?upgrade=success",
                cancel_url=request.host_url.rstrip("/") + "/dashboard?upgrade=cancelled",
                client_reference_id=g.user_id,
            )
            return jsonify({"url": session.url})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/webhook', methods=['POST'])
    def stripe_webhook():
        payload = request.get_data(as_text=True)
        sig_header = request.headers.get("Stripe-Signature")
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except Exception:
            return jsonify({"error": "Invalid signature"}), 400
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            user_id = session.get("client_reference_id")
            if user_id:
                try:
                    supabase_admin.table("profiles").upsert(
                        {"user_id": user_id, "tier": "pro"}, on_conflict="user_id"
                    ).execute()
                except Exception:
                    pass
        return jsonify({"status": "ok"})

    @app.route('/api/profile', methods=['GET'])
    def api_profile():
        if not g.get("user_id"):
            return jsonify({"error": "Unauthorized"}), 401
        return jsonify({"user_id": g.user_id, "email": g.user_email, "tier": g.tier})

    @app.route('/api/usage', methods=['GET'])
    def api_usage():
        if not CLOUD_MODE:
            return jsonify({"daily_limit": FREE_DAILY_LIMIT, "used": 0, "remaining": 999999})
        if not g.get("user_id"):
            return jsonify({"error": "Unauthorized"}), 401
        today = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d")
        try:
            resp = supabase_admin.table("usage_logs").select("id", count="exact") \
                .eq("user_id", g.user_id).gte("created_at", today).execute()
            used = resp.count or 0
        except Exception:
            used = 0
        return jsonify({
            "daily_limit": FREE_DAILY_LIMIT,
            "used": used,
            "remaining": max(0, FREE_DAILY_LIMIT - used)
        })

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

# ==================== Cloud Background Poller ====================
if CLOUD_MODE:
    from pulse_core.yfinance_client import start_background_poller

    def _get_all_user_tickers():
        tickers = set()
        try:
            pf = supabase_admin.table("portfolios").select("ticker").execute()
            for r in (pf.data or []):
                tickers.add(r["ticker"].upper())
        except Exception:
            pass
        try:
            wl = supabase_admin.table("watchlist").select("ticker").execute()
            for r in (wl.data or []):
                tickers.add(r["ticker"].upper())
        except Exception:
            pass
        return tickers

    start_background_poller(_get_all_user_tickers, interval=60)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)