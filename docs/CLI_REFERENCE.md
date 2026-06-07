# Справочник CLI

> 🔙 Назад → [README.md](README.md)

Полный справочник всех команд и флагов CLI Nexus.

## Оглавление

- [Общие флаги](#общие-флаги)
- [Команда run](#команда-run)
- [Команда interactive](#команда-interactive)
- [Команда search](#команда-search)
- [Команда history](#команда-history)
- [Команда cache-clear](#команда-cache-clear)
- [Команда status](#команда-status)
- [Команда update](#команда-update)
- [Команда test](#команда-test)
- [Команда debug](#команда-debug)
- [Команда version](#команда-version)
- [Команда mcp](#команда-mcp)
- [Команды интерактивного режима](#команды-интерактивного-режима)
- [Переменные окружения CLI](#переменные-окружения-cli)
- [Примеры использования](#примеры-использования)

---

## Общие флаги

Эти флаги работают со всеми командами и указываются **перед** именем команды:

```bash
nexus [ОБЩИЕ ФЛАГИ] КОМАНДА [АРГУМЕНТЫ]
```

| Флаг | Описание | Пример |
|------|----------|--------|
| `--verbose` | Включить debug-логирование | `nexus --verbose run "тест"` |
| `--config PATH` | Путь к YAML-конфигу | `nexus --config ./my_config.yaml run "тест"` |
| `--lang LANG` | Язык интерфейса (`ru`, `en`) | `nexus --lang en run "Hello"` |
| `-h, --help` | Показать справку | `nexus --help` |

---

## Команда `run`

Основная команда для отправки запроса в LLM.

```bash
nexus run "текст запроса" [ОПЦИИ]
```

### Опции

| Флаг | Тип | Описание |
|------|-----|----------|
| `prompt` | позиционный | Текст запроса (обязательный) |
| `--no-cache` | флаг | Не использовать и не сохранять кэш |
| `--search` | флаг | Включить web-поиск для этого запроса |
| `--no-search` | флаг | Отключить web-поиск (перекрывает конфиг) |

### Примеры

```bash
# Базовый запрос
nexus run "Привет! Что такое нейронные сети?"

# Запрос с web-поиском
nexus run "Что нового в Python 3.13?" --search

# Запрос без кэша
nexus run "Уникальный вопрос" --no-cache

# Запрос с отключённым поиском (если он включён глобально)
nexus run "Простой вопрос" --no-search
```

### Поведение

1. Загружает конфигурацию из `config.yaml`
2. Загружает API-ключ из `.env`
3. Извлекает URL из промпта и загружает контент
4. Проверяет кэш (если `--no-cache` — пропускает)
5. Строит контекст из истории диалога
6. Отправляет запрос в LLM
7. Стримит и рендерит ответ (Markdown, код)
8. Сохраняет в кэш и историю

---

## Команда `interactive`

Запуск интерактивного диалога со стримингом ответов.

```bash
nexus interactive [ОПЦИИ]
```

### Опции

| Флаг | Описание |
|------|----------|
| `--search` | Включить web-поиск для каждого хода |
| `--no-search` | Отключить web-поиск в этой сессии |

### Примеры

```bash
# Интерактивный диалог
nexus interactive

# С включённым поиском
nexus interactive --search

# Без поиска
nexus interactive --no-search
```

### Управление сессией

- **Выход:** `exit`, `quit`, `выход` или `Ctrl+C`
- **Автодополнение:** Если установлена `prompt_toolkit`, работают автодополнение команд

### Команды внутри сессии

См. раздел [Команды интерактивного режима](#команды-интерактивного-режима) ниже.

---

## Команда `search`

Web-поиск без LLM (или с прогоном через LLM).

```bash
nexus search "запрос" [ОПЦИИ]
```

### Опции

| Флаг | Тип | Описание |
|------|-----|----------|
| `query` | позиционный | Поисковый запрос (обязательный) |
| `--max N` | integer | Максимальное количество результатов (по умолчанию 5) |
| `--fetch` | флаг | Прогнать результаты поиска через LLM |

### Примеры

```bash
# Простой поиск
nexus search "последние новости Python"

# Поиск с ограничением результатов
nexus search "лучшие практики FastAPI" --max 10

# Поиск + анализ через LLM
nexus search "сравнение React и Vue.js" --fetch
```

### Формат вывода

```
[1] Заголовок страницы
    URL: https://example.com/page
    Описание: Краткое описание страницы...

[2] Заголовок страницы 2
    URL: https://example.com/page2
    Описание: Краткое описание страницы 2...
```

---

## Команда `history`

Показать историю всех запросов и ответов.

```bash
nexus history
```

### Пример вывода

```
📝 История запросов:

[2024-01-15 14:30:22] Привет! Что такое нейронные сети?
  → Нейронные сети — это...

[2024-01-15 14:35:11] Что нового в Python 3.13?
  → Python 3.13 включает...

Всего: 2 запроса
```

---

## Команда `cache-clear`

Очистить кэш, историю запросов и историю диалога.

```bash
nexus cache-clear
```

### Что очищается

| Что | Путь | Описание |
|-----|------|----------|
| Кэш ответов | `~/.nexus/cache/` | Файлы с закэшированными ответами LLM |
| История запросов | `~/.nexus/history/history.log` | Лог всех запросов и ответов |
| История диалога (JSON) | `~/.nexus/conversation.json` | Диалог в формате JSON |
| История диалога (SQLite) | `~/.nexus/memory.db` | Диалог в формате SQLite |

---

## Команда `status`

Показать информацию о системе.

```bash
nexus status
```

### Пример вывода

```
📊 Статус Nexus:

Директория: ~/.nexus/
Конфиг: ~/.nexus/config.yaml
API-ключ: GROQ_API_KEY ✓
Провайдер: groq
Модель: llama-3.3-70b-versatile

Кэш:
  Файлов: 12
  Размер: 2.3 MB

История:
  Файл: ~/.nexus/history/history.log
  Записей: 45

Web-поиск:
  Бэкенд: duckduckgo
  Включён: нет
```

---

## Команда `update`

Обновление Nexus до последней версии через pip.

```bash
nexus update
```

### Пример вывода

```
Nexus Update — current v1.0.0

Updating Nexus from PyPI...

✅ Update completed successfully!
  Successfully installed nexus-x.x.x
```

---

## Команда `test`

Запуск встроенных тестов для проверки работоспособности всех модулей.

```bash
nexus test
```

### Что проверяется

| Модуль | Описание |
|--------|----------|
| Configuration | Загрузка конфигурации |
| Agent | Инициализация агента |
| History | Система истории |
| i18n | Интернационализация |
| Paths | Пути и директории |
| Banners | ASCII-баннеры |
| Logo | Логотип |
| Web Search | Веб-поиск |
| Run Command | Основная команда |
| SQLite FTS5 | Полнотекстовый поиск |
| Translations | Система переводов |
| Web Search Config | Конфигурация поиска |

### Пример вывода

```
Nexus Test — v1.0.0

  ✅ Configuration        (nexus.core.config)  2ms
  ✅ Agent                (nexus.core.agent)   5ms
  ✅ History              (nexus.core.history)  1ms
  ✅ i18n                 (nexus.core.i18n)     1ms
  ✅ Paths                (nexus.core.paths)    0ms
  ✅ Banners              (nexus.core.banners)  0ms
  ✅ Logo                 (nexus.core.logo)     0ms
  ✅ Web Search           (nexus.core.web_search) 3ms
  ✅ Run Command          (nexus.commands.run)  1ms
  ✅ SQLite FTS5          1ms
  ✅ Translations         0ms
  ✅ Web Search Config    1ms

Result: 12/12 checks passed
```

---

## Команда `debug`

Режим глубокой отладки с дампом всех запросов/ответов и полной диагностикой.

```bash
nexus debug
```

### Что выводится

| Раздел | Описание |
|--------|----------|
| System | Версия Python, платформа, версия Nexus |
| Configuration | Все параметры конфига (API-ключи маскируются) |
| API Keys | Состояние переменных окружения (маскировано) |
| Providers | Установленные SDK провайдеров и их версии |
| Dependencies | Установленные зависимости и их версии |
| SQLite FTS5 | Наличие полнотекстового поиска |

### Пример вывода

```
Nexus Debug — v1.0.0

System
  Python: 3.11.5 (/usr/bin/python3)
  Platform: linux
  Nexus: v1.0.0

Configuration
  ✅ Config loaded
    provider: groq
    groq_model: llama-3.3-70b-versatile
    ...

API Keys (masked)
  ✅ groq: GROQ_API_KEY = gsk_****abc1
  ⚠️  openai: OPENAI_API_KEY not set
  ✅ ollama: no key needed

Providers
  ✅ groq: SDK installed (groq 0.x.x)
  ⚠️  openai: SDK not installed
  ...

Dependencies
  ✅ requests: 2.x.x
  ✅ beautifulsoup4: 4.x.x
  ...
```

---

## Команда `version`

Показать версию Nexus.

```bash
nexus version
```

### Пример вывода

```
Nexus v1.0.0
Python 3.11.5
```

---

## Команда `mcp`

Запуск MCP-сервера (stdio).

```bash
nexus mcp
```

> ⚠️ Требует установленного пакета `mcp`: `pip install mcp`

Сервер работает в режиме stdio и не принимает сетевые подключения. Для работы с ним нужен MCP-клиент (Claude Desktop, Cursor, Continue).

Подробнее → [MCP.md](MCP.md)

---

## Команды интерактивного режима

Внутри сессии `nexus interactive` доступны специальные команды (начинаются с `!`):

| Команда | Описание | Пример |
|---------|----------|--------|
| `!search on` | Включить web-поиск | `!search on` |
| `!search off` | Выключить web-поиск | `!search off` |
| `!search` | Показать состояние поиска | `!search` |
| `!search status` | Показать состояние поиска | `!search status` |
| `!lang ru` | Переключить на русский | `!lang ru` |
| `!lang en` | Переключить на английский | `!lang en` |
| `!lang` | Показать текущий язык | `!lang` |
| `!lang status` | Показать текущий язык | `!lang status` |
| `!help` | Показать справку | `!help` |
| `?` | Показать справку | `?` |
| `exit` | Выйти из режима | `exit` |
| `quit` | Выйти из режима | `quit` |
| `выход` | Выйти из режима | `выход` |

### Пример сессии

```
You: Привет!
Nexus: Здравствуйте! Чем могу помочь?

You: !search on
🔍 Web-поиск: включён

You: Расскажи о последних новостях Python
Nexus: [ищет в интернете...]
Python 3.13 был выпущен с множеством новых функций...

You: !lang en
🌐 Language: English

You: Hello!
Nexus: Hello! How can I help you?

You: exit
До свидания!
```

---

## Переменные окружения CLI

| Переменная | Описание | Пример |
|------------|----------|--------|
| `NEXUS_LANG` | Язык интерфейса | `export NEXUS_LANG=ru` |
| `NEXUS_ENV_PATH` | Путь к файлу `.env` | `export NEXUS_ENV_PATH=/path/to/.env` |
| `NEXUS_CONFIG` | Путь к конфигу | `export NEXUS_CONFIG=/path/to/config.yaml` |
| `NO_COLOR` | Отключить цвета в выводе | `export NO_COLOR=1` |

---

## Примеры использования

### Базовые

```bash
# Простой запрос
nexus run "Что такое нейронные сети?"

# Запрос на английском
nexus run "What is machine learning?"

# Интерактивный режим
nexus interactive
```

### С web-поиском

```bash
# Запрос с поиском
nexus run "Что нового в Python 3.13?" --search

# Ручной поиск
nexus search "последние новости AI"

# Поиск + LLM анализ
nexus search "лучшие практики Docker" --fetch
```

### Управление кэшем

```bash
# Запрос без кэша
nexus run "Уникальный вопрос" --no-cache

# Очистить кэш
nexus cache-clear

# Проверить статус кэша
nexus status
```

### Язык

```bash
# Русский интерфейс
nexus --lang ru run "Привет"

# Английский интерфейс
nexus --lang en run "Hello"

# Автоопределение (по умолчанию)
nexus run "Привет"
```

### Диагностика

```bash
# Глубокая отладка
nexus debug

# Показать версию
nexus version

# Показать статус
nexus status

# Показать историю
nexus history

# Обновить Nexus
nexus update

# Запустить тесты модулей
nexus test
```

### С произвольным конфигом

```bash
# Использовать другой конфиг
nexus --config ./production.yaml run "тест"

# Использовать другой конфиг + поиск
nexus --config ./production.yaml run "тест" --search
```

---

## См. также

- [README.md](README.md) — общее руководство
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) — справочник конфигурации
- [INSTALLATION.md](INSTALLATION.md) — установка Nexus