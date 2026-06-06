# Nexus — ИИ-ассистент

> 📖 Полная документация → [docs/README.md](docs/README.md)

**Nexus** — это Python-CLI, который общается с LLM (Groq, OpenAI, Anthropic, Ollama) и умеет подмешивать в ответ **актуальную информацию из интернета** через встроенный web-поиск.

## Возможности

- 💬 **LLM-провайдеры**: Groq (по умолчанию), OpenAI, Anthropic, локальный Ollama
- 🌐 **Web-поиск**: DuckDuckGo (без ключа), Tavily, SearXNG, Bing — через `nexus run "..." --search`
- 📄 **Загрузка контента** по URL: веб-страницы, YouTube, PDF, DOCX, PPTX, Excel, txt
- 🧠 **Контекст диалога**, история запросов, кэширование, стриминг ответов
- 🎨 **Rich UI**: Markdown, подсветка кода, прогресс-бары, панели

## Быстрый старт

```bash
# Установка
pip install -e .
cp config/.env.example config/.env
# отредактируйте config/.env и вставьте GROQ_API_KEY

# Обычный запрос
nexus run "Привет! Что такое нейронные сети?"

# Запрос с актуальной информацией из интернета
nexus run "Что нового в Python 3.13?" --search

# Интерактивный режим
nexus interactive
```

## Документация

- [docs/README.md](docs/README.md) — полное руководство (установка, конфигурация, все команды, troubleshooting)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — архитектура проекта, диаграммы, паттерны проектирования
- [docs/EXAMPLES.md](docs/EXAMPLES.md) — реальные примеры использования (CLI, Python API, интеграция)
- [docs/MCP.md](docs/MCP.md) — MCP-сервер (интеграция с Claude Desktop, Cursor, Continue)
- [docs/MEMORY.md](docs/MEMORY.md) — подключаемая память (JSON/SQLite бэкенды)
- [docs/REACT.md](docs/REACT.md) — ReAct-агент (многошаговое рассуждение с инструментами)
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — участие в разработке
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — история изменений
- [docs/SECURITY.md](docs/SECURITY.md) — политика безопасности
