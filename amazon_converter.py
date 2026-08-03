import re
from typing import List, Tuple, Optional
import httpx
from config import logger

# Regex patterns for Amazon ASINs (10-character alphanumeric, e.g. B08N5WRWNW or 10-digit ISBNs)
ASIN_PATTERNS = [
    re.compile(r'/dp/([A-Z0-9]{10})', re.IGNORECASE),
    re.compile(r'/gp/product/([A-Z0-9]{10})', re.IGNORECASE),
    re.compile(r'/gp/aw/d/([A-Z0-9]{10})', re.IGNORECASE),
    re.compile(r'/o/([A-Z0-9]{10})', re.IGNORECASE),
    re.compile(r'/product/([A-Z0-9]{10})', re.IGNORECASE),
    re.compile(r'/ASIN/([A-Z0-9]{10})', re.IGNORECASE),
    re.compile(r'[?&]asin=([A-Z0-9]{10})', re.IGNORECASE),
]

SHORT_LINK_PATTERNS = [
    re.compile(r'https?://amzn\.(?:to|in|eu|asia|com)/[A-Za-z0-9]+', re.IGNORECASE),
]

ANY_AMAZON_URL_PATTERN = re.compile(
    r'https?://(?:[a-zA-Z0-9-]+\.)?(?:amazon\.[a-z\.]+|amzn\.(?:to|in|eu|asia|com))/[^\s<>"\']+',
    re.IGNORECASE
)

DOMAIN_PATTERN = re.compile(r'https?://(?:www\.)?(amazon\.[a-z\.]+)', re.IGNORECASE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

def extract_asin(url: str) -> Optional[str]:
    """Extract 10-character Amazon Standard Identification Number (ASIN) from a URL string."""
    for pattern in ASIN_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1).upper()
    return None

def extract_domain(url: str, default_domain: str = "amazon.com") -> str:
    """Extract Amazon country domain from URL (e.g. amazon.in, amazon.co.uk) or fallback to default."""
    match = DOMAIN_PATTERN.search(url)
    if match:
        domain = match.group(1).lower()
        if domain.startswith("amazon."):
            return domain
    return default_domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").strip("/")

async def resolve_short_url(url: str) -> str:
    """Follow HTTP redirects for short Amazon URLs (e.g. amzn.to/xxx) to get full target URL."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=6.0, headers=HEADERS) as client:
            response = await client.head(url)
            if response.status_code in (405, 403):  # Fallback to GET if HEAD method is restricted
                response = await client.get(url)
            return str(response.url)
    except Exception as e:
        logger.warning(f"Could not resolve short URL {url}: {e}")
        return url

async def convert_all_amazon_links(input_text: str, affiliate_tag: str, default_domain: str = "amazon.com") -> List[Tuple[str, str]]:
    """
    Scans input_text for ALL Amazon URLs, resolves short links, extracts ASINs,
    and returns a list of tuples: [(original_url, affiliate_url), ...]
    """
    matches = ANY_AMAZON_URL_PATTERN.findall(input_text)
    if not matches:
        return []
    
    results: List[Tuple[str, str]] = []
    seen_asins = set()
    
    for original_url in matches:
        target_url = original_url
        
        # Check if short link resolution is needed
        if any(pattern.search(original_url) for pattern in SHORT_LINK_PATTERNS) or "amzn." in original_url:
            target_url = await resolve_short_url(original_url)
            
        asin = extract_asin(target_url) or extract_asin(original_url)
        if not asin or asin in seen_asins:
            continue
            
        seen_asins.add(asin)
        
        # Smart domain detection: preserve the original link's region domain if valid
        domain = extract_domain(target_url, default_domain=default_domain)
        affiliate_url = f"https://www.{domain}/dp/{asin}?tag={affiliate_tag}"
        
        results.append((original_url, affiliate_url))
        
    return results

async def convert_to_affiliate_link(input_text: str, affiliate_tag: str, domain: str = "amazon.com") -> Optional[Tuple[str, str]]:
    """Legacy helper for single link extraction."""
    links = await convert_all_amazon_links(input_text, affiliate_tag, default_domain=domain)
    return links[0] if links else None
