# -*- coding: utf-8 -*-
"""
database.py — инициализация SQLite, схема таблиц, полнотекстовый поиск (FTS5)
и набор асинхронных хелперов для работы с БД.

sqlite3 в стандартной библиотеке — синхронный модуль. Чтобы не блокировать
event loop aiogram, все обращения к БД выполняются в отдельном потоке через
asyncio.to_thread(). Соединение открывается с check_same_thread=False и
защищается блокировкой threading.Lock(), так как sqlite3-соединения не
потокобезопасны при параллельной записи.
"""
import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Optional

import config

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_connection: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    """Возвращает единое (singleton) соединение с БД."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL;")
        _connection.execute("PRAGMA foreign_keys=ON;")
    return _connection


# ---------------------------------------------------------------------------
# Синхронные операции (выполняются внутри asyncio.to_thread)
# ---------------------------------------------------------------------------

def _migrate_schema_sync() -> None:
    """Добавляет новые колонки и таблицы для существующих БД."""
    conn = _get_conn()
    migrations = [
        "ALTER TABLE users ADD COLUMN disclaimer_accepted INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN last_consultation_query TEXT",
        "ALTER TABLE users ADD COLUMN last_consultation_answer TEXT",
    ]
    with _lock:
        for sql in migrations:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_metadata (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.commit()


def _init_schema_sync() -> None:
    """Создаёт все таблицы, если их ещё нет."""
    conn = _get_conn()
    with _lock:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id                  INTEGER PRIMARY KEY,
                full_name                TEXT,
                address                  TEXT,
                phone                    TEXT,
                country                  TEXT DEFAULT 'RU',
                disclaimer_accepted      INTEGER DEFAULT 0,
                last_consultation_query  TEXT,
                last_consultation_answer TEXT,
                created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS laws (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                codex          TEXT NOT NULL,
                article_number TEXT NOT NULL,
                article_title  TEXT,
                article_text   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS consultation_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                query      TEXT,
                response   TEXT,
                timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS document_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                doc_type   TEXT,
                content    TEXT,
                timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cache (
                key         TEXT PRIMARY KEY,
                data        TEXT,
                expires_at  TIMESTAMP
            );
            """
        )

        conn.executescript(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS laws_fts USING fts5(
                codex,
                article_number,
                article_title,
                article_text,
                content='laws',
                content_rowid='id',
                tokenize='unicode61 remove_diacritics 2'
            );

            CREATE TRIGGER IF NOT EXISTS laws_ai AFTER INSERT ON laws BEGIN
                INSERT INTO laws_fts(rowid, codex, article_number, article_title, article_text)
                VALUES (new.id, new.codex, new.article_number, new.article_title, new.article_text);
            END;

            CREATE TRIGGER IF NOT EXISTS laws_ad AFTER DELETE ON laws BEGIN
                INSERT INTO laws_fts(laws_fts, rowid, codex, article_number, article_title, article_text)
                VALUES('delete', old.id, old.codex, old.article_number, old.article_title, old.article_text);
            END;

            CREATE TRIGGER IF NOT EXISTS laws_au AFTER UPDATE ON laws BEGIN
                INSERT INTO laws_fts(laws_fts, rowid, codex, article_number, article_title, article_text)
                VALUES('delete', old.id, old.codex, old.article_number, old.article_title, old.article_text);
                INSERT INTO laws_fts(rowid, codex, article_number, article_title, article_text)
                VALUES (new.id, new.codex, new.article_number, new.article_title, new.article_text);
            END;
            """
        )
        conn.commit()
    _migrate_schema_sync()


def _load_laws_sync() -> int:
    """
    Импортирует или обновляет законы из data/laws.json.
    Перезагружает базу, если изменился хэш файла laws.json.
  """
    conn = _get_conn()
    if not os.path.exists(config.LAWS_JSON_PATH):
        logger.warning("Файл %s не найден, база законов пуста.", config.LAWS_JSON_PATH)
        return 0

    with open(config.LAWS_JSON_PATH, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    with _lock:
        cur = conn.execute(
            "SELECT value FROM app_metadata WHERE key = 'laws_json_hash'"
        )
        row = cur.fetchone()
        stored_hash = row[0] if row else None

        cur = conn.execute("SELECT COUNT(*) AS cnt FROM laws")
        count = cur.fetchone()["cnt"]

        if count > 0 and stored_hash == file_hash:
            logger.info("База законов актуальна (%s статей).", count)
            return count

        if count > 0:
            logger.info("Обнаружено обновление laws.json — перезагружаю базу законов.")
            conn.execute("DELETE FROM laws")
            conn.commit()

        with open(config.LAWS_JSON_PATH, "r", encoding="utf-8") as f:
            laws = json.load(f)

        rows = [
            (item["codex"], item["article_number"], item.get("article_title", ""), item["article_text"])
            for item in laws
        ]
        conn.executemany(
            "INSERT INTO laws (codex, article_number, article_title, article_text) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.execute(
            "INSERT INTO app_metadata (key, value) VALUES ('laws_json_hash', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (file_hash,),
        )
        conn.commit()
        logger.info("Импортировано %s статей закона из laws.json", len(rows))
        return len(rows)


def _search_laws_sync(match_query: str, limit: int) -> list[dict]:
    """Полнотекстовый поиск по FTS5. match_query — уже подготовленная FTS5-строка."""
    conn = _get_conn()
    if not match_query.strip():
        return []
    try:
        with _lock:
            cur = conn.execute(
                """
                SELECT laws.id, laws.codex, laws.article_number, laws.article_title, laws.article_text
                FROM laws_fts
                JOIN laws ON laws.id = laws_fts.rowid
                WHERE laws_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (match_query, limit),
            )
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.OperationalError as exc:
        # Например, некорректный синтаксис FTS5-запроса (спецсимволы пользователя).
        logger.warning("Ошибка FTS5-запроса '%s': %s", match_query, exc)
        return []


