# Лучшие практики

> 🔙 Назад → [README.md](README.md)

Рекомендации по эффективному использованию Nexus.

## Оглавление

- [Структурирование промптов](#структурирование-промптов)
- [Управление контекстом](#управление-контекстом)
- [Кэширование](#кэширование)
- [Безопасность](#безопасность)
- [Производительность](#производительность)
- [Разработка](#разработка)

---

## Структурирование промптов

### Будьте конкретны

❌ Плохо:
```bash
nexus run "Расскажи о Python"
```

✅ Хорошо:
```bash
nexus run "Объясни разницу между списком и кортежем в Python 3.11 с примерами кода"
```

### Используйте системные промпты

Настройте поведение LLM через конфиг:

```yaml
system_prompt: "Ты — опытный Python-разработчик. Отвечай кратко, приводи примеры кода. Используй Python 3.11+."
```

### Добавляйте контекст

```bash
# Загрузите документацию
nexus run "Объясни этот API: https://docs.python.org/3/library/asyncio.html"

# Загрузите код
nexus run "Проанализируй этот код: https://example.com/script.py"
```

### Используйте web-поиск для актуальной информации

```bash
nexus run "Какие нововведения в Python 3.13?" --search
```

---

## Управление контекстом

### Ограничивайте историю

```yaml
# Для быстрых ответов
conversation_history_size: 3

# Для длинных сессий
conversation_history_size: 7
```

### Очищайте контекст при необходимости

```bash
# Начать новую сессию
nexus cache-clear

# Или используйте --no-cache для одноразовых запросов
nexus run "Уникальный вопрос" --no-cache
```

### Загружайте только нужный контент

```yaml
# Ограничьте размер загружаемого контента
max_content_length: 30000  # вместо 50000

# Настройте порог суммаризации
summarize_threshold: 20000
```

---

## Кэширование

### Используйте кэш для повторных запросов

```yaml
# Включите кэш
cache_ttl: 3600  # 1 час

# Увеличьте размер кэша
max_cache_size_mb: 100
```

### Отключайте кэш для уникальных запросов

```bash
nexus run "Актуальные новости" --no-cache
```

### Очищайте кэш регулярно

```bash
# Раз в неделю
nexus cache-clear

# Или настройте автоочистку
max_cache_size_mb: 50  # автоматическая очистка при превышении
```

---

## Безопасность

### Храните API-ключи безопасно

```bash
# Используйте .env файл
mkdir -p ~/.nexus
echo "GROQ_API_KEY=gsk_ваш_ключ" > ~/.nexus/.env

# Или переменные окружения
export GROQ_API_KEY=gsk_ваш_ключ
```

### Не коммитьте API-ключи

Убедитесь, что `.gitignore` содержит:

```
.env
~/.nexus/
```

### Ограничьте права API-ключей

- Используйте ключи с минимальными правами
- Регулярно ротируйте ключи
- Мониторьте использование

### Проверяйте URL перед загрузкой

```bash
# Nexus проверяет URL автоматически, но вы можете проверить вручную
curl -I https://example.com
```

---

## Производительность

### Выбирайте правильную модель

| Задача | Модель |
|--------|--------|
| Быстрые ответы | `llama-3.1-8b-instant` |
| Общий диалог | `llama-3.3-70b-versatile` |
| Сложные задачи | `gpt-4o` или `claude-sonnet-4-20250514` |

### Оптимизируйте настройки

```yaml
# Быстрые ответы
max_tokens: 1024
conversation_history_size: 2

#高质量 ответы
max_tokens: 8192
conversation_history_size: 7
```

### Используйте web-поиск точечно

```bash
# Не включайте поиск глобально, если он нужен не всегда
web_search:
  enabled: false

# Включайте для конкретных запросов
nexus run "Актуальные новости" --search
```

---

## Разработка

### Используйте виртуальные окружения

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[all]"
```

### Настройте pre-commit

```bash
pip install pre-commit
pre-commit install
```

### Пишите тесты

```bash
# Запуск тестов
python -m pytest tests/ -v

# С покрытием
python -m pytest tests/ --cov=nexus --cov-report=html
```

### Следите за стилем кода

```bash
# Форматирование
black nexus/ tests/

# Сортировка импортов
isort nexus/ tests/

# Проверка стиля
flake8 nexus/ tests/
```

---

## Шпаргалка

### Частые команды

```bash
# Быстрый запрос
nexus run "Вопрос"

# Запрос с поиском
nexus run "Вопрос" --search

# Интерактивный режим
nexus interactive

# Поиск
nexus search "запрос"

# Статус
nexus status

# Диагностика
nexus debug

# Очистка
nexus cache-clear
```

### Частые настройки

```yaml
# Быстрый старт
provider: "groq"
groq_model: "llama-3.3-70b-versatile"
temperature: 0.7
max_tokens: 4096

# Длинный контекст
conversation_history_size: 10
max_content_length: 100000

# Безопасность
cache_ttl: 3600
max_cache_size_mb: 50
```

---

## См. также

- [PERFORMANCE.md](PERFORMANCE.md) — тюнинг производительности
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) — справочник конфигурации
- [SECURITY.md](SECURITY.md) — политика безопасности