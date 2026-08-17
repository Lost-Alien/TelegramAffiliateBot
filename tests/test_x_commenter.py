"""
test_x_commenter.py — Comprehensive Test Suite for TechSelect X Auto-Commenter
Covers Twikit cookie auth, rate limits (10 replies/hr), state deduplication, Exa scanning, guardrails, and poster mocking.
"""

import pytest
import time
import re
from unittest.mock import patch, MagicMock, AsyncMock

import x_commenter.config_x as config_x
from x_commenter.scanner import extract_tweet_id, scan_candidate_tweets
from x_commenter.state import (
    already_replied,
    mark_replied,
    get_daily_count,
    increment_daily_count,
)
from x_commenter.reply_gen import (
    generate_techselect_reply,
    TECHSELECT_SYSTEM_PROMPT,
)
from x_commenter.poster import post_reply, async_post_reply


# ==========================================
# 1. Config Validation (Hourly 10 Replies Pacing)
# ==========================================
def test_config_keys_and_limits():
    """Test 1: Verify scaled daily limits (50 replies/day), run limits, search topics, and prompt rules."""
    assert config_x.MAX_REPLIES_PER_RUN == 4
    assert config_x.MAX_REPLIES_PER_DAY == 50
    assert config_x.MIN_DELAY_BETWEEN_REPLIES_SEC == 30
    assert config_x.MAX_QUOTE_REPOSTS_PER_DAY == 20
    assert config_x.MAX_CHAR_LIMIT == 260
    assert config_x.ALWAYS_POST_STANDALONE is True
    assert len(config_x.EXA_SEARCH_TOPICS) > 0
    assert len(config_x.TARGET_TECH_ACCOUNTS) > 0
    assert isinstance(config_x.EXA_API_KEY, str) and len(config_x.EXA_API_KEY) > 0




# ==========================================
# 2. Tweet ID Extraction (Valid URLs)
# ==========================================
def test_tweet_id_extraction_valid():
    """Test 2: Verify extraction of tweet IDs from x.com and twitter.com URLs."""
    url_x = "https://x.com/geekyranjit/status/1889922883377281923"
    url_twitter = "https://twitter.com/beebomco/status/1992837462819203948?s=20"
    url_params = "https://x.com/SamsungIndia/status/1234567890123456789?ref_src=twsrc%5Etfw"

    assert extract_tweet_id(url_x) == "1889922883377281923"
    assert extract_tweet_id(url_twitter) == "1992837462819203948"
    assert extract_tweet_id(url_params) == "1234567890123456789"


# ==========================================
# 3. Tweet ID Extraction (Invalid Inputs)
# ==========================================
def test_tweet_id_extraction_invalid():
    """Test 3: Verify graceful handling of non-tweet URLs, malformed strings, and None."""
    assert extract_tweet_id("https://x.com/home") is None
    assert extract_tweet_id("https://techselect.blog/article/samsung-s25") is None
    assert extract_tweet_id("") is None
    assert extract_tweet_id(None) is None


# ==========================================
# 4. State Deduplication (Mark & Check)
# ==========================================
def test_state_dedup_mark_and_check():
    """Test 4: Verify that a marked tweet ID is recognized as already replied."""
    dummy_id = f"test_tweet_{int(time.time())}_{pytest.__version__}"
    assert not already_replied(dummy_id)

    mark_replied(dummy_id, "Test reply text")
    assert already_replied(dummy_id)


# ==========================================
# 5. Daily Counter Increment
# ==========================================
def test_state_daily_counter_increment():
    """Test 5: Verify that the daily counter increases and returns integer counts."""
    initial = get_daily_count()
    new_count = increment_daily_count()
    assert new_count >= initial + 1
    assert get_daily_count() == new_count


# ==========================================
# 6. Safety Guardrail: Character Limit & Trimming
# ==========================================
def test_reply_guardrail_character_limit():
    """Test 6: Verify oversized replies are automatically trimmed to <= 260 chars."""
    oversized_text = (
        "The ROG Strix G16 sustains 140W at 84°C with liquid metal cooling. "
        "At ₹94,990 street price with ICICI bank card discount, it outperforms the Acer Predator Neo 16 in sustained 30-min Cinebench loops. "
        "Would you prioritize thermal headroom or portability for college coding?"
    )
    assert len(oversized_text) > config_x.MAX_CHAR_LIMIT

    with patch("x_commenter.reply_gen.get_exa_client") as mock_get_exa:
        mock_exa = MagicMock()
        mock_output = MagicMock()
        mock_output.content = {
            "reply": oversized_text,
            "contains_number": True,
        }
        mock_res = MagicMock()
        mock_res.output = mock_output
        mock_exa.search.return_value = mock_res
        mock_get_exa.return_value = mock_exa

        res = generate_techselect_reply("Test laptop query")
        assert res is not None
        assert len(res["reply"]) <= config_x.MAX_CHAR_LIMIT
        assert "₹" in res["reply"] or "Rs" in res["reply"] or bool(re.search(r'\d+', res["reply"]))


