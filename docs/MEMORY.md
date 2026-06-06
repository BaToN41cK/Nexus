# Подключаемая память (Pluggable Memory)

> 🔙 Назад → [README.md](README.md)

Nexus хранит историю диалогов в подключаемом *хранилище памяти* (memory store). «Из коробки» поставляются два бэкенда:

| Бэкенд | Класс | Лучше всего подходит для |
| :--- | :--- | :--- |
| `json` | `JsonMemoryStore` | По умолчанию; небольшая история, удобно просматривать/искать через grep. |
| `sqlite` | `SqliteMemoryStore` | Полноразмерная история, полнотекстовый поиск через FTS5. |

Все бэкенды реализуют один и тот же контракт :class:`nexus.core.memory.MemoryStore` — выберите тот, который подходит для вашей задачи, и переключайтесь прямо во время выполнения (runtime), не меняя остальную часть кода.

## Оглавление

- [Использование JSON-хранилища по умолчанию](#использование-json-хранилища-по-умолчанию)
- [Переключение на SQLite](#переключение-на-sqlite)
- [Использование фабрики](#использование-фабрики)
- [Сравнение бэкендов](#сравнение-бэкендов)
  - [JSON Backend](#json-backend)
  - [SQLite Backend](#sqlite-backend)
- [Добавление кастомного бэкенда](#добавление-кастомного-бэкенда)
- [API](#api)
  - [MemoryStore](#memorystore)
  - [Exchange](#exchange)
  - [Фабрика](#фабрика)
- [Миграция между бэкендами](#миграция-между-бэкендами)
- [Troubleshooting](#troubleshooting)

---

## Использование JSON-хранилища по умолчанию

Прежнее поведение осталось неизменным — просто вызывайте :func:`nexus.core.history.add_exchange` и т. д., как и раньше. По умолчанию они используют JSON-хранилище, расположенное по пути `~/.nexus/conversation.json`.

```python
from nexus.core.history import add_exchange, build_context, clear

# Добавить обмен репликами
add_exchange("Привет!", "Здравствуйте! Чем могу помочь?")

# Получить контекст для LLM
context_text, exchanges = build_context(
    system_prompt="Ты полезный ассистент.",
    max_exchanges=5
)
print(context_text)

# Очистить историю
clear()
```

---

## Переключение на SQLite

```python
from nexus.core.history import set_default_store
from nexus.core.memory import SqliteMemoryStore

set_default_store(SqliteMemoryStore(path="~/.nexus/memory.db"))
```

Теперь каждый вызов функций `add_exchange`, `build_context` и `search` проходит через SQLite с поддержкой FTS5.

> **Примечание:** SQLite-хранилище автоматически создаёт необходимые таблицы и индексы при первом обращении.

---

## Использование фабрики

```python
from nexus.core.memory import create_memory_store

# JSON
store = create_memory_store("json", path="~/.nexus/conversation.json", max_exchanges=5)

# SQLite
store = create_memory_store("sqlite", path="~/.nexus/memory.db", max_exchanges=50)
```

Фабрика принимает те же именованные аргументы (keyword arguments), что и класс бэкенда.

---

## Сравнение бэкендов

### JSON Backend

**Класс:** `JsonMemoryStore`

**Хранилище:** Файл `conversation.json` в формате JSON

**Особенности:**
- Простой файловый формат, легко читается вручную
- Поиск через substring matching (регистронезависимый)
- Потокобезопасен (thread-safe) через `threading.Lock`
- Автоматическая обрезка до `max_exchanges` записей
- Устойчив к повреждению файла (возвращает пустой список)

**Пример данных:**
```json
[
  {"prompt": "Привет!", "response": "Здравствуйте!"},
  {"prompt": "Как дела?", "response": "Отлично, спасибо!"}
]
```

**Подходит для:**
- Небольших объёмов истории (< 1000 записей)
- Быстрого просмотра через `cat`, `grep`, `jq`
- Простых сценариев без полнотекстового поиска

### SQLite Backend

**Класс:** `SqliteMemoryStore`

**Хранилище:** SQLite база данных с FTS5

**Особенности:**
- Полнотекстовый поиск через FTS5 (Full-Text Search 5)
- BM25 ранжирование результатов
- Автоматический fallback на LIKE-поиск если FTS5 недоступен
- Автоматическое создание схемы (таблицы, триггеры, FTS-индексы)
- Потокобезопасен через `threading.Lock`
- Поддержка `:memory:` для in-memory базы

**Схема таблицы:**
```sql
CREATE TABLE exchanges (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt    TEXT    NOT NULL,
    response  TEXT    NOT NULL,
    created   REAL    NOT NULL DEFAULT (julianday('now'))
);

CREATE VIRTUAL TABLE exchanges_fts USING fts5(
    prompt, response, content='exchanges', content_rowid='id'
);
```

**Подходит для:**
- Большой истории (тысячи записей)
- Полнотекстового поиска с ранжированием
- Сценариев, где важна производительность запросов

---

## Добавление кастомного бэкенда

Создайте подкласс от :class:`MemoryStore` и реализуйте пять абстрактных методов:

```python
from nexus.core.memory import MemoryStore, Exchange

class RedisMemoryStore(MemoryStore):
    def __init__(self, url: str, max_exchanges: int = 5):
        self.url = url
        self.max_exchanges = max_exchanges
        # Подключение к Redis
        import redis
        self.client = redis.from_url(url)

    def add_exchange(self, prompt: str, response: str, max_exchanges: int = 5) -> None:
        """Сохранить новый обмен и обрезать до max_exchanges."""
        import json
        self.client.rpush("exchanges", json.dumps({
            "prompt": prompt,
            "response": response
        }))
        # Обрезка до max_exchanges
        total = self.client.llen("exchanges")
        if total > max_exchanges:
            self.client.ltrim("exchanges", total - max_exchanges, -1)

    def build_context(self, system_prompt=None, max_exchanges=5):
        """Вернуть строку контекста и список реплик."""
        import json
        items = self.client.lrange("exchanges", -max_exchanges, -1)
        exchanges = [Exchange.from_dict(json.loads(x)) for x in items]
        if not exchanges:
            return "", []
        parts = []
        if system_prompt:
            parts.append(f"System: {system_prompt}")
        parts.append(f"Below is the conversation history (last {len(exchanges)} exchanges):")
        for i, ex in enumerate(exchanges, 1):
            parts.append(f"\n--- Exchange {i} ---")
            parts.append(f"User: {ex.prompt}")
            parts.append(f"Assistant: {ex.response}")
        parts.append("\n--- End of history ---")
        return "\n".join(parts), exchanges

    def search(self, query: str, limit: int = 5):
        """Полнотекстовый поиск по обменам."""
        import json
        all_items = self.client.lrange("exchanges", 0, -1)
        results = []
        q = query.lower()
        for item in all_items:
            ex = Exchange.from_dict(json.loads(item))
            if q in ex.prompt.lower() or q in ex.response.lower():
                results.append(ex)
        return results[-limit:]

    def clear(self) -> None:
        """Удалить все обмены."""
        self.client.delete("exchanges")

    def count(self) -> int:
        """Вернуть количество обменов."""
        return self.client.llen("exchanges")
```

Затем подключите его:

```python
from nexus.core.history import set_default_store
set_default_store(RedisMemoryStore(url="redis://localhost"))
```

---

## API

### MemoryStore

Абстрактный базовый класс для всех хранилищ памяти.

| Метод | Описание |
|-------|----------|
| `add_exchange(prompt, response, max_exchanges=5)` | Сохранить новый обмен репликами (exchange); обрезать хранилище до последних N записей. |
| `build_context(system_prompt=None, max_exchanges=5) -> (str, list[Exchange])` | Вернуть строку контекста и список реплик (exchanges), использованных для ее создания. |
| `search(query, limit=5) -> list[Exchange]` | Вернуть реплики, соответствующие поисковому запросу *query*, отсортированные по релевантности. |
| `clear() -> None` | Удалить все сохраненные реплики. |
| `count() -> int` | Вернуть количество сохраненных реплик. |

> Все реализации являются **потокобезопасными** (thread-safe).

### Exchange

Датакласс, представляющий один обмен репликами:

```python
@dataclass
class Exchange:
    prompt: str      # Вопрос пользователя
    response: str    # Ответ ассистента

    def to_dict(self) -> dict:
        """Сериализация в словарь."""
        return {"prompt": self.prompt, "response": self.response}

    @classmethod
    def from_dict(cls, data: dict) -> "Exchange":
        """Десериализация из словаря."""
        return cls(
            prompt=str(data.get("prompt", "")),
            response=str(data.get("response", ""))
        )
```

### Фабрика

```python
def create_memory_store(backend: str = "json", **kwargs) -> MemoryStore:
    """
    Создать хранилище памяти по имени.

    Args:
        backend: "json" или "sqlite".
        **kwargs: Аргументы для конструктора (path, max_exchanges).

    Raises:
        ValueError: Если имя бэкенда неизвестно.
    """
```

---

## Миграция между бэкендами

### Из JSON в SQLite

```python
import json
import os
from nexus.core.memory import JsonMemoryStore, SqliteMemoryStore

# 1. Загрузить данные из JSON
json_store = JsonMemoryStore(path="~/.nexus/conversation.json")
exchanges = json_store._load(max_exchanges=999999)  # Все записи

# 2. Записать в SQLite
sqlite_store = SqliteMemoryStore(path="~/.nexus/memory.db")
for ex in exchanges:
    sqlite_store.add_exchange(ex.prompt, ex.response, max_exchanges=999999)

# 3. Переключить дефолтное хранилище
from nexus.core.history import set_default_store
set_default_store(sqlite_store)

print(f"Мигрировано {len(exchanges)} записей")
```

### Автоматическая миграция (переключение при старте)

Добавьте в начало вашего скрипта:

```python
from nexus.core.history import set_default_store
from nexus.core.memory import SqliteMemoryStore

# Всегда использовать SQLite
set_default_store(SqliteMemoryStore(
    path=os.path.expanduser("~/.nexus/memory.db"),
    max_exchanges=50
))
```

---

## Troubleshooting

### JSON файл повреждён

**Симптом:** История пуста, хотя файл существует.

**Решение:** JSON-хранилище устойчиво к повреждению — оно просто возвращает пустой список. Файл можно удалить и начать заново:

```bash
rm ~/.nexus/conversation.json
```

### SQLite: FTS5 недоступен

**Симптом:** Поиск работает медленно.

**Решение:** FTS5 может быть недоступен в некоторых сборках Python. Nexus автоматически fallback на LIKE-поиск. Для полной поддержки FTS5 используйте официальную сборку Python или скомпилируйте SQLite с поддержкой FTS5.

### Ошибка "database is locked"

**Симптом:** `sqlite3.OperationalError: database is locked`

**Решение:** Это происходит при одновременном доступе из нескольких процессов. SQLite поддерживает только один процесс записи. Используйте JSON-хранилище для многопроцессных сценариев или убедитесь, что只有一个 экземпляр Nexus работает одновременно.

### Не применяются изменения хранилища

**Решение:** Убедитесь, что вы вызвали `set_default_store()` **до** первого вызова `add_exchange()` или `build_context()`.