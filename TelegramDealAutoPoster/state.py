"""In-memory state store and event history for the web UI monitor."""

import time
import logging
from collections import deque
from typing import Any

import config

recent_deals: deque[dict[str, Any]] = deque(maxlen=50)
recent_events: deque[dict[str, Any]] = deque(maxlen=300)

stats: dict[str, Any] = {
    "started_at": 0.0,
    "total_detected": 0,
    "total_posted": 0,
    "total_skipped_dup": 0,
    "total_errors": 0,
    "posts_today": 0,
    "last_post_at": 0.0,
}

_last_reset_day: str = time.strftime("%Y-%m-%d")
_event_counter: int = 0


class StateLogHandler(logging.Handler):
    """Custom log handler that captures log records into recent_events."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            record_event("log", msg, level=record.levelname)
        except Exception:
            self.handleError(record)


def _check_daily_reset() -> None:
    global _last_reset_day
    current_day = time.strftime("%Y-%m-%d")
    if current_day != _last_reset_day:
        _last_reset_day = current_day
        stats["posts_today"] = 0


def init() -> None:
    """Initialize state store and attach logging handler."""
    global _last_reset_day
    stats["started_at"] = time.time()
    _last_reset_day = time.strftime("%Y-%m-%d")

    # Attach log handler to config.logger
    handler = StateLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    config.logger.addHandler(handler)
    record_event("log", "State initialized and logging handler attached.")


def record_event(event_type: str, msg: str, level: str = "INFO") -> dict[str, Any]:
    """Append a structured event to recent_events."""
    global _event_counter
    _event_counter += 1
    ev = {
        "id": _event_counter,
        "ts": time.time(),
        "type": event_type,
        "msg": msg,
        "level": level,
    }
    recent_events.append(ev)
    return ev


def record_detected(asins: list[str], source_id: Any = None, source_title: str | None = None) -> None:
    """Record a detected deal."""
    stats["total_detected"] += 1
    src_display = source_title or str(source_id) or "Unknown"
    record_event(
        "detected",
        f"Detected deal from '{src_display}': ASINs {', '.join(asins)}",
    )


def record_posted(deal: dict[str, Any]) -> None:
    """Record a successfully posted deal."""
    _check_daily_reset()
    stats["total_posted"] += 1
    stats["posts_today"] += 1
    stats["last_post_at"] = time.time()

    if "ts" not in deal:
        deal["ts"] = time.time()
    recent_deals.append(deal)

    asins_str = ", ".join(deal.get("asins", [])) if isinstance(deal.get("asins"), list) else str(deal.get("asins", ""))
    record_event(
        "posted",
        f"Posted deal to '{deal.get('target')}': ASINs [{asins_str}]",
    )


def record_skipped(asins: list[str]) -> None:
    """Record a deal skipped due to deduplication."""
    stats["total_skipped_dup"] += 1
    record_event(
        "skipped_dup",
        f"Skipped duplicate deal: ASINs [{', '.join(asins)}] already posted",
    )


def record_error(msg: str) -> None:
    """Record an error event."""
    stats["total_errors"] += 1
    record_event("error", f"Error: {msg}", level="ERROR")


def snapshot() -> dict[str, Any]:
    """Return a clean copy of the stats dictionary."""
    _check_daily_reset()
    return dict(stats)


def recent(n: int = 50) -> list[dict[str, Any]]:
    """Return the n most recent deal posts."""
    return list(recent_deals)[-n:]


def recent_logs(n: int = 200) -> list[dict[str, Any]]:
    """Return the n most recent log/event entries."""
    return list(recent_events)[-n:]


def events_since(ts: float = 0.0) -> list[dict[str, Any]]:
    """Return all events with timestamp greater than ts."""
    return [e for e in recent_events if e["ts"] > ts]


def events_since_id(last_id: int = 0) -> list[dict[str, Any]]:
    """Return all events with ID greater than last_id."""
    return [e for e in recent_events if e["id"] > last_id]


def get_last_event_id() -> int:
    """Return the highest event ID currently recorded."""
    return _event_counter


def warmup_until() -> float:
    """Return the timestamp when warmup mode expires, or 0 if inactive."""
    if not stats["started_at"]:
        return 0.0
    warmup_hours = int(getattr(config, "WARMUP_HOURS", 0))
    if warmup_hours > 0:
        return stats["started_at"] + (warmup_hours * 3600)
    return 0.0
