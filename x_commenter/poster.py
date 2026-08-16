"""
poster.py — Posts replies to X/Twitter via official Twitter API v2 (Tweepy).
Supports dry-run testing and safety logging.
"""

import logging
from typing import Optional, Dict, Any
import tweepy
from x_commenter.config_x import (
    TWITTER_API_KEY,
    TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_TOKEN_SECRET,
    TWITTER_BEARER_TOKEN,
    DRY_RUN,
)

logger = logging.getLogger("x_commenter.poster")

_client: Optional[tweepy.Client] = None


def get_twitter_client() -> Optional[tweepy.Client]:
    global _client
    if _client is None:
        if not (TWITTER_API_KEY and TWITTER_ACCESS_TOKEN):
            logger.error("Missing Twitter API credentials in environment.")
            return None
        try:
            _client = tweepy.Client(
                bearer_token=TWITTER_BEARER_TOKEN or None,
                consumer_key=TWITTER_API_KEY,
                consumer_secret=TWITTER_API_SECRET,
                access_token=TWITTER_ACCESS_TOKEN,
                access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
            )
        except Exception as exc:
            logger.error(f"Failed to initialize Tweepy Client: {exc}")
            return None
    return _client


def post_reply(reply_text: str, in_reply_to_tweet_id: Optional[str] = None) -> bool:
    """
    Post a reply or tweet.
    Returns True if posted (or simulated in dry-run), False otherwise.
    """
    if not reply_text:
        logger.warning("Empty reply text provided. Skipping post.")
        return False

    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would post to tweet_id={in_reply_to_tweet_id}:\n{reply_text}")
        return True

    client = get_twitter_client()
    if not client:
        logger.error("Twitter client not initialized. Cannot post.")
        return False

    try:
        kwargs: Dict[str, Any] = {"text": reply_text}
        if in_reply_to_tweet_id:
            kwargs["in_reply_to_tweet_id"] = in_reply_to_tweet_id

        resp = client.create_tweet(**kwargs)
        if resp and resp.data:
            posted_id = resp.data.get("id")
            logger.info(f"Successfully posted reply! New Tweet ID: {posted_id}")
            return True
        logger.warning(f"Unexpected response from Twitter API: {resp}")
        return False
    except tweepy.errors.TweepyException as exc:
        logger.error(f"Twitter API error during posting: {exc}")
        return False
    except Exception as exc:
        logger.error(f"Unexpected error during posting: {exc}")
        return False
