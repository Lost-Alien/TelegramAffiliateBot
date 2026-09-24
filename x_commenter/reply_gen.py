"""
reply_gen.py — Synthesizes authoritative TechSelect India replies and quote-repost
commentary using Exa AI structured search, with Indian tech hardware review persona.

Exa usage pattern (correct):
  exa.search(query, system_prompt=..., output_schema=..., contents={"highlights": True})
  → res.output.content  (dict matching output_schema)

The query is crafted to pull FACTUAL DATA about the topic from authoritative tech
sources (91mobiles, GSMArena, The Verge, AnandTech, etc.) — NOT from Twitter.
This gives Exa's synthesis layer real specs, prices, and benchmarks to ground the
reply in, producing hard-number-rich replies instead of generic takes.
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


# Authoritative Indian + global tech sources Exa searches for grounding facts.
# Intentionally excludes twitter.com/x.com — we want spec sheets, price data,
# and benchmarks, not more social posts.
EXA_TECH_FACT_DOMAINS = [
    "91mobiles.com",
    "gadgets360.com",
    "gsmarena.com",
    "ndtvgadgets.com",
    "anandtech.com",
    "theverge.com",
    "androidauthority.com",
    "notebookcheck.net",
    "techradar.com",
    "bgr.in",
    "digit.in",
]


TECHSELECT_SYSTEM_PROMPT = """\
You are @techselect_blog, the editorial voice of TechSelect India — an independent consumer tech and hardware review publication.
Write ONE reply to the tweet below. Length is variable: use 1 sentence for sharp takes, 2-3 sentences for data breakdowns, up to 4 sentences if the topic demands proper context. Stay under 260 characters total.

CORE RULES:
1. No emojis. None. Not even a single one.
2. No hashtags. ABSOLUTELY NO URLs. No links. No product links. No Amazon links. No affiliate links. No shortened links. No "check link in bio". Nothing.
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

