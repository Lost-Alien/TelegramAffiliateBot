"""
cuelinks_converter.py — Multi-Merchant Link Monetization via Cuelinks V3 API.

Converts links from Flipkart, Croma, Myntra, Ajio, Tata CliQ, Samsung, Boat, etc.
into monetized affiliate redirect URLs using your official Cuelinks Publisher CID: 307730.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

CUELINKS_API_KEY = os.getenv("CUELINKS_API_KEY", "LmNADAnOLIEimDh8ItTaUEqjy1W_QTnfEkdXIaXqn7c").strip()
CUELINKS_BASE_URL = "https://developers.cuelinks.com/pub_api/v3"
DEFAULT_CID = "307730"

# Domains supported by Cuelinks (non-Amazon stores)
CUELINKS_SUPPORTED_DOMAINS = [
    "flipkart.com",
    "fkrt.it",
    "myntra.com",
    "croma.com",
    "ajio.com",
    "tatacliq.com",
    "reliancedigital.in",
    "samsung.com",
    "boat-lifestyle.com",
    "nykaa.com",
    "firstcry.com",
    "vijaysales.com",
    "jiomart.com",
    "pepperfry.com",
    "lenskart.com",
    "cleartrip.com",
    "makemytrip.com",
    "swiggy.com",
    "zomato.com",
    "dominos.co.in",
]


def is_cuelinks_supported(url: str) -> bool:
    """Check if URL belongs to a Cuelinks-supported merchant (non-Amazon)."""
    if "amazon." in url.lower() or "amzn.to" in url.lower():
        return False
    return any(d in url.lower() for d in CUELINKS_SUPPORTED_DOMAINS)


def convert_url_via_cuelinks(url: str, sub_id: str = "techselect_deals") -> str:
    """Convert any merchant URL into a monetized Cuelinks affiliate link.

    Uses Cuelinks V3 API endpoint: POST /pub_api/v3/links/convert.
    Falls back to direct linksredirect wrapper if API is unreachable.
    """
    if not is_cuelinks_supported(url):
        return url

    if not CUELINKS_API_KEY:
        encoded_url = urllib.parse.quote(url, safe="")
        return f"https://linksredirect.com/?cid={DEFAULT_CID}&subid={sub_id}&source=direct&url={encoded_url}"

    endpoint = f"{CUELINKS_BASE_URL}/links/convert"
    headers = {
        "Authorization": f"Token {CUELINKS_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "TechSelect-AutoPoster/1.0",
    }
    payload = {
        "url": url,
        "sub_id": sub_id,
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            data = res.get("data", {})
            aff_url = data.get("affiliate_url") or data.get("tracking_url")
            if aff_url:
                logger.info("✓ Cuelinks converted URL: %s -> %s", url[:50], aff_url[:60])
                return aff_url
    except Exception as e:
        logger.warning("Cuelinks API conversion failed (%s), using direct redirect wrapper", e)

    encoded = urllib.parse.quote(url, safe="")
    return f"https://linksredirect.com/?cid={DEFAULT_CID}&subid={sub_id}&source=api&url={encoded}"


def monetize_all_links_in_text(text: str, sub_id: str = "techselect") -> str:
    """Find and replace all supported merchant links in deal text with Cuelinks affiliate links."""
    url_pattern = re.compile(r"https?://[^\s<>\"']+")

    def _replace_match(match: re.Match) -> str:
        raw_url = match.group(0)
        if is_cuelinks_supported(raw_url):
            return convert_url_via_cuelinks(raw_url, sub_id=sub_id)
        return raw_url

    return url_pattern.sub(_replace_match, text)


if __name__ == "__main__":
    test_flipkart = "https://www.flipkart.com/apple-iphone-15-black-128-gb/p/itm6ac6485515ae4"
    result = convert_url_via_cuelinks(test_flipkart)
    print("Test Flipkart Conversion:\n", result)
