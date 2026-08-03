import asyncio
from typing import Set
from telethon import TelegramClient, events
import config
from config import logger
from amazon_engine import process_deal_text

# In-memory deduplication cache for processed ASINs and message hashes
PROCESSED_ASINS: Set[str] = set()

async def start_deal_listener(client: TelegramClient) -> None:
    """Register NewMessage handlers on Telethon client to listen to joined channels."""
    
    # Determine which channels to listen to
    chats_to_listen = config.SOURCE_CHANNELS if config.SOURCE_CHANNELS else None
    
    @client.on(events.NewMessage(chats=chats_to_listen))
    async def handler(event: events.NewMessage.Event):
        # Ignore messages sent by self to prevent infinite feedback loops
        if event.out:
            return
            
        text = event.message.message or ""
        if not text:
            return
            
        # Check if text contains Amazon links & convert them
        has_amazon, updated_text, asins = await process_deal_text(
            text=text,
            affiliate_tag=config.AFFILIATE_TAG,
            default_domain=config.DEFAULT_AMAZON_DOMAIN
        )
        
        if not has_amazon:
            return  # No Amazon deal found in message
            
        # Deduplication check: skip if all ASINs in message were already posted recently
        if asins and asins.issubset(PROCESSED_ASINS):
            logger.info(f"Skipping duplicate deal with ASINs: {asins}")
            return
            
        PROCESSED_ASINS.update(asins)
        
        # Limit deduplication set size to prevent unbounded memory growth
        if len(PROCESSED_ASINS) > 5000:
            PROCESSED_ASINS.clear()
            
        logger.info(f"Extracted Amazon deal from {event.chat_id} (ASINs: {asins})")
        
        # Post to target channels
        if not config.TARGET_CHANNELS:
            logger.warning("No TARGET_CHANNELS configured in .env! Printing converted deal to log:")
            logger.info(f"Converted Text:\n{updated_text}")
            return
            
        for target in config.TARGET_CHANNELS:
            try:
                # If original message has photo/media, send media with updated caption
                if event.message.media:
                    await client.send_file(
                        target,
                        file=event.message.media,
                        caption=updated_text,
                        parse_mode="html"
                    )
                else:
                    await client.send_message(
                        target,
                        updated_text,
                        parse_mode="html"
                    )
                logger.info(f"Successfully posted converted deal to target channel: {target}")
            except Exception as e:
                logger.error(f"Failed to post deal to target '{target}': {e}")

    logger.info("Multi-Channel Deal Listener active! Listening for incoming deal posts...")
