# Выполнение команд на хосте через Claude CLI

## Реализация через nsenter

### Что сделано:

1. **Создан скрипт-обертка** `/home/user/n8n-install/scripts/host-exec-nsenter.sh`:
   - Использует `nsenter` для выполнения команд в namespace хоста
   - Доступен в контейнере как `/usr/local/bin/host-exec`
   - Автоматически монтируется в контейнер через docker-compose
   - Использует fallback без IPC namespace, если полный доступ недоступен

2. **Обновлен docker-compose.yml**:
   - Добавлен `pid: host` для доступа к PID namespace хоста
   - Добавлен `privileged: true` для доступа к namespace хоста через nsenter
   - Скрипт смонтирован в контейнер как `/usr/local/bin/host-exec`

### Как использовать:

Claude CLI может выполнять команды на хосте, используя скрипт `host-exec`:

**В Claude CLI сессии:**
```
Выполни команду host-exec ping -c 4 8.8.8.8 на хосте
host-exec traceroute google.com
host-exec df -h
host-exec netstat -tuln
host-exec ip addr show
```

Claude CLI будет использовать Bash tool для выполнения команды `host-exec`, которая в свою очередь выполнит команду на хосте через nsenter.

### Технические детали:

- `nsenter -t 1`: Использует PID 1 (init процесс хоста) как точку входа
- `-m -u -n -p`: Входит в основные namespaces хоста:
  - `-m`: mount namespace (файловая система хоста)
  - `-u`: UTS namespace (hostname хоста)
  - `-n`: network namespace (сеть хоста) - **критично для сетевых команд**
  - `-p`: PID namespace (процессы хоста)
- IPC namespace (`-i`) исключен из fallback, так как требует дополнительных прав

### Требования:

- Контейнер должен быть запущен с `--pid=host` (реализовано через `pid: host` в docker-compose)
- Контейнер должен быть запущен с `--privileged` (реализовано через `privileged: true`)
- В контейнере должен быть установлен `nsenter` (обычно входит в `util-linux`)

### Безопасность:

- Команды выполняются с правами пользователя контейнера (1001:1001) на хосте
- Для выполнения привилегированных команд может потребоваться `sudo` (если настроен)
- Рекомендуется использовать whitelist разрешенных команд в Claude CLI настройках

### Примеры использования в Claude CLI:

1. **Сетевые команды:**
   ```
   host-exec ping -c 4 8.8.8.8
   host-exec traceroute google.com
   host-exec netstat -tuln
   ```

2. **Системные команды:**
   ```
   host-exec df -h
   host-exec free -h
   host-exec uptime
   ```

3. **Информация о системе:**
   ```
   host-exec hostname
   host-exec uname -a
   host-exec ip addr show
   ```

### Альтернативные варианты:

Если `nsenter` недоступен или не работает, можно использовать:
1. Docker API (как в `host_executor.py` для Telegram бота) - **уже реализовано через префикс !host**
2. SSH на хост (требует настройки SSH)
3. Специальный контейнер с `--network host --privileged`

### Примечания:

- Скрипт автоматически пытается использовать все namespaces, но при ошибке переключается на режим без IPC namespace
- Для полного доступа может потребоваться запуск контейнера от root, но это не рекомендуется по соображениям безопасности
