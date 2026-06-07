# Тестирование

> 🔙 Назад → [README.md](README.md)

Руководство по тестированию Nexus.

## Оглавление

- [Обзор](#обзор)
- [Запуск тестов](#запуск-тестов)
- [Структура тестов](#структура-тестов)
- [Написание тестов](#написание-тестов)
- [Моки и фикстуры](#моки-и-фикстуры)
- [Покрытие кода](#покрытие-кода)
- [CI/CD](#cicd)
- [Troubleshooting](#troubleshooting)

---

## Обзор

Nexus использует `pytest` для тестирования. Тесты расположены в директории `tests/`.

### Текущие тесты

| Файл | Описание |
|------|----------|
| `test_agent_react.py` | Тесты ReAct-агента |
| `test_history.py` | Тесты истории диалога |
| `test_mcp_server.py` | Тесты MCP-сервера |
| `test_memory.py` | Тесты подключаемой памяти |
| `test_web_search.py` | Тесты web-поиска |

---

## Запуск тестов

### Все тесты

```bash
python -m pytest tests/ -v
```

### Конкретный файл

```bash
python -m pytest tests/test_memory.py -v
```

### Конкретный тест

```bash
python -m pytest tests/test_memory.py::test_add_exchange -v
```

### С покрытием

```bash
python -m pytest tests/ --cov=nexus --cov-report=html
```

### В тихом режиме

```bash
python -m pytest tests/ -q
```

### С остановкой на первой ошибке

```bash
python -m pytest tests/ -x
```

---

## Структура тестов

```
tests/
├── __init__.py
├── test_agent_react.py      # Тесты ReAct-агента
├── test_history.py          # Тесты истории диалога
├── test_mcp_server.py       # Тесты MCP-сервера
├── test_memory.py           # Тесты памяти
└── test_web_search.py       # Тесты web-поиска
```

### Именование файлов

- Файлы тестов: `test_*.py`
- Классы тестов: `class TestSomething(unittest.TestCase)`
- Методы: `def test_specific_behavior(self)`

---

## Написание тестов

### Базовый пример

```python
import unittest
from nexus.core.memory import JsonMemoryStore, Exchange

class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        """Настройка перед каждым тестом."""
        self.store = JsonMemoryStore(path="/tmp/test_memory.json")
    
    def tearDown(self):
        """Очистка после каждого теста."""
        import os
        if os.path.exists("/tmp/test_memory.json"):
            os.remove("/tmp/test_memory.json")
    
    def test_add_exchange(self):
        """Тест добавления обмена."""
        self.store.add_exchange("Привет!", "Здравствуйте!")
        count = self.store.count()
        self.assertEqual(count, 1)
    
    def test_build_context(self):
        """Тест построения контекста."""
        self.store.add_exchange("Вопрос", "Ответ")
        context, exchanges = self.store.build_context()
        self.assertIn("Вопрос", context)
        self.assertIn("Ответ", context)
```

### Параметризованные тесты

```python
import pytest

@pytest.mark.parametrize("provider", ["groq", "openai", "anthropic"])
def test_provider_creation(provider):
    """Тест создания провайдеров."""
    # Тест для каждого провайдера
    pass
```

### Тесты исключений

```python
def test_invalid_config():
    """Тест обработки неверной конфигурации."""
    with self.assertRaises(ValueError):
        # Код, который должен выбросить исключение
        pass
```

---

## Моки и фикстуры

### Моки зависимостей

```python
from unittest.mock import MagicMock, patch

class TestAgent(unittest.TestCase):
    @patch("nexus.core.agent.NexusAgent")
    def test_agent_response(self, MockAgent):
        """Тест ответа агента с моком."""
        # Настройка мока
        mock_instance = MockAgent.return_value
        mock_instance.generate_response.return_value = {
            "text": "Тестовый ответ",
            "usage": {"total_tokens": 10}
        }
        
        # Вызов тестируемого кода
        result = mock_instance.generate_response("Вопрос")
        
        # Проверка
        self.assertEqual(result["text"], "Тестовый ответ")
```

### Моки HTTP-запросов

```python
import responses
from nexus.core.web_search import WebSearcher

@responses.activate
def test_web_search():
    """Тест web-поиска с моком HTTP."""
    responses.add(
        responses.GET,
        "https://api.duckduckgo.com/",
        json={"Abstract": "Тестовый результат"},
        status=200
    )
    
    searcher = WebSearcher(...)
    results = searcher.search("тест")
    self.assertTrue(len(results) > 0)
```

### Фикстуры pytest

```python
# conftest.py
import pytest
from nexus.core.memory import JsonMemoryStore

@pytest.fixture
def memory_store():
    """Фикстура для хранилища памяти."""
    store = JsonMemoryStore(path="/tmp/test_memory.json")
    yield store
    # Очистка после теста
    import os
    if os.path.exists("/tmp/test_memory.json"):
        os.remove("/tmp/test_memory.json")

# Использование в тесте
def test_with_store(memory_store):
    memory_store.add_exchange("Вопрос", "Ответ")
    assert memory_store.count() == 1
```

---

## Покрытие кода

### Генерация отчёта

```bash
python -m pytest tests/ --cov=nexus --cov-report=html
```

### Просмотр отчёта

Откройте `htmlcov/index.html` в браузере.

### Минимальное покрытие

```bash
python -m pytest tests/ --cov=nexus --cov-fail-under=80
```

---

## CI/CD

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11', '3.12']
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[all]"
          pip install pytest pytest-cov
      
      - name: Run tests
        run: pytest tests/ -v --cov=nexus
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

---

## Troubleshooting

### Тест не находит модуль

```bash
# Убедитесь, что Nexus установлен в editable-режиме
pip install -e .
```

### Тест падает с ошибкой импорта

```bash
# Установите все зависимости
pip install -e ".[all]"
pip install pytest pytest-cov
```

### Мок не работает

1. Убедитесь, что путь к мокируемому объекту правильный
2. Проверьте, что `@patch` применяется к правильному модулю
3. Используйте `@patch.object` для мока конкретного атрибута

### Тесты проходят локально, но падают в CI

1. Проверьте зависимости в CI
2. Убедитесь, что переменные окружения настроены
3. Проверьте версии Python в matrix

---

## См. также

- [CONTRIBUTING.md](CONTRIBUTING.md) — участие в разработке
- [DEVELOPMENT.md](DEVELOPMENT.md) — настройка окружения разработки
- [ARCHITECTURE.md](ARCHITECTURE.md) — архитектура проекта