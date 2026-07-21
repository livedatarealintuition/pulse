# Pulse

**Live Data · Real Intuition**

A lightweight, self-hosted multi-market portfolio dashboard. Track your stock holdings across US, HK, CN, TW, and TWO markets with real-time prices, P&L analytics, and a drag-and-drop watchlist — all in a single Python file.

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Python: 3.9+](https://img.shields.io/badge/python-3.9+-blue)

---

## Screenshots

| Dashboard | Watchlist |
|:---------:|:---------:|
| ![Pulse Dashboard](screenshots/dashboard.png) | ![Watchlist](screenshots/watchlist.png) |

| Settings | Multi-Currency |
|:--------:|:--------------:|
| ![Settings](screenshots/settings.png) | ![Currency](screenshots/currency.png) |

---

## Features

### Multi-Market Portfolio
- Real-time prices across **US / HK / CN (.SS/.SZ) / TW / TWO** markets
- Batch fetching via yfinance — one API call for all tickers
- Total market value, P&L, ROI, per-stock breakdown
- Buy/sell trade management with commission tracking
- AJAX trading — no page refresh
- Auto zero-padding for HK (4-digit) and CN (6-digit) ticker codes

### Visual Dashboard
- Market status indicator dots (green = open, red = closed) with zoneinfo timezone
- Market filter tabs: All / US / HK / CN / TW / TWO
- Click-to-expand transaction history per stock
- Capital recovery tracker (💰 badge when realized profit ≥ total cost)

### Multi-Currency
- Secondary currency display: HKD / CNY / TWD / JPY / EUR / GBP
- Real-time exchange rates

### Watchlist
- Slide-out sidebar with category-based organization
- Category CRUD: create, rename, delete groups
- Ticker CRUD: add/remove tickers per category
- HTML5 drag-and-drop category reordering

### i18n
- Three languages: 繁體中文 / 简体中文 / English
- Dynamic switching, no reload needed

### Performance
- TTL cache (30s during market hours, auto-extends to 4h when closed)
- Atomic JSON writes (threading.Lock + os.replace)
- Configurable refresh interval (10s–∞, default 30s)

### Pro Upgrade 🚧 Coming Soon
Pulse will have a **Pro tier** with additional features (currently in development):
- ⚡ AI audit reports (portfolio health analysis)
- 🎯 Target price alerts
- AI provider/model configuration

Stay tuned — these features are actively being built.

---

## Quick Start

### Requirements
- Python 3.9+
- Linux / macOS / WSL

### Install

```bash
git clone https://github.com/livedatarealintuition/pulse.git
cd pulse
pip install -r requirements.txt
```

### Configure

```bash
cp system_config.example.json system_config.json
```

### Run

```bash
# Default: data files stored next to the script
python3 pulse_free.py

# Or set a custom data directory
export PULSE_HOME=/path/to/your/data
python3 pulse_free.py
```

Open `http://localhost:5000` in your browser.

### Rebuild CSS (optional)

`pulse.css` is pre-built and committed. To regenerate after changing Tailwind classes:

```bash
# 1. Install Tailwind CLI (one-time)
curl -sL https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 -o tailwindcss
chmod +x tailwindcss

# 2. Extract classes from Python source
grep -oP 'class="\K[^"]+' pulse_free.py | tr ' ' '
' | sort -u | grep -v '[{{%]' > /tmp/classes.txt
python3 -c "print('<div class="' + ' '.join(open('/tmp/classes.txt').read().split()) + '"></div>')" > pulse_classes.html

# 3. Build
echo '@import "tailwindcss";' > input.css
./tailwindcss --input input.css --output pulse.css --minify

# 4. Clean up
rm input.css pulse_classes.html
```

### Production

```bash
PULSE_HOME=/data/pulse nohup python3 pulse_free.py > /tmp/pulse.log 2>&1 &
```

---

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PULSE_HOME` | Directory for `portfolio.json`, `watchlist.json`, `system_config.json` | Script directory |

---

## File Structure

```
pulse/
├── pulse_free.py              # Main application (Free version)
├── pulse.css                  # Pre-built Tailwind CSS (production)
├── pulse_logo.png             # Brand logo
├── requirements.txt           # Python dependencies
├── system_config.example.json # Config template
├── README.md
└── .gitignore
```

Data files (gitignored):
```
portfolio.json          # Your holdings — NOT committed
watchlist.json          # Your watchlist — NOT committed
system_config.json      # Your settings/keys — NOT committed
```

---

## Markets Supported

| Market | Ticker Format | Status Dot |
|--------|--------------|------------|
| US | `AAPL` | ● US |
| Hong Kong | `0005.HK` | ● HK |
| Shanghai | `600036.SS` | ● CN |
| Shenzhen | `000001.SZ` | ● CN |
| Taiwan | `2330.TW` | ● TW |
| Taiwan OTC | `6488.TWO` | ● TWO |

---

## License

MIT — see [LICENSE](LICENSE) file.

---

## Privacy — 100% Local Data Privacy

Pulse runs entirely on your machine. **No data ever leaves your server.**

- No telemetry, no analytics, no tracking
- `portfolio.json`, `watchlist.json`, `system_config.json` stay on your disk
- The only external requests are to Yahoo Finance (stock prices) and exchange rate APIs
- No accounts, no cloud sync, no third-party data sharing
- You own your data — always

---

## Pro Version 🚧 Coming Soon

Pulse Pro (AI-powered portfolio analysis, target price alerts, AI backend configuration) is currently in development. Stay tuned for release.
