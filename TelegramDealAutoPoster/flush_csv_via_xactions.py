"""
flush_csv_via_xactions.py
==========================
Reads posts.csv, filters out test/fake entries, and posts each real deal
to X (Twitter) via XActions GraphQL cookie engine.

===============================================================================
SECURITY & CREDENTIAL INSTRUCTIONS (GitHub Secrets / Environment Variables):
===============================================================================
Do NOT hardcode private cookies, API keys, or GitHub PATs in source code!

To run locally or in CI/CD (GitHub Actions / EC2):
1. Copy x.com cookies from Browser DevTools (F12 -> Application -> Cookies -> x.com):
   - `auth_token`: session cookie
   - `ct0`: CSRF token cookie

2. Add credentials to Environment Variables or .env file:
   - TWITTER_AUTH_TOKEN="<your_auth_token>"
   - TWITTER_CT0="<your_ct0_token>"

3. In GitHub Repository Secrets (Settings -> Secrets and variables -> Actions):
   - Secret Name: `TWITTER_AUTH_TOKEN` -> Value: `<your_auth_token>`
   - Secret Name: `TWITTER_CT0`        -> Value: `<your_ct0_token>`

4. In GitHub Actions workflows, pass them as environment variables:
   env:
     TWITTER_AUTH_TOKEN: ${{ secrets.TWITTER_AUTH_TOKEN }}
     TWITTER_CT0: ${{ secrets.TWITTER_CT0 }}

Usage:
    python flush_csv_via_xactions.py
===============================================================================
"""

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from dotenv import load_dotenv  # type: ignore

# ── Load .env ────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")

AUTH_TOKEN = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
CT0        = os.getenv("TWITTER_CT0", "").strip()
CSV_FILE   = Path(__file__).parent / "posts.csv"

# ── XActions constants (from nirholas/XActions public web client spec) ───────
# Default public web client Bearer token (embedded in X's public JS bundle)
_PUBLIC_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", _PUBLIC_BEARER_TOKEN).strip()
CREATE_TWEET_QUERY_ID = os.getenv("TWITTER_CREATE_TWEET_QUERY_ID", "SiM_cAu83R0wnrpmKQQSEw").strip()

