# Переменные окружения

> 🔙 Назад → [README.md](README.md)

Полный справочник всех переменных окружения, используемых Nexus.

## Оглавление

- [API-ключи провайдеров](#api-ключи-провайдеров)
- [API-ключи поисковиков](#api-ключи-поисковиков)
- [Системные переменные Nexus](#системные-переменные-nexus)
- [HTTP и сеть](#http-и-сеть)
- [Python](#python)
- [Другие](#другие)
- [Приоритет переменных](#приоритет-переменных)
- [Настройка переменных](#настройка-переменных)

---

## API-ключи провайдеров

| Переменная | Провайдер | Формат | Описание | Получение |
|------------|-----------|--------|----------|-----------|
| `GROQ_API_KEY` | Groq | `gsk_...` | API-ключ Groq | [console.groq.com](https://console.groq.com) |
| `OPENAI_API_KEY` | OpenAI | `sk-...` | API-ключ OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | Anthropic | `sk-ant-...` | API-ключ Anthropic | [console.anthropic.com](https://console.anthropic.com) |

---

## API-ключи поисковиков

| Переменная | Бэкенд | Формат | Описание | Получение |
|------------|--------|--------|----------|-----------|
| `TAVILY_API_KEY` | Tavily | `tvly-...` | API-ключ Tavily | [tavily.com](https://tavily.com) |
| `BING_API_KEY` | Bing | строка | API-ключ Azure Bing | Azure Portal |
| `SEARXNG_URL` | SearXNG | URL | URL экземпляра SearXNG | Self-hosted или публичный |

---

## Системные переменные Nexus

| Переменная | Тип | Дефолт | Описание |
|------------|-----|--------|----------|
| `NEXUS_LANG` | `ru` или `en` | авто | Язык интерфейса (перекрывает автоопределение) |
| `NEXUS_ENV_PATH` | путь | авто | Путь к файлу `.env` |
| `NEXUS_CONFIG` | путь | авто | Путь к файлу конфигурации `config.yaml` |

---

## HTTP и сеть

| Переменная | Тип | Описание |
|------------|-----|----------|
| `HTTP_PROXY` | URL | HTTP-прокси для запросов |
| `HTTPS_PROXY` | URL | HTTPS-прокси для запросов |
| `NO_PROXY` | список | Исключения из прокси (через запятую) |

### Примеры

```bash
# Установка прокси
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
export NO_PROXY=localhost,127.0.0.1,.example.com

# Или через .env файл
HTTP_PROXY=http://proxy.example.com:8080
HTTPS_PROXY=http://proxy.example.com:8080
NO_PROXY=localhost,127.0.0.1,.example.com
```

---

## Python

| Переменная | Описание |
|------------|----------|
| `PYTHONPATH` | Путь к Python-модулям (для development) |
| `VIRTUAL_ENV` | Путь к виртуальному окружению |
| `PYTHONDONTWRITEBYTECODE` | Отключить создание .pyc файлов |

---

## Другие

| Переменная | Описание |
|------------|----------|
| `HOME` | Домашняя директория (Linux/macOS) |
| `USERPROFILE` | Домашняя директория (Windows) |
| `NO_COLOR` | Отключить цвета в выводе (любое значение) |
| `TERM` | Тип терминала |

---

## Приоритет переменных

### API-ключи

1. Файл `.env` (приоритет最高的)
2. Переменные окружения
3. Конфигурация (если поддерживается)

### Язык

1. `NEXUS_LANG` (наивысший приоритет)
2. CLI-флаг `--lang`
3. Системная локаль
4. `"en"` (fallback)

### Конфигурация

1. CLI-флаг `--config`
2. `NEXUS_CONFIG`
3. `~/.nexus/config.yaml`
4. `config/nexus.yaml` (дефолтный шаблон)

---

## Настройка переменных

### Linux / macOS

```bash
# временно (текущая сессия)
export GROQ_API_KEY=gsk_ваш_ключ

# навсегда (добавить в ~/.bashrc, ~/.zshrc, ~/.profile)
echo 'export GROQ_API_KEY=gsk_ваш_ключ' >> ~/.bashrc
source ~/.bashrc

# или через .env файл
mkdir -p ~/.nexus
echo "GROQ_API_KEY=gsk_ваш_ключ" > ~/.nexus/.env
```

### Windows (PowerShell)

```powershell
# временно (текущая сессия)
$env:GROQ_API_KEY = "gsk_ваш_ключ"

# навсегда (пользовательская переменная)
[System.Environment]::SetEnvironmentVariable("GROQ_API_KEY", "gsk_ваш_ключ", "User")

# или через .env файл
mkdir -p $env:USERPROFILE\.nexus
"GROQ_API_KEY=gsk_ваш_ключ" | Out-File -FilePath $env:USERPROFILE\.nexus\.env -Encoding utf8
```

### Windows (cmd)

```cmd
:: временно (текущая сессия)
set GROQ_API_KEY=gsk_ваш_ключ

:: навсегда (пользовательская переменная)
setx GROQ_API_KEY "gsk_ваш_ключ"
```

---

## Проверка переменных

```bash
# Проверить переменную
echo $GROQ_API_KEY
echo $OPENAI_API_KEY

# Проверить все переменные Nexus
env | grep -i nexus
env | grep -i api_key

# Проверить через Nexus
nexus debug
nexus status
```

---

## Troubleshooting

### `API ключ не найден`

```bash
# Проверьте переменную
echo $GROQ_API_KEY

# Или проверьте .env файл
cat ~/.nexus/.env

# Запустите диагностику
nexus debug
```

### Переменная не применяется

1. Убедитесь, что переменная экспортирована: `export GROQ_API_KEY=...`
2. Перезапустите терминал
3. Проверьте: `echo $GROQ_API_KEY`

### Конфликт переменных

Если Nexus находит несколько API-ключей, приоритет:
1. `GROQ_API_KEY` (для Groq)
2. `OPENAI_API_KEY` (для OpenAI)
3. `ANTHROPIC_API_KEY` (для Anthropic)

---

## См. также

- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) — справочник конфигурации
- [CLI_REFERENCE.md](CLI_REFERENCE.md) — справочник CLI
- [FAQ.md](FAQ.md) — частые вопросы