"""FastAPI application for the Telegram Deal Auto-Poster Web UI Monitor."""

import asyncio
import json
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from telethon import TelegramClient

import channels
import config
import state
from utils import dedup_load, rate_limiter_status

WEB_DIR = Path(__file__).parent
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _check_monitor_access(
    request: Request,
    authorization: str | None = None,
    x_api_key: str | None = None,
) -> None:
    """Allow monitor access from loopback by default, or require a token when configured."""
    client_host = (request.client.host if request.client else "").lower()
    token = config.MONITOR_API_TOKEN
    if token:
        bearer = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else ""
        presented = bearer or (x_api_key or "").strip()
        if not presented or not secrets.compare_digest(presented, token):
            raise HTTPException(status_code=401, detail="Monitor authentication required")
        return
    if client_host not in _LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="Monitor is restricted to localhost")


def create_app(client: TelegramClient) -> FastAPI:
    app = FastAPI(
        title="Telegram Deal Auto-Poster Monitor",
        description="Localhost-only read-only monitoring dashboard.",
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/")
    async def get_index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/channels")
    async def get_channels(
        request: Request,
        refresh: bool = Query(False, description="Force re-scan"),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ) -> dict[str, Any]:
        _check_monitor_access(request, authorization, x_api_key)
        data = await channels.list_channels(client, force_refresh=refresh)
        return {"channels": data}

    @app.get("/api/stats")
    async def get_stats(
        request: Request,
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ) -> dict[str, Any]:
        _check_monitor_access(request, authorization, x_api_key)
        snap = state.snapshot()
        limiter = rate_limiter_status()
        warmup_end = state.warmup_until()
        warmup_hours = int(getattr(config, "WARMUP_HOURS", 0))

        try:
            dedup_size = len(dedup_load())
        except Exception:
            dedup_size = 0

        return {
            "stats": snap,
            "rate_limiter": limiter,
            "warmup_until": warmup_end,
            "warmup_hours": warmup_hours,
            "dedup_size": dedup_size,
        }

    @app.get("/api/recent")
    async def get_recent(
        request: Request,
        n: int = Query(50, ge=1, le=200),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ) -> dict[str, Any]:
        _check_monitor_access(request, authorization, x_api_key)
        return {"deals": state.recent(n)}

    @app.get("/api/logs")
    async def get_logs(
        request: Request,
        n: int = Query(200, ge=1, le=500),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ) -> dict[str, Any]:
        _check_monitor_access(request, authorization, x_api_key)
        return {"logs": state.recent_logs(n)}

    @app.get("/api/events")
    async def get_events(
        request: Request,
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ) -> StreamingResponse:
        _check_monitor_access(request, authorization, x_api_key)

        async def event_generator():
            last_id = state.get_last_event_id()
            try:
                while not await request.is_disconnected():
                    events = state.events_since_id(last_id)
                    if events:
                        for ev in events:
                            if ev["id"] > last_id:
                                last_id = ev["id"]
                            yield f"data: {json.dumps(ev)}\n\n"
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/invite-link")
    async def get_invite_link(
        request: Request,
        channel: str = Query(None, description="Target channel username or ID"),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _check_monitor_access(request, authorization, x_api_key)
        from join_approver import generate_invite_link

        target = channel or (config.TARGET_CHANNELS[0] if config.TARGET_CHANNELS else None)
        if not target:
            return {"error": "No target channel specified or configured."}
        try:
            link = await generate_invite_link(client, target, request_needed=True)
            return {"channel": target, "invite_link": link, "auto_approve": True}
        except Exception as e:
            return {"channel": target, "error": str(e)}

    @app.get("/api/approve-all")
    async def approve_all(
        request: Request,
        channel: str = Query(None, description="Target channel username or ID"),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _check_monitor_access(request, authorization, x_api_key)
        from join_approver import approve_all_pending_requests

        target = channel or (config.TARGET_CHANNELS[0] if config.TARGET_CHANNELS else None)
        if not target:
            return {"error": "No target channel specified or configured."}
        success = await approve_all_pending_requests(client, target)
        return {"channel": target, "success": success}

    return app
