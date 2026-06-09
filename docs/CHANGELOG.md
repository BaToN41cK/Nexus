# История изменений

> 🔙 Назад → [README.md](README.md)

Формат: [Keep a Changelog](https://keepachangelog.com/)

---

## [Unreleased]

### Added
- MCP-сервер (`nexus mcp`) для интеграции с Claude Desktop, Cursor, Continue
- ReAct-агент (`nexus.core.agent_react`) — многошаговое рассуждение с инструментами
- Подключаемая память (`nexus.core.memory`) — JSON и SQLite бэкенды
- Интернационализация (i18n) — интерфейс на русском и английском языках
- SQLite-хранилище с полнотекстовым поиском (FTS5)
- Фабрика `create_memory_store()` для создания хранилищ по имени
- Фабрика `create_provider()` для создания LLM-провайдеров
- Web-поиск: DuckDuckGo, Tavily, SearXNG, Bing
- Загрузка контента: YouTube, PDF, DOCX, PPTX, Excel
- Кэширование ответов с TTL и автоочисткой
- Кэширование результатов web-поиска
- Docker-образ для запуска в контейнере
- Pre-commit хуки для автоматической проверки кода
- Тесты для всех основных модулей
- **Инструменты DX:** `Makefile` с 11 целями (`make help/test/lint/format/typecheck/cov/build/...`)
- **CI:** workflows для `mypy` (`.github/workflows/mypy.yml`) и автообновлений `Dependabot` (`.github/dependabot.yml`)
- **Quality config:** секции `[tool.ruff]` (linter + formatter) и `[tool.mypy]` (type-checker) в `pyproject.toml`
- **Документация:** [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — 10 самых частых ошибок и их решения
- **CLI:** флаг `--version` (`nexus --version` без подкоманды)
- **Тесты:** маркер `slow` и опция `-ra` (показ всех причин skip/xfail) в pytest

### Changed
- Рефакторинг провайдеров: единый интерфейс `BaseProvider`
- Рефакторинг web-поиска: фасад `WebSearcher` с авто-выбором бэкенда
- Улучшена обработка ошибок во всех модулях
- Обновлена документация
- **`nexus/commands/run.py`:** константы путей (`NEXUS_DIR`, `CACHE_DIR`, и т.д.) теперь импортируются из `nexus.core.paths` вместо дубля
- **`nexus/core/security.py`:** функция `mask_api_key` приведена к PEP8 (убраны лишние пробелы)

### Fixed
- Исправлена работа стриминга с Groq API
- Исправлена работа с повреждёнными JSON-файлами истории
- Исправлена работа с YouTube-видео без субтитров
- **`README.md`:** исправлена опечатка в примере конфига OpenAI (`groq_model` → `openai_model`)
- **`nexus/cli.py`:** `SensitiveDataFilter` теперь устанавливается **после** `_setup_logging()`, а не до (мог теряться при `basicConfig`)
- **`nexus/commands/run.py`:** убран побочный эффект `os.makedirs(...)` на уровне модуля (заменён на вызов `ensure_dirs()` из `paths.py`)

---

## [1.0.0] - 2024-XX-XX

### Added
- Базовый CLI с командами `run`, `interactive`, `search`, `history`, `status`, `cache-clear`
- LLM-провайдеры: Groq, OpenAI, Anthropic, Ollama
- Web-поиск: DuckDuckGo, Tavily, SearXNG, Bing
- Загрузка контента: веб-страницы, YouTube, PDF, DOCX, PPTX, Excel
- Кэширование ответов
- История запросов
- Контекст диалога
- Rich UI: Markdown, подсветка кода, прогресс-бары
- Конфигурация через YAML
- Автоматический поиск .env файла