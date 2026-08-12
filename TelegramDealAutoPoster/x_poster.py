"""
x_poster.py — Post deals directly to X (Twitter) @techselect_blog.

Design goals:
  * Non-blocking — background posting so slow/errored X calls never delay Telegram or Website push.
  * Non-fatal   — errors are logged and swallowed; the bot keeps running smoothly.
  * Self-config — loads X credentials from config or environment variables.
  * Format-aware — truncates text cleanly to fit X's 280 character limit (URL counts as 23 chars).
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)


def _resolve_x_config() -> tuple[str, str, str, str, str, bool]:
    """Return (consumer_key, consumer_secret, access_token, access_token_secret, bearer_token, enabled)."""
    ck = os.getenv("TWITTER_API_KEY", "").strip() or os.getenv("X_API_KEY", "").strip()
    cs = os.getenv("TWITTER_API_SECRET", "").strip() or os.getenv("X_API_SECRET", "").strip()
    at = os.getenv("TWITTER_ACCESS_TOKEN", "").strip() or os.getenv("X_ACCESS_TOKEN", "").strip()
    ats = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "").strip() or os.getenv("X_ACCESS_TOKEN_SECRET", "").strip()
    bt = os.getenv("TWITTER_BEARER_TOKEN", "").strip() or os.getenv("X_BEARER_TOKEN", "").strip()

    # Try config module
    try:
        import config  # type: ignore
        ck = ck or getattr(config, "TWITTER_API_KEY", "") or getattr(config, "X_API_KEY", "")
        cs = cs or getattr(config, "TWITTER_API_SECRET", "") or getattr(config, "X_API_SECRET", "")
        at = at or getattr(config, "TWITTER_ACCESS_TOKEN", "") or getattr(config, "X_ACCESS_TOKEN", "")
        ats = ats or getattr(config, "TWITTER_ACCESS_TOKEN_SECRET", "") or getattr(config, "X_ACCESS_TOKEN_SECRET", "")
        bt = bt or getattr(config, "TWITTER_BEARER_TOKEN", "") or getattr(config, "X_BEARER_TOKEN", "")
    except Exception:
        pass

    enabled = bool(ck and cs and at and ats)
    return ck, cs, at, ats, bt, enabled


def clean_html_tags(raw_html: str) -> str:
    """Strip HTML tags like <b>, <i>, <a> from message text."""
    cleanr = re.compile("<.*?>")
    cleantext = re.sub(cleanr, "", raw_html)
    return cleantext.strip()


def format_tweet_text(text: str, asins: list[str], affiliate_tag: str = "techstor0caaf-21") -> str:
    """Format deal text into a clean X post under 280 characters, including site info."""
    clean_text = clean_html_tags(text)
    lines = [line.strip() for line in clean_text.split("\n") if line.strip()]

    # Extract first line as title
    title = lines[0] if lines else "Hot Tech Deal Alert!"
    
    # Target ASIN
    asin = asins[0] if asins else ""
    url = f"https://www.amazon.in/dp/{asin}?tag={affiliate_tag}" if asin else ""
    website_url = "https://techselect.blog"

    hashtags = "#TechDeals #TechSelect #Ad"
    
    # X counts any t.co link as 23 chars regardless of raw length.
    # Budget: 280 total - 23 (amazon url) - 23 (techselect url) - 26 (hashtags) - 30 (labels/newlines) = ~178 chars for title
    max_title_len = 170
    if len(title) > max_title_len:
        title = title[: max_title_len - 3] + "..."

    if url:
        tweet = f"⚡ {title}\n\n🛒 Check Price: {url}\n🌐 More Deals: {website_url}\n\n{hashtags}"
    else:
        tweet = f"⚡ {title}\n\n🌐 More Deals: {website_url}\n\n{hashtags}"

    return tweet


async def push_deal_to_x(
    *,
    text: str,
    asins: list[str],
    affiliate_tag: str = "techstor0caaf-21",
) -> bool:
    """Post deal to X (Twitter) via v2 API using tweepy.
    
    Returns True on success, False on failure or when disabled. Never raises exceptions.
    """
    ck, cs, at, ats, bt, enabled = _resolve_x_config()

    if not enabled:
        logger.debug("X post skipped: Twitter/X credentials not configured.")
        return False

    if not asins:
        logger.debug("X post skipped: No ASINs provided.")
        return False

    tweet_content = format_tweet_text(text, asins, affiliate_tag)

    try:
        import tweepy  # type: ignore

        client = tweepy.Client(
            bearer_token=bt or None,
            consumer_key=ck,
            consumer_secret=cs,
            access_token=at,
            access_token_secret=ats,
        )

        response = client.create_tweet(text=tweet_content)
        tweet_id = response.data.get("id") if response and response.data else "OK"
        logger.info("Pushed deal to X ✓ — Tweet ID=%s ASINs=%s", tweet_id, asins)
        return True

    except Exception as exc:
        logger.error("Failed to post deal directly to X: %s", exc)
        # Fallback: append to posts.csv queue (ReactorcoreGames TwitterAutoPoster integration)
        try:
            from poster import append_to_csv_queue
            clean_t = clean_html_tags(text)
            lines = [line.strip() for line in clean_t.split("\n") if line.strip()]
            title = lines[0] if lines else "Hot Tech Deal"
            asin = asins[0] if asins else ""
            url = f"https://www.amazon.in/dp/{asin}?tag={affiliate_tag}" if asin else ""
            hashtags = "#TechDeals #AmazonIndia #TechSelect #Ad"
            queued = append_to_csv_queue(title=title, url=url, hashtags=hashtags)
            if queued:
                logger.info("Fallback activated: Deal appended to posts.csv queue ✓")
        except Exception as fb_exc:
            logger.error("Failed to append deal to fallback CSV queue: %s", fb_exc)

        return False


def _selftest() -> None:
    """Manual test function: python x_poster.py"""
    import asyncio

    print("Running X Poster self-test...")
    test_text = "🔥 Apple MacBook Air M2 (8GB RAM, 256GB SSD) at lowest price ever!"
    test_asins = ["B0B3C4NKLF"]

    success = asyncio.run(push_deal_to_x(text=test_text, asins=test_asins))
    print("X Push Test Result:", "SUCCESS" if success else "FAILED (Check logs/credentials)")


if __name__ == "__main__":
    _selftest()
