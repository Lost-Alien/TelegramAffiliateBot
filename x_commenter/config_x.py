"""
config_x.py — Configuration and credentials for the X Auto-Commenter module.
Powered by Exa AI for discovery and Twikit (Cookie Auth) for free posting.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# ==========================================
# Exa AI API Configuration
# ==========================================
EXA_API_KEY = os.getenv("EXA_API_KEY", "ddffd3ea-5e2d-44b4-90b4-257d62150788").strip()

# ==========================================
# Twitter / X Cookie Auth Credentials (@techselect_blog)
# ==========================================
# Option 1: Direct Cookie Tokens from Chrome DevTools (Fastest & Easiest)
TWITTER_AUTH_TOKEN = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
TWITTER_CT0 = os.getenv("TWITTER_CT0", "").strip()

# Option 2: Base64 encoded cookies.json from GitHub Secrets
TWITTER_COOKIES_B64 = os.getenv("TWITTER_COOKIES_B64", "").strip()

# Local/runtime cookie file path
COOKIES_PATH = Path(__file__).resolve().parent / "cookies.json"


# ==========================================
# Upstash Redis Configuration
# ==========================================
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()

# ==========================================
# Safety & Rate Limits (Hourly Pacing: 10 replies/run)
# ==========================================
MAX_REPLIES_PER_RUN = int(os.getenv("MAX_REPLIES_PER_RUN", "10"))
MAX_REPLIES_PER_DAY = int(os.getenv("MAX_REPLIES_PER_DAY", "240"))
MIN_DELAY_BETWEEN_REPLIES_SEC = int(os.getenv("MIN_DELAY_BETWEEN_REPLIES_SEC", "25"))
MAX_CHAR_LIMIT = 260
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")

# ==========================================
# Curated Indian Tech Search & Target Topics
# ==========================================
EXA_SEARCH_TOPICS = [
    "Samsung Galaxy launch India price review",
    "OnePlus India smartphone launch price comparison",
    "Apple iPhone India sale card discount offer",
    "best gaming laptop under 1 lakh India benchmark",
    "best phone under 30000 India camera battery",
    "iQOO vs Redmi vs Realme phone comparison India",
    "MacBook Air M3 vs M4 price India student discount",
    "Amazon Great Indian Festival sale laptop tech deals",
]

TARGET_TECH_ACCOUNTS = [
    "geekyranjit",
    "beebomco",
    "techburner",
    "SamsungIndia",
    "OnePlus_IN",
    "Apple",
    "iQOOInd",
    "IndiaPOCO",
    "MotorolaIndia",
]

