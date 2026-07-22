# Pulse Changelog

## V1.820 (2026-07-23)
- Editable AI prompt with 3 presets: Strict / Balanced / Relaxed
- Prompt mode toggle: use preset style or custom prompt
- i18n complete rebuild (zh_tw / zh_cn / en)
- Custom prompt supports {summary} {holdings} {alloc} {lang} variables

## V1.815 (2026-07-23)
- API key confirmation dialog before AI calls (skipped for local LLMs)
- Smart error messages with i18n (timeout hints, connection help)
- Weight % column in holdings table (Pro)
- Market Distribution card with progress bars (Pro)
- Cash Ratio card with configurable cash balance (Pro)

## V1.87 (2026-07-22)
- AI report modal popup (replaced inline section)
- Form label accessibility (for/id on all inputs)
- JS syntax fixes (regex in Jinja2)
- AI prompt language follows user setting
- Settings split into General / AI Model tabs
- Configurable timeout (10-300s)

## V1.8 (2026-07-22)
- Rich portfolio prompt: MV, P&L, ROI, allocation, stop-loss flags
- Local inference presets: Ollama, vLLM, LM Studio with auto-fill

## V1.716 (2026-07-22)
- Remove deprecated Crucix macro report integration

## V1.715 (2026-07-21)
- PULSE_HOME env support
- Free/Pro architecture split (pulse_free.py + pulse_pro.py)
- Local Tailwind CSS build
- Form label fixes, JS escape, EUR/GBP FX fix, cache fallback

## V1.612 (2026-07-20)
- yfinance refactor with batch fetch + TTL cache
- Atomic JSON writes
- TWO (Taiwan OTC) market support
- Rebrand to Pulse

## V1.5 (2026-07-19)
- Initial release
- Multi-market dashboard (US/HK/CN/TW)
- Buy/Sell transaction tracking
- i18n (zh_tw / zh_cn / en)
- Watchlist with categories + drag-drop
- Multi-currency display
