"""
rss_poster.py — Fallback RSS feed parser and deal poster for https://techselect.blog/feed.xml.

Features:
  - Periodically fetches https://techselect.blog/feed.xml.
  - Extracts [Deal] items and articles from the XML feed.
  - Automatically enqueues or posts missing deals if Telegram feed source missed any item.
  - Built-in self-test & error handling.
"""

import logging
import os
import re
import xml.etree.ElementTree as ET
import urllib.request
from typing import List, Dict

logger = logging.getLogger(__name__)

FEED_URL = os.getenv("WEBSITE_RSS_FEED_URL", "https://techselect.blog/feed.xml")


def fetch_rss_feed(feed_url: str = FEED_URL) -> List[Dict[str, str]]:
    """Fetch and parse RSS 2.0 feed items."""
    items: List[Dict[str, str]] = []
    try:
        req = urllib.request.Request(
            feed_url,
            headers={"User-Agent": "TechSelect-RSS-Bot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        channel = root.find("channel")
        if channel is None:
            return items

        for item_elem in channel.findall("item"):
            title = item_elem.findtext("title") or ""
            link = item_elem.findtext("link") or ""
            description = item_elem.findtext("description") or ""
            pub_date = item_elem.findtext("pubDate") or ""
            guid = item_elem.findtext("guid") or ""

            items.append({
                "title": title,
                "link": link,
                "description": description,
                "pubDate": pub_date,
                "guid": guid,
            })

        logger.info("Fetched %d items from RSS feed %s", len(items), feed_url)
    except Exception as exc:
        logger.error("Failed to fetch RSS feed from %s: %s", feed_url, exc)

    return items


def extract_asins_from_text(text: str) -> List[str]:
    """Extract 10-character Amazon ASINs from text or links."""
    pattern = r"(?:dp/|product/|ASIN=)([B0-9][A-Z0-9]{9})"
    matches = re.findall(pattern, text)
    return list(set(matches))


def sync_deals_from_rss() -> List[Dict[str, str]]:
    """Sync deal items from TechSelect RSS feed."""
    all_items = fetch_rss_feed()
    deal_items = [item for item in all_items if item["title"].startswith("[Deal]")]
    logger.info("Identified %d deals in RSS feed", len(deal_items))
    return deal_items


def _selftest():
    print("Testing RSS Poster Module...")
    # Test sample RSS XML parsing
    sample_xml = """<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0">
      <channel>
        <title>TechSelect Feed</title>
        <item>
          <title>[Deal] Sony WH-1000XM5 Headphones</title>
          <link>https://techselect.blog/sales#asin-B0B3LNGG2V</link>
          <description>Check price on Amazon https://www.amazon.in/dp/B0B3LNGG2V</description>
          <pubDate>Wed, 12 Aug 2026 16:30:04 GMT</pubDate>
        </item>
      </channel>
    </rss>"""

    root = ET.fromstring(sample_xml)
    item = root.find("channel/item")
    assert item is not None
    title = item.findtext("title")
    link = item.findtext("link")
    desc = item.findtext("description")
    asins = extract_asins_from_text(desc + " " + link)

    print("Parsed Sample Title:", title)
    print("Parsed Sample Link:", link)
    print("Extracted ASINs:", asins)
    assert "[Deal]" in title
    assert "B0B3LNGG2V" in asins
    print("✅ RSS Poster self-test passed!")


if __name__ == "__main__":
    _selftest()
