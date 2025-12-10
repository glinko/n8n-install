# Flowise Agentflows and Custom Tools

Коллекция готовых агентов и инструментов для интеграции Flowise с n8n-install проектом.

## 📦 Содержимое

### 🤖 Agentflows

#### Universal AI Assistant (`Universal_AI_Assistant_Agentflow.json`)
Универсальный AI ассистент с полной интеграцией всех сервисов проекта.

**Возможности:**
- Выполнение n8n workflows
- Запросы к PostgreSQL (read-only)
- Управление Telegram ботом
- Кэширование в Redis
- Поиск в интернете (SerpAPI)
- Память разговора

**Используемые инструменты:**
- n8n Workflow Executor
- PostgreSQL Query Executor
- Telegram Bot Manager
- Redis Cache Manager
- Web Search (SerpAPI)

#### Web Search + n8n Agent (`Web Search + n8n Agent Chatflow.json`)
Агент с возможностью поиска в интернете и интеграцией с n8n.

### 🛠️ Custom Tools

#### 1. n8n Workflow Executor (`n8n_workflow_executor-CustomTool.json`)
Выполнение n8n workflows через webhook.

**Параметры:**
- `workflow_name`: Имя workflow (send_telegram_message, process_user_query, create_workflow, data_extraction)
- `payload`: JSON данные для workflow (опционально)

**Требуемые переменные Flowise:**
- `n8n_telegram_webhook`
- `n8n_query_webhook`
- `n8n_create_webhook`
- `n8n_extraction_webhook`
- `n8n_default_webhook`

**Пример использования:**
```
Execute workflow 'send_telegram_message' with payload {"chat_id": 123456789, "text": "Hello from AI!"}
```

#### 2. PostgreSQL Query Executor (`postgres_query_executor-CustomTool.json`)
Безопасное выполнение SELECT запросов к PostgreSQL.

**Параметры:**
- `query`: SQL запрос (только SELECT)
- `params`: Параметры запроса как JSON array (опционально)

**Требуемые переменные Flowise:**
- `postgres_host` (default: postgres)
- `postgres_port` (default: 5432)
- `postgres_db` (default: postgres)
- `postgres_user` (default: postgres)
- `postgres_password` (обязательно)

**Доступные таблицы:**
- `users` - пользователи Telegram бота
- `user_events` - логи действий пользователей
- `menu_items` - элементы меню бота
- n8n workflow таблицы

**Примеры запросов:**
```sql
-- Получить всех пользователей
SELECT * FROM users LIMIT 10

-- Статистика по ролям
SELECT role, COUNT(*) as count FROM users GROUP BY role

-- События за сегодня
SELECT * FROM user_events WHERE created_at >= CURRENT_DATE

-- Активное меню
SELECT * FROM menu_items WHERE enabled = true ORDER BY sort_order
```

#### 3. Telegram Bot Manager (`telegram_bot_manager-CustomTool.json`)
Управление Telegram ботом и пользователями.

**Параметры:**
- `action`: Действие (send_message, get_user, get_stats, list_users, update_menu)
- `params`: Параметры действия как JSON

**Требуемые переменные Flowise:**
- `postgres_host`, `postgres_port`, `postgres_db`, `postgres_user`, `postgres_password`
- `telegram_bot_token` (для отправки сообщений)

**Примеры действий:**

```javascript
// Отправить сообщение
action: "send_message"
params: {"chat_id": 123456789, "text": "Hello!", "parse_mode": "HTML"}

// Получить информацию о пользователе
action: "get_user"
params: {"telegram_id": 123456789}

// Статистика бота
action: "get_stats"
params: {}

// Список пользователей
action: "list_users"
params: {"role": "superadmin", "limit": 10}

// Обновить пункт меню
action: "update_menu"
params: {"key": "PROFILE", "label": "My Profile", "enabled": true}
```

#### 4. Redis Cache Manager (`redis_cache_manager-CustomTool.json`)
Управление кэшем в Redis.

**Параметры:**
- `operation`: Операция (get, set, delete, exists, ttl, keys)
- `key`: Ключ Redis
- `value`: Значение для установки (для set)
- `ttl_seconds`: Время жизни в секундах (для set)

