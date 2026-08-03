"""Utility modules shared by the deal poster: persistent dedup, rate limiter, flood-safe sends."""

import asyncio
import sqlite3
import time
import random
import os

import config
from config import logger

# ── Persistent Dedup Store (SQLite, 7-day TTL) ──────────────────────

DEDUP_DB = os.path.join(os.path.dirname(__file__), "dedup.db")


def _init_dedup_db():
    conn = sqlite3.connect(DEDUP_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS dedup (asin TEXT PRIMARY KEY, posted_at REAL NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_posted_at ON dedup(posted_at)")
    conn.commit()
    _prune(conn)
    return conn


def _prune(conn):
    cutoff = time.time() - (7 * 24 * 3600)  # 7 days
    conn.execute("DELETE FROM dedup WHERE posted_at < ?", (cutoff,))
    conn.commit()


_dedup_conn = _init_dedup_db()


def dedup_record(asin: str):
    """Persist an ASIN as seen (insert-or-replace)."""
    _dedup_conn.execute(
        "INSERT OR REPLACE INTO dedup (asin, posted_at) VALUES (?, ?)",
        (asin, time.time()),
    )
    _dedup_conn.commit()


def dedup_load() -> set:
    """Return all ASINs currently in the store."""
    return {row[0] for row in _dedup_conn.execute("SELECT asin FROM dedup").fetchall()}


def dedup_has(asin: str) -> bool:
    """Check whether an ASIN is already stored."""
    return bool(
        _dedup_conn.execute("SELECT 1 FROM dedup WHERE asin = ?", (asin,)).fetchone()
    )


def dedup_prune():
    """Explicitly prune entries older than 7 days."""
    _prune(_dedup_conn)


# ── Conservative Rate Limiter ────────────────────────────────────────

class RateLimiter:
    """Sliding-window limiter: no more than *max_per_hour* sends per rolling hour."""

    def __init__(
        self,
        max_per_hour: int = 10,
        min_delay: float = 30.0,
        max_delay: float = 90.0,
    ):
        self.max_per_hour = max_per_hour
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._timestamps = []  # sorted list of timestamps

    async def acquire(self):
        now = time.time()
        # Evict stale entries (>1 h old)
        self._timestamps = [t for t in self._timestamps if t > now - 3600]

        # Hourly cap: sleep until oldest slot frees up
        if len(self._timestamps) >= self.max_per_hour:
            wait = (self._timestamps[0] + 3600) - now
            if wait > 0:
                logger.info("Rate limit reached, waiting %.0fs …", wait)
                await asyncio.sleep(wait)
            self._timestamps = [t for t in self._timestamps if t > now - 3600]

        # Human-like random delay between min/max
        delay = random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(delay)
        self._timestamps.append(now)


# Instantiate once — reads config attributes at load time
_RATE_LIMITER = RateLimiter(
    max_per_hour=int(getattr(config, "RATE_LIMIT_HR", 10)),
    min_delay=float(getattr(config, "MIN_DELAY_S", 30)),
    max_delay=float(getattr(config, "MAX_DELAY_S", 90)),
)
