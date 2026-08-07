"""Deal listener: watches source channels, converts Amazon links, posts to targets."""

import asyncio
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, PeerFloodError

import config
from config import logger
from amazon_engine import process_deal_text
from utils import (
    dedup_has,
    dedup_load,
    dedup_record,
    dedup_prune,
    _RATE_LIMITER,
)
import state


async def safe_send(client, target, *, text=None, parse_mode=None, media=None, caption=None):
    """Send text or media with automatic FloodWait retry."""
    attempts = 0
    while True:
        attempts += 1
        try:
            if text is not None:
                return await client.send_message(target, message=text, parse_mode=parse_mode)
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

    warmup_hours = int(getattr(config, "WARMUP_HOURS", 0))
    if warmup_hours:
        logger.info("Warm-up mode enabled — will log deals silently for %dh …", warmup_hours)

    known_asins = dedup_load()
    dedup_prune()
    logger.info("Loaded %d ASINs from persistent dedup cache (7-day TTL)", len(known_asins))

    target_ids = set()
    for raw in config.TARGET_CHANNELS:
        try:
            entity = await client.get_entity(raw)
            target_ids.add(entity.id)
        except Exception as e:
            logger.error("Cannot resolve target '%s': %s", raw, e)

    chats_to_listen = config.SOURCE_CHANNELS if config.SOURCE_CHANNELS else None

    @client.on(events.NewMessage(chats=chats_to_listen))
    async def handler(event: events.NewMessage.Event):
        if event.out:
            return

        if event.sender_id:
            try:
                sender = await client.get_input_entity(event.sender_id)
                if hasattr(sender, "user_id") and sender.user_id == my_id:
                    return
            except Exception:
                pass

        if target_ids and event.chat_id in target_ids:
            return

        text = event.message.message or ""
        if not text:
            return

        chat = await event.get_chat()
        chat_title = getattr(chat, "title", str(event.chat_id)) if chat else str(event.chat_id)

        if warmup_hours > 0:
            _, _, asins = await process_deal_text(
                text=text, default_domain=config.DEFAULT_AMAZON_DOMAIN
            )
            if asins:
                logger.info("[WARMUP] Deal detected (skipping post): %s ASINs=%s", event.chat_id, asins)
                state.record_detected(asins, source_id=event.chat_id, source_title=chat_title)
                state.record_event("warmup", f"[WARMUP] Deal detected (skipping post): {chat_title} ASINs={asins}")
            return

        has_amazon, updated_text, asins = await process_deal_text(
            text=text, default_domain=config.DEFAULT_AMAZON_DOMAIN
        )
        if not has_amazon:
            return

        state.record_detected(asins, source_id=event.chat_id, source_title=chat_title)

        if asins and all(dedup_has(a) for a in asins):
            logger.info("Skipping duplicate deal from %s — ASINs %s already posted", event.chat_id, asins)
            state.record_skipped(asins)
            return

        logger.info("Deal extracted from %s — ASINs=%s", event.chat_id, asins)

        await _RATE_LIMITER.acquire()

        if not config.TARGET_CHANNELS:
            logger.warning("No TARGET_CHANNELS configured — printing to log:")
            logger.info(updated_text)
            return

        errors: list[str] = []
        posted_targets = 0
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
                posted_targets += 1
                state.record_posted({
                    "asins": asins,
                    "source_id": event.chat_id,
                    "source_title": chat_title,
                    "target": target_raw,
                    "has_media": bool(event.message.media),
                })
            except Exception as e:
                msg = f"{target_raw}: {e}"
                errors.append(msg)
                logger.error("Failed to post to '%s': %s", target_raw, e)
                state.record_error(msg)

        if posted_targets:
            for asin in asins:
                dedup_record(asin)

            # Push deal to TechSelect website
            if getattr(config, "WEBSITE_WEBHOOK_URL", None):
                try:
                    import httpx
                    import time as _time
                    webhook_payload = {
                        "asins": list(asins),
                        "text": updated_text,
                        "source_title": chat_title,
                        "has_media": bool(event.message.media),
                        "posted_at": _time.time(),
                    }
                    async with httpx.AsyncClient(timeout=5.0) as http:
                        resp = await http.post(
                            config.WEBSITE_WEBHOOK_URL,
                            json=webhook_payload,
                            headers={"x-webhook-secret": config.WEBSITE_WEBHOOK_SECRET or ""},
                        )
                    if resp.status_code == 200:
                        logger.info("Pushed deal to website ✓ — ASINs=%s", asins)
                    else:
                        logger.warning("Website webhook returned %d: %s", resp.status_code, resp.text[:200])
                except Exception as e:
                    logger.error("Failed to push deal to website: %s", e)

        if errors:
            alert_target_raw = getattr(config, "ALERT_CHAT_ID", "")
            if alert_target_raw:
                alert_msg = "\u26a0\ufe0f Deal Poster Errors\n" + "\n".join(errors)
                try:
                    target = await client.get_entity(alert_target_raw)
                    await safe_send(client, target, text=alert_msg, parse_mode="HTML")
                except Exception:
                    pass
            else:
                logger.warning("Posting errors occurred but ALERT_CHAT_ID is not configured")

        logger.info("Done with message from %s", event.chat_id)

    logger.info("Deal Listener active — listening for incoming posts …")
