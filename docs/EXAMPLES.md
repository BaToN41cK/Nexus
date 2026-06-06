# Примеры использования

> 🔙 Назад → [README.md](README.md)

Этот документ содержит реальные примеры использования Nexus для различных задач.

## Оглавление

- [Базовые примеры](#базовые-примеры)
- [Загрузка контента](#загрузка-контента)
- [Web-поиск](#web-поиск)
- [Программное использование (Python API)](#программное-использование-python-api)
- [Интеграция с другими системами](#интеграция-с-другими-системами)

---

## Базовые примеры

### Простой вопрос

```bash
nexus run "Что такое нейронные сети?"
```

### Вопрос на русском языке

```bash
nexus --lang ru run "Объясни квантовые вычисления простыми словами"
```

### Вопрос с конкретной моделью

```bash
# Временно переключить модель (через конфиг)
nexus run "Напиши код на Python" --config config/nexus.yaml
```

### Интерактивный диалог

```bash
nexus interactive
# You: Привет!
# Nexus: Здравствуйте! Чем могу помочь?
# You: Расскажи о Python
# Nexus: Python — это высокоуровневый язык программирования...
# You: exit
```

---

## Загрузка контента

### Анализ веб-страницы

```bash
# Краткое описание статьи
nexus run "Кратко опиши https://docs.python.org/3/tutorial/"

# Извлечение ключевых тезисов
nexus run "Выдели 5 главных тезисов из https://peps.python.org/pep-0001/"
```

### Работа с YouTube

```bash
# О чём видео?
nexus run "О чем это видео? https://youtube.com/watch?v=dQw4w9WgXcQ"

# Саммари видео
nexus run "Сделай краткое саммари видео https://youtube.com/watch?v=VIDEO_ID"

# Ключевые моменты
nexus run "Выдели ключевые моменты из этого видео https://youtube.com/watch?v=VIDEO_ID"
```

### Работа с документами

```bash
# PDF
nexus run "Сделай саммари этого документа https://example.com/report.pdf"

# Word (DOCX)
nexus run "Выдели основные тезисы https://example.com/document.docx"

# PowerPoint
nexus run "Опиши содержание презентации https://example.com/slides.pptx"

# Excel
nexus run "Проанализируй данные в таблице https://example.com/data.xlsx"
```

### Анализ нескольких источников

```bash
# Сравнение двух статей
nexus run "Сравни эти две статьи: https://example.com/a.html и https://example.com/b.html"

# Обзор нескольких источников
nexus run "Сделай обзор информации из этих источников: https://a.com, https://b.com, https://c.com"
```

---

## Web-поиск

### Поиск новостей

```bash
# Последние новости
nexus run "Что нового в мире технологий?" --search

# Конкретная тема
nexus run "Последние новости о Python 3.13" --search
```

### Поиск информации

```bash
# Лучшие практики
nexus run "Лучшие практики FastAPI" --search

# Сравнение технологий
nexus run "Сравни React и Vue.js в 2024 году" --search

# Как сделать что-то
nexus run "Как настроить CI/CD для Python проекта" --search
```

### Ручной поиск

```bash
# Просто показать результаты
nexus search "последние новости Python" --max 5

# Поиск + анализ через LLM
nexus search "лучшие практики Docker" --fetch
```

---

## Программное использование (Python API)

### Базовый пример

```python
from nexus.core.agent import NexusAgent

# Создание агента
agent = NexusAgent(
    api_key="your_key",
    model="llama-3.3-70b-versatile",
    provider="groq"
)

# Получение ответа
result = agent.generate_response(
    "Что такое Python?",
    system_prompt="Отвечай кратко."
)
print(result["text"])
```

### Стриминг ответа

```python
from nexus.core.agent import NexusAgent
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")
console = Console()

# Стриминг с отображением в реальном времени
response = ""
with Live(console=console) as live:
    for token in agent.generate_stream("Расскажи о Python"):
        response += token
        live.update(Markdown(response))
```

### Web-поиск через Python

```python
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

# Создание поисковика
config = WebSearchConfig(enabled=True, backend="auto")
searcher = WebSearcher(config, SEARCH_CACHE_DIR)

# Поиск
results = searcher.search("последние новости Python")
for r in results:
    print(f"{r.title}: {r.url}")

# Поиск + загрузка страниц
context, fetched = searcher.search_and_format("Python 3.13")
print(f"Загружено {len(fetched)} страниц")
print(context[:500])
```

### ReAct-агент

```python
from nexus.core.agent import NexusAgent
from nexus.core.agent_react import ReActAgent, build_default_tools
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

# Настройка
agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")
searcher = WebSearcher(WebSearchConfig(enabled=True), SEARCH_CACHE_DIR)
tools = build_default_tools(web_searcher=searcher)

# Запуск ReAct-цикла
react = ReActAgent(agent, tools, max_iterations=6)
result = react.run("Найди последние новости о Python и сделай саммари")

print(f"Ответ: {result.final_answer}")
print(f"Итераций: {result.iterations}")
print(f"Время: {result.duration_s:.1f}s")
```

### Работа с памятью

```python
from nexus.core.memory import create_memory_store, Exchange

# Создание хранилища
store = create_memory_store("sqlite", path="~/.nexus/memory.db")

# Добавление обменов
store.add_exchange("Привет!", "Здравствуйте!")
store.add_exchange("Как дела?", "Отлично!")

# Построение контекста
context, exchanges = store.build_context(max_exchanges=5)
print(context)

# Поиск
results = store.search("привет")
print(f"Найдено {len(results)} записей")

# Статистика
print(f"Всего записей: {store.count()}")
```

---

## Интеграция с другими системами

### Использование в скрипте

```python
#!/usr/bin/env python3
"""Скрипт для автоматического саммари статей."""

import sys
from nexus.core.agent import NexusAgent
from nexus.core.content_loader import load

def summarize_url(url: str) -> str:
    """Загрузить URL и сделать саммари."""
    agent = NexusAgent(
        api_key="your_key",
        model="llama-3.3-70b-versatile"
    )
    
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

### Использование в боте

```python
"""Пример Telegram-бота на базе Nexus."""

from nexus.core.agent import NexusAgent
from nexus.core.web_search import WebSearcher, WebSearchConfig
from nexus.core.paths import SEARCH_CACHE_DIR

class NexusBot:
    def __init__(self):
        self.agent = NexusAgent(
            api_key="your_key",
            model="llama-3.3-70b-versatile"
        )
        self.searcher = WebSearcher(
            WebSearchConfig(enabled=True),
            SEARCH_CACHE_DIR
        )
    
    def handle_message(self, text: str) -> str:
        """Обработать сообщение пользователя."""
        if text.startswith("/search "):
            query = text[8:]
            results = self.searcher.search(query, max_results=3)
            return "\n".join(f"- {r.title}: {r.url}" for r in results)
        
        result = self.agent.generate_response(text)
        return result["text"]
```

### Использование в веб-приложении

```python
"""Flask-приложение с Nexus."""

from flask import Flask, request, jsonify
from nexus.core.agent import NexusAgent

app = Flask(__name__)
agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")

@app.route("/ask", methods=["POST"])
def ask():
    """Ответить на вопрос пользователя."""
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