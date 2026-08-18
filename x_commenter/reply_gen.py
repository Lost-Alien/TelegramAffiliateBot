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
3. No em dashes (the — character). Use a comma, colon, or full stop instead.
4. Never sycophantic. No "Great post!", "Interesting!", "Thanks for sharing".
5. Every reply must do exactly ONE of the following:
   - Expose a counterintuitive data point the reader did not expect.
   - Reframe the issue through a concrete Indian consumer real cost (EMI, hidden fees, opportunity cost).
   - Trigger a genuine forced choice: "Pay X now or lose Y later."
6. Anchor to a real current trend when relevant (telecom hikes, chipset generation shifts, import duty cycles, festive sale patterns).
7. Include at least one hard number: Rs price, %, specs (mAh, nits, W, GB), or a benchmark figure.
8. Blend emotion and logic: acknowledge the frustration or excitement the reader feels, then ground it in data.
9. Variable sentence structure. No two replies should open the same way.
10. End with one sharp question or a forced choice that invites a real opinion.

TONE GUIDE:
- Indian English with simple grammar, direct, slightly blunt, never condescending.
- Sounds like a knowledgeable friend who reads spec sheets, not a corporate PR bot.
- Reads naturally on a phone screen. Short words. No jargon without context.
"""

TECHSELECT_QUOTE_SYSTEM_PROMPT = """
You are @techselect_blog, the editorial voice of TechSelect India — an independent consumer tech and hardware review publication.
Write ONE standalone market commentary post. This appears on your own timeline as a fresh opinion with the original tweet embedded below. Length is variable: 1 sentence for sharp verdicts, 2-3 for data analysis, up to 4 if context is essential. Stay under 260 characters.

CORE RULES:
1. No emojis. None. Not even a single one.
2. No hashtags. No URLs. No links.
3. No em dashes (the — character). Use a comma, colon, or full stop instead.
4. Never acknowledge "this tweet" or "the post above". Write as if you are starting the conversation yourself.
5. Every post must do exactly ONE of the following:
   - Surface a data point that reframes the entire discussion.
   - Show the real cost in Indian consumer terms (after EMI, cashback, exchange, or import duty).
   - Give a definitive verdict: "Worth it" or "Skip it" with the exact number that justifies it.
6. Anchor to a live trend when relevant: telecom tariff cycles, chipset availability, festive pricing, import duty changes.
7. Include at least one hard number: Rs price, %, specs (mAh, nits, W, GB), or benchmark.
8. Blend emotion and logic: validate the feeling, then cut through with data.
9. Variable structure. No two posts should open identically.
10. End with one question or forced choice that earns a reply.

