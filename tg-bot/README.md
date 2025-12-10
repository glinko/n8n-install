# Telegram Bot для n8n-install

Мультипользовательский Telegram бот с модульной архитектурой.

## Особенности

- **Модульная структура** - новые функции добавляются как отдельные роутеры
- **Меню в БД** - структура меню хранится в PostgreSQL, управляется через команды бота
- **Роли и права** - superadmin и user с разными уровнями доступа
- **Логирование** - все действия пользователей записываются в БД для анализа
- **Интеграция** - готов к интеграции с n8n, RAGApp, Qdrant, Supabase и другими сервисами

## Структура проекта

```
tg-bot/
├── app/
│   ├── __init__.py
│   ├── config.py          # Конфигурация из .env
│   ├── db.py              # Подключение к PostgreSQL
│   ├── models.py          # SQLAlchemy модели (User, UserEvent, MenuItem)
│   ├── menu.py            # Построение меню из БД
│   ├── main.py            # Точка входа
│   ├── routers/           # Модули/роутеры
│   │   ├── start.py       # /start и обработка меню
│   │   ├── profile.py    # Профиль пользователя
│   │   ├── admin.py       # Админские команды
│   │   └── admin_menu.py # Управление меню через бота
│   └── middlewares/
│       └── user_middleware.py  # Автоматическое создание/обновление пользователей
├── requirements.txt
├── .env                   # Переменные окружения (не коммитится)
└── .env.example
```

## Настройка

1. **Получите токен бота** у @BotFather в Telegram
2. **Настройте .env файл**:
   ```bash
   cp .env.example .env
   # Отредактируйте .env и укажите:
   # - TELEGRAM_BOT_TOKEN
   # - SUPERADMIN_IDS (ваш Telegram user_id, можно узнать через @userinfobot)
   ```

3. **Запуск через Docker Compose**:
   ```bash
   cd /home/user/n8n-install
   docker compose -p localai up -d tg-bot
   ```

4. **Проверка логов**:
   ```bash
   docker compose -p localai logs -f tg-bot
   ```

## Команды для суперадмина

- `/start` - главное меню
- `/users` - список пользователей
- `/setrole <telegram_id> <role>` - изменить роль пользователя
- `/menu_list` - список элементов меню
- `/menu_add <KEY> <label> <roles> <sort_order>` - добавить пункт меню
- `/menu_set_roles <KEY> <roles>` - изменить роли для пункта меню
- `/menu_toggle <KEY>` - включить/выключить пункт меню

## Добавление новых функций

1. Создайте новый роутер в `app/routers/`
2. Добавьте обработчик в `app/routers/start.py` для нового ключа меню
3. Зарегистрируйте роутер в `app/main.py`
4. Добавьте пункт меню через команду `/menu_add` в боте

## Интеграция с сервисами

Бот работает в той же Docker-сети, что и остальные сервисы, поэтому доступны:

- `http://n8n:5678` - n8n API
- `http://ragapp:8000` - RAGApp API
- `http://qdrant:6333` - Qdrant API
- `http://postgres:5432` - PostgreSQL
- `http://redis:6379` - Redis
- `http://ollama:11434` - Ollama API

## База данных

Бот использует тот же PostgreSQL, что и n8n. Создаются таблицы:
- `users` - пользователи бота
- `user_events` - логи действий
- `menu_items` - элементы меню

