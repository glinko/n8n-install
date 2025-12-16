# Варианты выполнения команд на хосте (сервере)

## Проблема
Claude CLI выполняется внутри контейнера `claude-code-console`, где нет доступа к системным командам хоста (ping, traceroute, mtr и т.д.) и результаты команд относятся к контейнеру, а не к хосту.

## Решения

### Вариант 1: Docker контейнер с доступом к хосту (РЕКОМЕНДУЕТСЯ)
**Преимущества:**
- Простота реализации
- Безопасность (изоляция через Docker)
- Не требует дополнительных сервисов

**Реализация:**
Использовать Docker API из `tg-bot` для запуска временного контейнера с доступом к хосту:
- `--network host` - доступ к сетевому стеку хоста
- `--privileged` - доступ к системным ресурсам
- `--rm` - автоматическое удаление после выполнения

**Пример команды:**
```bash
docker run --rm --network host --privileged alpine:latest ping -c 4 8.8.8.8
```

### Вариант 2: Скрипт-обертка на хосте
**Преимущества:**
- Полный контроль над выполнением
- Можно добавить логирование и ограничения
- Безопасность через whitelist команд

**Реализация:**
Создать скрипт `/home/user/n8n-install/scripts/host-exec.sh` на хосте, который:
- Принимает команду как аргумент
- Выполняет её на хосте
- Возвращает результат

**Пример:**
```bash
#!/bin/bash
# /home/user/n8n-install/scripts/host-exec.sh
ALLOWED_COMMANDS=("ping" "traceroute" "mtr" "netstat" "ss" "ip" "curl" "wget")
CMD="$1"
shift
ARGS="$@"

# Проверка whitelist (опционально)
if [[ ! " ${ALLOWED_COMMANDS[@]} " =~ " ${CMD} " ]]; then
    echo "Error: Command '$CMD' not allowed"
    exit 1
fi

# Выполнение на хосте
exec "$CMD" $ARGS
```

### Вариант 3: Отдельный сервис-API на хосте
**Преимущества:**
- Централизованное управление
- Логирование всех команд
- Можно добавить аутентификацию

**Реализация:**
Простой Python/Node.js сервис на хосте, который:
- Слушает на localhost:PORT
- Принимает команды через HTTP API
- Выполняет и возвращает результат

### Вариант 4: Использование nsenter
**Преимущества:**
- Прямой доступ к namespace хоста
- Минимальные изменения

**Реализация:**
Использовать `nsenter` для выполнения команд в namespace хоста через Docker.

## Рекомендация

**Вариант 1 (Docker с --network host)** - самый простой и безопасный:
1. `tg-bot` уже имеет доступ к Docker socket
2. Не требует установки дополнительных сервисов
3. Изоляция через Docker
4. Легко реализовать

**Вариант 2 (Скрипт-обертка)** - если нужен больший контроль:
1. Создать скрипт на хосте
2. Вызывать через `docker exec` на специальном контейнере или через SSH

## Пример реализации (Вариант 1)

```python
async def execute_host_command(command: str, args: list[str] = None) -> tuple[str, bool]:
    """
    Execute command on host using Docker with --network host and --privileged.
    Returns (output, success).
    """
    try:
        client = docker.from_env()
        
        # Build command
        cmd = [command]
        if args:
            cmd.extend(args)
        
        # Run in temporary container with host network access
        container = client.containers.run(
            image='alpine:latest',  # или другой образ с нужными утилитами
            command=cmd,
            network_mode='host',
            privileged=True,
            remove=True,  # auto-remove after execution
            detach=False,
            stdout=True,
            stderr=True
        )
        
        # Get output
        output = container.decode('utf-8', errors='replace')
        return (output, True)
    except Exception as e:
        return (f"Error: {str(e)}", False)
```

## Безопасность

Для всех вариантов рекомендуется:
1. **Whitelist команд** - разрешать только безопасные команды
2. **Ограничение аргументов** - проверять аргументы команд
3. **Таймауты** - устанавливать максимальное время выполнения
4. **Логирование** - записывать все выполняемые команды
