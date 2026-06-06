# Участие в разработке

> 🔙 Назад → [README.md](README.md)

Спасибо за интерес к Nexus! Этот документ описывает, как участвовать в разработке проекта.

## Оглавление

- [Быстрый старт для разработчиков](#быстрый-старт-для-разработчиков)
- [Структура проекта](#структура-проекта)
- [Как вносить изменения](#как-вносить-изменения)
- [Стиль кода](#стиль-кода)
- [Тесты](#тесты)
- [Pre-commit хуки](#pre-commit-хуки)
- [Pull Request](#pull-request)
- [Issues](#issues)

---

## Быстрый старт для разработчиков

```bash
# 1. Клонируйте репозиторий
git clone <repo-url> nexus
cd nexus

# 2. Создайте виртуальное окружение
python -m venv venv
# Windows:
venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate

# 3. Установите зависимости в режиме разработки
pip install -e .

# 4. Установите dev-зависимости (если есть)
pip install pytest flake8 black isort mypy

# 5. Установите pre-commit хуки
pre-commit install

# 6. Запустите тесты
python -m pytest tests/ -v
```

---

## Структура проекта

```
nexus/
├── nexus/
│   ├── cli.py              # CLI-интерфейс
│   ├── mcp_server.py       # MCP-сервер
│   ├── commands/            # Команды CLI
│   │   └── run.py          # Основная логика
│   ├── core/                # Ядро проекта
│   │   ├── agent.py         # NexusAgent
│   │   ├── agent_react.py   # ReAct-агент
│   │   ├── config.py        # Конфигурация
│   │   ├── content_loader.py # Загрузка контента
│   │   ├── history.py       # История диалога
│   │   ├── i18n.py          # Интернационализация
│   │   ├── memory.py        # Подключаемая память
│   │   ├── paths.py         # Пути файловой системы
│   │   ├── providers.py     # LLM-провайдеры
│   │   └── web_search.py    # Web-поиск
│   └── locale/              # Переводы
│       ├── en.json
│       └── ru.json
├── tests/                   # Тесты
├── docs/                    # Документация
├── config/                  # Конфигурация
└── scripts/                 # Скрипты установки
```

---

## Как вносить изменения

### 1. Fork и clone

```bash
# Fork репозитория на GitHub, затем:
git clone https://github.com/YOUR_USERNAME/nexus.git
cd nexus
git remote add upstream https://github.com/ORIGINAL_USERNAME/nexus.git
```

### 2. Создание ветки

```bash
# Для новой фичи:
git checkout -b feature/my-new-feature

# Для исправления бага:
git checkout -b fix/my-bugfix
```

### 3. Внесение изменений

- Сделайте изменения
- Напишите тесты
- Убедитесь, что тесты проходят

### 4. Коммит

```bash
git add .
git commit -m "feat: add my new feature"
```

**Формат коммитов:**
- `feat:` — новая фича
- `fix:` — исправление бага
- `docs:` — документация
- `test:` — тесты
- `refactor:` — рефакторинг
- `chore:` — сборка, CI, зависимости

### 5. Push и Pull Request

```bash
git push origin feature/my-new-feature
```

Откройте Pull Request на GitHub.

---

## Стиль кода

### Форматирование

- **Black** для форматирования кода
- **isort** для сортировки импортов
- **Flake8** для проверки стиля

```bash
# Форматирование
black nexus/ tests/

# Сортировка импортов
isort nexus/ tests/

# Проверка стиля
flake8 nexus/ tests/
```

### Типизация

- Используйте type hints где это возможно
- **mypy** для проверки типов:

```bash
mypy nexus/
```

### Именование

- `snake_case` для функций и переменных
- `PascalCase` для классов
- `UPPER_SNAKE_CASE` для констант
- Описательные имена: `web_searcher`, не `ws`

### Документирование

- Docstrings для всех публичных функций и классов
- Формат: Google style

```python
def my_function(param: str, count: int = 5) -> dict:
    """Краткое описание.

    Более подробное описание если нужно.

    Args:
        param: Описание параметра.
        count: Количество (по умолчанию 5).

    Returns:
        Словарь с результатами.

    Raises:
        ValueError: Если param пустой.
    """
```

---

## Тесты

### Запуск тестов

```bash
# Все тесты
python -m pytest tests/ -v

# Конкретный файл
python -m pytest tests/test_memory.py -v

# С покрытием
python -m pytest tests/ --cov=nexus --cov-report=html
```

### Написание тестов

- Файлы тестов: `tests/test_*.py`
- Классы тестов: `class TestSomething(unittest.TestCase)`
- Методы: `def test_specific_behavior(self)`
- Используйте `unittest.mock` для мока зависимостей

```python
import unittest
from unittest.mock import MagicMock, patch

class TestMyFeature(unittest.TestCase):
    def test_basic_behavior(self):
        """Тест базового поведения."""
        result = my_function("input")
        self.assertEqual(result, expected)

    @patch("nexus.core.module.dependency")
    def test_with_mock(self, mock_dep):
        """Тест с моком зависимости."""
        mock_dep.return_value = "mocked"
        result = my_function("input")
        self.assertIn("mocked", result)
```

---

## Pre-commit хуки

Проект использует pre-commit для автоматической проверки кода перед коммитом.

```bash
# Установка
pip install pre-commit
pre-commit install

# Запуск вручную
pre-commit run --all-files
```

Хуки автоматически:
- Форматируют код (Black)
- Сортируют импорты (isort)
- Проверяют стили (Flake8)
- Проверяют типы (mypy)

---

## Pull Request

### Требования

1. **Тесты:** Все новые фичи должны иметь тесты
2. **Документация:** Обновите документацию если нужно
3. **Стиль:** Код должен проходить проверку стиля
4. **Коммиты:** Чистая история коммитов (squash если нужно)

### Описание PR

Опишите:
- Что изменено
- Почему изменено
- Как тестировать
- Скриншоты (если применимо)

### Ревью

- Все PR требуют ревью
- Адресуйте комментарии ревьюера
- После одобрения — merge

---

## Issues

### Сообщение о баге

При создании issue указывайте:
- Версию Nexus
- ОС и Python
- Шаги для воспроизведения
- Ожидаемое поведение
- Фактическое поведение
- Логи ошибок

### Запрос фичи

Опишите:
- Проблему, которую решает фича
- Предлагаемое решение
- Альтернативы