TECHSELECT_QUOTE_SYSTEM_PROMPT = """\
You are @techselect_blog, the editorial voice of TechSelect India — an independent consumer tech and hardware review publication.
Write ONE standalone market commentary post. This appears on your own timeline as a fresh opinion with the original tweet embedded below. Length is variable: 1 sentence for sharp verdicts, 2-3 for data analysis, up to 4 if context is essential. Stay under 260 characters.

CORE RULES:
1. No emojis. None. Not even a single one.
2. No hashtags. ABSOLUTELY NO URLs. No links. No product links. No Amazon links. No affiliate links. No shortened links. Nothing.
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
# the next synthesis call upgrades to type="deep" for richer context.
# Defaults to 5 (neutral) so the first call always uses type="auto".
_last_virality_score: int = 5

# Simplified output schema — stays well within Exa's 10-property / 2-nesting limit.
_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["reply", "contains_number", "virality_score"],
    "properties": {
        "reply": {
            "type": "string",
            "description": (
                "Short Twitter reply under 260 chars. Must be grounded in a real Indian "
                "Rupee price or a technical spec (mAh, nits, W, GB, GHz, benchmark score). "
                "No URLs, no hashtags, no emojis."
            ),
        },
        "contains_number": {
            "type": "boolean",
            "description": "True if the reply contains an Indian Rupee price (Rs/₹) or a numeric spec.",
        },
        "virality_score": {
            "type": "integer",
            "description": (
                "Score 1-10: how likely this reply is to earn genuine engagement. "
                "10 = shocking price data, forced choice, or spec comparison. "
                "1 = generic commentary with no debate potential."
            ),
        },
    },
}


def _build_fact_query(topic: str, tweet_text: str) -> str:
    """
    Build an Exa query that searches for factual data ABOUT the topic
    from authoritative tech sources — specs, prices, benchmarks, comparisons.
    This is intentionally separate from the tweet text itself: we want
    Exa to retrieve real-world grounding data, not social commentary.
    """
    # Extract the most informative 120 chars of the tweet for topic context
    tweet_snippet = tweet_text[:120].strip()
    if topic:
        return (
            f"{topic} India specs price benchmark review 2024 "
            f"| {tweet_snippet}"
        )
    return (
        f"India consumer tech specs price benchmark comparison 2024 "
        f"| {tweet_snippet}"
    )


def _synthesize_techselect_text(
    system_prompt: str,
    query_label: str,
    tweet_text: str,
    topic: str = "",
    author: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Exa-powered synthesis for both reply and quote-repost generation.

    Exa searches authoritative tech news/review sites (NOT Twitter) for
    factual grounding data — specs, prices, benchmarks — then synthesises
    a reply using the system_prompt persona and the structured output_schema.

    Credit-efficiency:
      - Last call's virality_score gates search_type: >=7 -> "deep", else "auto"
      - First call always uses "auto" (default score = 5)
    """
    global _last_virality_score
    exa = get_exa_client()

    search_type = "deep" if _last_virality_score >= 7 else "auto"
    logger.info(
        f"Exa virality score from last call: {_last_virality_score}/10 "
        f"-> using type='{search_type}' for {query_label}"
    )

    # Query targets factual tech data sources, NOT Twitter
    query = _build_fact_query(topic, tweet_text)

    try:
        logger.info(f"Exa synthesis ({query_label}) query: {query[:80]}...")
        res = exa.search(
            query=query,
            type=search_type,
            num_results=5,
            include_domains=EXA_TECH_FACT_DOMAINS,
            system_prompt=system_prompt,
            output_schema=_OUTPUT_SCHEMA,
            contents={"highlights": True},
        )

        # Log how many evidence highlights Exa used for grounding
        all_highlights: list[str] = []
        for item in getattr(res, "results", []):
            hl = getattr(item, "highlights", [])
            if hl:
                all_highlights.extend(hl)
        if all_highlights:
            logger.debug(
                f"Exa returned {len(all_highlights)} highlight(s) as synthesis context."
            )
        else:
            logger.warning(
                "Exa returned 0 highlights — reply may lack grounding data."
            )

        output = getattr(res, "output", None)
        if not output or not getattr(output, "content", None):
            logger.warning(f"Exa returned no structured output for {query_label}.")
            return None

        content = output.content
        reply_text = content.get("reply", "").strip()

        if not reply_text:
            logger.warning("Exa output.content had empty 'reply' field.")
            return None

        # ── Safety Guardrails ─────────────────────────────────────────────

        # 1. Strip em dashes → comma
        reply_text = reply_text.replace("\u2014", ",").replace("\u2013", ",")

        # 2. Unwrap surrounding quotes
        if reply_text.startswith('"') and reply_text.endswith('"'):
            reply_text = reply_text[1:-1].strip()

        # 3. Trim to last complete sentence if over char limit
        if len(reply_text) > MAX_CHAR_LIMIT:
            logger.warning(
                f"Generated text exceeds limit ({len(reply_text)} > {MAX_CHAR_LIMIT}). Trimming."
            )
            sentences = re.split(r'(?<=[.!?])\s+', reply_text)
            trimmed = ""
            for s in sentences:
                candidate = (trimmed + " " + s).strip()
                if len(candidate) <= MAX_CHAR_LIMIT:
                    trimmed = candidate
            reply_text = trimmed or reply_text[:MAX_CHAR_LIMIT]

        # 4. Strip any URL that slipped through (http, www, amzn, t.co, etc.)
        url_pattern = re.compile(
            r'https?://\S+'
            r'|www\.\S+'
            r'|amzn\.\S+'
            r'|amazon\.\S+/dp/\S+'
            r'|flipkart\.com/\S+'
            r'|bit\.ly/\S+'
            r'|t\.co/\S+'
            r'|goo\.gl/\S+'
            r'|rb\.gy/\S+'
            r'|linktr\.ee/\S+',
            re.IGNORECASE,
        )
        if url_pattern.search(reply_text):
            reply_text = url_pattern.sub("", reply_text).strip()
            reply_text = re.sub(r" {2,}", " ", reply_text).strip()
            logger.warning("Stripped URL from generated reply text.")

        # 5. Hard reject if any raw link survives
        if "http://" in reply_text or "https://" in reply_text:
            logger.warning("Reply still contained a raw link after strip — rejecting.")
            return None

        # 6. Verify number presence (Rs, ₹, or any digit)
        has_digit = (
            bool(re.search(r"\d+", reply_text))
            or "₹" in reply_text
            or "Rs" in reply_text
        )

        # Update content with cleaned values
        content["reply"] = reply_text
        content["contains_number"] = has_digit

        # 7. Cache virality score for next call routing
        _last_virality_score = max(1, min(10, int(content.get("virality_score", 5))))
        logger.info(
            f"Exa synthesis done: virality={_last_virality_score}/10, "
            f"has_number={has_digit}, len={len(reply_text)}"
        )
        logger.info(f"Generated text:\n'{reply_text}'")

        return content

    except Exception as exc:
        logger.error(f"Exa {query_label} synthesis failed: {exc}", exc_info=True)

    return None


def generate_techselect_reply(
    tweet_text: str, topic: str = "", author: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Generate an authoritative reply grounded in real tech facts via Exa AI.
    Returns dict with 'reply', 'contains_number', 'virality_score'.
    """
    return _synthesize_techselect_text(
        TECHSELECT_SYSTEM_PROMPT, "reply to tweet", tweet_text, topic, author
    )


def generate_quote_commentary(
    tweet_text: str, topic: str = "", author: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Generate standalone quote-tweet commentary grounded in real tech facts via Exa AI.
    Returns dict with 'reply', 'contains_number', 'virality_score'.
    """
    return _synthesize_techselect_text(
        TECHSELECT_QUOTE_SYSTEM_PROMPT,
        "quote-repost commentary",
        tweet_text,
        topic,
        author,
    )
