# Миграция между версиями

> 🔙 Назад → [README.md](README.md)

Руководство по миграции между версиями Nexus.

## Оглавление

- [Обзор](#обзор)
- [Миграция на текущую версию](#миграция-на-текущую-версию)
- [Изменения конфигурации](#изменения-конфигурации)
- [Миграция данных](#миграция-данных)
- [Депрекации](#депрекации)
- [Откат на предыдущую версию](#откат-на-предыдущую-версию)

---

## Обзор

Этот документ описывает, как мигрировать между версиями Nexus. Следуйте инструкциям для вашей версии.

---

## Миграция на текущую версию

### Шаг 1. Обновите Nexus

```bash
pip install --upgrade nexus
```

### Шаг 2. Проверьте изменения

```bash
nexus version
nexus debug
```

### Шаг 3. Обновите конфигурацию

Проверьте, есть ли новые параметры в `config/nexus.yaml` (в репозитории). Скопируйте новые параметры в `~/.nexus/config.yaml`.

### Шаг 4. Проверьте данные

```bash
nexus status
```

---

## Изменения конфигурации

### Новые параметры

При обновлении Nexus могут появляться новые параметры конфигурации. Они не являются обязательными — Nexus использует дефолтные значения.

**Пример:** Если в новой версии добавлен параметр `web_search.cache_ttl`, Nexus будет использовать значение по умолчанию (`3600`), если вы не укажете его в конфиге.

### Изменённые параметры

Если параметр переименован или изменён его тип, Nexus попытается конвертировать старое значение. Если конвертация невозможна, будет использовано значение по умолчанию.

### Удалённые параметры

Удалённые параметры игнорируются Nexus. Вы можете удалить их из конфига для чистоты.

---

## Миграция данных

### История диалога

#### Из JSON в SQLite

Если вы хотите переключиться на SQLite для истории диалога:

```python
import json
import os
from nexus.core.memory import JsonMemoryStore, SqliteMemoryStore

# 1. Загрузить данные из JSON
json_store = JsonMemoryStore(path=os.path.expanduser("~/.nexus/conversation.json"))
exchanges = json_store._load(max_exchanges=999999)  # Все записи

# 2. Записать в SQLite
sqlite_store = SqliteMemoryStore(path=os.path.expanduser("~/.nexus/memory.db"))
for ex in exchanges:
    sqlite_store.add_exchange(ex.prompt, ex.response, max_exchanges=999999)

# 3. Переключить дефолтное хранилище
from nexus.core.history import set_default_store
set_default_store(sqlite_store)

print(f"Мигрировано {len(exchanges)} записей")
```

#### Автоматическая миграция при старте

Добавьте в начало вашего скрипта:

```python
import os
from nexus.core.history import set_default_store
from nexus.core.memory import SqliteMemoryStore

# Всегда использовать SQLite
set_default_store(SqliteMemoryStore(
    path=os.path.expanduser("~/.nexus/memory.db"),
    max_exchanges=50
))
```

### Кэш

Кэш совместим между версиями. Нет необходимости очищать его при обновлении.

### История запросов

История запросов (`~/.nexus/history/history.log`) совместима между версиями.

---

## Депрекации

### Текущие депрекации

| Версия | Что deprecated | Когда удалится | Альтернатива |
|--------|----------------|----------------|--------------|
| 1.0.0 | Параметр `model` в конфиге | 2.0.0 | `groq_model` |
| 1.0.0 | Функция `get_conversation_history()` | 2.0.0 | `build_context()` |

### Как проверить депрекации

```bash
nexus --verbose run "тест"
```

В логах будут предупреждения о deprecated функциях.

---

## Откат на предыдущую версию

### Через pip

```bash
# Установить конкретную версию
pip install nexus==0.9.0

# Или из GitHub
pip install git+https://github.com/BaToN41cK/Nexus.git@v0.9.0
```

### Через pipx

```bash
pipx install nexus==0.9.0 --force
```

### Откат данных

Если данные повреждены при обновлении:

1. Остановите Nexus
2. Восстановите данные из бэкапа:
   ```bash
   cp -r ~/.nexus.backup ~/.nexus
   ```
3. Или очистите данные:
   ```bash
   nexus cache-clear
   rm -rf ~/.nexus/
   ```

---

## См. также

- [CHANGELOG.md](CHANGELOG.md) — история изменений
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) — справочник конфигурации
- [FAQ.md](FAQ.md) — частые вопросы