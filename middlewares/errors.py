# -*- coding: utf-8 -*-
"""
middlewares/errors.py — централизованная обработка необработанных исключений.
"""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)

_USER_MESSAGE = (
    "⚠️ Произошла непредвиденная ошибка. Попробуйте ещё раз через минуту "
    "или обратитесь к администратору, если проблема повторяется."
)


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            logger.exception("Необработанное исключение в хендлере")
            await self._notify_user(event)
            return None

    @staticmethod
    async def _notify_user(event: TelegramObject) -> None:
        if isinstance(event, Message):
            await event.answer(_USER_MESSAGE)
        elif isinstance(event, CallbackQuery):
            await event.answer("Произошла ошибка. Попробуйте снова.", show_alert=True)
