import asyncio

import pytest
import utils


def test_concurrent_waiters_recheck_the_cap_and_record_actual_send_time(monkeypatch):
    clock = [10000.0]
    sleeps = []
    actual_sleep = asyncio.sleep

    async def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
        await actual_sleep(0)

    monkeypatch.setattr(utils.time, "time", lambda: clock[0])
    monkeypatch.setattr(utils.asyncio, "sleep", sleep)

    async def exercise():
        limiter = utils.RateLimiter(max_per_hour=1, min_delay=5, max_delay=5)
        await asyncio.gather(limiter.acquire(), limiter.acquire(), limiter.acquire())
        assert limiter._timestamps == [17215.0]

    asyncio.run(exercise())
    assert sleeps == [5, 3600, 5, 3600, 5]


def test_zero_hourly_limit_is_rejected():
    with pytest.raises(ValueError):
        utils.RateLimiter(max_per_hour=0)
