import os
import json
import secrets
import sys
import requests
from requests.exceptions import Timeout, ConnectionError as ReqConnectionError
import time
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_from_directory
import yfinance as yf
import numpy as np

# 📉 Risk Metrics (Pro) — pure computation module (sibling file, no circular import)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from risk_metrics import (reconstruct_daily_values, compute_risk_metrics,
                          RISK_METHODS, RISK_PERIODS, RISK_LONGEST_DAYS)

app = Flask(__name__)

# ==================== 🎯 1. 基礎路徑與配置 ====================
# 用 PULSE_HOME 環境變數指向 data 目錄，未設定時 fallback 到 script 所在目錄
BASE_DIR = os.environ.get("PULSE_HOME", os.path.dirname(os.path.abspath(__file__)))

PORTFOLIO_JSON = os.path.join(BASE_DIR, "portfolio.json")
WATCHLIST_JSON = os.path.join(BASE_DIR, "watchlist.json")  
CONFIG_JSON = os.path.join(BASE_DIR, "system_config.json")

VERSION = "V1.14.0"
IS_PRO = False  # this public build is the Free edition; pulse_pro.py sets this to True (not in this repo)
CHANGELOG = [
    ("V1.14.0", "[Session 14] Risk Metrics card (Pro) — A+ transaction-aware daily value reconstruction (BUY/SELL × closes, cash-flow-adjusted returns, CLOSED excluded), 5 metrics (Sharpe/Sortino/vol/MaxDrawdown/VaR95), 3 methods (historical/parametric/Monte Carlo, numpy-vectorized), Settings tab (period 90–5y, method, paths 1000–10000), 6h cache + 3h warmer, 3-language i18n + tooltips, standalone validation script"),
    ("V1.13.0", "[Session 13] Earnings Calendar card — upcoming earnings dates for all portfolio tickers (OPEN+CLOSED positions), yfinance Ticker.calendar + earnings_dates fallback, 6h TTL cache, 30-day lookahead"),
    ("V1.12.2", "[Session 12] Compact index ticker in top bar (between market status/refresh); Settings max 5 hard limit, min 1 warning; clickable filter"),
    ("V1.12.1", "[Session 12] User-selected indices — all 13 selectable in Settings (min 5 hint, counter, empty-state notice); removed fixed defaults"),
    ("V1.12.0", "[Session 12] Indices & FX Dashboard — 5 live market indices (S&P/Hang Seng/Shanghai/TAIEX/TPEx), currency rates row, yfinance cached"),
    ("V1.11.3", "[Session 11] AJAX watchlist reload — add/delete/rename/reorder without page refresh + loading overlay"),
    ("V1.11.2", "[Session 11] Fix i18n: settings_tab_bg English, import/export description labels"),
    ("V1.11.1", "[Session 11] Custom background image upload + remove + opacity slider in separate Settings tab"),
    ("V1.10.17", "[Session 10] Add JPY/EUR/GBP to currency dropdowns + FX matrix"),
    ("V1.10.16", "[Session 10] Fix: avg_buy_price converted to primary currency, ATR tooltip on column header"),
    ("V1.10.15", "[Session 10] Fix: clear HIGHEST_PRICE_CACHE per-request to prevent cross-currency pollution"),
    ("V1.10.14", "[Session 10] Fix: ATR stop-loss now converted to primary currency (was raw native)"),
    ("V1.10.13", "[Session 10] Fix: Performance card historical prices now converted to primary currency"),
    ("V1.10.12", "[Session 10] Fix: FX cross-rate formula inverted, buy price label JS DOM timing, clean HKD/TWD symbols"),
    ("V1.10.11", "[Session 10] Multi-currency Phase 2: primary/secondary currency, market-native buy/sell labels, FX cross-rate matrix, all prices in primary currency"),
    ("V1.10.1", "[Session 10] Financial disclaimer banner on all pages"),
    ("V1.9.5", "[Session 9] Performance card: Today/WTD/MTD/YTD returns using historical prices"),
    ("V1.9.4", "[Session 9] Watchlist multi-market support, JSON import/export (watchlist + portfolio)"),
    ("V1.9.3", "[Session 9] Company names in ticker display, watchlist sidebar indicator, remove $ prefix"),
    ("V1.9.2", "[Session 9] Remove CLOUD_MODE — pure selfhosted Flask codebase"),
    ("V1.9.1", "[Session 9] CLOUD_MODE: Supabase auth, dark mode, logout, data layer dispatch"),
    ("V1.8.20", "[Session 8] 20 items: Editable prompt (3 levels), mode toggle, i18n rebuild, Weight%, Market Dist, Cash Ratio, API confirm, smart errors, settings tabs, timeout, modal, label a11y"),
    ("V1.8.1", "[Session 8] AI Audit: rich portfolio prompt + local inference presets (Ollama/vLLM/LM Studio)"),
    ("V1.7.16", "[Session 7] Remove Crucix macro report integration"),
    ("V1.7.15", "[Session 7] 15 fixes: PULSE_HOME, Free/Pro split, local CSS, form labels, JS escape, EUR/GBP FX"),
    ("V1.6.12", "[Session 6] 12 fixes: yfinance refactor, batch fetch, TTL cache, atomic write, TWO market, Pulse rebrand"),
    ("V1.5.1", "[Session 5] Initial release: multi-market, buy/sell, i18n, watchlist, multi-currency"),
]

