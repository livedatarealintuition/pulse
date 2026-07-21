# Changelog

## V1.715 — July 21, 2026 (15 fixes)

**Enhancements:**
- PULSE_HOME environment variable for portable deployment
- Free/Pro split architecture (IS_PRO flag + Jinja2 template guards)
- Local production Tailwind CSS build (45KB minified)
- Form accessibility: labels with for/id attributes
- Bilingual changelog (EN/ZH)
- Field labels added to buy/sell forms (i18n)
- Auto-refresh label includes unit (sec/秒)

**Bug Fixes:**
- checkTargetAlerts() undefined in Free mode
- deleteTickerFromCategory / draggedCat in wrong is_pro block
- Free mode overwrites Pro config fields on settings save
- JS escape for watchlist category names with single quotes
- Duplicate capital_recovered dictionary key (dead code)
- Hardcoded HK$ in realtime_feed JS updater
- Top card grid 2-column in Free mode (was 3, leaving blank)
- EUR/GBP FX rate direction correction (Yahoo indirect quote)
- API returns 0.0 triggers false danger alert → cache fallback
- onkeypress Enter key uses unescaped cat_name in watchlist

---

## V1.612 — July 20, 2026 (12 fixes)

**Features:**
- Multi-market buy/sell, AJAX trading, auto zero-padding
- Market filter tabs (All/US/HK/CN/TW/TWO)
- Sell commission deduction in P&L calculation

**Bug Fixes:**
- realtime_feed updates when any tracked market is open
- CN market auto-detect Shanghai (.SS) vs Shenzhen (.SZ)
- TWO market support (Taiwan OTC)
- Cache fallback on network error (prevents false alerts)
- Remove stray `?` character from price element ID

**Refactors:**
- Migrate data layer to yfinance library
- Batch fetch (_batch_fetch_prices) with TTL cache integration
- Auto-extend cache TTL to 4h when markets closed

**Tweaks:**
- Default refresh interval 30s + API limit tooltip (i18n)
- Watchlist uses batch fetch instead of N individual calls
- threading.Lock + atomic write for JSON race condition
- Pulse branding: logo, favicon, "Live Data · Real Intuition"

---

## V1.5 — July 19, 2026

- Initial multi-market portfolio dashboard
- Real-time quotes, buy/sell trade management
- Multi-currency (HKD/CNY/TWD/JPY/EUR/GBP)
- Watchlist with drag-drop, category/ticker CRUD
- i18n: zh_TW / zh_CN / EN
- Capital recovery tracker, ROI display
- Target price alerts
- Market status dots with zoneinfo timezone
