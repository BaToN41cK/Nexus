# Troubleshooting — Решение частых проблем

> 🔙 Назад → [README.md](README.md)

Это руководство покрывает **10 самых частых ошибок** при использовании Nexus и способы их решения. Если здесь нет ответа — откройте issue на [GitHub](https://github.com/BaToN41cK/Nexus/issues) с выводом `nexus debug`.

---

## 1. ❌ «API ключ не найден»

**Симптомы:**

```
❌ API ключ не найден. Проверьте .env файл или переменную окружения.
```

**Причины и решения:**

| Причина | Решение |
|---------|---------|
| Файл `~/.nexus/.env` не создан | `nexus debug` → посмотрите путь; создайте `~/.nexus/.env` |
| Ключ есть, но с пробелами вокруг `=` | `GROQ_API_KEY=gsk_...` (без пробелов) |
| Ключ установлен для другого провайдера | `provider: "groq"` в `~/.nexus/config.yaml` + `GROQ_API_KEY=...` |
| Ollama настроен, но `provider: "openai"` | Ollama не требует ключа — смените `provider: "ollama"` |
| Windows: `echo` добавил кавычки | Используйте PowerShell: `Set-Content` или текстовый редактор |

**Быстрая проверка:**

```bash
# Linux / macOS
cat ~/.nexus/.env

# Windows
type %USERPROFILE%\.nexus\.env
```

---

## 2. 🐢 Ответ от LLM очень медленный

**Симптомы:** Запрос `nexus run "..."` висит 30+ секунд.

**Причины и решения:**

- **Длинный контекст** — `nexus run` автоматически суммаризирует контент > 50 000 символов. Если промпт большой, добавьте `--no-cache` чтобы не загружать прошлый результат.
- **Медленный провайдер** — `nexus status` покажет, какая модель активна. Попробуйте `groq` (самый быстрый, бесплатный).
- **Сетевые задержки** — используйте прокси или VPN. Настройте `--timeout 120` (если поддерживается) или `timeout: 120` в `config.yaml`.
- **Много URL-ов в промпте** — `nexus run "https://a.com https://b.com https://c.com"` загружает их последовательно.

---

## 3. 🐍 «Python 3.9 or higher required»

**Симптомы:**

```
Nexus requires Python 3.9 or higher.
  You are running Python 3.8.10
```

**Решение:**

| Платформа | Действие |
|-----------|----------|
| Windows | Скачайте [Python 3.11+](https://www.python.org/downloads/) (при установке отметьте «Add Python to PATH») |
| macOS | `brew install python@3.11` |
| Ubuntu/Debian | `sudo apt install python3.11` |
| Используете `pyenv` | `pyenv install 3.11 && pyenv local 3.11` |

**Проверка:** `python --version` должно показать `3.9+`.

---

## 4. 🔌 «ModuleNotFoundError: No module named 'groq'»

**Симптомы:**

```
ModuleNotFoundError: No module named 'groq'
```

**Решение:**

```bash
# Только Groq (по умолчанию)
pip install nexus

# С OpenAI / Anthropic / Ollama / MCP
pip install "nexus[all]"

# Только один дополнительный
pip install "nexus[openai]"
```

**Проверка:** `pip show groq` должен показать версию.

---

## 5. 🌐 Web-поиск не работает (DuckDuckGo / Tavily)

**Симптомы:**

- `nexus run "..." --search` падает с ошибкой.
- `nexus search "..."` возвращает 0 результатов.

**Причины и решения:**

| Бэкенд | Нужен ключ? | Решение |
|--------|------------|---------|
| DuckDuckGo | Нет | Должен работать из коробки. Если не работает — за прокси/VPN. |
| Tavily | ✅ `TAVILY_API_KEY` | Зарегистрируйтесь на [tavily.com](https://tavily.com) |
| Bing | ✅ `BING_SEARCH_API_KEY` | Azure Bing API |
| SearXNG | ❌ | Нужен свой инстанс. Укажите `searxng_url` в конфиге. |

**Проверка:** `nexus search "test"` — должны появиться результаты.

---

## 6. 🎨 Баннер / эмодзи отображаются криво в Windows

**Симптомы:** В `cmd.exe` вместо эмодзи — `?` или квадраты.

**Решение:**

- **Лучший вариант:** используйте [Windows Terminal](https://aka.ms/terminal) вместо `cmd.exe`.
- **Быстрый фикс:** `nexus --banner classic` (использует только ASCII).
- **Глобально:** установите `NEXUS_BANNER=classic` в переменных среды.

---

## 7. 📁 «Permission denied» на `~/.nexus/.env`

**Симптомы (Linux/macOS):**

```
Permission denied: '/home/user/.nexus/.env'
```

**Решение:**

```bash
chmod 600 ~/.nexus/.env
chmod 700 ~/.nexus
```

**Проверка:** `ls -la ~/.nexus/.env` должно показать `-rw-------`.

---

## 8. 🔄 Кэш занимает слишком много места

**Симптомы:** `nexus status` показывает 100+ MB в кэше.

**Решение:**

```bash
# Очистить весь кэш + историю
nexus cache-clear

# Настроить лимит (по умолчанию 50 MB, в config.yaml)
cache:
  max_size_mb: 20
  ttl: 3600
```

Кэш автоматически очищается при превышении `max_cache_size_mb` (по умолчанию 50 MB).

---

## 9. 🛠 MCP-сервер не подключается в Claude Desktop / Cursor

**Симптомы:** Claude Desktop не видит инструменты Nexus.

**Решение:**

1. **Конфиг Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json` на macOS, `%APPDATA%\Claude\claude_desktop_config.json` на Windows):

   ```json
   {
     "mcpServers": {
       "nexus": {
         "command": "nexus",
         "args": ["mcp"]
       }
     }
   }
   ```

2. **Перезапустите** Claude Desktop / Cursor.

3. **Проверьте:** `nexus mcp` должен запускаться и ждать ввода (не падать).

4. **Полный путь** если `nexus` не в PATH:

   ```json
   {
     "mcpServers": {
       "nexus": {
         "command": "C:\\Users\\you\\AppData\\Roaming\\Python\\Python311\\Scripts\\nexus.exe",
         "args": ["mcp"]
       }
     }
   }
   ```

См. [docs/MCP.md](MCP.md) для деталей.

---

## 10. 🐞 `nexus debug` показывает ошибки

**Запустите:**

```bash
nexus debug
```

**Что покажет:**

- Версию Python, платформу, версию Nexus
- Загруженный конфиг (с маскированными секретами)
- Найденные API-ключи (замаскированы)
- Установленные SDK (groq, openai, anthropic, ollama)
- Доступность SQLite FTS5
- Прочее

**Приложите вывод** (без секретов) к issue на [GitHub](https://github.com/BaToN41cK/Nexus/issues).

---

## 🔍 Общее руководство по диагностике

1. **Запустите** `nexus debug` — соберёт всю нужную информацию.
2. **Включите verbose:** `nexus run "..." --verbose` — покажет HTTP-запросы.
3. **Проверьте логи** в `~/.nexus/history/history.log`.
4. **Сбросьте кэш:** `nexus cache-clear`.
5. **Проверьте версию:** `pip show nexus` — обновите при необходимости: `pip install --upgrade nexus`.

---

## 💬 Поддержка

- 📧 [Sergey.gerasimenko1208@gmail.com](mailto:Sergey.gerasimenko1208@gmail.com)
- ✈️ [@Baton41ck (Telegram)](https://t.me/Baton41ck)
- 🐛 [GitHub Issues](https://github.com/BaToN41cK/Nexus/issues)
