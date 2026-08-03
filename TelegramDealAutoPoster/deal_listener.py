"""Deal listener: watches source channels, converts Amazon links, posts to targets."""

import asyncio
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, PeerFloodError

import config
from config import logger
from amazon_engine import process_deal_text
from utils import (
    DEDUP_DB,
    dedup_has,
    dedup_load,
    dedup_record,
    dedup_prune,
    _RATE_LIMITER,
)


async def safe_send(client, target, *, text=None, parse_mode=None, media=None, caption=None):
    """Send text or media with automatic FloodWait retry."""
    attempts = 0
    while True:
        attempts += 1
        try:
            if text is not None:
                return await client.send_message(target, text=text, parse_mode=parse_mode)
            kwargs = {"file": media}
            if caption:
                kwargs["caption"] = caption
            if parse_mode:
                kwargs["parse_mode"] = parse_mode
            return await client.send_file(target, **kwargs)
        except FloodWaitError as e:
            wait_sec = int(e.seconds) + 1
            logger.warning("FloodWait(%ds) on attempt %d — sleeping …", wait_sec, attempts)
            await asyncio.sleep(wait_sec)
        except (PeerFloodError, ValueError) as e:
            logger.error("Non-retryable error on attempt %d: %s", attempts, e)
            raise
        except Exception as e:
            logger.error("Send failed (attempt %d): %s", attempts, e)
            raise


async def start_deal_listener(client: TelegramClient) -> None:
    """Register NewMessage handlers to listen to joined channels."""

    me = await client.get_me()
    my_id = me.id

    # Warm-up mode
    warmup_hours = int(getattr(config, "WARMUP_HOURS", 0))
    if warmup_hours:
        logger.info("Warm-up mode enabled — will log deals silently for %dh …", warmup_hours)

    # Load previously-seen ASINs from SQLite
    known_asins = dedup_load()
    dedup_prune()  # remove anything older than 7 days
    logger.info("Loaded %d ASINs from persistent dedup cache (7-day TTL)", len(known_asins))

    # Pre-resolve target channel IDs at startup for fast loop guards (no per-message awaits)
    target_ids = set()
    for raw in config.TARGET_CHANNELS:
        try:
            entity = await client.get_entity(raw)
            target_ids.add(entity.id)
        except Exception as e:
            logger.error("Cannot resolve target '%s': %s", raw, e)

    # Which channels to monitor (empty list = all joined chats)
    chats_to_listen = config.SOURCE_CHANNELS if config.SOURCE_CHANNELS else None

    @client.on(events.NewMessage(chats=chats_to_listen))
    async def handler(event: events.NewMessage.Event):
        # ── Loop protection ──────────────────────────────────────────
        if event.out:
            return  # skip messages we sent ourselves

        if event.sender_id:
            try:
                sender = await client.get_input_entity(event.sender_id)
                if hasattr(sender, "user_id") and sender.user_id == my_id:
                    return  # skip messages originating from our own account
            except Exception:
                pass

        # Skip messages from our own target channels
        if target_ids and event.chat_id in target_ids:
            return

        # ── Extract & convert ────────────────────────────────────────
        text = event.message.message or ""
        if not text:
            return

        # Warm-up: detect deals but never post
        if warmup_hours > 0:
            _, _, asins = await process_deal_text(
                text=text, default_domain=config.DEFAULT_AMAZON_DOMAIN
            )
            if asins:
                logger.info("[WARMUP] Deal detected (skipping post): %s ASINs=%s", event.chat_id, asins)
            return

        has_amazon, updated_text, asins = await process_deal_text(
            text=text, default_domain=config.DEFAULT_AMAZON_DOMAIN
        )
        if not has_amazon:
            return

        # Record ASINs in persistent store
        for a in asins:
            dedup_record(a)

        logger.info("Deal extracted from %s — ASINs=%s", event.chat_id, asins)

        # Enforce conservative posting cadence
        await _RATE_LIMITER.acquire()

        # ── Post to targets ──────────────────────────────────────────
        if not config.TARGET_CHANNELS:
            logger.warning("No TARGET_CHANNELS configured — printing to log:")
            logger.info(updated_text)
            return

        errors: list[str] = []
        for target_raw in config.TARGET_CHANNELS:
            try:
                target = await client.get_entity(target_raw)
                if event.message.media:
                    await safe_send(
                        client,
                        target,
                        media=event.message.media,
                        caption=updated_text,
                        parse_mode="HTML",
                    )
                else:
                    await safe_send(
                        client,
                        target,
                        text=updated_text,
                        parse_mode="HTML",
                    )
                logger.info("Posted to %s ✓", target_raw)
            except Exception as e:
                errors.append(f"{target_raw}: {e}")
                logger.error("Failed to post to '%s': %s", target_raw, e)

        # Alert on failures (to configured alert chat or first target fallback)
        if errors:
            alert_msg = "\u26a0\ufe0f Deal Poster Errors\n" + "\n".join(errors)
            alert_target_raw = getattr(config, "ALERT_CHAT_ID", "") or (
                config.TARGET_CHANNELS[0] if config.TARGET_CHANNELS else None
            )
            if alert_target_raw:
                try:
                    t = await client.get_entity(alert_target_raw)
                    await safe_send(client, t, text=alert_msg, parse_mode="HTML")
                except Exception:
                    pass  # alerts failing is meta-failing; already logged above

        logger.info("Done with message from %s", event.chat_id)

    logger.info("Deal Listener active — listening for incoming posts …")
