# Multi-Channel Telegram Deal Auto-Poster & Link Converter

A Telegram Userbot application using **Telethon** that automatically monitors all joined third-party deal channels, extracts Amazon product links, replaces existing affiliate tags with your tag, and forwards/posts the converted deal posts (with images and text) to your target destination channels!

## Features

- 📢 **Multi-Channel Extraction**: Listens to all joined deal channels (or specific whitelisted channels).
- 🏷️ **Affiliate Tag Replacement**: In-place replacement of Amazon product URLs and `amzn.to` short links with your tag (e.g. `techselect-20`).
- 🖼️ **Media & Caption Preservation**: Preserves photos, deal image attachments, and post text layout.
- 🔁 **Deduplication Engine**: Prevents reposting identical deals with SQLite persistent cache (7-day TTL).
- 👥 **Multi-Destination Serving**: Forward and publish converted deals to multiple channels or target Telegram accounts simultaneously.
- 🌐 **Web UI Monitor Dashboard**: Real-time localhost web interface (`http://127.0.0.1:8000`) showing KPIs, live SSE console logs, and recent deals.
- 📡 **Channel Auto-Discovery**: Automatically scans and lists all joined channels/groups (`/api/channels`) to easily discover deal source channels.
- 🛡️ **Burner Account Warm-Up**: Configurable `WARMUP_HOURS` to log deals silently before live posting.

---

## Setup Instructions

### 1. Get Telegram API Credentials
Go to [https://my.telegram.org/apps](https://my.telegram.org/apps), log in with your phone number, and copy your `API_ID` and `API_HASH`.

### 2. Configure `.env`
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env`:
```env
API_ID=12345678
API_HASH=0123456789abcdef0123456789abcdef
AFFILIATE_TAGS=tagone-20,tagtwo-20
TARGET_CHANNELS=@TechSelectDeals
WARMUP_HOURS=24
WEB_HOST=127.0.0.1
WEB_PORT=8000
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Login Session (First Time Only)
Run the session login helper once to authenticate your Telegram account:
```bash
python auto_login.py
```

### 5. Run Auto-Poster & Web Monitor
```bash
python main.py
```
- Open your browser to **http://127.0.0.1:8000** to monitor live activity, view discovered channels, and inspect converted deals.

### 6. Run Unit Tests
```bash
python -m pytest tests/ -v
```
