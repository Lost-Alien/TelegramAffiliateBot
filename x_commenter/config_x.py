"""
config_x.py — Configuration and credentials for the X Auto-Commenter module.
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
# Twitter / X API Credentials (@techselect_blog)
# ==========================================
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "").strip()
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "").strip()
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "").strip()
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "").strip()
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
TWITTER_CLIENT_ID = os.getenv("TWITTER_CLIENT_ID", "").strip()
TWITTER_CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET", "").strip()

# ==========================================
# Upstash Redis Configuration
# ==========================================
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()

# ==========================================
# Safety & Rate Limits (Strict anti-ban policies)
# ==========================================
MAX_REPLIES_PER_RUN = int(os.getenv("MAX_REPLIES_PER_RUN", "2"))
MAX_REPLIES_PER_DAY = int(os.getenv("MAX_REPLIES_PER_DAY", "6"))
MIN_DELAY_BETWEEN_REPLIES_SEC = int(os.getenv("MIN_DELAY_BETWEEN_REPLIES_SEC", "180"))
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
