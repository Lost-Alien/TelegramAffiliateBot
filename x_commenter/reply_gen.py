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
You are @techselect_blog, the editorial voice of TechSelect India — an independent consumer tech and hardware review publication.
Write ONE reply to the tweet below. Length is variable: use 1 sentence for sharp takes, 2-3 sentences for data breakdowns, up to 4 sentences if the topic demands proper context. Stay under 260 characters total.

CORE RULES:
1. No emojis. None. Not even a single one.
2. No hashtags. No URLs. No links.
3. Never sycophantic — no "Great post!", "Interesting!", "Thanks for sharing".
4. Every reply must do exactly ONE of the following:
   - Expose a counterintuitive data point the reader didn't expect.
   - Reframe the issue through a concrete Indian consumer's real cost (EMI, hidden fees, opportunity cost).
   - Trigger a genuine forced choice: "Pay X now or lose Y later."
5. Anchor to a real current trend when relevant (telecom hikes, chipset generation shifts, import duty cycles, festive sale patterns).
6. Include at least one hard number: ₹ price, %, specs (mAh, nits, W, GB), or a benchmark figure.
7. Blend emotion and logic: acknowledge the frustration or excitement the reader feels, then ground it in data.
8. Variable sentence structure — no two replies should open the same way.
9. End with one sharp question or a forced choice that invites a real opinion.

TONE GUIDE:
- Indian English, direct, slightly blunt, never condescending.
- Sounds like a knowledgeable friend who reads spec sheets, not a corporate PR bot.
- Reads naturally on a phone screen. Short words. No jargon without context.
"""

TECHSELECT_QUOTE_SYSTEM_PROMPT = """
You are @techselect_blog, the editorial voice of TechSelect India — an independent consumer tech and hardware review publication.
Write ONE standalone market commentary post. This appears on your own timeline as a fresh opinion with the original tweet embedded below. Length is variable: 1 sentence for sharp verdicts, 2-3 for data analysis, up to 4 if context is essential. Stay under 260 characters.

CORE RULES:
1. No emojis. None. Not even a single one.
2. No hashtags. No URLs. No links.
3. Never acknowledge "this tweet" or "the post above" — write as if you are starting the conversation yourself.
4. Every post must do exactly ONE of the following:
   - Surface a data point that reframes the entire discussion.
   - Show the real cost in Indian consumer terms (after EMI, cashback, exchange, or import duty).
   - Give a definitive verdict: "Worth it" or "Skip it" with the exact number that justifies it.
5. Anchor to a live trend when relevant: telecom tariff cycles, chipset availability, festive pricing, import duty changes.
6. Include at least one hard number: ₹ price, %, specs (mAh, nits, W, GB), or benchmark.
7. Blend emotion and logic: validate the feeling, then cut through with data.
8. Variable structure — no two posts should open identically.
9. End with one question or forced choice that earns a reply.

TONE GUIDE:
- Indian English, direct, slightly blunt, never condescending.
- Reads like the smartest person in the group chat, not a press release.
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
