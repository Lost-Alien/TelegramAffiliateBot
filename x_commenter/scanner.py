"""
scanner.py — Discovers trending Indian tech tweets and discussions to comment on.

Discovery is tiered to conserve Exa credits while maximising tweet quality:

1. PRIMARY   — Exa neural search targeted at TARGET_TECH_ACCOUNTS, domain-restricted
               to twitter.com/x.com. Each batch of ACCOUNT_QUERY_BATCH_SIZE accounts
               shares one Exa call. Results have real tweet IDs usable as reply targets.

2. SECONDARY — Free, credit-less fallback (account_fallback.py via the authenticated
               twikit session). Used only if Exa errors out or returns nothing.
               Results also have real tweet IDs.

3. TERTIARY  — Exa topic search restricted to twitter.com/x.com — last resort for
               finding tweetable content when the account lists produce nothing.
               Results have real tweet IDs.

NOTE: The previous QUATERNARY tier (scan_trending_tech_news) searched unconstrained
web sources and returned id=None candidates. These were incorrectly flowing into the
reply pipeline and being posted as standalone tweets even when the daily cap was
exhausted. That tier has been REMOVED. Standalone commentary is now handled solely
by run.py's topic-based fallback when ALL tiers return zero results.

Per-account daily caps (MAX_REPLIES_PER_ACCOUNT_PER_DAY) are enforced here so
candidates from accounts already replied to enough times today are skipped.
"""

import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from exa_py import Exa

from x_commenter.config_x import (
    ACCOUNT_QUERY_BATCH_SIZE,
    ENABLE_ACCOUNT_FALLBACK_SCRAPER,
    EXA_API_KEY,
    EXA_SEARCH_TOPICS,
    MAX_REPLIES_PER_ACCOUNT_PER_DAY,
    TARGET_TECH_ACCOUNTS,
)
from x_commenter.state import already_replied, get_account_daily_count

logger = logging.getLogger("x_commenter.scanner")

_exa_client: Optional[Exa] = None

# Exa PRIMARY window: tweets posted within the last 48 hours
_RECENCY_HOURS = 48

# Twitter/X domains — used in all tiers to guarantee real tweet IDs
_TWITTER_DOMAINS = ["twitter.com", "x.com"]


def get_exa_client() -> Exa:
    global _exa_client
    if _exa_client is None:
        _exa_client = Exa(api_key=EXA_API_KEY)
    return _exa_client


def extract_tweet_id(url: str) -> Optional[str]:
    """Extract tweet ID from any X/Twitter URL."""
    if not url:
        return None
    match = re.search(r"(?:twitter\.com|x\.com)/[^/]+/status/(\d+)", url)
    return match.group(1) if match else None


def extract_author_from_url(url: str) -> str:
    """Extract the account handle from any X/Twitter status URL."""
    if not url:
        return ""
    match = re.search(r"(?:twitter\.com|x\.com)/([^/]+)/status/\d+", url)
    return match.group(1) if match else ""


def _eligible_accounts() -> List[str]:
    """Target accounts that haven't hit today's per-account reply cap, daily-rotated."""
    eligible = [
        acc for acc in TARGET_TECH_ACCOUNTS
        if get_account_daily_count(acc) < MAX_REPLIES_PER_ACCOUNT_PER_DAY
    ]
    # Deterministic-per-day shuffle: fair rotation across accounts without extra state
    rng = random.Random(time.strftime("%Y-%m-%d"))
    rng.shuffle(eligible)
    return eligible