CURRENCY_SYMBOLS = {"USD": "$", "HKD": "$", "TWD": "$", "CNY": "¥", "JPY": "¥", "EUR": "€", "GBP": "£"}
CURRENCY_MAP = {"USD": "USD=X", "HKD": "HKD=X", "TWD": "TWD=X", "CNY": "CNY=X", "JPY": "JPY=X", "EUR": "EUR=X", "GBP": "GBP=X"}
DEFAULT_CONFIG = {
    "api_key": "", "refresh_interval": 30, "language": "zh_tw", "bg_image": False, "bg_opacity": 0.55,
    "ai_provider": "gemini", "ai_model": "gemini-2.5-flash",
    "custom_api_url": "https://generativelanguage.googleapis.com/v1beta/models/",
    "primary_currency": "USD",
    "secondary_currency": "HKD",
    "ai_timeout": 60,
    "cash_balance": 0,
    "prompt_level": "balanced",
    "custom_prompt": "",
    "prompt_mode": "style",
    "extra_indices": [],
    "risk_period": 90,           # 90 | 120 | 180 | 365 | 0(=longest, 5y)
    "risk_method": "historical", # historical | parametric | montecarlo
    "risk_paths": 5000           # 1000–10000, Monte Carlo only
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
        "watchlist_title": "📋 自選股",
        "capital_recovered_badge": "💵 已收回本金",
        "capital_recovered_label": "已收回本金",
        "capital_recover_hint": "(待收回",
        "capital_recover_hint_end": "股)",
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
        "table_stop_loss_hint": "以20日平均真實波幅(ATR)的2倍計算移動止蝕價，股價跌破止蝕價時觸發警告",
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
        "settings_tab_bg": "背景圖",
        "settings_tab_ai": "AI 模型",
        "settings_tab_indices": "📊 指數",
        "settings_indices_hint": "選擇 1–5 個要顯示的指數，存檔後套用至市場概覽。（超過 5 個將無法勾選）",
        "settings_indices_selectable": "可選指數",
        "settings_indices_min": "最多 5 個",
        "index_none_compact": "未選指數 — 點此設定",
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
        "index_title": "🌍 市場概覽",
        "index_fx_label": "匯率",
        "index_none": "尚未選擇指數，請到 Settings → 📊 指數 勾選後儲存。",
        "index_none": "尚未選擇指數，請到 Settings → 📊 指數 勾選後儲存。",
        "perf_title": "📈 投資表現",
        "perf_today": "今日",
        "perf_wtd": "本週",
        "perf_mtd": "本月",
        "perf_ytd": "今年",
        "settings_cash_balance": "現金餘額",
        "settings_timeout_hint": "建議 30-120 秒",
        "settings_prompt_hint": "可用變數：{summary} {holdings} {alloc} {lang}。留空使用分析風格的預設 Prompt。",
        "changelog_title": "更新日誌",
        "settings_ai_provider": "AI Provider",
        "settings_model": "Model Name",
        "settings_api_url": "Custom API URL",
        "settings_api_key": "API Key",
        "settings_language": "介面語言",
        "settings_primary_currency": "主要貨幣",
        "settings_secondary_currency": "次要貨幣 (≈)",
        "settings_currency": "次要貨幣 (≈)",
        "settings_save": "儲存設定",
        "wl_add_cat": "+ 新增分組",
        "wl_delete_cat": "刪除組",
        "wl_input_placeholder": "輸入代碼",
        "wl_loading": "更新中...",
        "wl_new_cat_prompt": "新分組名稱",
        "wl_market_label": "市場",
        "export_btn": "📤 導出",
        "import_btn": "📥 導入",
        "import_preview": "導入預覽",
        "import_confirm": "確認導入",
        "import_watchlist": "自選股",
        "import_portfolio": "交易明細",
        "import_will_add": "將新增",
        "import_exists_skip": "已存在，跳過",
        "import_success": "導入成功",
        "export_select": "選擇導出內容",
        "import_export_desc": "導入/導出 交易明細及自選股",
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
        "audit_confirm": "將會使用你的 API Key 呼叫 AI 模型產生報告，確定要繼續嗎？",
        "disclaimer": "免責聲明：本應用程式僅供資訊記錄與教育參考，不構成任何財務、投資或法律建議。AI 分析為自動化生成，不應作為投資決策的唯一依據。",
        "bg_title": "背景圖",
        "bg_upload_btn": "上傳",
        "bg_remove_btn": "移除",
        "bg_invalid_format": "不支援的格式（僅限 jpg/png/gif/webp）",
        "bg_opacity": "覆蓋透明度",
        "earnings_title": "📅 財報日曆",
        "earnings_window_label": "未來{days}天",
        "earnings_ticker_header": "股票",
        "earnings_date_header": "財報日期",
        "earnings_countdown_label": "{n}天",
        "earnings_today": "今天",
        "earnings_no_data": "無即將到來的財報",
        "earnings_source_note": "數據來源 Yahoo Finance",
        "risk_card_title": "📉 風險指標",
        "risk_settings_tab": "📉 風險指標",
        "risk_settings_intro": "以交易日期重建每日持倉市值，計算三種風險模型：歷史模擬（直接取歷史報酬分位數）、參數法（假設常態分配）、Monte Carlo（亂數模擬路徑）。",
        "risk_period_label": "計算期間",
        "risk_period_90": "90 天",
        "risk_period_120": "120 天",
        "risk_period_180": "180 天",
        "risk_period_365": "365 天",
        "risk_period_longest": "最長 (最多 5 年)",
        "risk_method_label": "計算方法",
        "risk_method_historical": "歷史模擬",
        "risk_method_parametric": "參數法",
        "risk_method_montecarlo": "Monte Carlo",
        "risk_paths_label": "模擬路徑數",
        "risk_paths_hint": "路徑愈小計算速度快，反之愈大計算速度慢",
        "risk_sharpe": "Sharpe 比率",
        "risk_sharpe_hint": "每單位總風險（年化波動）所換取的超額報酬（無風險利率假設 0%）。愈高代表風險調整後報酬愈佳。",
        "risk_sortino": "Sortino 比率",
        "risk_sortino_hint": "與 Sharpe 類似，但只以「下跌波動」（負報酬）作為風險分母，只看下行風險。",
        "risk_volatility": "年化波動率",
        "risk_volatility_hint": "每日報酬標準差 × √252，衡量報酬的波動程度。數值愈高代表價格波動愈大。",
        "risk_max_drawdown": "最大回撤",
        "risk_max_drawdown_hint": "期間內從最高點回落的「最大幅度」（現金流調整後），代表歷史最差的下跌深度。",
        "risk_var": "VaR 95% (1日)",
        "risk_var_hint": "有 95% 信心，單日損失不會超過此金額。歷史模擬取歷史報酬第 5 百分位；參數法假設常態分配；Monte Carlo 以模擬路徑估算。",
        "risk_no_positions": "尚無未平倉持倉，無法計算風險指標",
        "risk_insufficient_data": "資料不足（需至少 2 個交易日）",
        "risk_source_note": "資料來源 Yahoo Finance · 現金流調整法 · 無風險利率 0%",
        "risk_pro_only_note": "風險指標僅在 Pro 版本可用。"
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
        "table_stop_loss_hint": "以20日平均真实波幅(ATR)的2倍计算移动止损价，股价跌破止损价时触发警告",
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
        "settings_tab_bg": "背景图",
        "settings_tab_ai": "AI 模型",
        "settings_tab_indices": "📊 指数",
        "settings_indices_hint": "选择 1–5 个要显示的指数，保存后套用至市场概览。（超过 5 个将无法勾选）",
        "settings_indices_selectable": "可选指数",
        "settings_indices_min": "最多 5 个",
        "index_none_compact": "未选指数 — 点此设定",
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
        "index_title": "🌍 市场概览",
        "index_fx_label": "汇率",
        "index_none": "尚未选择指数，请到 Settings → 📊 指数 勾选后保存。",
        "index_none": "尚未选择指数，请到 Settings → 📊 指数 勾选后保存。",
        "perf_title": "📈 投资表现",
        "perf_today": "今日",
        "perf_wtd": "本周",
        "perf_mtd": "本月",
        "perf_ytd": "今年",
        "settings_cash_balance": "现金余额",
        "settings_timeout_hint": "建议 30-120 秒",
        "settings_prompt_hint": "可用变数：{summary} {holdings} {alloc} {lang}。留空使用分析风格的预设 Prompt。",
        "changelog_title": "更新日志",
        "settings_ai_provider": "AI Provider",
        "settings_model": "Model Name",
        "settings_api_url": "Custom API URL",
        "settings_api_key": "API Key",
        "settings_language": "界面语言",
        "settings_primary_currency": "主要货币",
        "settings_secondary_currency": "次要货币 (≈)",
        "settings_currency": "次要货币 (≈)",
        "settings_save": "保存设定",
        "wl_add_cat": "+ 新增分组",
        "wl_delete_cat": "删除组",
        "wl_input_placeholder": "输入代码",
        "wl_loading": "更新中...",
        "wl_new_cat_prompt": "新分组名称",
        "wl_market_label": "市场",
        "export_btn": "📤 导出",
        "import_btn": "📥 导入",
        "import_preview": "导入预览",
        "import_confirm": "确认导入",
        "import_watchlist": "自选股",
        "import_portfolio": "交易明细",
        "import_will_add": "将新增",
        "import_exists_skip": "已存在，跳过",
        "import_success": "导入成功",
        "export_select": "选择导出内容",
        "import_export_desc": "导入/导出 交易明细及自选股",
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
        "audit_confirm": "将会使用你的 API Key 调用 AI 模型生成报告，确定要继续吗？",
        "disclaimer": "免责声明：本应用程序仅供信息记录与教育参考，不构成任何财务、投资或法律建议。AI 分析为自动化生成，不应作为投资决策的唯一依据。",
        "bg_title": "背景图",
        "bg_upload_btn": "上传",
        "bg_remove_btn": "移除",
        "bg_invalid_format": "不支持的格式（仅限 jpg/png/gif/webp）",
        "bg_opacity": "覆盖透明度",
        "earnings_title": "📅 财报日历",
        "earnings_window_label": "未来{days}天",
        "earnings_ticker_header": "股票",
        "earnings_date_header": "财报日期",
        "earnings_countdown_label": "{n}天",
        "earnings_today": "今天",
        "earnings_no_data": "无即将到来的财报",
        "earnings_source_note": "数据来源 Yahoo Finance",
        "risk_card_title": "📉 风险指标",
        "risk_settings_tab": "📉 风险指标",
        "risk_settings_intro": "以交易日期重建每日持仓市值，计算三种风险模型：历史模拟（直接取历史报酬分位数）、参数法（假设正态分布）、Monte Carlo（随机模拟路径）。",
        "risk_period_label": "计算期间",
        "risk_period_90": "90 天",
        "risk_period_120": "120 天",
        "risk_period_180": "180 天",
        "risk_period_365": "365 天",
        "risk_period_longest": "最长 (最多 5 年)",
        "risk_method_label": "计算方法",
        "risk_method_historical": "历史模拟",
        "risk_method_parametric": "参数法",
        "risk_method_montecarlo": "Monte Carlo",
        "risk_paths_label": "模拟路径数",
        "risk_paths_hint": "路径愈小计算速度快，反之愈大计算速度慢",
        "risk_sharpe": "Sharpe 比率",
        "risk_sharpe_hint": "每单位总风险（年化波动）所换取的超额报酬（无风险利率假设 0%）。愈高代表风险调整后报酬愈佳。",
        "risk_sortino": "Sortino 比率",
        "risk_sortino_hint": "与 Sharpe 类似，但只以「下跌波动」（负报酬）作为风险分母，只看下行风险。",
        "risk_volatility": "年化波动率",
        "risk_volatility_hint": "每日报酬标准差 × √252，衡量报酬的波动程度。数值愈高代表价格波动愈大。",
        "risk_max_drawdown": "最大回撤",
        "risk_max_drawdown_hint": "期间内从最高点回落的「最大幅度」（现金流调整后），代表历史最差的下跌深度。",
        "risk_var": "VaR 95% (1日)",
        "risk_var_hint": "有 95% 信心，单日损失不会超过此金额。历史模拟取历史报酬第 5 百分位；参数法假设正态分布；Monte Carlo 以模拟路径估算。",
        "risk_no_positions": "尚无未平仓持仓，无法计算风险指标",
        "risk_insufficient_data": "数据不足（需至少 2 个交易日）",
        "risk_source_note": "资料来源 Yahoo Finance · 现金流调整法 · 无风险利率 0%",
        "risk_pro_only_note": "风险指标仅在 Pro 版本可用。"
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
        "table_stop_loss_hint": "2x 20-period Average True Range (ATR) trailing stop. Warning triggered when price falls below stop-loss.",
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
        "settings_tab_bg": "Background",
        "settings_tab_ai": "AI Model",
        "settings_tab_indices": "📊 Indices",
        "settings_indices_hint": "Select 1–5 indices to display. Save to apply to the market overview. (Max 5 — others will be disabled)",
        "settings_indices_selectable": "Selectable Indices",
        "settings_indices_min": "max 5",
        "index_none_compact": "No indices — click to set",
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
        "index_title": "🌍 Market Overview",
        "index_fx_label": "FX",
        "index_none": "No indices selected. Go to Settings → 📊 Indices to choose and save.",
        "index_none": "No indices selected. Go to Settings → 📊 Indices to choose and save.",
        "perf_title": "📈 Performance",
        "perf_today": "Today",
        "perf_wtd": "WTD",
        "perf_mtd": "MTD",
        "perf_ytd": "YTD",
        "settings_cash_balance": "Cash Balance",
        "settings_timeout_hint": "Recommend 30-120 sec",
        "settings_prompt_hint": "Variables: {summary} {holdings} {alloc} {lang}. Leave empty to use Analysis Style preset.",
        "changelog_title": "Changelog",
        "settings_ai_provider": "AI Provider",
        "settings_model": "Model Name",
        "settings_api_url": "Custom API URL",
        "settings_api_key": "API Key",
        "settings_language": "Language",
        "settings_primary_currency": "Primary Currency",
        "settings_secondary_currency": "Secondary (≈)",
        "settings_currency": "Secondary (≈)",
        "settings_save": "Save Settings",
        "wl_add_cat": "+ Add Group",
        "wl_delete_cat": "Delete Group",
        "wl_input_placeholder": "Enter ticker",
        "wl_loading": "Updating...",
        "wl_new_cat_prompt": "New group name",
        "wl_market_label": "Market",
        "export_btn": "📤 Export",
        "import_btn": "📥 Import",
        "import_preview": "Import Preview",
        "import_confirm": "Confirm Import",
        "import_watchlist": "Watchlist",
        "import_portfolio": "Portfolio",
        "import_will_add": "Will add",
        "import_exists_skip": "Exists, skip",
        "import_success": "Import successful",
        "export_select": "Select export data",
        "import_export_desc": "Import/Export Portfolio & Watchlist",
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
        "audit_confirm": "This will use your API key to call the AI model. Continue?",
        "disclaimer": "Disclaimer: This application is for informational and educational purposes only. It does not constitute financial, investment, or legal advice. AI analysis is automated and should not be the sole basis for investment decisions.",
        "bg_title": "Background",
        "bg_upload_btn": "Upload",
        "bg_remove_btn": "Remove",
        "bg_invalid_format": "Unsupported format (jpg/png/gif/webp only)",
        "bg_opacity": "Overlay Opacity",
        "earnings_title": "📅 Earnings Calendar",
        "earnings_window_label": "Next {days} days",
        "earnings_ticker_header": "Ticker",
        "earnings_date_header": "Earnings Date",
        "earnings_countdown_label": "{n} days",
        "earnings_today": "Today",
        "earnings_no_data": "No upcoming earnings",
        "earnings_source_note": "Data from Yahoo Finance",
        "risk_card_title": "📉 Risk Metrics",
        "risk_settings_tab": "📉 Risk Metrics",
        "risk_settings_intro": "Rebuilds daily portfolio value from transaction dates and computes three risk models: Historical Simulation (empirical return quantiles), Parametric (assumes normal distribution), Monte Carlo (simulated random paths).",
        "risk_period_label": "Lookback period",
        "risk_period_90": "90 days",
        "risk_period_120": "120 days",
        "risk_period_180": "180 days",
        "risk_period_365": "365 days",
        "risk_period_longest": "Longest (up to 5 years)",
        "risk_method_label": "Method",
        "risk_method_historical": "Historical Simulation",
        "risk_method_parametric": "Parametric",
        "risk_method_montecarlo": "Monte Carlo",
        "risk_paths_label": "Path count",
        "risk_paths_hint": "Fewer paths compute faster; more paths compute slower",
        "risk_sharpe": "Sharpe Ratio",
        "risk_sharpe_hint": "Excess return per unit of total risk (annualized volatility), assuming a 0% risk-free rate. Higher is better.",
        "risk_sortino": "Sortino Ratio",
        "risk_sortino_hint": "Like Sharpe, but penalizes only downside volatility (negative returns).",
        "risk_volatility": "Ann. Volatility",
        "risk_volatility_hint": "Daily return standard deviation × √252. Higher means larger price swings.",
        "risk_max_drawdown": "Max Drawdown",
        "risk_max_drawdown_hint": "Largest peak-to-trough decline (cash-flow adjusted) over the period — the worst historical drop.",
        "risk_var": "VaR 95% (1-day)",
        "risk_var_hint": "95% confidence that the one-day loss will not exceed this amount. Historical uses the 5th percentile of returns; Parametric assumes a normal distribution; Monte Carlo estimates from simulated paths.",
        "risk_no_positions": "No open positions — risk metrics unavailable",
        "risk_insufficient_data": "Insufficient data (need ≥ 2 trading days)",
        "risk_source_note": "Data: Yahoo Finance · cash-flow adjusted · 0% risk-free rate",
        "risk_pro_only_note": "Risk Metrics is a Pro feature."
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
    """Load portfolio transactions from JSON."""
    return load_json_file(PORTFOLIO_JSON, [])

def save_portfolio(data):
    """Save portfolio transactions to JSON."""
    save_json_file(PORTFOLIO_JSON, data)
def load_watchlist():
    """Load watchlist from JSON."""
    return load_json_file(WATCHLIST_JSON, {"categories": {}})

def save_watchlist(data):
    """Save watchlist to JSON."""
    save_json_file(WATCHLIST_JSON, data)
def load_config():
    """Load user config from JSON."""
    return load_json_file(CONFIG_JSON, DEFAULT_CONFIG)

def save_config(data):
    """Save user config to JSON."""
    save_json_file(CONFIG_JSON, data)

# ==================== 🎯 2. 數據抓取與工具 (yfinance) ====================
ATR_CACHE = {}
HIGHEST_PRICE_CACHE = {}
PRICE_CACHE = {}
PRICE_CACHE_TTL = 30          # seconds — active trading hours
PRICE_CACHE_TTL_IDLE = 14400  # seconds (4h) — all markets closed
COMPANY_NAMES = {}             # ticker → company name cache

def get_effective_ttl():
    """Return short TTL during trading hours, long TTL when all markets closed."""
    return PRICE_CACHE_TTL if check_any_market_active() else PRICE_CACHE_TTL_IDLE

def get_historical_prices(tickers, dates):
    """Fetch historical close prices using yfinance Ticker.history().
    Returns {ticker: {label: price_or_None}}."""
    if not tickers: return {}
    result = {t: {} for t in tickers}
    from datetime import timedelta as td
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            min_dt = datetime.strptime(min(d[1] for d in dates), '%Y-%m-%d') - td(days=5)
            hist = t.history(start=min_dt.strftime('%Y-%m-%d'), period='max')
            if hist.empty: continue
            for label, date_str in dates:
                target = datetime.strptime(date_str, '%Y-%m-%d')
                for _ in range(5):
                    ds = target.strftime('%Y-%m-%d')
                    if ds in hist.index.strftime('%Y-%m-%d'):
                        val = hist.loc[ds, 'Close']
                        result[ticker][label] = float(val)
                        break
                    target -= td(days=1)
        except Exception:
            pass
    return result


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

def get_company_name(ticker):
    """Fetch company name from yfinance, with cache."""
    tk = ticker.upper()
    if tk in COMPANY_NAMES:
        return COMPANY_NAMES[tk]
    try:
        t = yf.Ticker(ticker)
        info = t.info
        name = info.get('shortName') or info.get('longName') or ''
        COMPANY_NAMES[tk] = name
        return name
    except Exception:
        COMPANY_NAMES[tk] = ''
        return ''


# ==================== 📅 財報日曆 (Earnings Calendar) ====================
EARNINGS_LOOKAHEAD_DAYS = 30
EARNINGS_CACHE_TTL = 21600     # 6 hours in seconds
_earnings_cache = {}           # ticker -> (earnings_date, cached_at_ts)

def _parse_earnings_date(value):
    """Normalize a yfinance earnings-date value to datetime.date (or None).
    Handles: datetime.date, datetime, pandas Timestamp, list/tuple (take first), ISO string."""
    if value is None:
        return None
    # datetime.date / datetime.datetime / pandas Timestamp all expose year/month/day;
    # plain datetime.date has NO .date() method (only datetime does), so return as-is.
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value
    # list/tuple -> recurse on first element
    if isinstance(value, (list, tuple)) and value:
        return _parse_earnings_date(value[0])
    # string -> ISO parse
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except Exception:
                continue
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
        except Exception:
            return None
    return None

def _get_next_earnings_date(ticker):
    """Next upcoming earnings date (datetime.date) for ticker, or None."""
    tk = ticker.upper()
    now = datetime.now()
    cached = _earnings_cache.get(tk)
    if cached and (now - cached[1]).total_seconds() < EARNINGS_CACHE_TTL:
        return cached[0]
    result = None
    try:
        cal = yf.Ticker(ticker).calendar
        if isinstance(cal, dict):
            ed = _parse_earnings_date(cal.get('Earnings Date'))
            if ed is not None and ed >= now.date():
                result = ed
    except Exception:
        pass
    if result is None:
        try:
            edates = yf.Ticker(ticker).earnings_dates
            if edates is not None and not edates.empty:
                future = sorted(d for d in edates.index if d.date() >= now.date())
                if future:
                    result = future[0].date()
        except Exception:
            pass
    if result is not None:
        _earnings_cache[tk] = (result, datetime.now())
    return result

def get_earnings_calendar(tickers):
    """Return sorted list of (ticker, 'YYYY-MM-DD', days_until) for upcoming earnings."""
    if not tickers:
        return []
    today = datetime.now().date()
    cutoff = today + timedelta(days=EARNINGS_LOOKAHEAD_DAYS)
    rows = []
    for ticker in sorted({t.upper() for t in tickers if t and str(t).strip()}):
        ed = _get_next_earnings_date(ticker)
        if ed is None:
            continue
        if today <= ed <= cutoff:
            rows.append((ticker, ed.strftime('%Y-%m-%d'), (ed - today).days))
    rows.sort(key=lambda r: r[1])
    return rows


# ==================== 📉 風險指標 (Risk Metrics, Pro) ====================
RISK_CACHE_TTL = 21600      # 6h — mirrors EARNINGS_CACHE_TTL
RISK_WARMER_INTERVAL = 10800  # 3h background re-warm (half TTL)
_risk_cache = {}            # signature -> (metrics_dict, computed_at_ts)
_risk_cache_lock = threading.Lock()
_risk_warmer_thread = None

def _risk_cache_signature(ledger_key, period_days, method, paths):
    """Cache key = (open-position identity+share ledger, period, method, paths).
    ledger_key = tuple(sorted((ticker, type, date, shares)) for every tx of every OPEN ticker)."""
    return (ledger_key, period_days, method, paths)

def _invalidate_risk_cache():
    with _risk_cache_lock:
        _risk_cache.clear()

def _start_risk_warmer():
    """Daemon thread: recompute now, then every RISK_WARMER_INTERVAL. No-op in Free tier."""
    global _risk_warmer_thread
    if not get_is_pro():
        return
    if _risk_warmer_thread and _risk_warmer_thread.is_alive():
        return
    def _loop():
        while True:
            try:
                with _risk_cache_lock:
                    _risk_cache.clear()
                get_risk_metrics()   # recompute + repopulate (never raises)
            except Exception:
                pass
            time.sleep(RISK_WARMER_INTERVAL)
    _risk_warmer_thread = threading.Thread(target=_loop, daemon=True)
    _risk_warmer_thread.start()

def get_risk_metrics():
    """Cached entry point used by _render_dashboard (Pro only). Never raises.
    Fresh (<6h) → cached; expired → recompute synchronously; yfinance failure → serve
    expired cache with stale=True, else {'status':'error'} (spec §6.4, §11.12)."""
    if not get_is_pro():
        return None
    try:
        config = load_config()
        portfolio = load_portfolio()
        prim_cur = config.get("primary_currency", "USD")
        fx_matrix = get_fx_matrix()
        period_days = config.get("risk_period", 90)
        if period_days not in RISK_PERIODS: period_days = 90
        method = config.get("risk_method", "historical")
        if method not in RISK_METHODS: method = "historical"
        paths = max(1000, min(10000, int(config.get("risk_paths", 5000) or 5000)))
        # OPEN-only ledger key (no price fetch needed to decide openness)
        agg = {}
        for tx in portfolio:
            agg.setdefault(tx["ticker"].upper(), []).append(
                (tx.get("type"), tx.get("date"), float(tx.get("shares", 0) or 0)))
        ledger_key = tuple(sorted((tk, t, d, s)
            for tk, txs in agg.items()
            if sum(s for t, d, s in txs if t == "BUY") > sum(s for t, d, s in txs if t == "SELL")
            for t, d, s in txs))
        sig = _risk_cache_signature(ledger_key, period_days, method, paths)
        with _risk_cache_lock:
            cached = _risk_cache.get(sig)
            if cached and (datetime.now() - cached[1]).total_seconds() < RISK_CACHE_TTL:
                return cached[0]
        # Recompute (outside lock so renders don't serialize)
        dates, values, cashflows = reconstruct_daily_values(
            portfolio, period_days, fx_matrix, prim_cur)
        metrics = compute_risk_metrics(dates, values, cashflows, method, paths,
                                       prim_symbol=get_currency_symbol(prim_cur))
        if metrics.get("status") != "ok":
            return metrics   # no_positions / insufficient — not cached
        result = dict(metrics)
        with _risk_cache_lock:
            _risk_cache[sig] = (result, datetime.now())
        return result
    except Exception:
        # Stale-but-served fallback: expired cache → stale=True; else error state
        with _risk_cache_lock:
            for sig, (data, ts) in _risk_cache.items():
                return dict(data, stale=True)
        return {"status": "error"}


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

# ==================== 💱 FX Matrix (Multi-Currency) ====================
FX_CACHE = {}        # currency → {rate, ts}
FX_CACHE_TTL = 300   # 5 minutes

# ==================== 📊 指數與匯率儀表板 ====================
INDEX_CACHE = {}      # ticker → {price, prev_close, ts}
INDEX_CACHE_TTL = 300 # 5 minutes

INDEX_LIST = {
    # ── 預設：每個市場的代表指數 ──
    "US":  {"ticker": "^GSPC", "name_en": "S&P 500", "name_zh_tw": "標普500", "name_zh_cn": "标普500", "market": "US", "default": True},
    "HK":  {"ticker": "^HSI", "name_en": "Hang Seng", "name_zh_tw": "恆生指數", "name_zh_cn": "恒生指数", "market": "HK", "default": True},
    "CN":  {"ticker": "000001.SS", "name_en": "Shanghai", "name_zh_tw": "上證指數", "name_zh_cn": "上证指数", "market": "CN", "default": True},
    "TW":  {"ticker": "^TWII", "name_en": "TAIEX", "name_zh_tw": "加權指數", "name_zh_cn": "加权指数", "market": "TW", "default": True},
    "TWO": {"ticker": "^TWOII", "name_en": "TPEx", "name_zh_tw": "櫃買指數", "name_zh_cn": "柜买指数", "market": "TWO", "default": True},
    # ── 進階指數（用戶可在 Settings 勾選加掛）──
    "ADV_US_NQ":  {"ticker": "^IXIC", "name_en": "NASDAQ", "name_zh_tw": "納斯達克", "name_zh_cn": "纳斯达克", "market": "US"},
    "ADV_US_DJI": {"ticker": "^DJI", "name_en": "Dow Jones", "name_zh_tw": "道瓊工業", "name_zh_cn": "道琼斯工业", "market": "US"},
    "ADV_US_SOX": {"ticker": "^SOX", "name_en": "Philadelphia SE", "name_zh_tw": "費城半導體", "name_zh_cn": "费城半导体", "market": "US"},
    "ADV_HK_HSCEI": {"ticker": "^HSCE", "name_en": "HSCEI", "name_zh_tw": "國企指數", "name_zh_cn": "国企指数", "market": "HK"},
    "ADV_HK_TECH":  {"ticker": "^HSTECH", "name_en": "Hang Seng TECH", "name_zh_tw": "恒生科技", "name_zh_cn": "恒生科技", "market": "HK"},
    "ADV_CN_300":  {"ticker": "000300.SS", "name_en": "CSI 300", "name_zh_tw": "滬深300", "name_zh_cn": "沪深300", "market": "CN"},
    "ADV_CN_GEB":  {"ticker": "399006.SZ", "name_en": "ChiNext", "name_zh_tw": "創業板", "name_zh_cn": "创业板", "market": "CN"},
    "ADV_TW_TEC":  {"ticker": "^TEC.TW", "name_en": "TSEC Electronic", "name_zh_tw": "電子指數", "name_zh_cn": "电子指数", "market": "TW"},
}

def get_active_indices(config=None):
    """Return user-selected index entries.  V1.12.1+: fully user-driven.
    If config has no 'extra_indices' key (pre-V1.12.1 upgrade), fall back to the
    5 market representatives so the dashboard isn't empty on first load.
    Once the user saves Settings → Indices, the field is set and full control
    shifts to the user — zero selected means zero displayed.
    """
    if config is None:
        config = {}
    if "extra_indices" not in config:
        # Smooth migration: preserve current 5 defaults until user saves
        config["extra_indices"] = [k for k, v in INDEX_LIST.items() if v.get("default")]
    selected = [INDEX_LIST[k] for k in config["extra_indices"] if k in INDEX_LIST]
    # Sort by market order: US, HK, CN, TW, TWO
    market_order = {"US": 0, "HK": 1, "CN": 2, "TW": 3, "TWO": 4}
    return sorted(selected, key=lambda x: market_order.get(x["market"], 99))

def fetch_index_data(ticker):
    """Return dict with price, prev_close, change_pct for an index ticker. Cached."""
    now = datetime.now()
    cached = INDEX_CACHE.get(ticker)
    if cached and (now - cached["ts"]).total_seconds() < INDEX_CACHE_TTL:
        return {"price": cached["price"], "prev_close": cached["prev_close"],
                "change_pct": cached.get("change_pct", 0), "stale": False}
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = getattr(info, 'last_price', None) or getattr(info, 'regular_market_price', None) or 0
        prev = getattr(info, 'regular_market_previous_close', None) or getattr(info, 'previous_close', None) or 0
        pct = ((price - prev) / prev * 100) if prev > 0 else 0
        result = {"price": float(price), "prev_close": float(prev), "change_pct": round(pct, 2), "stale": False}
        INDEX_CACHE[ticker] = {"price": result["price"], "prev_close": result["prev_close"],
                                "change_pct": result["change_pct"], "ts": now}
        return result
    except Exception:
        # Return cached data if available (stale), else empty
        if ticker in INDEX_CACHE:
            c2 = INDEX_CACHE[ticker]
            return {"price": c2["price"], "prev_close": c2["prev_close"],
                    "change_pct": c2.get("change_pct", 0), "stale": True}
        return {"price": 0, "prev_close": 0, "change_pct": 0, "stale": True}

def get_all_index_data(config=None):
    """Return list of dicts for all active indices with live data."""
    indices = get_active_indices(config)
    result = []
    for idx in indices:
        data = fetch_index_data(idx["ticker"])
        data["key"] = idx.get("default") and idx.get("market", "") or list(INDEX_LIST.keys())[list(INDEX_LIST.values()).index(idx)] if idx in INDEX_LIST.values() else ""
        data["name_en"] = idx["name_en"]
        data["name_zh_tw"] = idx["name_zh_tw"]
        data["name_zh_cn"] = idx["name_zh_cn"]
        data["market"] = idx["market"]
        data["ticker"] = idx["ticker"]
        result.append(data)
    return result

def get_fx_rate(currency):
    """Get USD→currency rate. Returns float or None."""
    if currency == "USD":
        return 1.0
    now = datetime.now()
    cached = FX_CACHE.get(currency)
    if cached and (now - cached["ts"]).total_seconds() < FX_CACHE_TTL:
        return cached["rate"]
    try:
        ticker = CURRENCY_MAP.get(currency, f"{currency}=X")
        t = yf.Ticker(ticker)
        info = t.fast_info
        rate = getattr(info, 'last_price', None) or getattr(info, 'regular_market_previous_close', None) or 0.0
        if rate and rate > 0:
            FX_CACHE[currency] = {"rate": float(rate), "ts": now}
            return float(rate)
    except Exception:
        pass
    # Fallback: try old realtime method
    rt = get_realtime_data(f"{currency}=X")
    if rt['price'] > 0:
        FX_CACHE[currency] = {"rate": rt['price'], "ts": now}
        return rt['price']
    return None

def get_fx_matrix():
    """Build 4x4 cross-rate dict: {from_cur: {to_cur: rate}}."""
    currencies = ["USD", "HKD", "TWD", "CNY", "JPY", "EUR", "GBP"]
    # Get USD→X rates
    rates = {}
    for cur in currencies:
        r = get_fx_rate(cur)
        if r and r > 0:
            rates[cur] = r
    # Fallback defaults
    defaults = {"HKD": 7.80, "TWD": 32.5, "CNY": 7.25, "USD": 1.0, "JPY": 150.0, "EUR": 0.92, "GBP": 0.79}
    for cur in currencies:
        if cur not in rates:
            rates[cur] = defaults.get(cur, 1.0)
    # Build cross matrix
    matrix = {"rates": rates}
    for src in currencies:
        matrix[src] = {}
        for dst in currencies:
            if rates[dst] > 0:
                matrix[src][dst] = rates[dst] / rates[src]
    return matrix

def convert_currency(amount, from_cur, to_cur, fx_matrix=None):
    """Convert amount between currencies. Returns float."""
    if from_cur == to_cur:
        return float(amount)
    if fx_matrix is None:
        fx_matrix = get_fx_matrix()
    rate = fx_matrix.get(from_cur, {}).get(to_cur, 1.0)
    return float(amount) * rate

def get_market_native_currency(market):
    """Return native currency for a market."""
    MAP = {"US": "USD", "HK": "HKD", "CN": "CNY", "TW": "TWD", "TWO": "TWD"}
    return MAP.get(market, "USD")

def get_currency_symbol(cur):
    """Return symbol for a currency code."""
    return CURRENCY_SYMBOLS.get(cur, "$")

def get_usd_hkd_rate():
    """Legacy — returns USD→HKD rate (deprecated, use get_fx_rate)."""
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
    # Clear cross-request caches to prevent currency pollution
    HIGHEST_PRICE_CACHE.clear()
    prim_cur = config.get("primary_currency", "USD")
    sec_cur = config.get("secondary_currency", "HKD")
    fx_matrix = get_fx_matrix()
    prim_symbol = get_currency_symbol(prim_cur)
    sec_symbol = get_currency_symbol(sec_cur)
    prim_to_sec = fx_matrix.get(prim_cur, {}).get(sec_cur, 1.0)
    if sec_cur in ("EUR", "GBP"):
        prim_to_sec = 1.0 / prim_to_sec if prim_to_sec > 0 else 1.0
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
    total_market_value_primary = total_open_cost_primary = 0.0

    # Batch fetch all prices in ONE yfinance call (massive reduction in API requests)
    all_tickers = list(aggregated.keys())
    batch_prices = _batch_fetch_prices(all_tickers) if all_tickers else {}

    for ticker, data in aggregated.items():
        # 按日期排序各股票內部的明細
        data['history_txs'].sort(key=lambda x: x['date'])
        mkt = data['history_txs'][0].get('market') or 'US'
        native_cur = get_market_native_currency(mkt)
        # Conversion rate: yfinance native price → primary currency
        native_to_prim = fx_matrix.get(native_cur, {}).get(prim_cur, 1.0)

        total_buy_shares = sum(float(x['shares']) for x in data['buys'])
        total_buy_spend = sum(float(x['shares']) * float(x['price']) + float(x['commission']) for x in data['buys'])
        total_sell_shares = sum(float(x['shares']) for x in data['sells'])
        total_sell_proceeds = sum(float(x['shares']) * float(x['price']) - float(x['commission']) for x in data['sells'])

        current_shares = max(0.0, total_buy_shares - total_sell_shares)
        avg_buy_price = (total_buy_spend / total_buy_shares) if total_buy_shares > 0 else 0.0
        # Convert stored prices (market-native) → primary currency
        avg_buy_price = avg_buy_price * native_to_prim
        current_open_cost = current_shares * avg_buy_price

        # Batch-fetched prices include TTL cache hits + fresh yfinance data
        bp = batch_prices.get(ticker, {})
        current_price_native = bp.get('price', 0.0) if bp.get('price', 0.0) > 0 else 0.0
        prev_close_native = bp.get('prev_close', 0.0)
        if current_price_native <= 0:
            # Last resort: individual cache/API fallback
            rt_data = get_realtime_data(ticker)
            current_price_native, prev_close_native = rt_data['price'], rt_data['prev_close']
        # Convert yfinance native prices → primary currency
        current_price = current_price_native * native_to_prim
        prev_close = prev_close_native * native_to_prim
        day_change = current_price - prev_close
        day_change_pct = (day_change / prev_close * 100) if prev_close > 0 else 0
        current_mv = current_shares * current_price
        pnl_primary = current_mv - current_open_cost if current_shares > 0 else 0.0
        roi = (pnl_primary / current_open_cost) * 100 if current_open_cost > 0 else 0.0
        
        # 本金收回追蹤
        capital_recovered_flag = (total_sell_proceeds >= total_buy_spend) and (total_buy_spend > 0)
        shares_to_sell_to_recover = 0.0
        if current_shares > 0 and not capital_recovered_flag:
            remaining_cost = total_buy_spend - total_sell_proceeds
            if current_price > 0:
                shares_to_sell_to_recover = min(remaining_cost / current_price, current_shares)

        if current_shares > 0:
            total_market_value_primary += current_mv
            total_open_cost_primary += current_open_cost
            open_tickers_set.add(ticker)
            ticker_market[ticker] = mkt
            status = "OPEN"
            atr_20 = fetch_atr_20(ticker) * native_to_prim
            HIGHEST_PRICE_CACHE[ticker] = max(HIGHEST_PRICE_CACHE.get(ticker, current_price), current_price, avg_buy_price)
            stop_loss = HIGHEST_PRICE_CACHE[ticker] - (2.0 * atr_20)
            is_danger = (current_price <= stop_loss) and (atr_20 > 0)
        else:
            status, atr_20, stop_loss, is_danger = "CLOSED", 0, 0, False
            
        processed_holdings.append({
            'ticker': ticker, 'status': status, 'total_shares': f"{int(current_shares)}", 'avg_buy_price': f"{avg_buy_price:,.2f}", 'current_price': f"{current_price:,.2f}",
            'day_change': day_change, 'day_change_pct': day_change_pct, 'stop_loss': stop_loss, 'atr_20': atr_20, 'is_danger': is_danger, 'current_mv': f"{current_mv:,.2f}" if current_shares > 0 else '-', 'current_mv_raw': current_mv,
            'pnl_primary_str': f"{pnl_primary:+,.2f}" if current_shares > 0 else '-', 'pnl_sec_str': f"{(pnl_primary * prim_to_sec):+,.2f}" if current_shares > 0 else '-', 'roi_str': f"{roi:+.2f}%" if current_shares > 0 else '-',
            'market': mkt,
            'praw': pnl_primary,
            'capital_recovered': capital_recovered_flag,
            'capital_recovered_str': f"{total_sell_proceeds:,.2f}" if total_sell_proceeds > 0 else '-',
            'shares_to_sell_to_recover': f"{shares_to_sell_to_recover:.1f}",
            'history_txs': data['history_txs']  # 🌟 該股票專屬的流水帳明細
        })
    # Sort by market: US first, then HK, CN, TW
    market_order = {"US": 0, "HK": 1, "CN": 2, "TW": 3, "TWO": 4}
    processed_holdings.sort(key=lambda s: (market_order.get(s.get('market', 'US'), 99), s['ticker']))
    open_tickers_sorted = sorted(open_tickers_set, key=lambda t: (market_order.get(ticker_market.get(t, "US"), 99), t))
    return processed_holdings, open_tickers_sorted, ticker_market, total_market_value_primary, total_open_cost_primary, prim_cur, prim_symbol, sec_cur, sec_symbol, prim_to_sec, fx_matrix

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
                <select id="wl-market-{cat_name}" class="bg-slate-900 border border-slate-800 text-[10px] p-1 rounded text-slate-400">
                    <option value="US">US</option>
                    <option value="HK">HK</option>
                    <option value="CN">CN</option>
                    <option value="TW">TW</option>
                </select>
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
            if get_is_pro():
                if target_price:
                    target_html = '<span id="wl-target-' + tk + '"><button onclick="deleteTarget(\'' + tk + '\')" class="text-[9px] text-amber-400 hover:text-rose-400 font-mono" title="刪除目標價">🎯$' + f'{target_price:.2f}' + ' ✕</button></span>'
                else:
                    target_html = '<span id="wl-target-' + tk + '"><button onclick="setTarget(\'' + tk + '\')" class="text-[9px] text-slate-600 hover:text-amber-400 font-mono" title="' + target_btn + '">' + target_btn + '</button></span>'
            else:
                target_html = ''
            html += f"""
            <div class="flex justify-between items-center p-1.5 rounded bg-slate-900/40 hover:bg-slate-900/90 transition-colors text-xs">
                <div class="flex items-center gap-1">
                    <span class="font-bold font-mono text-slate-300">{tk}</span>
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

def get_is_pro():
    """Return True if user has Pro features (IS_PRO module flag)."""
    return IS_PRO


# ==================== 🎯 4. 路由控制 ====================
def _render_dashboard(is_mobile=False):
    """Render the Pulse dashboard — shared between selfhosted index() and cloud /dashboard."""
    config = load_config()
    if "primary_currency" not in config:
        config["primary_currency"] = "USD"
    if "secondary_currency" not in config:
        config["secondary_currency"] = "HKD"
    t = get_translations(config.get("language", "zh_tw"))
    stocks, open_tickers, ticker_market, total_mv_primary, total_open_cost, prim_cur, prim_symbol, sec_cur, sec_symbol, prim_to_sec, fx_matrix = calculate_portfolio_matrix()
    active_markets = set(ticker_market.values())
    # Add company names (yfinance, cached)
    for s in stocks:
        s["company_name"] = get_company_name(s["ticker"])
    watchlist_html = build_watchlist_html(t)
    wl_data = load_watchlist()
    targets_json = wl_data.get("targets", {})
    total_pnl_primary = total_mv_primary - total_open_cost
    total_roi = (total_pnl_primary / total_open_cost) * 100 if total_open_cost > 0 else 0.0
    total_roi_str = f"{total_roi:+.2f}%"
    
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Performance: today, WTD, MTD, YTD
    today = datetime.now()
    yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')
    # WTD: Monday of current week
    wtd_date = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
    # MTD: 1st of current month
    mtd_date = today.strftime('%Y-%m-01')
    # YTD: Jan 1
    ytd_date = today.strftime('%Y-01-01')

    perf_tickers = list(open_tickers)
    perf_dates = [('yesterday', yesterday), ('wtd', wtd_date), ('mtd', mtd_date), ('ytd', ytd_date)]
    hist_prices = get_historical_prices(perf_tickers, perf_dates) if perf_tickers else {}

    perf = {}
    for label in ['today', 'wtd', 'mtd', 'ytd']:
        perf[label] = {'mv': 0, 'pct': 0}
    today_mv = total_mv_primary
    yesterday_mv = wtd_mv = mtd_mv = ytd_mv = 0
    for s in stocks:
        tk = s['ticker']
        shares = s.get('total_shares_raw', s.get('total_shares', 0))
        if isinstance(shares, str):
            shares = float(shares.replace(',', ''))
        # Convert historical prices from market-native to primary currency
        mkt = s.get('market', 'US')
        native_cur = get_market_native_currency(mkt)
        native_to_prim = fx_matrix.get(native_cur, {}).get(prim_cur, 1.0)
        for label, date_str in [('yesterday', yesterday), ('wtd', wtd_date), ('mtd', mtd_date), ('ytd', ytd_date)]:
            hp = hist_prices.get(tk, {}).get(label)
            if hp:
                mv_contrib = hp * native_to_prim * float(shares)
                if label == 'yesterday': yesterday_mv += mv_contrib
                elif label == 'wtd': wtd_mv += mv_contrib
                elif label == 'mtd': mtd_mv += mv_contrib
                elif label == 'ytd': ytd_mv += mv_contrib
    # Today = (current MV - yesterday MV) / yesterday MV
    perf['today'] = {'mv': today_mv, 'pct': (today_mv - yesterday_mv) / yesterday_mv * 100 if yesterday_mv > 0 else 0}
    perf['wtd'] = {'mv': today_mv, 'pct': (today_mv - wtd_mv) / wtd_mv * 100 if wtd_mv > 0 else 0}
    perf['mtd'] = {'mv': today_mv, 'pct': (today_mv - mtd_mv) / mtd_mv * 100 if mtd_mv > 0 else 0}
    perf['ytd'] = {'mv': today_mv, 'pct': (today_mv - ytd_mv) / ytd_mv * 100 if ytd_mv > 0 else 0}

    is_active = check_us_market_active_hours()
    markets_status = {k: is_market_open(k) for k in MARKETS}
    is_pro = get_is_pro()

    # 📅 Earnings Calendar — scan ALL portfolio tickers (OPEN + CLOSED positions)
    earnings_data = get_earnings_calendar([s["ticker"] for s in stocks])

    # 📉 Risk Metrics (Pro only) — cached; None in Free tier (spec §9.6)
    risk_metrics = get_risk_metrics() if is_pro else None

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en" class="dark">
    <head>
        <meta charset="UTF-8">
{% if is_mobile %}<meta name="viewport" content="width=device-width, initial-scale=1.0">{% endif %}
        <title>Pulse — Live Data · Real Intuition</title>
        <link rel="icon" href="/pulse_logo.jpg" type="image/jpeg">
        <link rel="stylesheet" href="/pulse.css">
        <style>
            @keyframes pulse-alert { 0%, 100% { background-color: rgba(159, 18, 57, 0.2); } 50% { background-color: rgba(225, 29, 72, 0.5); } }
            .danger-row { animation: pulse-alert 2s infinite; border-left: 4px solid #f43f5e; }
            .watchlist-sidebar { position: fixed; top: 0; left: 0; width: 280px; height: 100vh; background: #0f172a; border-right: 1px solid rgba(255, 255, 255, 0.1); z-index: 1000; padding: 20px 15px; transform: translateX(-265px); transition: transform 0.3s; }
            .watchlist-sidebar::after { content: '📋'; position: absolute; right: -28px; top: 50%; transform: translateY(-50%); background: #0f172a; color: #34d399; padding: 12px 6px; border-radius: 0 6px 6px 0; font-size: 16px; writing-mode: horizontal-tb; border: 1px solid rgba(255,255,255,0.1); border-left: none; cursor: default; }
            .watchlist-sidebar:hover { transform: translateX(0); }
            .watchlist-sidebar:hover::after { opacity: 0; }
            .hamburger-btn { display: none; position: fixed; top: 10px; left: 10px; z-index: 3100; background: #1e293b; border: 1px solid #334155; color: #34d399; padding: 6px 10px; border-radius: 6px; font-size: 18px; cursor: pointer; }
            .wl-cat-group.dragging { opacity: 0.4; }
            .wl-cat-group.drag-over { border-top: 2px solid #34d399; }
            .wl-loading-overlay { display: none; position: absolute; inset: 0; background: rgba(15,23,42,0.85); z-index: 10; align-items: center; justify-content: center; border-radius: 0; }
            .wl-loading-overlay.active { display: flex; }
            .wl-loading-spinner { color: #34d399; font-size: 14px; font-weight: 700; animation: wl-pulse 1.2s infinite; }
            @keyframes wl-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
            .modal-bg { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(2, 6, 23, 0.75); backdrop-filter: blur(4px); z-index: 2000; align-items: center; justify-content: center; }
            .modal-active { display: flex; }
        
    body.has-bg::before{content:"";position:fixed;inset:0;background:rgba(10,15,30,var(--bg-opacity,0.55));z-index:0;pointer-events:none}
{% if is_mobile %}
    /* ── Mobile (≤768px) ── */
    @media (max-width: 768px) {
        .watchlist-sidebar { width: 260px; transform: translateX(-250px); z-index: 3000; }
        .watchlist-sidebar.mobile-open { transform: translateX(0); box-shadow: 8px 0 30px rgba(0,0,0,0.6); }
        .wl-backdrop { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 2999; }
        .wl-backdrop.active { display: block; }
        .hamburger-btn { display: inline-flex !important; }
        .container { padding: 0 12px; }
        .top-bar-wrap { flex-wrap: wrap; gap: 10px; }
        .top-bar-left { width: 100%; }
        .top-bar-right { width: 100%; justify-content: flex-start; }
        .cards-grid { grid-template-columns: 1fr !important; }
        .perf-bar { flex-wrap: wrap; gap: 8px; }
        .perf-bar > div { flex: 1 1 45%; }
        .table-wrap { font-size: 10px; }
        .settings-modal-inner { width: 95vw !important; max-width: none !important; margin: 8px !important; padding: 16px !important; }
        .settings-form-grid { grid-template-columns: 1fr !important; }
        .buy-sell-grid { grid-template-columns: 1fr !important; }
    }
{% endif %}
    </style>
    </head>
    <body class="bg-slate-950 text-slate-100 min-h-screen font-sans">
{% if is_pro and config.bg_image %}
        <script>document.body.classList.add('has-bg');document.body.style.backgroundImage='url(/api/bg?'+Date.now()+')';document.body.style.backgroundSize='cover';document.body.style.backgroundAttachment='fixed';document.documentElement.style.setProperty('--bg-opacity','{{ config.bg_opacity }}');</script>
{% endif %}
{% if is_mobile %}
        <!-- Mobile hamburger -->
        <button class="hamburger-btn" onclick="toggleWatchlist()" title="Watchlist">☰</button>
        <div class="wl-backdrop" onclick="toggleWatchlist()"></div>
{% endif %}

        <!-- Watchlist Sidebar -->
        <div class="watchlist-sidebar">
        <div id="wl-loading" class="wl-loading-overlay"><span class="wl-loading-spinner">{{ t.wl_loading }}</span></div>
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
                    <button type="button" id="tab-btn-bg" onclick="switchSettingsTab('bg')" class="px-4 py-1.5 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700">{{ t.settings_tab_bg }}</button>
                    <button type="button" id="tab-btn-ai" onclick="switchSettingsTab('ai')" class="px-4 py-1.5 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700">{{ t.settings_tab_ai }}</button>
                    <button type="button" id="tab-btn-idx" onclick="switchSettingsTab('idx')" class="px-4 py-1.5 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700">{{ t.settings_tab_indices }}</button>
                    <button type="button" id="tab-btn-risk" onclick="switchSettingsTab('risk')" class="px-4 py-1.5 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700">{{ t.risk_settings_tab }}</button>
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
                            <label class="block text-slate-400 font-bold mb-1" for="settings-primary-currency">{{ t.settings_primary_currency }}</label>
                            <select name="primary_currency" id="settings-primary-currency" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-bold">
                                <option value="USD" {% if config.primary_currency == 'USD' %}selected{% endif %}>$ USD</option>
                                <option value="HKD" {% if config.primary_currency == 'HKD' %}selected{% endif %}>$ HKD</option>
                                <option value="TWD" {% if config.primary_currency == 'TWD' %}selected{% endif %}>$ TWD</option>
                                <option value="CNY" {% if config.primary_currency == 'CNY' %}selected{% endif %}>¥ CNY</option>
                                <option value="JPY" {% if config.primary_currency == 'JPY' %}selected{% endif %}>¥ JPY</option>
                                <option value="EUR" {% if config.primary_currency == 'EUR' %}selected{% endif %}>€ EUR</option>
                                <option value="GBP" {% if config.primary_currency == 'GBP' %}selected{% endif %}>£ GBP</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-currency">{{ t.settings_secondary_currency }}</label>
                            <select name="secondary_currency" id="settings-currency" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-bold">
                                <option value="" {% if not config.secondary_currency %}selected{% endif %}>— None —</option>
                                <option value="USD" {% if config.secondary_currency == 'USD' %}selected{% endif %}>$ USD</option>
                                <option value="HKD" {% if config.secondary_currency == 'HKD' %}selected{% endif %}>$ HKD</option>
                                <option value="TWD" {% if config.secondary_currency == 'TWD' %}selected{% endif %}>$ TWD</option>
                                <option value="CNY" {% if config.secondary_currency == 'CNY' %}selected{% endif %}>¥ CNY</option>
                                <option value="JPY" {% if config.secondary_currency == 'JPY' %}selected{% endif %}>¥ JPY</option>
                                <option value="EUR" {% if config.secondary_currency == 'EUR' %}selected{% endif %}>€ EUR</option>
                                <option value="GBP" {% if config.secondary_currency == 'GBP' %}selected{% endif %}>£ GBP</option>
                            </select>
                        </div>

                <!-- 📋 Changelog -->
                <div class="border-t border-slate-800 mt-4 pt-4">
                    <p class="text-slate-500 text-[10px] font-bold uppercase mb-2">{{ t.changelog_title }}</p>
                    <div class="space-y-1 max-h-32 overflow-y-auto">
                        {% for ver, msg in changelog %}
                        <div class="text-[10px]"><span class="text-cyan-400 font-mono">{{ ver }}</span> <span class="text-slate-500">{{ msg }}</span></div>
                        {% endfor %}
                    </div>
                </div>
                    </div>

                    <!-- BG TAB -->
                    <div id="settings-tab-bg" class="hidden space-y-4">
{% if is_pro %}
                        <input type="hidden" name="bg_image" value="{% if config.bg_image %}true{% else %}false{% endif %}">
                        <input type="hidden" name="bg_opacity" value="{{ config.bg_opacity }}">
                        <div>
                            <label class="block text-slate-400 font-bold mb-1">{{ t.bg_title }}</label>
                            <div class="flex items-center gap-3">
                                <input type="file" accept="image/*" id="bg-file-input" onchange="uploadBg(this)" class="text-slate-300 text-xs file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-bold file:bg-cyan-600 file:text-slate-900 hover:file:bg-cyan-500">
                                <button type="button" onclick="removeBg()" id="bg-remove-btn" class="px-3 py-1.5 rounded text-xs font-bold bg-rose-900 text-rose-300 hover:bg-rose-800{% if not config.bg_image %} hidden{% endif %}">{{ t.bg_remove_btn }}</button>
                            </div>
                            <img id="bg-preview" src="/api/bg" class="mt-2 max-w-[200px] rounded border border-slate-700{% if not config.bg_image %} hidden{% endif %}" onerror="this.style.display='none'">
                            <div class="mt-3">
                                <label class="block text-slate-400 font-bold mb-1 text-xs">{{ t.bg_opacity }}: <span id="bg-opacity-val">{{ "%.2f"|format(config.bg_opacity) }}</span></label>
                                <input type="range" name="bg_opacity" id="bg-opacity-slider" min="0" max="0.95" step="0.05" value="{{ config.bg_opacity }}" oninput="updateBgOpacity(this.value)" class="w-full max-w-[200px] accent-cyan-500">
                            </div>
                        </div>
{% endif %}
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
                                <input type="text" name="ai_model" id="settings-model" value="{{ config.ai_model }}" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-mono">
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

                    <!-- 📊 INDICES TAB (V1.12.1 — fully user-selected) -->
                    <div id="settings-tab-idx" class="hidden space-y-4">
                        <p class="text-slate-400 text-[11px]">{{ t.settings_indices_hint }}</p>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1">{{ t.settings_indices_selectable }} <span id="idx-count" class="text-cyan-400 font-mono text-[10px]">{{
                                (config.extra_indices or [])|length
                            }}</span><span class="text-slate-600 font-mono text-[10px]">/5</span>
                            <span id="idx-warn" class="text-amber-400 text-[10px] hidden ml-1">⚠ {{ t.settings_indices_min }}</span></label>
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                                {% for key, idx in index_list.items() %}
                                <label class="flex items-center gap-2 bg-slate-950/60 border border-slate-800 rounded px-2 py-1.5 cursor-pointer hover:border-cyan-700">
                                    <input type="checkbox" name="extra_indices" value="{{ key }}" {% if key in (config.extra_indices or []) %}checked{% endif %} class="accent-cyan-500 idx-cb">
                                    <span class="text-slate-200 font-bold">{{ idx.name_zh_tw }}</span>
                                    <span class="text-slate-500 text-[10px] font-mono ml-auto">{{ idx.ticker }}</span>
                                    <span class="text-slate-600 text-[9px] font-mono ml-1">{{ idx.market }}</span>
                                </label>
                                {% endfor %}
                            </div>
                            <script>
                                (function() {
                                    var cbs = document.querySelectorAll('.idx-cb');
                                    var cnt = document.getElementById('idx-count');
                                    var warn = document.getElementById('idx-warn');
                                    var MAX = 5;
                                    function update() {
                                        var n = 0;
                                        cbs.forEach(function(c) { if (c.checked) n++; });
                                        cnt.textContent = n;
                                        warn.classList.toggle('hidden', n > 0);
                                        // Disable unchecked when at max
                                        var atMax = (n >= MAX);
                                        cbs.forEach(function(c) {
                                            if (!c.checked) c.disabled = atMax;
                                        });
                                    }
                                    cbs.forEach(function(c) { c.addEventListener('change', update); });
                                    update();
                                })();
                            </script>
                        </div>
                    </div>

                    <!-- 📉 RISK METRICS TAB (Pro) — mirrors AI-tab pattern (spec §7.1) -->
                    <div id="settings-tab-risk" class="hidden space-y-4">
                        {% if is_pro %}
                        <p class="text-slate-400 text-[11px]">{{ t.risk_settings_intro }}</p>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-risk-period">{{ t.risk_period_label }}</label>
                            <select name="risk_period" id="settings-risk-period" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-bold">
                                <option value="90" {% if config.risk_period == 90 %}selected{% endif %}>{{ t.risk_period_90 }}</option>
                                <option value="120" {% if config.risk_period == 120 %}selected{% endif %}>{{ t.risk_period_120 }}</option>
                                <option value="180" {% if config.risk_period == 180 %}selected{% endif %}>{{ t.risk_period_180 }}</option>
                                <option value="365" {% if config.risk_period == 365 %}selected{% endif %}>{{ t.risk_period_365 }}</option>
                                <option value="0" {% if config.risk_period == 0 %}selected{% endif %}>{{ t.risk_period_longest }}</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-risk-method">{{ t.risk_method_label }}</label>
                            <select name="risk_method" id="settings-risk-method" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-bold">
                                <option value="historical" {% if config.risk_method == 'historical' %}selected{% endif %}>{{ t.risk_method_historical }}</option>
                                <option value="parametric" {% if config.risk_method == 'parametric' %}selected{% endif %}>{{ t.risk_method_parametric }}</option>
                                <option value="montecarlo" {% if config.risk_method == 'montecarlo' %}selected{% endif %}>{{ t.risk_method_montecarlo }}</option>
                            </select>
                        </div>
                        <div id="risk-paths-row" {% if config.risk_method != 'montecarlo' %}class="hidden"{% endif %}>
                            <label class="block text-slate-400 font-bold mb-1" for="settings-risk-paths">{{ t.risk_paths_label }}</label>
                            <input type="number" name="risk_paths" id="settings-risk-paths" value="{{ config.risk_paths }}" min="1000" max="10000" step="100" class="w-40 bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-mono">
                            <p class="text-slate-600 text-[10px] mt-1">{{ t.risk_paths_hint }}</p>
                        </div>
                        <script>
                            (function() {
                                var sel = document.getElementById('settings-risk-method');
                                var row = document.getElementById('risk-paths-row');
                                if (sel && row) sel.addEventListener('change', function() {
                                    row.classList.toggle('hidden', this.value !== 'montecarlo');
                                });
                            })();
                        </script>
                        {% else %}
                        <p class="text-slate-500 text-sm">{{ t.risk_pro_only_note }}</p>
                        {% endif %}
                    </div>

                    <div class="border-t border-slate-800 pt-4 flex justify-end">
                        <button type="submit" class="px-6 py-2 bg-cyan-600 hover:bg-cyan-500 font-black rounded text-slate-900 tracking-wider">{{ t.settings_save }}</button>
                    </div>
                </form>

                <!-- 📥📤 Import / Export -->
                <div class="border-t border-slate-800 mt-4 pt-4">
                    <p class="text-slate-500 text-[10px] font-bold uppercase mb-2">📥📤 Import / Export</p>
                    <div class="flex gap-2">
                        <p class="text-slate-500 text-[10px] mb-2">{{ t.import_export_desc }}</p>
                    <button type="button" onclick="doExport()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded text-xs font-bold">{{ t.export_btn }}</button>
                        <button type="button" onclick="document.getElementById('import-file').click()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded text-xs font-bold">{{ t.import_btn }}</button>
                        <input type="file" id="import-file" accept=".json" onchange="doImport(this)" class="hidden">
                    </div>
                    <div id="import-preview" class="hidden mt-2 text-xs text-slate-400"></div>
                </div>
            </div>
        </div>

        <div class="container mx-auto px-6 py-8 pl-12">
            <!-- 頂部 Bar -->
            <div class="flex justify-between items-center border-b border-slate-800 pb-6 mb-8">
                <div class="flex items-center gap-4">
                    <img src="/pulse_logo.jpg" alt="Pulse" class="w-10 h-10 rounded-lg">
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
                <!-- 📊 Index ticker + FX (compact, top bar) -->
                {% if index_data %}
                <div class="border border-slate-500/50 rounded-lg px-3 py-2 text-[10px]">
                    <div class="flex items-center gap-1 overflow-hidden" style="flex-wrap: nowrap">
                        <span class="text-slate-600 font-bold mr-0.5">📊</span>
                        {% for idx in index_data %}
                        <span class="cursor-pointer hover:bg-slate-800 rounded px-1 py-0.5 transition-colors inline-flex items-center gap-0.5" onclick="filterMarket('{{ idx.market }}')" title="{{ idx.name_en }}">
                            <span class="text-slate-400">{{ idx.name_en }}</span>
                            <span class="font-mono text-cyan-400 font-bold">{{ "{:,.0f}".format(idx.price) }}</span>
                            <span class="font-mono {% if idx.change_pct >= 0 %}text-emerald-400{% else %}text-rose-500{% endif %}">
                                {{ "▲" if idx.change_pct >= 0 else "▼" }}{{ "%.2f"|format(idx.change_pct|abs) }}%
                            </span>
                        </span>
                        {% if not loop.last %}<span class="text-slate-700 text-[8px]">｜</span>{% endif %}
                        {% endfor %}
                    </div>
                    <hr class="border-slate-500/30 my-1.5">
                    <div class="flex items-center gap-1 overflow-hidden text-[10px]" style="flex-wrap: nowrap">
                        <span class="text-slate-500 mr-0.5">💱</span>
                        {% for cur in ["USD", "HKD", "CNY", "TWD"] %}
                            {% if cur != prim_cur and fx_matrix.get(prim_cur, {}).get(cur) %}
                            <span class="text-slate-500">{{ prim_cur|upper }}→{{ cur }}</span>
                            <span class="font-mono text-slate-300">{{ "%.4f"|format(fx_matrix[prim_cur][cur]) }}</span>
                            {% if not loop.last %}<span class="text-slate-700">｜</span>{% endif %}
                            {% endif %}
                        {% endfor %}
                    </div>
                </div>
                {% else %}
                <div class="text-slate-500 text-[10px] px-3 cursor-pointer hover:text-cyan-400" onclick="toggleSettingsModal()">{{ t.index_none_compact }}</div>
                {% endif %}
                <div class="flex items-center gap-3">
                    <div class="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 flex items-center gap-2 text-xs">
                        <span class="text-slate-400 font-bold">{{ t.auto_refresh_label }}</span>
                        <input type="number" id="refreshIntervalInput" name="refresh_interval" value="{{ config.refresh_interval }}" min="10" title="{{ t.refresh_tooltip }}" class="w-12 bg-slate-950 text-center text-emerald-400 font-mono rounded font-bold" onchange="updateLiveInterval(this.value)">
                        <span id="refreshIndicator" class="h-2 w-2 rounded-full bg-emerald-500"></span>
                    </div>
                    {% if is_pro %}<button onclick="runAiAudit()" class="px-5 py-2.5 bg-gradient-to-r from-cyan-500 to-emerald-500 font-bold rounded-lg text-xs tracking-widest">{{ t.ai_report_btn }}</button>{% endif %}
                    <button onclick="toggleSettingsModal()" class="p-2.5 bg-slate-900 border border-slate-800 rounded-lg text-slate-300">⚙️</button>

                </div>
            </div>

            <!-- 三大數據卡片 -->
            <div class="grid {% if is_pro %}grid-cols-3{% else %}grid-cols-2{% endif %} gap-6 mb-8">
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl">
                    <p class="text-slate-400 text-xs font-bold uppercase">{{ t.total_mv_label }} ({% if sec_cur %}{{ prim_cur }} / {{ sec_cur }}{% else %}{{ prim_cur }}{% endif %})</p>
                    <p id="top-total-mv-primary" class="text-3xl font-black text-cyan-400 mt-2">{{ prim_symbol }}{{ "{:,.2f}".format(total_mv_primary) }}</p>
                    {% if sec_cur %}<p id="top-total-mv-sec" class="text-xs font-mono text-slate-500 mt-1">≈ {{ sec_symbol }}{{ "{:,.2f}".format(total_mv_primary * prim_to_sec) }}</p>{% endif %}
                </div>
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl">
                    <p class="text-slate-400 text-xs font-bold uppercase">{{ t.total_pnl_label }} ({% if sec_cur %}{{ prim_cur }} / {{ sec_cur }}{% else %}{{ prim_cur }}{% endif %})</p>
                    <p id="top-total-pnl-primary" class="text-3xl font-black mt-2 {% if total_pnl_primary >= 0 %}text-emerald-400{% else %}text-rose-500{% endif %}">{{ prim_symbol }}{{ "{:+,.2f}".format(total_pnl_primary) }} <span class="text-xl font-medium">({{ total_roi_str }})</span></p>
                    {% if sec_cur %}<p id="top-total-pnl-sec" class="text-xs font-mono mt-1 {% if total_pnl_primary >= 0 %}text-emerald-500/80{% else %}text-rose-500/80{% endif %}">≈ {{ sec_symbol }}{{ "{:+,.2f}".format(total_pnl_primary * prim_to_sec) }}</p>{% endif %}
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

            {% if earnings_data %}
            <!-- 📅 Earnings Calendar -->
            <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl mb-8">
                <div class="flex items-center justify-between mb-3">
                    <p class="text-slate-400 text-xs font-bold uppercase">{{ t.earnings_title }}</p>
                    <span class="text-[10px] text-slate-500">{{ t.earnings_window_label.replace("{days}", earnings_lookahead_days|string) }}</span>
                </div>
                <div class="flex flex-wrap gap-x-6 gap-y-2 text-xs">
                    {% for item in earnings_data %}
                    <div class="flex items-center gap-2">
                        <span class="font-mono font-bold text-cyan-400">{{ item[0] }}</span>
                        <span class="text-slate-300 font-mono">{{ item[1] }}</span>
                        <span class="text-slate-500">{% if item[2] == 0 %}{{ t.earnings_today }}{% else %}{{ t.earnings_countdown_label.replace("{n}", item[2]|string) }}{% endif %}</span>
                    </div>
                    {% if not loop.last %}<span class="text-slate-700 text-[8px] self-center">｜</span>{% endif %}
                    {% endfor %}
                </div>
                <p class="text-[10px] text-slate-600 mt-2">⚠ 此卡片暫時只支援美國市場，未來會開放更多市場</p>
            </div>
            {% endif %}

            <!-- 📈 Performance (Free + Pro — horizontal bar, spec §9.1) -->
            <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl mb-8 flex items-center gap-6">
                <p class="text-slate-400 text-xs font-bold uppercase whitespace-nowrap">{{ t.perf_title }}</p>
                {% for period in [('today', t.perf_today), ('wtd', t.perf_wtd), ('mtd', t.perf_mtd), ('ytd', t.perf_ytd)] %}
                <div class="flex items-center gap-1.5">
                    <span class="text-slate-500 text-[10px] uppercase">{{ period[1] }}</span>
                    <span class="font-mono font-bold text-sm {% if perf[period[0]].pct >= 0 %}text-emerald-400{% else %}text-rose-500{% endif %}">{{ '%+.1f'|format(perf[period[0]].pct) }}%</span>
                </div>
                {% endfor %}
            </div>
            {% if is_pro %}
            <!-- Pro: 📉 Risk Metrics + 🌍 Market Dist + 💰 Cash Ratio -->
            <div class="grid grid-cols-3 gap-6 mb-8">
                <!-- 📉 Risk Metrics -->
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl">
                    <p class="text-slate-400 text-xs font-bold uppercase mb-3">{{ t.risk_card_title }}</p>
                    {% if risk_metrics and risk_metrics.status == 'ok' %}
                    <div class="space-y-2 text-xs">
                        <div class="flex justify-between items-center" title="{{ t.risk_sharpe_hint }}">
                            <span class="text-slate-400 text-xs">{{ t.risk_sharpe }}</span>
                            <span class="font-mono font-bold text-cyan-400">{{ risk_metrics.sharpe }}</span>
                        </div>
                        <div class="flex justify-between items-center" title="{{ t.risk_sortino_hint }}">
                            <span class="text-slate-400 text-xs">{{ t.risk_sortino }}</span>
                            <span class="font-mono font-bold text-cyan-400">{{ risk_metrics.sortino }}</span>
                        </div>
                        <div class="flex justify-between items-center" title="{{ t.risk_volatility_hint }}">
                            <span class="text-slate-400 text-xs">{{ t.risk_volatility }}</span>
                            <span class="font-mono font-bold text-cyan-400">{{ risk_metrics.volatility }}</span>
                        </div>
                        <div class="flex justify-between items-center" title="{{ t.risk_max_drawdown_hint }}">
                            <span class="text-slate-400 text-xs">{{ t.risk_max_drawdown }}</span>
                            <span class="font-mono font-bold text-rose-400">{{ risk_metrics.max_drawdown }}</span>
                        </div>
                        <div class="flex justify-between items-center" title="{{ t.risk_var_hint }}">
                            <span class="text-slate-400 text-xs">{{ t.risk_var }}{% if config.risk_method == 'historical' %}-{{ t.risk_method_historical }}{% elif config.risk_method == 'parametric' %}-{{ t.risk_method_parametric }}{% elif config.risk_method == 'montecarlo' %}-{{ t.risk_method_montecarlo }}{% endif %}</span>
                            <span class="font-mono font-bold text-rose-400">{{ risk_metrics.var95_amount }} <span class="text-[10px]">({{ risk_metrics.var95_pct }})</span></span>
                        </div>
                    </div>
                    {% if risk_metrics.stale %} <p class="text-[10px] text-amber-500 mt-2">stale</p>{% endif %}
                    {% elif risk_metrics and risk_metrics.status == 'no_positions' %}
                    <p class="text-slate-500 text-xs text-center py-4">{{ t.risk_no_positions }}</p>
                    {% else %}
                    <p class="text-slate-500 text-xs text-center py-4">{{ t.risk_insufficient_data }}</p>
                    {% endif %}
                </div>
                <!-- 🌍 Market Distribution -->
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
                        <span class="text-cyan-400 font-mono text-xs">{{ "%.1f"|format(mv / total_mv_primary_raw * 100) if total_mv_primary_raw > 0 else 0 }}%</span>
                    </div>
                    <div class="w-full bg-slate-800 rounded-full h-1.5 mb-2">
                        <div class="bg-cyan-500 h-1.5 rounded-full" style="width: {{ "%.0f"|format(mv / total_mv_primary_raw * 100) if total_mv_primary_raw > 0 else 0 }}%"></div>
                    </div>
                    {% endfor %}
                </div>
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl flex flex-col justify-center items-center">
                    <p class="text-slate-400 text-xs font-bold uppercase mb-2">{{ t.card_cash_ratio }}</p>
                    <p class="text-4xl font-black text-emerald-400">{{ "%.1f"|format(cash_balance / (total_mv_primary_raw + cash_balance) * 100) if (total_mv_primary_raw + cash_balance) > 0 else 0 }}%</p>
                    <p class="text-slate-500 text-xs mt-1">{{ prim_symbol }}{{ "{:,.0f}".format(cash_balance) }} / {{ prim_symbol }}{{ "{:,.0f}".format(total_mv_primary_raw + cash_balance) }}</p>
                </div>
            </div>
            {% endif %}
            {# Performance bar now renders unconditionally above the Pro grid (Edit 5a) #}

            <!-- 交易輸入表單 -->
            <div class="grid grid-cols-2 gap-6 mb-8">
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl border-l-4 border-l-emerald-500">
                    <h3 class="text-md font-black text-emerald-400 mb-4">{{ t.buy_title }}</h3>
                    <form id="buy-form" class="grid grid-cols-2 gap-3 text-xs" onsubmit="submitTrade(event, 'buy')">
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="buy-ticker">{{ t.ticker_label }}</label><input type="text" name="ticker" id="buy-ticker" placeholder="{{ t.buy_ticker_ph }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2 font-mono uppercase"></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="buy-market">{{ t.market_label }}</label><select name="market" id="buy-market" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-100 font-bold"><option value="US">US</option><option value="HK">HK</option><option value="CN">CN</option><option value="TW">TW</option><option value="TWO">TWO</option></select></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="buy-date">{{ t.date_label }}</label><input type="date" name="buy_date" id="buy-date" value="{{ today_date }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="buy-price" id="buy-price-label">{{ t.price_label }} (USD)</label><input type="number" step="0.0001" name="buy_price" id="buy-price" placeholder="{{ t.buy_price_ph }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
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
                        <div><label class="block text-slate-500 text-[10px] font-bold mb-0.5" for="sell-price" id="sell-price-label">{{ t.sell_price_label }} (USD)</label><input type="number" step="0.0001" name="sell_price" id="sell-price" placeholder="{{ t.sell_price_ph }}" required class="w-full bg-slate-950 border border-slate-800 rounded p-2"></div>
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
                            <th class="px-4 py-4" title="{{ t.table_stop_loss_hint }}">{{ t.table_stop_loss }}</th>
                            <th class="px-4 py-4">{{ t.table_mv }}</th>
                            <th class="px-6 py-4 text-right">{{ t.table_pnl }}</th>
                            {% if is_pro %}<th class="px-4 py-4 text-right">{{ t.table_weight }}</th>{% endif %}
                        </tr>
                    </thead>
                    
                    {% for stock in stocks %}
            <!-- 🌟 股票核心資料列 -->
            <!-- 🌟 股票核心資料列 -->
                    <tbody class="border-b border-slate-800/80" data-market="{{ stock.market }}">
                        <tr class="hover:bg-slate-800/30 cursor-pointer transition-colors {% if stock.is_danger %}danger-row{% endif %}" onclick="toggleHistory('details-{{ stock.ticker }}')">
                            <td class="px-6 py-4 text-center text-cyan-400 font-bold select-none text-sm">▶</td>
                            <td class="px-4 py-4 font-black text-slate-100 text-sm">{{ stock.ticker }}{% if stock.company_name %} <span class="text-slate-500 font-normal text-xs">{{ stock.company_name }}</span>{% endif %}
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
                                {{ stock.pnl_primary_str }} ({{ stock.roi_str }})
                            </td>
                            {% if is_pro %}
                            <td class="px-4 py-4 text-right font-mono text-slate-400 text-sm">
                                {{ "%.1f"|format(stock.current_mv_raw / total_mv_primary_raw * 100) if total_mv_primary_raw > 0 and stock.current_mv_raw > 0 else "-" }}%
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
                                    <div class="text-slate-400 font-bold mb-2 uppercase font-mono tracking-wider text-[11px]">{{ t.history_title }} — {{ stock.ticker }}{% if stock.company_name %} - {{ stock.company_name }}{% endif %} | {{ t.capital_recovered_label }}: ${{ stock.capital_recovered_str }}</div>
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
                document.getElementById('settings-tab-bg').classList.toggle('hidden', tab !== 'bg');
                document.getElementById('settings-tab-ai').classList.toggle('hidden', tab !== 'ai');
                document.getElementById('settings-tab-idx').classList.toggle('hidden', tab !== 'idx');
                document.getElementById('settings-tab-risk').classList.toggle('hidden', tab !== 'risk');
                var bg = document.getElementById('tab-btn-bg');
                var gb = document.getElementById('tab-btn-general');
                var ab = document.getElementById('tab-btn-ai');
                var ib = document.getElementById('tab-btn-idx');
                var rb = document.getElementById('tab-btn-risk');
                var active = 'px-4 py-1.5 text-xs font-bold rounded bg-cyan-600 text-slate-900';
                var inactive = 'px-4 py-1.5 text-xs font-bold rounded bg-slate-800 text-slate-400 hover:bg-slate-700';
                gb.className = tab === 'general' ? active : inactive;
                bg.className = tab === 'bg' ? active : inactive;
                ab.className = tab === 'ai' ? active : inactive;
                ib.className = tab === 'idx' ? active : inactive;
                if (rb) rb.className = tab === 'risk' ? active : inactive;
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
                            document.getElementById('top-total-mv-primary').innerText = data.prim_symbol + data.total_mv_primary_str;
                            var secEl = document.getElementById('top-total-mv-sec'); if (secEl) { secEl.innerText = '≈ ' + data.sec_cur + data.total_mv_sec_str; }
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

            // 📋 Watchlist Helpers
{% if is_mobile %}
            function toggleWatchlist() {
                var wl = document.querySelector('.watchlist-sidebar');
                var bd = document.querySelector('.wl-backdrop');
                wl.classList.toggle('mobile-open');
                if (bd) bd.classList.toggle('active');
            }
{% endif %}
            function reloadWatchlist() {
                var overlay = document.getElementById('wl-loading');
                if (overlay) overlay.classList.add('active');
                fetch('/api/wl/render')
                    .then(function(r) { return r.text(); })
                    .then(function(html) {
                        var sidebar = document.querySelector('.watchlist-sidebar');
                        // Remove old groups from the scrollable container
                        var box = document.getElementById('watchlist-master-box');
                        box.querySelectorAll('.wl-cat-group').forEach(function(el) { el.remove(); });
                        // Append new groups
                        var frag = document.createElement('div');
                        frag.innerHTML = html;
                        while (frag.firstChild) {
                            box.appendChild(frag.firstChild);
                        }
                        if (overlay) overlay.classList.remove('active');
                        // Re-attach drag listeners
                        document.querySelectorAll('.wl-cat-group').forEach(function(el) {
                            el.addEventListener('dragenter', handleDragEnter);
                            el.addEventListener('dragleave', handleDragLeave);
                        });
                    })
                    .catch(function() {
                        var overlay = document.getElementById('wl-loading');
                        if (overlay) overlay.classList.remove('active');
                    });
            }

            // 📋 Watchlist Management
            function createNewCategory() {
                const name = prompt('{{ t.wl_new_cat_prompt }}');
                if (!name || !name.trim()) return;
                fetch('/api/wl/add_category', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: name.trim()}) })
                .then(r => r.json()).then(d => { if (d.success) reloadWatchlist(); else alert(d.error); });
            }
            function deleteCategory(name) {
                if (!confirm('{{ t.wl_delete_cat }}: ' + name + '?')) return;
                fetch('/api/wl/delete_category', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: name}) })
                .then(r => r.json()).then(d => { if (d.success) reloadWatchlist(); });
            }
            function renameCategory(oldName, newName) {
                if (!newName.trim() || newName.trim() === oldName) return;
                fetch('/api/wl/rename_category', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({old_name: oldName, new_name: newName.trim()}) })
                .then(r => r.json()).then(d => { if (d.success) reloadWatchlist(); });
            }
            function addTickerToCategory(catName, el) {
                const input = el.tagName === 'INPUT' ? el : el.previousElementSibling;
                const ticker = input.value.trim().toUpperCase();
                if (!ticker) return;
                const marketSel = document.getElementById('wl-market-' + catName);
                const market = marketSel ? marketSel.value : 'US';
                fetch('/api/wl/add_ticker', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({category: catName, ticker: ticker, market: market}) })
                .then(r => r.json()).then(d => { if (d.success) reloadWatchlist(); });
            }
            function deleteTickerFromCategory(catName, ticker) {
                fetch('/api/wl/delete_ticker', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({category: catName, ticker: ticker}) })
                .then(r => r.json()).then(d => { if (d.success) reloadWatchlist(); });
            }
{% if is_pro %}
            // 🖼️ Background Image (Pro)
            function updateBgOpacity(val) {
                document.getElementById('bg-opacity-val').textContent = parseFloat(val).toFixed(2);
                document.documentElement.style.setProperty('--bg-opacity', val);
                var hi = document.querySelector('input[name=bg_opacity]');
                if (hi) hi.value = val;
            }
            function uploadBg(input) {
                const file = input.files[0];
                if (!file) return;
                const valid = ['image/jpeg','image/png','image/gif','image/webp'];
                if (!valid.includes(file.type)) {
                    var warn = document.createElement('div');
                    warn.style.cssText = 'position:fixed;top:16px;right:16px;background:#be123c;color:#fff;padding:12px 20px;border-radius:8px;z-index:9999;font-size:14px';
                    warn.textContent = 'Unsupported format (jpg/png/gif/webp only)';
                    document.body.appendChild(warn);
                    setTimeout(function(){ warn.remove(); }, 3000);
                    input.value = '';
                    return;
                }
                const fd = new FormData();
                fd.append('bg', file);
                fetch('/api/config/upload_bg', { method: 'POST', body: fd })
                    .then(function(r) { return r.json(); })
                    .then(function(d) {
                        if (d.success) {
                            var ts = Date.now();
                            document.getElementById('bg-preview').src = '/api/bg?' + ts;
                            document.getElementById('bg-preview').classList.remove('hidden');
                    document.getElementById('bg-remove-btn').classList.remove('hidden');
                    document.body.classList.add('has-bg');
                    var hi = document.querySelector('input[name=bg_image]');
                    if (hi) hi.value = 'true';
                            document.body.style.backgroundImage = 'url(/api/bg?' + ts + ')';
                            document.body.style.backgroundSize = 'cover';
                            document.body.style.backgroundAttachment = 'fixed';
                    var op = document.getElementById('bg-opacity-slider');
                    if (op) document.documentElement.style.setProperty('--bg-opacity', op.value);
                        }
                    });
            }
            function removeBg() {
                fetch('/api/config/remove_bg', { method: 'POST' })
                    .then(function(r) { return r.json(); })
                    .then(function(d) {
                        if (d.success) {
                            document.getElementById('bg-preview').classList.add('hidden');
                            document.getElementById('bg-remove-btn').classList.add('hidden');
                            document.getElementById('bg-file-input').value = '';
                    document.body.classList.remove('has-bg');
                    document.body.style.backgroundImage = '';
                    var hi = document.querySelector('input[name=bg_image]');
                    if (hi) hi.value = 'false';
                        }
                    });
            }

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

            // Market-native currency labels
            const CURR_LABELS = {US:'USD', HK:'HKD', CN:'CNY', TW:'TWD', TWO:'TWD'};
            function updateBuyPriceLabel() {
                const mkt = document.getElementById('buy-market').value;
                const label = document.getElementById('buy-price-label');
                if (label) label.textContent = '{{ t.price_label }} (' + (CURR_LABELS[mkt] || 'USD') + ')';
            }
            function updateSellPriceLabel() {
                const sel = document.getElementById('sell-ticker');
                if (!sel) return;
                const opt = sel.options[sel.selectedIndex];
                const mkt = opt && opt.parentElement.label ? opt.parentElement.label : 'USD';
                const label = document.getElementById('sell-price-label');
                if (label) label.textContent = '{{ t.sell_price_label }} (' + (CURR_LABELS[mkt] || mkt) + ')';
            }
            window.onload = function() {
                startHighFrequencyUpdater();
                updateBuyPriceLabel();
                updateSellPriceLabel();
                document.getElementById('buy-market').addEventListener('change', updateBuyPriceLabel);
                document.getElementById('sell-ticker').addEventListener('change', updateSellPriceLabel);
                attachCostCalculator('#buy-form', 'input[type="number"]', 'buy-estimated-cost', '{{ t.buy_est_cost }}', 1);
                attachCostCalculator('#sell-form', 'input[type="number"]', 'sell-estimated-cost', '{{ t.sell_est_income }}', -1);
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

            // 📥📤 Import / Export
            function doExport() {
                const wl = confirm('{{ t.import_watchlist }}?') ? '1' : '0';
                const pf = confirm('{{ t.import_portfolio }}?') ? '1' : '0';
                if (wl === '0' && pf === '0') return;
                fetch('/api/export?watchlist=' + wl + '&portfolio=' + pf)
                .then(r => r.json())
                .then(data => {
                    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = 'pulse_export.json';
                    a.click();
                });
            }
            async function doImport(input) {
                const file = input.files[0];
                if (!file) return;
                const text = await file.text();
                let data;
                try { data = JSON.parse(text); } catch(e) { alert('Invalid JSON'); return; }
                const resp = await fetch('/api/import', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                const result = await resp.json();
                if (!result.success) { alert(result.error); return; }
                const p = result.preview;
                var lines = [];
                if (p.watchlist && p.watchlist.length > 0) { lines.push('{{ t.import_watchlist }}: {{ t.import_will_add }} ' + p.watchlist.length + ' tickers'); }
                if (p.watchlist_exists && p.watchlist_exists.length > 0) { lines.push('{{ t.import_watchlist }}: ' + p.watchlist_exists.length + ' {{ t.import_exists_skip }}'); }
                if (p.portfolio && p.portfolio.length > 0) { lines.push('{{ t.import_portfolio }}: {{ t.import_will_add }} ' + p.portfolio.length + ' entries'); }
                if (p.portfolio_exists && p.portfolio_exists.length > 0) { lines.push('{{ t.import_portfolio }}: ' + p.portfolio_exists.length + ' {{ t.import_exists_skip }}'); }
                if (lines.length === 0) { lines.push('{{ t.import_exists_skip }}'); }
                alert('{{ t.import_success }}! ' + lines.join(', '));
                location.reload();
            }
        </script>

    <div class="border-t border-slate-800 pt-3 mt-6 text-center"><p class="text-[10px] text-slate-500">{{ t.disclaimer }}</p></div>

    </body>
    </html>
    """, t=t, stocks=stocks, open_tickers=open_tickers, ticker_market=ticker_market,
        total_mv_primary=total_mv_primary, total_open_cost=total_open_cost,
        total_pnl_primary=total_pnl_primary, total_roi_str=total_roi_str,
        prim_cur=prim_cur, prim_symbol=prim_symbol, sec_cur=sec_cur, sec_symbol=sec_symbol, prim_to_sec=prim_to_sec,
        watchlist_html=watchlist_html,
        targets_json=targets_json, markets_status=markets_status,
        active_markets=active_markets, version=VERSION, changelog=CHANGELOG,
        today_date=date_str, config=config, is_pro=get_is_pro(),
        perf=perf,
        earnings_data=earnings_data, earnings_lookahead_days=EARNINGS_LOOKAHEAD_DAYS,
        risk_metrics=risk_metrics,
        total_mv_primary_raw=total_mv_primary, total_open_cost_raw=total_open_cost,
        cash_balance=config.get("cash_balance", 0),
        index_data=get_all_index_data(config), fx_matrix=fx_matrix,
        index_list=INDEX_LIST,
        is_mobile=is_mobile)


