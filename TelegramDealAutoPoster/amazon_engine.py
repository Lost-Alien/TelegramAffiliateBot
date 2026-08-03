import re
import itertools
from typing import Tuple, Set, Optional, List
import httpx
import config

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
}

# Round-robin generator for rotating affiliate tags
_tag_cycler = itertools.cycle(config.AFFILIATE_TAGS)

def get_next_affiliate_tag(override_tags: Optional[List[str]] = None) -> str:
    """Return the next affiliate tag from rotation list."""
    tags = override_tags if override_tags else config.AFFILIATE_TAGS
    if not tags:
        return "onamztechst01-21"
    return next(itertools.cycle(tags))

def extract_asin(url: str) -> Optional[str]:
    """Extract 10-character Amazon Standard Identification Number (ASIN) from URL."""
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
    """Follow HTTP redirects for short Amazon URLs (amzn.to/xxx) to get full target URL."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=6.0, headers=HEADERS) as client:
            response = await client.head(url)
            if response.status_code in (405, 403):
                response = await client.get(url)
            return str(response.url)
    except Exception:
        return url

async def process_deal_text(text: str, affiliate_tags: Optional[List[str]] = None, default_domain: str = config.DEFAULT_AMAZON_DOMAIN) -> Tuple[bool, str, Set[str]]:
    """
    Scans text/caption for Amazon links, resolves short links, converts to affiliate links,
    and replaces them in-place within the text using tag rotation.
    
    Returns (has_amazon_links, updated_text, set_of_extracted_asins)
    """
    if not text:
        return False, text, set()
        
    urls = ANY_AMAZON_URL_PATTERN.findall(text)
    if not urls:
        return False, text, set()
        
    extracted_asins: Set[str] = set()
    updated_text = text
    tags_list = affiliate_tags if affiliate_tags else config.AFFILIATE_TAGS
    
    for orig_url in urls:
        target_url = orig_url
        if any(pattern.search(orig_url) for pattern in SHORT_LINK_PATTERNS) or "amzn." in orig_url:
            target_url = await resolve_short_url(orig_url)
            
        asin = extract_asin(target_url) or extract_asin(orig_url)
        if not asin:
            continue
            
        extracted_asins.add(asin)
        domain = extract_domain(target_url, default_domain=default_domain)
        tag = next(_tag_cycler) if tags_list else "onamztechst01-21"
        
        affiliate_url = f"https://www.{domain}/dp/{asin}?tag={tag}"
        
        # Replace original link with clean affiliate link
        updated_text = updated_text.replace(orig_url, affiliate_url)
        
    has_links = len(extracted_asins) > 0
    return has_links, updated_text, extracted_asins
