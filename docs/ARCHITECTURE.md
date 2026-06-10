# Архитектура проекта

> 🔙 Назад → [README.md](README.md)

Этот документ описывает внутреннюю архитектуру Nexus — как организован код, какие компоненты взаимодействуют и как расширять функционал.

## Оглавление

- [Обзор](#обзор)
- [Диаграмма компонентов](#диаграмма-компонентов)
- [Поток данных](#поток-данных)
- [Ключевые модули](#ключевые-модули)
- [Паттерны проектирования](#паттерны-проектирования)
- [Расширяемость](#расширяемость)

---

## Обзор

Nexus построен по принципу **многослойной архитектуры**:

```
┌─────────────────────────────────────────────────────┐
│                    CLI (cli.py)                     │
│         argparse, i18n, rich вывод                  │
├─────────────────────────────────────────────────────┤
│               Команды (commands/)                   │
│              run.py — основная логика               │
├─────────────────────────────────────────────────────┤
│                Ядро (core/)                         │
│  agent.py │ agent_react.py │ resilience.py          │
│  health.py │ tiny_fallback.py │ config.py           │
│  memory.py │ providers.py                           │
├─────────────────────────────────────────────────────┤
│     Resilience Layer (resilience.py)                │
│  CircuitBreaker | FallbackProviderChain             │
│  IdempotencyManager | retry_call                   │
├─────────────────────────────────────────────────────┤
│     Health Checker (health.py)                      │
│  HealthChecker — background daemon thread           │
│  Pings OPEN providers => auto-closes circuit breaker│
├─────────────────────────────────────────────────────┤
│     Emergency Fallback (tiny_fallback.py)            │
│  TinyFallbackResponder (rules-based patterns)       │
│  try_ollama_tiny_fallback() | emergency_fallback()  │
├─────────────────────────────────────────────────────┤
│             Провайдеры (providers.py)               │
│    GroqProvider │ OpenAIProvider │ AnthropicProvider│
│                    OllamaProvider                   │
├─────────────────────────────────────────────────────┤
│            Внешние сервисы                          │
│  web_search.py │ content_loader.py │ MCP server     │
└─────────────────────────────────────────────────────┘
```

---

## Диаграмма компонентов

```
                          ┌──────────────┐
                          │ Пользователь │
                          └──────┬───────┘
                                 │ CLI / Python API
                          ┌──────▼───────┐
                          │   cli.py     │
                          │  (argparse)  │
                          └──────┬───────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
         ┌──────▼──────┐ ┌──────▼──────┐ ┌───────▼──────┐
         │   run.py    │ │ interactive │ │  search.py   │
         │  (команда)  │ │   (CLI)     │ │  (CLI cmd)   │
         └──────┬──────┘ └──────┬──────┘ └──────┬───────┘
                │                │                │
                └────────────────┼────────────────┘
                                 │
                          ┌──────▼───────┐
                          │  NexusAgent  │
                          │  (agent.py)  │
                          └──────┬───────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
   ┌──────▼───────┐     ┌───────▼──────┐     ┌────────▼───────┐
   │  Resilience   │     │  Providers   │     │  Emergency     │
   │ (resilience.py)│    │ (groq,etc.)  │     │  Fallback      │
   │ CircuitBr.   │     │              │     │ (tiny_fallback)│
   │ FallbackChain│     │              │     │ Rules | Ollama │
   │ Idempotency  │     │              │     │ tiny model     │
   └──────┬───────┘     └──────┬───────┘     └────────┬───────┘
          │                    │                      │
          └──────┬─────────────┼──────────────────────┘
                 │             │
          ┌──────▼──────┐ ┌────▼─────────┐
          │  Health     │ │ web_search   │
          │  Checker    │ │ memory       │
          │ (health.py) │ │ content_load │
          └─────────────┘ └──────────────┘
```

---

## Поток данных

### Базовый запрос (`nexus run "..."`)

```
1. cli.py: парсинг аргументов
2. run.py: загрузка конфигурации (config.yaml)
3. run.py: загрузка API-ключа (.env)
4. run.py: извлечение URL из промпта
5. content_loader.py: загрузка контента по URL
6. run.py: проверка кэша
7. history.py: построение контекста из истории
8. agent.py: отправка запроса в LLM
   a. Primary provider (Groq/OpenAI/etc.)
   b. Если ошибка -> FallbackProviderChain (следующий провайдер)
   c. Если все провайдеры упали -> Emergency Fallback
      1. Ollama tinyllama (локально)
      2. Rules-based (TinyFallbackResponder)
      3. Generic offline message
9. rich: стриминг и рендеринг ответа
10. run.py: сохранение в кэш и историю
```

### Web-поиск (`nexus run "..." --search`)

```
1. cli.py: парсинг аргументов
2. run.py: загрузка конфигурации
3. web_search.py: выбор бэкенда (auto -> tavily/bing/searxng/ddg)
4. web_search.py: поиск запроса
5. web_search.py: загрузка top-N страниц (content_loader)
6. agent.py: формирование augmented prompt с контекстом
7. agent.py: стриминг ответа
8. rich: рендеринг ответа + список источников
```

### ReAct-агент

```
1. ReActAgent: построение системного промпта
2. Цикл (max_iterations):
   a. NexusAgent.generate_response(transcript)
   b. parse_react_step(text) -> ReactStep
   c. Если Final Answer -> выход из цикла
   d. Если Action -> ToolRegistry.call(name, input)
   e. Добавление Observation в transcript
   f. Если нет действия -> nudge (напоминание)
3. Фолбек: запрос Final Answer если не получен
4. Возврат ReactResult
```

---

## Ключевые модули

### `nexus/cli.py` — Точка входа

- Парсинг аргументов через `argparse`
- Маршрутизация команд (`COMMAND_MAP`)
- Интерактивный режим с `prompt_toolkit`
- Интернационализация (`--lang`)

### `nexus/core/agent.py` — Агент

- `NexusAgent` — основной класс, общающийся с LLM
- Поддержка streaming и non-streaming режимов
- Метод `search_and_answer_stream()` для web-поиска
- Автоматическая суммаризация длинного контента
- Интеграция с `FallbackProviderChain` для multi-provider failover
- Использование `emergency_fallback()` как последней надежды

### `nexus/core/resilience.py` — Resilience-слой

- `CircuitBreaker` — state machine (CLOSED -> OPEN -> HALF_OPEN)
- `FallbackProviderChain` — ordered multi-provider fallback
- `IdempotencyManager` — deduplication of identical requests
- `retry_call()` — exponential backoff with jitter
- `resilient_call()` — unified wrapper (retry + circuit breaker + idempotency)

### `nexus/core/health.py` — Pre-emptive Health Checker

- `HealthChecker` — background daemon thread
- Periodically pings providers whose circuit breaker is OPEN
- On successful ping -> immediately closes the circuit breaker
- Bypasses `recovery_timeout` + HALF_OPEN -> CLOSED dance
- Integrates with `FallbackProviderChain` via `health_checker` parameter

### `nexus/core/tiny_fallback.py` — Emergency Fallback

- `emergency_fallback()` — 3-tier graceful degradation:
  1. Ollama tiny model (`tinyllama`) — local, no internet needed
  2. `TinyFallbackResponder` — rules-based pattern matching (ru/en)
  3. Generic offline diagnostic message
- `ResponseRule` — configurable pattern -> response with priority
- Used by `NexusAgent` when all providers in the chain fail

### `nexus/core/providers.py` — Провайдеры

- `BaseProvider` — абстрактный базовый класс
- `GroqProvider` — Groq API (SDK `groq`)
- `OpenAIProvider` — OpenAI API (SDK `openai`)
- `AnthropicProvider` — Anthropic API (SDK `anthropic`)
- `OllamaProvider` — Ollama (SDK `ollama`)
- Фабрика `create_provider()` для создания по имени

### `nexus/core/web_search.py` — Web-поиск

- `WebSearcher` — фасад для поиска
- `DuckDuckGoBackend` — HTML-парсинг (без API)
- `TavilyBackend` — REST API (рекомендуется)
- `SearXNGBackend` — self-hosted
- `BingBackend` — Azure Bing
- `_SearchCache` — TTL-кэш на диске

### `nexus/core/content_loader.py` — Загрузка контента

- Диспетчер по расширению файла
- YouTube (субтитры), PDF, DOCX, PPTX, Excel
- Веб-страницы (requests + BeautifulSoup)
- Автоматическое определение типа

### `nexus/core/memory.py` — Память

- `MemoryStore` — абстрактный интерфейс
- `JsonMemoryStore` — JSON-файл
- `SqliteMemoryStore` — SQLite + FTS5
- Фабрика `create_memory_store()`

### `nexus/core/config.py` — Конфигурация

- `NexusConfig` — dataclass с валидацией
- `WebSearchConfig` — настройки поиска
- Загрузка из YAML с проверкой типов
- Автосоздание дефолтного конфига

### `nexus/mcp_server.py` — MCP-сервер

- Сервер через stdio (JSON-RPC)
- Три инструмента: `nexus_run`, `nexus_search`, `nexus_fetch`
- Ленивая загрузка SDK `mcp`

---

## Паттерны проектирования

### Strategy Pattern (Провайдеры)

```python
# Все провайдеры реализуют один интерфейс
class BaseProvider(ABC):
    def generate(messages, stream=False) -> dict: ...
    def generate_stream(messages) -> Generator: ...

# Фабрика создаёт нужный провайдер
provider = create_provider(ProviderConfig(name="groq", ...))
```

### Facade Pattern (WebSearcher)

```python
# WebSearcher скрывает сложность выбора бэкенда
searcher = WebSearcher(config, cache_dir)
results = searcher.search("query")  # Автоматически выбирает бэкенд
```

### Strategy Pattern (Memory Store)

```python
# Все хранилища реализуют один интерфейс
class MemoryStore(ABC):
    def add_exchange(prompt, response, max_exchanges): ...
    def build_context(system_prompt, max_exchanges): ...
    def search(query, limit): ...
    def clear(): ...
    def count(): ...
```

### Observer Pattern (Streaming)

```python
# Генераторы для стриминга ответов
gen = agent.generate_stream(prompt)
for token in gen:
    live.update(Panel(Markdown(token)))
```

### Circuit Breaker Pattern (Resilience)

```python
# CircuitBreaker prevents cascading failures
cb = CircuitBreaker(config)
if cb.allow_request():
    try:
        result = call_provider()
        cb.record_success()
    except Exception:
        cb.record_failure()  # OPEN after failure_threshold
```

### Background Health Checker Pattern

```python
# HealthChecker auto-recovers OPEN circuits
checker = HealthChecker(interval=15.0)
checker.register("groq:model", ping_fn, circuit_breaker)
checker.start()  # daemon thread, auto-recovery on ping success
```

---

## Расширяемость

### Добавление нового LLM-провайдера

1.Создайте класс в `nexus/core/providers.py`:

```python
class MyProvider(BaseProvider):
    def _init_client(self): ...
    def generate(self, messages, stream=False): ...
    def generate_stream(self, messages): ...
```

2.Зарегистрируйте в `PROVIDER_MAP`:

```python
PROVIDER_MAP["my_provider"] = MyProvider
```

3.Добавьте в `config.py`:

```python
VALID_PROVIDERS.append("my_provider")
```

### Добавление нового поискового бэкенда

1.Создайте класс в `nexus/core/web_search.py`:

```python
class MySearchBackend(SearchBackend):
    name = "my_search"
    def search(self, query, max_results): ...
```

2.Добавьте в `_select_backend()` и `_auto_priority()`

### Добавление нового формата контента

1. Создайте функцию в `nexus/core/content_loader.py`:

```python
def load_my_format(url_or_path): ...
```

2.Добавьте в `_EXTENSION_MAP`:

```python
_EXTENSION_MAP[".myext"] = load_my_format
```

### Добавление нового ReAct-инструмента

```python
tools = build_default_tools(web_searcher=searcher)

def my_tool(value):
    """Description for LLM."""
    return "result"

tools.register("my_tool", my_tool, "Description for LLM.")
```

### Добавление новых health-check ping-функций

```python
# Кастомная ping-функция для HealthChecker
def my_ping() -> bool:
    try:
        # Лёгкий запрос к провайдеру
        return True
    except Exception:
        return False

checker = HealthChecker()
checker.register("my_provider:model", my_ping, circuit_breaker)
checker.start()
```

### Добавление новых правил для TinyFallbackResponder

```python
from nexus.core.tiny_fallback import ResponseRule, TinyFallbackResponder

my_rule = ResponseRule(
    patterns=[r"(?i)my custom pattern"],
    response="My custom response",
    priority=50,
)
responder = TinyFallbackResponder(rules=[my_rule])
result = responder.respond(messages)