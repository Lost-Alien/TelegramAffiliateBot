"""
run.py — Main orchestrator for TechSelect X Auto-Commenter.
Can be executed locally or via GitHub Actions.
"""

import logging
import random
import sys
import time
from typing import List, Dict, Any

from x_commenter.config_x import (
    MAX_REPLIES_PER_RUN,
    MAX_REPLIES_PER_DAY,
    MAX_REPLIES_PER_ACCOUNT_PER_DAY,
    MIN_DELAY_BETWEEN_REPLIES_SEC,
    ENABLE_QUOTE_REPOSTS,
    MAX_QUOTE_REPOSTS_PER_RUN,
    MAX_QUOTE_REPOSTS_PER_DAY,
    QUOTE_REPOST_CHANCE,
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


def _human_pause():
    delay = MIN_DELAY_BETWEEN_REPLIES_SEC + random.randint(10, 45)
    logger.info(f"Waiting {delay}s before next action to maintain human pacing...")
    time.sleep(delay)


def run_session() -> int:
    """
    Executes a single commenting session: replies AND quote-reposts
    ("repost with own thoughts"). Returns the total number of successful
    actions (replies + quote-reposts) posted.
    """
    logger.info("=== Starting TechSelect X Auto-Commenter Session ===")
    if DRY_RUN:
        logger.info("Running in DRY_RUN mode (no tweets will actually be posted).")

    # 1. Daily Quota Guards (replies and quote-reposts have independent budgets)
    current_daily = get_daily_count()
    logger.info(f"Daily replies posted so far: {current_daily}/{MAX_REPLIES_PER_DAY}")
    remaining_daily = max(0, MAX_REPLIES_PER_DAY - current_daily)
    target_replies = min(MAX_REPLIES_PER_RUN, remaining_daily)

    target_quotes = 0
    if ENABLE_QUOTE_REPOSTS:
        current_quote_daily = get_quote_daily_count()
        logger.info(f"Daily quote-reposts posted so far: {current_quote_daily}/{MAX_QUOTE_REPOSTS_PER_DAY}")
        remaining_quote_daily = max(0, MAX_QUOTE_REPOSTS_PER_DAY - current_quote_daily)
        target_quotes = min(MAX_QUOTE_REPOSTS_PER_RUN, remaining_quote_daily)

    if target_replies <= 0 and target_quotes <= 0:
        logger.info("Daily reply and quote-repost limits reached. Exiting gracefully to protect account.")
        return 0

    logger.info(f"Targeting up to {target_replies} reply/replies and {target_quotes} quote-repost(s) this run.")

    # 2. Scan for candidate discussions
    scan_limit = max((target_replies + target_quotes) * 3, 3)
    candidates: List[Dict[str, Any]] = scan_candidate_tweets(limit=scan_limit)

    # If no specific tweet URLs were found in general search, synthesize an authoritative market commentary tweet
    if not candidates:
        logger.info("No unreplied tweet URLs found in scan. Generating a standalone market commentary update.")
        candidates = [{
            "id": None,
            "url": None,
            "title": "Indian Tech Market Price-to-Performance Highlight",
            "text": "Latest smartphone and laptop deals in India with street pricing and discounts.",
            "author": "",
            "topic": "Indian Tech Value Comparison",
        }]

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

        account_capped = bool(author) and get_account_daily_count(author) >= MAX_REPLIES_PER_ACCOUNT_PER_DAY

        can_reply = (
            posted_count < target_replies
            and not (tweet_id and already_replied(tweet_id))
            and not account_capped
        )
        can_quote = (
            quoted_count < target_quotes
            and tweet_id and tweet_url
            and not already_quoted(tweet_id)
        )

        if not can_reply and not can_quote:
            if tweet_id and already_replied(tweet_id):
                logger.info(f"Skipping already-replied tweet ID: {tweet_id}")
            elif account_capped:
                logger.info(f"Skipping @{author}: already hit daily per-account reply cap ({MAX_REPLIES_PER_ACCOUNT_PER_DAY}).")
            continue

        # Randomly prefer a quote-repost over a plain reply when both are viable,
        # to keep a natural mix of engagement types across accounts.
        do_quote = can_quote and (not can_reply or random.random() < QUOTE_REPOST_CHANCE)

        action_label = "quote-repost" if do_quote else "reply"
        logger.info(f"Processing candidate [{idx+1}/{len(candidates)}] as {action_label}: {topic} | {text[:50]}...")

        # 3. Generate structured text with Exa AI
        generator = generate_quote_commentary if do_quote else generate_techselect_reply
        gen_result = generator(tweet_text=text, topic=topic, author=author)

        if not gen_result or not gen_result.get("reply"):
            logger.warning(f"Failed to generate valid {action_label} text. Skipping candidate.")
            continue

        gen_text = gen_result["reply"]
        contains_num = gen_result.get("contains_number", False)
        logger.info(f"Generated TechSelect text (len={len(gen_text)}, num={contains_num}):\n'{gen_text}'")

        # 4. Safety rule: Must contain concrete numbers/specs
        if not contains_num:
            logger.warning(f"{action_label.capitalize()} text lacks concrete data point (price/spec). Skipping for quality control.")
            continue

        # 5. Post to X
        if do_quote:
            success = post_quote_tweet(comment_text=gen_text, quoted_tweet_url=tweet_url)
            if success:
                mark_quoted(tweet_id, gen_text)
                new_q_count = increment_quote_daily_count()
                quoted_count += 1
                logger.info(f"Quote-repost #{quoted_count} successfully recorded (Daily total: {new_q_count}/{MAX_QUOTE_REPOSTS_PER_DAY}).")
                if posted_count < target_replies or quoted_count < target_quotes:
                    _human_pause()
            else:
                logger.error("Failed to post quote-repost. Moving to next candidate.")
        else:
            success = post_reply(reply_text=gen_text, in_reply_to_tweet_id=tweet_id)
            if success:
                if tweet_id:
                    mark_replied(tweet_id, gen_text)
                if author:
                    increment_account_daily_count(author)
                new_count = increment_daily_count()
                posted_count += 1
                logger.info(f"Reply #{posted_count} successfully recorded (Daily total: {new_count}/{MAX_REPLIES_PER_DAY}).")
                if posted_count < target_replies or quoted_count < target_quotes:
                    _human_pause()
            else:
                logger.error("Failed to post reply. Moving to next candidate.")

    logger.info(f"=== Session Completed: {posted_count} replies + {quoted_count} quote-repost(s) posted ===")
    return posted_count + quoted_count


if __name__ == "__main__":
    posted = run_session()
    sys.exit(0)