DEFAULT_FEATURES = {
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

WEBSITE_URL = "https://techselect.blog"


def _build_hook_text_from_row(title: str, hashtags: str) -> str:
    """Build link-free hook tweet for Step 1 of the PriceHawk two-step method.
    Mirrors the logic in x_poster._build_hook_tweet() but operates on CSV row fields.
    """
    import os as _os
    max_title = int(_os.getenv("DEAL_PRODUCT_MAX_LEN", "80"))
    t = title.strip()
    if len(t) > max_title:
        t = t[:max_title - 3] + "..."
    return f"{t} just dropped!\n\n\ud83d\udc47 Amazon link in reply below"


def xactions_post(tweet_text: str) -> tuple[bool, str]:
    """Post tweet via XActions GraphQL. Returns (success, tweet_id_or_error)."""
    url = f"https://x.com/i/api/graphql/{CREATE_TWEET_QUERY_ID}/CreateTweet"
    headers = {
        "Authorization": f"Bearer {urllib.parse.unquote(BEARER_TOKEN)}",
        "x-csrf-token": CT0,
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
        "Cookie": f"auth_token={AUTH_TOKEN}; ct0={CT0};",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Origin": "https://x.com",
        "Referer": "https://x.com/compose/tweet",
    }
    payload = {
        "variables": {
            "tweet_text": tweet_text,
            "dark_request": False,
            "media": {"media_entities": [], "possibly_sensitive": False},
            "semantic_annotation_ids": [],
        },
        "features": DEFAULT_FEATURES,
        "queryId": CREATE_TWEET_QUERY_ID,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = (
            data.get("data", {}).get("create_tweet", {}).get("tweet_results", {}).get("result")
            or data.get("data", {}).get("create_tweet", {}).get("tweet_result", {}).get("result")
        )
        if result:
            tid = result.get("rest_id") or result.get("legacy", {}).get("id_str") or "OK"
            return True, str(tid)
        errors = data.get("errors", [])
        if errors:
            return False, errors[0].get("message", "GraphQL error")
        return True, "posted"
    except urllib.error.HTTPError as e:
        body_txt = ""
        try:
            body_txt = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        return False, f"HTTP {e.code}: {e.reason} — {body_txt}"
    except Exception as e:
        return False, str(e)


def format_tweet(title: str, url: str, hashtags: str) -> str:
    """PriceHawk-style deal card for queued CSV posts.

    Inspired by cld-maindev/pricehawk patterns:
      * Single outbound link only (no secondary website URL — avoids X dual-link penalty)
      * Max 2 hashtags (X algorithm suppresses posts with >2 hashtags as spam)
      * Price anchoring headline for instant value recognition

    To revert to legacy Loot/Sale format, set DEAL_FORMAT_STYLE=loot_sale in env.
    """
    import os as _os

    style = _os.getenv("DEAL_FORMAT_STYLE", "pricehawk").lower().strip()

    if style == "loot_sale":
        # Legacy format (backward compat)
        title = title.strip()
        if len(title) > 130:
            title = title[:127] + "..."
        if hashtags == "#TechDeals #TechSelect #Ad" or not hashtags:
            hashtags = "#Loot #LootDeal #AmazonSale #TechDeals #Ad"
        return (
            f"🔥 MEGA LOOT SALE 💥\n"
            f"⚡ {title}\n\n"
            f"🛒 Grab Loot: {url}\n"
            f"🌐 Live Sales: {WEBSITE_URL}\n\n"
            f"{hashtags}"
        )

    # ── PriceHawk format (default) ──────────────────────────────────────────
    title = title.strip()
    # Trim to 80 chars to leave budget for price / coupon lines
    if len(title) > 80:
        title = title[:77] + "..."

    # Use minimal algorithm-safe hashtags unless overridden
    if not hashtags or hashtags in ("#TechDeals #TechSelect #Ad", "#Loot #LootDeal #AmazonSale #TechDeals #Ad"):
        hashtags = _os.getenv("DEAL_HASHTAGS", "#TechDeals #Ad").strip()

    return (
        f"🔥 Price Drop: {title}\n\n"
        f"🛒 Grab Deal: {url}\n\n"
        f"{hashtags}"
    )


def is_fake(url: str) -> bool:
    """Skip test/fake entries (B0TEST* ASINs)."""
    return "B0TEST" in url.upper()


def main():
    if not AUTH_TOKEN or not CT0:
        print("❌ ERROR: Missing X (Twitter) authentication tokens!")
        print("   Please set TWITTER_AUTH_TOKEN and TWITTER_CT0 in environment or .env file.")
        print("   In GitHub Actions, configure secrets TWITTER_AUTH_TOKEN and TWITTER_CT0.")
        sys.exit(1)

    if not CSV_FILE.exists():
        print(f"❌ posts.csv not found at {CSV_FILE}")
        sys.exit(1)

    print(f"🔑 Auth token configured: {AUTH_TOKEN[:4]}*** ✓")
    print(f"🔑 CT0 token configured: {CT0[:4]}*** ✓")
    print(f"📄 Reading {CSV_FILE}\n")

    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    real_rows = [r for r in rows if not is_fake(r.get("url", ""))]
    fake_count = len(rows) - len(real_rows)

    if not real_rows:
        print(f"ℹ️ No real queued items to post (Total in CSV: {len(rows)}, Fake/Test: {fake_count}).")
        sys.exit(0)

    print(f"📊 Total queued: {len(rows)} | Skipping {fake_count} test entries | Posting {len(real_rows)} real deals\n")
    print("─" * 60)

    posted = []
    failed = []

    posting_mode = os.getenv("DEAL_POSTING_MODE", "two_step").lower().strip()

    # Import reply engine for two-step mode
    _reply_fn = None
    if posting_mode == "two_step":
        try:
            import sys as _sys, os as _os
            _sys.path.insert(0, str(Path(__file__).parent))
            from x_poster import _xactions_reply_tweet  # type: ignore
            _reply_fn = _xactions_reply_tweet
        except ImportError as _ie:
            print(f"  ⚠️  Could not import _xactions_reply_tweet: {_ie}. Falling back to single-tweet mode.")
            posting_mode = "single_tweet"

    for i, row in enumerate(real_rows, 1):
        title    = row.get("title", "Tech Deal Alert").strip()
        url      = row.get("url", "").strip()
        hashtags = row.get("hashtags", "#TechDeals #TechSelect #Ad").strip()

        # Normalise hashtags to algorithm-safe set
        clean_hashtags = os.getenv("DEAL_HASHTAGS", "#TechDeals #Ad").strip()

        print(f"[{i}/{len(real_rows)}] Posting ({posting_mode}): {title[:60]}...")
        print(f"          URL: {url}")

        if posting_mode == "two_step" and _reply_fn is not None:
            # ── STEP 1: Hook tweet (no link) ─────────────────────────────
            hook_text = _build_hook_text_from_row(title, clean_hashtags)
            hook_ok, hook_result = xactions_post(hook_text)

            if hook_ok and hook_result not in ("posted", "OK", ""):
                # ── STEP 2: Reply with affiliate link via XActions ─────────
                import time as _time
                _time.sleep(2)
                reply_text = f"\ud83d\uded2 Amazon: {url}\n\n{clean_hashtags}"
                reply_ok, reply_result = _reply_fn(AUTH_TOKEN, CT0, reply_text, hook_result)

                if reply_ok:
                    print(f"          ✅ Two-step complete — Hook ID: {hook_result} | Reply ID: {reply_result}\n")
                    posted.append(row)
                else:
                    print(f"          ⚠️  Hook posted (ID={hook_result}) but reply failed: {reply_result}\n")
                    posted.append(row)  # Hook is live — still count
            elif hook_ok:
                # Hook posted but tweet_id not parseable — post reply as standalone
                print(f"          ⚠️  Hook posted but ID not parseable — posting link as standalone tweet.")
                link_tweet = format_tweet(title, url, clean_hashtags)
                ok2, res2 = xactions_post(link_tweet)
                if ok2:
                    print(f"          ✅ Standalone fallback posted — ID: {res2}\n")
                    posted.append(row)
                else:
                    print(f"          ❌ Standalone fallback also failed: {res2}\n")
                    failed.append((row, res2))
            else:
                print(f"          ❌ Hook failed: {hook_result}\n")
                failed.append((row, hook_result))

        else:
            # ── Single-tweet mode (legacy) ───────────────────────────────
            tweet_text = format_tweet(title, url, hashtags)
            success, result = xactions_post(tweet_text)

            if success:
                print(f"          ✅ Tweet ID: {result}\n")
                posted.append(row)
            else:
                print(f"          ❌ Failed: {result}\n")
                failed.append((row, result))

        # Rate limit safety: 8s between tweets
        if i < len(real_rows):
            print(f"          ⏳ Waiting 8s (X rate limit safety)...")
            time.sleep(8)

    print("─" * 60)
    print(f"\n✅ Posted: {len(posted)} tweets")
    print(f"❌ Failed: {len(failed)} tweets")

    if failed:
        print("\nFailed entries:")
        for row, err in failed:
            print(f"  - {row.get('title', '')[:50]} → {err}")

    # Clear successfully posted rows from CSV
    if posted:
        remaining = [r for r in rows if r not in posted]
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "url", "hashtags", "created_at"])
            writer.writeheader()
            writer.writerows(remaining)
        print(f"\n🧹 Cleared {len(posted)} posted entries from posts.csv")
        print(f"   {len(remaining)} entries remain in queue")


if __name__ == "__main__":
    main()
