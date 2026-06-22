# -*- coding: utf-8 -*-
import time

import pytest

from utils.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_allows_within_limit():
    limiter = RateLimiter(per_user_limit=3, global_limit=10, window_seconds=60)
    for _ in range(3):
        assert await limiter.allow(user_id=1) is True


@pytest.mark.asyncio
async def test_blocks_over_user_limit():
    limiter = RateLimiter(per_user_limit=2, global_limit=100, window_seconds=60)
    assert await limiter.allow(user_id=42) is True
    assert await limiter.allow(user_id=42) is True
    assert await limiter.allow(user_id=42) is False


@pytest.mark.asyncio
async def test_separate_user_limits():
    limiter = RateLimiter(per_user_limit=1, global_limit=100, window_seconds=60)
    assert await limiter.allow(user_id=1) is True
    assert await limiter.allow(user_id=2) is True
    assert await limiter.allow(user_id=1) is False


@pytest.mark.asyncio
async def test_seconds_until_available():
    limiter = RateLimiter(per_user_limit=1, global_limit=100, window_seconds=60)
    await limiter.allow(user_id=99)
    await limiter.allow(user_id=99)
    wait = await limiter.seconds_until_available(99)
    assert 0 < wait <= 60
