import pytest
import asyncio
from amazon_converter import extract_asin, extract_domain, convert_all_amazon_links

def test_extract_asin_dp():
    url = "https://www.amazon.com/dp/B08N5WRWNW"
    assert extract_asin(url) == "B08N5WRWNW"

def test_extract_asin_gp_product():
    url = "https://www.amazon.in/gp/product/B08N5WRWNW/ref=as_li_ss_tl"
    assert extract_asin(url) == "B08N5WRWNW"

def test_extract_asin_query_param():
    url = "https://www.amazon.com/exec/obidos/ASIN/B08N5WRWNW?asin=B08N5WRWNW"
    assert extract_asin(url) == "B08N5WRWNW"

def test_extract_domain():
    assert extract_domain("https://www.amazon.co.uk/dp/B08N5WRWNW") == "amazon.co.uk"
    assert extract_domain("https://amazon.in/gp/product/B08N5WRWNW") == "amazon.in"
    assert extract_domain("https://unknown.com", default_domain="amazon.com") == "amazon.com"

def test_convert_all_amazon_links_multi():
    async def _test():
        text = (
            "Check out product 1: https://www.amazon.com/dp/B08N5WRWNW "
            "and product 2: https://www.amazon.co.uk/dp/B07PVF65GF"
        )
        results = await convert_all_amazon_links(text, affiliate_tag="mytag-20")
        assert len(results) == 2
        assert "https://www.amazon.com/dp/B08N5WRWNW?tag=mytag-20" in results[0][1]
        assert "https://www.amazon.co.uk/dp/B07PVF65GF?tag=mytag-20" in results[1][1]
    asyncio.run(_test())

def test_convert_strips_foreign_affiliate_tag():
    async def _test():
        text = "https://www.amazon.in/dp/B08D9GTM7W?psc=1&th=1&tag=collab-dealbee-21"
        results = await convert_all_amazon_links(text, affiliate_tag="onamztechst01-21")
        assert len(results) == 1
        assert results[0][1] == "https://www.amazon.in/dp/B08D9GTM7W?tag=onamztechst01-21"
    asyncio.run(_test())

def test_get_affiliate_tag_from_config():
    import config
    assert config.get_affiliate_tag() in config.AFFILIATE_TAGS
