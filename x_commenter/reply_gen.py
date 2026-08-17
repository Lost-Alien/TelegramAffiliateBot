"""
reply_gen.py — Synthesizes authoritative TechSelect India replies and quote-repost
commentary using Exa AI, with structured output schema and Indian tech hardware
review persona.
"""

import logging
import re
from typing import Optional, Dict, Any
from exa_py import Exa
from x_commenter.config_x import EXA_API_KEY, MAX_CHAR_LIMIT

logger = logging.getLogger("x_commenter.reply_gen")

_exa_client: Optional[Exa] = None


def get_exa_client() -> Exa:
    global _exa_client
    if _exa_client is None:
        _exa_client = Exa(api_key=EXA_API_KEY)
    return _exa_client


TECHSELECT_SYSTEM_PROMPT = """
You are @techselect_blog, the editorial team at TechSelect India — an independent consumer tech & hardware review site.
Write ONE short (2-3 sentences, under 260 chars), direct, data-backed reply for the given tweet.

RULES:
1. Include at least one concrete number: ₹ price, mAh, nits, °C, wattage, or benchmark score.
2. For pricing, cite the effective street price after bank/card discounts or exchange offers where relevant.
3. Tone: direct, honest, authoritative Indian English. Never sycophantic — no "Great post!", "Awesome!", "Thanks for sharing".
4. Vary your opening line and structure each time — never reuse the same sentence pattern across replies.
5. End with exactly ONE engaging question, forced choice, or unexpected hardware insight.
6. No hashtags, no URLs/links, no spam, max one emoji.
"""

TECHSELECT_QUOTE_SYSTEM_PROMPT = """
You are @techselect_blog, the editorial team at TechSelect India — an independent consumer tech & hardware review site.
Write ONE short (2-3 sentences, under 260 chars) standalone quote-repost commentary reacting to the tweet below.
This becomes its OWN post on your timeline with the original tweet embedded beneath it — it must read as a fresh,
standalone hot take or analysis, not as a nested reply acknowledging "this tweet".

RULES:
1. Include at least one concrete number: ₹ price, mAh, nits, °C, wattage, or benchmark score.
2. For pricing, cite the effective street price after bank/card discounts or exchange offers where relevant.
3. Tone: direct, honest, authoritative Indian English. Never sycophantic — no "Great post!", "Awesome!", "Thanks for sharing".
4. Vary your opening line and structure each time — never reuse the same sentence pattern across posts.
5. End with exactly ONE engaging question, forced choice, or unexpected hardware insight.
6. No hashtags, no URLs/links, no spam, max one emoji.
"""


def _synthesize_techselect_text(
    system_prompt: str,
    query_label: str,
    tweet_text: str,
    topic: str = "",
    author: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Shared Exa synthesis + safety guardrails used by both reply and
    quote-repost generation. Returns a dict with 'reply' and 'contains_number'.
    """
    exa = get_exa_client()
    query = f"TechSelect India hardware review expert {query_label} on {topic or 'tech hardware'}: \"{tweet_text[:250]}\""

    try:
        logger.info(f"Synthesizing {query_label} via Exa for: {tweet_text[:60]}...")
        res = exa.search(
            query=query,
            type="deep",
            system_prompt=system_prompt,
            output_schema={
                "type": "object",
                "required": ["reply", "contains_number"],
                "properties": {
                    "reply": {
                        "type": "string",
                        "description": "Short Twitter text under 250 chars with Indian pricing or hardware spec"
                    },
                    "contains_number": {
                        "type": "boolean",
                        "description": "True if the text contains an Indian Rupee price or technical spec number"
                    }
                }
            },
            contents={"highlights": True}
        )

        output = getattr(res, "output", None)
        if output and hasattr(output, "content") and output.content:
            content = output.content
            reply_text = content.get("reply", "").strip()

            # Safety Guardrails:
            # 1. Clean quotes if wrapped
            if reply_text.startswith('"') and reply_text.endswith('"'):
                reply_text = reply_text[1:-1].strip()

            # 2. Check length
            if len(reply_text) > MAX_CHAR_LIMIT:
                logger.warning(f"Generated text exceeds character limit ({len(reply_text)} > {MAX_CHAR_LIMIT}). Trimming...")
                # Trim cleanly to last sentence
                sentences = re.split(r'(?<=[.!?])\s+', reply_text)
                trimmed = ""
                for s in sentences:
                    if len((trimmed + " " + s).strip()) <= MAX_CHAR_LIMIT:
                        trimmed = (trimmed + " " + s).strip()
                reply_text = trimmed or reply_text[:MAX_CHAR_LIMIT]

            # 3. Check for URLs or banned spam phrases
            if "http://" in reply_text or "https://" in reply_text:
                logger.warning("Text contained raw link — rejecting for compliance safety.")
                return None

            # 4. Check for numbers (₹ or digits)
            has_digit = bool(re.search(r'\d+', reply_text)) or "₹" in reply_text or "Rs" in reply_text
            content["reply"] = reply_text
            content["contains_number"] = has_digit

            return content
    except Exception as exc:
        logger.error(f"Exa {query_label} synthesis failed: {exc}")

    return None


def generate_techselect_reply(tweet_text: str, topic: str = "", author: str = "") -> Optional[Dict[str, Any]]:
    """
    Generate an authoritative reply using Exa AI structured synthesis.
    Returns a dict with 'reply' and 'contains_number'.
    """
    return _synthesize_techselect_text(
        TECHSELECT_SYSTEM_PROMPT, "reply to tweet", tweet_text, topic, author
    )


def generate_quote_commentary(tweet_text: str, topic: str = "", author: str = "") -> Optional[Dict[str, Any]]:
    """
    Generate standalone "repost with own thoughts" (quote-tweet) commentary
    using Exa AI structured synthesis. Returns a dict with 'reply' and
    'contains_number' (same shape as generate_techselect_reply for pipeline
    compatibility).
    """
    return _synthesize_techselect_text(
        TECHSELECT_QUOTE_SYSTEM_PROMPT, "quote-repost commentary", tweet_text, topic, author
    )
