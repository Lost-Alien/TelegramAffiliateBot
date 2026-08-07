import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "")
SESSION_NAME = os.getenv("SESSION_NAME", "userbot_session")

# Affiliate Tags Support (Comma-separated list of tags for round-robin rotation)
AFFILIATE_TAGS_RAW = os.getenv("AFFILIATE_TAGS") or os.getenv("AFFILIATE_TAG", "onamztechst01-21,techstor0caaf-21")
AFFILIATE_TAGS = [t.strip() for t in AFFILIATE_TAGS_RAW.split(",") if t.strip()]

DEFAULT_AMAZON_DOMAIN = os.getenv("AMAZON_DOMAIN", "amazon.com")

# Channel Configurations (Comma-separated channel usernames or numeric IDs)
SOURCE_CHANNELS_RAW = os.getenv("SOURCE_CHANNELS", "")
SOURCE_CHANNELS = [ch.strip() for ch in SOURCE_CHANNELS_RAW.split(",") if ch.strip()]

TARGET_CHANNELS_RAW = os.getenv("TARGET_CHANNELS", "")
TARGET_CHANNELS = [ch.strip() for ch in TARGET_CHANNELS_RAW.split(",") if ch.strip()]

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Web UI Monitor Configuration (binds 127.0.0.1 only by default)
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))
MONITOR_API_TOKEN = os.getenv("MONITOR_API_TOKEN", "").strip()

# Optional knobs
WARMUP_HOURS = int(os.getenv("WARMUP_HOURS", "0"))

RATE_LIMIT_HR = int(os.getenv("RATE_LIMIT_HR", "10"))
MIN_DELAY_S = int(os.getenv("MIN_DELAY_S", "30"))
MAX_DELAY_S = int(os.getenv("MAX_DELAY_S", "90"))

ALERT_CHAT_ID = os.getenv("ALERT_CHAT_ID", "").strip()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO)
)
logger = logging.getLogger("TelegramDealAutoPoster")