def _get_user_sync(user_id: int) -> Optional[dict]:
    conn = _get_conn()
    with _lock:
        cur = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _ensure_user_sync(user_id: int, full_name: str = "") -> None:
    conn = _get_conn()
    with _lock:
        existing = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (user_id, full_name) VALUES (?, ?)",
                (user_id, full_name),
            )
            conn.commit()


def _is_disclaimer_accepted_sync(user_id: int) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT disclaimer_accepted FROM users WHERE user_id = ?", (user_id,)
        )
        row = cur.fetchone()
        return bool(row and row["disclaimer_accepted"])


def _accept_disclaimer_sync(user_id: int) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute(
            "UPDATE users SET disclaimer_accepted = 1 WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()


def _save_last_consultation_sync(user_id: int, query: str, answer: str) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute(
            "UPDATE users SET last_consultation_query = ?, last_consultation_answer = ? "
            "WHERE user_id = ?",
            (query, answer, user_id),
        )
        conn.commit()


def _get_last_consultation_sync(user_id: int) -> Optional[dict]:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT last_consultation_query AS query, last_consultation_answer AS answer "
            "FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        if row and row["query"] and row["answer"]:
            return {"query": row["query"], "answer": row["answer"]}
        return None


def _get_document_history_sync(user_id: int, limit: int = 10) -> list[dict]:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT id, doc_type, timestamp FROM document_log "
            "WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def _upsert_user_sync(user_id: int, **fields: Any) -> None:
    conn = _get_conn()
    with _lock:
        existing = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if existing:
            if fields:
                set_clause = ", ".join(f"{k} = ?" for k in fields)
                conn.execute(
                    f"UPDATE users SET {set_clause} WHERE user_id = ?",
                    (*fields.values(), user_id),
                )
        else:
            columns = ", ".join(["user_id", *fields.keys()])
            placeholders = ", ".join(["?"] * (len(fields) + 1))
            conn.execute(
                f"INSERT INTO users ({columns}) VALUES ({placeholders})",
                (user_id, *fields.values()),
            )
        conn.commit()


def _delete_user_data_sync(user_id: int) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM consultation_log WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM document_log WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM fsm_storage WHERE user_id = ?", (user_id,))
        conn.commit()


def _log_consultation_sync(user_id: int, query: str, response: str) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO consultation_log (user_id, query, response) VALUES (?, ?, ?)",
            (user_id, query, response),
        )
        conn.commit()


