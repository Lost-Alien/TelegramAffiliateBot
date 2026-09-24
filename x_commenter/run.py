"""
run.py — Main orchestrator for TechSelect X Auto-Commenter.
Can be executed locally or via GitHub Actions.
"""

import logging
import random
import sys
import time
import warnings
from typing import List, Dict, Any

warnings.filterwarnings("ignore")

from x_commenter.config_x import (
    MAX_REPLIES_PER_RUN,
    MAX_REPLIES_PER_DAY,
    MAX_REPLIES_PER_ACCOUNT_PER_DAY,
    MIN_DELAY_BETWEEN_REPLIES_SEC,
    ENABLE_QUOTE_REPOSTS,
    MAX_QUOTE_REPOSTS_PER_RUN,
    MAX_QUOTE_REPOSTS_PER_DAY,
    QUOTE_REPOST_CHANCE,
    ALWAYS_POST_STANDALONE,
    DRY_RUN,
)
from x_commenter.state import (
    get_daily_count,
    increment_daily_count,
    already_replied,
    mark_replied,
    get_account_daily_count,
    increment_account_daily_count,
    already_quoted,
    mark_quoted,
    get_quote_daily_count,
    increment_quote_daily_count,
)
from x_commenter.scanner import scan_candidate_tweets
from x_commenter.reply_gen import generate_techselect_reply, generate_quote_commentary
from x_commenter.poster import post_reply, post_quote_tweet

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("x_commenter")

# ── Standalone topic pool ────────────────────────────────────────────────────
# Used ONLY when all three scanner tiers return zero candidates.
# Topics are pure editorial analysis — no deals, no Amazon links, no pricing angles.
_STANDALONE_TOPICS = [
    (
        "Indian Chipset Benchmark Analysis",
        "Dimensity 9300 vs Snapdragon 8 Gen 3 sustained performance in India flagship phones: "
        "real thermal throttle data, AnTuTu sustained vs peak, and which holds up after "
        "20 minutes of gaming.",
    ),
    (
        "Budget 5G India 2024 Camera Real-World",
        "Phones under 25000 in India: 108MP marketing vs actual DxO-style scores, pixel "
        "binning quality, night mode noise floor — what the spec sheet hides.",
    ),
    (
        "Gaming Laptop India Thermals 2024",
        "Sub-1-lakh gaming laptops India: sustained GPU TGP after 30 min load, throttle "
        "percentage, and which BIOS modes actually matter for competitive titles.",
    ),
    (
        "MacBook Air M3 Battery vs Windows",
        "MacBook Air M3 vs Asus Zenbook 14 OLED in real Indian usage: idle drain at 200 nits, "
        "video playback longevity, and whether the premium holds for engineering students.",
    ),
    (
        "Display Panel India Value Tier",
        "AMOLED vs IPS at Rs 20,000 segment India: peak brightness, PWM frequency, colour "
        "accuracy delta-E, and whether the surcharge is justified for outdoor Indian summers.",
    ),
    (
        "Telecom Hike Impact on Data Cost India",
        "Post-Jio/Airtel hike effective data cost per GB vs 2022 baseline, and how it changes "
        "the value equation for Wi-Fi-only tablets vs SIM-enabled smartphones for remote work.",
    ),
]


def _human_pause() -> None:
    """XActions-style randomised micro-jitter pacing between posts."""
    base = MIN_DELAY_BETWEEN_REPLIES_SEC
    jitter = base * 0.25 * (random.random() - 0.5)
    delay = max(20, int(base + jitter + random.randint(5, 20)))
    logger.info(f"Waiting {delay}s before next action (natural human pacing)...")
    time.sleep(delay)


