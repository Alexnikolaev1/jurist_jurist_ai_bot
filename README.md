# ⚖️ JURIST AI — персональный AI-юрист в Telegram

Бот заменяет дорогостоящие юридические консультации: отвечает на вопросы
по законодательству РФ, составляет претензии / иски / жалобы, проверяет
договоры по фото и выдаёт экстренный протокол при задержании.

---

## Возможности

| Функция | Описание |
|---|---|
| ⚖️ Консультация | Текст или голос → поиск по FTS5-базе законов → ответ Gemini со ссылками на статьи |
| 📄 Документ | Пошаговый сбор данных → заполнение шаблона → текст + PDF |
| 🔍 Проверка договора | Фото → OCR Gemini Vision → анализ рисков |
| 🆘 Экстренно | Протокол при задержании, обыске, допросе + контакты бесплатной юрпомощи |
| 📋 История | Последние 10 консультаций |
| ⚙️ Настройки | ФИО, адрес, телефон для автоподстановки в документы |

---

## Стек

- **Python 3.11+**, **aiogram 3.x** (асинхронный, вебхук/поллинг)
- **Google Gemini 1.5 Flash** — консультации, OCR, генерация документов
- **Groq Whisper Large v3** — транскрибация голоса
- **Microsoft Edge TTS** — озвучка длинных ответов
- **SQLite + FTS5** — хранилище пользователей, история, кэш, полнотекстовый поиск по законам
- **ReportLab** — генерация PDF с кириллицей
- Хостинг: **Railway** (бесплатный тир)

---

## Быстрый старт (локально)

```bash
git clone <repo>
cd jurist_bot

# Создаём виртуальное окружение
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Устанавливаем зависимости
pip install -r requirements.txt

# Настраиваем переменные окружения
cp .env.example .env
# Отредактируйте .env: вставьте токены

# Запускаем (режим polling — вебхук не нужен)
python bot.py
```

---

## Переменные окружения

| Переменная | Описание | Где получить |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота | @BotFather в Telegram |
| `GEMINI_API_KEY` | Ключ Google AI Studio | [aistudio.google.com](https://aistudio.google.com) |
| `GROQ_API_KEY` | Ключ Groq (Whisper) | [console.groq.com](https://console.groq.com) |
| `WEBHOOK_URL` | URL вебхука (Railway автовыставляет через RAILWAY_PUBLIC_DOMAIN) | Автоматически на Railway |
| `PORT` | Порт HTTP-сервера (Railway выставляет сам) | По умолчанию 8000 |
| `DB_PATH` | Путь к SQLite-файлу | По умолчанию `jurist.db` в корне |

---

## Деплой на Railway

1. Зарегистрируйтесь на [railway.app](https://railway.app)
2. Создайте новый проект → **Deploy from GitHub repo** (или загрузите ZIP)
3. В разделе **Variables** добавьте:
   - `TELEGRAM_BOT_TOKEN`
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
4. Railway автоматически подхватит `Procfile` (`web: python bot.py`) и запустит бота
5. После деплоя Railway покажет публичный домен — вебхук установится автоматически

> ⚠️ На бесплатном тире Railway диск **эфемерный** — база jurist.db сбрасывается при редеплое.
> Для продакшена подключите Railway Postgres или Volume (persistent disk).

---

## Расширение базы законов

Файл `data/laws.json` содержит массив объектов:

```json
{
  "codex": "ГК РФ",
  "article_number": "450",
  "article_title": "Основания изменения и расторжения договора",
  "article_text": "Полный текст статьи..."
}
```

Добавляйте статьи по тем отраслям права, которые актуальны для вашей аудитории.
При следующем запуске бота (пока таблица `laws` пуста) они автоматически
импортируются в FTS5-индекс.

---

## Структура проекта

```
jurist_bot/
├── bot.py                  # Точка входа, вебхук/поллинг
├── config.py               # Переменные окружения и константы
├── database.py             # SQLite + FTS5, async-хелперы
├── keyboards.py            # Клавиатуры (reply и inline)
├── states.py               # FSM-состояния (документы, настройки)
├── requirements.txt
├── Procfile
├── handlers/
│   ├── start.py            # /start, дисклеймер
│   ├── consult.py          # Консультация (текст + голос)
│   ├── document.py         # Генерация документов
│   ├── contract.py         # Проверка договора по фото
│   ├── emergency.py        # Экстренный протокол
│   ├── history.py          # История + удаление данных
│   └── settings.py         # Личный кабинет
├── services/
│   ├── gemini_service.py   # Google Gemini API
│   ├── groq_service.py     # Groq Whisper транскрибация
│   ├── law_search.py       # FTS5-поиск по законам
│   ├── pdf_service.py      # ReportLab PDF
│   └── tts_service.py      # Edge TTS озвучка
├── utils/
│   ├── rate_limiter.py     # Rate limiter для Gemini
│   └── text_utils.py       # Хелперы: ключевые слова, FTS5-запрос, хэш
├── data/
│   ├── laws.json           # База статей закона
│   ├── emergency_contacts.json
│   └── document_types.json
├── templates/              # Шаблоны документов
│   ├── config.json
│   ├── pretension.txt
│   ├── claim.txt
│   ├── complaint_prosecutor.txt
│   ├── complaint_rospotrebnadzor.txt
│   ├── labor_complaint.txt
│   └── agreement.txt
└── fonts/
    └── DejaVuSans.ttf      # Шрифт с кириллицей для PDF
```

---

## Лицензия

MIT — используйте и адаптируйте свободно.

> **Дисклеймер:** бот предоставляет информацию на основе законодательства РФ
> и не заменяет профессионального юриста. В сложных случаях обращайтесь
> к квалифицированному специалисту очно.