# ==========================================
# 7. Safety Guardrail: Raw URL Blocking
# ==========================================
def test_reply_guardrail_url_blocking():
    """Test 7: Verify that generated text with raw links is rejected for compliance."""
    with patch("x_commenter.reply_gen.get_exa_client") as mock_get_exa:
        mock_exa = MagicMock()
        mock_output = MagicMock()
        mock_output.content = {
            "reply": "Check out this deal at https://amzn.to/example for ₹49,999! Buy now?",
            "contains_number": True,
        }
        mock_res = MagicMock()
        mock_res.output = mock_output
        mock_exa.search.return_value = mock_res
        mock_get_exa.return_value = mock_exa

        res = generate_techselect_reply("Test tweet about laptop deal")
        assert res is None, "Replies containing raw URLs must be rejected."


# ==========================================
# 8. Safety Guardrail: Concrete Number Enforcement
# ==========================================
def test_reply_guardrail_number_validation():
    """Test 8: Verify that replies without data numbers are correctly flagged."""
    with patch("x_commenter.reply_gen.get_exa_client") as mock_get_exa:
        mock_exa = MagicMock()
        mock_output = MagicMock()
        mock_output.content = {
            "reply": "Both laptops have great displays and powerful performance. Which brand do you prefer?",
            "contains_number": False,
        }
        mock_res = MagicMock()
        mock_res.output = mock_output
        mock_exa.search.return_value = mock_res
        mock_get_exa.return_value = mock_exa

        res = generate_techselect_reply("Which laptop is better?")
        assert res is not None
        assert res["contains_number"] is False


# ==========================================
# 9. Poster Dry-Run Mode Simulation
# ==========================================
def test_poster_dry_run_mode():
    """Test 9: Verify poster simulates output safely in DRY_RUN mode without calling X API."""
    with patch("x_commenter.poster.DRY_RUN", True):
        result = post_reply(
            reply_text="Galaxy S25 at ₹74k effective price beats Pixel 9. Which one?",
            in_reply_to_tweet_id="1234567890",
        )
        assert result is True

    # Empty text should fail safely
    assert post_reply("", in_reply_to_tweet_id="12345") is False


# ==========================================
# 10. Scanner Filtering for Already-Replied Tweets
# ==========================================
def test_scanner_filtering_already_replied():
    """Test 10: Verify scanner skips tweets that have already been replied to."""
    already_seen_id = "998877665544332211"
    mark_replied(already_seen_id, "Prior reply")

    with patch("x_commenter.scanner.get_exa_client") as mock_get_exa:
        mock_exa = MagicMock()
        item1 = MagicMock()
        item1.url = f"https://x.com/beebomco/status/{already_seen_id}"
        item1.title = "Old Tweet"
        item1.highlights = ["Specs"]

        item2 = MagicMock()
        item2.url = "https://x.com/geekyranjit/status/112233445566778899"
        item2.title = "Fresh Tweet"
        item2.highlights = ["New Launch"]

        mock_res = MagicMock()
        mock_res.results = [item1, item2]
        mock_exa.search.return_value = mock_res
        mock_get_exa.return_value = mock_exa

        candidates = scan_candidate_tweets(limit=2)
        candidate_ids = [c["id"] for c in candidates]

        assert already_seen_id not in candidate_ids
        assert "112233445566778899" in candidate_ids


# ==========================================
# 11. Poster Missing Cookies Fallback
# ==========================================
def test_poster_missing_cookies_handled_gracefully():
    """Test 11: Verify poster fails gracefully when no cookies are available and DRY_RUN is False."""
    with patch("x_commenter.poster.DRY_RUN", False), \
         patch("x_commenter.poster.get_cookie_credentials", return_value=None):
        success = post_reply("Testing missing cookies", in_reply_to_tweet_id="123456789")
        assert success is False


# ==========================================
# 12. Direct auth_token and ct0 Credential Extraction
# ==========================================
def test_poster_direct_auth_token_and_ct0_extraction():
    """Test 12: Verify get_cookie_credentials extracts credentials from TWITTER_AUTH_TOKEN and TWITTER_CT0."""
    from x_commenter.poster import get_cookie_credentials
    with patch("x_commenter.poster.TWITTER_AUTH_TOKEN", "test_auth_token_123"), \
         patch("x_commenter.poster.TWITTER_CT0", "test_ct0_456"):
        creds = get_cookie_credentials()
        assert creds == ("test_auth_token_123", "test_ct0_456")


# ==========================================
# 13. Poster Success with GraphQL Mock
# ==========================================
def test_poster_graphql_success_mock():
    """Test 13: Verify post_reply successfully parses GraphQL CreateTweet response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "create_tweet": {
                "tweet_results": {
                    "result": {
                        "rest_id": "1928374650192837465"
                    }
                }
            }
        }
    }

    with patch("x_commenter.poster.DRY_RUN", False), \
         patch("x_commenter.poster.get_cookie_credentials", return_value=("dummy_auth", "dummy_ct0")), \
         patch("curl_cffi.requests.post", return_value=mock_resp) as mock_post:
        success = post_reply(
            reply_text="OnePlus 13 vs iQOO 13 at ₹54,999: 6000mAh battery makes the difference.",
            in_reply_to_tweet_id="188273645192837465",
        )
        assert success is True
        assert mock_post.called


