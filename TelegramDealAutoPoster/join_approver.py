"""Join Request Auto-Approver & Invite Link Generator.

Allows users to join target deal channels via a public invite link with auto-approval.
"""

import asyncio
from telethon import TelegramClient, events
from telethon.tl import types
from telethon.tl.functions.messages import HideChatJoinRequestRequest, ExportChatInviteRequest, HideAllChatJoinRequestsRequest
from config import logger


async def approve_all_pending_requests(client: TelegramClient, channel_raw: str) -> int:
    """Approve all pending join requests for a channel in a single API call."""
    try:
        entity = await client.get_entity(channel_raw)
        await client(HideAllChatJoinRequestsRequest(
            peer=entity,
            approved=True
        ))
        logger.info("⚡ Approved all pending join requests for %s", channel_raw)
        return True
    except Exception as e:
        logger.warning("Could not approve all join requests for %s: %s", channel_raw, e)
        return False


async def _periodic_join_sweeper(client: TelegramClient) -> None:
    """Periodically sweep all target channels and approve any waiting join requests."""
    await asyncio.sleep(15)  # initial delay
    while True:
        try:
            from config import TARGET_CHANNELS
            for target in TARGET_CHANNELS:
                await approve_all_pending_requests(client, target)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug("Join sweeper error: %s", e)
        await asyncio.sleep(60)


def start_join_request_approver(client: TelegramClient) -> None:
    """Register raw event handlers to automatically approve pending join requests."""

    @client.on(events.Raw(types.UpdateBotChatInviteRequester))
    async def on_bot_join_request(event: types.UpdateBotChatInviteRequester):
        try:
            await client(HideAllChatJoinRequestsRequest(
                peer=event.peer,
                approved=True
            ))
            logger.info("⚡ Auto-approved join request(s) on chat ID %s (user ID: %s)", getattr(event.peer, 'channel_id', event.peer), getattr(event, 'user_id', 'unknown'))
        except Exception as e:
            logger.warning("Failed to auto-approve join request: %s", e)

    @client.on(events.Raw(types.UpdatePendingJoinRequests))
    async def on_pending_join_requests(event: types.UpdatePendingJoinRequests):
        try:
            await client(HideAllChatJoinRequestsRequest(
                peer=event.peer,
                approved=True
            ))
            logger.info("⚡ Auto-approved pending join request(s) on chat ID %s", getattr(event.peer, 'channel_id', event.peer))
        except Exception as e:
            logger.warning("Failed to auto-approve pending join requests: %s", e)

    # Start 60-second periodic sweeper task
    asyncio.create_task(_periodic_join_sweeper(client))
    logger.info("✓ Join Request Auto-Approver active (Instant events + 60s sweeper)")


async def generate_invite_link(client: TelegramClient, channel_raw: str, request_needed: bool = True) -> str:
    """Generate an invite link for a channel (with optional Request to Join enabled)."""
    try:
        entity = await client.get_entity(channel_raw)
        result = await client(ExportChatInviteRequest(
            peer=entity,
            request_needed=request_needed,
            title="Auto-Approve Invite"
        ))
        return result.link
    except Exception as e:
        logger.error("Failed to generate invite link for %s: %s", channel_raw, e)
        raise
