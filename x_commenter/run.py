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
    MIN_DELAY_BETWEEN_REPLIES_SEC,
    DRY_RUN,
)
from x_commenter.state import (
    get_daily_count,
    increment_daily_count,
    already_replied,
    mark_replied,
)
from x_commenter.scanner import scan_candidate_tweets
from x_commenter.reply_gen import generate_techselect_reply
from x_commenter.poster import post_reply

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("x_commenter")


def run_session() -> int:
    """
    Executes a single commenting session.
    Returns the number of successful replies posted.
    """
    logger.info("=== Starting TechSelect X Auto-Commenter Session ===")
    if DRY_RUN:
        logger.info("Running in DRY_RUN mode (no tweets will actually be posted).")

    # 1. Daily Quota Guard
    current_daily = get_daily_count()
    logger.info(f"Daily replies posted so far: {current_daily}/{MAX_REPLIES_PER_DAY}")
    if current_daily >= MAX_REPLIES_PER_DAY:
        logger.info("Daily reply limit reached. Exiting gracefully to protect account.")
        return 0

    remaining_daily = MAX_REPLIES_PER_DAY - current_daily
    target_replies = min(MAX_REPLIES_PER_RUN, remaining_daily)
    logger.info(f"Targeting up to {target_replies} reply/replies for this run.")

    # 2. Scan for candidate discussions
    candidates: List[Dict[str, Any]] = scan_candidate_tweets(limit=target_replies * 3)
    
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

    for idx, cand in enumerate(candidates):
        if posted_count >= target_replies:
            break

        tweet_id = cand.get("id")
        if tweet_id and already_replied(tweet_id):
            logger.info(f"Skipping already-replied tweet ID: {tweet_id}")
            continue

        topic = cand.get("topic", "")
        text = cand.get("text", "")
        logger.info(f"Processing candidate [{idx+1}/{len(candidates)}]: {topic} | {text[:50]}...")

        # 3. Generate structured reply with Exa AI
        gen_result = generate_techselect_reply(
            tweet_text=text,
            topic=topic,
            author=cand.get("author", ""),
        )

        if not gen_result or not gen_result.get("reply"):
            logger.warning("Failed to generate valid reply. Skipping candidate.")
            continue

        reply_text = gen_result["reply"]
        contains_num = gen_result.get("contains_number", False)
        logger.info(f"Generated TechSelect text (len={len(reply_text)}, num={contains_num}):\n'{reply_text}'")

        # 4. Safety rule: Must contain concrete numbers/specs
        if not contains_num:
            logger.warning("Reply lacks concrete data point (price/spec). Skipping for quality control.")
            continue

        # 5. Post to X
        success = post_reply(reply_text=reply_text, in_reply_to_tweet_id=tweet_id)
        if success:
            if tweet_id:
                mark_replied(tweet_id, reply_text)
            new_count = increment_daily_count()
            posted_count += 1
            logger.info(f"Reply #{posted_count} successfully recorded (Daily total: {new_count}/{MAX_REPLIES_PER_DAY}).")

            # Human-paced pause if more replies to post
            if posted_count < target_replies:
                delay = MIN_DELAY_BETWEEN_REPLIES_SEC + random.randint(10, 45)
                logger.info(f"Waiting {delay}s before next action to maintain human pacing...")
                time.sleep(delay)
        else:
            logger.error("Failed to post reply. Moving to next candidate.")

    logger.info(f"=== Session Completed: {posted_count} replies posted ===")
    return posted_count


if __name__ == "__main__":
    posted = run_session()
    sys.exit(0)
