# Система плагинов Nexus

> 🔙 Назад → [README.md](README.md)

Nexus поддерживает **расширение функциональности через плагины**. Плагин — это обычный Python-файл, расположенный в директории `~/.nexus/plugins/`, содержащий функцию `setup()`. Плагины позволяют:

- 🔌 Регистрировать **собственные LLM-провайдеры** (например, локальный Llama.cpp, LM Studio, vLLM)
- 🔍 Регистрировать **собственные поисковые бэкенды** (Google CSE, Brave, Kagi, Arxiv)
- 🛠 Регистрировать **собственные CLI-команды**
- 🪝 Подписываться на **lifecycle-хуки** (`pre_command`, `post_command`, `on_startup`, `on_shutdown`)

---

## Оглавление

- [Быстрый старт](#быстрый-старт)
- [Расположение и загрузка плагинов](#расположение-и-загрузка-плагинов)
- [Регистрация LLM-провайдера](#регистрация-llm-провайдера)
- [Регистрация поискового бэкенда](#регистрация-поискового-бэкенда)
- [Регистрация CLI-команд](#регистрация-cli-команд)
- [Lifecycle-хуки](#lifecycle-хуки)
- [API плагинов (полный справочник)](#api-плагинов-полный-справочник)
- [Безопасность](#безопасность)
- [Отладка плагинов](#отладка-плагинов)
- [Примеры плагинов](#примеры-плагинов)

---

## Быстрый старт

Создайте файл `~/.nexus/plugins/my_plugin.py`:

```python
# ~/.nexus/plugins/my_provider.py
from nexus.core.providers import BaseProvider
from nexus.core.plugin import register_provider, register_hook


class MyLLM(BaseProvider):
    name = "my_llm"

    def generate(self, prompt: str, **kwargs) -> str:
        # Здесь вызывается ваш собственный LLM API
        return f"echo: {prompt}"


def setup():
    register_provider(MyLLM)
    print("[my_provider] registered")
```

После этого при следующем запуске `nexus` провайдер `my_llm` станет доступен:

```bash
# В ~/.nexus/config.yaml
provider: "my_llm"
```

```bash
nexus run "Привет"
```

---

## Расположение и загрузка плагинов

### Директория по умолчанию

```
~/.nexus/plugins/
```

Любой файл с расширением `.py` (без префикса `_`) в этой директории считается плагином.

### Сканирование

1. При старте CLI Nexus сканирует `~/.nexus/plugins/`.
2. Для каждого `.py`-файла вызывается `importlib.util.spec_from_file_location()`.
3. Если в модуле определена функция `setup()`, она вызывается.
4. Все зарегистрированные провайдеры/бэкенды/команды/хуки становятся доступны немедленно.

### Ручной вызов

```python
from nexus.core.plugin import discover_plugins

loaded = discover_plugins()
print(loaded)  # ['my_provider', 'weather_tool', ...]
```

### Отключение проверки владельца (CI, Docker)

```python
loaded = discover_plugins(require_owned_by_user=False)
```

### Программный импорт конкретного плагина

```python
from nexus.core.plugin import discover_plugins
discover_plugins("/path/to/custom/plugins")
```

---

## Регистрация LLM-провайдера

```python
from nexus.core.providers import BaseProvider
from nexus.core.plugin import register_provider


class MyProvider(BaseProvider):
    name = "my_provider"   # используется в конфиге provider: "my_provider"

    def __init__(self, api_key: str = "", model: str = "default", **kwargs):
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        # Здесь логика вызова API
        ...

    def generate_stream(self, prompt: str, system_prompt: str = "", **kwargs):
        # Опционально: стриминг токенов
        for token in my_api.stream(prompt):
            yield token


def setup():
    register_provider(MyProvider)
```

После установки в `~/.nexus/config.yaml`:

```yaml
provider: "my_provider"
groq_model: "my_model_name"   # имя модели для вашего провайдера
```

### Минимальный контракт `BaseProvider`

| Атрибут/Метод | Тип | Описание |
|---------------|-----|----------|
| `name` | `str` (атрибут класса) | Уникальное имя провайдера |
| `generate(prompt, system_prompt, **kwargs) -> str` | метод | Синхронная генерация |
| `generate_stream(prompt, system_prompt, **kwargs) -> Iterator[str]` | метод (опц.) | Стриминг токенов |

---

## Регистрация поискового бэкенда

```python
from nexus.core.web_search import SearchBackend, SearchResult
from nexus.core.plugin import register_search_backend


class MySearch(SearchBackend):
    name = "my_search"

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        # Здесь вызов вашего поисковика
        return [
            SearchResult(title="...", url="https://...", snippet="..."),
            ...
        ]


def setup():
    register_search_backend(MySearch)
```

Затем в конфиге:

```yaml
web_search:
  backend: "my_search"   # или "auto" — ваш бэкенд будет добавлен в авто-цепочку
```

### Контракт `SearchBackend`

| Атрибут/Метод | Тип | Описание |
|---------------|-----|----------|
| `name` | `str` (атрибут класса) | Уникальное имя бэкенда |
| `search(query, max_results=5) -> list[SearchResult]` | метод | Возвращает список `SearchResult` |
| `fetch(url, timeout=15) -> str` | метод (опц.) | Загрузка содержимого страницы |

---

## Регистрация CLI-команд

```python
from nexus.core.plugin import register_cli_command


def my_command(args):
    """Handler принимает распарсенные аргументы argparse.Namespace."""
    print(f"Hello, {args.name}!")


def setup():
    register_cli_command(
        name="hello",
        help_text="Say hello to someone",
        handler=my_command,
    )
```

После загрузки плагина команда доступна как:

```bash
nexus hello --name World
```

> ℹ️ Кастомные команды наследуют все глобальные флаги (`--verbose`, `--config`, `--lang`, `--banner`).

---

## Lifecycle-хуки

Nexus вызывает зарегистрированные хуки в определённые моменты:

| Хук | Когда вызывается | Аргументы |
|-----|------------------|-----------|
| `on_startup` | При запуске CLI (до парсинга аргументов) | — |
| `pre_command` | Перед выполнением команды | `args: argparse.Namespace` |
| `post_command` | После выполнения команды | `args: argparse.Namespace`, `result` |
| `on_shutdown` | При завершении CLI | — |

### Пример: метрики и логирование

```python
import time
from nexus.core.plugin import register_hook


def on_startup():
    print("[my_plugin] Nexus started")


def pre_command(args):
    args._my_plugin_start = time.monotonic()


def post_command(args, result=None):
    elapsed = time.monotonic() - getattr(args, "_my_plugin_start", time.monotonic())
    print(f"[my_plugin] {args.command} took {elapsed:.2f}s")


def setup():
    register_hook("on_startup", on_startup)
    register_hook("pre_command", pre_command)
    register_hook("post_command", post_command)
```

---

## API плагинов (полный справочник)

```python
# nexus.core.plugin

register_provider(provider_cls)          # -> None
register_search_backend(backend_cls)     # -> None
register_cli_command(name, help_text, handler)  # -> None
register_hook(hook_name, fn)             # -> None

run_hook(hook_name, *args, **kwargs)     # -> None (внутреннее; не нужно вызывать из плагинов)
discover_plugins(plugin_dir=None, *, require_owned_by_user=True) -> list[str]
get_loaded_plugins() -> dict[str, ModuleType]
list_custom_commands() -> dict[str, dict]
```

### Исключения

- `register_search_backend` бросает `ValueError`, если бэкенд с таким именем уже зарегистрирован.
- `register_search_backend` бросает `TypeError`, если класс не наследует `SearchBackend`.
- `register_hook` бросает `ValueError`, если имя хука неизвестно.

---

## Безопасность

> ⚠️ **Плагины выполняются с полными привилегиями текущего пользователя.** Устанавливайте плагины только из источников, которым доверяете.

### Встроенная защита

1. **Проверка владельца файла** (POSIX). На Unix-системах Nexus сравнивает `st_uid` каждого `.py`-файла в `~/.nexus/plugins/` с `os.getuid()`. Если владелец не совпадает — файл пропускается с предупреждением.
2. **Изоляция ошибок**. Если `setup()` бросает исключение — плагин не загружается, но CLI продолжает работу.
3. **Изоляция хуков**. Если хук бросает исключение — оно логируется, но не прерывает основную команду.

### Рекомендации

- Устанавливайте плагины **только** из надёжных источников.
- Проверяйте исходный код плагина перед копированием в `~/.nexus/plugins/`.
- В CI/Docker отключайте проверку владельца через `require_owned_by_user=False`.
- Для production-окружений рассмотрите возможность **точечного импорта** нужных модулей (без `discover_plugins`).

### Отключение проверки владельца

В Docker-контейнерах, где все файлы принадлежат `root`, проверка `st_uid` не блокирует плагины. Если вы хотите отключить её явно (например, в CI):

```python
# В вашем CI-скрипте
from nexus.core.plugin import discover_plugins
discover_plugins(require_owned_by_user=False)
```

---

## Отладка плагинов

### Логирование

Плагины используют стандартный `logging`:

```python
import logging
logger = logging.getLogger(__name__)

def setup():
    logger.info("my_plugin loaded")
```

Запустите Nexus с `--verbose` для отладки:

```bash
nexus --verbose run "Привет"
```

### Частые ошибки

| Симптом | Причина | Решение |
|---------|---------|---------|
| Плагин не загружается | Файл начинается с `_` | Переименуйте `__my_plugin.py` → `my_plugin.py` |
| Плагин не загружается | Не определена `setup()` | Добавьте функцию `def setup():` |
| `ValueError: backend already registered` | Дублирование имени | Используйте уникальный `name` |
| `TypeError: must inherit from SearchBackend` | Неправильный базовый класс | Унаследуйте от `SearchBackend` |
| На Unix плагин пропускается с предупреждением | Владелец файла не совпадает с текущим пользователем | `chown $USER ~/.nexus/plugins/my_plugin.py` |

### Программная проверка

```python
from nexus.core.plugin import discover_plugins, get_loaded_plugins

loaded = discover_plugins()
print("Loaded:", loaded)
print("Modules:", list(get_loaded_plugins().keys()))
```

---

## Примеры плагинов

### Пример 1. Локальный Llama.cpp

```python
# ~/.nexus/plugins/llamacpp.py
import requests
from nexus.core.providers import BaseProvider
from nexus.core.plugin import register_provider


class LlamaCppProvider(BaseProvider):
    name = "llamacpp"

    def __init__(self, api_key: str = "", model: str = "local", base_url: str = "http://localhost:8080", **kwargs):
        self.base_url = base_url
        self.model = model

    def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        r = requests.post(
            f"{self.base_url}/completion",
            json={"prompt": full_prompt, "n_predict": 512},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["content"]

    def generate_stream(self, prompt: str, system_prompt: str = "", **kwargs):
        # Простой стриминг по словам для демонстрации
        text = self.generate(prompt, system_prompt, **kwargs)
        for word in text.split(" "):
            yield word + " "


def setup():
    register_provider(LlamaCppProvider)
```

Конфиг:

```yaml
provider: "llamacpp"
groq_model: "local"
base_url: "http://localhost:8080"
```

### Пример 2. Поиск через Brave Search API

```python
# ~/.nexus/plugins/brave.py
import os
import requests
from nexus.core.web_search import SearchBackend, SearchResult
from nexus.core.plugin import register_search_backend


class BraveSearch(SearchBackend):
    name = "brave"

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        api_key = os.getenv("BRAVE_API_KEY", "")
        if not api_key:
            return []
        r = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"X-Subscription-Token": api_key},
            timeout=10,
        )
        r.raise_for_status()
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
            )
            for item in r.json().get("web", {}).get("results", [])
        ]


def setup():
    register_search_backend(BraveSearch)
```

Конфиг:

```yaml
web_search:
  backend: "brave"   # или "auto"
```

### Пример 3. Кастомная команда `nexus stats-clear`

```python
# ~/.nexus/plugins/stats_clear.py
import os
from nexus.core.paths import NEXUS_DIR
from nexus.core.plugin import register_cli_command


def stats_clear_handler(args):
    usage_file = os.path.join(NEXUS_DIR, "usage_stats.json")
    if os.path.isfile(usage_file):
        os.remove(usage_file)
        print("✅ Usage statistics cleared")
    else:
        print("ℹ️  No usage statistics to clear")


def setup():
    register_cli_command(
        name="stats-clear",
        help_text="Clear usage statistics",
        handler=stats_clear_handler,
    )
```

### Пример 4. Хук для отправки телеметрии

```python
# ~/.nexus/plugins/telemetry.py
import logging
import requests
from nexus.core.plugin import register_hook

logger = logging.getLogger(__name__)
ENDPOINT = "https://example.com/telemetry"


def post_command(args, result=None):
    try:
        requests.post(
            ENDPOINT,
            json={
                "command": getattr(args, "command", None),
                "ts": time.time(),
            },
            timeout=2,
        )
    except Exception as e:
        logger.debug("telemetry failed: %s", e)


def setup():
    register_hook("post_command", post_command)
```

---

## Дистрибуция плагинов

Рекомендуемый способ распространения плагина — обычный Python-пакет, при установке которого пользователь сам копирует файл в `~/.nexus/plugins/` (или использует `entry_points` — см. ниже).

### Через `entry_points` (для авторов пакетов)

В `pyproject.toml` вашего плагина добавьте:

```toml
[project.entry-points."nexus.plugins"]
my_plugin = "my_plugin_pkg.module:register"
```

После `pip install my-plugin` Nexus автоматически обнаружит плагин через `importlib.metadata.entry_points()`.

### Рекомендуемая структура пакета-плагина

```
nexus-plugin-brave/
├── pyproject.toml
├── README.md
└── src/
    └── nexus_plugin_brave/
        ├── __init__.py
        └── brave.py   # с функцией register() = setup()
```

---

## См. также

- [docs/ADVANCED_USAGE.md](ADVANCED_USAGE.md) — продвинутые сценарии (кастомные провайдеры, пайплайны)
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — архитектура Nexus
- [docs/CONTRIBUTING.md](CONTRIBUTING.md) — контрибуция в ядро
- [docs/API.md](API.md) — Python API
