# Интеграции

> 🔙 Назад → [README.md](README.md)

Гайды по интеграции Nexus с IDE, редакторами и другими системами.

## Оглавление

- [VS Code](#vs-code)
- [JetBrains (PyCharm, IntelliJ)](#jetbrains)
- [Neovim / Doom Emacs](#neovim--doom-emacs)
- [Terminal и оболочки](#terminal-и-оболочки)
- [Obsidian](#obsidian)
- [Raycast / Alfred](#raycast--alfred)
- [CI/CD](#cicd)
- [Docker и Kubernetes](#docker-и-kubernetes)
- [Другие MCP-клиенты](#другие-mcp-клиенты)

---

## VS Code

### Через MCP (Claude Desktop / Cursor / Continue)

Nexus можно использовать как MCP-сервер в VS Code через расширения:

#### Continue (рекомендуется)

1. Установите расширение [Continue](https://marketplace.visualstudio.com/items?itemName=Continue.continue)
2. Настройте MCP в `~/.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "nexus",
      "command": "nexus",
      "args": ["mcp"]
    }
  ]
}
```

3. Перезапустите VS Code
4. Используйте Nexus через панель Continue

#### Claude Code

1. Установите [Claude Code](https://claude.ai/code)
2. Настройте MCP сервер
3. Nexus будет доступен как инструмент

#### Cursor

1. Установите [Cursor](https://cursor.sh)
2. Настройте MCP в `~/.cursor/mcp.json`:

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

### Как терминальный инструмент

Используйте Nexus напрямую в терминале VS Code:

```bash
# Откройте терминал в VS Code (Ctrl+`)
nexus run "Что такое Python?"
nexus interactive
nexus search "последние новости"
```

---

## JetBrains

### PyCharm / IntelliJ IDEA

1. Настройте Python-интерпретатор с Nexus
2. Используйте Nexus через терминал IDE
3. Или настройте MCP через плагин Continue

### Настройка терминала

```bash
# В терминале JetBrains
nexus run "Вопрос"
nexus interactive
```

---

## Neovim / Doom Emacs

### Neovim

Используйте Nexus через встроенный терминал:

```vim
" Открыть терминал
:terminal

" Запустить Nexus
nexus run "Вопрос"
nexus interactive
```

### Doom Emacs

```elisp
;; Используйте vterm для терминала
;; M-x vterm
;; nexus run "Вопрос"
```

### Через MCP

Если вы используете [Avante.nvim](https://github.com/yetone/avante.nvim) или аналогичные плагины, настройте MCP:

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

---

## Terminal и оболочки

### Bash / Zsh

Добавьте алиас для удобства:

```bash
# ~/.bashrc или ~/.zshrc
alias ai='nexus run'
alias ai-search='nexus run --search'
alias ai-interactive='nexus interactive'
```

```bash
# Использование
ai "Что такое Python?"
ai-search "Последние новости"
ai-interactive
```

### PowerShell

```powershell
# Добавьте в $PROFILE
function Invoke-Nexus { nexus run @args }
Set-Alias -Name ai -Value Invoke-Nexus
```

```powershell
# Использование
ai "Что такое Python?"
```

### Fish

```fish
# ~/.config/fish/config.fish
alias ai 'nexus run'
alias ai-search 'nexus run --search'
alias ai-interactive 'nexus interactive'
```

---

## Obsidian

### Через MCP

Если вы используете Obsidian с MCP-плагинами:

1. Установите MCP-плагин для Obsidian
2. Настройте Nexus как MCP-сервер
3. Используйте Nexus для генерации заметок

### Через скрипт

Создайте скрипт для автоматического саммари:

```python
#!/usr/bin/env python3
"""Скрипт для саммари заметок Obsidian."""

import os
import sys
from nexus.core.agent import NexusAgent

agent = NexusAgent(api_key="your_key", model="llama-3.3-70b-versatile")

vault_path = os.path.expanduser("~/Documents/MyVault")
note_path = sys.argv[1] if len(sys.argv) > 1 else "README.md"

full_path = os.path.join(vault_path, note_path)

if not os.path.exists(full_path):
    print(f"Note not found: {full_path}")
    sys.exit(1)

with open(full_path, 'r', encoding='utf-8') as f:
    content = f.read()

result = agent.generate_response(
    f"Сделай краткое саммари этой заметки:\n\n{content[:5000]}",
    system_prompt="Ты помощник для заметок. Кратко и по делу."
)

print(result["text"])
```

---

## Raycast / Alfred

### Raycast

Если вы используете Raycast на macOS, можно настроить Nexus как команду:

1. Создайте скрипт:
```bash
#!/bin/bash
# ~/.local/bin/nexus-raycast
nexus run "$1"
```

2. Настройте Raycast для вызова скрипта

### Alfred

Создайте Workflow для Alfred:

```json
{
  "alfredworkflow": {
    "uid": "com.nexus.query",
    "name": "Nexus AI Query",
    "description": "Ask Nexus a question",
    "objects": [
      {
        "uid": "nexus-query",
        "type": "keyword",
        "keyword": "nexus",
        "subtitle": "Ask Nexus a question",
        "arg": "{query}",
        "config": {
          "script": "nexus run \"{query}\""
        }
      }
    ]
  }
}
```

---

## CI/CD

### GitHub Actions

```yaml
# .github/workflows/nexus.yml
name: Nexus AI

on:
  issues:
    types: [opened, edited]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install Nexus
        run: pip install nexus
      
      - name: Analyze issue
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
        run: |
          nexus run "Проанализируй этот issue и предложи решение: $(cat issue.txt)" > analysis.md
```

### GitLab CI

```yaml
# .gitlab-ci.yml
nexus-analyze:
  stage: analyze
  image: python:3.11
  script:
    - pip install nexus
    - nexus run "Проанализируй изменения" > analysis.md
  artifacts:
    paths:
      - analysis.md
```

---

## Docker и Kubernetes

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

### Kubernetes

```yaml
# nexus-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nexus
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nexus
  template:
    metadata:
      labels:
        app: nexus
    spec:
      containers:
      - name: nexus
        image: nexus:latest
        env:
        - name: GROQ_API_KEY
          valueFrom:
            secretKeyRef:
              name: nexus-secrets
              key: groq-api-key
```

### systemd сервис

```ini
# /etc/systemd/system/nexus.service
[Unit]
Description=Nexus MCP Server
After=network.target

[Service]
Type=simple
User=nexus
Environment=GROQ_API_KEY=your_key
ExecStart=/usr/local/bin/nexus mcp
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Управление сервисом
sudo systemctl start nexus
sudo systemctl stop nexus
sudo systemctl enable nexus
sudo systemctl status nexus
```

---

## Другие MCP-клиенты

### Any MCP Client

Любой MCP-клиент, поддерживающий stdio, может работать с Nexus:

```bash
# Стандартный запуск
nexus mcp

# С явным указанием API-ключа
GROQ_API_KEY=your_key nexus mcp
```

### Конфигурация для MCP-клиентов

```json
{
  "mcpServers": {
    "nexus": {
      "command": "nexus",
      "args": ["mcp"],
      "env": {
        "GROQ_API_KEY": "your_key"
      }
    }
  }
}
```

---

## См. также

- [MCP.md](MCP.md) — MCP-сервер
- [CLI_REFERENCE.md](CLI_REFERENCE.md) — справочник CLI
- [ADVANCED_USAGE.md](ADVANCED_USAGE.md) — продвинутое использование