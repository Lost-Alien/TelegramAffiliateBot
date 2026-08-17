"""
scanner.py — Discovers trending Indian tech tweets and discussions to comment on.

Discovery is tiered to spread engagement across many accounts while keeping
Exa credit usage low:

1. PRIMARY   — Exa search targeted directly at TARGET_TECH_ACCOUNTS, batched
               into a handful of queries (ACCOUNT_QUERY_BATCH_SIZE accounts
               per call) and domain-restricted to twitter.com/x.com so every
               credit spent is likely to return a usable tweet.
2. SECONDARY — Free, credit-less fallback (account_fallback.py, via the
               authenticated twikit session) used only if Exa errors out or
               returns nothing at all.
3. TERTIARY  — Generic topic search (EXA_SEARCH_TOPICS), used only as a last
               resort when the above two don't produce enough candidates.

Per-account daily caps (MAX_REPLIES_PER_ACCOUNT_PER_DAY) are enforced here so
candidates from accounts already replied to enough times today are skipped
before ever spending a search credit on them.
"""

import logging
import random
import re
import time
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
    """Target accounts that haven't hit today's per-account reply cap yet, daily-rotated."""
    eligible = [
        acc for acc in TARGET_TECH_ACCOUNTS
        if get_account_daily_count(acc) < MAX_REPLIES_PER_ACCOUNT_PER_DAY
    ]
    # Deterministic-per-day shuffle: gives every account a fair rotation
    # through the list across runs/days without needing extra state.
    rng = random.Random(time.strftime("%Y-%m-%d"))
    rng.shuffle(eligible)
    return eligible


def _batch(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def scan_account_tweets(limit: int) -> List[Dict[str, Any]]:
    """PRIMARY: Exa search batched and targeted at TARGET_TECH_ACCOUNTS' profiles."""
    accounts = _eligible_accounts()
    if not accounts:
        logger.info("All target accounts have hit their daily per-account reply cap.")
        return []

    exa = get_exa_client()
    candidates: List[Dict[str, Any]] = []
    seen_ids = set()

    for batch in _batch(accounts, ACCOUNT_QUERY_BATCH_SIZE):
        if len(candidates) >= limit * 2:
            break

        site_filter = " OR ".join(f"site:x.com/{acc} OR site:twitter.com/{acc}" for acc in batch)
        query = f"({site_filter}) latest tweet launch review price specs"

        try:
            logger.info(f"Exa account-batch query for: {batch}")
            results = exa.search(
                query=query,
                type="auto",
                num_results=6,
                include_domains=["twitter.com", "x.com"],
                contents={"highlights": True},
            )

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

        except Exception as exc:
            logger.debug(f"Exa account-batch scan notice for {batch}: {exc}")

    logger.info(f"Discovered {len(candidates)} unreplied candidates from account-targeted Exa scan.")
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

    # Only probe as many accounts as plausibly needed (each account costs a
    # real network round-trip with no Exa credits, but isn't instant either).
    accounts = _eligible_accounts()[:max(limit * 3, 6)]
    candidates: List[Dict[str, Any]] = []
    seen_ids = set()

    # Fetched in a single batched call (one event loop for every account) —
    # see account_fallback.py for why per-account asyncio.run() calls break.
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

    logger.info(f"Discovered {len(candidates)} unreplied candidates from free fallback scan.")
    return candidates


def scan_topic_tweets(limit: int) -> List[Dict[str, Any]]:
    """TERTIARY (last resort): generic topic search, only used to conserve Exa credits."""
    exa = get_exa_client()
    candidates: List[Dict[str, Any]] = []
    seen_ids = set()

    for topic in EXA_SEARCH_TOPICS:
        if len(candidates) >= limit * 2:
            break

        query = f"{topic} India review price specs discussion"
        try:
            logger.info(f"Exa topic-fallback query: {query}")
            results = exa.search(
                query=query,
                type="auto",
                num_results=3,
                include_domains=["twitter.com", "x.com"],
                contents={"highlights": True},
            )

            for item in getattr(results, "results", []):
                url = getattr(item, "url", "")
                tweet_id = extract_tweet_id(url)
                if not tweet_id or tweet_id in seen_ids or already_replied(tweet_id):
                    continue

                author = extract_author_from_url(url) or getattr(item, "author", "")
                highlights = getattr(item, "highlights", [])
                snippet = " ".join(highlights) if highlights else getattr(item, "title", "")
                candidates.append({
                    "id": tweet_id,
                    "url": url,
                    "title": getattr(item, "title", ""),
                    "text": snippet,
                    "author": author,
                    "topic": topic,
                })
                seen_ids.add(tweet_id)
        except Exception as exc:
            logger.debug(f"Exa topic scan notice for topic '{topic}': {exc}")

    logger.info(f"Discovered {len(candidates)} unreplied candidates from topic-fallback Exa scan.")
    return candidates


def scan_trending_tech_news(limit: int) -> List[Dict[str, Any]]:
    """QUATERNARY: Real-time Exa market intelligence search across authoritative tech news and reviews."""
    exa = get_exa_client()
    candidates: List[Dict[str, Any]] = []
    seen_titles = set()

    for topic in EXA_SEARCH_TOPICS:
        if len(candidates) >= limit:
            break

        query = f"{topic} India price discount sale specs review"
        try:
            results = exa.search(
                query=query,
                type="auto",
                num_results=2,
                contents={"highlights": True},
            )

            for item in getattr(results, "results", []):
                title = getattr(item, "title", "").strip()
                if not title or title in seen_titles:
                    continue

                highlights = getattr(item, "highlights", [])
                snippet = " ".join(highlights) if highlights else title
                candidates.append({
                    "id": None,
                    "url": getattr(item, "url", ""),
                    "title": title,
                    "text": snippet[:500],
                    "author": "",
                    "topic": topic,
                })
                seen_titles.add(title)
        except Exception as exc:
            logger.debug(f"Exa news scan notice for '{topic}': {exc}")

    logger.info(f"Discovered {len(candidates)} live market candidates from Exa intelligence scan.")
    return candidates


def scan_candidate_tweets(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Orchestrates tiered discovery:
    1. Primary: Account-targeted Exa search
    2. Secondary: Authenticated fallback scraper
    3. Tertiary: Exa Twitter topic search
    4. Quaternary: Real-time Exa live market intelligence (guaranteed results)
    """
    candidates = scan_account_tweets(limit)

    if not candidates:
        candidates = scan_account_tweets_fallback(limit)

    if len(candidates) < limit:
        remaining = limit - len(candidates)
        seen_ids = {c["id"] for c in candidates if c.get("id")}
        for c in scan_topic_tweets(remaining):
            if c["id"] not in seen_ids:
                candidates.append(c)
                seen_ids.add(c["id"])

    # If Twitter-specific URLs are empty, pull real-time Exa live market intelligence
    if len(candidates) < limit:
        remaining = limit - len(candidates)
        candidates.extend(scan_trending_tech_news(remaining))

    return candidates[:limit]
