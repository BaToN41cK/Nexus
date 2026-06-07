# Развёртывание окружения разработчика

> 🔙 Назад → [README.md](README.md)

Подробное руководство по настройке окружения для разработки Nexus.

## Оглавление

- [Требования](#требования)
- [Установка](#установка)
- [Инструменты разработки](#инструменты-разработки)
- [Pre-commit хуки](#pre-commit-хуки)
- [Запуск тестов](#запуск-тестов)
- [Форматирование кода](#форматирование-кода)
- [Проверка типов](#проверка-типов)
- [Сборка пакета](#сборка-пакета)
- [Релиз](#релиз)
- [Troubleshooting](#troubleshooting)

---

## Требования

| Инструмент | Версия | Описание |
|------------|--------|----------|
| Python | 3.9+ | Рекомендуется 3.11+ |
| pip | 21.0+ | Менеджер пакетов |
| git | 2.0+ | Контроль версий |
| pre-commit | 3.0+ | Хуки перед коммитом |

---

## Установка

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/BaToN41cK/Nexus.git
cd Nexus
```

### 2. Создайте виртуальное окружение

```bash
python -m venv venv
```

### 3. Активируйте окружение

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```

**Windows (cmd):**
```cmd
venv\Scripts\activate.bat
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

### 4. Установите зависимости

```bash
# Основные зависимости
pip install -e .

# Все зависимости (включая опциональные)
pip install -e ".[all]"

# Dev-зависимости
pip install pytest pytest-cov flake8 black isort mypy pre-commit
```

### 5. Установите pre-commit хуки

```bash
pre-commit install
```

---

## Инструменты разработки

### Black (форматирование)

```bash
# Форматирование всего кода
black nexus/ tests/

# Проверка без изменений
black --check nexus/ tests/

# Форматирование конкретного файла
black nexus/core/agent.py
```

### isort (сортировка импортов)

```bash
# Сортировка импортов
isort nexus/ tests/

# Проверка без изменений
isort --check-only nexus/ tests/
```

### Flake8 (проверка стиля)

```bash
# Проверка стиля
flake8 nexus/ tests/

# С исправлением авто-fixable проблем
flake8 --extend-ignore=E203,W503 nexus/ tests/
```

### mypy (проверка типов)

```bash
# Проверка типов
mypy nexus/

# С исправлением
mypy --ignore-missing-imports nexus/
```

### pytest (тесты)

```bash
# Запуск тестов
python -m pytest tests/ -v

# С покрытием
python -m pytest tests/ --cov=nexus --cov-report=html

# С остановкой на ошибке
python -m pytest tests/ -x
```

---

## Pre-commit хуки

### Установка

```bash
pip install pre-commit
pre-commit install
```

### Конфигурация (.pre-commit-config.yaml)

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
  
  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
  
  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.3.0
    hooks:
      - id: mypy
```

### Запуск вручную

```bash
# Все хуки
pre-commit run --all-files

# Конкретный хук
pre-commit run black --all-files
pre-commit run isort --all-files
pre-commit run flake8 --all-files
pre-commit run mypy --all-files
```

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

### С покрытием

```bash
python -m pytest tests/ --cov=nexus --cov-report=html
# Откройте htmlcov/index.html
```

### Параллельный запуск

```bash
python -m pytest tests/ -n auto
```

---

## Форматирование кода

### Автоматическое форматирование

```bash
# Форматирование всего кода
black nexus/ tests/
isort nexus/ tests/

# Или через Makefile (если есть)
make format
```

### Проверка форматирования

```bash
black --check nexus/ tests/
isort --check-only nexus/ tests/
```

---

## Проверка типов

### Запуск mypy

```bash
mypy nexus/
```

### Конфигурация mypy (mypy.ini)

```ini
[mypy]
python_version = 3.9
warn_return_any = True
warn_unused_configs = True
ignore_missing_imports = True
```

---

## Сборка пакета

### Установка build

```bash
pip install build
```

### Сборка wheel и sdist

```bash
python -m build
```

### Результат

```
dist/
├── nexus-1.0.0-py3-none-any.whl
└── nexus-1.0.0.tar.gz
```

### Установка из собранного пакета

```bash
pip install dist/nexus-1.0.0-py3-none-any.whl
```

---

## Релиз

### Процесс релиза

1. Обновите версию в `nexus/__init__.py`
2. Обновите `CHANGELOG.md`
3. Создайте коммит
4. Создайте тег
5. Запушьте

```bash
# Обновите версию
# nexus/__init__.py: __version__ = "1.1.0"

# Создайте коммит
git add .
git commit -m "chore: release v1.1.0"

# Создайте тег
git tag v1.1.0

# Запушьте
git push origin main --tags
```

### Публикация на PyPI

```bash
# Установите twine
pip install twine

# Загрузите на PyPI
twine upload dist/*

# Или на TestPyPI (для тестирования)
twine upload --repository testpypi dist/*
```

---

## Troubleshooting

### `pip install -e .` падает

1. Убедитесь, что Python 3.9+
2. Обновите pip: `pip install --upgrade pip`
3. Проверьте, что все зависимости доступны

### Pre-commit хуки не работают

```bash
# Переустановите хуки
pre-commit uninstall
pre-commit install

# Или обновите
pre-commit autoupdate
```

### mypy показывает ошибки

1. Проверьте, что все зависимости установлены
2. Используйте `--ignore-missing-imports`
3. Добавьте type hints в код

### Тесты падают

1. Убедитесь, что Nexus установлен: `pip install -e .`
2. Проверьте зависимости: `pip install -e ".[all]"`
3. Запустите конкретный тест: `pytest tests/test_memory.py -v`

---

## См. также

- [CONTRIBUTING.md](CONTRIBUTING.md) — участие в разработке
- [TESTING.md](TESTING.md) — тестирование
- [ARCHITECTURE.md](ARCHITECTURE.md) — архитектура проекта