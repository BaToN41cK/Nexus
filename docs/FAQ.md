# Частые вопросы (FAQ)

> 🔙 Назад → [README.md](README.md)

Ответы на часто задаваемые вопросы о Nexus.

## Оглавление

- [Общие вопросы](#общие-вопросы)
- [Установка](#установка)
- [Конфигурация](#конфигурация)
- [Провайдеры и модели](#провайдеры-и-модели)
- [Web-поиск](#web-поиск)
- [Кэширование](#кэширование)
- [Память и история](#память-и-история)
- [MCP-сервер](#mcp-сервер)
- [ReAct-агент](#react-агент)
- [Производительность](#производительность)
- [Безопасность](#безопасность)
- [Ошибки](#ошибки)

---

## Общие вопросы

### Что такое Nexus?

Nexus — это CLI-инструмент на Python, который работает с LLM-провайдерами (Groq, OpenAI, Anthropic, Ollama) для генерации ответов ИИ. Он умеет загружать контент из URL, выполнять web-поиск и передавать результаты модели как контекст.

### Nexus бесплатный?

Да, Nexus — это бесплатный инструмент с открытым исходным кодом (лицензия MIT). Однако для работы с LLM-провайдерами необходим API-ключ, который может быть платным (зависит от провайдера).

### Какие провайдеры поддерживаются?

- **Groq** (рекомендуется, бесплатный)
- **OpenAI** (GPT-4o, GPT-4o-mini, и т.д.)
- **Anthropic** (Claude)
- **Ollama** (локальные модели, бесплатно)

### Какие форматы контента поддерживаются?

- Веб-страницы (HTML)
- YouTube (субтитры)
- PDF
- DOCX (Word)
- PPTX (PowerShell)
- Excel (XLSX)
- TXT/MD/CSV/JSON/XML/YAML

### Можно ли использовать Nexus без интернета?

Только с локальным Ollama. Все остальные провайдеры требуют доступа к интернету.

---

## Установка

### Какую версию Python нужно?

Python 3.9 или новее. Рекомендуется Python 3.11+.

### Как обновить Nexus?

```bash
pip install --upgrade nexus
```

### Как удалить Nexus?

```bash
pip uninstall nexus
```

Для удаления данных:
```bash
nexus cache-clear
rm -rf ~/.nexus/
```

### `nexus: command not found`

1. Убедитесь, что Python установлен и добавлен в PATH
2. Попробуйте: `python -m nexus`
3. Проверьте, что `pip` установлен в то же окружение

### Можно ли установить Nexus в виртуальное окружение?

Да, рекомендуется:
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
pip install nexus
```

---

## Конфигурация

### Где находится конфиг?

- Шаблон: `config/nexus.yaml` (в репозитории)
- Пользовательский: `~/.nexus/config.yaml`

### Как сбросить конфиг?

```bash
rm ~/.nexus/config.yaml
# Будет пересоздан при следующем запуске
```

### Как узнать текущие настройки?

```bash
nexus status
cat ~/.nexus/config.yaml
```

### Можно ли использовать несколько конфигов?

Да:
```bash
nexus --config ./production.yaml run "тест"
nexus --config ./development.yaml run "тест"
```

---

## Провайдеры и модели

### Какой провайдер выбрать?

| Провайдер | Лучше всего для | Стоимость |
|-----------|-----------------|-----------|
| Groq | Быстрый старт, тестирование | Бесплатно |
| Openai | Качество ответов | Платно |
| Anthropic | Длинные контексты | Платно |
| Ollama | Приватность, оффлайн | Бесплатно |

### Как переключить провайдера?

Измените `provider` в `~/.nexus/config.yaml`:
```yaml
provider: "openai"
```

### Какую модель выбрать?

| Задача | Рекомендуемая модель |
|--------|---------------------|
| Общий диалог | `llama-3.3-70b-versatile` (Groq) |
| Код | `codellama` (Ollama) или `gpt-4o` (OpenAI) |
| Длинные тексты | `claude-sonnet-4-20250514` (Anthropic) |
| Быстрые ответы | `llama-3.1-8b-instant` (Groq) |

### Можно ли использовать кастомный API?

Да, через `base_url` в конфиге:
```yaml
base_url: "http://localhost:8000/v1"
```

---

## Web-поиск

### Как включить web-поиск?

В конфиге:
```yaml
web_search:
  enabled: true
```

Или для конкретного запроса:
```bash
nexus run "Вопрос" --search
```

### Какой бэкенд поиска выбрать?

| Бэкенд | API-ключ нужен? | Качество |
|--------|-----------------|----------|
| DuckDuckGo | Нет | Среднее |
| Tavily | Да | Высокое |
| Bing | Да | Высокое |
| SearXNG | Зависит от экземпляра | Среднее |

### Поиск не возвращает результатов

1. Проверьте, включён ли поиск: `nexus search "тест" --max 1`
2. Попробуйте другой бэкенд: `web_search.backend: "duckduckgo"`
3. Проверьте интернет-соединение

---

## Кэширование

### Как работает кэш?

Nexus кэширует ответы LLM на основе хеша промпта. При повторном запросе с тем же промптом возвращается закэшированный ответ.

### Как отключить кэш?

Для конкретного запроса:
```bash
nexus run "Вопрос" --no-cache
```

### Как очистить кэш?

```bash
nexus cache-clear
```

### Где хранится кэш?

`~/.nexus/cache/`

### Как настроить TTL кэша?

В конфиге:
```yaml
cache_ttl: 3600  # 1 час
```

---

## Память и история

### Где хранится история?

- Лог: `~/.nexus/history/history.log`
- Диалог (JSON): `~/.nexus/conversation.json`
- Диалог (SQLite): `~/.nexus/memory.db`

### Как переключиться на SQLite?

```python
from nexus.core.history import set_default_store
from nexus.core.memory import SqliteMemoryStore

set_default_store(SqliteMemoryStore(path="~/.nexus/memory.db"))
```

### Как очистить историю?

```bash
nexus cache-clear
```

### Можно ли экспортировать историю?

Да, файлы истории — это обычные текстовые/JSON файлы:
```bash
cat ~/.nexus/history/history.log
cat ~/.nexus/conversation.json
```

---

## MCP-сервер

### Что такое MCP?

Model Context Protocol — стандарт для подключения ИИ-инструментов к LLM-клиентам (Claude Desktop, Cursor, Continue).

### Как запустить MCP-сервер?

```bash
pip install mcp
nexus mcp
```

### Как настроить Claude Desktop?

Добавьте в `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "nexus": {
      "command": "nexus",
      "args": ["mcp"]
    }
  }
}
```

### Какие инструменты доступны через MCP?

- `nexus_run` — задать вопрос Nexus
- `nexus_search` — поиск в интернете
- `nexus_fetch` — загрузить контент из URL

---

## ReAct-агент

### Что такое ReAct?

ReAct (Reasoning + Acting) — паттерн многошагового рассуждения с вызовом инструментов. LLM чередует мысли, действия и наблюдения до тех пор, пока не получит достаточно информации.

### Как использовать ReAct?

```python
from nexus.core.agent import NexusAgent
from nexus.core.agent_react import ReActAgent, build_default_tools

agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")
tools = build_default_tools()
react = ReActAgent(agent, tools, max_iterations=6)
result = react.run("Ваш вопрос")
print(result.final_answer)
```

### Какие инструменты доступны?

- `web_search` — поиск в интернете
- `web_fetch` — загрузка страницы

### Можно ли добавить свой инструмент?

Да:
```python
def my_tool(value):
    """Описание для LLM."""
    return "результат"

tools.register("my_tool", my_tool, "Описание инструмента.")
```

---

## Производительность

### Как ускорить Nexus?

1. Используйте быстрые модели (Groq)
2. Уменьшите `conversation_history_size`
3. Отключите кэш для уникальных запросов
4. Используйте `--no-cache` для одноразовых запросов

### Nexus потребляет много памяти

1. Уменьшите `max_tokens`
2. Уменьшите `conversation_history_size`
3. Очистите кэш: `nexus cache-clear`

### Таймауты запросов

Увеличьте `timeout` в конфиге:
```yaml
timeout: 60  # по умолчанию 30
```

---

## Безопасность

### Безопасно ли хранить API-ключи в .env?

Да, если:
- `.env` добавлен в `.gitignore`
- Файл имеет ограниченные права доступа
- Ключи не коммитятся в репозиторий

### Можно ли использовать Nexus в продакшене?

Да, но рекомендуется:
- Использовать ключи с ограниченными правами
- Настроить rate limiting
- Мониторить использование API

### Как защитить API-ключи?

1. Используйте переменные окружения вместо .env файла
2. Ограничьте права API-ключей
3. Регулярно ротируйте ключи

---

## Ошибки

### `API ключ не найден`

1. Проверьте `~/.nexus/.env`
2. Или установите переменную окружения: `export GROQ_API_KEY=your_key`
3. Проверьте: `nexus doctor`

### `Invalid configuration`

1. Удалите `~/.nexus/config.yaml`
2. Или исправьте YAML-синтаксис

### `Timeout error`

1. Увеличьте `timeout` в конфиге
2. Попробуйте другую модель
3. Проверьте интернет-соединение

### `ModuleNotFoundError: No module named 'groq'`

```bash
pip install groq
# или
pip install "nexus[all]"
```

### `youtube-transcript-api не установлен`

```bash
pip install youtube-transcript-api
```

### `mcp not installed`

```bash
pip install mcp
```

---

## См. также

- [README.md](README.md) — общее руководство
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — подробное руководство по устранению ошибок
- [INSTALLATION.md](INSTALLATION.md) — установка Nexus