"""
account_fallback.py — Free, credit-less discovery fallback for the X scanner.

When Exa search errors out or returns nothing usable, this module pulls
target accounts' latest tweets directly from X using the same authenticated
session (cookies) already required for posting in poster.py. No Exa credits
are spent.

This mirrors the "no API key, keyless scraping" philosophy popularized by
toolkits like XActions (https://github.com/nirholas/XActions) — that project
is a separate Node.js/Puppeteer toolkit that can't be dropped into this
Python codebase directly, but the same core idea (free, authenticated,
direct account reads as a fallback data source) is implemented here using
`twikit` (installed in this project via the actively-maintained `twifork`
fork, which is a drop-in replacement still imported as `twikit`).

All accounts in a scan are fetched inside a single event loop (one
`asyncio.run()` call for the whole batch) rather than one loop per account —
twikit's `Client` owns a persistent `httpx.AsyncClient` bound to the loop it
was created in, so reusing a client (or looping `asyncio.run()` repeatedly)
across separate event loops raises "Event loop is closed" on every call
after the first.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from twikit import Client

from x_commenter.config_x import COOKIES_PATH, TWITTER_AUTH_TOKEN, TWITTER_CT0

logger = logging.getLogger("x_commenter.account_fallback")


def _build_client() -> Optional[Client]:
    """Builds a fresh authenticated twikit client from existing cookies (no network I/O yet)."""
    client = Client(language="en-US")
    try:
        if TWITTER_AUTH_TOKEN and TWITTER_CT0:
            client.set_cookies({"auth_token": TWITTER_AUTH_TOKEN, "ct0": TWITTER_CT0})
        elif COOKIES_PATH.is_file():
            client.load_cookies(str(COOKIES_PATH))
        else:
            logger.warning("No X session cookies available — account fallback scanner disabled.")
            return None
    except Exception as exc:
        logger.error(f"Failed to initialize fallback X client: {exc}")
        return None
    return client


async def _fetch_one_account(client: Client, username: str, count: int) -> List[Dict[str, Any]]:
    try:
        user = await client.get_user_by_screen_name(username)
        if not user:
            return []

        tweets = await user.get_tweets("Tweets", count=count)
        candidates: List[Dict[str, Any]] = []
        for tweet in list(tweets)[:count]:
            text = getattr(tweet, "full_text", None) or getattr(tweet, "text", "") or ""
            candidates.append({
                "id": str(tweet.id),
                "url": f"https://x.com/{username}/status/{tweet.id}",
                "title": f"@{username} tweet",
                "text": text,
                "author": username,
                "topic": f"{username} update",
            })
        return candidates
    except Exception as exc:
        logger.warning(f"Fallback scan failed for @{username}: {exc}")
        return []


async def _fetch_accounts_async(usernames: List[str], count: int) -> Dict[str, List[Dict[str, Any]]]:
    client = _build_client()
    if not client:
        return {}

    results: Dict[str, List[Dict[str, Any]]] = {}
    for username in usernames:
        results[username] = await _fetch_one_account(client, username, count)
    return results


def fetch_accounts_tweets(usernames: List[str], count: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch recent tweets for multiple accounts without spending Exa credits.
    All accounts are fetched within a single event loop for correctness and
    efficiency (see module docstring). Returns {username: [tweet_dict, ...]}.
    """
    if not usernames:
        return {}
    try:
        return asyncio.run(_fetch_accounts_async(usernames, count))
    except RuntimeError:
        # Only hit if an event loop is already running in this thread.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_fetch_accounts_async(usernames, count))
        finally:
            loop.close()


def fetch_account_tweets(username: str, count: int = 3) -> List[Dict[str, Any]]:
    """Convenience wrapper for a single account. Prefer fetch_accounts_tweets for batches."""
    return fetch_accounts_tweets([username], count).get(username, [])
