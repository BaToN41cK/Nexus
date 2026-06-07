# Установка Nexus

> 🔙 Назад → [README.md](README.md)

Полное руководство по установке Nexus на различных платформах.

## Оглавление

- [Требования](#требования)
- [Установка через pip (рекомендуется)](#установка-через-pip)
- [Установка через pipx (изолированный режим)](#установка-через-pipx)
- [Установка через uv (быстрая)](#установка-через-uv)
- [Установка из GitHub](#установка-из-github)
- [Установка для разработчиков](#установка-для-разработчиков)
- [Платформо-зависимая установка](#платформо-зависимая-установка)
  - [Windows](#windows)
  - [macOS](#macos)
  - [Linux](#linux)
- [Установка через Docker](#установка-через-docker)
- [Дополнительные провайдеры](#дополнительные-провайдеры)
- [Настройка API-ключа](#настройка-api-ключа)
- [Проверка установки](#проверка-установки)
- [Обновление Nexus](#обновление-nexus)
- [Удаление Nexus](#удаление-nexus)
- [Troubleshooting](#troubleshooting)

---

## Требования

| Требование | Минимальное | Рекомендуемое |
|------------|-------------|---------------|
| Python | 3.9+ | 3.11+ |
| pip | 21.0+ | Последняя версия |
| ОС | Windows 10+, macOS 12+, Linux (x86_64/arm64) | Последняя версия |
| RAM | 512 МБ | 1 ГБ+ |
| Диск | 50 МБ | 100 МБ+ |

---

## Установка через pip

### Базовая установка (Groq)

```bash
pip install nexus
```

> ℹ️ `pip` сам установит все зависимости (groq, requests, beautifulsoup4, rich, youtube-transcript-api, pypdf, python-docx, python-pptx, openpyxl) и создаст исполняемый файл `nexus` в `PATH`.

### С дополнительными провайдерами

```bash
# Все зависимости разом
pip install "nexus[all]"

# OpenAI
pip install "nexus[openai]"

# Anthropic
pip install "nexus[anthropic]"

# Локальный Ollama
pip install "nexus[ollama]"

# MCP-сервер (Claude Desktop, Cursor, Continue)
pip install "nexus[mcp]"

# Автодополнение в интерактивном режиме
pip install "nexus[interactive]"

# Комбинация
pip install "nexus[openai,mcp]"
```

---

## Установка через pipx

[pipx](https://pypa.github.io/pipx/) — инструмент для установки Python-приложений в изолированные окружения (рекомендуется для системных инструментов):

```bash
# Установка pipx (если не установлен)
pip install pipx

# Установка Nexus в изолированном окружении
pipx install nexus

# С дополнительными зависимостями
pipx install "nexus[all]"

# Обновление
pipx upgrade nexus
```

---

## Установка через uv

[uv](https://github.com/astral-sh/uv) — ультрабыстрый менеджер пакетов (10-100x быстрее pip):

```bash
# Установка uv (если не установлен)
curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/macOS
# или
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# Установка Nexus
uv pip install nexus

# Или запуск напрямую
uv tool install nexus
uv tool run nexus run "Привет!"
```

---

## Установка из GitHub

### Последняя версия из main

```bash
pip install git+https://github.com/BaToN41cK/Nexus.git
```

### С дополнительными зависимостями из GitHub

```bash
pip install "nexus[all] @ git+https://github.com/BaToN41cK/Nexus.git"
```

### Конкретная версия/ветка/коммит

```bash
# Конкретная ветка
pip install git+https://github.com/BaToN41cK/Nexus.git@main

# Конкретный тег
pip install git+https://github.com/BaToN41cK/Nexus.git@v1.0.0

# Конкретный коммит
pip install git+https://github.com/BaToN41cK/Nexus.git@c0b2e26
```

### Клонирование для установки

```bash
git clone https://github.com/BaToN41cK/Nexus.git
cd Nexus
pip install -e .
# или с опциональными зависимостями
pip install -e ".[all]"
```

---

## Установка для разработчиков

```bash
# 1. Клонировать репозиторий
git clone https://github.com/BaToN41cK/Nexus.git
cd Nexus

# 2. Создать виртуальное окружение
python -m venv venv

# 3. Активировать
# Windows (PowerShell)
venv\Scripts\Activate.ps1
# Windows (cmd)
venv\Scripts\activate.bat
# Linux / macOS
source venv/bin/activate

# 4. Установить в editable-режиме
pip install -e ".[all]"

# 5. Установить dev-зависимости
pip install pytest pytest-cov flake8 black isort mypy pre-commit

# 6. Установить pre-commit хуки
pre-commit install

# 7. (Опционально) Собрать дистрибутив
python -m pip install build
python -m build
```

---

## Платформо-зависимая установка

### Windows

#### pip (стандартный способ)

```powershell
pip install nexus
```

#### Windows Package Manager (winget)

```powershell
winget install Python.Python.3.12  # если Python не установлен
pip install nexus
```

#### Chocolatey

```powershell
choco install python  # если Python не установлен
pip install nexus
```

#### Scoop

```powershell
scoop bucket add extras
scoop install python  # если Python не установлен
pip install nexus
```

#### Скрипт установки (PowerShell)

```powershell
# Скачать и запустить скрипт установки
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
```

### macOS

#### pip

```bash
pip install nexus
```

#### Homebrew

```bash
brew install python  # если Python не установлен
pip install nexus
```

#### Скрипт установки (bash)

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

### Linux

#### pip

```bash
pip install nexus
```

#### APT (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
pip install nexus
```

#### DNF (Fedora/RHEL)

```bash
sudo dnf install python3 python3-pip
pip install nexus
```

#### Pacman (Arch/Manjaro)

```bash
sudo pacman -S python python-pip
pip install nexus
```

#### AUR (Arch/Manjaro)

```bash
# Если доступен AUR-пакет (проверьте availability)
yay -S nexus  # или paru -S nexus
```

#### Snap

```bash
sudo snap install nexus  # если доступен в Snap Store
```

#### Flatpak

```bash
flatpak install nexus  # если доступен в Flathub
```

#### Скрипт установки

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

---

## Установка через Docker

### Сборка образа

```bash
docker build -f docker/Dockerfile -t nexus .
```

### Запуск

```bash
# Одиночный запрос
docker run --rm -e GROQ_API_KEY=your_key nexus run "Привет!"

# Интерактивный режим
docker run --rm -it -e GROQ_API_KEY=your_key nexus interactive

# С mount конфига и кэша
docker run --rm \
  -e GROQ_API_KEY=your_key \
  -v ~/.nexus:/root/.nexus \
  nexus run "Что нового в Python?"
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  nexus:
    build:
      context: .
      dockerfile: docker/Dockerfile
    environment:
      - GROQ_API_KEY=${GROQ_API_KEY}
    volumes:
      - ~/.nexus:/root/.nexus
    stdin_open: true
    tty: true
```

```bash
# Запуск
docker-compose run --rm nexus interactive
```

---

## Дополнительные провайдеры

### OpenAI

```bash
pip install "nexus[openai]"
```

Добавьте в `~/.nexus/.env`:

```
OPENAI_API_KEY=sk-...
```

### Anthropic

```bash
pip install "nexus[anthropic]"
```

Добавьте в `~/.nexus/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### Ollama (локальный)

```bash
pip install "nexus[ollama]"
```

```bash
# Установите Ollama: https://ollama.com
ollama serve  # запустите сервер
ollama pull llama3.2  # скачайте модель
```

### MCP-сервер

```bash
pip install "nexus[mcp]"
```

---

## Настройка API-ключа

### Шаг 1. Получите ключ

| Провайдер | Где получить ключ |
|-----------|-------------------|
| Groq (рекомендуется) | [console.groq.com](https://console.groq.com) → API Keys → Create API Key |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) |
| Ollama | не нужен (работает локально) |

### Шаг 2. Сохраните ключ

**Вариант A: Файл `.env` (рекомендуется)**

```bash
mkdir -p ~/.nexus
echo "GROQ_API_KEY=gsk_ваш_ключ" > ~/.nexus/.env
```

**Вариант B: Переменная окружения**

```bash
# Linux / macOS (~/.bashrc, ~/.zshrc, ~/.profile)
export GROQ_API_KEY=gsk_ваш_ключ

# Windows (PowerShell)
[System.Environment]::SetEnvironmentVariable("GROQ_API_KEY", "gsk_ваш_ключ", "User")
```

### Шаг 3. Проверьте

```bash
nexus test
```

---

## Проверка установки

```bash
# Версия Nexus
nexus version

# Диагностика окружения
nexus debug

# Тестовый запрос
nexus run "Привет! Что такое нейронные сети?"

# Тестовый запрос с поиском
nexus run "Что нового в Python 3.13?" --search
```

---

## Обновление Nexus

### Через pip

```bash
pip install --upgrade nexus
# или
pip install -U nexus
```

### Через pipx

```bash
pipx upgrade nexus
```

### Через uv

```bash
uv tool upgrade nexus
```

### Из GitHub (обновление до последней версии)

```bash
pip install --upgrade git+https://github.com/BaToN41cK/Nexus.git
```

---

## Удаление Nexus

### Через pip

```bash
pip uninstall nexus
```

### Через pipx

```bash
pipx uninstall nexus
```

### Удаление данных

```bash
# Удалить все данные Nexus (конфиг, кэш, история, память)
nexus cache-clear

# Или вручную
rm -rf ~/.nexus/
```

---

## Troubleshooting

### `pip: command not found`

**Решение:** Установите Python с [python.org](https://www.python.org/downloads/) (отметьте «Add Python to PATH» при установке).

### `nexus: command not found`

**Решение:**
1. Убедитесь, что `pip` установлен в то же окружение, что и Python
2. Проверьте, что `Scripts/` (Windows) или `bin/` (Linux/macOS) находится в `PATH`
3. Попробуйте: `python -m nexus`

### `Permission denied`

**Решение:**
```bash
# Не используйте sudo с pip
# Вместо этого используйте виртуальное окружение
python -m venv venv
source venv/bin/activate  # или venv\Scripts\activate
pip install nexus
```

### `ERROR: Could not find a version that satisfies the requirement`

**Решение:**
1. Обновите pip: `pip install --upgrade pip`
2. Проверьте версию Python: `python --version` (нужен 3.9+)
3. Попробуйте установить из GitHub: `pip install git+https://github.com/BaToN41cK/Nexus.git`

### `ERROR: No matching distribution found for`

**Решение:** Версия Python слишком старая. Обновите Python до 3.9+.

### Проблемы с прокси

```bash
pip install --proxy http://proxy:port nexus
# или
pip install --proxy socks5://proxy:port nexus
```

### Проблемы с SSL

```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org nexus
```

---

## См. также

- [README.md](README.md) — общее руководство
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) — справочник конфигурации
- [FAQ.md](FAQ.md) — частые вопросы