"""Channel discovery module using Telethon client.get_dialogs() with in-memory caching."""

import time
from typing import Any
from telethon import TelegramClient

import config
from config import logger

_CACHE: list[dict[str, Any]] = []
_CACHE_TS: float = 0.0
CACHE_TTL: float = 120.0  # 120 seconds TTL


def _is_target_channel(dialog_id: int, username: str | None) -> bool:
    """Check if a dialog matches any configured target channel."""
    target_set = {str(t).strip().lower() for t in config.TARGET_CHANNELS if str(t).strip()}
    if str(dialog_id) in target_set:
        return True
    if username:
        user_lower = username.lower()
        if user_lower in target_set or f"@{user_lower}" in target_set:
            return True
    return False


async def list_channels(client: TelegramClient, force_refresh: bool = False) -> list[dict[str, Any]]:
    """
    List all joined channels and groups, excluding private DMs and target channels.
    Results are cached in-memory for CACHE_TTL seconds unless force_refresh is True.
    """
    global _CACHE, _CACHE_TS

    now = time.time()
    if not force_refresh and (now - _CACHE_TS < CACHE_TTL) and _CACHE:
        return _CACHE

    logger.info("Scanning joined dialogs for channel discovery...")
    result: list[dict[str, Any]] = []
    try:
        dialogs = await client.get_dialogs()
        for d in dialogs:
            if not (d.is_channel or d.is_group):
                continue

            username = getattr(d.entity, "username", None) or ""
            if _is_target_channel(d.id, username):
                continue

            chat_type = "channel" if getattr(d.entity, "broadcast", False) else "group"
            participants = getattr(d.entity, "participants_count", 0) or 0

            result.append({
                "id": d.id,
                "title": d.title or str(d.id),
                "username": username,
                "type": chat_type,
                "participants_count": participants,
            })

        _CACHE = result
        _CACHE_TS = now
        logger.info("Discovered %d source channels/groups.", len(_CACHE))
    except Exception as e:
        logger.error("Error scanning dialogs for list_channels: %s", e)
        # Return existing cache on failure if available
        if _CACHE:
            return _CACHE
        raise

    return _CACHE


async def refresh(client: TelegramClient) -> list[dict[str, Any]]:
    """Force re-scan of dialogs and update cache."""
    return await list_channels(client, force_refresh=True)
