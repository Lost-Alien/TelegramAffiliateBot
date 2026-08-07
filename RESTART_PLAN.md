# Restart Plan

## Progress So Far

- Updated the local OpenAI API key for dev use in `claude-code-telegram/.env` and in the user environment.
- Confirmed the key is usable for model access, but billing visibility still depends on account permissions.
- Audited the repo for the main risk areas.
- Fixed the `TelegramDealAutoPoster` dedup flow so ASINs are recorded only after at least one successful post.
- Removed the public-channel fallback for error alerts; alerts now go only to `ALERT_CHAT_ID`.
- Hardened the monitor API so it is localhost-only by default and can also require `MONITOR_API_TOKEN`.
- Verified the `TelegramDealAutoPoster` test suite passes after the fixes.

## Current State

- `TelegramDealAutoPoster` is in a safer state for production use.
- The dashboard still shows live events, recent deal posts, and logs.
- The monitor API now exposes less operational data and can be token-protected.

## Next Steps

1. Decide whether to add `MONITOR_API_TOKEN` to `TelegramDealAutoPoster/.env` for stronger dashboard access control.
2. Decide whether to set `ALERT_CHAT_ID` to a private admin chat so posting failures are visible again.
3. Optionally tighten `claude-code-telegram` auth by removing the development allow-all fallback if you want stricter access control.
4. Run a full startup check for `claude-code-telegram` to confirm it picks up the OpenAI key cleanly.
5. If you want the dashboard to show the source channel in every live `posted` line, update `TelegramDealAutoPoster/state.py` and `TelegramDealAutoPoster/web/index.html` together.

## Notes For Resume

- Do not reintroduce the old dedup behavior where ASINs are recorded before posting succeeds.
- Do not restore the public target fallback for error alerts.
- Avoid printing or committing any API keys or Telegram secrets.