TONE GUIDE:
- Indian English with simple grammar, direct, slightly blunt, never condescending.
- Reads like the smartest person in the group chat, not a press release.
"""

# Per-session virality score cache.
# Exa LLM scores each reply (1-10). If a prior candidate scored >= 7,
# the next call upgrades to type="deep" for richer synthesis.
# Defaults to 5 (neutral) so the first call always uses type="auto".
_last_virality_score: int = 5


def _synthesize_techselect_text(
    system_prompt: str,
    query_label: str,
    tweet_text: str,
    topic: str = "",
    author: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Shared Exa synthesis + safety guardrails used by both reply and
    quote-repost generation.

    Credit-efficiency logic (Exa LLM as the scorer, no external model needed):
    - The output_schema asks Exa to return virality_score (1-10) and sentiment
      alongside the reply, using its own LLM judgment.
    - The previous call's virality_score determines this call's search_type:
        score >= 7  (high engagement potential)  -> type="deep"
        score < 7   (standard/generic content)   -> type="auto" (cheaper)
    - First call always uses type="auto" (default score = 5).
    - Aggregates ALL result highlights as synthesis context.

    Returns a dict with 'reply', 'contains_number', 'virality_score', 'sentiment'.
    """
    global _last_virality_score
    exa = get_exa_client()

    # Route based on previous call's Exa-predicted virality
    search_type = "deep" if _last_virality_score >= 7 else "auto"
    logger.info(
        f"Exa virality score from last call: {_last_virality_score}/10 "
        f"-> using type='{search_type}' for {query_label}"
    )

    query = (
        f"TechSelect India hardware review {query_label} on "
        f"{topic or 'consumer tech'}: \"{tweet_text[:250]}\""
    )

    try:
        logger.info(f"Synthesizing {query_label} via Exa for: {tweet_text[:60]}...")
        res = exa.search(
            query=query,
            type=search_type,
            num_results=3,
            system_prompt=system_prompt,
            output_schema={
                "type": "object",
                "required": ["reply", "contains_number", "virality_score", "sentiment"],
                "properties": {
                    "reply": {
                        "type": "string",
                        "description": "Short Twitter reply under 260 chars grounded in Indian pricing or hardware spec"
                    },
                    "contains_number": {
                        "type": "boolean",
                        "description": "True if the reply contains an Indian Rupee price or a technical spec number"
                    },
                    "virality_score": {
                        "type": "integer",
                        "description": (
                            "Score from 1 to 10 predicting how likely this tweet is to generate replies and engagement. "
                            "10 = highly controversial, emotional, or contains shocking price data. "
                            "1 = generic announcement with no debate potential. "
                            "Consider: sarcasm, frustration, price shock, spec comparison, telecom controversy, "
                            "forced choice questions."
                        )
                    },
                    "sentiment": {
                        "type": "string",
                        "enum": ["frustrated", "excited", "curious", "neutral", "sarcastic", "outraged"],
                        "description": "Dominant sentiment of the original tweet being replied to"
                    }
                }
            },
            contents={"highlights": True}
        )

        # Aggregate all highlights from every returned result as extra context
        # (used implicitly by Exa's synthesis layer; also logged for debugging)
        all_highlights: list[str] = []
        for item in getattr(res, "results", []):
            hl = getattr(item, "highlights", [])
            if hl:
                all_highlights.extend(hl)
        if all_highlights:
            logger.debug(f"Exa returned {len(all_highlights)} highlight(s) as synthesis context.")

        output = getattr(res, "output", None)
        if output and hasattr(output, "content") and output.content:
            content = output.content
            reply_text = content.get("reply", "").strip()

            # Safety Guardrails:
            # 1. Strip em dashes — replace with comma for readability
            reply_text = reply_text.replace("\u2014", ",")

            # 2. Clean quotes if wrapped
            if reply_text.startswith('"') and reply_text.endswith('"'):
                reply_text = reply_text[1:-1].strip()

            # 3. Check length — trim cleanly to last complete sentence
            if len(reply_text) > MAX_CHAR_LIMIT:
                logger.warning(f"Generated text exceeds limit ({len(reply_text)} > {MAX_CHAR_LIMIT}). Trimming.")
                sentences = re.split(r'(?<=[.!?])\s+', reply_text)
                trimmed = ""
                for s in sentences:
                    if len((trimmed + " " + s).strip()) <= MAX_CHAR_LIMIT:
                        trimmed = (trimmed + " " + s).strip()
                reply_text = trimmed or reply_text[:MAX_CHAR_LIMIT]

            # 4. Reject if raw URL slipped through
            if "http://" in reply_text or "https://" in reply_text:
                logger.warning("Text contained raw link — rejecting for compliance safety.")
                return None

            # 5. Check for numbers (Rs / ₹ / digits)
            has_digit = bool(re.search(r'\d+', reply_text)) or "₹" in reply_text or "Rs" in reply_text
            content["reply"] = reply_text
            content["contains_number"] = has_digit

            # 6. Cache Exa LLM virality score for next call routing
            _last_virality_score = int(content.get("virality_score", 5))
            sentiment_label = content.get("sentiment", "neutral")
            logger.info(
                f"Exa LLM scored this candidate: virality={_last_virality_score}/10, "
                f"sentiment={sentiment_label}"
            )

            return content

    except Exception as exc:
        logger.error(f"Exa {query_label} synthesis failed: {exc}")

    return None


def generate_techselect_reply(tweet_text: str, topic: str = "", author: str = "") -> Optional[Dict[str, Any]]:
    """
    Generate an authoritative reply using Exa AI structured synthesis.
    Automatically routes to deep or auto Exa search based on sentiment score.
    Returns a dict with 'reply' and 'contains_number'.
    """
    return _synthesize_techselect_text(
        TECHSELECT_SYSTEM_PROMPT, "reply to tweet", tweet_text, topic, author
    )


def generate_quote_commentary(tweet_text: str, topic: str = "", author: str = "") -> Optional[Dict[str, Any]]:
    """
    Generate standalone quote-tweet commentary using Exa AI structured synthesis.
    Automatically routes to deep or auto Exa search based on sentiment score.
    Returns a dict with 'reply' and 'contains_number'.
    """
    return _synthesize_techselect_text(
        TECHSELECT_QUOTE_SYSTEM_PROMPT, "quote-repost commentary", tweet_text, topic, author
    )
