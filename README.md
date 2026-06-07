# Nexus — ИИ-ассистент

> 📖 Полная документация → [docs/README.md](docs/README.md)

**Nexus** — это Python-CLI, который общается с LLM (Groq, OpenAI, Anthropic, Ollama) и умеет подмешивать в ответ **актуальную информацию из интернета** через встроенный web-поиск.

## Возможности

- 💬 **LLM-провайдеры**: Groq (по умолчанию), OpenAI, Anthropic, локальный Ollama
- 🌐 **Web-поиск**: DuckDuckGo (без ключа), Tavily, SearXNG, Bing — через `nexus run "..." --search`
- 📄 **Загрузка контента** по URL: веб-страницы, YouTube, PDF, DOCX, PPTX, Excel, txt
- 🧠 **Контекст диалога**, история запросов, кэширование, стриминг ответов
- 🎨 **Rich UI**: Markdown, подсветка кода, прогресс-бары, панели

---

## 🚀 Быстрая установка для пользователей (одна команда)

### Шаг 1. Установить Nexus

Нужно: **Python 3.9 или новее** ([скачать](https://www.python.org/downloads/) — при установке отметьте «Add Python to PATH»).

Откройте терминал (`cmd` / `PowerShell` / `bash`) и выполните **одну** команду:

```bash
pip install nexus
```

> ℹ️ `pip` сам скачает и установит **все зависимости** (groq, requests, beautifulsoup4, rich, youtube-transcript-api, pypdf, python-docx, python-pptx, openpyxl и т.д.), создаст в `Scripts/`/`bin/` исполняемый файл `nexus.exe`/`nexus` и сразу же положит его в `PATH`. **Никаких ручных правок PATH не нужно** — после завершения `pip install` команда `nexus` доступна в новом терминале.

Если пакет ещё не опубликован на PyPI, поставьте напрямую с GitHub (одна команда, те же зависимости):

```bash
pip install git+https://github.com/BaToN41cK/Nexus.git
```

> 🔁 После публикации проекта на PyPI команда `pip install nexus` будет работать у всех пользователей «из коробки» — без клонирования и ручной сборки.

### Шаг 2. Получить API-ключ

Nexus работает через LLM-провайдеров. Самый быстрый старт — **Groq** (бесплатно, за 30 секунд):

1. Зайдите на [console.groq.com](https://console.groq.com) и зарегистрируйтесь
2. Перейдите в **API Keys → Create API Key**
3. Скопируйте ключ вида `gsk_...`

### Шаг 3. Сохранить ключ

**Windows (PowerShell / cmd):**
```powershell
mkdir %USERPROFILE%\.nexus
echo GROQ_API_KEY=gsk_ваш_ключ_сюда> %USERPROFILE%\.nexus\.env
```

**Linux / macOS (bash / zsh):**
```bash
mkdir -p ~/.nexus
echo "GROQ_API_KEY=gsk_ваш_ключ_сюда" > ~/.nexus/.env
```

> 💡 Если у вас уже есть ключ в системной переменной `GROQ_API_KEY`, дополнительный файл создавать не нужно — Nexus подхватит его автоматически.

### Шаг 4. Запустить!

```bash
# Проверить, что всё работает (покажет версии, конфиг, найденные ключи)
nexus doctor

# Первый запрос
nexus run "Привет! Что такое нейронные сети?"

# Запрос с актуальной информацией из интернета
nexus run "Что нового в Python 3.13?" --search

# Интерактивный диалог со стримингом и подсветкой кода
nexus interactive
```

**Готово.** Дальше `nexus doctor` поможет, если что-то пошло не так.

---

## 📦 Установка с дополнительными провайдерами

По умолчанию ставится только **Groq** (рекомендуемый). Чтобы добавить OpenAI / Anthropic / Ollama / MCP-сервер:

```bash
# Все опциональные зависимости разом
pip install "nexus[all]"

# Или по отдельности
pip install "nexus[openai]"        # OpenAI (gpt-4o, gpt-4o-mini, ...)
pip install "nexus[anthropic]"     # Anthropic (claude-sonnet-4, ...)
pip install "nexus[ollama]"        # Локальный Ollama
pip install "nexus[mcp]"           # MCP-сервер для Claude Desktop / Cursor
pip install "nexus[interactive]"   # Автодополнение в интерактивном режиме

# Комбинация (OpenAI + MCP):
pip install "nexus[openai,mcp]"
```

Из GitHub синтаксис тот же:

```bash
pip install "nexus[all] @ git+https://github.com/BaToN41cK/Nexus.git"
```

После установки не забудьте указать ключ в `~/.nexus/.env`:
```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

И выбрать провайдера в `~/.nexus/config.yaml`:
```yaml
provider: "openai"   # groq | openai | anthropic | ollama
groq_model: "gpt-4o-mini"   # используется как «основная модель» для всех провайдеров
```

---

## 🛠 Установка для разработчиков

Если вы хотите **править код** Nexus или собирать wheel/sdist:

```bash
git clone https://github.com/BaToN41cK/Nexus.git
cd Nexus

# Рекомендуется: виртуальное окружение
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# Установка в editable-режиме (правки в коде сразу видны)
pip install -e ".[all]"

# Быстрая сборка wheel и sdist
python -m pip install build
python -m build
```

Автоматические скрипты (venv + установка зависимостей + добавление в PATH):

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File scripts/install.ps1

# Linux / macOS
bash scripts/install.sh
```

---

## ⌨️ Краткая шпаргалка по командам

```bash
nexus run "запрос"              # одиночный запрос
nexus run "запрос" --search     # запрос + web-поиск
nexus run "..." --no-cache      # без сохранения в кэш
nexus interactive               # интерактивный диалог
nexus search "запрос"           # web-поиск без LLM
nexus search "запрос" --fetch   # поиск + прогон через LLM
nexus history                   # показать историю запросов
nexus status                    # показать кэш / историю / пути
nexus cache-clear               # очистить кэш и историю
nexus doctor                    # диагностика окружения
nexus version                   # версия
nexus --lang ru run "..."       # русский интерфейс
nexus --lang en run "..."       # английский интерфейс
nexus mcp                       # запустить MCP-сервер (stdio)
```

---

## 🔍 Что внутри

| Провайдер | Переменная           | Ключ нужен? |
|-----------|----------------------|-------------|
| Groq (по умолчанию) | `GROQ_API_KEY`   | ✅ |
| OpenAI    | `OPENAI_API_KEY`     | ✅ |
| Anthropic | `ANTHROPIC_API_KEY`  | ✅ |
| Ollama    | _не требуется_       | ❌ (локально) |

Полная документация — в [docs/README.md](docs/README.md).

## Документация

- [docs/README.md](docs/README.md) — полное руководство (установка, конфигурация, все команды, troubleshooting)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — архитектура проекта, диаграммы, паттерны проектирования
- [docs/EXAMPLES.md](docs/EXAMPLES.md) — реальные примеры использования (CLI, Python API, интеграция)
- [docs/MCP.md](docs/MCP.md) — MCP-сервер (интеграция с Claude Desktop, Cursor, Continue)
- [docs/MEMORY.md](docs/MEMORY.md) — подключаемая память (JSON/SQLite бэкенды)
- [docs/REACT.md](docs/REACT.md) — ReAct-агент (многошаговое рассуждение с инструментами)
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — участие в разработке
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — история изменений
- [docs/SECURITY.md](docs/SECURITY.md) — политика безопасности
</content>
</invoke>