**Требуемые переменные Flowise:**
- `redis_host` (default: redis)
- `redis_port` (default: 6379)
- `redis_password` (опционально)

**Примеры операций:**

```javascript
// Сохранить данные на 1 час
operation: "set"
key: "user:123:profile"
value: '{"name": "John", "role": "user"}'
ttl_seconds: 3600

// Получить данные
operation: "get"
key: "user:123:profile"

// Проверить существование
operation: "exists"
key: "user:123:profile"

// Узнать TTL
operation: "ttl"
key: "user:123:profile"

// Найти ключи по паттерну
operation: "keys"
key: "user:*"

// Удалить ключ
operation: "delete"
key: "user:123:profile"
```

### 📝 Существующие инструменты (legacy)

- `create_google_doc-CustomTool.json` - Создание Google Docs
- `get_postgres_tables-CustomTool.json` - Получение списка таблиц PostgreSQL
- `send_slack_message_through_n8n-CustomTool.json` - Отправка сообщений в Slack через n8n
- `summarize_slack_conversation-CustomTool.json` - Саммаризация Slack переписки

## 🚀 Установка

### 1. Импорт Custom Tools

В Flowise UI:
1. Перейдите в **Tools** → **Custom Tools**
2. Нажмите **Import**
3. Загрузите JSON файлы инструментов:
   - `n8n_workflow_executor-CustomTool.json`
   - `postgres_query_executor-CustomTool.json`
   - `telegram_bot_manager-CustomTool.json`
   - `redis_cache_manager-CustomTool.json`

### 2. Настройка переменных

В Flowise перейдите в **Settings** → **Variables** и добавьте:

```bash
# n8n Webhooks
n8n_telegram_webhook=http://n8n:5678/webhook/telegram-message
n8n_query_webhook=http://n8n:5678/webhook/query-processor
n8n_create_webhook=http://n8n:5678/webhook/workflow-creator
n8n_extraction_webhook=http://n8n:5678/webhook/data-extractor
n8n_default_webhook=http://n8n:5678/webhook/default

# PostgreSQL
postgres_host=postgres
postgres_port=5432
postgres_db=postgres
postgres_user=postgres
postgres_password=YOUR_POSTGRES_PASSWORD

# Redis
redis_host=redis
redis_port=6379
redis_password=YOUR_REDIS_PASSWORD

# Telegram Bot
telegram_bot_token=YOUR_BOT_TOKEN

# SerpAPI (для веб-поиска)
serp_api_key=YOUR_SERP_API_KEY
```

**Получение паролей из .env:**
```bash
cd /home/user/n8n-install
cat .env | grep POSTGRES_PASSWORD
cat .env | grep REDIS_PASSWORD
cat .env | grep TELEGRAM_BOT_TOKEN
```

### 3. Импорт Agentflow

1. Перейдите в **Agentflows** в Flowise UI
2. Нажмите **Import**
3. Загрузите `Universal_AI_Assistant_Agentflow.json`
4. Настройте параметры:
   - Проверьте что все Custom Tools импортированы
   - Убедитесь что Ollama модель доступна
   - При необходимости измените модель (llama3.2, llama3, mistral и т.д.)

### 4. Создание n8n Webhooks

Создайте workflows в n8n с webhook triggers:

```
/webhook/telegram-message    - Отправка Telegram сообщений
/webhook/query-processor      - Обработка пользовательских запросов
/webhook/workflow-creator     - Создание новых workflows
/webhook/data-extractor       - Извлечение и структурирование данных
/webhook/default              - Универсальный webhook
```

## 📊 Примеры использования

### Пример 1: Анализ пользователей и отправка уведомлений

**Вопрос к агенту:**
```
Show me all superadmin users and send them a greeting message via Telegram
```

**Что сделает агент:**
1. Выполнит SQL запрос через `postgres_query_executor`:
   ```sql
   SELECT telegram_id, username, first_name FROM users WHERE role = 'superadmin'
   ```
2. Для каждого пользователя вызовет `telegram_bot_manager`:
   ```json
   {
     "action": "send_message",
     "params": {
       "chat_id": 123456789,
       "text": "Hello, admin! How can I help you today?"
     }
   }
   ```

