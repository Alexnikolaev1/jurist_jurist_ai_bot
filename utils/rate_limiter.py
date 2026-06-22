# -*- coding: utf-8 -*-
"""
rate_limiter.py — асинхронный rate limiter (sliding window) для запросов
к Gemini API. Защищает бесплатную квоту от превышения: ограничение
персональное (на пользователя) и глобальное (на весь бот).

Реализация in-memory (без Redis) — этого достаточно для одного процесса
на Railway free-tier.
"""
import asyncio
import time
from collections import defaultdict, deque

import config


class RateLimiter:
    def __init__(
        self,
        per_user_limit: int = config.GEMINI_RATE_LIMIT_PER_USER,
        global_limit: int = config.GEMINI_RATE_LIMIT_GLOBAL,
        window_seconds: int = config.RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        self.per_user_limit = per_user_limit
        self.global_limit = global_limit
        self.window_seconds = window_seconds
        self._user_calls: dict[int, deque] = defaultdict(deque)
        self._global_calls: deque = deque()
        self._lock = asyncio.Lock()

    async def allow(self, user_id: int) -> bool:
        """
        Проверяет, можно ли пользователю user_id сейчас сделать запрос.
        Если да — сразу регистрирует этот запрос (атомарно под локом).
        """
        now = time.monotonic()
        async with self._lock:
            self._evict_old(self._global_calls, now)
            user_queue = self._user_calls[user_id]
            self._evict_old(user_queue, now)

            if len(self._global_calls) >= self.global_limit:
                return False
            if len(user_queue) >= self.per_user_limit:
                return False

            self._global_calls.append(now)
            user_queue.append(now)
            return True

    def _evict_old(self, q: deque, now: float) -> None:
        while q and now - q[0] > self.window_seconds:
            q.popleft()

    async def seconds_until_available(self, user_id: int) -> int:
        """Сколько секунд подождать пользователю до следующей попытки."""
        now = time.monotonic()
        async with self._lock:
            user_queue = self._user_calls[user_id]
            self._evict_old(user_queue, now)
            self._evict_old(self._global_calls, now)
            candidates = []
            if user_queue and len(user_queue) >= self.per_user_limit:
                candidates.append(self.window_seconds - (now - user_queue[0]))
            if self._global_calls and len(self._global_calls) >= self.global_limit:
                candidates.append(self.window_seconds - (now - self._global_calls[0]))
            return max(1, int(max(candidates))) if candidates else 1


# Единый на всё приложение лимитер для запросов к Gemini.
gemini_rate_limiter = RateLimiter()
