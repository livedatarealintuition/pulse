# Pulse Changelog

Versioning: `V1.<session>.<item>`. Every release is also listed inside the app
itself (`CHANGELOG` in `pulse_free.py`), which is the source of truth; entries
marked *backfilled* were recovered from there after this file fell behind.

## V1.14.0 (2026-08-13) — Risk Metrics card (Pro)
- Transaction-aware daily value reconstruction (BUY/SELL × closes, cash-flow-adjusted returns, CLOSED positions excluded)
- Five metrics: Sharpe, Sortino, volatility, maximum drawdown, VaR-95
- Three methods: historical / parametric / Monte Carlo (numpy-vectorised)
- Settings tab: period 90 days – 5 years, method, Monte Carlo paths 1,000–10,000
- 6-hour result cache + 3-hour background warmer
- Three-language labels and tooltips, plus a standalone validation script (`risk_metrics.py`)

## V1.13.0 (2026-08-13) — Earnings calendar
- Upcoming earnings dates for every portfolio ticker (OPEN and CLOSED positions)
- `yfinance` `Ticker.calendar` with an `earnings_dates` fallback
- 6-hour TTL cache, 30-day lookahead

## V1.12.2 (2026-08-12) — Compact index ticker
- Index ticker in the top bar, between market status and refresh
- Settings: hard limit of 5 indices, warning below 1
- Clickable filter from the ticker

## V1.12.1 (2026-08-11) — User-selected indices
- All 13 indices selectable in Settings (counter, minimum-5 hint, empty-state notice)
- Fixed defaults removed

## V1.12.0 (2026-08-08) — Indices & FX dashboard
- Five live market indices (S&P 500, Hang Seng, Shanghai, TAIEX, TPEx)
- Currency rates row, both cached from yfinance

## V1.11.3 — AJAX watchlist reload
- Add / delete / rename / reorder categories and tickers without a page reload
- Loading overlay while the fragment refreshes

## V1.11.2 — i18n fixes
- English label for the background settings tab
- Import/export description labels

## V1.11.1 (2026-08-02) — Custom background image
- Upload, remove and an opacity slider, in their own Settings tab

## V1.10.17 – V1.10.11 (2026-08-02) — Multi-currency Phase 2
- Primary currency selectable (USD / HKD / TWD / CNY / JPY / EUR / GBP); secondary display currency
- FX cross-rate matrix from yfinance (5-minute cache); buy/sell price labels follow the ticker's market
- Every portfolio calculation moved to the primary currency
- Fixes: FX cross-rate formula was inverted (`src/dst` → `dst/src`), buy-price label DOM timing, `HIGHEST_PRICE_CACHE` cleared per request, ATR stop-loss and performance-card history converted to primary currency, `avg_buy_price` converted
- Currency symbols cleaned up (HKD/TWD show `$`, not `HK$`/`NT$`)

## V1.10.1 — Financial disclaimer
- Disclaimer banner on all pages

## Session 9 — V1.9.1 – V1.9.5
- **V1.9.5** Performance card: Today / WTD / MTD / YTD returns from historical prices
- **V1.9.4** Watchlist multi-market support; JSON import/export for watchlist and portfolio
- **V1.9.3** Company names in ticker display, watchlist sidebar indicator, `$` prefix removed
- **V1.9.2** Remove CLOUD_MODE — pure self-hosted Flask codebase (the cloud app became a separate repo)
- **V1.9.1** CLOUD_MODE: Supabase auth, dark mode, logout, data-layer dispatch

## Session 8 — V1.8 – V1.820 (2026-07-22 ~ 23) *backfilled*
- **V1.820** Editable AI prompt with Strict / Balanced / Relaxed presets; prompt-mode toggle; custom prompt with `{summary}` `{holdings}` `{alloc}` `{lang}`; weight-% column, market distribution card and cash ratio card (Pro); API-key confirmation dialog (skipped for local endpoints); smart i18n error messages; Settings split into General / AI; configurable AI timeout (10–300 s); AI report modal; form-label accessibility; full i18n rebuild (zh_tw / zh_cn / en)
- **V1.8** Rich portfolio prompt with market value, P&L, ROI, allocation and stop-loss flags; local inference presets (Ollama / vLLM / LM Studio) with auto-fill

## Session 7 — V1.715 – V1.716 (2026-07-21)
- **V1.716** Remove the deprecated Crucix macro-report integration
- **V1.715** `PULSE_HOME` env var, Free/Pro architecture, local CSS, form labels, JS escaping, EUR/GBP FX fix, cache fallback

## Session 6 — V1.612 (2026-07-20)
- yfinance refactor with batch fetch and TTL cache
- Atomic JSON writes, TWO market support, Pulse rebrand

## Session 5 — V1.5.1 (2026-07-19) — Initial release
- Multi-market dashboard (US / HK / CN / TW), buy/sell tracking
- i18n (zh_tw / zh_cn / en), watchlist with drag-and-drop, multi-currency
