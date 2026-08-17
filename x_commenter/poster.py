"""
poster.py — Posts replies to X/Twitter via Twikit (Cookie Auth / Free Session).
Supports cookie restoration from base64 env vars, dry-run simulation, and async/sync interfaces.
"""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from twikit import Client
from twikit.errors import TwitterException

from x_commenter.config_x import (
    TWITTER_AUTH_TOKEN,
    TWITTER_CT0,
    TWITTER_COOKIES_B64,
    COOKIES_PATH,
    DRY_RUN,
)

logger = logging.getLogger("x_commenter.poster")

_client: Optional[Client] = None


def ensure_cookies_file() -> Optional[Path]:
    """
    Ensures a valid cookies.json file exists on disk.
    If COOKIES_PATH exists, returns it.
    Otherwise, if TWITTER_COOKIES_B64 is provided, decodes and writes it.
    """
    if COOKIES_PATH.is_file() and COOKIES_PATH.stat().st_size > 0:
        return COOKIES_PATH

    if TWITTER_COOKIES_B64:
        try:
            decoded_bytes = base64.b64decode(TWITTER_COOKIES_B64)
            COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(COOKIES_PATH, "wb") as f:
                f.write(decoded_bytes)
            logger.info(f"Successfully decoded TWITTER_COOKIES_B64 to {COOKIES_PATH}")
            return COOKIES_PATH
        except Exception as exc:
            logger.error(f"Failed to decode TWITTER_COOKIES_B64: {exc}")
            return None

    return None


async def get_twikit_client() -> Optional[Client]:
    """
    Initializes and authenticates a Twikit Client using session cookies.
    Supports:
    1. Direct TWITTER_AUTH_TOKEN + TWITTER_CT0 env vars (Chrome DevTools copy-paste)
    2. TWITTER_COOKIES_B64 / cookies.json file
    """
    global _client
    if _client is not None:
        return _client

    client = Client(language="en-US")

    # Priority 1: Direct auth_token and ct0 from Chrome DevTools
    if TWITTER_AUTH_TOKEN and TWITTER_CT0:
        try:
            client.set_cookies({
                "auth_token": TWITTER_AUTH_TOKEN,
                "ct0": TWITTER_CT0,
            })
            _client = client
            logger.info("Twikit Client authenticated with direct auth_token & ct0 cookies.")
            return _client
        except Exception as exc:
            logger.error(f"Failed setting direct cookies: {exc}")

    # Priority 2: Cookie file or decoded Base64 cookies
    cookie_file = ensure_cookies_file()
    if cookie_file:
        try:
            client.load_cookies(str(cookie_file))
            _client = client
            logger.info("Twikit Client authenticated successfully with session cookies file.")
            return _client
        except Exception as exc:
            logger.error(f"Failed to authenticate Twikit Client from cookies file: {exc}")

    logger.error(
        "Missing X session cookies! Please set TWITTER_AUTH_TOKEN and TWITTER_CT0 in your environment/secrets, "
        "or run 'python -m x_commenter.login_helper'."
    )
    return None



async def async_post_reply(reply_text: str, in_reply_to_tweet_id: Optional[str] = None) -> bool:
    """
    Asynchronously post a reply or tweet using Twikit.
    """
    if not reply_text:
        logger.warning("Empty reply text provided. Skipping post.")
        return False

    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would post to tweet_id={in_reply_to_tweet_id}:\n{reply_text}")
        return True

    client = await get_twikit_client()
    if not client:
        logger.error("Twikit client not initialized. Cannot post.")
        return False

    try:
        kwargs: Dict[str, Any] = {"text": reply_text}
        if in_reply_to_tweet_id:
            kwargs["reply_to"] = str(in_reply_to_tweet_id)

        tweet = await client.create_tweet(**kwargs)
        if tweet:
            tweet_id = getattr(tweet, "id", None) or getattr(tweet, "tweet_id", "unknown")
            logger.info(f"Successfully posted reply via Twikit! New Tweet ID: {tweet_id}")
            return True

        logger.warning("Twikit returned empty response from create_tweet.")
        return False
    except TwitterException as exc:
        logger.error(f"Twitter/Twikit API error during posting: {exc}")
        return False
    except Exception as exc:
        logger.error(f"Unexpected error during Twikit posting: {exc}")
        return False


def post_reply(reply_text: str, in_reply_to_tweet_id: Optional[str] = None) -> bool:
    """
    Synchronous wrapper for posting replies to X.
    Compatible with existing orchestrator and pipeline scripts.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If already inside an async loop, schedule in a new task or runner
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run, async_post_reply(reply_text, in_reply_to_tweet_id)
                ).result()
        else:
            return loop.run_until_complete(
                async_post_reply(reply_text, in_reply_to_tweet_id)
            )
    except RuntimeError:
        return asyncio.run(async_post_reply(reply_text, in_reply_to_tweet_id))
