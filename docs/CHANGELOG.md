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

### Changed
- Рефакторинг провайдеров: единый интерфейс `BaseProvider`
- Рефакторинг web-поиска: фасад `WebSearcher` с авто-выбором бэкенда
- Улучшена обработка ошибок во всех модулях
- Обновлена документация

### Fixed
- Исправлена работа стриминга с Groq API
- Исправлена работа с повреждёнными JSON-файлами истории
- Исправлена работа с YouTube-видео без субтитров

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