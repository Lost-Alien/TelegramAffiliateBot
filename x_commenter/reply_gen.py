"""
reply_gen.py — Synthesizes authoritative TechSelect India replies using Exa AI
with structured output schema and Indian tech hardware review persona.
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
Your goal is to write SHORT (2-3 sentences max), DIRECT, and DATA-BACKED replies on Twitter/X under Indian tech discussions.

RULES:
1. Always include at least ONE concrete Indian market number: ₹ price, mAh, nits, °C, wattage, or benchmark score.
2. If discussing pricing, mention the effective street price after bank card discounts / exchange offers where applicable.
3. Tone: Direct, honest, authoritative Indian English. Never sycophantic. No "Great post!", "Awesome!", "Thanks for sharing".
4. End with EXACTLY ONE engaging question, forced choice, or unexpected hardware insight.
5. NO hashtags, NO URLs/links, NO spam, max ONE emoji.
6. Must strictly fit within 260 characters.
"""


def generate_techselect_reply(tweet_text: str, topic: str = "", author: str = "") -> Optional[Dict[str, Any]]:
    """
    Generate an authoritative reply using Exa AI structured synthesis.
    Returns a dict with 'reply' and 'contains_number'.
    """
    exa = get_exa_client()
    query = f"TechSelect India hardware review expert reply to tweet on {topic or 'tech hardware'}: \"{tweet_text[:250]}\""

    try:
        logger.info(f"Synthesizing reply via Exa for: {tweet_text[:60]}...")
        res = exa.search(
            query=query,
            type="deep",
            system_prompt=TECHSELECT_SYSTEM_PROMPT,
            output_schema={
                "type": "object",
                "required": ["reply", "contains_number"],
                "properties": {
                    "reply": {
                        "type": "string",
                        "description": "Short Twitter reply under 250 chars with Indian pricing or hardware spec"
                    },
                    "contains_number": {
                        "type": "boolean",
                        "description": "True if the reply contains an Indian Rupee price or technical spec number"
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
                logger.warning(f"Generated reply exceeds character limit ({len(reply_text)} > {MAX_CHAR_LIMIT}). Trimming...")
                # Trim cleanly to last sentence
                sentences = re.split(r'(?<=[.!?])\s+', reply_text)
                trimmed = ""
                for s in sentences:
                    if len((trimmed + " " + s).strip()) <= MAX_CHAR_LIMIT:
                        trimmed = (trimmed + " " + s).strip()
                reply_text = trimmed or reply_text[:MAX_CHAR_LIMIT]

            # 3. Check for URLs or banned spam phrases
            if "http://" in reply_text or "https://" in reply_text:
                logger.warning("Reply contained raw link — rejecting for compliance safety.")
                return None

            # 4. Check for numbers (₹ or digits)
            has_digit = bool(re.search(r'\d+', reply_text)) or "₹" in reply_text or "Rs" in reply_text
            content["reply"] = reply_text
            content["contains_number"] = has_digit

            return content
    except Exception as exc:
        logger.error(f"Exa reply synthesis failed: {exc}")

    return None