@app.route('/')
def index():
    """Main route — render dashboard directly."""
    return _render_dashboard()


@app.route('/mobile')
def mobile():
    """Mobile page — responsive layout test."""
    return _render_dashboard(is_mobile=True)


@app.route('/dashboard')
def dashboard():
    """Dashboard route — redirect to /."""
    return redirect("/")

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "version": VERSION, "mode": "selfhosted"})


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
    market = data.get('market', 'US').strip()
    if not cat_name or not ticker: return jsonify({'success': False})
    # Auto-append market suffix
    SUFFIX_MAP = {"HK": ".HK", "TW": ".TW", "TWO": ".TWO"}
    PAD_MAP = {"HK": 4, "CN": 6}
    if market in SUFFIX_MAP and "." not in ticker:
        if market in PAD_MAP and ticker.isdigit():
            ticker = ticker.zfill(PAD_MAP[market])
        ticker += SUFFIX_MAP[market]
    elif market == "CN" and "." not in ticker:
        if ticker.isdigit():
            ticker = ticker.zfill(6)
        SH_PREFIXES = ('600', '601', '603', '605', '688')
        SZ_PREFIXES = ('000', '001', '002', '003', '300', '301')
        if ticker[:3] in SH_PREFIXES:
            ticker += '.SS'
        elif ticker[:3] in SZ_PREFIXES:
            ticker += '.SZ'
        else:
            ticker += '.SS'
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

