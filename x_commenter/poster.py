"""
poster.py — Posts replies to X/Twitter via session cookie authentication.
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


def get_cookie_credentials() -> Optional[Tuple[str, str]]:
    """
    Extracts (auth_token, ct0) from environment or cookie files.
    """
    # 1. Direct env vars
    if TWITTER_AUTH_TOKEN and TWITTER_CT0:
        return TWITTER_AUTH_TOKEN, TWITTER_CT0

    # 2. Base64 decoded cookie string
    if TWITTER_COOKIES_B64:
        try:
            decoded_text = base64.b64decode(TWITTER_COOKIES_B64).decode("utf-8")
            data = json.loads(decoded_text)
            auth_token = data.get("auth_token") or data.get("auth_token_secret")
            ct0 = data.get("ct0") or data.get("csrf_token")
            if auth_token and ct0:
                return auth_token, ct0
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
                return auth_token, ct0
        except Exception as exc:
            logger.error(f"Error reading {COOKIES_PATH}: {exc}")

    return None


def post_reply_sync(reply_text: str, in_reply_to_tweet_id: Optional[str] = None) -> bool:
    """
    Synchronously posts a tweet or reply to X using Chrome TLS impersonation.
    """
    if not reply_text:
        logger.warning("Empty reply text provided. Skipping post.")
        return False

    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would post to tweet_id={in_reply_to_tweet_id}:\n{reply_text}")
        return True

    creds = get_cookie_credentials()
    if not creds:
        logger.error(
            "Missing X session cookies! Please set TWITTER_AUTH_TOKEN and TWITTER_CT0 in environment/secrets."
        )
        return False

    auth_token, ct0 = creds

    headers = {
        "authorization": f"Bearer {BEARER_TOKEN}",
        "x-csrf-token": ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "content-type": "application/json",
        "referer": "https://x.com/",
        "origin": "https://x.com",
    }

    cookies = {
        "auth_token": auth_token,
        "ct0": ct0,
    }

    variables: Dict[str, Any] = {
        "tweet_text": reply_text,
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
            # Extract posted tweet ID from GraphQL response
            try:
                tweet_res = (
                    res_data.get("data", {})
                    .get("create_tweet", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                posted_id = tweet_res.get("rest_id") or "unknown"
                logger.info(f"Successfully posted reply via Cookie Auth! New Tweet ID: {posted_id}")
            except Exception:
                logger.info("Successfully posted reply via Cookie Auth!")
            return True
        else:
            logger.error(
                f"Failed to post reply (HTTP {response.status_code}): {response.text[:300]}"
            )
            return False

    except Exception as exc:
        logger.error(f"Unexpected exception during X post: {exc}")
        return False


async def async_post_reply(reply_text: str, in_reply_to_tweet_id: Optional[str] = None) -> bool:
    """
    Asynchronous wrapper for posting replies.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, post_reply_sync, reply_text, in_reply_to_tweet_id)


def post_reply(reply_text: str, in_reply_to_tweet_id: Optional[str] = None) -> bool:
    """
    Synchronous interface compatible with all pipeline modules.
    """
    return post_reply_sync(reply_text, in_reply_to_tweet_id)
