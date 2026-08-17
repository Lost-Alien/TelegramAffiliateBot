"""
poster.py — Posts replies and quote-reposts to X/Twitter via session cookie authentication.
Uses Chrome TLS fingerprinting (curl_cffi) to bypass bot protection reliably.
Supports direct auth_token/ct0 cookies, Base64 secrets, and dry-run simulation.
"""

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from curl_cffi import requests

from x_commenter.config_x import (
    TWITTER_AUTH_TOKEN,
    TWITTER_CT0,
    TWITTER_COOKIES_B64,
    COOKIES_PATH,
    DRY_RUN,
)

logger = logging.getLogger("x_commenter.poster")

BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

CREATE_TWEET_URL = "https://x.com/i/api/graphql/SiM_cAu83R0wnrpmKQQSEw/CreateTweet"

CREATE_TWEET_FEATURES = {
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_media_download_video_enabled": False,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_awards_web_tipping_enabled": False,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "tweetypie_unmention_optimization_enabled": True,
    "verified_phone_label_enabled": False,
    "view_counts_everywhere_api_enabled": True,
}


def _clean_token(val: Any) -> str:
    """Strip whitespace, quotes, and UTF-8 BOM characters that break HTTP header encoding."""
    if not val:
        return ""
    return str(val).strip().strip("\ufeff\u200b\r\n\t'\"")


