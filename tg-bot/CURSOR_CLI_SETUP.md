# Cursor CLI Integration

## Обзор

Интеграция Cursor CLI в Telegram бота, аналогичная Claude CLI. Позволяет создавать сессии, выполнять запросы через Cursor CLI и управлять сессиями через Telegram интерфейс.

## Структура

### База данных

- **cursor_cli_sessions**: Хранит сессии пользователей
  - `id`: Уникальный идентификатор
  - `user_id`: ID пользователя Telegram
  - `session_name`: Название сессии
  - `uuid`: Session ID от Cursor CLI (для возобновления сессии)
  - `created_at`, `updated_at`: Timestamps

- **cursor_cli_messages**: Хранит историю сообщений
  - `id`: Уникальный идентификатор
  - `session_id`: ID сессии (nullable, SET NULL при удалении сессии)
  - `user_id`: ID пользователя
  - `query`: Запрос пользователя
  - `response`: Ответ от Cursor CLI
  - `flags_used`: Использованные флаги
  - `created_at`: Timestamp с индексом

### Docker контейнер

Сервис `cursor-code-console` в `docker-compose.yml`:
- Образ: `cursor-cli-cursor-code-console:latest`
- Контейнер: `cursor-code-console`
- Profile: `cursor`
- Настройки:
  - `pid: host` - доступ к PID namespace хоста
  - `privileged: true` - для выполнения команд через nsenter
  - Volumes:
    - `./:/home/cursor/workspace` - рабочая директория
    - `./.cursorcli:/home/cursor/.config/cursor` - конфигурация Cursor
    - `./.cursorcli-data:/home/cursor/.cursor` - данные Cursor
    - `./scripts/host-exec-nsenter.sh:/usr/local/bin/host-exec:ro` - скрипт для выполнения команд на хосте

### Команды Cursor CLI

**Создание сессии:**
Сессии в Cursor CLI создаются автоматически при первом запросе. Для инициализации используется:
```bash
cursor-agent -p --output-format json "Initializing session"
```
Chat-id извлекается из JSON ответа (поле `chat_id`, `chatId`, или `id`).

**Выполнение запроса:**
```bash
# Для новой сессии (без chat-id):
cursor-agent -p "QUERY" [FLAGS]

# Для существующей сессии (с chat-id):
cursor-agent -p "QUERY" --resume CHAT_ID [FLAGS]
```

**Завершение сессии:**
Cursor CLI не требует явного завершения сессий - они управляются автоматически. Функция `end_cursor_session()` оставлена для API совместимости.

## Использование

### Через Telegram бота

1. Перейти в меню **Sysopka** → **CursorCLI**
2. Создать новую сессию (кнопка "New Session")
3. Ввести запрос для сессии
4. Использовать команды:
   - `/exit` - выйти из режима Cursor CLI
   - `/delete` - удалить текущую сессию (сохраняет историю сообщений)
   - `!host <команда>` или `#host <команда>` - выполнить команду на хосте

### Выполнение команд на хосте

Cursor CLI поддерживает выполнение команд на хосте через префиксы:
- `!host <команда>` 
- `#host <команда>`
- `!exec <команда>`
- `#exec <команда>`

Команды выполняются через скрипт `host-exec-nsenter.sh`, который использует `nsenter` для доступа к namespace хоста.

## Интеграция в меню

Элемент меню добавлен в `MENU_STRUCTURE`:
```python
{
    "key": "SYSOPKA_CURSORCLI",
    "label": "CursorCLI",
    "parent_key": "SYSOPKA",
    "roles": None,
    "sort_order": 20,
    "is_active": True,
    "action_type": "cursor_cli_submenu",
    "action_config": None,
}
```

## Файлы

- `tg-bot/app/models.py` - модели `CursorCLISession` и `CursorCLIMessage`
- `tg-bot/app/states/cursor_cli.py` - FSM состояния
- `tg-bot/app/routers/cursor_cli.py` - основной роутер с бизнес-логикой
- `tg-bot/app/main.py` - регистрация роутера и миграции БД
- `tg-bot/app/routers/start.py` - интеграция с меню
- `docker-compose.yml` - конфигурация Docker сервиса

## Миграции БД

Миграции выполняются автоматически при старте приложения в функции `on_startup()`:
- Создание таблиц через SQLAlchemy metadata
- Добавление unique constraint для `(user_id, session_name)`
- Настройка nullable `session_id` с `ON DELETE SET NULL` для сохранения истории при удалении сессии
