import os
import logging
import random
from dotenv import load_dotenv

# Load environment variables from .env file if available
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TOKEN")
AFFILIATE_TAG = os.getenv("AFFILIATE_TAG", "my-affiliate-tag-20")
AFFILIATE_TAGS = [t.strip() for t in os.getenv("AFFILIATE_TAGS", AFFILIATE_TAG).split(",") if t.strip()] or [AFFILIATE_TAG]
AMAZON_DOMAIN = os.getenv("AMAZON_DOMAIN", "amazon.com")
DEV_CHAT_ID = os.getenv("DEV_CHAT_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
SOURCE_CHANNEL_ID = os.getenv("SOURCE_CHANNEL_ID", "").strip()
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://techselect.blog/")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Normalize domain
if AMAZON_DOMAIN.startswith("http://") or AMAZON_DOMAIN.startswith("https://"):
    AMAZON_DOMAIN = AMAZON_DOMAIN.split("://")[-1]
if AMAZON_DOMAIN.startswith("www."):
    AMAZON_DOMAIN = AMAZON_DOMAIN[4:]
AMAZON_DOMAIN = AMAZON_DOMAIN.rstrip("/")

# Set up logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO)
)
logger = logging.getLogger("AffiliateTelegramBot")

# Suppress verbose HTTP logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

def get_affiliate_tag() -> str:
    """Return one of the configured affiliate tags at random (supports multiple tags)."""
    return random.choice(AFFILIATE_TAGS)

def _as_chat_id(value: str):
    """Return chat id as int when numeric (e.g. -100...), else as string (e.g. @username)."""
    if value.lstrip("-").isdigit():
        return int(value)
    return value

def channel_chat_id():
    return _as_chat_id(CHANNEL_ID)

def source_chat_id():
    return _as_chat_id(SOURCE_CHANNEL_ID)
