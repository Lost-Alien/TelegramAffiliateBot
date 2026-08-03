# Multi-Channel Telegram Deal Auto-Poster & Link Converter

A Telegram Userbot application using **Telethon** that automatically monitors all joined third-party deal channels, extracts Amazon product links, replaces existing affiliate tags with your tag, and forwards/posts the converted deal posts (with images and text) to your target destination channels!

## Features

- 📢 **Multi-Channel Extraction**: Listens to all joined deal channels (or specific whitelisted channels).
- 🏷️ **Affiliate Tag Replacement**: In-place replacement of Amazon product URLs and `amzn.to` short links with your tag (e.g. `techselect-20`).
- 🖼️ **Media & Caption Preservation**: Preserves photos, deal image attachments, and post text layout.
- 🔁 **Deduplication Engine**: Prevents reposting identical deals.
- 👥 **Multi-Destination Serving**: Forward and publish converted deals to multiple channels or target Telegram accounts simultaneously.

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
AFFILIATE_TAG=techselect-20
TARGET_CHANNELS=@my_deal_channel
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Login Session (First Time Only)
Run the session login helper once to authenticate your Telegram account:
```bash
python session_login.py
```

### 5. Run Auto-Poster
```bash
python main.py
```

### 6. Run Unit Tests
```bash
python -m pytest
```
