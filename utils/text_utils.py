# -*- coding: utf-8 -*-
"""
text_utils.py — вспомогательные функции для очистки текста, хэширования
и подготовки поисковых запросов FTS5.
"""
import hashlib
import re

import config

# Базовый список русских стоп-слов — не несут смысловой нагрузки для поиска
# по статьям закона, их выкидываем из FTS5-запроса.
_STOPWORDS = {
    "я", "ты", "он", "она", "оно", "мы", "вы", "они", "это", "этот", "эта", "эти",
    "и", "а", "но", "или", "да", "нет", "не", "ни", "же", "ли", "бы", "то", "так",
    "как", "что", "чтобы", "когда", "где", "куда", "откуда", "почему", "зачем",
    "в", "во", "на", "с", "со", "к", "ко", "от", "до", "из", "у", "о", "об",
    "по", "за", "под", "над", "при", "для", "без", "через", "между",
    "был", "была", "было", "были", "есть", "буду", "будет", "будут",
    "мне", "меня", "мой", "моя", "моё", "мои", "его", "её", "их", "нас", "вас",
    "сегодня", "вчера", "завтра", "очень", "просто", "можно", "нужно", "надо",
}

# Telegram MarkdownV2/HTML — экранируем потенциально проблемные символы FTS5.
_FTS_SPECIAL_CHARS = re.compile(r'["\*\^\(\)]')


def clean_text(text: str) -> str:
    """Убирает лишние пробелы/переносы строк."""
    return re.sub(r"\s+", " ", text or "").strip()


def hash_text(text: str) -> str:
    """SHA-256 хэш для ключей кэша Gemini-запросов."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """
    Извлекает значимые слова из запроса пользователя для построения
    FTS5 MATCH-запроса. Простая эвристика без NLP-библиотек (чтобы не
    тянуть тяжёлые зависимости на бесплатном Railway).
    """
    text = clean_text(text).lower()
    words = re.findall(r"[а-яёa-z0-9]+", text)
    keywords = [w for w in words if len(w) > 2 and w not in _STOPWORDS]
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    unique_keywords = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique_keywords.append(w)
    return unique_keywords[:max_keywords]


def build_fts_query(text: str) -> str:
    """
    Строит безопасный запрос для FTS5 MATCH из произвольного текста
    пользователя: ключевые слова с подстановочным знаком (префиксный поиск)
    через OR, чтобы найти статьи хотя бы по части совпадений.
    """
    keywords = extract_keywords(text)
    if not keywords:
        return ""
    # Экранируем спецсимволы FTS5 и добавляем '*' для префиксного поиска.
    safe_keywords = [_FTS_SPECIAL_CHARS.sub("", w) + "*" for w in keywords if w]
    return " OR ".join(safe_keywords)


def split_long_message(text: str, limit: int = config.TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """
    Разбивает длинный текст на части не длиннее лимита Telegram,
    стараясь резать по границам абзацев/предложений, а не посередине слова.
    """
    if len(text) <= limit:
        return [text]

    parts = []
    remaining = text
    while len(remaining) > limit:
        # Ищем ближайший перенос строки или точку перед лимитом
        cut = remaining.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = remaining.rfind(". ", 0, limit)
        if cut == -1:
            cut = limit
        else:
            cut += 1  # включаем разделитель в текущую часть
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def detect_emergency_keywords(text: str) -> bool:
    """Грубая проверка на экстренную ситуацию (задержание, допрос и т.п.)."""
    triggers = [
        "задержал", "задержали", "задержание", "полиция приехала",
        "вызывают на допрос", "повестка", "угрожают", "арестовали",
        "арест", "обыск", "задержан", "забрали в отдел", "увезли в полицию",
    ]
    lowered = text.lower()
    return any(trigger in lowered for trigger in triggers)
