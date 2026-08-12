# Affiliate Telegram Bot

A high-performance Python Telegram bot that automatically detects Amazon product links in messages and converts them into Amazon Affiliate links with your tag.

Inspired by [Aritzherrero4/AffiliateTelegramBot](https://github.com/Aritzherrero4/AffiliateTelegramBot).

## Features

- 🔍 **Automatic ASIN Extraction**: Detects product IDs from `/dp/`, `/gp/product/`, `/gp/aw/d/`, `/product/`, etc.
- 🔗 **Shortened URL Expansion**: Resolves `amzn.to`, `amzn.in`, `amzn.eu` shortened links automatically.
- 🌍 **Multi-Country Support**: Configurable for `amazon.com`, `amazon.in`, `amazon.es`, `amazon.co.uk`, `amazon.de`, etc.
- 🤖 **Group & Direct Chat Support**: Responds in private DMs or automatically in Telegram groups.
- 🛒 **Rich Formatting & Buttons**: Includes interactive Telegram inline buttons.
- 🐳 **Docker & Docker-Compose Ready**: Simple one-command deployment.

---

## Setup Instructions

### 1. Prerequisites
- Python 3.9+ installed
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Amazon Associates Tag (e.g., `mytag-20`)

### 2. Configuration
Copy `.env.example` to `.env` and fill in your details:
```bash
cp .env.example .env
```

Edit `.env`:
```env
TELEGRAM_TOKEN=your_telegram_bot_token_here
AFFILIATE_TAG=your_affiliate_tag_here
AMAZON_DOMAIN=amazon.com
```

### 3. Install & Run Locally

```bash
pip install -r requirements.txt
python bot.py
```

### 4. Running Unit Tests

```bash
pytest
```

### 5. Running with Docker

```bash
docker-compose up -d --build
```

---

## Multi-Channel Deal Auto-Poster & Web UI Monitor (`TelegramDealAutoPoster/`)

For advanced multi-channel monitoring using a Telegram Userbot (Telethon), see [`TelegramDealAutoPoster/`](file:///c:/Users/conne/Downloads/AffiliateTelegramBot/TelegramDealAutoPoster/README.md).

### Highlights:
- 📡 **Channel Auto-Discovery**: Automatically lists all joined channels and groups (`/api/channels`).
- 🌐 **Live Web UI Dashboard**: Localhost monitoring interface at **http://127.0.0.1:8000** showing real-time metrics, recent deal conversions, and live SSE console logs.
- 🔁 **SQLite Deduplication & Rate Limiting**: Persistent 7-day deduplication cache and configurable per-hour posting limits.
- 🛡️ **Burner Account Warm-Up**: Configurable `WARMUP_HOURS` to log deals silently without posting for new accounts.

To run the Multi-Channel Auto-Poster:
```bash
cd TelegramDealAutoPoster
pip install -r requirements.txt
python auto_login.py  # 1-time Telegram account login
python main.py        # Starts Auto-Poster + Web UI Monitor on http://127.0.0.1:8000
```

---

## License

GPL-3.0 License
