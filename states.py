# -*- coding: utf-8 -*-
"""
states.py — состояния конечных автоматов (FSM) aiogram для многошаговых
сценариев: генерация документа и настройки профиля.
"""
from aiogram.fsm.state import State, StatesGroup


class DocumentStates(StatesGroup):
    choosing_type = State()      # пользователь выбирает тип документа
    collecting_data = State()    # бот по очереди запрашивает недостающие поля
    ready_to_generate = State()  # все данные собраны, ждём подтверждения


class SettingsStates(StatesGroup):
    full_name = State()
    address = State()
    phone = State()
    country = State()


class ContractStates(StatesGroup):
    awaiting_photo = State()  # пользователь нажал «Проверка договора» и ждёт фото
