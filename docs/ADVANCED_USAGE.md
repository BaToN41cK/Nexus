# Продвинутое использование

> 🔙 Назад → [README.md](README.md)

Продвинутые сценарии использования Nexus: кастомные провайдеры, инструменты, пайплайны.

## Оглавление

- [Кастомные провайдеры](#кастомные-провайдеры)
- [Кастомные инструменты ReAct](#кастомные-инструменты-react)
- [Программное использование](#программное-использование)
- [Пайплайны обработки](#пайплайны-обработки)
- [Интеграция с другими системами](#интеграция-с-другими-системами)
- [Расширения](#расширения)

---

## Кастомные провайдеры

### Добавление нового провайдера

1. Создайте класс в `nexus/core/providers.py`:

```python
from nexus.core.providers import BaseProvider

class MyCustomProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, **kwargs):
        super().__init__(api_key, model, **kwargs)
        self._init_client()
    
    def _init_client(self):
        """Инициализация клиента API."""
        # Ваша логика инициализации
        pass
    
    def generate(self, messages: list, stream: bool = False) -> dict:
        """Генерация ответа."""
        # Ваша логика генерации
        return {
            "text": "Ответ от вашего провайдера",
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
    
    def generate_stream(self, messages: list):
        """Генерация ответа с потоковой передачей."""
        # Ваша логика потоковой генерации
        yield "Ответ "
        yield "от "
        yield "вашего "
        yield "провайдера"
```

2. Зарегистрируйте в `PROVIDER_MAP`:

```python
from nexus.core.providers import PROVIDER_MAP

PROVIDER_MAP["my_provider"] = MyCustomProvider
```

3. Добавьте в `config.py`:

```python
VALID_PROVIDERS.append("my_provider")
```

4. Используйте в конфиге:

```yaml
provider: "my_provider"
groq_model: "my-model-name"
```

### Пример: Локальный API

```python
import requests
from nexus.core.providers import BaseProvider

class LocalLLMProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, **kwargs):
        super().__init__(api_key, model, **kwargs)
        self.base_url = kwargs.get("base_url", "http://localhost:8000")
    
    def _init_client(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}"
        })
    
    def generate(self, messages: list, stream: bool = False) -> dict:
        response = self.session.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature
            }
        )
        data = response.json()
        return {
            "text": data["choices"][0]["message"]["content"],
            "usage": data.get("usage", {})
        }
```

---

## Кастомные инструменты ReAct

### Создание инструмента

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
    
    # Безопасное вычисление
    import ast
    try:
        tree = ast.parse(expr, mode='eval')
        result = eval(compile(tree, '<calc>', 'eval'))
        return str(result)
    except Exception as e:
        return f"Error: {e}"

tools.register("calculator", calculator, "Evaluate a math expression. Input: {'expr': '2 + 2'}")
```

### Инструмент с доступом к NexusAgent

```python
def search_with_context(query):
    """Search the web and get context-aware results."""
    from nexus.core.web_search import WebSearcher, WebSearchConfig
    from nexus.core.paths import SEARCH_CACHE_DIR
    
    config = WebSearchConfig(enabled=True)
    searcher = WebSearcher(config, SEARCH_CACHE_DIR)
    
    results = searcher.search(query, max_results=3)
    if not results:
        return "No results found."
    
    context = searcher.search_and_format(query)
    return context

tools.register("search_with_context", search_with_context, "Search the web with full context.")
```

### Инструмент для работы с файлами

```python
import os

def file_reader(value):
    """Read a local file."""
    if isinstance(value, dict):
        path = value.get("path", "")
    else:
        path = str(value)
    
    path = os.path.expanduser(path)
    
    if not os.path.exists(path):
        return f"Error: File not found: {path}"
    
    if os.path.getsize(path) > 100000:  # 100KB limit
        return "Error: File too large (>100KB)"
    
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return content

tools.register("file_reader", file_reader, "Read a local file. Input: {'path': '~/documents/file.txt'}")
```

### Инструмент для выполнения кода

```python
import subprocess
import shlex

def code_executor(value):
    """Execute a shell command."""
    if isinstance(value, dict):
        command = value.get("command", "")
    else:
        command = str(value)
    
    try:
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return f"Error (exit code {result.returncode}):\n{result.stderr}"
        
        return result.stdout
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds"
    except Exception as e:
        return f"Error: {e}"

tools.register("code_executor", code_executor, "Execute a shell command. Input: {'command': 'ls -la'}")
```

---

## Программное использование

### Базовый пример

```python
from nexus.core.agent import NexusAgent
from nexus.core.config import load_config

# Загрузка конфига
config = load_config()

# Создание агента
agent = NexusAgent(
    api_key="your_key",
    model=config.groq_model,
    provider=config.provider
)

# Генерация ответа
result = agent.generate_response(
    "Что такое Python?",
    system_prompt="Отвечай кратко."
)
print(result["text"])
```

### Стриминг

```python
from nexus.core.agent import NexusAgent
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")
console = Console()

response = ""
with Live(console=console) as live:
    for token in agent.generate_stream("Расскажи о Python"):
        response += token
        live.update(Markdown(response))
```

### Web-поиск + LLM

```python
from nexus.core.agent import NexusAgent
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")
searcher = WebSearcher(WebSearchConfig(enabled=True), SEARCH_CACHE_DIR)

result = agent.search_and_answer_stream(
    "Что нового в Python 3.13?",
    web_searcher=searcher,
    system_prompt="Отвечай на основе найденной информации."
)
```

### ReAct-агент

```python
from nexus.core.agent import NexusAgent
from nexus.core.agent_react import ReActAgent, build_default_tools
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")
searcher = WebSearcher(WebSearchConfig(enabled=True), SEARCH_CACHE_DIR)
tools = build_default_tools(web_searcher=searcher)

react = ReActAgent(agent, tools, max_iterations=6)
result = react.run("Найди последние новости о Python")

print(result.final_answer)
print(f"Iterations: {result.iterations}")
print(f"Duration: {result.duration_s:.1f}s")
```

---

## Пайплайны обработки

### Автоматическое саммари статей

```python
import sys
from nexus.core.agent import NexusAgent
from nexus.core.content_loader import load

def summarize_url(url: str) -> str:
    agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")
    
    content = load(url)
    if content.startswith("[Ошибка"):
        return f"Не удалось загрузить: {content}"
    
    result = agent.generate_response(
        f"Сделай краткое саммари:\n\n{content[:10000]}",
        system_prompt="Ты эксперт по анализу текстов."
    )
    return result["text"]

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    print(summarize_url(url))
```

### Пакетная обработка

```python
from nexus.core.agent import NexusAgent
from nexus.core.content_loader import load

agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")

urls = [
    "https://example.com/article1.html",
    "https://example.com/article2.html",
    "https://example.com/article3.html"
]

results = []
for url in urls:
    content = load(url)
    if not content.startswith("[Ошибка"):
        result = agent.generate_response(
            f"Сделай саммари:\n\n{content[:5000]}",
            system_prompt="Краткое саммари в 3 предложениях."
        )
        results.append({
            "url": url,
            "summary": result["text"]
        })

for r in results:
    print(f"\n{r['url']}")
    print(f"{r['summary']}")
```

### Пайплайн: Поиск → Загрузка → Анализ

```python
from nexus.core.agent import NexusAgent
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR
from nexus.core.content_loader import load

agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")
searcher = WebSearcher(WebSearchConfig(enabled=True), SEARCH_CACHE_DIR)

# Шаг 1: Поиск
results = searcher.search("лучшие практики FastAPI", max_results=5)

# Шаг 2: Загрузка топ-3 страниц
summaries = []
for r in results[:3]:
    content = load(r.url)
    if not content.startswith("[Ошибка"):
        result = agent.generate_response(
            f"Проанализируй статью:\n\n{content[:5000]}",
            system_prompt="Выдели 3 ключевых тезиса."
        )
        summaries.append({
            "title": r.title,
            "url": r.url,
            "key_points": result["text"]
        })

# Шаг 3: Итоговый анализ
final_prompt = "Объедини ключевые тезисы:\n\n"
for s in summaries:
    final_prompt += f"### {s['title']}\n{s['key_points']}\n\n"

final_result = agent.generate_response(
    final_prompt,
    system_prompt="Создай общий обзор."
)
print(final_result["text"])
```

---

## Интеграция с другими системами

### Telegram-бот

```python
"""Пример Telegram-бота на базе Nexus."""

from nexus.core.agent import NexusAgent
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

class NexusBot:
    def __init__(self):
        self.agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")
        self.searcher = WebSearcher(WebSearchConfig(enabled=True), SEARCH_CACHE_DIR)
    
    def handle_message(self, text: str) -> str:
        if text.startswith("/search "):
            query = text[8:]
            results = self.searcher.search(query, max_results=3)
            return "\n".join(f"- {r.title}: {r.url}" for r in results)
        
        result = self.agent.generate_response(text)
        return result["text"]
```

### Flask API

```python
"""Flask API с Nexus."""

from flask import Flask, request, jsonify
from nexus.core.agent import NexusAgent

app = Flask(__name__)
agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    question = data.get("question", "")
    
    result = agent.generate_response(
        question,
        system_prompt=data.get("system_prompt")
    )
    
    return jsonify({
        "answer": result["text"],
        "tokens": result["total_tokens"]
    })

if __name__ == "__main__":
    app.run(debug=True)
```

### FastAPI

```python
"""FastAPI с Nexus."""

from fastapi import FastAPI
from pydantic import BaseModel
from nexus.core.agent import NexusAgent

app = FastAPI()
agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")

class Question(BaseModel):
    question: str
    system_prompt: str = None

@app.post("/ask")
def ask(q: Question):
    result = agent.generate_response(
        q.question,
        system_prompt=q.system_prompt
    )
    return {
        "answer": result["text"],
        "tokens": result["total_tokens"]
    }
```

---

## Расширения

### Плагины (планируется)

В будущем Nexus планирует поддерживать плагины:

```python
# Плагин для Nexus (концепт)
class MyPlugin:
    def __init__(self, nexus):
        self.nexus = nexus
    
    def on_before_request(self, prompt: str) -> str:
        """Хук перед отправкой запроса."""
        return prompt
    
    def on_after_response(self, response: str) -> str:
        """Хук после получения ответа."""
        return response

# Регистрация плагина
nexus.register_plugin(MyPlugin())
```

### Middleware (планируется)

```python
# Middleware для Nexus (концепт)
class LoggingMiddleware:
    def process(self, prompt: str, response: str):
        print(f"Prompt: {prompt[:100]}...")
        print(f"Response: {response[:100]}...")

nexus.add_middleware(LoggingMiddleware())
```

---

## См. также

- [REACT.md](REACT.md) — ReAct-агент
- [ARCHITECTURE.md](ARCHITECTURE.md) — архитектура проекта
- [EXAMPLES.md](EXAMPLES.md) — примеры использования