### Пример 2: Кэширование результатов запроса

**Вопрос к агенту:**
```
Get bot statistics and cache them for 1 hour
```

**Что сделает агент:**
1. Выполнит запрос статистики через `telegram_bot_manager`:
   ```json
   {"action": "get_stats"}
   ```
2. Сохранит результат в Redis через `redis_cache_manager`:
   ```json
   {
     "operation": "set",
     "key": "bot:stats:daily",
     "value": "{...stats...}",
     "ttl_seconds": 3600
   }
   ```

### Пример 3: Триггер n8n workflow с данными

**Вопрос к агенту:**
```
Extract data from this text and process it: "User John Doe, email john@example.com, wants to subscribe"
```

**Что сделает агент:**
1. Вызовет `n8n_workflow_executor`:
   ```json
   {
     "workflow_name": "data_extraction",
     "payload": {
       "text": "User John Doe, email john@example.com, wants to subscribe",
       "extract_fields": ["name", "email", "intent"]
     }
   }
   ```

### Пример 4: Комплексный сценарий

**Вопрос к агенту:**
```
Get all users who joined today, save their count to cache, and notify admins
```

**Последовательность действий:**
1. **PostgreSQL**: Получить пользователей за сегодня
2. **Redis**: Сохранить статистику в кэш
3. **Telegram**: Отправить уведомление суперадминам
4. **n8n**: Запустить workflow для логирования

## 🔒 Безопасность

### PostgreSQL Query Executor
- ✅ Только SELECT запросы
- ✅ Блокировка опасных ключевых слов (DROP, DELETE, UPDATE и т.д.)
- ✅ Поддержка параметризованных запросов
- ⚠️ Не используйте для модификации данных - используйте n8n workflows

### Redis Cache Manager
- ✅ TTL для автоматической очистки
- ✅ Поддержка паролей
- ⚠️ Будьте осторожны с операцией `keys` на больших базах

### Telegram Bot Manager
- ✅ Прямая работа с БД через подключение
- ✅ Валидация параметров
- ⚠️ Храните TELEGRAM_BOT_TOKEN в секрете

### n8n Workflow Executor
- ✅ Маршрутизация через именованные workflows
- ✅ Метаданные запроса (sessionId, chatId, timestamp)
- ⚠️ Настройте аутентификацию на n8n webhooks

## 🐛 Troubleshooting

### Ошибка подключения к PostgreSQL
```
Error: connect ECONNREFUSED
```
**Решение:**
- Проверьте что PostgreSQL запущен: `docker ps | grep postgres`
- Убедитесь что переменные `postgres_*` настроены в Flowise
- Проверьте пароль: `docker exec postgres psql -U postgres -c "SELECT 1"`

### Ошибка подключения к Redis
```
Error: Redis connection refused
```
**Решение:**
- Проверьте что Redis запущен: `docker ps | grep redis`
- Проверьте пароль в `.env`: `grep REDIS_PASSWORD .env`

### Custom Tool не найден
```
Error: Tool not found
```
**Решение:**
- Убедитесь что Custom Tool импортирован в Flowise UI
- Проверьте что имя инструмента совпадает в agentflow и в tool файле

### n8n webhook не отвечает
```
Error: fetch failed
```
**Решение:**
- Проверьте что n8n запущен: `docker ps | grep n8n`
- Создайте workflow с webhook trigger в n8n
- Проверьте URL webhook в переменных Flowise

## 📚 Дополнительные ресурсы

- [Flowise Documentation](https://docs.flowiseai.com/)
- [n8n Documentation](https://docs.n8n.io/)
- [Custom Tools Guide](https://docs.flowiseai.com/tools/custom-tools)
- [Agent Flows Guide](https://docs.flowiseai.com/agents)

## 🤝 Контрибьюция

Добавляйте свои custom tools и agentflows в эту директорию!

**Именование файлов:**
- Custom Tools: `<tool_name>-CustomTool.json`
- Agentflows: `<AgentflowName>_Agentflow.json`

## 📝 Changelog

- **2025-12-10**: Добавлены 4 новых custom tools и Universal AI Assistant agentflow
- **Initial**: Web Search + n8n Agent и базовые custom tools
