# -*- coding: utf-8 -*-
"""
utils/filters.py — переиспользуемые фильтры aiogram для контроля доступа
и изоляции хендлеров (дисклеймер, FSM-состояния, кнопки меню).
"""
from typing import Any

from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

import database as db
import keyboards as kb


MENU_BUTTON_TEXTS = frozenset({
    kb.BTN_CONSULT, kb.BTN_DOCUMENT, kb.BTN_CONTRACT,
    kb.BTN_HISTORY, kb.BTN_SETTINGS, kb.BTN_EMERGENCY,
})


class DisclaimerAcceptedFilter(BaseFilter):
    """Пропускает только пользователей, принявших дисклеймер."""

    async def __call__(self, event: TelegramObject, **kwargs: Any) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False
        return await db.is_disclaimer_accepted(user.id)


class NotMenuButtonFilter(BaseFilter):
    """Текстовое сообщение не является кнопкой главного меню."""

    async def __call__(self, message: Message, **kwargs: Any) -> bool:
        return message.text not in MENU_BUTTON_TEXTS


class DisclaimerNotAcceptedFilter(BaseFilter):
    """Пропускает пользователей, ещё не принявших дисклеймер."""

    async def __call__(self, event: TelegramObject, **kwargs: Any) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False
        return not await db.is_disclaimer_accepted(user.id)


class NoActiveFsmFilter(BaseFilter):
    """Пользователь не находится в активном FSM-сценарии."""

    async def __call__(self, event: TelegramObject, state: FSMContext, **kwargs: Any) -> bool:
        current = await state.get_state()
        return current is None