@app.route('/api/export')
def api_export():
    """Export watchlist and/or portfolio as JSON."""
    data = {"version": 1, "source": "pulse_free"}
    export_wl = request.args.get("watchlist", "1") == "1"
    export_pf = request.args.get("portfolio", "1") == "1"
    if export_wl:
        wl = load_watchlist()
        data["watchlist"] = {"categories": wl.get("categories", {}), "targets": wl.get("targets", {})}
    if export_pf:
        pf = load_portfolio()
        # Strip internal fields (id, user_id, sort_order, etc.)
        clean_pf = []
        for tx in pf:
            clean_tx = {k: v for k, v in tx.items() if k not in ('id', 'user_id', 'sort_order')}
            clean_pf.append(clean_tx)
        data["portfolio"] = clean_pf
    return jsonify(data)


@app.route('/api/import', methods=['POST'])
def api_import():
    """Import watchlist and/or portfolio. Merges with existing data."""
    import_data = request.get_json()
    if not import_data:
        return jsonify({"success": False, "error": "No data"})
    preview = {"watchlist": [], "portfolio": [], "watchlist_exists": [], "portfolio_exists": []}
    if "watchlist" in import_data:
        wl = load_watchlist()
        cats = wl.get("categories", {})
        for cat, tickers in import_data["watchlist"].get("categories", {}).items():
            for tk in tickers:
                if tk not in cats.get(cat, []):
                    cats.setdefault(cat, []).append(tk)
                    preview["watchlist"].append({"category": cat, "ticker": tk})
                else:
                    preview["watchlist_exists"].append({"category": cat, "ticker": tk})
        wl["categories"] = cats
        for tk, price in import_data["watchlist"].get("targets", {}).items():
            wl.setdefault("targets", {})[tk] = price
        save_watchlist(wl)
    if "portfolio" in import_data:
        pf = load_portfolio()
        existing = {(tx["ticker"].upper(), tx["date"]) for tx in pf}
        for tx in import_data["portfolio"]:
            key = (tx["ticker"].upper(), tx.get("date", ""))
            if key not in existing:
                pf.append(tx)
                existing.add(key)
                preview["portfolio"].append(tx)
            else:
                preview["portfolio_exists"].append(tx)
        save_portfolio(pf)
    return jsonify({"success": True, "preview": preview})


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
        config["bg_image"] = request.form.get("bg_image", "false") == "true"
        config["bg_opacity"] = float(request.form.get("bg_opacity", "0.55"))
    if get_is_pro():
        config["ai_timeout"] = int(request.form.get("ai_timeout", "60"))
        config["prompt_level"] = request.form.get("prompt_level", "balanced")
        config["custom_prompt"] = request.form.get("custom_prompt", "").strip()
        config["prompt_mode"] = request.form.get("prompt_mode", "style")
        # 📉 Risk Metrics (Pro) — parse + clamp/validate (spec §7.2)
        config["risk_period"] = int(request.form.get("risk_period", "90"))
        if config["risk_period"] not in RISK_PERIODS: config["risk_period"] = 90
        config["risk_method"] = request.form.get("risk_method", "historical")
        if config["risk_method"] not in RISK_METHODS: config["risk_method"] = "historical"
        config["risk_paths"] = max(1000, min(10000, int(request.form.get("risk_paths", "5000") or 5000)))
    config["language"] = request.form.get("language", "zh_tw")
    config["cash_balance"] = float(request.form.get("cash_balance", "0") or 0)
    config["primary_currency"] = request.form.get("primary_currency", "USD")
    config["secondary_currency"] = request.form.get("secondary_currency", "") or None
    # 📊 進階指數：checkbox 多選，過濾只留合法 key
    selected = request.form.getlist("extra_indices")
    config["extra_indices"] = [k for k in selected if k in INDEX_LIST]
    save_config(config)
    if get_is_pro():
        _invalidate_risk_cache()   # spec §6.2 — then background recompute, don't block redirect
        _start_risk_warmer()
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
    
    stocks, _, _, total_mv_primary, total_open_cost, prim_cur, prim_symbol, sec_cur, sec_symbol, prim_to_sec, fx_matrix = calculate_portfolio_matrix()
    open_stocks = [s for s in stocks if s['status'] == 'OPEN']
    if not open_stocks: return jsonify({'success': False, 'error': 'No open positions.'})
    
    # Build rich portfolio context
    total_pnl = total_mv_primary - total_open_cost
    total_roi = (total_pnl / total_open_cost * 100) if total_open_cost > 0 else 0
    
    # Market allocation
    market_mv = {}
    for s in open_stocks:
        mkt = s['market']
        market_mv[mkt] = market_mv.get(mkt, 0) + float(s.get('current_mv', '0').replace(',', '') or '0')
    alloc_lines = [f"  {m}: {prim_symbol}{v:,.2f} ({v/total_mv_primary*100:.1f}%)" for m, v in sorted(market_mv.items(), key=lambda x: -x[1]) if total_mv_primary > 0]
    
    holding_lines = []
    for s in open_stocks:
        danger = " ⚠️ STOP-LOSS TRIGGERED" if s.get('is_danger') else ""
        holding_lines.append(
            f"${s['ticker']} [{s['market']}] | Shares: {s['total_shares']} | "
            f"Avg Cost: ${s['avg_buy_price']} | Current: ${s['current_price']} | "
            f"P&L: {s['pnl_primary_str']} | ROI: {s['roi_str']}{danger}"
        )
    
    lang_map = {"zh_tw": "Traditional Chinese (繁體中文)", "zh_cn": "Simplified Chinese (簡體中文)", "en": "English"}
    lang = lang_map.get(config.get("language", "zh_tw"), "Traditional Chinese (繁體中文)")

    # Build summary strings for prompt templates
    summary_str = f"Total MV: {prim_symbol}{total_mv_primary:,.2f}, Cost: {prim_symbol}{total_open_cost:,.2f}, PnL: {prim_symbol}{total_pnl:+,.2f} ({total_roi:+.2f}%), Holdings: {len(open_stocks)}"
    holdings_str = "; ".join([f"{prim_symbol}{s['ticker']} [{s['market']}] Shs:{s['total_shares']} Cost:{prim_symbol}{s['avg_buy_price']} Now:{prim_symbol}{s['current_price']} PnL:{s['pnl_primary_str']} ROI:{s['roi_str']}" for s in open_stocks])
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
        prompt_text = f"You are a professional portfolio analyst. Provide a comprehensive portfolio analysis report in {lang}. Use markdown formatting with clear section headers.\n\n## Portfolio Overview\n- Total Market Value: {prim_symbol}{total_mv_primary:,.2f} {prim_cur}\n- Total Cost Basis: {prim_symbol}{total_open_cost:,.2f} {prim_cur}\n- Total P&L: {prim_symbol}{total_pnl:+,.2f} {prim_cur} ({total_roi:+.2f}%)\n- Number of Holdings: {len(open_stocks)}\n\n## Market Allocation\n{chr(10).join(alloc_lines) if alloc_lines else '  N/A'}\n\n## Holdings Detail\n{chr(10).join(holding_lines)}\n\n## Required Analysis Sections\n1. Overall Assessment\n2. Per-Stock Analysis\n3. Risk Alerts\n4. Actionable Suggestions\n\nKeep it concise. Use a summary table."
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
    stocks, _, _, total_mv_primary, total_open_cost, prim_cur, prim_symbol, sec_cur, sec_symbol, prim_to_sec, fx_matrix = calculate_portfolio_matrix()
    config = load_config()
    sec_cur = config.get('secondary_currency', 'HKD')
    return jsonify({'market_active': True, 'total_mv_primary_str': f"{total_mv_primary:,.2f}", 'total_mv_sec_str': f"{(total_mv_primary * prim_to_sec):,.2f}", 'prim_cur': prim_cur, 'prim_symbol': prim_symbol, 'sec_cur': sec_cur})

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

