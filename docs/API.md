# Python API

> 🔙 Назад → [README.md](README.md)

Nexus можно использовать **как Python-библиотеку** — без CLI. Это удобно для интеграции в собственные приложения, Jupyter-ноутбуки, Telegram/Discord-ботов, веб-сервисы и CI/CD-пайплайны.

---

## Оглавление

- [Установка для Python API](#установка-для-python-api)
- [Быстрый старт](#быстрый-старт)
- [`NexusAgent` — основной класс](#nexusagent--основной-класс)
- [Поисковые бэкенды](#поисковые-бэкенды)
- [ReAct-агент](#react-агент)
- [Память (Memory)](#память-memory)
- [Конфигурация](#конфигурация)
- [Плагины](#плагины)
- [Утилиты](#утилиты)
- [Полные примеры](#полные-примеры)

---

## Установка для Python API

```bash
pip install nexus                # минимум (Groq)
pip install "nexus[all]"         # все провайдеры (OpenAI, Anthropic, Ollama)
```

Импорт:

```python
from nexus import NexusAgent     # упрощённый импорт из __init__.py
```

или из ядра:

```python
from nexus.core.agent import NexusAgent
```

---

## Быстрый старт

```python
import os
from nexus import NexusAgent

agent = NexusAgent(
    api_key=os.getenv("GROQ_API_KEY"),
    model="llama-3.3-70b-versatile",
    provider="groq",                  # groq | openai | anthropic | ollama
)

# Одиночный запрос
answer = agent.generate("Что такое Python?")
print(answer)
```

---

## `NexusAgent` — основной класс

### Импорт

```python
from nexus.core.agent import NexusAgent
```

### Конструктор

```python
NexusAgent(
    api_key: str = "",
    model: str = "llama-3.3-70b-versatile",
    provider: str = "groq",          # groq | openai | anthropic | ollama
    base_url: str = "",              # для OpenAI-совместимых API и Ollama
    timeout: int = 30,               # секунды
    max_tokens: int = 4096,
    temperature: float = 0.7,
    **kwargs,
)
```

| Параметр | Тип | Описание |
|----------|-----|----------|
| `api_key` | `str` | API-ключ провайдера (для Ollama — не нужен) |
| `model` | `str` | Имя модели (см. [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)) |
| `provider` | `str` | Идентификатор провайдера |
| `base_url` | `str` | URL API (для Ollama: `http://localhost:11434`) |
| `timeout` | `int` | Таймаут HTTP-запроса, сек |
| `max_tokens` | `int` | Максимум токенов в ответе |
| `temperature` | `float` | Температура сэмплирования (0.0–2.0) |

### Методы

#### `generate(prompt, system_prompt="", history=None, **kwargs) -> str`

Синхронная генерация.

```python
text = agent.generate(
    prompt="Привет!",
    system_prompt="Ты — дружелюбный помощник.",
    history=[
        {"role": "user", "content": "Как дела?"},
        {"role": "assistant", "content": "Отлично!"},
    ],
)
```

#### `generate_stream(prompt, system_prompt="", history=None, **kwargs) -> Iterator[str]`

Стриминг токенов (для UI с обновлением в реальном времени).

```python
for token in agent.generate_stream("Расскажи длинную историю"):
    print(token, end="", flush=True)
```

#### `generate_response(prompt, system_prompt="", **kwargs) -> dict`

Возвращает словарь с метаданными (`text`, `usage`, `model`).

```python
result = agent.generate_response("Сколько будет 2+2?")
print(result)
# {"text": "4", "usage": {"prompt_tokens": 12, "completion_tokens": 1, "total_tokens": 13}, "model": "..."}
```

#### `search_and_answer_stream(prompt, web_searcher, web_config, system_prompt="") -> (Iterator[str], list[Source])`

Совмещает web-поиск и стриминг ответа. Возвращает кортеж `(генератор, список источников)`.

```python
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

web_config = WebSearchConfig(enabled=True, backend="auto", max_results=5)
searcher = WebSearcher(web_config, SEARCH_CACHE_DIR)

gen, sources = agent.search_and_answer_stream(
    prompt="Что нового в Python 3.13?",
    web_searcher=searcher,
    web_config=web_config,
)

for token in gen:
    print(token, end="", flush=True)

print("\nИсточники:")
for s in sources:
    print(f"- {s.url}")
```

### Свойства

| Свойство | Тип | Описание |
|----------|-----|----------|
| `provider` | `str` | Имя провайдера |
| `model` | `str` | Имя модели |
| `usage` | `UsageStats` | Накопленная статистика (запросы, токены) |

---

## Поисковые бэкенды

```python
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

config = WebSearchConfig(
    enabled=True,
    backend="auto",          # auto | duckduckgo | tavily | searxng | bing
    max_results=5,
    fetch_top_n=3,
    timeout=15,
    cache_enabled=True,
)
searcher = WebSearcher(config, SEARCH_CACHE_DIR)

results = searcher.search("лучшие практики FastAPI", max_results=5)
for r in results:
    print(r.title, r.url, r.snippet)

# Загрузка top-N страниц и формирование контекста
context_text, fetched = searcher.search_and_format("новости Python", max_results=3)
```

### `WebSearchConfig`

| Поле | Тип | По умолчанию | Описание |
|------|-----|--------------|----------|
| `enabled` | `bool` | `False` | Глобальный флаг включения |
| `backend` | `str` | `"auto"` | Имя бэкенда или `"auto"` |
| `max_results` | `int` | `5` | Кол-во результатов от поисковика |
| `fetch_top_n` | `int` | `3` | Сколько top-страниц загрузить |
| `timeout` | `int` | `15` | Таймаут HTTP, сек |
| `cache_enabled` | `bool` | `True` | Кэшировать ли результаты |
| `cache_ttl` | `int` | `3600` | TTL кэша, сек |

### `SearchResult`

```python
@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float = 0.0
```

---

## ReAct-агент

```python
from nexus.core.agent import NexusAgent
from nexus.core.agent_react import ReActAgent, build_default_tools
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

agent = NexusAgent(api_key="...", model="llama-3.3-70b-versatile")
searcher = WebSearcher(WebSearchConfig(enabled=True), SEARCH_CACHE_DIR)
tools = build_default_tools(web_searcher=searcher)

react = ReActAgent(agent, tools, max_iterations=6)
result = react.run("What's the latest news about Python 3.13?")

print(result.final_answer)
print(f"Steps: {result.iterations}, time: {result.duration_s:.1f}s")
print(f"Trace: {result.trace}")
```

Подробнее → [REACT.md](REACT.md)

---

## Память (Memory)

```python
from nexus.core.memory import create_memory_store, JsonMemoryStore, SqliteMemoryStore

# Фабрика (рекомендуется)
store = create_memory_store("sqlite", path="~/.nexus/memory.db")

# Или явно
store = JsonMemoryStore("~/.nexus/conversation.json")
store = SqliteMemoryStore("~/.nexus/memory.db")

# Добавление сообщения
store.add(role="user", content="Привет!")
store.add(role="assistant", content="Привет! Чем помочь?")

# Чтение истории
history = store.get_all()       # list[dict]
recent = store.recent(limit=10) # последние 10

# Полнотекстовый поиск (только для SQLite)
hits = store.search("Python")   # list[dict] с FTS5-релевантностью

# Очистка
store.clear()
```

Подробнее → [MEMORY.md](MEMORY.md)

---

## Конфигурация

```python
from nexus.core.config import load_config, NexusConfig

# Загрузить YAML
config = load_config("~/.nexus/config.yaml")
print(config.provider)        # "groq"
print(config.groq_model)      # "llama-3.3-70b-versatile"

# Или собрать программно
config = NexusConfig(
    provider="openai",
    groq_model="gpt-4o-mini",
    max_tokens=2048,
    temperature=0.5,
    timeout=60,
)

# Передача в агента
agent = NexusAgent(
    api_key=os.getenv("OPENAI_API_KEY"),
    model=config.groq_model,
    **config.to_dict(),
)
```

Подробнее → [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)

---

## Плагины

```python
from nexus.core.plugin import (
    discover_plugins,
    register_provider,
    register_search_backend,
    register_hook,
    register_cli_command,
)

# Загрузить все плагины из ~/.nexus/plugins/
loaded = discover_plugins()
print("Loaded plugins:", loaded)
```

Подробнее → [PLUGINS.md](PLUGINS.md)

---

## Утилиты

### Пути файловой системы

```python
from nexus.core.paths import (
    NEXUS_DIR,           # ~/.nexus/
    CACHE_DIR,           # ~/.nexus/cache/
    HISTORY_LOG,         # ~/.nexus/history/history.log
    SEARCH_CACHE_DIR,    # ~/.nexus/search_cache/
    ensure_dirs,
)

ensure_dirs()
print(NEXUS_DIR)   # C:\Users\you\.nexus  (Windows)
                   # /home/you/.nexus    (Linux)
```

### Маскирование секретов

```python
from nexus.core.security import mask_config_value, SensitiveDataFilter

print(mask_config_value("api_key", "sk-abcdefghij1234567890"))
# "sk-abc...7890"  (или ****, если значение короткое)
```

### Статистика использования

```python
from nexus.core.usage_stats import get_global_stats

stats = get_global_stats()
print(f"Requests: {stats.total_requests}")
print(f"Tokens:   {stats.total_tokens:,}")
print(f"Cost:     ${stats.estimated_cost():.4f}")
```

### Автоопределение лучшего провайдера

```python
from nexus.core.autodetect import detect_best_provider

detection = detect_best_provider()
print(f"Best provider: {detection.best_provider}")
print(f"Best model:    {detection.best_model}")

for p in detection.available_providers:
    print(f"  {p.name}: {p.available}, sdk={p.sdk_installed}, key={p.api_key}")
```

### Баннеры

```python
from nexus.core.logo import list_banners, print_logo
from rich.console import Console

console = Console()
print("Available banners:", list_banners())
print_logo(console, banner="default")
```

---

## Полные примеры

### Пример 1. Telegram-бот на `python-telegram-bot`

```python
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from nexus import NexusAgent

agent = NexusAgent(
    api_key=os.getenv("GROQ_API_KEY"),
    model="llama-3.3-70b-versatile",
)

async def start(update: Update, context):
    await update.message.reply_text("Привет! Я Nexus. Спроси меня о чём угодно.")

async def chat(update: Update, context):
    user_text = update.message.text
    answer = agent.generate(user_text)
    await update.message.reply_text(answer)

app = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
app.run_polling()
```

### Пример 2. FastAPI-эндпоинт

```python
from fastapi import FastAPI
from pydantic import BaseModel
from nexus import NexusAgent

app = FastAPI()
agent = NexusAgent(api_key=os.getenv("GROQ_API_KEY"), model="llama-3.3-70b-versatile")


class Req(BaseModel):
    prompt: str
    system: str = ""


class Resp(BaseModel):
    text: str


@app.post("/generate", response_model=Resp)
async def generate(req: Req):
    text = agent.generate(req.prompt, system_prompt=req.system)
    return Resp(text=text)
```

### Пример 3. CLI-обёртка с сохранением в файл

```python
#!/usr/bin/env python3
import sys
from nexus import NexusAgent

agent = NexusAgent()
prompt = " ".join(sys.argv[1:]) or "Расскажи шутку"
text = agent.generate(prompt)
print(text)

with open("last_response.md", "w", encoding="utf-8") as f:
    f.write(text)
```

### Пример 4. Пайплайн: «поиск + суммаризация + запись в файл»

```python
from nexus import NexusAgent
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

agent = NexusAgent()
searcher = WebSearcher(WebSearchConfig(enabled=True, backend="auto"), SEARCH_CACHE_DIR)

query = "новости Python 3.13"
context, sources = searcher.search_and_format(query, max_results=5)

augmented = f"{query}\n\nКонтекст из интернета:\n{context}"
summary = agent.generate(
    augmented,
    system_prompt="Сделай краткое саммари на основе контекста. Ответ дай на русском.",
)

with open("summary.md", "w", encoding="utf-8") as f:
    f.write(f"# {query}\n\n{summary}\n\n## Источники\n\n")
    for s in sources:
        f.write(f"- {s.url}\n")
```

### Пример 5. Jupyter-ноутбук

```python
# Ячейка 1
from nexus import NexusAgent
agent = NexusAgent()

# Ячейка 2
import IPython.display as display
response = agent.generate("Объясни квантовые компьютеры простым языком")
display.Markdown(response)
```

### Пример 6. Асинхронный воркер (Celery/RQ)

```python
from celery import Celery
from nexus import NexusAgent

app = Celery("nexus_tasks", broker="redis://localhost:6379/0")
agent = NexusAgent()

@app.task
def generate_task(prompt: str) -> str:
    return agent.generate(prompt)
```

---

## Версионирование API

Python API следует [Semantic Versioning](https://semver.org/):

- **Публичные классы/функции** в `nexus.core.*` и `nexus.__init__` — стабильный API.
- **Внутренние модули** (начинающиеся с `_`) — могут меняться без предупреждения.
- **Экспериментальные возможности** помечены в коде как `EXPERIMENTAL` и могут быть удалены в минорной версии.

## См. также

- [docs/REACT.md](REACT.md) — ReAct-агент
- [docs/MEMORY.md](MEMORY.md) — подключаемая память
- [docs/PLUGINS.md](PLUGINS.md) — система плагинов
- [docs/ADVANCED_USAGE.md](ADVANCED_USAGE.md) — продвинутые сценарии
- [docs/CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) — конфигурация
