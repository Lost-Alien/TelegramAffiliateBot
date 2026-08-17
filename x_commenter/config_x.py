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
# Safety & Rate Limits (Safe Pacing: 10 replies/day total)
# ==========================================
MAX_REPLIES_PER_RUN = int(os.getenv("MAX_REPLIES_PER_RUN", "2"))
MAX_REPLIES_PER_DAY = int(os.getenv("MAX_REPLIES_PER_DAY", "10"))
MIN_DELAY_BETWEEN_REPLIES_SEC = int(os.getenv("MIN_DELAY_BETWEEN_REPLIES_SEC", "45"))
MAX_CHAR_LIMIT = 260
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")

# ==========================================
# Multi-Account Engagement Controls
# ==========================================
# Caps replies to any single account per day so engagement is spread across
# the whole TARGET_TECH_ACCOUNTS list instead of hammering one account.
MAX_REPLIES_PER_ACCOUNT_PER_DAY = int(os.getenv("MAX_REPLIES_PER_ACCOUNT_PER_DAY", "2"))

# How many target accounts get packed into a single Exa search query.
# Keeps Exa credit usage low: N accounts get scanned in ceil(N / batch) calls
# instead of N separate calls.
ACCOUNT_QUERY_BATCH_SIZE = int(os.getenv("ACCOUNT_QUERY_BATCH_SIZE", "4"))

# Free, credit-less fallback (authenticated twikit session, no Exa cost) used
# only when Exa search errors out or returns zero usable candidates.
ENABLE_ACCOUNT_FALLBACK_SCRAPER = os.getenv("ENABLE_ACCOUNT_FALLBACK_SCRAPER", "true").lower() in ("true", "1", "yes")

# ==========================================
# Repost-with-Own-Thoughts (Quote Tweet) Controls
# ==========================================
# Quote-tweeting (reposting a tweet with your own commentary attached) posts
# a brand-new tweet on your own timeline rather than a nested reply, so it
# gets its own daily/run budget instead of eating into MAX_REPLIES_PER_DAY.
ENABLE_QUOTE_REPOSTS = os.getenv("ENABLE_QUOTE_REPOSTS", "true").lower() in ("true", "1", "yes")
MAX_QUOTE_REPOSTS_PER_RUN = int(os.getenv("MAX_QUOTE_REPOSTS_PER_RUN", "1"))
MAX_QUOTE_REPOSTS_PER_DAY = int(os.getenv("MAX_QUOTE_REPOSTS_PER_DAY", "4"))

# Probability (0.0-1.0) that an eligible candidate becomes a quote-repost
# instead of a plain reply, when both budgets still have room. Keeps the mix
# of replies vs. reposts varied instead of always preferring one action.
QUOTE_REPOST_CHANCE = float(os.getenv("QUOTE_REPOST_CHANCE", "0.3"))

# ==========================================
# Curated Indian Tech Search Topics (LAST-RESORT fallback only)
# ==========================================
# Only used when account-targeted scanning below doesn't produce enough
# candidates — kept generic on purpose to conserve Exa credits.
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

# ==========================================
# Target Accounts — PRIMARY discovery source
# ==========================================
# Add/remove handles freely — the scanner automatically batches Exa queries,
# rotates daily, and enforces MAX_REPLIES_PER_ACCOUNT_PER_DAY, so this list
# can grow as large as you like without any other code changes.

# Reviewers / creators who cover new launches, comparisons & hands-on tests.
TECH_CREATOR_ACCOUNTS = [
    "geekyranjit",
    "beebomco",
    "techburner",
    "TechnicalGuruji",
    "TrakinTech",
    "GadgetsToUse",
    "91mobiles",
    "IGyaanTech",
    "MrWhosetheboss",
    "UnboxTherapy",
    "MKBHD",
    "JonProsser",
    "evleaks",
]

# Official brand / launch-event accounts — good source of fresh price & spec
# announcements to jump into early.
TECH_LAUNCH_ACCOUNTS = [
    "SamsungIndia",
    "OnePlus_IN",
    "Apple",
    "iQOOInd",
    "IndiaPOCO",
    "MotorolaIndia",
    "XiaomiIndia",
    "realmeIndia",
    "vivo_India",
    "GoogleIndia",
    "NothingIndia",
    "AsusIndia",
]

# Combined flat list actually used by the scanner.
TARGET_TECH_ACCOUNTS = TECH_CREATOR_ACCOUNTS + TECH_LAUNCH_ACCOUNTS

