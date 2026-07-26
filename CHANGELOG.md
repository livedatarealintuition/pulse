# Pulse Changelog

## V1.9 — Unified Codebase (2026-07-26)

- **CLOUD_MODE**: Single pulse_free.py for selfhosted (n200) + cloud (Render)
- **Auth**: Supabase JWT via cookie, Google OAuth + email/pw
- **Data layer**: JSON files (selfhosted) / Supabase (cloud) dispatch
- **Dashboard**: Same template for both modes (Tailwind CDN for cloud)
- **Logout**: Cloud mode logout button
- **Deploy**: Render auto-deploy from `livedatarealintuition/pulse`

## Session 8 — V1.820 (2026-07-22 ~ 23)
**20 items total**

### V1.820
- Editable AI prompt with 3 presets: Strict / Balanced / Relaxed
- Prompt mode toggle: Analysis Style vs Custom Prompt
- Custom prompt with {summary} {holdings} {alloc} {lang} variables
- Weight% column in holdings table (Pro)
- Market Distribution card with progress bars (Pro)
- Cash Ratio card + configurable cash balance (Pro)
- API key confirmation dialog (skipped for local LLMs)
- Smart error messages with i18n (timeout/connection hints)
- Settings split into General / AI Model tabs
- Configurable AI timeout (10-300s)
- AI report modal popup
- Form label accessibility (for/id on all fields)
- AI prompt language follows user setting
- Complete i18n rebuild (zh_tw/zh_cn/en)

### V1.8
- Rich portfolio prompt with MV, P&L, ROI, allocation, stop-loss flags
- Local inference presets: Ollama, vLLM, LM Studio with auto-fill

## Session 7 — V1.715 → V1.716 (2026-07-21)
**16 items total**

- V1.716: Remove deprecated Crucix macro report integration
- V1.715: PULSE_HOME env, Free/Pro architecture, local CSS, form labels, JS escape, EUR/GBP FX fix, cache fallback

## Session 6 — V1.612 (2026-07-20)
**12 items**

- yfinance refactor with batch fetch + TTL cache
- Atomic JSON writes, TWO market, Pulse rebrand

## Session 5 — V1.5 (2026-07-19)
**Initial release**

- Multi-market dashboard (US/HK/CN/TW), buy/sell tracking
- i18n (zh_tw/zh_cn/en), watchlist with drag-drop, multi-currency
