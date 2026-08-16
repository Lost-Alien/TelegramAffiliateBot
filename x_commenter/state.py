"""
state.py — Manages deduplication and daily comment counters using Upstash Redis.
Falls back to a local SQLite / JSON store if Upstash is unavailable.
"""

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
import httpx
from x_commenter.config_x import UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN

logger = logging.getLogger("x_commenter.state")

REPLIED_SET_KEY = "x_commenter:replied_tweet_ids"
DAILY_COUNTER_KEY = "x_commenter:daily_count"
FALLBACK_DB_PATH = Path(__file__).resolve().parent / "local_state.db"


def _init_local_db():
    try:
        conn = sqlite3.connect(FALLBACK_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS replied_tweets (
                tweet_id TEXT PRIMARY KEY,
                reply_text TEXT,
                replied_at INTEGER
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_counter (
                day_key TEXT PRIMARY KEY,
                count INTEGER
            )
            """
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"Failed to initialize local fallback SQLite DB: {exc}")


_init_local_db()


def _redis_command(*args) -> any:
    """Execute a REST command against Upstash Redis."""
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        return None

    path = "/".join(str(arg) for arg in args)
    headers = {"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"}

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(f"{UPSTASH_REDIS_REST_URL}/{path}", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result")
    except Exception as exc:
        logger.warning(f"Upstash Redis request failed ({args[0]}): {exc}")
    return None


def already_replied(tweet_id: str) -> bool:
    """Check if we have already posted a comment to this tweet."""
    if not tweet_id:
        return True

    # 1. Check Upstash Redis
    res = _redis_command("SISMEMBER", REPLIED_SET_KEY, tweet_id)
    if res is not None:
        return bool(res)

    # 2. Local fallback
    try:
        conn = sqlite3.connect(FALLBACK_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM replied_tweets WHERE tweet_id = ?", (tweet_id,))
        row = cursor.fetchone()
        conn.close()
        return bool(row)
    except Exception as exc:
        logger.error(f"Local state check error: {exc}")
        return False


def mark_replied(tweet_id: str, reply_text: str = "") -> bool:
    """Mark tweet as replied in both Upstash Redis and local DB."""
    if not tweet_id:
        return False

    # 1. Update Upstash Redis
    _redis_command("SADD", REPLIED_SET_KEY, tweet_id)
    _redis_command("EXPIRE", REPLIED_SET_KEY, 2592000)  # 30 days retention

    # 2. Update local DB
    try:
        conn = sqlite3.connect(FALLBACK_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO replied_tweets (tweet_id, reply_text, replied_at)
            VALUES (?, ?, ?)
            """,
            (tweet_id, reply_text, int(time.time())),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        logger.error(f"Failed to record replied tweet locally: {exc}")
        return False


def get_daily_count() -> int:
    """Get number of replies posted today."""
    today_key = time.strftime("%Y-%m-%d")
    redis_key = f"{DAILY_COUNTER_KEY}:{today_key}"

    # 1. Check Upstash Redis
    res = _redis_command("GET", redis_key)
    if res is not None:
        try:
            return int(res)
        except (ValueError, TypeError):
            return 0

    # 2. Local fallback
    try:
        conn = sqlite3.connect(FALLBACK_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT count FROM daily_counter WHERE day_key = ?", (today_key,))
        row = cursor.fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except Exception as exc:
        logger.error(f"Failed to get local daily count: {exc}")
        return 0


def increment_daily_count() -> int:
    """Increment number of replies posted today."""
    today_key = time.strftime("%Y-%m-%d")
    redis_key = f"{DAILY_COUNTER_KEY}:{today_key}"

    # 1. Upstash Redis
    _redis_command("INCR", redis_key)
    _redis_command("EXPIRE", redis_key, 86400 * 2)  # 48 hours TTL

    # 2. Local fallback
    try:
        conn = sqlite3.connect(FALLBACK_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO daily_counter (day_key, count)
            VALUES (?, 1)
            ON CONFLICT(day_key) DO UPDATE SET count = count + 1
            """,
            (today_key,),
        )
        conn.commit()
        cursor.execute("SELECT count FROM daily_counter WHERE day_key = ?", (today_key,))
        row = cursor.fetchone()
        conn.close()
        return int(row[0]) if row else 1
    except Exception as exc:
        logger.error(f"Failed to increment local daily count: {exc}")
        return 1
