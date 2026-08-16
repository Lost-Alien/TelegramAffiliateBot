"""
scanner.py — Discovers trending Indian tech tweets and discussions to comment on.
Leverages Exa AI search and target creator references.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from exa_py import Exa
from x_commenter.config_x import EXA_API_KEY, EXA_SEARCH_TOPICS, TARGET_TECH_ACCOUNTS
from x_commenter.state import already_replied

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
    if match:
        return match.group(1)
    return None


def scan_candidate_tweets(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search for trending Indian tech topics, discussions, and reviews.
    Returns a list of candidate tweet targets with ID, URL, text, and author.
    """
    exa = get_exa_client()
    candidates: List[Dict[str, Any]] = []
    seen_ids = set()

    for topic in EXA_SEARCH_TOPICS:
        if len(candidates) >= limit * 2:
            break

        query = f"{topic} India review price specs discussion"
        try:
            logger.info(f"Exa search query: {query}")
            results = exa.search(
                query=query,
                type="auto",
                num_results=3,
                contents={"highlights": True},
            )

            for item in getattr(results, "results", []):
                url = getattr(item, "url", "")
                tweet_id = extract_tweet_id(url)
                
                # If the search result is an X link:
                if tweet_id and tweet_id not in seen_ids:
                    if not already_replied(tweet_id):
                        highlights = getattr(item, "highlights", [])
                        snippet = " ".join(highlights) if highlights else getattr(item, "title", "")
                        candidates.append({
                            "id": tweet_id,
                            "url": url,
                            "title": getattr(item, "title", ""),
                            "text": snippet,
                            "author": getattr(item, "author", ""),
                            "topic": topic,
                        })
                        seen_ids.add(tweet_id)
        except Exception as exc:
            logger.warning(f"Exa scan error for topic '{topic}': {exc}")

    logger.info(f"Discovered {len(candidates)} unreplied candidates from Exa scan.")
    return candidates[:limit]