@app.route('/pulse_logo.jpg')
def pulse_logo():
    return send_from_directory(BASE_DIR, 'pulse_logo.jpg')

@app.route('/pulse.css')
def pulse_css():
    return send_from_directory(BASE_DIR, 'pulse.css')

@app.route('/api/config/upload_bg', methods=['POST'])
def api_upload_bg():
    if not get_is_pro():
        return jsonify({'error': 'Pro feature'}), 403
    file = request.files.get('bg')
    if not file:
        return jsonify({'success': False, 'error': 'No file'}), 400
    valid = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    if file.mimetype not in valid:
        return jsonify({'success': False, 'error': 'Unsupported format'}), 400
    os.makedirs(os.path.join(BASE_DIR, 'uploads'), exist_ok=True)
    path = os.path.join(BASE_DIR, 'uploads', 'bg.jpg')
    file.save(path)
    config = load_config()
    config['bg_image'] = True
    save_config(config)
    return jsonify({'success': True})

@app.route('/api/config/remove_bg', methods=['POST'])
def api_remove_bg():
    if not get_is_pro():
        return jsonify({'error': 'Pro feature'}), 403
    path = os.path.join(BASE_DIR, 'uploads', 'bg.jpg')
    if os.path.exists(path):
        os.remove(path)
    config = load_config()
    config['bg_image'] = False
    save_config(config)
    return jsonify({'success': True})

@app.route('/api/bg')
def serve_bg():
    path = os.path.join(BASE_DIR, 'uploads', 'bg.jpg')
    if not os.path.exists(path):
        return '', 404
    return send_from_directory(os.path.dirname(path), os.path.basename(path))

@app.route('/api/wl/render')
def api_wl_render():
    config = load_config()
    t = get_translations(config.get("language", "zh_tw"))
    return build_watchlist_html(t)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