def get_cookie_credentials() -> Optional[Tuple[str, str]]:
    """
    Extracts (auth_token, ct0) from environment or cookie files.
    """
    # 1. Direct env vars
    if TWITTER_AUTH_TOKEN and TWITTER_CT0:
        return _clean_token(TWITTER_AUTH_TOKEN), _clean_token(TWITTER_CT0)

    # 2. Base64 decoded cookie string
    if TWITTER_COOKIES_B64:
        try:
            decoded_text = base64.b64decode(TWITTER_COOKIES_B64).decode("utf-8")
            data = json.loads(decoded_text)
            auth_token = data.get("auth_token") or data.get("auth_token_secret")
            ct0 = data.get("ct0") or data.get("csrf_token")
            if auth_token and ct0:
                return _clean_token(auth_token), _clean_token(ct0)
        except Exception as exc:
            logger.error(f"Error parsing TWITTER_COOKIES_B64: {exc}")

    # 3. Local cookies.json file
    if COOKIES_PATH.is_file():
        try:
            with open(COOKIES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            auth_token = data.get("auth_token")
            ct0 = data.get("ct0")
            if auth_token and ct0:
                return _clean_token(auth_token), _clean_token(ct0)
        except Exception as exc:
            logger.error(f"Error reading {COOKIES_PATH}: {exc}")

    return None


def _create_tweet_sync(
    tweet_text: str,
    in_reply_to_tweet_id: Optional[str] = None,
    attachment_url: Optional[str] = None,
    action_label: str = "reply",
) -> bool:
    """
    Shared implementation for posting a tweet via X's CreateTweet GraphQL
    endpoint — used for both plain replies (in_reply_to_tweet_id) and
    quote-reposts (attachment_url set to the quoted tweet's URL).
    """
    if not tweet_text:
        logger.warning(f"Empty {action_label} text provided. Skipping post.")
        return False

    if DRY_RUN:
        target = in_reply_to_tweet_id or attachment_url
        logger.info(f"[DRY_RUN] Would post {action_label} for target={target}:\n{tweet_text}")
        return True

    creds = get_cookie_credentials()
    if not creds:
        logger.error(
            "Missing X session cookies! Please set TWITTER_AUTH_TOKEN and TWITTER_CT0 in environment/secrets."
        )
        return False

    auth_token, ct0 = creds

    # Dynamic Contextual Referer & Full Chrome 124 Browser Headers
    if in_reply_to_tweet_id:
        referer_url = f"https://x.com/i/status/{in_reply_to_tweet_id}"
    elif attachment_url:
        referer_url = attachment_url
    else:
        referer_url = "https://x.com/compose/post"

    headers = {
        "authorization": f"Bearer {BEARER_TOKEN}",
        "x-csrf-token": ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "content-type": "application/json",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": referer_url,
        "origin": "https://x.com",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "priority": "u=1, i",
    }

    cookies = {
        "auth_token": auth_token,
        "ct0": ct0,
    }

    variables: Dict[str, Any] = {
        "tweet_text": tweet_text,
        "dark_request": False,
        "media": {
            "media_entities": [],
            "possibly_sensitive": False,
        },
        "semantic_annotation_ids": [],
    }

    if in_reply_to_tweet_id:
        variables["reply"] = {
            "in_reply_to_tweet_id": str(in_reply_to_tweet_id),
            "exclude_reply_user_ids": [],
        }

    if attachment_url:
        variables["attachment_url"] = attachment_url

    payload = {
        "variables": variables,
        "features": CREATE_TWEET_FEATURES,
        "queryId": "SiM_cAu83R0wnrpmKQQSEw",
    }

    try:
        response = requests.post(
            CREATE_TWEET_URL,
            json=payload,
            headers=headers,
            cookies=cookies,
            impersonate="chrome124",
            timeout=20,
        )

        if response.status_code == 200:
            res_data = response.json()
            errors = res_data.get("errors", [])
            if errors:
                first_err = errors[0]
                err_msg = first_err.get("message", "Unknown GraphQL error")
                err_code = first_err.get("code")
                if err_code == 226:
                    logger.warning(
                        f"X automated activity cooldown active (code 226). Posting will resume automatically on the next scheduled run."
                    )
                elif err_code == 344:
                    logger.warning(
                        f"X 24-hour daily posting limit reached (code 344). Posting will resume after rolling window resets."
                    )
                else:
                    logger.error(f"X GraphQL error during {action_label} posting (code {err_code}): {err_msg}")
                return False

            tweet_res = (
                res_data.get("data", {})
                .get("create_tweet", {})
                .get("tweet_results", {})
                .get("result", {})
            )
            posted_id = tweet_res.get("rest_id")
            if posted_id:
                logger.info(f"Successfully posted {action_label} via Cookie Auth! Tweet URL: https://x.com/techselect_blog/status/{posted_id}")
                return True
            else:
                logger.warning(f"Unexpected response structure: {res_data}")
                return False
        else:
            logger.error(
                f"Failed to post {action_label} (HTTP {response.status_code}): {response.text[:300]}"
            )
            return False

    except Exception as exc:
        logger.error(f"Unexpected exception during X {action_label} post: {exc}")
        return False


def post_reply_sync(reply_text: str, in_reply_to_tweet_id: Optional[str] = None) -> bool:
    """Synchronously posts a reply to X using Chrome TLS impersonation."""
    return _create_tweet_sync(reply_text, in_reply_to_tweet_id=in_reply_to_tweet_id, action_label="reply")


def post_quote_tweet_sync(comment_text: str, quoted_tweet_url: str) -> bool:
    """
    Synchronously posts a quote-repost ("repost with own thoughts") — a new
    standalone tweet with quoted_tweet_url attached, so the original tweet
    renders embedded beneath your commentary.
    """
    if not quoted_tweet_url:
        logger.warning("No quoted_tweet_url provided. Skipping quote-repost.")
        return False
    return _create_tweet_sync(comment_text, attachment_url=quoted_tweet_url, action_label="quote-repost")


async def async_post_reply(reply_text: str, in_reply_to_tweet_id: Optional[str] = None) -> bool:
    """Asynchronous wrapper for posting replies."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, post_reply_sync, reply_text, in_reply_to_tweet_id)


async def async_post_quote_tweet(comment_text: str, quoted_tweet_url: str) -> bool:
    """Asynchronous wrapper for posting quote-reposts."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, post_quote_tweet_sync, comment_text, quoted_tweet_url)


def post_reply(reply_text: str, in_reply_to_tweet_id: Optional[str] = None) -> bool:
    """Synchronous interface compatible with all pipeline modules."""
    return post_reply_sync(reply_text, in_reply_to_tweet_id)


def post_quote_tweet(comment_text: str, quoted_tweet_url: str) -> bool:
    """Synchronous interface for posting a quote-repost ("repost with own thoughts")."""
    return post_quote_tweet_sync(comment_text, quoted_tweet_url)
