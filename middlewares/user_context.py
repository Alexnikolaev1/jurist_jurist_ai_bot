# -*- coding: utf-8 -*-
"""
middlewares/user_context.py — автоматическая регистрация пользователя при любом апдейте.
"""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

import database as db

logger = logging.getLogger(__name__)


class UserContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user:
            await db.ensure_user(user.id, user.full_name or "")
        return await handler(event, data)
