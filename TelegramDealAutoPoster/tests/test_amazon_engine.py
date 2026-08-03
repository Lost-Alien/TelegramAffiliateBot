import pytest
import asyncio
from amazon_engine import extract_asin, extract_domain, process_deal_text

def test_extract_asin():
    assert extract_asin("https://www.amazon.com/dp/B08N5WRWNW") == "B08N5WRWNW"
    assert extract_asin("https://www.amazon.in/gp/product/B08N5WRWNW") == "B08N5WRWNW"

def test_extract_domain():
    assert extract_domain("https://www.amazon.in/dp/B08N5WRWNW") == "amazon.in"
    assert extract_domain("https://www.amazon.co.uk/dp/B08N5WRWNW") == "amazon.co.uk"

def test_process_deal_text_replacement():
    async def _test():
        raw_post = (
            "🔥 HUGE DISCOUNT ON HEADPHONES! 🔥\n"
            "Buy now: https://www.amazon.com/dp/B08N5WRWNW?tag=oldtag-20\n"
            "Hurry up before stock ends!"
        )
        has_links, updated_text, asins = await process_deal_text(
            raw_post, affiliate_tags=["onamztechst01-21", "techstor0caaf-21"], default_domain="amazon.com"
        )
        assert has_links is True
        assert "B08N5WRWNW" in asins
        assert "tag=onamztechst01-21" in updated_text or "tag=techstor0caaf-21" in updated_text
        assert "oldtag-20" not in updated_text
    asyncio.run(_test())
