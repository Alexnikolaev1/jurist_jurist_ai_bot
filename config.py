# -*- coding: utf-8 -*-
"""
config.py — переменные окружения и константы проекта JURIST AI.

Все секреты (токены, ключи API) задаются ТОЛЬКО через переменные окружения
(в Railway это делается во вкладке Variables). Хардкодить ключи в коде нельзя.
"""
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

# === Базовые токены и ключи API ===
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "Не задана переменная окружения TELEGRAM_BOT_TOKEN. "
        "Добавьте её в Railway -> Variables."
    )

# === Режим работы: вебхук или поллинг ===
_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("RAILWAY_STATIC_URL")
WEBHOOK_HOST: str = os.getenv("WEBHOOK_URL") or (
    f"https://{_railway_domain}" if _railway_domain else ""
)
# Хэш токена вместо самого токена — не светим секрет в URL и логах.
_webhook_secret = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).hexdigest()[:24]
WEBHOOK_PATH: str = f"/webhook/{_webhook_secret}"
WEBHOOK_URL: str = f"{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else ""
USE_WEBHOOK: bool = bool(WEBHOOK_HOST)
PORT: int = int(os.getenv("PORT", 8000))

# === Gemini (Google AI Studio, бесплатный тариф) ===
GEMINI_MODEL: str = "gemini-1.5-flash"
GEMINI_API_URL: str = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# === Groq Whisper (бесплатная транскрибация голоса) ===
GROQ_TRANSCRIPTION_URL: str = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_WHISPER_MODEL: str = "whisper-large-v3"

# === Rate limiting для Gemini (бесплатный тариф ограничен по RPM) ===
GEMINI_RATE_LIMIT_PER_USER: int = 5     # запросов в минуту на одного пользователя
GEMINI_RATE_LIMIT_GLOBAL: int = 14      # запросов в минуту суммарно по всем пользователям
RATE_LIMIT_WINDOW_SECONDS: int = 60

# === Кэширование ответов Gemini ===
CACHE_TTL_SECONDS: int = 24 * 60 * 60   # 24 часа

# === Голосовые ответы (edge-tts) ===
TTS_VOICE_MALE: str = "ru-RU-DmitryNeural"
TTS_VOICE_FEMALE: str = "ru-RU-SvetlanaNeural"
TTS_DEFAULT_VOICE: str = TTS_VOICE_MALE
TTS_MIN_LENGTH_FOR_VOICE: int = 300     # озвучиваем ответы длиннее N символов

# === База данных ===
BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
DB_PATH: str = os.getenv("DB_PATH", os.path.join(BASE_DIR, "jurist.db"))

# === Пути к файлам данных и шаблонам ===
DATA_DIR: str = os.path.join(BASE_DIR, "data")
LAWS_JSON_PATH: str = os.path.join(DATA_DIR, "laws.json")
EMERGENCY_CONTACTS_PATH: str = os.path.join(DATA_DIR, "emergency_contacts.json")
DOCUMENT_TYPES_PATH: str = os.path.join(DATA_DIR, "document_types.json")

TEMPLATES_DIR: str = os.path.join(BASE_DIR, "templates")
TEMPLATES_CONFIG_PATH: str = os.path.join(TEMPLATES_DIR, "config.json")

FONTS_DIR: str = os.path.join(BASE_DIR, "fonts")
FONT_PATH: str = os.path.join(FONTS_DIR, "DejaVuSans.ttf")

TMP_DIR: str = os.path.join(BASE_DIR, "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

# === Дисклеймер (HTML-разметка для Telegram) ===
DISCLAIMER: str = (
    "⚖️ <b>JURIST AI</b> — ваш персональный AI-юрист.\n\n"
    "Бот предоставляет юридические консультации и документы на основе "
    "законодательства РФ, но <b>не заменяет</b> профессионального юриста "
    "или адвоката. В сложных и спорных случаях обязательно обратитесь "
    "к квалифицированному специалисту очно.\n\n"
    "Создатель бота не несёт ответственности за юридические последствия "
    "использования предоставленной информации.\n\n"
    "Нажимая «Продолжить», вы подтверждаете, что ознакомились с этим "
    "дисклеймером."
)

# === Лимиты ===
MAX_CONTRACT_TEXT_WORDS: int = 3000
TELEGRAM_MESSAGE_LIMIT: int = 4096  # технический лимит Telegram на 1 сообщение

# === FTS5: сколько статей закона передавать в контекст Gemini ===
LAW_SEARCH_LIMIT: int = 10

# === Шрифт DejaVu (для PDF) ===
DEJAVU_FONT_URL: str = (
    "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf"
)


def validate_api_keys() -> list[str]:
    """Возвращает список предупреждений о незаданных ключах API."""
    warnings: list[str] = []
    if not GEMINI_API_KEY:
        warnings.append("GEMINI_API_KEY не задан — консультации и документы не будут работать.")
    if not GROQ_API_KEY:
        warnings.append("GROQ_API_KEY не задан — голосовые сообщения не будут распознаваться.")
    return warnings
