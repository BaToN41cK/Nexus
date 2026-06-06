# ReAct Agent

> 🔙 Назад → [README.md](README.md)

Модуль `nexus.core.agent_react` реализует паттерн **ReAct** (Reasoning + Acting — Рассуждение + Действие) на базе :class:`NexusAgent`. LLM получает инструкцию чередовать рассуждения, вызовы инструментов и наблюдения до тех пор, пока у неё не будет достаточно информации для ответа.

## Оглавление

- [Быстрый старт](#быстрый-старт)
- [Как это работает](#как-это-работает)
- [Формат, которому должна следовать LLM](#формат-которому-должна-следовать-llm)
- [Встроенные инструменты](#встроенные-инструменты)
- [Кастомные инструменты](#кастомные-инструменты)
- [Класс NexusAgent](#класс-nexusagent)
- [Анализ выполнения](#анализ-выполнения)
- [Интеграция с CLI](#интеграция-с-cli)
- [Ограничения](#ограничения)
- [Troubleshooting](#troubleshooting)

---

## Быстрый старт

```python
from nexus.core.agent import NexusAgent
from nexus.core.agent_react import ReActAgent, build_default_tools
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

# 1. Создайте базового агента
agent = NexusAgent(
    api_key="your_groq_api_key",
    model="llama-3.3-70b-versatile",
    provider="groq"
)

# 2. Создайте web-поиск (опционально)
searcher = WebSearcher(
    WebSearchConfig(enabled=True),
    SEARCH_CACHE_DIR
)

# 3. Зарегистрируйте инструменты
tools = build_default_tools(web_searcher=searcher)

# 4. Создайте ReAct-агента
react = ReActAgent(agent, tools, max_iterations=6)

# 5. Запустите
result = react.run("What's the latest news about Python 3.13?")

print(result.final_answer)
print(f"Took {result.iterations} steps in {result.duration_s:.1f}s")
```

---

## Как это работает

ReAct-агент работает в цикле:

```
┌─────────────────────────────────────────────────────────┐
│  1. LLM получает вопрос + список доступных инструментов  │
│  2. LLM генерирует Thought → Action → Action Input       │
│  3. Система выполняет действие и возвращает Observation   │
│  4. Повторяется до Final Answer или исчерпания итераций  │
└─────────────────────────────────────────────────────────┘
```

**Пример цикла:**

```
Thought: Нужно найти последние новости о Python
Action: web_search
Action Input: {"query": "latest Python 3.13 news", "max_results": 3}

Observation: [1] Python 3.13 Released | https://python.org/...
             [2] What's New in Python 3.13 | https://docs.python.org/...

Thought: У меня достаточно информации для ответа
Final Answer: Python 3.13 был выпущен в октябре 2024 года с множеством...
```

---

## Формат, которому должна следовать LLM

LLM должна возвращать строго следующую структуру (без учёта регистра):

```
Thought: <reasoning>
Action: <tool name>
Action Input: <JSON object or plain string>

(system appends)

Observation: <tool result>

... repeat ...

Final Answer: <response to the user>
```

**Правила парсинга:**
- `Final Answer:` имеет приоритет над `Action:` (если оба присутствуют)
- Разбор регистронезависимый (`thought:`, `THOUGHT:`, `Thought:` — всё равно)
- `Action` берётся как первое слово после двоеточия
- `Action Input` парсится как JSON; если не JSON — используется как строка
- Пустые или некорректные шаги обрабатываются через "nudge" (напоминание)

---

## Встроенные инструменты

`build_default_tools` регистрирует два инструмента:

### `web_search`

| Поле | Описание |
|------|----------|
| Вход | `{"query": "...", "max_results": 5}` или строка |
| Выход | Главные результаты поиска (заголовки, URL, сниппеты) |

```python
# Пример вызова из ReAct-цикла
# Action: web_search
# Action Input: {"query": "FastAPI best practices", "max_results": 5}
```

### `web_fetch`

| Поле | Описание |
|------|----------|
| Вход | Строка URL |
| Выход | Извлечённый текст страницы (до 8000 символов) |

```python
# Пример вызова из ReAct-цикла
# Action: web_fetch
# Action Input: https://docs.python.org/3/whatsnew/3.13.html
```

---

## Кастомные инструменты

Вы можете зарегистрировать любой вызываемый объект (callable), который принимает один аргумент и возвращает строку:

```python
from nexus.core.agent_react import ToolRegistry

tools = ToolRegistry()

# Простой калькулятор
def calculator(value):
    """Evaluate a math expression."""
    if isinstance(value, dict):
        expr = value.get("expr", "")
    else:
        expr = str(value)
    return str(eval(expr))

tools.register("calculator", calculator, "Evaluate a math expression.")

# Поиск в базе знаний
def knowledge_base(value):
    """Search internal knowledge base."""
    query = str(value).strip()
    # Ваша логика поиска
    results = search_knowledge_base(query)
    return "\n".join(results)

tools.register("knowledge_base", knowledge_base, "Search internal docs.")
```

**Аргументы инструментов** могут быть как в формате JSON (парсятся автоматически), так и в виде обычной строки.

**Обработка ошибок:** Если инструмент выбрасывает исключение, оно перехватывается и возвращается в виде текста `Observation: [Error in tool 'name': ...]`, чтобы LLM могла адаптироваться.

---

## Класс NexusAgent

`NexusAgent` — базовый агент, который общается с LLM-провайдерами. Он поддерживает:

### Методы

| Метод | Описание |
|-------|----------|
| `generate_response(prompt, system_prompt, history)` | Отправить запрос и получить полный ответ |
| `generate_stream(prompt, system_prompt, history)` | Стриминг ответа (генератор токенов) |
| `summarize(text)` | Суммаризация длинного текста |
| `search_and_answer_stream(prompt, web_searcher, ...)` | Web-поиск + стриминг ответа с контекстом |

### Инициализация

```python
agent = NexusAgent(
    api_key="your_key",                    # API-ключ провайдера
    model="llama-3.3-70b-versatile",       # Модель
    provider="groq",                       # groq | openai | anthropic | ollama
    base_url="",                           # Для OpenAI-совместимых API
    timeout=30,                            # Таймаут (секунды)
    max_tokens=4096,                       # Макс. токенов в ответе
    temperature=0.7,                       # Температура сэмплирования
)
```

### Поддерживаемые провайдеры

| Провайдер | Класс | SDK |
|-----------|-------|-----|
| groq | `GroqProvider` | `groq` |
| openai | `OpenAIProvider` | `openai` |
| anthropic | `AnthropicProvider` | `anthropic` |
| ollama | `OllamaProvider` | `ollama` |

Каждый провайдер реализует интерфейс `BaseProvider` с методами `generate()` и `generate_stream()`.

---

## Анализ выполнения

`react.run(...)` возвращает объект :class:`ReactResult`:

```python
@dataclass
class ReactResult:
    final_answer: str                      # Финальный ответ
    steps: list[dict]                      # Шаги (llm + tool)
    iterations: int                        # Количество итераций
    duration_s: float                      # Время выполнения (секунды)
```

**Пример структуры `steps`:**

```python
result = react.run("Что такое Python?")

for step in result.steps:
    if step["type"] == "llm":
        print(f"LLM: {step['text'][:100]}...")
        print(f"Tokens: {step['tokens']}")
    elif step["type"] == "tool":
        print(f"Tool: {step['name']}({step['input']})")
        print(f"Result: {step['observation'][:100]}...")
```

**Пример вывода:**

```
LLM: Thought: Нужно найти информацию о Python...
Tokens: {'prompt_tokens': 150, 'completion_tokens': 30, 'total_tokens': 180}
Tool: web_search({"query": "what is Python", "max_results": 3})
Result: [1] Python.org | https://python.org | Python is a programming...
LLM: Thought: У меня достаточно информации...
Tokens: {'prompt_tokens': 200, 'completion_tokens': 100, 'total_tokens': 300}
```

---

## Интеграция с CLI

На данный момент ReAct-агент доступен только через Python API. Для использования из CLI:

```python
# react_cli.py
from nexus.core.agent import NexusAgent
from nexus.core.agent_react import ReActAgent, build_default_tools
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR
from nexus.core.config import load_config

# Загрузите конфигурацию
config = load_config()

# Создайте агента
agent = NexusAgent(
    api_key="your_key",
    model=config.groq_model,
    provider=config.provider,
)

# Настройте web-поиск
web_config = WebSearchConfig(enabled=True)
searcher = WebSearcher(web_config, SEARCH_CACHE_DIR)
tools = build_default_tools(web_searcher=searcher)

# Запустите ReAct-агент
react = ReActAgent(agent, tools, max_iterations=6)
result = react.run(input("Ваш вопрос: "))

print("\n=== Ответ ===")
print(result.final_answer)
print(f"\nИтераций: {result.iterations}, Время: {result.duration_s:.1f}s")
```

```bash
python react_cli.py
```

---

## Ограничения

- **Парсинг текстовый:** Основан на обработке текста, а не на специфичных функциях конкретных провайдеров API. LLM иногда выдают некорректно отформатированные шаги; в таких случаях цикл подталкивает их, отправляя напоминание. В худшем случае фолбек-запрос всё равно сформирует финальный ответ.

- **`max_iterations` — жёсткое ограничение:** Значение 6 является хорошим дефолтом. При превышении лимита агент делает одну последнюю попытку, прося LLM обобщить уже имеющиеся наблюдения.

- **Ошибки инструментов:** Передаются обратно в LLM в виде текста `Observation:`, чтобы модель могла адаптироваться. Они никогда не приводят к аварийному завершению цикла.

- **Нет стриминга промежуточных шагов:** В текущей реализации `ReActAgent.run()` возвращает результат после завершения всего цикла. Для стриминга промежуточных шагов используйте `result.steps`.

- **Только текстовые инструменты:** Инструменты должны возвращать строки. Структурированные данные нужно сериализовать в JSON или текст.

---

## Troubleshooting

### LLM не генерирует корректный формат

**Симптом:** Агент зацикливается без прогресса.

**Решение:**
- Убедитесь, что модель поддерживает инструкции (не все модели хорошо следуют формату)
- Попробуйте модель покрупнее (например, `llama-3.3-70b-versatile` вместо `llama-3.1-8b-instant`)
- Уменьшите `max_iterations` чтобы избежать бесконечного цикла

### Инструмент возвращает ошибку

**Симптом:** `Observation: [Error in tool 'name': ...]`

**Решение:** LLM получит текст ошибки и попробует другой подход. Это штатное поведение — ошибка не прерывает цикл.

### Агент исчерпывает итерации

**Симптом:** `final_answer` пустой или содержит текст "You have used all your tool calls..."

**Решение:** Увеличьте `max_iterations`:
```python
react = ReActAgent(agent, tools, max_iterations=10)
```

### Медленная работа

**Симптом:** ReAct-агент работает дольше обычного.

**Причина:** Каждая итерация — это отдельный запрос к LLM. При 6 итерациях это 6+ запросов.

**Решение:**
- Используйте быстрые модели (Groq обычно быстрее OpenAI)
- Уменьшите `max_iterations`
- Используйте более точкие промпты чтобы сократить количество итераций