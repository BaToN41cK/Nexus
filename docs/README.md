# Nexus — Полное руководство

**Nexus** — это CLI-инструмент на Python, который работает с LLM-провайдерами (Groq, OpenAI, Anthropic, Ollama) для генерации ответов ИИ.
Он умеет загружать контент из URL (веб-страницы, YouTube, PDF, DOCX, PPTX, Excel, txt), выполнять web-поиск и передавать результаты модели как контекст.

> 🔙 Корневой README → [../README.md](../README.md)

## Оглавление

- [Возможности](#возможности)
- [Требования](#требования)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Использование](#использование)
  - [Базовый запрос](#базовый-запрос)
  - [Загрузка контента по URL](#загрузка-контента-по-url)
  - [Web-поиск](#web-поиск)
  - [Интерактивный режим](#интерактивный-режим)
  - [Просмотр истории и статуса](#просмотр-истории-и-статуса)
  - [Управление кэшем](#управление-кэшем)
- [Все команды и флаги](#все-команды-и-флаги)
- [Конфигурация](#конфигурация)
  - [Основные параметры](#основные-параметры)
  - [Web-поиск](#web-поиск-конфигурация)
  - [Поиск .env файла](#поиск-env-файла)
- [Docker](#docker)
- [Международизация (i18n)](#международизация-i18n)
- [ReAct-агент](#react-агент)
- [MCP-сервер](#mcp-сервер)
- [Подключаемая память (Memory)](#подключаемая-память-memory)
- [Структура проекта](#структура-проекта)
- [Зависимости](#зависимости)
- [Troubleshooting](#troubleshooting)
- [Лицензия](#лицензия)

---

## Дополнительная документация

- [INSTALLATION.md](INSTALLATION.md) — подробное руководство по установке на различных платформах
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) — полный справочник конфигурации
- [CLI_REFERENCE.md](CLI_REFERENCE.md) — справочник всех команд и флагов CLI
- [FAQ.md](FAQ.md) — частые вопросы
- [PERFORMANCE.md](PERFORMANCE.md) — тюнинг производительности
- [ADVANCED_USAGE.md](ADVANCED_USAGE.md) — продвинутое использование: кастомные провайдеры, инструменты, пайплайны
- [MIGRATION.md](MIGRATION.md) — миграция между версиями
- [INTEGRATIONS.md](INTEGRATIONS.md) — интеграция с IDE и другими системами
- [ENV_VARS.md](ENV_VARS.md) — полный справочник переменных окружения
- [ROADMAP.md](ROADMAP.md) — дорожная карта проекта
- [GLOSSARY.md](GLOSSARY.md) — глоссарий терминов
- [BEST_PRACTICES.md](BEST_PRACTICES.md) — лучшие практики использования
- [TESTING.md](TESTING.md) — руководство по тестированию
- [DEVELOPMENT.md](DEVELOPMENT.md) — настройка окружения разработчика

---

---

## Возможности

- 💬 **LLM-провайдеры**: Groq (по умолчанию), OpenAI, Anthropic, локальный Ollama
- 🌐 **Web-поиск**: DuckDuckGo (без ключа), Tavily, SearXNG, Bing — через `nexus run "..." --search`
- 📄 **Загрузка контента** по URL: веб-страницы, YouTube, PDF, DOCX, PPTX, Excel, txt
- 🧠 **Контекст диалога**, история запросов, кэширование, стриминг ответов
- 🧩 **ReAct-агент** (Reasoning + Acting) — многошаговое рассуждение с вызовом инструментов
- 🔌 **MCP-сервер** — интеграция с Claude Desktop, Cursor, Continue
- 🧠 **Подключаемая память** — JSON и SQLite бэкенды с FTS5 поиском
- 🌍 **Интернационализация** — интерфейс на русском и английском
- 🐳 **Docker** — запуск в контейнере
- 🎨 **Rich UI**: Markdown, подсветка кода, прогресс-бары, панели

---

## Требования

- **Python 3.9+**
- Доступ к API одного из провайдеров (Groq рекомендуется для быстрого старта)
- Интернет для загрузки URL-контента (YouTube, веб-страницы)

---

## Установка

> **Требования:** Python 3.9+. Скачать можно с [python.org](https://www.python.org/downloads/) (при установке на Windows отметьте «Add Python to PATH»).

### Вариант A. Установка как Python-пакет (рекомендуется для пользователей)

Самый простой способ — одна команда в терминале. `pip` сам установит **все зависимости** (groq, requests, beautifulsoup4, rich, youtube-transcript-api, pypdf, python-docx, python-pptx, openpyxl и т.д.) и **создаст исполняемый файл `nexus` в PATH**. Никаких ручных правок PATH не потребуется.

```bash
# 1) Из PyPI (после публикации проекта)
pip install nexus

# 2) Прямо из GitHub (текущая актуальная версия, те же зависимости)
pip install git+https://github.com/BaToN41cK/Nexus.git
```

Проверить установку:
```bash
nexus version
nexus doctor
```

#### Дополнительные провайдеры

По умолчанию ставится **Groq** (рекомендуемый, бесплатный). Чтобы подключить OpenAI, Anthropic, Ollama или MCP-сервер:

```bash
# Все опциональные зависимости сразу
pip install "nexus[all]"

# Или по отдельности
pip install "nexus[openai]"        # OpenAI: gpt-4o, gpt-4o-mini, ...
pip install "nexus[anthropic]"     # Anthropic: claude-sonnet-4, ...
pip install "nexus[ollama]"        # Локальный Ollama (без облака)
pip install "nexus[mcp]"           # MCP-сервер для Claude Desktop / Cursor
pip install "nexus[interactive]"   # Автодополнение в интерактивном режиме

# Комбинация
pip install "nexus[openai,mcp]"
```

Из GitHub синтаксис тот же:
```bash
pip install "nexus[all] @ git+https://github.com/BaToN41cK/Nexus.git"
```

#### 2) Получить API-ключ

Самый быстрый путь — **Groq** (бесплатно, без карты):

1. Зайдите на [console.groq.com](https://console.groq.com) → **API Keys → Create API Key**
2. Скопируйте ключ вида `gsk_...`

Для других провайдеров:

| Провайдер | Где получить ключ |
|-----------|-------------------|
| OpenAI    | [platform.openai.com](https://platform.openai.com/api-keys) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) |
| Ollama    | не нужен (запускается локально: `ollama serve`) |

#### 3) Сохранить ключ

**Windows (PowerShell / cmd):**
```powershell
mkdir %USERPROFILE%\.nexus
"GROQ_API_KEY=gsk_ваш_ключ" | Out-File -FilePath $env:USERPROFILE\.nexus\.env -Encoding utf8
```

**Linux / macOS (bash / zsh):**
```bash
mkdir -p ~/.nexus
echo "GROQ_API_KEY=gsk_ваш_ключ" > ~/.nexus/.env
```

> 💡 Если у вас уже установлена системная переменная `GROQ_API_KEY` (или `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`), дополнительный файл создавать не нужно — Nexus подхватит её автоматически.

> ℹ️ При первом запуске найденный `.env` копируется в `~/.nexus/.env` для последующего использования.

#### 4) Первый запуск

```bash
# Диагностика окружения (Python, ключи, провайдеры, FTS5)
nexus doctor

# Одиночный запрос
nexus run "Привет! Что такое нейронные сети?"

# Запрос с актуальной информацией из интернета
nexus run "Что нового в Python 3.13?" --search

# Интерактивный диалог со стримингом
nexus interactive
```

**Поддерживаемые провайдеры и переменные окружения:**

| Провайдер | Переменная           | Пример модели                  | API-ключ |
|-----------|----------------------|--------------------------------|----------|
| groq      | `GROQ_API_KEY`       | `llama-3.3-70b-versatile`      | Обязателен |
| openai    | `OPENAI_API_KEY`     | `gpt-4o-mini`                  | Обязателен |
| anthropic | `ANTHROPIC_API_KEY`  | `claude-sonnet-4-20250514`     | Обязателен |
| ollama    | _не требуется_       | `llama3.2` (локально)          | Не нужен |

Переключение провайдера выполняется параметром `provider` в `~/.nexus/config.yaml` (при первом запуске создаётся автоматически из шаблона).

---

### Вариант B. Установка для разработчиков (editable-режим)

Этот вариант — если вы хотите **править код** Nexus, собирать wheel/sdist, запускать тесты:

```bash
# 1) Клонировать репозиторий
git clone https://github.com/BaToN41cK/Nexus.git
cd Nexus

# 2) Создать виртуальное окружение
python -m venv venv
# Windows (PowerShell)
venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate

# 3) Установить в editable-режиме (правки в коде сразу видны)
pip install -e ".[all]"

# 4) (Опционально) Собрать дистрибутив
python -m pip install build
python -m build
```

#### Быстрая установка (скрипты)

В папке `scripts/` лежат автоматические скрипты (venv + установка + добавление в PATH):

**Windows (PowerShell):**
```powershell
.\scripts\install.ps1
```

**Linux / macOS:**
```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

> ⚠️ **Не требуется для обычных пользователей** — скрипты `install.ps1` / `install.sh` нужны только при локальной разработке. После `pip install nexus` Nexus уже доступен глобально.

---

## Быстрый старт

```bash
# Обычный запрос
nexus run "Привет! Что такое нейронные сети?"

# Запрос с актуальной информацией из интернета
nexus run "Что нового в Python 3.13?" --search

# Интерактивный режим
nexus interactive

# Web-поиск
nexus search "последние новости Python"

# Статус системы
nexus status
```

---

## Использование

### Базовый запрос

```bash
nexus run "Привет! Что такое нейронные сети?"
```

Отправляет запрос в LLM и выводит ответ с подсветкой Markdown и кода.

### Загрузка контента по URL

Nexus автоматически определяет тип контента по URL и загружает его как контекст:

```bash
# Веб-страница
nexus run "Кратко опиши https://example.com"

# YouTube-видео (по субтитрам)
nexus run "О чем это видео? https://youtube.com/watch?v=dQw4w9WgXcQ"

# PDF-документ
nexus run "Сделай краткое саммари https://example.com/file.pdf"

# DOCX-документ
nexus run "Выдели ключевые тезисы https://example.com/report.docx"

# PowerPoint-презентация
nexus run "Опиши слайды https://example.com/presentation.pptx"

# Excel-файл
nexus run "Проанализируй данные https://example.com/data.xlsx"

# Локальный файл
nexus run "Прочитай этот файл /path/to/document.txt"
```

**Поддерживаемые форматы:**

| Формат | Библиотека | Описание |
|--------|------------|----------|
| Веб-страницы | `requests` + `beautifulsoup4` | HTML → текст |
| YouTube | `youtube-transcript-api` | Извлечение субтитров |
| PDF | `pypdf` | Извлечение текста со страниц |
| DOCX | `python-docx` | Извлечение абзацев |
| PPTX | `python-pptx` | Извлечение текста со слайдов |
| Excel | `openpyxl` | Извлечение данных с листов |
| TXT/MD/CSV/JSON/XML/YAML | стандартный ввод-вывод | Прямое чтение текста |

### Web-поиск

При включённом поиске Nexus сначала ищет в интернете, загружает top-N страниц и передаёт их содержимое модели как контекст.

```bash
# Одноразовый поиск
nexus run "Что нового в Python 3.13?" --search

# Отключить поиск для конкретного вызова (если он включён глобально)
nexus run "Простой вопрос" --no-search

# Ручной поиск (без LLM)
nexus search "последние новости Python" --max 5

# Поиск + автоматический прогон через LLM
nexus search "лучшие практики FastAPI" --fetch
```

В конце ответа выводится список использованных источников.

### Интерактивный режим

```bash
nexus interactive
```

В интерактивном режиме доступен многотуровый диалог со стримингом ответа.

**Выход из режима:** `exit`, `quit`, `выход` или `Ctrl+C`.

**Команды внутри сессии:**

| Команда | Описание |
|---------|----------|
| `!search on` | Включить web-поиск |
| `!search off` | Выключить web-поиск |
| `!search` / `!search status` | Показать состояние поиска |
| `!lang ru` | Переключить интерфейс на русский |
| `!lang en` | Переключить интерфейс на английский |
| `!lang` / `!lang status` | Показать текущий язык |
| `!help` / `?` | Показать справку |

**Автодополнение:** Если установлена библиотека `prompt_toolkit`, в интерактивном режиме работает автодополнение команд.

### Просмотр истории и статуса

```bash
# Показать историю запросов
nexus history

# Показать статус системы (кэш, история, директории)
nexus status
```

Статус системы показывает:
- Количество и размер файлов в кэше
- Наличие и размер файла истории
- Путь к пользовательской директории `~/.nexus/`

### Управление кэшем

```bash
# Очистить кэш, историю запросов и историю диалога
nexus cache-clear
```

Очищает:
- Кэш ответов (`~/.nexus/cache/`)
- Файл истории (`~/.nexus/history/history.log`)
- Историю диалога (`~/.nexus/conversation.json` или `~/.nexus/memory.db`)

---

## Все команды и флаги

### Глобальные флаги

| Флаг         | Описание                                  |
|--------------|-------------------------------------------|
| `--verbose`  | Включить debug-логирование                |
| `--config`   | Путь к YAML-конфигу (по умолчанию `~/.nexus/config.yaml`) |
| `--lang`     | Язык интерфейса (`ru`, `en`)              |

### Команда `run`

```bash
nexus run "текст запроса" [опции]
```

| Флаг         | Описание                                  |
|--------------|-------------------------------------------|
| `prompt`     | Текст запроса (обязательный позиционный)  |
| `--no-cache` | Не использовать и не сохранять кэш        |
| `--search`   | Включить web-поиск для этого запроса      |
| `--no-search`| Отключить web-поиск (перекрывает конфиг)  |

### Команда `interactive`

```bash
nexus interactive [опции]
```

| Флаг         | Описание                                  |
|--------------|-------------------------------------------|
| `--search`   | Включить web-поиск для каждого хода       |
| `--no-search`| Отключить web-поиск в этой сессии         |

### Команда `search`

```bash
nexus search "запрос" [опции]
```

| Флаг         | Описание                                  |
|--------------|-------------------------------------------|
| `query`      | Поисковый запрос (обязательный)           |
| `--max`      | Максимальное количество результатов (по умолчанию 5) |
| `--fetch`    | Сразу прогоняет результаты через LLM     |

### Команда `history`

```bash
nexus history
```

Показывает историю всех запросов и ответов.

### Команда `cache-clear`

```bash
nexus cache-clear
```

Очищает кэш, историю и диалог.

### Команда `status`

```bash
nexus status
```

Показывает информацию о системе.

### Команда `mcp`

```bash
nexus mcp
```

Запускает MCP-сервер (stdio). Подробнее → [MCP.md](MCP.md).

---

## Конфигурация

### Основные параметры

Основной файл — `config/nexus.yaml`. При первом запуске он копируется в `~/.nexus/config.yaml`, и далее правки можно вносить там.

```yaml
# --- Провайдер ---
provider: "groq"                          # groq | openai | anthropic | ollama
groq_model: "llama-3.3-70b-versatile"    # Модель для выбранного провайдера
base_url: ""                              # Для OpenAI-совместимых API и Ollama

# --- Генерация ---
timeout: 30                               # Таймаут запроса (секунды)
max_tokens: 4096                          # Максимальное количество токенов в ответе
temperature: 0.7                          # Температура сэмплирования (0.0–2.0)

# --- Загрузка контента ---
max_content_length: 50000                 # Макс. длина подгружаемого контента (символов)
summarize_threshold: 40000                # Порог автоматической суммаризации

# --- Кэш ---
cache_ttl: 3600                           # TTL кэша в секундах
max_cache_size_mb: 50                     # Авто-очистка кэша по размеру (MB)
max_retries: 3                            # Количество повторных попыток
rate_limit: 5                             # Лимит запросов

# --- Диалог ---
conversation_history_size: 5              # Сколько прошлых обменов помнить
system_prompt: "Ты — полезный ассистент. Отвечай кратко и по делу."
```

#### Доступные модели по провайдерам

| Провайдер | Модель по умолчанию | Примеры других моделей |
|-----------|---------------------|------------------------|
| groq | `llama-3.3-70b-versatile` | `mixtral-8x7b-32768`, `llama-3.1-8b-instant` |
| openai | `gpt-4o` | `gpt-4o-mini`, `gpt-3.5-turbo` |
| anthropic | `claude-sonnet-4-20250514` | `claude-haiku-3-5`, `claude-opus-4-20250514` |
| ollama | `llama3.2` | `mistral`, `codellama`, `phi3` |

### Web-поиск (конфигурация)

```yaml
web_search:
  enabled: false               # Если true — --search подразумевается у nexus run
  backend: "auto"              # auto | duckduckgo | tavily | searxng | bing
  max_results: 5               # Сколько результатов запрашивать у поисковика
  fetch_top_n: 3               # Сколько top-страниц загрузить как контекст
  timeout: 15                  # Таймаут запросов (секунды)
  cache_enabled: true          # Кэшировать результаты поиска
  cache_ttl: 3600              # TTL кэша поиска (секунды)
  # API-ключи (можно указать здесь или через .env):
  # tavily_api_key: "tvly-..."
  # bing_api_key: "..."
  # searxng_url: "https://searx.be"
```

**Приоритет выбора бэкенда** (при `backend: "auto"`): `tavily → bing → searxng → duckduckgo`.

DuckDuckGo используется как fallback и работает без API-ключа.

#### Переменные окружения для ключей поиска

| Бэкенд     | Переменная       | Описание |
|------------|------------------|----------|
| Tavily     | `TAVILY_API_KEY` | [tavily.com](https://tavily.com) — рекомендуется для LLM |
| Bing       | `BING_API_KEY`   | Azure Bing Web Search |
| SearXNG    | `SEARXNG_URL`    | URL self-hosted или публичного экземпляра |
| DuckDuckGo | _не требуется_   | Работает без ключа |

### Поиск .env файла

Поиск `.env` выполняется в следующем порядке (первый найденный выигрывает):

1. Путь из переменной окружения `NEXUS_ENV_PATH`
2. `~/.nexus/.env`
3. `config/.env` в текущей рабочей директории
4. Поиск `config/.env` вверх по дереву каталогов
5. Переменные окружения `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`

При первом запуске найденный `.env` копируется в `~/.nexus/.env` для последующего использования.

---

## Docker

### Сборка образа

```bash
docker build -f docker/Dockerfile -t nexus .
```

### Запуск в контейнере

```bash
# Передача API-ключа через переменную окружения
docker run --rm -e GROQ_API_KEY=your_key nexus run "Привет!"

# С mount конфига и кэша
docker run --rm \
  -e GROQ_API_KEY=your_key \
  -v ~/.nexus:/root/.nexus \
  nexus run "Что нового в Python?"
```

### Интерактивный режим

```bash
docker run --rm -it -e GROQ_API_KEY=your_key nexus interactive
```

---

## Международизация (i18n)

Nexus поддерживает интерфейс на **русском** и **английском** языках. Язык определяется автоматически по настройкам ОС.

### Автоопределение языка

Порядок определения:
1. Переменная окружения `NEXUS_LANG` (наивысший приоритет)
2. Системная локаль Windows (Win32 API)
3. Переменные `LANG` / `LANGUAGE`
4. Python-модуль `locale`
5. `"en"` (fallback)

### Переключение языка

**Через CLI-флаг:**
```bash
nexus --lang ru run "Привет"
nexus --lang en run "Hello"
```

**В интерактивном режиме:**
```
You: !lang ru    # переключить на русский
You: !lang en    # переключить на английский
You: !lang       # показать текущий язык
```

**Через переменную окружения:**
```bash
export NEXUS_LANG=ru
nexus run "Привет"
```

### Поддерживаемые языки

| Код | Язык |
|-----|------|
| `ru` | Русский |
| `en` | English |

### Добавление нового языка

Создайте файл `nexus/locale/<код>.json` на основе `nexus/locale/en.json` и добавьте код в `_SUPPORTED` в `nexus/core/i18n.py`.

---

## ReAct-агент

Nexus реализует паттерн **ReAct** (Reasoning + Acting) — многошаговое рассуждение с вызовом инструментов.

```python
from nexus.core.agent import NexusAgent
from nexus.core.agent_react import ReActAgent, build_default_tools
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

# Создание агента
agent = NexusAgent(api_key="...", model="llama-3.3-70b-versatile")
searcher = WebSearcher(WebSearchConfig(enabled=True), SEARCH_CACHE_DIR)
tools = build_default_tools(web_searcher=searcher)

# Запуск ReAct-цикла
react = ReActAgent(agent, tools, max_iterations=6)
result = react.run("What's the latest news about Python 3.13?")

print(result.final_answer)
print(f"Took {result.iterations} steps in {result.duration_s:.1f}s")
```

Подробнее → [REACT.md](REACT.md)

---

## MCP-сервер

Nexus может использоваться как инструмент [Model Context Protocol](https://modelcontextprotocol.io/) в клиентах, поддерживающих MCP (Claude Desktop, Cursor, Continue).

```bash
# Установка дополнительной зависимости
pip install mcp

# Запуск MCP-сервера
nexus mcp
```

Подробнее → [MCP.md](MCP.md)

---

## Подключаемая память (Memory)

Nexus хранит историю диалогов в подключаемом хранилище памяти. Доступны два бэкенда:

- **JSON** (`JsonMemoryStore`) — по умолчанию, простой файловый формат
- **SQLite** (`SqliteMemoryStore`) — с полнотекстовым поиском через FTS5

Подробнее → [MEMORY.md](MEMORY.md)

---

## Структура проекта

```
nexus/
├── config/
│   ├── .env.example              # Пример конфигурации API-ключей
│   └── nexus.yaml                # Основной конфигурационный файл
├── docker/
│   └── Dockerfile                # Docker-образ для запуска Nexus
├── docs/
│   ├── LICENSE                   # Лицензия
│   ├── MCP.md                    # Документация MCP-сервера
│   ├── MEMORY.md                 # Документация системы памяти
│   ├── REACT.md                  # Документация ReAct-агента
│   └── README.md                 # Эта документация
├── nexus/
│   ├── __init__.py               # Версия пакета
│   ├── cli.py                    # CLI-интерфейс (argparse)
│   ├── mcp_server.py             # MCP-сервер (stdio)
│   ├── commands/
│   │   ├── __init__.py
│   │   └── run.py                # Команда `run` (стриминг, кэш, история)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── agent.py              # Класс NexusAgent (мульти-провайдер)
│   │   ├── agent_react.py        # ReAct-агент (Reasoning + Acting)
│   │   ├── config.py             # Валидированная конфигурация (NexusConfig)
│   │   ├── content_loader.py     # Загрузка контента из URL
│   │   ├── history.py            # Обратная совместимость с историей диалога
│   │   ├── i18n.py               # Интернационализация (ru/en)
│   │   ├── memory.py             # Подключаемые бэкенды памяти (JSON/SQLite)
│   │   ├── paths.py              # Централизованные пути файловой системы
│   │   ├── providers.py          # Адаптеры провайдеров (groq/openai/anthropic/ollama)
│   │   └── web_search.py         # Web-поиск (DDG/Tavily/SearXNG/Bing)
│   └── locale/
│       ├── en.json               # Английские переводы
│       └── ru.json               # Русские переводы
├── scripts/
│   ├── append_cli.py             # Скрипт добавления CLI-команд
│   ├── install.ps1               # Установка для Windows
│   └── install.sh                # Установка для Linux/macOS
├── tests/
│   ├── test_agent_react.py       # Тесты ReAct-агента
│   ├── test_history.py           # Тесты истории диалога
│   ├── test_mcp_server.py        # Тесты MCP-сервера
│   ├── test_memory.py            # Тесты подключаемой памяти
│   └── test_web_search.py        # Тесты web-поиска
├── .pre-commit-config.yaml       # Pre-commit хуки
├── .gitignore
└── requirements.txt              # Список зависимостей
```

---

## Зависимости

### Основные (устанавливаются автоматически)

| Зависимость | Назначение |
|-------------|------------|
| `groq` | Клиент Groq API |
| `requests` + `beautifulsoup4` | Загрузка веб-страниц |
| `python-dotenv` | Загрузка `.env` |
| `pyyaml` | Чтение YAML-конфигов |
| `rich` | Цветной вывод, Markdown, прогресс-бары |
| `youtube-transcript-api` | Субтитры YouTube |
| `pypdf` | Чтение PDF |
| `python-docx` | Чтение DOCX |
| `python-pptx` | Чтение PPTX |
| `openpyxl` | Чтение Excel |

### Опциональные провайдеры

Раскомментируйте нужные в `requirements.txt`, затем установите вручную:

```bash
pip install openai       # Для OpenAI
pip install anthropic    # Для Anthropic
pip install ollama       # Для Ollama
```

### Опциональные зависимости

```bash
pip install mcp          # Для MCP-сервера (nexus mcp)
pip install prompt_toolkit  # Для автодополнения в интерактивном режиме
```

---

## Troubleshooting

### API ключ не найден

**Симптом:** `❌ API ключ не найден. Проверьте .env файл или переменную окружения.`

**Решение:**
1. Убедитесь, что файл `~/.nexus/.env` существует и содержит корректный API-ключ
2. Или установите переменную окружения: `export GROQ_API_KEY=your_key`
3. Проверьте: `nexus status` покажет путь к директории Nexus

### Ошибка при загрузке веб-страницы

**Симптом:** `[Ошибка загрузки веб-страницы: ...]`

**Решение:**
- Проверьте, доступен ли URL из браузера
- Некоторые сайты блокируют ботов — попробуйте другой URL
- Увеличьте `timeout` в конфиге

### YouTube субтитры не загружаются

**Симптом:** `[Ошибка: youtube-transcript-api не установлен]`

**Решение:**
```bash
pip install youtube-transcript-api
```

**Симптом:** `[Ошибка загрузки YouTube видео: ...]`

**Решение:**
- Убедитесь, что видео доступ公開но и имеет субтитры
- Не все видео имеют субтитры — Nexus может загружать только те, у которых они есть

### PDF/DOCX/PPTX/Excel не загружается

**Симптом:** `[Ошибка: pypdf не установлен]` (или аналогичное)

**Решение:**
```bash
pip install pypdf python-docx python-pptx openpyxl
```

### Web- поиск не работает

**Симптом:** `nexus_search` не возвращает результатов

**Решение:**
1. Убедитесь, что web-поиск включён в конфиге:
   ```yaml
   web_search:
     enabled: true
   ```
2. Проверьте, что бэкенд доступен:
   ```bash
   nexus search "тест" --max 1
   ```
3. Если используете `auto`, DuckDuckGo будет использован как fallback (не требует ключа)

### Groq API ошибка / Таймаут

**Симптом:** `[Ошибка: таймаут запроса к Groq API]` или `[Ошибка: превышен лимит запросов к Groq API]`

**Решение:**
1. Увеличьте `timeout` в конфиге (по умолчанию 30 секунд)
2. Проверьте, не превышен ли лимит запросов на вашем тарифе Groq
3. Попробуйте другую модель (меньшие модели обычно быстрее)

### Конфигурация повреждена

**Симптом:** `Invalid configuration: ...`

**Решение:**
1. Удалите `~/.nexus/config.yaml` — он будет пересоздан с дефолтами
2. Или исправьте YAML-синтаксис вручную

### Ollama не подключается

**Симптом:** `[Ошибка Ollama: ...]`

**Решение:**
1. Убедитесь, что Ollama запущен: `ollama serve`
2. Проверьте `base_url` в конфиге (по умолчанию `http://localhost:11434`)
3. Убедитесь, что модель загружена: `ollama pull llama3.2`

### MCP-сервер не запускается

**Симптом:** `The 'mcp' package is required to run the Nexus MCP server.`

**Решение:**
```bash
pip install mcp
```

### Интерфейс на неправильном языке

**Решение:**
```bash
nexus --lang ru run "Привет"   # Принудительно на русском
nexus --lang en run "Hello"    # Принудительно на английском
```

### Очистка всех данных Nexus

```bash
nexus cache-clear
# Или вручную:
rm -rf ~/.nexus/
```

---

## Лицензия

См. файл [LICENSE](LICENSE).