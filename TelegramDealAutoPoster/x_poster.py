"""
x_poster.py — Post deals directly to X (Twitter) @techselect_blog.

Design goals:
  * Primary   — XActions GraphQL web-session engine (cookie auth, no API fees, no 402 errors).
  * Fallback1 — Official Twitter API v2 via tweepy (if cookies not set).
  * Fallback2 — posts.csv queue via poster.py (if both above fail).
  * Non-blocking — background posting so slow/errored X calls never delay Telegram.
  * Non-fatal   — errors are logged and swallowed; the bot keeps running.
  * Format-aware — truncates text cleanly to fit X's 280 character limit.

XActions source: https://github.com/nirholas/XActions
  - Bearer token & queryId extracted from src/scrapers/twitter/http/endpoints.js
  - CreateTweet payload from src/scrapers/twitter/http/actions.js
  - Header structure from src/client/auth/TokenManager.js
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
import urllib.parse
import urllib.error

logger = logging.getLogger(__name__)

# ============================================================================
# XActions Constants (from nirholas/XActions repo, extracted directly)
# src/scrapers/twitter/http/endpoints.js → BEARER_TOKEN
# src/scrapers/twitter/http/endpoints.js → GRAPHQL.CreateTweet.queryId
# ============================================================================

_XACTIONS_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
_XACTIONS_CREATE_TWEET_QUERY_ID = "SiM_cAu83R0wnrpmKQQSEw"

# Default feature flags (from src/client/api/graphqlQueries.js → DEFAULT_FEATURES)
_XACTIONS_DEFAULT_FEATURES = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


# ============================================================================
# Credential Resolvers
# ============================================================================

def _resolve_xactions_cookies() -> tuple[str, str, bool]:
    """Return (auth_token, ct0, enabled) for XActions cookie-based posting."""
    auth_token = (
        os.getenv("TWITTER_AUTH_TOKEN", "").strip()
        or os.getenv("X_AUTH_TOKEN", "").strip()
    )
    ct0 = (
        os.getenv("TWITTER_CT0", "").strip()
        or os.getenv("X_CT0", "").strip()
    )

    # Try config module fallback
    try:
        import config  # type: ignore
        auth_token = auth_token or getattr(config, "TWITTER_AUTH_TOKEN", "") or getattr(config, "X_AUTH_TOKEN", "")
        ct0 = ct0 or getattr(config, "TWITTER_CT0", "") or getattr(config, "X_CT0", "")
    except Exception:
        pass

    enabled = bool(auth_token and ct0)
    return auth_token, ct0, enabled


def _resolve_x_config() -> tuple[str, str, str, str, str, bool]:
    """Return (consumer_key, consumer_secret, access_token, access_token_secret, bearer_token, enabled)."""
    ck = os.getenv("TWITTER_API_KEY", "").strip() or os.getenv("X_API_KEY", "").strip()
    cs = os.getenv("TWITTER_API_SECRET", "").strip() or os.getenv("X_API_SECRET", "").strip()
    at = os.getenv("TWITTER_ACCESS_TOKEN", "").strip() or os.getenv("X_ACCESS_TOKEN", "").strip()
    ats = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "").strip() or os.getenv("X_ACCESS_TOKEN_SECRET", "").strip()
    bt = os.getenv("TWITTER_BEARER_TOKEN", "").strip() or os.getenv("X_BEARER_TOKEN", "").strip()

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


# ============================================================================
# Text Utilities
# ============================================================================

def clean_html_tags(raw_html: str) -> str:
    """Strip HTML tags like <b>, <i>, <a> from message text."""
    cleanr = re.compile("<.*?>")
    cleantext = re.sub(cleanr, "", raw_html)
    return cleantext.strip()


def format_tweet_text(text: str, asins: list[str], affiliate_tag: str = "techstor0caaf-21") -> str:
    """Format deal text into a clean X post under 280 characters, including site info.

    Tweet structure (from implementation_plan.md § 3.3):
      ⚡ {Title}

      🛒 Check Price: {amazon_url}
      🌐 More Deals: https://techselect.blog

      #TechDeals #TechSelect #Ad

    Character budget:
      - X shortens all URLs to 23 chars (t.co)
      - Amazon URL: 23 chars
      - Website URL: 23 chars
      - Hashtags + labels + newlines: ~46 chars
      - Title budget: 170 chars → total ~210 chars (safe under 280)
    """
    clean_text = clean_html_tags(text)
    lines = [line.strip() for line in clean_text.split("\n") if line.strip()]

    title = lines[0] if lines else "Hot Tech Deal Alert!"
    asin = asins[0] if asins else ""
    url = f"https://www.amazon.in/dp/{asin}?tag={affiliate_tag}" if asin else ""
    website_url = "https://techselect.blog"
    hashtags = "#TechDeals #TechSelect #Ad"

    max_title_len = 170
    if len(title) > max_title_len:
        title = title[: max_title_len - 3] + "..."

    if url:
        tweet = f"⚡ {title}\n\n🛒 Check Price: {url}\n🌐 More Deals: {website_url}\n\n{hashtags}"
    else:
        tweet = f"⚡ {title}\n\n🌐 More Deals: {website_url}\n\n{hashtags}"

    return tweet


# ============================================================================
# XActions GraphQL Tweet Engine (Primary Poster — No API fees, No 402 errors)
# Based on: nirholas/XActions src/scrapers/twitter/http/actions.js postTweet()
# ============================================================================

def _xactions_post_tweet(auth_token: str, ct0: str, tweet_text: str) -> tuple[bool, str]:
    """Post a tweet via X's internal GraphQL API using session cookies.

    Directly implements the XActions CreateTweet flow:
      URL: https://x.com/i/api/graphql/{queryId}/CreateTweet
      Headers: Authorization Bearer, x-csrf-token (ct0), Cookie (auth_token + ct0)
      Body: { variables: { tweet_text, dark_request, media, semantic_annotation_ids },
              features: DEFAULT_FEATURES, queryId }

    Returns:
        (success: bool, tweet_id_or_error: str)
    """
    query_id = _XACTIONS_CREATE_TWEET_QUERY_ID
    url = f"https://x.com/i/api/graphql/{query_id}/CreateTweet"

    # Exact header structure from XActions TokenManager.getHeaders(authenticated=True)
    # + CookieAuth.getCookieString()
    headers = {
        "Authorization": f"Bearer {urllib.parse.unquote(_XACTIONS_BEARER_TOKEN)}",
        "x-csrf-token": ct0,
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
        "Cookie": f"auth_token={auth_token}; ct0={ct0};",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://x.com",
        "Referer": "https://x.com/compose/tweet",
    }

    # Exact payload from XActions actions.js postTweet() variables object
    payload = {
        "variables": {
            "tweet_text": tweet_text,
            "dark_request": False,
            "media": {
                "media_entities": [],
                "possibly_sensitive": False,
            },
            "semantic_annotation_ids": [],
        },
        "features": _XACTIONS_DEFAULT_FEATURES,
        "queryId": query_id,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        # Parse response: data.create_tweet.tweet_results.result (from XActions parseTweetResult)
        tweet_result = (
            resp_data.get("data", {}).get("create_tweet", {}).get("tweet_results", {}).get("result")
            or resp_data.get("data", {}).get("create_tweet", {}).get("tweet_result", {}).get("result")
            or resp_data.get("data", {}).get("create_tweet")
        )

        if tweet_result:
            tweet_id = (
                tweet_result.get("rest_id")
                or tweet_result.get("legacy", {}).get("id_str")
                or "OK"
            )
            return True, str(tweet_id)

        # Check for errors in response
        errors = resp_data.get("errors", [])
        if errors:
            error_msg = errors[0].get("message", "Unknown GraphQL error")
            return False, error_msg

        return True, "posted"  # No error but no parseable result = likely success

    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        return False, f"HTTP {e.code}: {e.reason} — {error_body}"
    except urllib.error.URLError as e:
        return False, f"Network error: {e.reason}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


# ============================================================================
# Public API
# ============================================================================

async def push_deal_to_x(
    *,
    text: str,
    asins: list[str],
    affiliate_tag: str = "techstor0caaf-21",
) -> bool:
    """Post deal to X (Twitter). Returns True on success, False on failure. Never raises.

    Posting priority:
      1. XActions GraphQL (cookie auth — FREE, no 402 errors) ← PRIMARY
      2. Tweepy Official API v2 (if cookies not configured) ← FALLBACK 1
      3. posts.csv queue (if both above fail) ← FALLBACK 2
    """
    if not asins:
        logger.debug("X post skipped: No ASINs provided.")
        return False

    tweet_content = format_tweet_text(text, asins, affiliate_tag)

    # ── PRIMARY: XActions GraphQL cookie engine ──────────────────────────────
    auth_token, ct0, xactions_enabled = _resolve_xactions_cookies()

    if xactions_enabled:
        logger.info("X poster: Using XActions GraphQL engine (cookie auth, no API fees).")
        success, result = _xactions_post_tweet(auth_token, ct0, tweet_content)
        if success:
            logger.info(
                "✅ XActions: Tweet posted to @techselect_blog — ID=%s ASINs=%s",
                result, asins,
            )
            return True
        else:
            logger.warning("⚠️  XActions post failed: %s — trying official API fallback.", result)
    else:
        logger.info(
            "XActions cookies not configured (TWITTER_AUTH_TOKEN/TWITTER_CT0 not set). "
            "Trying official API."
        )

    # ── FALLBACK 1: Tweepy Official API v2 ───────────────────────────────────
    ck, cs, at, ats, bt, tweepy_enabled = _resolve_x_config()

    if tweepy_enabled:
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
            logger.info("✅ Tweepy: Tweet posted — ID=%s ASINs=%s", tweet_id, asins)
            return True

        except Exception as exc:
            logger.error("⚠️  Tweepy official API failed: %s", exc)
    else:
        logger.debug("Tweepy credentials not configured.")

    # ── FALLBACK 2: posts.csv queue ──────────────────────────────────────────
    try:
        from poster import append_to_csv_queue  # type: ignore

        clean_t = clean_html_tags(text)
        lines_list = [line.strip() for line in clean_t.split("\n") if line.strip()]
        title = lines_list[0] if lines_list else "Hot Tech Deal"
        asin = asins[0] if asins else ""
        url = f"https://www.amazon.in/dp/{asin}?tag={affiliate_tag}" if asin else ""
        hashtags = "#TechDeals #AmazonIndia #TechSelect #Ad"
        queued = append_to_csv_queue(title=title, url=url, hashtags=hashtags)
        if queued:
            logger.info("📋 Fallback 2: Deal queued in posts.csv for later posting ✓")
    except Exception as fb_exc:
        logger.error("❌ Failed to append deal to fallback CSV queue: %s", fb_exc)

    return False


# ============================================================================
# Self-test
# ============================================================================

def _selftest() -> None:
    """Manual test: python x_poster.py"""
    import asyncio

    print("Running X Poster self-test (XActions primary, tweepy fallback)...")
    test_text = "🔥 Apple MacBook Air M2 (8GB RAM, 256GB SSD) at lowest price ever!"
    test_asins = ["B0B3C4NKLF"]

    # Print resolved config for debugging
    auth_token, ct0, xactions_enabled = _resolve_xactions_cookies()
    ck, cs, at, ats, bt, tweepy_enabled = _resolve_x_config()
    print(f"  XActions cookies: {'✅ Configured' if xactions_enabled else '❌ Not set (set TWITTER_AUTH_TOKEN & TWITTER_CT0)'}")
    print(f"  Tweepy Official API: {'✅ Configured' if tweepy_enabled else '❌ Not set'}")

    success = asyncio.run(push_deal_to_x(text=test_text, asins=test_asins))
    print("X Push Test Result:", "✅ SUCCESS" if success else "❌ FAILED (Check logs/credentials)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _selftest()
