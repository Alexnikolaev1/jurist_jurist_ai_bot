# -*- coding: utf-8 -*-
"""
storage/sqlite_storage.py — персистентное хранилище FSM-состояний в SQLite.

Позволяет сохранять прогресс многошаговых сценариев (документ, настройки)
между перезапусками бота и редеплоями на Railway.
"""
import asyncio
import json
import logging
import threading
from typing import Any, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

import config

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_connection = None


def _get_conn():
    global _connection
    if _connection is None:
        import sqlite3
        _connection = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _connection.execute("PRAGMA journal_mode=WAL;")
    return _connection


def _init_fsm_table_sync() -> None:
    conn = _get_conn()
    with _lock:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fsm_storage (
                bot_id      INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                state       TEXT,
                data        TEXT DEFAULT '{}',
                PRIMARY KEY (bot_id, chat_id, user_id)
            )
            """
        )
        conn.commit()


def _set_state_sync(key: StorageKey, state: Optional[str]) -> None:
    conn = _get_conn()
    with _lock:
        if state is None:
            conn.execute(
                "DELETE FROM fsm_storage WHERE bot_id=? AND chat_id=? AND user_id=?",
                (key.bot_id, key.chat_id, key.user_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO fsm_storage (bot_id, chat_id, user_id, state, data)
                VALUES (?, ?, ?, ?, '{}')
                ON CONFLICT(bot_id, chat_id, user_id)
                DO UPDATE SET state = excluded.state
                """,
                (key.bot_id, key.chat_id, key.user_id, state),
            )
        conn.commit()


def _get_state_sync(key: StorageKey) -> Optional[str]:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT state FROM fsm_storage WHERE bot_id=? AND chat_id=? AND user_id=?",
            (key.bot_id, key.chat_id, key.user_id),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _set_data_sync(key: StorageKey, data: dict[str, Any]) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute(
            """
            INSERT INTO fsm_storage (bot_id, chat_id, user_id, state, data)
            VALUES (?, ?, ?, NULL, ?)
            ON CONFLICT(bot_id, chat_id, user_id)
            DO UPDATE SET data = excluded.data
            """,
            (key.bot_id, key.chat_id, key.user_id, json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()


def _get_data_sync(key: StorageKey) -> dict[str, Any]:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT data FROM fsm_storage WHERE bot_id=? AND chat_id=? AND user_id=?",
            (key.bot_id, key.chat_id, key.user_id),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return {}
        return json.loads(row[0])


class SQLiteStorage(BaseStorage):
    def __init__(self) -> None:
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await asyncio.to_thread(_init_fsm_table_sync)
            self._initialized = True

    async def set_state(self, key: StorageKey, state: State | str | None = None) -> None:
        await self._ensure_initialized()
        state_str = state.state if isinstance(state, State) else state
        await asyncio.to_thread(_set_state_sync, key, state_str)

    async def get_state(self, key: StorageKey) -> Optional[str]:
        await self._ensure_initialized()
        return await asyncio.to_thread(_get_state_sync, key)

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        await self._ensure_initialized()
        await asyncio.to_thread(_set_data_sync, key, data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        await self._ensure_initialized()
        return await asyncio.to_thread(_get_data_sync, key)

    async def close(self) -> None:
        pass
