"""Join Request Auto-Approver & Invite Link Generator.

Allows users to join target deal channels via a public invite link with auto-approval.
"""

import asyncio
from telethon import TelegramClient, events
from telethon.tl import types
from telethon.tl.functions.messages import HideChatJoinRequestRequest, ExportChatInviteRequest
from config import logger


def start_join_request_approver(client: TelegramClient) -> None:
    """Register raw event handlers to automatically approve pending join requests."""

    @client.on(events.Raw(types.UpdateBotChatInviteRequester))
    async def on_bot_join_request(event: types.UpdateBotChatInviteRequester):
        try:
            await client(HideChatJoinRequestRequest(
                peer=event.peer,
                user_id=event.user_id,
                approved=True
            ))
            logger.info("⚡ Auto-approved join request from user ID %s", event.user_id)
        except Exception as e:
            logger.warning("Failed to auto-approve join request from user ID %s: %s", event.user_id, e)

    @client.on(events.Raw(types.UpdatePendingJoinRequests))
    async def on_pending_join_requests(event: types.UpdatePendingJoinRequests):
        requesters = getattr(event, "recent_requesters", []) or []
        for user_id in requesters:
            try:
                await client(HideChatJoinRequestRequest(
                    peer=event.peer,
                    user_id=user_id,
                    approved=True
                ))
                logger.info("⚡ Auto-approved join request from user ID %s", user_id)
            except Exception as e:
                logger.warning("Failed to auto-approve join request from user ID %s: %s", user_id, e)

    logger.info("✓ Join Request Auto-Approver active — listening for incoming requests …")


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