def _log_document_sync(user_id: int, doc_type: str, content: str) -> int:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "INSERT INTO document_log (user_id, doc_type, content) VALUES (?, ?, ?)",
            (user_id, doc_type, content),
        )
        conn.commit()
        return cur.lastrowid


def _get_document_sync(doc_log_id: int, user_id: int) -> Optional[dict]:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT * FROM document_log WHERE id = ? AND user_id = ?",
            (doc_log_id, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _get_history_sync(user_id: int, limit: int = 10) -> list[dict]:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT query, response, timestamp FROM consultation_log "
            "WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def _cache_get_sync(key: str) -> Optional[str]:
    conn = _get_conn()
    with _lock:
        cur = conn.execute("SELECT data, expires_at FROM cache WHERE key = ?", (key,))
        row = cur.fetchone()
        if not row:
            return None
        if row["expires_at"] < time.time():
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
            return None
        return row["data"]


def _cache_set_sync(key: str, data: str, ttl_seconds: int) -> None:
    conn = _get_conn()
    with _lock:
        expires_at = time.time() + ttl_seconds
        conn.execute(
            "INSERT INTO cache (key, data, expires_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET data = excluded.data, expires_at = excluded.expires_at",
            (key, data, expires_at),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Публичный асинхронный API (используется в хендлерах и сервисах)
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Инициализация схемы БД и загрузка базы законов. Вызывается при старте бота."""
    await asyncio.to_thread(_init_schema_sync)
    loaded = await asyncio.to_thread(_load_laws_sync)
    logger.info("База данных готова. Статей закона в базе: %s", loaded)


async def search_laws(match_query: str, limit: int = config.LAW_SEARCH_LIMIT) -> list[dict]:
    return await asyncio.to_thread(_search_laws_sync, match_query, limit)


async def get_user(user_id: int) -> Optional[dict]:
    return await asyncio.to_thread(_get_user_sync, user_id)


async def upsert_user(user_id: int, **fields: Any) -> None:
    await asyncio.to_thread(_upsert_user_sync, user_id, **fields)


async def ensure_user(user_id: int, full_name: str = "") -> None:
    await asyncio.to_thread(_ensure_user_sync, user_id, full_name)


async def is_disclaimer_accepted(user_id: int) -> bool:
    return await asyncio.to_thread(_is_disclaimer_accepted_sync, user_id)


async def accept_disclaimer(user_id: int) -> None:
    await asyncio.to_thread(_accept_disclaimer_sync, user_id)


async def save_last_consultation(user_id: int, query: str, answer: str) -> None:
    await asyncio.to_thread(_save_last_consultation_sync, user_id, query, answer)


async def get_last_consultation(user_id: int) -> Optional[dict]:
    return await asyncio.to_thread(_get_last_consultation_sync, user_id)


async def get_document_history(user_id: int, limit: int = 10) -> list[dict]:
    return await asyncio.to_thread(_get_document_history_sync, user_id, limit)


async def delete_user_data(user_id: int) -> None:
    await asyncio.to_thread(_delete_user_data_sync, user_id)


async def log_consultation(user_id: int, query: str, response: str) -> None:
    await asyncio.to_thread(_log_consultation_sync, user_id, query, response)


async def log_document(user_id: int, doc_type: str, content: str) -> int:
    return await asyncio.to_thread(_log_document_sync, user_id, doc_type, content)


async def get_document(doc_log_id: int, user_id: int) -> Optional[dict]:
    return await asyncio.to_thread(_get_document_sync, doc_log_id, user_id)


async def get_history(user_id: int, limit: int = 10) -> list[dict]:
    return await asyncio.to_thread(_get_history_sync, user_id, limit)


async def cache_get(key: str) -> Optional[str]:
    return await asyncio.to_thread(_cache_get_sync, key)


async def cache_set(key: str, data: str, ttl_seconds: int = config.CACHE_TTL_SECONDS) -> None:
    await asyncio.to_thread(_cache_set_sync, key, data, ttl_seconds)