def run_session() -> int:
    """
    Executes a single commenting session.

    Flow:
      1. Read daily counters (Redis -> SQLite fallback).
      2. If BOTH reply AND quote budgets are exhausted, exit immediately.
         ALWAYS_POST_STANDALONE no longer bypasses the daily cap — it
         only allows a standalone post when the scanner found real tweets
         but the reply cap happened to reset mid-run. The daily cap is
         the single source of truth.
      3. Run the 3-tier scanner to find tweet candidates.
      4. If the scanner finds nothing (all tiers empty), fall back to a
         random standalone topic post — but only if the daily cap still
         has room (i.e., today's count is 0).
      5. Generate reply / quote commentary via Exa AI.
      6. Post via cookie-auth GraphQL. Track state.

    Returns the total number of successful actions posted.
    """
    logger.info("=== Starting TechSelect X Auto-Commenter Session ===")
    if DRY_RUN:
        logger.info("Running in DRY_RUN mode (no tweets will actually be posted).")

    # ── 1. Daily quota guards ─────────────────────────────────────────────────
    current_daily = get_daily_count()
    logger.info(f"Daily replies posted so far: {current_daily}/{MAX_REPLIES_PER_DAY}")
    remaining_daily = max(0, MAX_REPLIES_PER_DAY - current_daily)
    target_replies = min(MAX_REPLIES_PER_RUN, remaining_daily)

    target_quotes = 0
    if ENABLE_QUOTE_REPOSTS:
        current_quote_daily = get_quote_daily_count()
        logger.info(
            f"Daily quote-reposts posted so far: {current_quote_daily}/{MAX_QUOTE_REPOSTS_PER_DAY}"
        )
        remaining_quote_daily = max(0, MAX_QUOTE_REPOSTS_PER_DAY - current_quote_daily)
        target_quotes = min(MAX_QUOTE_REPOSTS_PER_RUN, remaining_quote_daily)

    # Hard exit: both budgets are exhausted — respect the daily cap.
    # ALWAYS_POST_STANDALONE no longer overrides this; the 1/day limit is strict.
    if target_replies <= 0 and target_quotes <= 0:
        logger.info(
            "Daily reply and quote-repost limits reached. "
            "Exiting to protect account health."
        )
        return 0

    logger.info(
        f"Targeting up to {target_replies} reply/replies "
        f"and {target_quotes} quote-repost(s) this run."
    )

    # ── 2. Scan for candidate tweets ─────────────────────────────────────────
    scan_limit = max(target_replies + target_quotes, 1)
    candidates: List[Dict[str, Any]] = scan_candidate_tweets(limit=scan_limit)

    # ── 3. Standalone fallback ────────────────────────────────────────────────
    # Only used when the scanner found ZERO usable tweet URLs AND today's post
    # count is still 0 (i.e., we genuinely haven't posted yet today).
    # This ensures we always have at least 1 editorial post per day even if
    # Twitter's scraping is flaky, while still respecting the daily limit.
    if not candidates:
        if current_daily > 0 or (ENABLE_QUOTE_REPOSTS and current_quote_daily > 0):
            logger.info(
                "Scanner found no tweets, but we've already posted today. "
                "Skipping standalone to avoid exceeding 1/day."
            )
            return 0

        if ALWAYS_POST_STANDALONE:
            topic_title, topic_text = random.choice(_STANDALONE_TOPICS)
            logger.info(
                f"Scanner found no tweets. Standalone fallback: '{topic_title}'"
            )
            candidates = [
                {
                    "id": None,
                    "url": None,
                    "title": topic_title,
                    "text": topic_text,
                    "author": "",
                    "topic": topic_title,
                }
            ]
        else:
            logger.info("Scanner found no tweets and ALWAYS_POST_STANDALONE is off. Exiting.")
            return 0

    # ── 4. Post loop ──────────────────────────────────────────────────────────
    posted_count = 0
    quoted_count = 0

    for idx, cand in enumerate(candidates):
        if posted_count >= target_replies and quoted_count >= target_quotes:
            break

        tweet_id = cand.get("id")
        tweet_url = cand.get("url")
        author = cand.get("author", "")
        topic = cand.get("topic", "")
        text = cand.get("text", "")

        account_capped = (
            bool(author) and get_account_daily_count(author) >= MAX_REPLIES_PER_ACCOUNT_PER_DAY
        )

        can_reply = (
            posted_count < target_replies
            and not (tweet_id and already_replied(tweet_id))
            and not account_capped
        )
        can_quote = (
            quoted_count < target_quotes
            and tweet_id is not None
            and tweet_url is not None
            and not already_quoted(tweet_id)
        )

        if not can_reply and not can_quote:
            if tweet_id and already_replied(tweet_id):
                logger.info(f"Skipping already-replied tweet ID: {tweet_id}")
            elif account_capped:
                logger.info(
                    f"Skipping @{author}: already hit daily per-account reply cap "
                    f"({MAX_REPLIES_PER_ACCOUNT_PER_DAY})."
                )
            continue

        # Randomly prefer quote-repost over plain reply when both are viable
        do_quote = can_quote and (not can_reply or random.random() < QUOTE_REPOST_CHANCE)

        action_label = "quote-repost" if do_quote else "reply"
        logger.info(
            f"Processing candidate [{idx + 1}/{len(candidates)}] as {action_label}: "
            f"{topic} | {text[:50]}..."
        )

        # ── 5. Generate text via Exa AI ───────────────────────────────────────
        generator = generate_quote_commentary if do_quote else generate_techselect_reply
        gen_result = generator(tweet_text=text, topic=topic, author=author)

        if not gen_result or not gen_result.get("reply"):
            logger.info(f"Could not generate valid {action_label} text. Skipping candidate.")
            continue

        gen_text = gen_result["reply"]
        contains_num = gen_result.get("contains_number", False)

        # Quality gate: reply must contain a concrete number/spec
        if not contains_num:
            logger.info(
                f"{action_label.capitalize()} text lacks concrete data point. "
                "Skipping for quality control."
            )
            continue

        # ── 6. Post to X ──────────────────────────────────────────────────────
        if do_quote:
            success = post_quote_tweet(comment_text=gen_text, quoted_tweet_url=tweet_url)
            if success:
                mark_quoted(tweet_id, gen_text)
                new_q_count = increment_quote_daily_count()
                quoted_count += 1
                logger.info(
                    f"Quote-repost #{quoted_count} recorded "
                    f"(Daily total: {new_q_count}/{MAX_QUOTE_REPOSTS_PER_DAY})."
                )
                if posted_count < target_replies or quoted_count < target_quotes:
                    _human_pause()
            else:
                logger.error("Failed to post quote-repost. Moving to next candidate.")

        else:
            # Attempt direct reply
            success = post_reply(reply_text=gen_text, in_reply_to_tweet_id=tweet_id)

            if not success and tweet_id:
                # X anti-automation Code 226: fall back to quote-repost
                logger.info(
                    "Direct reply failed (likely Code 226). Trying quote-repost fallback..."
                )
                if tweet_url:
                    success = post_quote_tweet(comment_text=gen_text, quoted_tweet_url=tweet_url)
                    if success:
                        mark_quoted(tweet_id, gen_text)
                        quoted_count += 1
                        new_q_count = increment_quote_daily_count()
                        logger.info(
                            f"Quote-repost fallback succeeded! "
                            f"(Daily total: {new_q_count}/{MAX_QUOTE_REPOSTS_PER_DAY})"
                        )
                        if posted_count < target_replies or quoted_count < target_quotes:
                            _human_pause()

                if not success:
                    # Last resort: standalone post (only if tweet_id is None = standalone mode)
                    if tweet_id is None:
                        success = post_reply(reply_text=gen_text, in_reply_to_tweet_id=None)
                        if success:
                            posted_count += 1
                            new_count = increment_daily_count()
                            logger.info(
                                f"Standalone post succeeded! "
                                f"(Daily total: {new_count}/{MAX_REPLIES_PER_DAY})"
                            )
                            if posted_count < target_replies or quoted_count < target_quotes:
                                _human_pause()
                    else:
                        logger.error(
                            "All posting methods failed for this candidate. Skipping."
                        )

            elif success:
                if tweet_id:
                    mark_replied(tweet_id, gen_text)
                if author:
                    increment_account_daily_count(author)
                new_count = increment_daily_count()
                posted_count += 1
                logger.info(
                    f"Reply #{posted_count} recorded "
                    f"(Daily total: {new_count}/{MAX_REPLIES_PER_DAY})."
                )
                if posted_count < target_replies or quoted_count < target_quotes:
                    _human_pause()

            else:
                logger.error("Failed to post reply and all fallbacks exhausted. Moving on.")

    logger.info(
        f"=== Session Complete: {posted_count} replies + {quoted_count} quote-repost(s) posted ==="
    )
    return posted_count + quoted_count


if __name__ == "__main__":
    posted = run_session()
    sys.exit(0)