def _batch(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _cutoff_timestamp() -> str:
    """ISO timestamp for the start of the recency window."""
    return (
        datetime.now(timezone.utc) - timedelta(hours=_RECENCY_HOURS)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_exa_results(results, seen_ids: set) -> List[Dict[str, Any]]:
    """
    Extract valid tweet candidates from an Exa search result object.
    Only includes items that:
      - Have a real tweet URL (x.com/*/status/*)
      - Have a tweet ID not already seen or replied to
      - Come from an account not over its daily cap
    """
    candidates: List[Dict[str, Any]] = []
    for item in getattr(results, "results", []):
        url = getattr(item, "url", "")
        tweet_id = extract_tweet_id(url)
        if not tweet_id or tweet_id in seen_ids or already_replied(tweet_id):
            continue

        author = extract_author_from_url(url) or getattr(item, "author", "")
        if author and get_account_daily_count(author) >= MAX_REPLIES_PER_ACCOUNT_PER_DAY:
            continue

        highlights = getattr(item, "highlights", [])
        snippet = " ".join(highlights) if highlights else getattr(item, "title", "")

        candidates.append({
            "id": tweet_id,
            "url": url,
            "title": getattr(item, "title", ""),
            "text": snippet,
            "author": author,
            "topic": f"{author or 'Indian Tech'} update",
        })
        seen_ids.add(tweet_id)

    return candidates


def scan_account_tweets(limit: int) -> List[Dict[str, Any]]:
    """
    PRIMARY: Exa neural search targeted at TARGET_TECH_ACCOUNTS.

    Uses a clean topic query (no redundant site: operators — include_domains
    already restricts results to twitter.com and x.com). This gives Exa's
    neural ranking full freedom to surface the most engaging recent tweets
    from the target accounts without query noise.
    """
    accounts = _eligible_accounts()
    if not accounts:
        logger.info("All target accounts have hit their daily per-account reply cap.")
        return []

    exa = get_exa_client()
    candidates: List[Dict[str, Any]] = []
    seen_ids: set = set()
    cutoff = _cutoff_timestamp()

    for batch in _batch(accounts, ACCOUNT_QUERY_BATCH_SIZE):
        if len(candidates) >= limit:
            break

        # Clean natural-language query — include_domains restricts to Twitter/X,
        # so no need to embed "site:x.com/handle" noise in the query string.
        account_names = " OR ".join(batch)
        query = f"tech launch review specs India from {account_names}"

        try:
            logger.info(f"Exa PRIMARY account-batch query for: {batch}")
            results = exa.search(
                query=query,
                type="auto",
                num_results=3,          # 3 is enough; we only need 1 candidate
                include_domains=_TWITTER_DOMAINS,
                start_published_date=cutoff,
                contents={"highlights": True},
            )
            new = _parse_exa_results(results, seen_ids)
            candidates.extend(new)
            logger.debug(f"Batch {batch} yielded {len(new)} candidates.")

            # Early-exit: found at least one usable tweet, no need to burn more credits
            if candidates:
                logger.info(
                    f"Found {len(candidates)} candidate(s) in first successful batch. "
                    "Skipping remaining batches to save Exa credits."
                )
                break

        except Exception as exc:
            logger.debug(f"Exa PRIMARY scan notice for {batch}: {exc}")

    logger.info(
        f"PRIMARY scan complete: {len(candidates)} unreplied tweet candidates."
    )
    return candidates


def scan_account_tweets_fallback(limit: int) -> List[Dict[str, Any]]:
    """SECONDARY: free, credit-less scraping via the authenticated X session."""
    if not ENABLE_ACCOUNT_FALLBACK_SCRAPER:
        return []

    try:
        from x_commenter.account_fallback import fetch_accounts_tweets
    except Exception as exc:
        logger.debug(f"Account fallback scraper notice: {exc}")
        return []

    accounts = _eligible_accounts()[: max(limit * 3, 6)]
    candidates: List[Dict[str, Any]] = []
    seen_ids: set = set()

    results_by_account = fetch_accounts_tweets(accounts, count=2)

    for account in accounts:
        if len(candidates) >= limit * 2:
            break
        for tweet in results_by_account.get(account, []):
            tweet_id = tweet.get("id")
            if not tweet_id or tweet_id in seen_ids or already_replied(tweet_id):
                continue
            candidates.append(tweet)
            seen_ids.add(tweet_id)

    logger.info(
        f"SECONDARY scan complete: {len(candidates)} unreplied tweet candidates."
    )
    return candidates


def scan_topic_tweets(limit: int) -> List[Dict[str, Any]]:
    """
    TERTIARY (last resort): Exa topic search restricted to twitter.com/x.com.

    Results always have real tweet IDs, so they are safe to use as reply targets.
    Only triggered when PRIMARY + SECONDARY both return fewer than `limit` candidates.
    """
    exa = get_exa_client()
    candidates: List[Dict[str, Any]] = []
    seen_ids: set = set()
    cutoff = _cutoff_timestamp()

    for topic in EXA_SEARCH_TOPICS:
        if len(candidates) >= limit:
            break

        query = f"{topic} India review price specs discussion"
        try:
            logger.info(f"Exa TERTIARY topic query: {query[:60]}...")
            results = exa.search(
                query=query,
                type="auto",
                num_results=2,          # minimal — we only need 1 reply target
                include_domains=_TWITTER_DOMAINS,
                start_published_date=cutoff,
                contents={"highlights": True},
            )
            new = _parse_exa_results(results, seen_ids)
            candidates.extend(new)
            if candidates:
                logger.info("TERTIARY found candidates. Stopping topic loop.")
                break

        except Exception as exc:
            logger.debug(f"Exa TERTIARY notice for topic '{topic}': {exc}")

    logger.info(
        f"TERTIARY scan complete: {len(candidates)} unreplied tweet candidates."
    )
    return candidates


def scan_candidate_tweets(limit: int = 1) -> List[Dict[str, Any]]:
    """
    Orchestrates tiered discovery. All tiers return only real tweet IDs.

    Tier order:
      1. PRIMARY:   Exa account-targeted search (twitter.com/x.com)
      2. SECONDARY: Authenticated twikit fallback scraper (free, no Exa)
      3. TERTIARY:  Exa topic search (twitter.com/x.com)

    If all three tiers return nothing, run.py handles the standalone
    commentary fallback using its own topic list — no mixing of
    web-article candidates (id=None) into the reply pipeline.
    """
    candidates = scan_account_tweets(limit)

    if not candidates:
        logger.info("PRIMARY returned nothing. Trying SECONDARY (free twikit scrape)...")
        candidates = scan_account_tweets_fallback(limit)

    if len(candidates) < limit:
        remaining = limit - len(candidates)
        seen_ids = {c["id"] for c in candidates if c.get("id")}
        logger.info(
            f"TERTIARY needed for {remaining} more candidate(s)."
        )
        for c in scan_topic_tweets(remaining):
            if c.get("id") and c["id"] not in seen_ids:
                candidates.append(c)
                seen_ids.add(c["id"])

    logger.info(
        f"Total candidates after all tiers: {len(candidates)} "
        f"(limit={limit})"
    )
    return candidates[:limit]
