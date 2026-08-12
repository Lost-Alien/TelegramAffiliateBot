"""
poster.py — Standalone CSV-queue Twitter Poster based on ReactorcoreGames/TwitterAutoPoster.

Supports OAuth 1.0a signed direct requests, reading posts from CSV, maintaining state in state.json,
and falling back gracefully when API limits or network issues occur.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.parse
from datetime import datetime, timezone
import requests

logger = logging.getLogger(__name__)

CSV_FILE = os.path.join(os.path.dirname(__file__), "posts.csv")
STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")


def _get_api_credentials():
    api_key = os.environ.get("TWITTER_API_KEY", "").strip()
    api_secret = os.environ.get("TWITTER_API_SECRET", "").strip()
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "").strip()
    access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "").strip()

    try:
        import config  # type: ignore
        api_key = api_key or getattr(config, "TWITTER_API_KEY", "")
        api_secret = api_secret or getattr(config, "TWITTER_API_SECRET", "")
        access_token = access_token or getattr(config, "TWITTER_ACCESS_TOKEN", "")
        access_token_secret = access_token_secret or getattr(config, "TWITTER_ACCESS_TOKEN_SECRET", "")
    except Exception:
        pass

    return api_key, api_secret, access_token, access_token_secret


def create_oauth_signature(method: str, url: str, params: dict, api_secret: str, token_secret: str) -> str:
    """Create OAuth 1.0a signature for Twitter API."""
    sorted_params = sorted(params.items())
    param_string = "&".join([f"{k}={v}" for k, v in sorted_params])
    base_string = f"{method}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_string, safe='')}"
    signing_key = f"{urllib.parse.quote(api_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"
    
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    return signature


def create_oauth_header(method: str, url: str, api_key: str, api_secret: str, access_token: str, token_secret: str, params: dict = None) -> str:
    """Create OAuth 1.0a authorization header for Twitter API."""
    if params is None:
        params = {}
    
    oauth_params = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": secrets.token_urlsafe(32),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }
    
    all_params = {**oauth_params, **params}
    encoded_params = {k: urllib.parse.quote(str(v), safe="") for k, v in all_params.items()}
    
    signature = create_oauth_signature(method, url, encoded_params, api_secret, token_secret)
    oauth_params["oauth_signature"] = signature
    
    oauth_header = "OAuth " + ", ".join([f'{k}="{urllib.parse.quote(str(v), safe="")}"' for k, v in oauth_params.items()])
    return oauth_header


def init_csv_and_state():
    """Ensure posts.csv and state.json exist with headers."""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["title", "url", "hashtags", "created_at"])

    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_row_index": -1, "last_post_time": None, "total_posts": 0}, f, indent=2)


def append_to_csv_queue(title: str, url: str, hashtags: str = "#TechDeals #TechSelect #Ad") -> bool:
    """Append a deal item into the CSV fallback queue."""
    init_csv_and_state()
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([title, url, hashtags, now_iso])
        logger.info("Queued deal into posts.csv queue ✓ — Title: %s", title[:40])
        return True
    except Exception as e:
        logger.error("Failed to append to CSV queue: %s", e)
        return False


def post_next_from_csv() -> tuple[bool, str]:
    """Read next unposted row from posts.csv, attempt post to Twitter API v2."""
    init_csv_and_state()
    api_key, api_secret, access_token, access_token_secret = _get_api_credentials()

    if not all([api_key, api_secret, access_token, access_token_secret]):
        return False, "Twitter API credentials missing"

    # Read state
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    # Read CSV rows
    rows = []
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if row:
                rows.append(row)

    if not rows:
        return False, "posts.csv is empty"

    next_index = state.get("last_row_index", -1) + 1
    if next_index >= len(rows):
        # Loop around or stop
        next_index = 0

    row = rows[next_index]
    title = row[0] if len(row) > 0 else "Tech Deal"
    url = row[1] if len(row) > 1 else ""
    hashtags = row[2] if len(row) > 2 else "#TechDeals"

    tweet_text = f"⚡ {title}\n\n🛒 Check Price: {url}\n🌐 More Deals: https://techselect.blog\n\n{hashtags}".strip()
    if len(tweet_text) > 280:
        # X t.co link counting replaces URLs with 23 chars; truncate title if total raw text exceeds 280
        tweet_text = tweet_text[:277] + "..."

    # Endpoint
    tweet_url = "https://api.twitter.com/2/tweets"
    headers = {
        "Authorization": create_oauth_header("POST", tweet_url, api_key, api_secret, access_token, access_token_secret),
        "Content-Type": "application/json",
    }
    payload = {"text": tweet_text}

    try:
        res = requests.post(tweet_url, json=payload, headers=headers, timeout=10)
        if res.status_code in (200, 201):
            state["last_row_index"] = next_index
            state["last_post_time"] = datetime.now(timezone.utc).isoformat()
            state["total_posts"] = state.get("total_posts", 0) + 1
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            logger.info("Posted row %d from CSV to Twitter ✓", next_index)
            return True, f"Posted row {next_index}"
        else:
            err_msg = f"HTTP {res.status_code}: {res.text[:200]}"
            logger.warning("Twitter API CSV post failed: %s", err_msg)
            return False, err_msg
    except Exception as exc:
        logger.error("Network exception posting CSV row to Twitter: %s", exc)
        return False, str(exc)


if __name__ == "__main__":
    init_csv_and_state()
    print("CSV Queue initialized at:", CSV_FILE)
    print("State File initialized at:", STATE_FILE)
