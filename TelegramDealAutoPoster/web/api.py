"""FastAPI application for the Telegram Deal Auto-Poster Web UI Monitor."""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from telethon import TelegramClient

import config
import state
import channels
from utils import RATE_LIMITER, rate_limiter_status, dedup_load

WEB_DIR = Path(__file__).parent


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
    async def get_channels(refresh: bool = Query(False, description="Force re-scan")) -> dict[str, Any]:
        data = await channels.list_channels(client, force_refresh=refresh)
        return {"channels": data}

    @app.get("/api/stats")
    async def get_stats() -> dict[str, Any]:
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
            "target_channels": config.TARGET_CHANNELS,
            "affiliate_tags": config.AFFILIATE_TAGS,
            "dedup_size": dedup_size,
        }

    @app.get("/api/recent")
    async def get_recent(n: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
        return {"deals": state.recent(n)}

    @app.get("/api/logs")
    async def get_logs(n: int = Query(200, ge=1, le=500)) -> dict[str, Any]:
        return {"logs": state.recent_logs(n)}

    @app.get("/api/events")
    async def get_events(request: Request) -> StreamingResponse:
        async def event_generator():
            # Start streaming from the current latest event ID
            last_id = state.get_last_event_id()
            try:
                while not request.is_disconnected():
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

    return app
