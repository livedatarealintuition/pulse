# Changelog

All notable changes to Pulse will be documented in this file.

## V2.0 (2026-07-21)

- Bilingual changelog (EN/ZH)
- Field labels added to buy/sell forms (i18n)
- Auto-refresh label includes unit (sec/秒)
- GitHub release with README, screenshots, .gitignore

## V1.99

- UI: Add field labels to buy/sell forms, commission single-column / 買入/賣出表單加入欄位標籤

## V1.98

- Fix: Fallback to cached price when API returns 0.0 (false danger alert) / API 回傳 0.0 時 fallback

## V1.97

- Fix: EUR/GBP FX rate direction (Yahoo indirect quote → use division) / EUR/GBP 匯率修正

## V1.96

- Fix: Free mode top card grid uses 2 cols (was 3, leaving blank) / 頂部卡片 2 欄

## V1.95

- Fix: realtime_feed uses dynamic currency from config instead of hardcoded HK$ / 動態貨幣

## V1.94

- Cleanup: Remove duplicate capital_recovered key (dead code) / 移除死碼

## V1.93

- Fix: JS escape for watchlist category names with single quotes / 單引號 escape

## V1.92

- Fix: Free mode no longer overwrites Pro config fields on save / 設定儲存不覆蓋 Pro 欄位

## V1.91

- Fix: deleteTickerFromCategory / draggedCat moved out of is_pro block / JS ReferenceError 修復

## V1.9

- Enhance: Local Tailwind CSS production build (45KB minified)
- Accessibility: form label for= associations, field id attributes
- Fix: Settings form grid div balanced inside is_pro block

## V1.869

- Fix: checkTargetAlerts() undefined in Free mode (wrapped call in is_pro guard)

## V1.868

- Refactor: Free/Pro split architecture (IS_PRO flag + Jinja2 template guards)
- New files: pulse_free.py, pulse_pro.py

## V1.867

- Refactor: Hardcoded path replaced with PULSE_HOME environment variable

## V1.866

- Fix: threading.Lock + atomic write (os.replace) for JSON race condition prevention
- Branding: Pulse logo + favicon, "Live Data · Real Intuition" slogan

## V1.865

- Fix: build_watchlist_html uses _batch_fetch_prices (was N individual yfinance calls)

## V1.864

- Tweak: Default refresh interval 30s + tooltip explaining API limits (i18n)

## V1.863

- Optimize: Auto-extend cache TTL to 4h when markets closed (get_effective_ttl)

## V1.862

- Optimize: _batch_fetch_prices integrated with TTL cache

## V1.861

- Refactor: Migrate data layer to yfinance library (auto cookie/crumb + batch fetch)

## V1.86

- Fix: Remove stray `?` character from price element ID

## V1.85

- Fix: Fallback to cached price on network error instead of returning 0.0

## V1.84

- Fix: Add TWO market support (Taiwan OTC)

## V1.83

- Fix: Auto-detect CN market suffix .SS/.SZ by ticker prefix

## V1.82

- Fix: realtime_feed updates when any tracked market is open (not just US)

## V1.81

- Fix: Deduct sell commission from total proceeds in calculate_portfolio_matrix()

## V1.8

- Feature: Market filter tabs, multi-market buy/sell, AJAX trading, auto zero-pad

## V1.7

- Feature: Market status dots (US/HK/CN/TW), zoneinfo timezone support

## V1.6

- Feature: Multi-currency support (HKD/CNY/TWD/JPY/EUR/GBP)

## V1.5

- Feature: Target price alerts (DOM-based instant check, no reload)

## V1.4

- Feature: Watchlist drag-and-drop reorder + target price notifications

## V1.3

- Feature: Editable watchlist sidebar (category/ticker CRUD)

## V1.2

- Feature: Total ROI display, capital recovery tracker (💰 badge)

## V1.1

- Feature: i18n support (zh_TW/zh_CN/EN), real-time cost estimation

## V1.0

- Initial release: Portfolio dashboard with buy/sell, real-time quotes
