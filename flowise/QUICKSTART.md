# Flowise Quick Start Guide

Быстрый старт для использования Universal AI Assistant в вашем n8n-install проекте.

## 🚀 5-минутная установка

### Шаг 1: Получите пароли

```bash
cd /home/user/n8n-install

# Получите необходимые пароли из .env
export POSTGRES_PASS=$(grep "^POSTGRES_PASSWORD=" .env | cut -d'=' -f2)
export REDIS_PASS=$(grep "^REDIS_PASSWORD=" .env | cut -d'=' -f2)
export TG_BOT_TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" .env | cut -d'=' -f2)

echo "PostgreSQL Password: $POSTGRES_PASS"
echo "Redis Password: $REDIS_PASS"
echo "Telegram Bot Token: $TG_BOT_TOKEN"
```

### Шаг 2: Откройте Flowise

```bash
# Проверьте что Flowise запущен
docker ps | grep flowise

# Откройте в браузере
# URL зависит от вашего FLOWISE_HOSTNAME в .env
# Обычно: https://flowise.yourdomain.com
```

### Шаг 3: Импортируйте Custom Tools

В Flowise UI:

1. **Tools** → **Custom Tools** → **Import**
2. Загрузите по очереди:
   - `flowise/n8n_workflow_executor-CustomTool.json`
   - `flowise/postgres_query_executor-CustomTool.json`
   - `flowise/telegram_bot_manager-CustomTool.json`
   - `flowise/redis_cache_manager-CustomTool.json`

### Шаг 4: Настройте переменные

**Settings** → **Variables** → **Add Variable**

```bash
# Обязательные переменные
postgres_password=<ВАШ_POSTGRES_PASSWORD>
telegram_bot_token=<ВАШ_TELEGRAM_BOT_TOKEN>

# Опциональные (defaults работают)
postgres_host=postgres
postgres_port=5432
postgres_db=postgres
postgres_user=postgres

redis_host=redis
redis_port=6379
redis_password=<ВАШ_REDIS_PASSWORD_ИЛИ_ПУСТО>

# n8n webhooks (настроите позже)
n8n_default_webhook=http://n8n:5678/webhook/default
```

### Шаг 5: Импортируйте Agentflow

1. **Agentflows** → **Import**
2. Загрузите `flowise/Universal_AI_Assistant_Agentflow.json`
3. Откройте agentflow
4. Проверьте подключения (все линии должны быть зелеными)
5. Нажмите **Save**

### Шаг 6: Тестируйте! 🎉

Нажмите **Chat** в правом верхнем углу и попробуйте:

```
Show me the list of users from the database
```

```
Get bot statistics
```

```
Cache this data: "test" with key "my-test" for 60 seconds
```

## 📋 Быстрые примеры

### Пример 1: Получить пользователей
```
Query the database: show me all users with role 'superadmin'
```

### Пример 2: Отправить Telegram сообщение
```
Send a Telegram message to chat_id 123456789: "Hello from AI assistant!"
```

### Пример 3: Статистика бота
```
Get Telegram bot statistics: total users, events today, and users by role
```

### Пример 4: Кэширование
```
Save this data to Redis with key "user:stats" for 1 hour: {"users": 100, "active": 50}
```

### Пример 5: Проверка кэша
```
Check if Redis key "user:stats" exists and show me its TTL
```

## 🔧 Создание n8n Webhooks

Для полной функциональности создайте workflows в n8n:

### 1. Default Webhook (универсальный)

**Workflow:**
1. **Webhook Trigger** → Path: `/webhook/default`, Method: POST
2. **Function Node** → Обработка входящих данных
3. **Response** → Возврат результата

**Пример обработки:**
```javascript
// Function Node
return [{
  json: {
    status: 'success',
    received: items[0].json,
    timestamp: new Date().toISOString()
  }
}];
```

### 2. Telegram Message Webhook

**Workflow:**
1. **Webhook Trigger** → Path: `/webhook/telegram-message`
2. **Telegram Send Message Node**
   - Chat ID: `{{$json.input.chat_id}}`
   - Text: `{{$json.input.text}}`
3. **Response**

### 3. Query Processor Webhook

**Workflow:**
1. **Webhook Trigger** → Path: `/webhook/query-processor`
2. **Postgres Node** → Execute query from webhook
3. **Function Node** → Format result
4. **Response**

## 🎯 Продвинутые примеры

### Комплексный анализ

```
Analyze our user base:
1. Get total user count
2. Group users by role
3. Find users who joined today
4. Cache the results for 30 minutes
5. Give me a summary
```

### Автоматизация с n8n

```
Execute the 'data_extraction' workflow with this data:
{
  "text": "Extract: John Doe, email john@example.com, registered 2024-01-15",
  "fields": ["name", "email", "date"]
}
```

### Мониторинг и уведомления

```
Check bot activity:
1. Get events count for today
2. If more than 100 events, send alert to all superadmins
3. Cache the alert status
```

## ⚠️ Важные замечания

1. **Безопасность паролей**: Храните переменные Flowise в секрете
2. **PostgreSQL**: Только SELECT запросы разрешены для безопасности
3. **Redis TTL**: Всегда устанавливайте TTL для временных данных
4. **n8n webhooks**: Настройте аутентификацию для production

## 🐛 Быстрое решение проблем

### Инструмент не работает
```bash
# Проверьте логи Flowise
docker compose -p localai logs -f flowise | tail -50

# Проверьте переменные
# В Flowise UI: Settings → Variables
```

### Ошибка подключения к БД
```bash
# Проверьте PostgreSQL
docker exec postgres psql -U postgres -c "SELECT 1"

# Проверьте пароль
grep POSTGRES_PASSWORD /home/user/n8n-install/.env
```

### n8n webhook не отвечает
```bash
# Проверьте n8n
docker ps | grep n8n

# Проверьте webhook в n8n UI
# Workflows → Ваш workflow → Test Workflow
```

## 📚 Следующие шаги

1. **Прочитайте [README.md](README.md)** для полной документации
2. **Создайте свои custom tools** на основе примеров
3. **Настройте n8n workflows** для автоматизации
4. **Интегрируйте с Qdrant** для RAG возможностей

## 🎓 Полезные SQL запросы

```sql
-- Все пользователи
SELECT * FROM users ORDER BY created_at DESC LIMIT 10;

-- Статистика по ролям
SELECT role, COUNT(*) FROM users GROUP BY role;

-- Активность за сегодня
SELECT COUNT(*) FROM user_events WHERE created_at >= CURRENT_DATE;

-- Активные пункты меню
SELECT * FROM menu_items WHERE enabled = true ORDER BY sort_order;

-- События конкретного пользователя
SELECT * FROM user_events WHERE telegram_id = 123456789
ORDER BY created_at DESC LIMIT 20;
```

## 💡 Советы

1. **Используйте кэш** для часто запрашиваемых данных
2. **Группируйте запросы** в один для эффективности
3. **Тестируйте инструменты** по отдельности перед использованием в агенте
4. **Мониторьте логи** при разработке новых интеграций

---

Готово! Теперь у вас есть мощный AI ассистент с доступом ко всем сервисам проекта! 🚀
